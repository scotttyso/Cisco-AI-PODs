#!/usr/bin/env python3
"""Paced GET-only C880 chassis health check with sanitized output."""

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
)


PATHS = (
    "/redfish/v1/Chassis/DGX",
    "/redfish/v1/Chassis/DGX/PowerSubsystem",
    "/redfish/v1/Chassis/DGX/PowerSubsystem/PowerSupplies",
    "/redfish/v1/Chassis/DGX/ThermalSubsystem",
    "/redfish/v1/ServiceConditions",
)


def _health_ok(value):
    return isinstance(value, dict) and value.get("Status", {}).get("Health") == "OK"


def probe(fetch, pause=time.sleep):
    resources = []
    for path in PATHS:
        if resources:
            pause(MIN_REQUEST_SPACING_SECONDS)
        resources.append(fetch(path))
    chassis, power, supplies, thermal, conditions = resources
    supply_members = supplies.get("Members")
    active_conditions = conditions.get("Conditions")
    if not isinstance(supply_members, list) or not isinstance(active_conditions, list):
        raise ValueError("Unexpected chassis health collection")
    severities = [entry.get("Severity") for entry in active_conditions if isinstance(entry, dict)]
    return {
        "mode": "read_only_live",
        "requests": len(PATHS),
        "checks": {
            "chassis_health_ok": _health_ok(chassis),
            "power_health_ok": _health_ok(power),
            "thermal_health_ok": _health_ok(thermal),
            "twelve_power_supplies_listed": len(supply_members) == 12,
            "no_active_warning_or_critical_conditions": not any(
                value in ("Warning", "Critical") for value in severities
            ),
        },
        "active_condition_count": len(active_conditions),
        "still_unverified": [
            "per_psu_and_per_sensor_health",
            "gpu_and_dimm_instance_counts",
            "sel_history_and_deassertion_review",
        ],
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
        print(f"C880 chassis probe failed: HTTP status {error.code}; no response body retained.", file=sys.stderr)
        return 2
    except urllib.error.URLError:
        print("C880 chassis probe failed: TLS or network transport; no response body retained.", file=sys.stderr)
        return 2
    except Exception:
        print("C880 chassis probe failed: inventory or unexpected response; no response body retained.", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
