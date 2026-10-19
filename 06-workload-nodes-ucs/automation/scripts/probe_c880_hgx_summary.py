#!/usr/bin/env python3
"""Paced, GET-only C880-3 HGX summary after active service-condition alerts."""

import argparse
import json
from pathlib import Path
import sys
import time
import urllib.error

from probe_c880_readonly import MIN_REQUEST_SPACING_SECONDS, RedfishReader, _read_host, _read_vault_password


PATHS = (
    "/redfish/v1/Systems/HGX_Baseboard_0",
    "/redfish/v1/Managers/HGX_BMC_0",
)


def _health_status(value):
    status = value.get("Status") if isinstance(value, dict) else None
    if not isinstance(status, dict):
        return "unreported"
    health = status.get("Health")
    return health if health in ("OK", "Warning", "Critical") else "unreported"


def probe(fetch, pause=time.sleep):
    system = fetch(PATHS[0])
    pause(MIN_REQUEST_SPACING_SECONDS)
    manager = fetch(PATHS[1])
    processor = system.get("ProcessorSummary")
    processor_count = processor.get("Count") if isinstance(processor, dict) else None
    return {
        "mode": "read_only_live",
        "requests": len(PATHS),
        "hgx_baseboard_health": _health_status(system),
        "hgx_bmc_health": _health_status(manager),
        "hgx_processor_count": processor_count if isinstance(processor_count, int) else None,
        "still_unverified": ["individual_hgx_conditions_and_logs", "gpu_and_nvlink_member_health"],
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
        print(f"C880 HGX probe failed: HTTP status {error.code}; no response body retained.", file=sys.stderr)
        return 2
    except urllib.error.URLError:
        print("C880 HGX probe failed: TLS or network transport; no response body retained.", file=sys.stderr)
        return 2
    except Exception:
        print("C880 HGX probe failed: inventory or unexpected response; no response body retained.", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
