#!/usr/bin/env python3
"""One GET to compare per-instance OOB versions from AMI embedded inventory.

The local Cisco v1.2 source combines HGX_FW_GPU_n and HGX_InfoROM_GPU_n.
Compare all eight pairs, not only GPU_0 or Processor.FirmwareVersion. This
does not cover HUU components, activation, hardware health or image trust.
"""

import argparse
import json
from pathlib import Path
import sys
import urllib.error

from probe_c880_readonly import RedfishReader, _read_host, _read_vault_password


GPU_VBIOS = "97.10.7E.00.03"
GPU_INFOROM = "G540.0216.00.03"
TARGETS = {"BMC": "4.0(2.260022)", "BIOS": "4.0.2.67",
           "CPLDDCSM_0": "0.1.0.1", "CPLDMB_0": "0.1.2.8",
           "CPLDE1SBP_0": "0.1.0.7", "CPLDBACK_0": "0.1.0.7",
           "EROT_BMC_0": "4.0.15", "EROT_BIOS_0": "4.0.15"}


def summarize(collection):
    try:
        entries = collection["Oem"]["Ami"]["FirmwareInventory"]
    except (KeyError, TypeError):
        raise ValueError("Embedded AMI inventory is unavailable") from None
    if not isinstance(entries, list) or not entries or len(entries) > 128:
        raise ValueError("Unexpected embedded inventory size")
    wanted = set(TARGETS)
    for index in range(8):
        wanted.update((f"HGX_FW_GPU_{index}", f"HGX_InfoROM_GPU_{index}"))
    versions = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Malformed embedded inventory entry")
        name = entry.get("Name")
        if isinstance(name, str) and name in wanted:
            if name in versions:
                raise ValueError("Duplicated expected component")
            value = entry.get("Version")
            versions[name] = value if isinstance(value, str) and value else None
    gpus = []
    for index in range(8):
        vbios, inforom = versions.get(f"HGX_FW_GPU_{index}"), versions.get(f"HGX_InfoROM_GPU_{index}")
        gpus.append({"instance": index, "vbios_present": vbios is not None,
                     "inforom_present": inforom is not None,
                     "vbios_matches_target": vbios == GPU_VBIOS,
                     "inforom_matches_target": inforom == GPU_INFOROM,
                     "composite_matches_target": vbios == GPU_VBIOS and inforom == GPU_INFOROM})
    components = {name: {"version_present": versions.get(name) is not None,
                         "matches_target": versions.get(name) == target}
                  for name, target in TARGETS.items()}
    complete = all(gpu["composite_matches_target"] for gpu in gpus) and all(
        item["matches_target"] for item in components.values())
    return {"requests": 1, "mode": "one_get_embedded_oob_version_comparison",
            "gpu_instances": gpus, "platform_components": components,
            "all_listed_oob_versions_match": complete,
            "firmware_member_gets": 0, "huu_components_verified": False,
            "activation_and_health_verified": False,
            "full_upgrade_signoff": False, "mutations_performed": False}


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
        reader = RedfishReader(address, username, password,
                               allow_self_signed_lab=args.allow_self_signed_lab)
        result = summarize(reader("/redfish/v1/UpdateService/FirmwareInventory"))
        result["host"] = args.host
    except urllib.error.HTTPError as error:
        print(json.dumps({"read_pass_failed": True, "http_status": error.code}))
        return 2
    except Exception:
        print(json.dumps({"read_or_projection_failed": True, "raw_response_retained": False}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
