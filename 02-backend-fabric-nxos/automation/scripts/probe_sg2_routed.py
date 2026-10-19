#!/usr/bin/env python3
"""Paced SG2 routed-config observation; no configuration, secrets or IPs emitted."""

import argparse
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import re
import time

from probe_sg2_connectivity import HOSTS, NAMES, SPACING, ROUTED_COMMANDS, _read_show_outputs


def observed_ports(name):
    """October 3 LLDP observation, not an approved intended-cabling map."""
    if name not in NAMES:
        raise ValueError("Host outside SG2")
    parents = (list(range(1, 9)) + list(range(17, 25)) if "-SP" in name
               else list(range(33, 41)) + list(range(49, 57)))
    return {f"Ethernet1/{parent}/{child}" for parent in parents for child in (1, 2)}


def summarize_routed(name, outputs):
    if name not in NAMES or len(outputs) != len(ROUTED_COMMANDS):
        raise ValueError("Unexpected routed observation")
    if outputs[0].strip().upper() != name:
        raise ValueError("Switch hostname mismatch")
    for output in outputs[1:]:
        if (not isinstance(output, str) or not re.search(r"!Command:\s*show running-config", output)
                or re.search(r"Invalid command|Invalid input|Syntax error|Authorization failed", output, re.I)):
            raise ValueError("Unrecognized configuration response")
    bgp = outputs[1]
    router = bool(re.search(r"^router bgp [0-9.]+\s*$", bgp, re.M))
    neighbors = set()
    for match in re.finditer(r"^\s+neighbor ((?:[0-9]{1,3}\.){3}[0-9]{1,3})\s*$", bgp, re.M):
        neighbors.add(str(ipaddress.IPv4Address(match.group(1))))
    interfaces = {}
    current = None
    for line in outputs[2].splitlines():
        header = re.fullmatch(r"interface (Ethernet[0-9]+/[0-9]+(?:/[0-9]+)?)", line)
        if header:
            current = header.group(1)
            if current in interfaces:
                raise ValueError("Duplicate interface section")
            interfaces[current] = {"routed": False, "ipv4": False,
                                   "shutdown": False, "explicit_no_shutdown": False}
        elif line and not line.startswith(" "):
            current = None
        elif current:
            command = line.strip()
            state = interfaces[current]
            if command == "no switchport":
                state["routed"] = True
            elif command == "shutdown":
                state["shutdown"] = True
                state["explicit_no_shutdown"] = False
            elif command == "no shutdown":
                state["shutdown"] = False
                state["explicit_no_shutdown"] = True
            elif command.startswith("ip address "):
                fields = command.split()
                if len(fields) >= 3 and fields[2] not in ("dhcp", "none"):
                    address = fields[2].split("/")[0]
                    ipaddress.IPv4Address(address)
                    state["ipv4"] = True
    expected = observed_ports(name)
    found = {key: value for key, value in interfaces.items() if key in expected}
    return {"hostname": name, "commands": len(ROUTED_COMMANDS),
            "router_bgp_configured": router, "distinct_ipv4_neighbor_addresses_all_vrfs": len(neighbors),
            "observed_lldp_local_ports": len(expected),
            "observed_lldp_ports_with_config_sections": len(found),
            "observed_lldp_ports_explicitly_routed": sum(s["routed"] for s in found.values()),
            "observed_lldp_ports_with_ipv4_address": sum(s["ipv4"] for s in found.values()),
            "observed_lldp_ports_explicitly_shutdown": sum(s["shutdown"] for s in found.values()),
            "observed_lldp_ports_with_explicit_no_shutdown": sum(s["explicit_no_shutdown"] for s in found.values()),
            "intended_cabling_verified": False, "e2e_complete": False,
            "unnumbered_portchannel_and_ipv6_alternatives_verified": False,
            "configuration_changed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory_dir", type=Path)
    parser.add_argument("--host", choices=HOSTS)
    args = parser.parse_args()
    observations, failures = [], []
    for index, host in enumerate((args.host,) if args.host else HOSTS):
        if index:
            time.sleep(SPACING)
        try:
            outputs = _read_show_outputs(args.inventory_dir, host, ROUTED_COMMANDS)
            observations.append(summarize_routed(host.upper(), outputs))
        except Exception as error:
            category = "transport_or_auth" if type(error).__module__.startswith("paramiko") else "read_or_parse"
            failures.append({"hostname": host.upper(), "failure_category": category})
    print(json.dumps({"captured_utc": datetime.now(timezone.utc).isoformat(),
                      "observations": observations, "failures": failures,
                      "minimum_spacing_seconds": SPACING, "mutations_performed": False},
                     indent=2, sort_keys=True))
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
