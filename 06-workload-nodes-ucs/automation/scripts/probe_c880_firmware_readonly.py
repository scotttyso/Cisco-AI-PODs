#!/usr/bin/env python3
"""Slow, GET-only C880 firmware inventory comparison; prints no raw inventory."""

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


MAX_MEMBERS = 100
TARGET_VERSIONS = {
    "gpu": "97.10.7E.00.03-G540.0216.00.03",
    "dcscm_cpld": "0.1.0.1",
    "motherboard_cpld": "0.1.2.8",
    "backplane_cpld": "0.1.0.7",
    "erot": "4.0.15",
}


def probe(fetch, pause=time.sleep):
    collection = fetch("/redfish/v1/UpdateService/FirmwareInventory")
    members = collection.get("Members")
    if not isinstance(members, list) or len(members) > MAX_MEMBERS:
        raise ValueError("Unexpected firmware inventory size")
    if collection.get("Members@odata.nextLink"):
        raise ValueError("Firmware inventory pagination requires review")
    versions = []
    unhealthy = 0
    for member in members:
        if not isinstance(member, dict):
            raise ValueError("Invalid firmware member")
        path = _resource_path(member.get("@odata.id"))
        pause(MIN_REQUEST_SPACING_SECONDS)
        item = fetch(path)
        version = item.get("Version")
        if isinstance(version, str):
            versions.append(version)
        status = item.get("Status")
        if isinstance(status, dict) and status.get("Health") not in (None, "OK"):
            unhealthy += 1
    return {
        "mode": "read_only_live",
        "requests": len(members) + 1,
        "firmware_members_checked": len(members),
        "members_with_version": len(versions),
        "members_reporting_non_ok_health": unhealthy,
        "target_version_presence": {
            name: value in versions for name, value in TARGET_VERSIONS.items()
        },
        "note": "Version presence alone does not establish that every instance is current.",
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
        print(f"C880 firmware probe failed: HTTP status {error.code}; no response body retained.", file=sys.stderr)
        return 2
    except urllib.error.URLError:
        print("C880 firmware probe failed: TLS or network transport; no response body retained.", file=sys.stderr)
        return 2
    except Exception:
        print("C880 firmware probe failed: inventory or unexpected response; no response body retained.", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
