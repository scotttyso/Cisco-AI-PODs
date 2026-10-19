#!/usr/bin/env python3
"""Paced, GET-only C880-3 condition baseline and current HGX health gate."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import urllib.error

from c880_health_gate import evaluate_components, evaluate_gate, make_baseline
from probe_c880_readonly import (
    MIN_REQUEST_SPACING_SECONDS, RedfishReader, _read_host,
    _read_vault_password, _resource_path,
)


PATHS = (
    "/redfish/v1/Chassis/DGX/PowerSubsystem/PowerSupplies",
    "/redfish/v1/ServiceConditions",
)

HGX_BASEBOARD = "/redfish/v1/Systems/HGX_Baseboard_0"
HGX_BMC = "/redfish/v1/Managers/HGX_BMC_0"
GPU_COLLECTION = HGX_BASEBOARD + "/Processors"
SWITCH_COLLECTION = "/redfish/v1/Fabrics/HGX_NVLinkFabric_0/Switches"
MAX_GPU_COLLECTION = 10
MAX_SWITCH_COLLECTION = 3
PILOT_HOST = "ucs-c880-3"


def _read_members(fetch, collection_path, limit, pause):
    pause(MIN_REQUEST_SPACING_SECONDS)
    collection = fetch(collection_path)
    members = collection.get("Members")
    if not isinstance(members, list) or len(members) > limit:
        raise ValueError("Unexpected component collection")
    resources = []
    seen = set()
    for member in members:
        if not isinstance(member, dict):
            raise ValueError("Unexpected component member")
        path = _resource_path(member.get("@odata.id"))
        if not path.startswith(collection_path + "/"):
            raise ValueError("Component outside approved collection")
        if path in seen:
            raise ValueError("Duplicate component member")
        seen.add(path)
        pause(MIN_REQUEST_SPACING_SECONDS)
        resources.append(fetch(path))
    return resources


def probe_gate(fetch, baseline=None, pause=time.sleep):
    """One bounded pass; old conditions do not fail without a new observation."""
    conditions = fetch(PATHS[1]).get("Conditions")
    pause(MIN_REQUEST_SPACING_SECONDS)
    baseboard = fetch(HGX_BASEBOARD)
    pause(MIN_REQUEST_SPACING_SECONDS)
    hgx_bmc = fetch(HGX_BMC)
    processors = _read_members(fetch, GPU_COLLECTION, MAX_GPU_COLLECTION, pause)
    switches = _read_members(fetch, SWITCH_COLLECTION, MAX_SWITCH_COLLECTION, pause)
    checks = evaluate_components(baseboard, hgx_bmc, processors, switches)
    result = evaluate_gate(conditions, checks, baseline)
    result.update({
        "mode": "read_only_live",
        "requests": 5 + len(processors) + len(switches),
        "minimum_request_spacing_seconds": MIN_REQUEST_SPACING_SECONDS,
        "live_execution_allowed": False,
        "window_coverage": "sample_only",
        "upgrade_window_verified": False,
        "upgrade_or_downgrade_performed": False,
    })
    return result


def capture_baseline(fetch):
    conditions = fetch(PATHS[1]).get("Conditions")
    baseline = make_baseline(conditions)
    baseline["captured_utc"] = datetime.now(timezone.utc).isoformat()
    baseline["host"] = PILOT_HOST
    baseline["phase"] = "post_manual_upgrade_reference"
    return baseline


def validate_baseline_file(baseline):
    if (not isinstance(baseline, dict) or baseline.get("host") != PILOT_HOST
            or baseline.get("phase") != "post_manual_upgrade_reference"
            or not isinstance(baseline.get("captured_utc"), str)):
        raise ValueError("Baseline identity or phase mismatch")
    datetime.fromisoformat(baseline["captured_utc"])
    return baseline


def _write_new_baseline(path, baseline):
    """Create an opaque-fingerprint file; never replace an existing baseline."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(baseline, stream, sort_keys=True)
            stream.write("\n")
    except Exception:
        # Do not leave a partial baseline that a later run might trust.
        Path(path).unlink(missing_ok=True)
        raise


