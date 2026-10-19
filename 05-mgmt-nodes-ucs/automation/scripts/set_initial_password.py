#!/usr/bin/env python3
"""Change the factory default CIMC / BMC password ('password') to the password stored in the vault, over Redfish.

Only hosts whose ``ucs.factory_default`` is true (the Factory default checkbox on the Claim Targets page) are
changed. The new password comes from the environment variable named by ``ucs.cimc.pass_ref``. Hosts that already
accept the new password are reported as done. Without ``--apply`` the script only reports the plan.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.lib.redfish import Redfish, RedfishError, endpoints, password  # noqa: E402

FACTORY_PASSWORD = "password"
MIN_LENGTH = 12
REDFISH_ROLES = ("ucs-server", "hgx-node")


def accepts(address: str, user: str, secret: str) -> bool:
    try:
        Redfish(address, user, secret, timeout=10).get("/redfish/v1/AccountService/Accounts")
        return True
    except (RedfishError, requests.RequestException, ValueError):
        return False


def change(name: str, ucs: dict, apply: bool) -> str:
    cimc = ucs.get("cimc") or {}
    if not ucs.get("factory_default") or ucs.get("device_role") not in REDFISH_ROLES:
        return "skip: not marked factory default"
    address, user = cimc.get("dhcp_ip") or cimc.get("ip"), cimc.get("user", "admin")
    new = password(ucs)
    if len(new) < MIN_LENGTH:
        return f"failed: the vault password is shorter than {MIN_LENGTH} characters"
    if accepts(address, user, new):
        return "ok: already uses the vault password"
    client = Redfish(address, user, FACTORY_PASSWORD)
    accounts = [client.get(path) for path in client.members("/redfish/v1/AccountService/Accounts")]
    account = next((item for item in accounts if item.get("UserName") == user), None)
    if not account:
        return f"failed: no account {user} on {address}"
    print(f"  {name}: {address} {account['@odata.id']} ({user})", flush=True)
    if not apply:
        return "planned"
    response = client.patch(account["@odata.id"], {"Password": new})
    if response.status_code >= 400:
        return f"failed: HTTP {response.status_code} {response.text[:300]}"
    return "ok: password changed" if accepts(address, user, new) else "failed: the new password is not accepted"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-dir", type=Path, required=True, help="UI-generated stage inventory directory")
    parser.add_argument("--host", action="append", default=[], help="limit to these inventory hosts")
    parser.add_argument("--apply", action="store_true", help="make the change (default: report only)")
    args = parser.parse_args()
    hosts = {name: ucs for name, ucs in endpoints(args.inventory_dir, REDFISH_ROLES).items()
             if ucs.get("factory_default") and (not args.host or name in args.host)}
    if not hosts:
        print("No targets are marked factory default on the Claim Targets page.")
        return 0
    failures = 0
    print(("Changing" if args.apply else "Planning") + f" factory default passwords for {len(hosts)} hosts", flush=True)
    for name, ucs in hosts.items():
        try:
            result = change(name, ucs, args.apply)
        except (RedfishError, requests.RequestException, KeyError) as error:
            result = f"failed: {error}"
        failures += result.startswith("failed")
        print(f"{name:<28} {result}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
