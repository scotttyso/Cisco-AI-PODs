#!/usr/bin/env python
"""Read deployed UCS domain uplink state and CDP/LLDP neighbors without changing configuration."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

import requests
import yaml

from collect_intersight_macs import session


UPLINK_ROLES = (
    ("fabric/UplinkRoles", "ether/PhysicalPorts"),
    ("fabric/UplinkPcRoles", "ether/PhysicalPorts"),
    ("fabric/FcoeUplinkRoles", "ether/PhysicalPorts"),
    ("fabric/FcoeUplinkPcRoles", "ether/PhysicalPorts"),
    ("fabric/FcUplinkRoles", "fc/PhysicalPorts"),
    ("fabric/FcUplinkPcRoles", "fc/PhysicalPorts"),
)


def quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def query(client: requests.Session, base: str, path: str, expression: str) -> list[dict]:
    results = []
    while True:
        response = client.get(
            f"{base}/api/v1/{path}",
            params={"$filter": expression, "$top": 1000, "$skip": len(results)}, timeout=60,
        )
        response.raise_for_status()
        page = response.json().get("Results")
        if not isinstance(page, list):
            raise ValueError(f"GET {path}: expected a Results list")
        results.extend(page)
        if len(page) < 1000:
            return results


def domain_targets(directory: Path) -> dict[str, str]:
    targets = {}
    for path in sorted(directory.rglob("*.ezai.yaml")):
        model = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(model, dict):
            raise ValueError(f"{path}: expected a YAML mapping")
        intersight = model.get("intersight") or {}
        configurations = intersight.get("configure") or intersight.get("config") or {}
        for org, configuration in configurations.items():
            for profile in configuration.get("profiles", {}).get("domain", []):
                serials = profile.get("serial_numbers", [])
                if not isinstance(serials, list):
                    raise ValueError(f"{path}: domain serial_numbers must be a list")
                for serial in serials:
                    if not isinstance(serial, str) or not serial.strip():
                        raise ValueError(f"{path}: domain serial numbers must be nonempty strings")
                    targets[serial] = f"{org}/{profile['name']}"
    if not targets:
        raise ValueError("No domain profile serial_numbers found. Save domain profiles before checking connectivity.")
    return targets


def port_key(port: dict) -> tuple[int, int, int]:
    return int(port["SlotId"]), int(port["PortId"]), int(port.get("AggregatePortId") or 0)


def port_label(key: tuple[int, int, int]) -> str:
    slot, port, breakout = key
    return f"{slot}/{port}" + (f"/{breakout}" if breakout else "")


def check_switch(client: requests.Session, base: str, serial: str, label: str) -> bool:
    elements = query(client, base, "network/Elements", f"Serial eq {quote(serial)}")
    if len(elements) != 1:
        raise ValueError(f"{label}: expected one discovered switch for serial {serial}, found {len(elements)}")
    element = elements[0]
    moid = quote(element["Moid"])
    profiles = query(client, base, "fabric/SwitchProfiles", f"AssignedSwitch.Moid eq {moid}")
    if len(profiles) != 1:
        raise ValueError(f"{label}: switch {serial} must have exactly one assigned switch profile")
    policies = [policy for policy in profiles[0].get("PolicyBucket", [])
                if policy.get("ObjectType") == "fabric.PortPolicy"]
    if len(policies) != 1:
        raise ValueError(f"{label}: no unique port policy on assigned switch profile")
    print(f"\n{label} - fabric {element.get('SwitchId', '?')} - {serial}", flush=True)
    expected: dict[str, set[tuple[int, int, int]]] = {}
    for endpoint, inventory in UPLINK_ROLES:
        roles = query(client, base, endpoint, f"PortPolicy.Moid eq {quote(policies[0]['Moid'])}")
        for role in roles:
            ports = role.get("Ports") if "Ports" in role else [role]
            if not ports:
                raise ValueError(f"{endpoint}: configured uplink role has no member ports")
            expected.setdefault(inventory, set()).update(port_key(port) for port in ports)
    if not expected:
        raise ValueError(f"{label}: assigned port policy has no Ethernet, FCoE, or FC uplinks to validate")

    healthy = True
    for inventory, keys in expected.items():
        ports = query(client, base, inventory, f"Ancestors/any(t:t/Moid eq {moid})")
        by_port = {port_key(port): port for port in ports}
        for key in sorted(keys):
            port = by_port.get(key)
            state = str(port.get("OperState") or "unknown") if port else "missing"
            up = state.lower() == "up"
            healthy = healthy and up
            if port:
                print(f"  {'PASS' if up else 'FAIL'} {inventory.split('/')[0]} {port_label(key)}: {state}"
                      f" (speed: {port.get('OperSpeed') or 'unknown'}; "
                      f"reason: {port.get('OperStateQual') or 'none reported'})", flush=True)
            else:
                print(f"  FAIL {inventory.split('/')[0]} {port_label(key)}: missing from inventory", flush=True)
            if port and inventory == "ether/PhysicalPorts":
                neighbors = query(client, base, "network/DiscoveredNeighbors",
                                  f"PhysicalPort.Moid eq {quote(port['Moid'])}")
                for neighbor in neighbors:
                    protocol = ("CDP" if neighbor.get("CdpNeighbor") else
                                "LLDP" if neighbor.get("LldpNeighbor") else neighbor.get("NeighborType", "Discovery"))
                    print(f"    {protocol}: {neighbor.get('NeighborDeviceId') or neighbor.get('DeviceId') or 'unknown'}"
                          f" port {neighbor.get('NeighborInterface') or neighbor.get('NeighborPortId') or 'unknown'}"
                          f" ({neighbor.get('ManagementAddress') or 'no management address'})", flush=True)
                if not neighbors:
                    print("    CDP/LLDP: no neighbor reported; link state alone cannot confirm the remote switch.",
                          flush=True)
    return healthy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domains-dir", type=Path, required=True)
    parser.add_argument("--url", default=os.environ.get("intersight_fqdn", "intersight.com"))
    args = parser.parse_args()
    base = args.url.rstrip("/")
    if not base.startswith(("https://", "http://")):
        base = f"https://{base}"
    try:
        targets = domain_targets(args.domains_dir)
        healthy = True
        with session() as client:
            for serial, label in targets.items():
                try:
                    if not check_switch(client, base, serial, label):
                        healthy = False
                except (ValueError, KeyError, requests.RequestException) as error:
                    print(f"FAIL {label} ({serial}): {error}", file=sys.stderr, flush=True)
                    healthy = False
        print("\nUplink link-state check " + ("passed." if healthy else "failed.") +
              " Neighbor data is reported when available; intended remote cabling is not verified.", flush=True)
        return 0 if healthy else 1
    except (OSError, ValueError, yaml.YAMLError, requests.RequestException) as error:
        print(f"Connectivity check failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
