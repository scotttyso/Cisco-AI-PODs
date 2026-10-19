#!/usr/bin/env python3
"""Configure HGX server BMCs (Cisco UCS C845A / C880A) through Redfish from an ``hgx_servers`` variables file.

Sets, per server and as enabled in ``hgx_servers.bmc_settings.configure``:

* NTP servers, with the NTP protocol enabled (``Managers/<id>/NetworkProtocol``)
* ``DateTimeLocalOffset`` - the current UTC offset of ``timezone`` (``Managers/<id>``)
* ``HostName``, ``FQDN`` and ``StaticNameServers`` on the BMC interface that owns ``bmc.ip``

Without ``--apply`` the script only reads the BMCs and prints what would change. With ``--apply`` it patches the
differences, then re-reads the BMC until the settings are confirmed (the interface patch restarts BMC networking).
Passwords come from the environment variable named by ``password_ref`` (the web UI exports them from Ansible Vault).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.lib.redfish import Redfish, RedfishError  # noqa: E402

CONFIGURE = ("hostname", "dns", "ntp", "timezone")
ALREADY_SET = ("PatchValueAlreadyExists", "already applied")


def timezone_offset(zone: str, at: datetime | None = None) -> str:
    """Current offset of an IANA zone as +HH:MM (the BMC stores an offset, not the zone)."""
    instant = at or datetime.now(timezone.utc)
    minutes = int(instant.astimezone(ZoneInfo(zone)).utcoffset().total_seconds() // 60)
    return f"{'+' if minutes >= 0 else '-'}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


def load_servers(path: Path, hosts: list[str]) -> tuple[dict, list[dict]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    root = data.get("hgx_servers") if isinstance(data, dict) else None
    if not isinstance(root, dict):
        raise ValueError(f"{path} has no hgx_servers mapping")
    settings = root.get("bmc_settings") or {}
    for key in ("dns_servers", "ntp_servers", "domain_name", "timezone"):
        if not settings.get(key):
            raise ValueError(f"hgx_servers.bmc_settings.{key} is required")
    ZoneInfo(settings["timezone"])
    servers = [server for server in root.get("servers") or [] if isinstance(server, dict)]
    if hosts:
        wanted = {name.lower() for name in hosts}
        servers = [server for server in servers if str(server.get("hostname", "")).lower() in wanted]
    if not servers:
        raise ValueError("No HGX servers selected" + (f" ({', '.join(hosts)})" if hosts else ""))
    return settings, servers


def desired(settings: dict, server: dict, at: datetime | None = None) -> dict:
    configure = {key: (settings.get("configure") or {}).get(key, True) for key in CONFIGURE}
    hostname = str(server["hostname"])
    dns = [str(value) for value in settings["dns_servers"]]
    return {
        "hostname": hostname if configure["hostname"] else None,
        "fqdn": f"{hostname}.{settings['domain_name']}" if configure["hostname"] else None,
        # The C880A BMC keeps an IPv6 slot in StaticNameServers; "::" leaves it empty.
        "dns": (dns + ["::"] if server.get("model") == "C880A" and "::" not in dns else dns) if configure["dns"] else None,
        "ntp": [str(value) for value in settings["ntp_servers"]] if configure["ntp"] else None,
        "offset": timezone_offset(settings["timezone"], at) if configure["timezone"] else None,
    }


class Bmc:
    """Redfish reads and ETag-guarded patches with the spacing the HGX BMCs need."""

    def __init__(self, client: Redfish, address: str, spacing: float = 3.0, sleep=time.sleep):
        self.client, self.address, self.spacing, self.sleep = client, address, spacing, sleep
        self.paths: dict[str, str] = {}

    def get(self, path: str) -> dict:
        self.sleep(self.spacing)
        return self.client.get(path)

    def discover(self) -> dict[str, str]:
        if not self.paths:
            self.sleep(self.spacing)
            manager = self.client.manager()
            self.sleep(self.spacing)
            interface, _ = self.client.manager_interface(self.address)
            self.paths = {"manager": manager, "protocol": manager.rstrip("/") + "/NetworkProtocol", "interface": interface}
        return self.paths

    def read(self) -> dict:
        paths = self.discover()
        protocol, manager, interface = self.get(paths["protocol"]), self.get(paths["manager"]), self.get(paths["interface"])
        ntp = protocol.get("NTP") or {}
        return {"hostname": interface.get("HostName"), "fqdn": interface.get("FQDN"),
                "dns": list(interface.get("StaticNameServers") or []), "ntp": list(ntp.get("NTPServers") or []),
                "ntp_enabled": bool(ntp.get("ProtocolEnabled")), "offset": manager.get("DateTimeLocalOffset"),
                "ssh": bool((protocol.get("SSH") or {}).get("ProtocolEnabled"))}

    def patch(self, key: str, body: dict, retries: int = 3) -> None:
        path = self.discover()[key]
        for attempt in range(retries):
            self.sleep(self.spacing)
            try:
                response = self.client.patch(path, body)
            except (requests.ConnectionError, requests.Timeout):
                if key == "interface":
                    return  # the interface patch restarts BMC networking; verification follows
                raise
            if response.status_code < 400 or any(text in response.text for text in ALREADY_SET):
                return
            if response.status_code == 412 and attempt < retries - 1:
                self.sleep(5)
                continue
            raise RedfishError(f"PATCH {path}: HTTP {response.status_code} {response.text[:300]}")


def differences(target: dict, current: dict) -> dict[str, dict]:
    """Redfish bodies for the settings that differ, keyed by resource."""
    changes: dict[str, dict] = {}
    if target["ntp"] is not None and (current["ntp"] != target["ntp"] or not current["ntp_enabled"]):
        changes["protocol"] = {"NTP": {"NTPServers": target["ntp"], "ProtocolEnabled": True}}
    if target["offset"] is not None and current["offset"] != target["offset"]:
        changes["manager"] = {"DateTimeLocalOffset": target["offset"]}
    interface = {}
    if target["hostname"] is not None and (current["hostname"] != target["hostname"] or current["fqdn"] != target["fqdn"]):
        interface.update(HostName=target["hostname"], FQDN=target["fqdn"])
    if target["dns"] is not None and not set(value for value in target["dns"] if value != "::") <= set(current["dns"]):
        interface["StaticNameServers"] = target["dns"]
    if interface:
        changes["interface"] = interface
    return changes


def configure(bmc: Bmc, target: dict, apply: bool, log=print, attempts: int = 15) -> bool:
    current = bmc.read()
    changes = differences(target, current)
    if not current["ssh"]:
        log("    note: SSH / SOL is disabled on the BMC")
    if not changes:
        log("    already configured")
        return True
    for key, body in changes.items():
        log(f"    {'set' if apply else 'would set'} {key}: {body}")
    if not apply:
        return True
    for key in ("protocol", "manager", "interface"):
        if key in changes:
            bmc.patch(key, changes[key])
    for attempt in range(1, attempts + 1):
        try:
            remaining = differences(target, bmc.read())
        except (RedfishError, requests.RequestException) as error:
            log(f"    waiting for the BMC ({type(error).__name__}), attempt {attempt}")
            bmc.sleep(5)
            continue
        if not remaining:
            log("    verified")
            return True
        bmc.sleep(5)
    log(f"    NOT verified, still different: {sorted(remaining)}")
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--vars", type=Path, required=True, help="YAML file with the hgx_servers mapping")
    parser.add_argument("--host", action="append", default=[], help="limit to these host names (repeatable)")
    parser.add_argument("--apply", action="store_true", help="patch the BMCs (default: report only)")
    args = parser.parse_args(argv)
    try:
        settings, servers = load_servers(args.vars, args.host)
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"error: {error}")
        return 2
    failures = 0
    for server in servers:
        bmc_spec = server.get("bmc") or {}
        reference = bmc_spec.get("password_ref") or settings.get("password_ref") or "HGX_BMC_PASSWORD"
        username = bmc_spec.get("username") or settings.get("username") or "admin"
        print(f"{server['hostname']} ({bmc_spec.get('ip')}, {server.get('model', 'HGX')})", flush=True)
        password = os.environ.get(reference, "")
        if not password:
            print(f"    environment variable {reference} is not set; store the BMC password in the vault")
            failures += 1
            continue
        try:
            client = Redfish(bmc_spec["ip"], username, password, verify=bool(settings.get("verify_ssl", False)))
            bmc = Bmc(client, bmc_spec["ip"], float(settings.get("request_spacing", 3)))
            if not configure(bmc, desired(settings, server), args.apply):
                failures += 1
        except (KeyError, RedfishError, requests.RequestException, ValueError) as error:
            print(f"    failed: {error}")
            failures += 1
    print(f"\n{len(servers) - failures} of {len(servers)} servers {'configured' if args.apply else 'checked'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
