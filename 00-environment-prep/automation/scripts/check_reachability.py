#!/usr/bin/env python3
"""Check that inventory devices answer on their management address before (and after) a deployment step.

Input is a JSON list of ``{"hostname", "ip", "role"}`` objects. Each address gets one ICMP echo and TCP probes on
22 (SSH) and 443 (HTTPS / Redfish / API). A device passes when any probe answers.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def tcp(address: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((address, port), timeout=timeout):
            return True
    except OSError:
        return False


def probe(device: dict, timeout: float) -> dict:
    address = device.get("ip", "")
    ping = subprocess.run(["ping", "-c", "1", "-W", str(max(1, int(timeout))), address],
                          capture_output=True, check=False).returncode == 0 if address else False
    return dict(device, ping=ping, ssh=bool(address) and tcp(address, 22, timeout),
                https=bool(address) and tcp(address, 443, timeout))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--devices", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()
    devices = [device for device in json.loads(args.devices.read_text(encoding="utf-8")) if device.get("ip")]
    if not devices:
        print("No inventory devices with an IP address. Save the Initial Inventory first.")
        return 1
    with ThreadPoolExecutor(max_workers=32) as pool:
        results = list(pool.map(lambda device: probe(device, args.timeout), devices))
    failed = 0
    print(f"{'Hostname':<28} {'Role':<20} {'Address':<16} ping  ssh   https")
    for item in sorted(results, key=lambda entry: (entry.get("role", ""), entry["hostname"])):
        marks = ["yes" if item[key] else "-" for key in ("ping", "ssh", "https")]
        ok = any(item[key] for key in ("ping", "ssh", "https"))
        failed += not ok
        print(f"{item['hostname']:<28} {item.get('role', ''):<20} {item['ip']:<16} {marks[0]:<5} {marks[1]:<5} {marks[2]:<5}"
              + ("" if ok else "  UNREACHABLE"), flush=True)
    print(f"\n{len(results) - failed}/{len(results)} devices reachable")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
