#!/usr/bin/env python3
"""Two paced GETs for active BIOS tokens named in MOP Procedure 6.

Values are compared to chapter intent, not asserted as verified factory
defaults. No BIOS Settings PATCH, reset, KVM or firmware action is available.
BlueField NIC mode needs its own verified interface and is never inferred.
"""

import argparse
import json
from pathlib import Path
import sys
import time

from probe_c880_readonly import (RedfishReader, MIN_REQUEST_SPACING_SECONDS,
                                 _read_host, _read_vault_password, _resource_path)


EXPECTED = {
    "STR_PCI_4G_PROMPT": "Enabled", "NvidiaAcsEnable": "Disable",
    "ControlIommu": "Enable", "ProcessorVmxEnable": "Enable",
    "PcieRelaxedOrdering": "Enable", "P2pRelaxedOrdering": "Enable",
    "PcieMaxReadRequestSize": "4096B", "SriovSupport": "Enabled",
    "PwrPerfTuning": "OS Controls EPB", "AltEngPerfBIAS": "Performance",
    "ProcessorC1eEnable": "Disable", "PackageCState": "C0/C1 state",
    "TurboMode": "Enable", "VirtualNumaEnable": "Disable", "NumaEn": "Enable",
}


def summarize(bios):
    attributes = bios.get("Attributes") if isinstance(bios, dict) else None
    if not isinstance(attributes, dict):
        raise ValueError("Active BIOS attributes unavailable")
    checks = {}
    for token, target in EXPECTED.items():
        present = token in attributes
        value = attributes.get(token)
        checks[token] = {"present": present, "matches_chapter_literal": present and value == target}
    return {"requests": 2, "mode": "read_only_active_bios_observation",
            "tokens": checks, "all_chapter_literals_match": all(
                item["matches_chapter_literal"] for item in checks.values()),
            "missing_tokens": sum(not item["present"] for item in checks.values()),
            "present_nonmatching_literals": sum(item["present"] and not item["matches_chapter_literal"]
                                                for item in checks.values()),
            "literal_mismatch_requires_registry_review_not_a_hardware_failure": True,
            "factory_defaults_independently_proven": False,
            "bluefield_both_adapters_nic_mode_verified": False,
            "pending_settings_verified": False, "procedure6_complete": False,
            "mutations_performed": False}


def probe(fetch, pause=time.sleep):
    system = fetch("/redfish/v1/Systems/DGX")
    link = system.get("Bios") if isinstance(system, dict) else None
    if not isinstance(link, dict):
        raise ValueError("BMC does not advertise the host BIOS resource")
    path = _resource_path(link.get("@odata.id"))
    if path != "/redfish/v1/Systems/DGX/Bios":
        raise ValueError("Unreviewed BIOS resource path")
    pause(MIN_REQUEST_SPACING_SECONDS)
    return summarize(fetch(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory_dir", type=Path)
    parser.add_argument("--host", choices=("ucs-c880-3",), required=True)
    parser.add_argument("--allow-self-signed-lab", action="store_true")
    args = parser.parse_args()
    try:
        if args.allow_self_signed_lab and args.inventory_dir.resolve().name != "lab":
            raise ValueError("TLS exception is lab-only")
        address, username, reference = _read_host(args.inventory_dir, args.host)
        password = _read_vault_password(args.inventory_dir, reference)
        result = probe(RedfishReader(address, username, password,
                                    allow_self_signed_lab=args.allow_self_signed_lab))
        result["host"] = args.host
    except Exception:
        print(json.dumps({"read_or_projection_failed": True, "raw_response_retained": False}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
