"""Ansible Vault backed credential store shared by the UI pages and the automation they launch.

One encrypted file holds two layouts so every consumer reads it natively:

* section maps (``intersight:``, ``openshift:`` ...) read by ``scripts/deploy_ai_pod.py`` and
  ``vault_credentials.<section>`` lookups in the main-repo roles;
* top-level ``vault_*`` keys read by the stage playbooks through ``vars_files``.

Plaintext only ever exists in memory and on the ``ansible-vault`` stdin/stdout pipes.
"""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

import yaml

SECTIONS = ("nexus_dashboard", "everpure", "intersight", "openshift", "splunk_observability")
TOP = ""
VAULT_HEADER = "$ANSIBLE_VAULT;"
PEM_ENV_KEYS = frozenset({"intersight_secret_key"})


class VaultError(RuntimeError):
    pass


@dataclass(frozen=True)
class SecretField:
    """One credential input. ``targets`` are (section, key) pairs; section "" is the top level."""

    key: str
    label: str
    targets: tuple[tuple[str, str], ...]
    multiline: bool = False
    help: str = ""
    min_length: int = 0
    # Not required by actions unless the saved YAML references it.
    optional: bool = False
    # Entered on another page (named here); this page only shows whether it is stored.
    source: str = ""


def tool(name: str) -> str | None:
    sibling = Path(sys.executable).parent / name
    if sibling.is_file() and os.access(sibling, os.X_OK):
        return str(sibling)
    return shutil.which(name)


def stage_env_name(key: str) -> str:
    """vault_nd_admin_password -> ND_ADMIN_PASSWORD, the *_pass_ref convention of the stage scripts."""
    return key.removeprefix("vault_").upper()


class VaultStore:
    def __init__(self, vault_file: Path, password_file: Path):
        self.vault_file = Path(vault_file)
        self.password_file = Path(password_file)
        self._lock = threading.Lock()
        self._cache: tuple[float, dict] | None = None

    def status(self) -> dict:
        problems = []
        if tool("ansible-vault") is None:
            problems.append("ansible-vault is not installed")
        if not self.password_file.is_file():
            problems.append(f"Vault password file is missing: {self.password_file}")
        elif self.password_file.stat().st_mode & 0o077:
            problems.append(f"Vault password file must be mode 0600: {self.password_file}")
        return {"ready": not problems, "problems": problems, "exists": self.vault_file.is_file(),
                "vault_file": str(self.vault_file), "password_file": str(self.password_file)}

    def create_password(self, password: str | None = None) -> None:
        if self.password_file.exists():
            raise VaultError(f"{self.password_file} already exists")
        value = password or secrets.token_urlsafe(32)
        if len(value) < 12:
            raise VaultError("The vault password must contain at least 12 characters")
        self.password_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(self.password_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(value + "\n")

    def _vault_cmd(self, *arguments: str, data: str | None = None) -> str:
        status = self.status()
        if not status["ready"]:
            raise VaultError("; ".join(status["problems"]))
        command = [tool("ansible-vault"), *arguments, "--vault-password-file", str(self.password_file)]
        env = {key: value for key, value in os.environ.items() if not key.startswith("ANSIBLE_VAULT")}
        result = subprocess.run(command, input=data, capture_output=True, text=True, env=env,
                                cwd=self.vault_file.parent if self.vault_file.parent.is_dir() else None)
        if result.returncode:
            message = (result.stderr or result.stdout).strip().splitlines()
            raise VaultError(message[-1] if message else f"ansible-vault {arguments[0]} failed")
        return result.stdout

    def load(self) -> dict:
        with self._lock:
            return self._load()

    def _load(self) -> dict:
        if not self.vault_file.is_file():
            return {}
        mtime = self.vault_file.stat().st_mtime
        if self._cache and self._cache[0] == mtime:
            return _copy(self._cache[1])
        raw = self.vault_file.read_text(encoding="utf-8")
        text = self._vault_cmd("view", str(self.vault_file)) if raw.startswith(VAULT_HEADER) else raw
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            raise VaultError("The vault content must be a YAML mapping")
        self._cache = (mtime, data)
        return _copy(data)

    def is_set(self, data: dict, section: str, key: str) -> bool:
        holder = data if section == TOP else data.get(section) or {}
        value = holder.get(key) if isinstance(holder, dict) else None
        return value not in (None, "")

    def update(self, changes: dict[tuple[str, str], str | None]) -> None:
        """Set or (with None/"") remove values, then re-encrypt atomically."""
        with self._lock:
            data = self._load()
            for (section, key), value in changes.items():
                if section and section not in SECTIONS:
                    raise VaultError(f"Unknown vault section: {section}")
                holder = data if section == TOP else data.setdefault(section, {})
                if not isinstance(holder, dict):
                    raise VaultError(f"Vault section {section} must be a mapping")
                if value in (None, ""):
                    holder.pop(key, None)
                else:
                    holder[key] = value
            for section in SECTIONS:
                if section in data and not data[section]:
                    data.pop(section)
            plaintext = "---\n# Managed by the Cisco AI PODs Automation UI.\n" + yaml.safe_dump(
                data, sort_keys=True, default_flow_style=False)
            ciphertext = self._vault_cmd("encrypt", "--output", "-", "-", data=plaintext)
            self.vault_file.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=".vault-", dir=self.vault_file.parent)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    stream.write(ciphertext)
                os.chmod(temporary, 0o600)
                os.replace(temporary, self.vault_file)
            finally:
                Path(temporary).unlink(missing_ok=True)
            self._cache = None

    def environment(self, scratch: Path | None = None, prefer: str | None = None) -> tuple[dict[str, str], list[str]]:
        """Return (env vars, secret values to redact). PEM keys become 0600 files under ``scratch``. ``prefer`` is
        exported last so its values win names shared by sections (Everpure and Intersight local_user_password_N)."""
        data = self.load()
        env: dict[str, str] = {}
        for section in sorted(SECTIONS, key=lambda name: name == prefer):
            for name, value in (data.get(section) or {}).items():
                if isinstance(name, str) and _scalar(value):
                    env[name] = _text(value)
        for name, value in data.items():
            if isinstance(name, str) and name.startswith("vault_") and _scalar(value):
                env.setdefault(stage_env_name(name), _text(value))
        # Intersight LDAP policies reuse the Shared services LDAP bind password unless one is stored for Intersight.
        ldap_bind = (data.get("openshift") or {}).get("ldap_bind_password")
        if _scalar(ldap_bind) and str(ldap_bind):
            env.setdefault("ldap_binding_password_1", _text(ldap_bind))
        if scratch is not None:
            for name in PEM_ENV_KEYS & env.keys():
                if env[name].lstrip().startswith("-----BEGIN"):
                    path = scratch / f"{name}.pem"
                    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                        stream.write(env[name].strip() + "\n")
                    env[name] = str(path)
        redact = sorted({_text(value) for section in (data, *[data.get(name) or {} for name in SECTIONS])
                         if isinstance(section, dict) for value in section.values()
                         if _scalar(value) and not isinstance(value, bool) and len(_text(value)) >= 4},
                        key=len, reverse=True)
        return env, redact


