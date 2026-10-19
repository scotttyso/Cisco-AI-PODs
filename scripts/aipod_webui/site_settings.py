"""Detect deployment-host defaults for shared services and persist operator overrides."""

import json
import os
import re
import socket
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

SETTINGS_LOCK = threading.Lock()

Validator = Callable[[dict], list[str]]


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _command(*arguments: str) -> str:
    try:
        return subprocess.run(arguments, check=False, capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _unique(values) -> list[str]:
    seen = []
    for value in values:
        value = str(value).strip()
        if value and value not in seen:
            seen.append(value)
    return seen


def detect_resolver(root: Path = Path("/")) -> tuple[list[str], list[str]]:
    # systemd-resolved keeps the real upstream servers here; /etc/resolv.conf may only list the 127.0.0.53 stub.
    servers, search = [], []
    for candidate in ("run/systemd/resolve/resolv.conf", "etc/resolv.conf"):
        text = _read(root / candidate)
        for line in text.splitlines():
            parts = line.split("#", 1)[0].split()
            if len(parts) < 2:
                continue
            if parts[0] == "nameserver" and not parts[1].startswith("127."):
                servers.append(parts[1])
            elif parts[0] in ("search", "domain"):
                search.extend(part for part in parts[1:] if part != ".")
        if servers or search:
            break
    return _unique(servers), _unique(search)


def detect_domain(search_domains: list[str]) -> str:
    fqdn = socket.getfqdn()
    if "." in fqdn and not fqdn.endswith(".localdomain") and not fqdn.startswith("localhost"):
        return fqdn.split(".", 1)[1]
    return search_domains[0] if search_domains else ""


def detect_ntp(root: Path = Path("/")) -> list[str]:
    files = [root / "etc/chrony.conf", root / "etc/chrony/chrony.conf"]
    for folder in ("etc/chrony.d", "etc/chrony/conf.d", "etc/chrony/sources.d"):
        directory = root / folder
        if directory.is_dir():
            files.extend(sorted(path for path in directory.iterdir() if path.suffix in (".conf", ".sources")))
    servers = []
    for path in files:
        for line in _read(path).splitlines():
            parts = line.split("#", 1)[0].split()
            if len(parts) >= 2 and parts[0] in ("server", "pool"):
                servers.append(parts[1])
    for path in [root / "etc/systemd/timesyncd.conf", *sorted((root / "etc/systemd/timesyncd.conf.d").glob("*.conf"))]:
        for line in _read(path).splitlines():
            match = re.match(r"\s*NTP\s*=\s*(.+)", line)
            if match:
                servers.extend(match.group(1).split())
    return _unique(servers)


def detect_timezone(root: Path = Path("/")) -> str:
    if root == Path("/"):
        zone = _command("timedatectl", "show", "-p", "Timezone", "--value")
        if zone:
            return zone
    zone = _read(root / "etc/timezone").strip()
    if zone:
        return zone
    try:
        target = os.readlink(root / "etc/localtime")
    except OSError:
        return ""
    return target.split("zoneinfo/", 1)[1] if "zoneinfo/" in target else ""


def _split_proxy_url(url: str) -> tuple[str, str]:
    """Return the proxy URL without credentials and the username it contained."""
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.hostname:
        return url.strip(), ""
    host = parts.hostname if ":" not in parts.hostname else f"[{parts.hostname}]"
    netloc = f"{host}:{parts.port}" if parts.port else host
    return urlunsplit((parts.scheme, netloc, parts.path.rstrip("/"), "", "")), parts.username or ""


def detect_proxy(environ: dict | None = None, root: Path = Path("/")) -> dict:
    values = {}
    for line in _read(root / "etc/environment").splitlines():
        match = re.match(r"\s*(?:export\s+)?([A-Za-z_]+)\s*=\s*[\"']?([^\"'\n]*)", line)
        if match:
            values[match.group(1).lower()] = match.group(2).strip()
    for key, value in (os.environ if environ is None else environ).items():
        if key.lower() in ("http_proxy", "https_proxy", "no_proxy") and value:
            values[key.lower()] = value
    proxy = {}
    for key in ("http_proxy", "https_proxy"):
        if values.get(key):
            url, username = _split_proxy_url(values[key])
            proxy[key] = url
            if username:
                proxy.setdefault("username", username)
    if values.get("no_proxy"):
        proxy["no_proxy"] = _unique(values["no_proxy"].split(","))
    return proxy


def detect_host_defaults(root: Path = Path("/"), environ: dict | None = None) -> dict:
    dns_servers, search_domains = detect_resolver(root)
    detected = {
        "dns_servers": dns_servers,
        "dns_search_domains": search_domains,
        "domain_name": detect_domain(search_domains) if root == Path("/") else (search_domains[:1] or [""])[0],
        "ntp_servers": detect_ntp(root),
        "timezone": detect_timezone(root),
        "proxy_servers": detect_proxy(environ, root),
    }
    return {key: value for key, value in detected.items() if value}


def _fit_list(key: str, values: list, validate: Callable[[list], list[str]]) -> tuple[list, list]:
    items = [entry for entry in values if not validate([entry])]
    dropped = [entry for entry in values if entry not in items]
    while items and validate(items):
        dropped.append(items.pop())
    return items, dropped


def sanitize(settings: dict, validate: Validator) -> tuple[dict, list[str]]:
    """Drop detected values that the schema rejects so defaults never block a save."""
    clean, dropped = {}, []
    for key, value in settings.items():
        if key == "proxy_servers":
            proxy = {}
            for name, item in value.items():
                if isinstance(item, list):
                    kept, rejected = _fit_list(name, item, lambda entries, name=name: validate({key: {name: entries}}))
                    dropped.extend(f"{key}.{name}: {entry}" for entry in rejected)
                    if kept:
                        proxy[name] = kept
                elif not validate({key: {name: item}}):
                    proxy[name] = item
                else:
                    dropped.append(f"{key}.{name}: {item}")
            if proxy:
                clean[key] = proxy
        elif isinstance(value, list):
            kept, rejected = _fit_list(key, value, lambda entries, key=key: validate({key: entries}))
            dropped.extend(f"{key}: {entry}" for entry in rejected)
            if kept:
                clean[key] = kept
        elif not validate({key: value}):
            clean[key] = value
        else:
            dropped.append(f"{key}: {value}")
    return clean, dropped


def strip_empty(settings: dict) -> dict:
    result = {}
    for key, value in settings.items():
        if isinstance(value, dict):
            value = strip_empty(value)
        if value not in (None, "", [], {}):
            result[key] = value
    return result


def overrides_from(effective: dict, detected: dict) -> dict:
    """Return only keys that differ from the detected defaults; None records a cleared default."""
    overrides = {}
    for key in sorted(set(effective) | set(detected)):
        if key == "proxy_servers":
            proxy_effective, proxy_detected = effective.get(key, {}), detected.get(key, {})
            proxy = {name: proxy_effective.get(name) for name in sorted(set(proxy_effective) | set(proxy_detected))
                     if proxy_effective.get(name) != proxy_detected.get(name)}
            if proxy:
                overrides[key] = proxy
        elif effective.get(key) != detected.get(key):
            overrides[key] = effective.get(key)
    return overrides


def merge(detected: dict, overrides: dict) -> dict:
    merged = json.loads(json.dumps(detected))
    for key, value in overrides.items():
        if key == "proxy_servers" and isinstance(value, dict):
            proxy = merged.setdefault(key, {})
            for name, item in value.items():
                if item is None:
                    proxy.pop(name, None)
                else:
                    proxy[name] = item
        elif value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return strip_empty(merged)


def write_json(path: Path, document) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, sort_keys=True)
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_json(path: Path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


class WorkspaceStore:
    """Deployment-wide state shared by every UI page: shared-service overrides and the device inventory."""

    def __init__(self, directory: Path, validate: Validator, detect: Callable[[], dict] = detect_host_defaults):
        self.directory = Path(directory)
        self.settings_path = self.directory / "site_settings.json"
        self.inventory_path = self.directory / "initial_inventory.json"
        self.validate = validate
        self.detect = detect

    def _settings(self) -> dict:
        document = load_json(self.settings_path, {})
        return document if isinstance(document, dict) else {}

    def detected(self) -> tuple[dict, list[str]]:
        return sanitize(self.detect(), self.validate)

    def overrides(self) -> dict:
        return self._settings().get("shared_services_overrides", {})

    def shared_services(self) -> dict:
        detected, _ = self.detected()
        return merge(detected, self.overrides())

    def save_shared_services(self, shared_services: dict) -> dict:
        shared_services = strip_empty(shared_services)
        problems = self.validate(shared_services)
        if problems:
            raise ValueError("\n".join(problems))
        detected, _ = self.detected()
        overrides = overrides_from(shared_services, detected)
        with SETTINGS_LOCK:
            document = self._settings()
            document["shared_services_overrides"] = overrides
            write_json(self.settings_path, document)
        return overrides

    def reset_shared_services(self) -> None:
        with SETTINGS_LOCK:
            document = self._settings()
            document.pop("shared_services_overrides", None)
            write_json(self.settings_path, document)

    def inventory(self) -> list[dict]:
        rows = load_json(self.inventory_path, [])
        return rows if isinstance(rows, list) else []

    def save_inventory(self, rows: list[dict]) -> None:
        keys = ("hostname", "ip", "mac", "pid", "serial_number")
        saved = []
        for row in rows:
            entry = {key: str(row.get(key, "")) for key in keys}
            if row.get("role"):
                entry["role"] = str(row["role"])
            if row.get("pool_ip") is True:
                entry["pool_ip"] = True
                entry["ip"] = ""
            saved.append(entry)
        with SETTINGS_LOCK:
            write_json(self.inventory_path, saved)

    def page_state(self, name: str) -> dict:
        state = self._settings().get("pages", {}).get(name, {})
        return state if isinstance(state, dict) else {}

    def save_page_state(self, name: str, state: dict) -> None:
        with SETTINGS_LOCK:
            document = self._settings()
            document.setdefault("pages", {})[name] = state
            write_json(self.settings_path, document)
