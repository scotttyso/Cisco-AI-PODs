#!/usr/bin/env python3
"""One paced SG2 observation pass; no configuration or raw output retained.

Observed LLDP reciprocity is not proof of intended cabling or E2E readiness.
Only the four inventory SG2 hosts and five fixed show commands are permitted.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import stat
import sys
import time

import paramiko
import yaml


HOSTS = ("be-sg2-sp1", "be-sg2-sp2", "be-sg2-lf1", "be-sg2-lf2")
NAMES = {host.upper() for host in HOSTS}
COMMANDS = ("show switchname", "show lldp neighbors", "show interface status",
            "show ip interface brief vrf all", "show bgp ipv4 unicast summary")
ROUTED_COMMANDS = ("show switchname", "show running-config bgp",
                   "show running-config interface")
SPACING = 3
MAX_BYTES = 512 * 1024
PORT = r"(?:Eth|Ethernet)[0-9]+/[0-9]+(?:/[0-9]+)?"


def port(value):
    if not isinstance(value, str) or not re.fullmatch(PORT, value):
        raise ValueError("Invalid physical port")
    return value.replace("Ethernet", "Eth")


def summarize(name, outputs):
    if name not in NAMES or len(outputs) != len(COMMANDS):
        raise ValueError("Unexpected SG2 observation")
    if outputs[0].strip().upper() != name:
        raise ValueError("Switch hostname does not match inventory")
    for output in outputs:
        if not isinstance(output, str) or re.search(
                r"Invalid command|Invalid input|Syntax error|Authorization failed", output, re.I):
            raise ValueError("Read command did not succeed")
    links = []
    for line in outputs[1].splitlines():
        fields = line.split()
        if len(fields) >= 5 and re.fullmatch(PORT, fields[1]) and re.fullmatch(PORT, fields[-1]):
            peer = fields[0].split("(")[0].upper()
            links.append({"local_port": port(fields[1]),
                          "peer": peer if peer in NAMES else "unclassified_peer",
                          "peer_port": port(fields[-1])})
    if not re.search(r"Device ID|Total entries displayed", outputs[1], re.I):
        raise ValueError("LLDP response format unrecognized")
    if len({link["local_port"] for link in links}) != len(links):
        raise ValueError("LLDP local port appears more than once")
    states = {}
    for line in outputs[2].splitlines():
        match = re.match(r"^\s*(" + PORT + r")\s+.*?\s+(connected|notconnect|disabled|err-disabled|sfpAbsent|xcvrAbsent|linkFlapErr|inactive)\s+", line)
        if match:
            local = port(match.group(1))
            if local in states:
                raise ValueError("Duplicate interface status")
            states[local] = match.group(2)
    if not states:
        raise ValueError("Interface status format unrecognized")
    for link in links:
        link["state"] = states.get(link["local_port"], "unverified")
    bgp = outputs[4]
    rows = [line.split() for line in bgp.splitlines()
            if re.match(r"^\s*(?:[0-9]{1,3}\.){3}[0-9]{1,3}\s+", line)]
    if not re.search(r"BGP summary|BGP is not running|BGP not configured|BGP routing table|Neighbor\s+V\s+AS", bgp, re.I):
        raise ValueError("BGP summary format unrecognized")
    return {"hostname": name, "commands": len(COMMANDS), "lldp_links": links,
            "physical_ports_observed": len(states),
            # Text columns vary by release; do not infer no IPs from no regex match.
            "ip_brief_collected_not_interpreted": True,
            "routed_config_verified": False,
            "bgp_peer_rows": len(rows),
            "bgp_established_peer_rows": sum(row[-1].isdigit() for row in rows),
            "intended_cabling_verified": False, "nd_health_verified": False,
            "e2e_complete": False}


def reciprocal_summary(observations):
    edges = set()
    for observation in observations:
        for link in observation["lldp_links"]:
            if link["peer"] in NAMES:
                edges.add((observation["hostname"], link["local_port"],
                           link["peer"], link["peer_port"]))
    reciprocal = {edge for edge in edges if (edge[2], edge[3], edge[0], edge[1]) in edges}
    return {"observed_directed_sg2_links": len(edges),
            "reciprocal_physical_child_lanes": len(reciprocal) // 2,
            "nonreciprocal_directed_links": len(edges - reciprocal),
            "intended_cabling_verified": False}


def _read_show_outputs(inventory_dir, host, commands, pause=time.sleep):
    if commands not in (COMMANDS, ROUTED_COMMANDS):
        raise ValueError("Only fixed read-only command profiles are permitted")
    if host not in HOSTS:
        raise ValueError("Host is outside SG2 observation scope")
    data = yaml.safe_load((inventory_dir / "host_vars" / (host + ".yml")).read_text())
    switch = data["be_switch"]
    if switch["fabric_key"] != "sg2" or switch["hostname"] != host.upper():
        raise ValueError("Inventory SG2 identity mismatch")
    vault_path = inventory_dir / "group_vars" / "vault.yml"
    if stat.S_IMODE(vault_path.stat().st_mode) & 0o077:
        raise ValueError("Vault permissions too broad")
    vault = yaml.safe_load(vault_path.read_text())
    password = vault.get("vault_" + switch["pass_ref"].lower())
    if not isinstance(password, str) or not password or password.startswith("<"):
        raise ValueError("Credential reference unresolved")
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(switch["mgmt_ip"], username=switch["username"], password=password,
                       look_for_keys=False, allow_agent=False, timeout=10,
                       auth_timeout=10, banner_timeout=10)
        outputs = []
        for index, command in enumerate(commands):
            if index:
                pause(SPACING)
            stdin, stdout, stderr = client.exec_command(command, timeout=20)
            try:
                body = stdout.read(MAX_BYTES + 1)
                error = stderr.read(MAX_BYTES + 1)
                if len(body) > MAX_BYTES or len(error) > MAX_BYTES or error.strip():
                    raise ValueError("Read response rejected")
                if stdout.channel.recv_exit_status() != 0:
                    raise ValueError("Read command failed")
                outputs.append(body.decode("utf-8", errors="replace"))
            finally:
                stdin.close()
                stdout.close()
                stderr.close()
        return outputs
    finally:
        client.close()


def read_once(inventory_dir, host, pause=time.sleep):
    return summarize(host.upper(), _read_show_outputs(inventory_dir, host, COMMANDS, pause))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory_dir", type=Path)
    args = parser.parse_args()
    observations = []
    failures = []
    for index, host in enumerate(HOSTS):
        if index:
            time.sleep(SPACING)
        try:
            observations.append(read_once(args.inventory_dir, host))
        except Exception:
            # Never emit exception strings, raw responses, addresses or secrets.
            failures.append({"hostname": host.upper(), "read_pass_failed": True})
    result = {"captured_utc": datetime.now(timezone.utc).isoformat(),
              "mode": "paced_show_commands_only", "observations": observations,
              "failures": failures, "reciprocity": reciprocal_summary(observations),
              "minimum_spacing_seconds": SPACING, "mutations_performed": False}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