def probe(fetch, pause=time.sleep):
    supplies = fetch(PATHS[0])
    pause(MIN_REQUEST_SPACING_SECONDS)
    conditions = fetch(PATHS[1])
    members = supplies.get("Members")
    entries = conditions.get("Conditions")
    if not isinstance(members, list) or not isinstance(entries, list):
        raise ValueError("Unexpected health collection")
    severities = Counter(
        entry.get("Severity") for entry in entries if isinstance(entry, dict)
    )
    origin_groups = Counter()
    linked_log_entries = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        origin = entry.get("OriginOfCondition")
        path = origin.get("@odata.id") if isinstance(origin, dict) else None
        if not isinstance(path, str):
            group = "missing"
        elif "/Sensors/" in path:
            group = "sensors"
        elif "/PowerSupplies/" in path:
            group = "power_supplies"
        elif "/Systems/HGX" in path or "/Chassis/HGX" in path:
            group = "hgx"
        elif "/Systems/DGX" in path or "/Chassis/DGX" in path:
            group = "host_or_chassis"
        else:
            group = "other"
        origin_groups[group] += 1
        log_entry = entry.get("LogEntry")
        if isinstance(log_entry, dict) and isinstance(log_entry.get("@odata.id"), str):
            linked_log_entries += 1
    allowed = ("OK", "Warning", "Critical")
    return {
        "mode": "read_only_live",
        "requests": len(PATHS),
        "power_supply_collection_members": len(members),
        "service_condition_count": len(entries),
        "service_condition_severity_counts": {
            severity.lower(): severities.get(severity, 0) for severity in allowed
        },
        "service_condition_other_severity_count": sum(
            count for severity, count in severities.items() if severity not in allowed
        ),
        "conditions_expose_resolution_field": any(
            any(key in entry for key in ("Resolved", "IsActive", "IsAsserted"))
            for entry in entries if isinstance(entry, dict)
        ),
        "condition_origin_group_counts": dict(sorted(origin_groups.items())),
        "conditions_with_log_link": linked_log_entries,
        "live_execution_allowed": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory_dir", type=Path)
    parser.add_argument("--host", required=True)
    tls = parser.add_mutually_exclusive_group()
    tls.add_argument("--ca-file", type=Path)
    tls.add_argument("--allow-self-signed-lab", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write-baseline", type=Path,
                      help="Create a 0600 sanitized fingerprint baseline; never overwrite")
    mode.add_argument("--evaluate-gate", action="store_true",
                      help="Paced component check against an optional pre-window baseline")
    parser.add_argument("--baseline-file", type=Path,
                        help="Sanitized baseline captured before the observation window")
    args = parser.parse_args()
    try:
        if args.baseline_file and not args.evaluate_gate:
            raise ValueError("Baseline comparison requires --evaluate-gate")
        address, username, pass_ref = _read_host(args.inventory_dir, args.host)
        if args.allow_self_signed_lab and args.inventory_dir.resolve().name != "lab":
            raise ValueError("Self-signed certificate exception is lab-only")
        password = _read_vault_password(args.inventory_dir, pass_ref)
        reader = RedfishReader(
            address, username, password, args.ca_file, args.allow_self_signed_lab
        )
        if args.write_baseline:
            baseline = capture_baseline(reader)
            _write_new_baseline(args.write_baseline, baseline)
            result = {"mode": "read_only_baseline", "requests": 1,
                      "condition_count": len(baseline["fingerprints"]),
                      "baseline_saved": True, "live_execution_allowed": False}
        elif args.evaluate_gate:
            baseline = None
            if args.baseline_file:
                baseline = validate_baseline_file(json.loads(
                    args.baseline_file.read_text(encoding="utf-8")))
            result = probe_gate(reader, baseline)
        else:
            result = probe(reader)
        result["host"] = args.host
    except urllib.error.HTTPError as error:
        print(f"C880 health-count probe failed: HTTP status {error.code}; no response body retained.", file=sys.stderr)
        return 2
    except urllib.error.URLError:
        print("C880 health-count probe failed: TLS or network transport; no response body retained.", file=sys.stderr)
        return 2
    except Exception:
        print("C880 health-count probe failed: inventory or unexpected response; no response body retained.", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
