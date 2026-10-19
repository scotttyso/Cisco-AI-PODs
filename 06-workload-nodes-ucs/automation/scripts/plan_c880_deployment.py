#!/usr/bin/env python3
"""Read-only, sanitized C880 deployment preflight. Never contacts a BMC."""

import argparse
import ipaddress
import json
from pathlib import Path
import stat
import sys

import yaml


def _load_mapping(path):
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Invalid YAML mapping: {path.name}")
    return value


def build_plan(inventory_dir):
    inventory_dir = Path(inventory_dir)
    hosts_dir = inventory_dir / "host_vars"
    paths = sorted(hosts_dir.glob("ucs-c880-*.yml"))
    if not paths:
        raise ValueError("No C880 host inventory files found")

    shared = _load_mapping(inventory_dir / "group_vars" / "all.yml")
    services = shared.get("aipod") or {}
    if not isinstance(services, dict):
        raise ValueError("Invalid shared management services")
    dns_ok = isinstance(services.get("dns_servers"), list) and bool(services["dns_servers"])
    ntp_ok = isinstance(services.get("ntp_servers"), list) and bool(services["ntp_servers"])

    vault_path = inventory_dir / "group_vars" / "vault.yml"
    vault = {}
    if vault_path.is_file() and not stat.S_IMODE(vault_path.stat().st_mode) & 0o077:
        loaded = yaml.safe_load(vault_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            vault = loaded

    hosts = []
    for path in paths:
        name = path.stem
        ucs = _load_mapping(path).get("ucs") or {}
        if not isinstance(ucs, dict):
            raise ValueError("Invalid UCS host inventory")
        cimc = ucs.get("cimc") or {}
        if not isinstance(cimc, dict):
            raise ValueError("Invalid BMC host inventory")
        checks = {
            "platform_present": isinstance(ucs.get("platform"), str) and bool(ucs["platform"]),
            "bmc_address_valid": False,
            "bmc_user_present": isinstance(cimc.get("user"), str) and bool(cimc["user"]),
            "credential_reference_present": isinstance(cimc.get("pass_ref"), str) and bool(cimc["pass_ref"]),
            "credential_reference_resolves": False,
            "shared_dns_present": dns_ok,
            "shared_ntp_present": ntp_ok,
        }
        try:
            ipaddress.ip_address(cimc.get("ip"))
            checks["bmc_address_valid"] = True
        except (ValueError, TypeError):
            pass
        ref = cimc.get("pass_ref")
        if isinstance(ref, str) and ref and ref.replace("_", "").isalnum():
            value = vault.get("vault_" + ref.lower())
            checks["credential_reference_resolves"] = (
                isinstance(value, str) and bool(value) and not value.startswith("<")
            )
        hosts.append({"host": name, "inventory_checks": checks})

    return {
        "mode": "read_only_offline",
        "hosts": hosts,
        "live_execution_allowed": False,
        "unverified_prerequisites": [
            "approved_maintenance_window_and_pilot",
            "exact_firmware_bundle_script_iso_and_checksums",
            "script_v1_2_command_and_credential_handling",
            "bmc_reachable_iso_source_and_vmedia_behavior",
            "current_bmc_release_health_and_workload_state",
            "c880_specific_huu_automation_support",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory_dir", type=Path)
    args = parser.parse_args()
    try:
        plan = build_plan(args.inventory_dir)
    except Exception:
        print("C880 preflight failed; inspect the inventory privately.", file=sys.stderr)
        return 2
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
