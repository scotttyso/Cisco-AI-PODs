"""Capture the cluster access details iServer prints when an install finishes, hide them from the job log, and save
them: the kubeconfig as a 0600 file, the kubeadmin password and the kubeconfig in the automation vault.

iServer prints, after "Installation finished...":

    Cluster console access
    ----------------------
    URL      : https://console-openshift-console.apps.<cluster>.<domain>
    Username : kubeadmin
    Password : <password>
    Kubeconfig
    ----------
    apiVersion: v1
    clusters: ...
"""
from __future__ import annotations

import datetime
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

KUBECONFIG_KEYS = ("apiVersion", "clusters", "contexts", "current-context", "kind", "preferences", "users", "extensions")
SECRET_VALUE = re.compile(r"((?:client-key-data|client-certificate-data|certificate-authority-data|token)\s*:\s*)\S+")
FIELD = re.compile(r"^\s*(URL|Username|Password)\s*:\s*(.*?)\s*$")
HIDDEN_NOTE = "(kubeconfig captured and hidden; see Cluster Deployment > Cluster access)"
PASSWORD_NOTE = "******** (captured; see Cluster Deployment > Cluster access)"
VAULT_PASSWORD_KEY = "kubeadmin_password"
VAULT_KUBECONFIG_KEY = "ocp_kubeconfig"
INFO_FILE = "cluster-access.json"
KUBECONFIG_FILE = "kubeconfig"


@dataclass
class AccessCapture:
    """Feed it iServer's output line by line; it returns the lines that are safe to show."""
    console_url: str = ""
    username: str = ""
    password: str = ""
    kubeconfig_lines: list[str] = field(default_factory=list)
    _state: str = "idle"

    @property
    def kubeconfig(self) -> str:
        return "\n".join(self.kubeconfig_lines) + "\n" if self.kubeconfig_lines else ""

    @property
    def captured(self) -> bool:
        return bool(self.kubeconfig_lines or self.password)

    def feed(self, line: str) -> list[str]:
        text = line.rstrip("\r\n")
        if self._state == "kubeconfig":
            if self._is_kubeconfig_line(text):
                self.kubeconfig_lines.append(text)
                return []
            self._state = "idle"
        if self._state == "kubeconfig_header":
            if text.strip() and set(text.strip()) == {"-"}:
                self._state = "kubeconfig"
                return [text, HIDDEN_NOTE]
            self._state = "idle"
        stripped = text.strip()
        if stripped == "Kubeconfig":
            self._state = "kubeconfig_header"
            return [text]
        if stripped == "Cluster console access":
            self._state = "console"
            return [text]
        if self._state == "console":
            match = FIELD.match(text)
            if match:
                name, value = match.groups()
                if name == "URL":
                    self.console_url = value
                elif name == "Username":
                    self.username = value
                else:
                    self.password = value
                    return [text[:text.index(":") + 1] + " " + PASSWORD_NOTE]
                return [text]
            if stripped and set(stripped) != {"-"}:
                self._state = "idle"
        return [SECRET_VALUE.sub(r"\1********", text)]

    @staticmethod
    def _is_kubeconfig_line(text: str) -> bool:
        if not text.strip():
            return False
        if text[0] in " \t-":
            return True
        return text.split(":", 1)[0] in KUBECONFIG_KEYS


def access_dir(host_vars_dir: Path) -> Path:
    """<environment>/auth, next to host_vars; the environment .gitignore already excludes it."""
    return Path(host_vars_dir).resolve().parent / "auth"


def kubeconfig_path(host_vars_dir: Path) -> Path:
    return access_dir(host_vars_dir) / KUBECONFIG_FILE


def write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(text)
    path.chmod(0o600)


def cluster_name(kubeconfig: str) -> str:
    try:
        data = yaml.safe_load(kubeconfig) or {}
        return str(data["clusters"][0]["name"])
    except (yaml.YAMLError, KeyError, IndexError, TypeError):
        return ""


def save_access(capture: AccessCapture, host_vars_dir: Path, vault) -> list[str]:
    """Write the kubeconfig file and the non-secret access summary, and store the secrets in the vault.

    ``vault`` is a VaultStore (or None). Returns human readable notes about what was saved or why not."""
    notes = []
    directory = access_dir(host_vars_dir)
    if capture.kubeconfig_lines:
        write_private(directory / KUBECONFIG_FILE, capture.kubeconfig)
        notes.append(f"kubeconfig saved to {directory / KUBECONFIG_FILE}")
    info = {"cluster": cluster_name(capture.kubeconfig), "console_url": capture.console_url,
            "username": capture.username, "captured_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}
    write_private(directory / INFO_FILE, json.dumps(info, indent=2) + "\n")
    changes = {}
    if capture.password:
        changes[("openshift", VAULT_PASSWORD_KEY)] = capture.password
    if capture.kubeconfig_lines:
        changes[("openshift", VAULT_KUBECONFIG_KEY)] = capture.kubeconfig
    if changes and vault is not None:
        try:
            vault.update(changes)
            notes.append("kubeadmin password and kubeconfig stored in the vault")
        except Exception as error:  # a vault problem must not hide the install result
            notes.append(f"could not store the access details in the vault ({error}); the kubeconfig file was kept")
    elif changes:
        notes.append("no vault is configured; the access details were only written to the kubeconfig file")
    return notes


def load_info(host_vars_dir: Path) -> dict:
    try:
        return json.loads((access_dir(host_vars_dir) / INFO_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def ensure_kubeconfig_file(host_vars_dir: Path, vault) -> Path | None:
    """The captured kubeconfig file, restored from the vault when the file was removed."""
    path = kubeconfig_path(host_vars_dir)
    if path.is_file():
        return path
    if vault is None:
        return None
    try:
        text = ((vault.load().get("openshift") or {}).get(VAULT_KUBECONFIG_KEY)) or ""
    except Exception:
        return None
    if not text:
        return None
    write_private(path, text if text.endswith("\n") else text + "\n")
    return path
