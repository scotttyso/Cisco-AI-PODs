"""Minimal Redfish client shared by the CIMC / BMC automation scripts (stdlib + requests only)."""

from __future__ import annotations

import os
from pathlib import Path

import requests
import urllib3
import yaml

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class RedfishError(RuntimeError):
    pass


class Redfish:
    def __init__(self, address: str, username: str, password: str, timeout: float = 20.0, verify: bool = False):
        self.base = f"https://{address}"
        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.verify = verify
        self.session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
        self.timeout = timeout

    def get(self, path: str) -> dict:
        response = self.session.get(self.base + path, timeout=self.timeout)
        if response.status_code >= 400:
            raise RedfishError(f"GET {path}: HTTP {response.status_code}")
        return response.json()

    def patch(self, path: str, body: dict) -> requests.Response:
        etag = self.session.get(self.base + path, timeout=self.timeout).headers.get("ETag")
        headers = {"If-Match": etag} if etag else {}
        return self.session.patch(self.base + path, json=body, headers=headers, timeout=self.timeout)

    def members(self, path: str) -> list[str]:
        return [item["@odata.id"] for item in self.get(path).get("Members", [])]

    def manager(self) -> str:
        managers = self.members("/redfish/v1/Managers")
        if not managers:
            raise RedfishError("no Redfish manager found")
        preferred = [path for path in managers if path.rstrip("/").rsplit("/", 1)[-1].upper() in ("CIMC", "BMC", "1")]
        return (preferred or managers)[0]

    def manager_interface(self, address: str = "") -> tuple[str, dict]:
        """The BMC/CIMC NIC that owns ``address`` (or the first one with IPv4)."""
        candidates = []
        for path in self.members(self.manager() + "/EthernetInterfaces"):
            data = self.get(path)
            addresses = [entry.get("Address") for entry in data.get("IPv4Addresses") or []]
            if address and address in addresses:
                return path, data
            if addresses:
                candidates.append((path, data))
        if not candidates:
            raise RedfishError("no manager Ethernet interface with an IPv4 address")
        return candidates[0]


def endpoints(inventory_dir: Path, roles: tuple[str, ...] = ()) -> dict[str, dict]:
    """UCS endpoints from the UI-generated stage inventory (``host_vars/<host>.yml`` with a ``ucs`` key)."""
    hosts = {}
    for path in sorted((Path(inventory_dir) / "host_vars").glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        ucs = data.get("ucs")
        if isinstance(ucs, dict) and (not roles or ucs.get("device_role") in roles):
            hosts[path.stem] = ucs
    return hosts


def password(ucs: dict) -> str:
    reference = (ucs.get("cimc") or {}).get("pass_ref", "")
    value = os.environ.get(reference, "")
    if not value:
        raise RedfishError(f"environment variable {reference or '<pass_ref>'} is not set; store it in the vault")
    return value