def _scalar(value) -> bool:
    return value is not None and not isinstance(value, (dict, list, tuple, set))


def _text(value) -> str:
    return str(value).lower() if isinstance(value, bool) else str(value)


def _copy(data: dict) -> dict:
    return {key: dict(value) if isinstance(value, dict) else value for key, value in data.items()}


def sensitive_fields(model: dict) -> list[SecretField]:
    """Credential inputs for every integer secret reference found in a saved YAML model."""
    from validate_sensitive_variables import _SENSITIVE_VAR_PATTERNS, collect_required_sensitive_variables

    sections_of = _example_sections()
    own = next((key for key in SECTIONS if key in model), "openshift")
    fields = []
    for name, (prefix, _) in sorted(collect_required_sensitive_variables(model).items()):
        label = _SENSITIVE_VAR_PATTERNS.get(prefix, (None, prefix.replace("_", " ").title()))[1]
        candidates = sections_of.get(prefix, ())
        section = own if own in candidates or not candidates else candidates[0]
        multiline = prefix == "ssh_public_key"
        number = name.rsplit('_', 1)[-1]
        fields.append(SecretField(name, f"{label} #{number} (vault key {name})", ((section, name),), multiline,
                                  f"The YAML only holds the reference number ({number}); the value itself is "
                                  f"encrypted into the vault as {name} and exported to the automation."))
    return fields


def _example_sections() -> dict[str, tuple[str, ...]]:
    """Map env-name prefixes to the vault sections documented in examples/vault.example.yaml (some, such as
    local_user_password, are listed under both everpure and intersight)."""
    example = Path(__file__).resolve().parents[2] / "examples/vault.example.yaml"
    mapping = {}
    try:
        data = yaml.safe_load(example.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return mapping
    for section, values in data.items():
        for name in (values or {}):
            prefix = name.rsplit("_", 1)[0] if name[-1].isdigit() else name
            if section not in mapping.setdefault(prefix, ()):
                mapping[prefix] += (section,)
    return mapping
