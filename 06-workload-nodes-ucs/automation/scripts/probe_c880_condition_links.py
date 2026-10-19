#!/usr/bin/env python3
"""Bounded, paced, GET-only diagnostic of C880-3 condition-linked logs.

Resolved=false is a log-entry field, not proof that the origin resource has a
current fault. Use the separate baseline-and-component health gate for that.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time
import urllib.error

from probe_c880_readonly import (
    MIN_REQUEST_SPACING_SECONDS, RedfishReader, _read_host,
    _read_vault_password, _resource_path,
)


CONDITIONS_PATH = "/redfish/v1/ServiceConditions"
MAX_LINKS = 50


def probe(fetch, pause=time.sleep):
    conditions = fetch(CONDITIONS_PATH).get("Conditions")
    if not isinstance(conditions, list) or len(conditions) > MAX_LINKS:
        raise ValueError("Unexpected or excessive service-condition count")
    links = []
    for condition in conditions:
        if not isinstance(condition, dict):
            raise ValueError("Unexpected service condition")
        log_entry = condition.get("LogEntry")
        if not isinstance(log_entry, dict):
            raise ValueError("Service condition lacks log link")
        path = _resource_path(log_entry.get("@odata.id"))
        if "/LogServices/" not in path or "/Entries/" not in path:
            raise ValueError("Unexpected service-condition log link")
        links.append(path)
    unique_links = list(dict.fromkeys(links))
    resolved = Counter()
    for path in unique_links:
        pause(MIN_REQUEST_SPACING_SECONDS)
        entry = fetch(path)
        value = entry.get("Resolved")
        if value is True:
            resolved["true"] += 1
        elif value is False:
            resolved["false"] += 1
        else:
            resolved["unreported"] += 1
    return {
        "mode": "read_only_live",
        "requests": 1 + len(unique_links),
        "conditions": len(conditions),
        "unique_linked_logs": len(unique_links),
        "linked_log_resolved_counts": {key: resolved.get(key, 0)
                                       for key in ("true", "false", "unreported")},
        "condition_log_resolution_is_not_clearance": True,
        "linked_log_resolution_is_not_current_component_health": True,
        "diagnostic_only_not_an_upgrade_gate": True,
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
        print(f"C880 log-link probe failed: HTTP status {error.code}; no response body retained.", file=sys.stderr)
        return 2
    except urllib.error.URLError:
        print("C880 log-link probe failed: TLS or network transport; no response body retained.", file=sys.stderr)
        return 2
    except Exception:
        print("C880 log-link probe failed: inventory or unexpected response; no response body retained.", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
