#!/usr/bin/env python3
"""Collect host NIC MAC addresses from CIMC / BMC Redfish for the OpenShift install and network-operator YAML.

Output (``--output``) is ``{"source": "redfish", "hosts": {<host>: {<port name>: <mac>}}}``. NVIDIA / Mellanox
ports are named ``mlx-<n>`` in PCIe order so the UI can map them onto the persistent_net_rules interface names;
other ports keep their Redfish identifiers.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.lib.redfish import Redfish, RedfishError, endpoints, password  # noqa: E402

MELLANOX = ("mellanox", "nvidia", "connectx", "bluefield", "mt2", "15b3")


def _mac(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isalnum()).lower()
    return ":".join(digits[i:i + 2] for i in range(0, 12, 2)) if len(digits) == 12 else ""


def collect(client: Redfish) -> tuple[dict, dict]:
    summary, ports = {}, []
    systems = client.members("/redfish/v1/Systems")
    if systems:
        system = client.get(systems[0])
        summary = {key: system.get(key) for key in ("Model", "SerialNumber", "PowerState", "BiosVersion")}
        for path in client.members(systems[0] + "/EthernetInterfaces"):
            data = client.get(path)
            if _mac(data.get("MACAddress") or data.get("PermanentMACAddress")):
                ports.append((data.get("Id") or path.rsplit("/", 1)[-1], _mac(data.get("PermanentMACAddress") or data.get("MACAddress")),
                              " ".join(str(data.get(key, "")) for key in ("Name", "Description"))))
    for chassis in client.members("/redfish/v1/Chassis"):
        try:
            adapters = client.members(chassis + "/NetworkAdapters")
        except RedfishError:
            continue
        for adapter_path in adapters:
            adapter = client.get(adapter_path)
            vendor = " ".join(str(adapter.get(key, "")) for key in ("Manufacturer", "Model", "Name"))
            try:
                functions = client.members(adapter_path + "/NetworkDeviceFunctions")
            except RedfishError:
                functions = []
            for function_path in functions:
                function = client.get(function_path)
                ethernet = function.get("Ethernet") or {}
                mac = _mac(ethernet.get("PermanentMACAddress") or ethernet.get("MACAddress"))
                if mac and mac not in {port[1] for port in ports}:
                    ports.append((f"{adapter.get('Id', 'adapter')}-{function.get('Id', len(ports))}", mac, vendor))
    named, index = {}, 0
    for name, mac, description in ports:
        if any(word in description.lower() for word in MELLANOX):
            index += 1
            named[f"mlx-{index}"] = mac
        else:
            named[str(name)] = mac
    return summary, named


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--role", action="append", default=[], help="device roles to query (default: servers and HGX)")
    args = parser.parse_args()
    hosts = endpoints(args.inventory_dir, tuple(args.role or ("ucs-server", "hgx-node")))
    if not hosts:
        print("No standalone servers or HGX nodes in the inventory. Assign roles on the Initial Inventory page.")
        return 1
    result, failures = {}, 0
    for name, ucs in hosts.items():
        cimc = ucs.get("cimc") or {}
        try:
            summary, ports = collect(Redfish(cimc["ip"], cimc.get("user", "admin"), password(ucs)))
        except (RedfishError, requests.RequestException, KeyError, ValueError) as error:
            failures += 1
            print(f"{name:<28} failed: {error}", flush=True)
            continue
        result[name] = ports
        details = ", ".join(f"{key}={value}" for key, value in summary.items() if value)
        print(f"{name:<28} {len(ports)} ports ({sum(key.startswith('mlx-') for key in ports)} NVIDIA/Mellanox) {details}", flush=True)
        for port, mac in ports.items():
            print(f"    {port:<24} {mac}", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    previous = {}
    if args.output.is_file():
        previous = json.loads(args.output.read_text(encoding="utf-8")).get("hosts", {})
    previous.update(result)
    args.output.write_text(json.dumps({"source": "redfish", "collected": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                       "hosts": previous}, indent=2), encoding="utf-8")
    print(f"\nSaved MAC addresses for {len(result)} hosts to {args.output}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
