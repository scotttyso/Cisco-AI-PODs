#!/usr/bin/env python3
"""Paced, single-server, GET-only C880 BMC health probe.

This is deliberately not a firmware updater or vMedia controller. It prints
allowlisted booleans only and never writes BMC response bodies or credentials.
"""

import argparse
import base64
import json
from pathlib import Path
import ssl
import stat
import sys
import time
import urllib.error
import urllib.request

import yaml


MAX_RESPONSE_BYTES = 1024 * 1024
MIN_REQUEST_SPACING_SECONDS = 3


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        return None


def _resource_path(value):
    """Accept only same-BMC Redfish paths returned by the service."""
    if not isinstance(value, str) or not value.startswith("/redfish/v1/"):
        raise ValueError("Unsafe Redfish resource path")
    if "//" in value or "?" in value or "#" in value or ".." in value:
        raise ValueError("Unsafe Redfish resource path")
    return value


def _select_member(members, suffix):
    """Select only the documented host/BMC resource from a collection."""
    if not isinstance(members, list):
        raise ValueError("Invalid Redfish collection")
    matches = [
        _resource_path(member.get("@odata.id"))
        for member in members if isinstance(member, dict) and member.get("@odata.id") == suffix
    ]
    if len(matches) != 1:
        raise ValueError("Documented C880 resource missing or duplicated")
    return matches[0]


HOSTS = ("ucs-c880-1", "ucs-c880-2", "ucs-c880-3", "ucs-c880-4")

def _read_host(inventory_dir, host):
    if host not in HOSTS:
        raise ValueError(f"Host {host} is outside C880 workflow")
    path = Path(inventory_dir) / "host_vars" / f"{host}.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    ucs = data["ucs"]
    if ucs["platform"] != "standalone" or ucs["role"] != "gpu":
        raise ValueError("Selected host is not a standalone GPU server")
    cimc = ucs["cimc"]
    return cimc["ip"], cimc["user"], cimc["pass_ref"]


def _read_vault_password(inventory_dir, pass_ref):
    """Resolve the selected inventory reference without exposing its value."""
    if not isinstance(pass_ref, str) or not pass_ref or not pass_ref.replace("_", "").isalnum():
        raise ValueError("Invalid credential reference")
    path = Path(inventory_dir) / "group_vars" / "vault.yml"
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("Vault file permissions are too broad")
    vault = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(vault, dict):
        raise ValueError("Invalid vault mapping")
    password = vault.get("vault_" + pass_ref.lower())
    if not isinstance(password, str) or not password or password.startswith("<"):
        raise ValueError("Credential reference is unresolved")
    return password


class RedfishReader:
    def __init__(self, address, username, password, ca_file=None, allow_self_signed_lab=False):
        if ca_file is not None:
            context = ssl.create_default_context(cafile=str(ca_file))
        elif allow_self_signed_lab:
            context = ssl._create_unverified_context()
        else:
            context = ssl.create_default_context()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context), _NoRedirect()
        )
        self._base = f"https://{address}"
        token = base64.b64encode(f"{username}:{password}".encode("utf-8"))
        self._authorization = "Basic " + token.decode("ascii")

    def __call__(self, path):
        request = urllib.request.Request(
            self._base + _resource_path(path),
            headers={"Accept": "application/json", "Authorization": self._authorization},
            method="GET",
        )
        with self._opener.open(request, timeout=12) as response:
            if response.status != 200:
                raise ValueError("Unexpected BMC status")
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise ValueError("BMC response too large")
            value = json.loads(body)
            if not isinstance(value, dict):
                raise ValueError("Unexpected BMC response format")
            return value


def _health_ok(value):
    return isinstance(value, dict) and value.get("Status", {}).get("Health") == "OK"


def probe(fetch, pause=time.sleep):
    """Four serial reads, with a mandatory pause before every subsequent read."""
    root = fetch("/redfish/v1/")
    systems_path = _resource_path(root["Systems"]["@odata.id"])
    pause(MIN_REQUEST_SPACING_SECONDS)
    systems = fetch(systems_path)
    system_path = _select_member(systems.get("Members", []), "/redfish/v1/Systems/DGX")
    pause(MIN_REQUEST_SPACING_SECONDS)
    system = fetch(system_path)
    managers_path = _resource_path(root["Managers"]["@odata.id"])
    pause(MIN_REQUEST_SPACING_SECONDS)
    managers = fetch(managers_path)
    manager_path = _select_member(managers.get("Members", []), "/redfish/v1/Managers/BMC")
    pause(MIN_REQUEST_SPACING_SECONDS)
    manager = fetch(manager_path)

    return {
        "mode": "read_only_live",
        "requests": 5,
        "checks": {
            "system_health_ok": _health_ok(system),
            "power_on": system.get("PowerState") == "On",
            "two_processors_present": system.get("ProcessorSummary", {}).get("Count") == 2,
            "processor_health_ok": _health_ok(system.get("ProcessorSummary")),
            "memory_health_ok": _health_ok(system.get("MemorySummary")),
            "manager_health_ok": _health_ok(manager),
            "bmc_firmware_version_present": bool(manager.get("FirmwareVersion")),
        },
        "release_checks": {
            "bmc_matches_4_0_2_260022": manager.get("FirmwareVersion") in (
                "4.0(2.260022)", "4.0.2.260022"
            ),
            "bios_matches_4_0_2_67": isinstance(system.get("BiosVersion"), str)
            and system["BiosVersion"].endswith("4.0.2.67"),
        },
        "still_unverified": [
            "dimms_gpus_psus_sensors_and_sel",
            "firmware_bundle_and_huu_component_baselines",
            "vmedia_and_boot_behavior",
        ],
        "live_execution_allowed": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory_dir", type=Path)
    parser.add_argument("--host", required=True, help="Exactly one canonical C880 host")
    tls = parser.add_mutually_exclusive_group()
    tls.add_argument("--ca-file", type=Path)
    tls.add_argument("--allow-self-signed-lab", action="store_true")
    args = parser.parse_args()
    try:
        address, username, pass_ref = _read_host(args.inventory_dir, args.host)
        if args.allow_self_signed_lab and args.inventory_dir.resolve().name != "lab":
            raise ValueError("Self-signed certificate exception is lab-only")
        password = _read_vault_password(args.inventory_dir, pass_ref)
        result = probe(RedfishReader(
            address, username, password, args.ca_file, args.allow_self_signed_lab
        ))
        result["host"] = args.host
    except urllib.error.HTTPError as error:
        print(f"C880 read-only probe failed: HTTP status {error.code}; no response body retained.", file=sys.stderr)
        return 2
    except urllib.error.URLError:
        print("C880 read-only probe failed: TLS or network transport; no response body retained.", file=sys.stderr)
        return 2
    except Exception:
        print("C880 read-only probe failed: inventory or unexpected response; no response body retained.", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
