#!/usr/bin/env python3
"""Paced GET-only C880 media/firmware capability check; never emits raw responses."""

import argparse
import json
from pathlib import Path
import sys
import time
import urllib.error

from probe_c880_readonly import (
    MIN_REQUEST_SPACING_SECONDS,
    RedfishReader,
    _read_host,
    _read_vault_password,
    _resource_path,
)


def probe(fetch, pause=time.sleep):
    calls = 0

    def read(path):
        nonlocal calls
        if calls:
            pause(MIN_REQUEST_SPACING_SECONDS)
        calls += 1
        return fetch(path)

    manager = read("/redfish/v1/Managers/BMC")
    media = read("/redfish/v1/Managers/BMC/VirtualMedia")
    firmware = read("/redfish/v1/UpdateService/FirmwareInventory")
    system = read("/redfish/v1/Systems/DGX")
    settings_link = system.get("@Redfish.Settings", {}).get("SettingsObject", {}).get("@odata.id")
    settings = read(_resource_path(settings_link)) if settings_link else {}
    members = media.get("Members", [])
    if not isinstance(members, list):
        raise ValueError("Unexpected virtual media collection")
    cd1 = [item for item in members if isinstance(item, dict)
           and item.get("@odata.id") == "/redfish/v1/Managers/BMC/VirtualMedia/CD1"]
    disc = read("/redfish/v1/Managers/BMC/VirtualMedia/CD1") if len(cd1) == 1 else {}

    firmware_members = firmware.get("Members", [])
    if not isinstance(firmware_members, list):
        raise ValueError("Unexpected firmware collection")
    boot = settings.get("Boot", {})
    if not isinstance(boot, dict):
        boot = {}
    actions = manager.get("Actions", {})
    oem_actions = actions.get("Oem", {}) if isinstance(actions, dict) else {}
    if not isinstance(oem_actions, dict):
        oem_actions = {}

    return {
        "mode": "read_only_live",
        "requests": calls,
        "capabilities": {
            "remote_media_enable_action_present": "#AMIVirtualMedia.EnableRMedia" in oem_actions,
            "cd1_present": len(cd1) == 1,
            "cd1_insert_action_present": isinstance(disc.get("Actions"), dict)
            and "#VirtualMedia.InsertMedia" in disc["Actions"],
            "cd1_currently_inserted": disc.get("Inserted") is True,
            "one_time_cd_boot_allowed": "Cd" in boot.get(
                "BootSourceOverrideTarget@Redfish.AllowableValues", []
            ),
        },
        "firmware_inventory_members": len(firmware_members),
        "firmware_inventory_complete": not bool(firmware.get("Members@odata.nextLink")),
        "live_execution_allowed": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory_dir", type=Path)
    parser.add_argument("--host", required=True)
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
        print(f"C880 capability probe failed: HTTP status {error.code}; no response body retained.", file=sys.stderr)
        return 2
    except urllib.error.URLError:
        print("C880 capability probe failed: TLS or network transport; no response body retained.", file=sys.stderr)
        return 2
    except Exception:
        print("C880 capability probe failed: inventory or unexpected response; no response body retained.", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
