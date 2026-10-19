#!/usr/bin/env python3
"""BE-only physical core gate before fabric-template deployment through ND.

Exit 0: physical expectation met; 1: connectivity discrepancy (or inventory
mismatch with --require-inventory-match); 2: incomplete
evidence/input failure. Cloud-scale checks two links per spine/leaf pair,
not exact port intent. SG2 checks an explicit cabling-plan CSV, not learned LLDP.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

import paramiko
import yaml

FABRICS = {}
FABRIC_NAMES = {}
SWITCH_ROLES = {}
ALL_NAMES = set()
SWITCH_HOST_VARS = {}
COMMANDS = ("show switchname", "show lldp neighbors", "show interface status")
SPACING = 3
MAX_BYTES = 512 * 1024
PORT_RE = r"(?:Eth|Ethernet|e)\d+/\d+(?:/\d+)?"
STATE_RE = r"connected|notconnect|notconnec|disabled|err-disabled|sfpAbsent|xcvrAbsent|xcvrAbsen|linkFlapErr|inactive|down"


def port(value):
    if not isinstance(value, str) or not re.fullmatch(PORT_RE, value, re.I):
        raise ValueError("Invalid physical port")
    return "Eth" + re.sub(r"^(?:Ethernet|Eth|e)", "", value, flags=re.I)


def cable(a, ap, b, bp):
    return tuple(sorted(((a, port(ap)), (b, port(bp)))))


def load_cabling_plan(path, fabric_key):
    if fabric_key not in FABRICS:
        raise ValueError("Unknown fabric in cabling plan")
    names = FABRICS[fabric_key]
    raw = path.read_bytes()
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    expected, endpoints = set(), set()
    for row in rows:
        a, b = row["Source switch"].upper(), row["Destination switch"].upper()
        if row["Fabric"] != FABRIC_NAMES[fabric_key] or a not in names or b not in names:
            raise ValueError("Plan includes another fabric")
        if {SWITCH_ROLES[a], SWITCH_ROLES[b]} != {"spine", "leaf"}:
            raise ValueError("Plan is not spine to leaf")
        edge = cable(a, row["Source port"], b, row["Destination port"])
        if edge in expected or any(e in endpoints for e in edge):
            raise ValueError("Duplicate cable or reused plan port")
        expected.add(edge)
        endpoints.update(edge)
    pairs = {tuple(sorted((a, b))) for (a, _), (b, _) in expected}
    spines = [n for n in names if SWITCH_ROLES[n] == "spine"]
    leaves = [n for n in names if SWITCH_ROLES[n] == "leaf"]
    required = {tuple(sorted((s, l))) for s in spines for l in leaves}
    if pairs != required:
        raise ValueError("Plan does not cover every spine-to-leaf pair")
    return expected, {"file": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(),
                      "expected_child_lanes": len(expected)}


def parse_outputs(name, outputs):
    if name not in ALL_NAMES or len(outputs) != len(COMMANDS) or outputs[0].strip().upper() != name:
        raise ValueError("Switch identity mismatch")
    for body in outputs:
        if re.search(r"Invalid command|Invalid input|Syntax error|Authorization failed|--More--", body, re.I):
            raise ValueError("Failed or paginated read")
    body = outputs[1]
    total = re.search(r"Total entries displayed\s*:\s*(\d+)", body, re.I)
    if not total or not re.search(r"Device ID\s+Local Intf", body, re.I):
        raise ValueError("Unrecognized LLDP format")
    links, seen, row_count, pending = [], set(), 0, None
    in_table = False
    for line in body.splitlines():
        if re.search(r"Device ID\s+Local Intf", line, re.I):
            in_table = True
            continue
        if re.search(r"Total entries displayed", line, re.I):
            if pending is not None:
                raise ValueError("Incomplete wrapped LLDP row")
            in_table = False
        fields = line.split()
        if not in_table or not fields or set(line.strip()) <= {"-", " "}:
            continue
        # NX-OS wraps a long Device ID onto its own line. It is counted once,
        # joined to exactly four remaining columns and never retained verbatim.
        if len(fields) == 1 and pending is None:
            pending = fields[0]
            continue
        if pending is not None:
            if len(fields) != 4:
                raise ValueError("Invalid wrapped LLDP continuation")
            fields = [pending] + fields
            pending = None
        if len(fields) < 5:
            raise ValueError("Incomplete LLDP row")
        row_count += 1
        if fields[1].lower() == "mgmt0":
            continue
        local = port(fields[1])
        if local in seen:
            raise ValueError("Multiple neighbors on one local port")
        seen.add(local)
        remote_name = fields[0].split("(")[0].upper()
        peer = remote_name if remote_name in ALL_NAMES else "outside_be_core"
        remote_port = port(fields[-1]) if re.fullmatch(PORT_RE, fields[-1], re.I) else None
        if peer in ALL_NAMES and remote_port is None:
            raise ValueError("Core peer physical port missing")
        links.append({"local_port": local, "peer": peer, "peer_port": remote_port})
    if row_count != int(total.group(1)):
        raise ValueError("LLDP count does not match parsed rows")
    states = {}
    if not re.search(r"Port\s+Name\s+Status\s+Vlan", outputs[2], re.I):
        raise ValueError("Unrecognized interface status format")
    for line in outputs[2].splitlines():
        fields = line.split()
        if not fields or not re.fullmatch(PORT_RE, fields[0], re.I):
            continue
        local = port(fields[0])
        match = re.search(r"\s(" + STATE_RE + r")\s+", line, re.I)
        if local in states:
            raise ValueError("Duplicate interface row")
        if not match:
            # Unknown state is not 'up'. Only expected/observed core ports
            # influence the gate; unfamiliar spare-port states cannot invent
            # missing cables or erase the good core observations.
            states[local] = {"state": "unverified", "speed": "unverified"}
            continue
        tail = line[match.end():].split()
        if len(tail) < 3:
            raise ValueError("Incomplete interface row")
        speed = tail[2]
        state = {"xcvrabsen": "xcvrAbsent", "notconnec": "notconnect"}.get(match.group(1).lower(), match.group(1).lower())
        states[local] = {"state": state,
                         "speed": speed if re.fullmatch(r"(?:a-)?\d+(?:\.\d+)?[GMK]?|auto", speed, re.I) else "unverified"}
    if not states:
        raise ValueError("Empty interface status table")
    return {"hostname": name, "links": links, "ports": states, "commands": len(COMMANDS)}


def evaluate(fabric, observations, expected=None):
    names = FABRICS[fabric]
    selected = [o for o in observations if o["hostname"] in names]
    if len({o["hostname"] for o in selected}) != len(selected):
        raise ValueError("Duplicate switch observation")
    by_name = {o["hostname"]: o for o in observations if o["hostname"] in names}
    issues, incomplete, directed = [], [], set()
    for name in names:
        if name not in by_name:
            incomplete.append({"type": "switch_evidence_missing", "switch": name})
            continue
        for link in by_name[name]["links"]:
            peer = link["peer"]
            if peer not in names:
                # Non-core uplinks/server ports are outside this gate. A BE
                # cross-fabric peer or foreign peer on a planned core port
                # is a discrepancy. Unplanned-fabric pair counts still catch loss
                # of a required spine/leaf connection.
                if peer in ALL_NAMES or (expected and any((name, link["local_port"]) in e for e in expected)):
                    issues.append({"type": "unexpected_core_peer", "switch": name, "port": link["local_port"], "peer": peer})
                continue
            if {SWITCH_ROLES.get(name), SWITCH_ROLES.get(peer)} != {"spine", "leaf"}:
                issues.append({"type": "not_spine_to_leaf", "switch": name, "peer": peer})
            directed.add((name, link["local_port"], peer, link["peer_port"]))
    edges = {cable(*e) for e in directed}
    for name in names:
        observation = by_name.get(name)
        if not observation:
            continue
        declared = set(observation.get("inventory_core_ports", []))
        if not declared:
            continue
            # A core port intent only names local ports, so derive this switch's
        # observed endpoint set directly from its own LLDP rows.
        observed_ports = {link["local_port"] for link in observation["links"] if link["peer"] in names}
        for port_name in sorted(declared - observed_ports):
            issues.append({"type": "inventory_core_port_missing_lldp", "switch": name, "port": port_name})
        for port_name in sorted(observed_ports - declared):
            issues.append({"type": "core_port_not_in_inventory", "switch": name, "port": port_name})
    reciprocal = {cable(*e) for e in directed if (e[2], e[3], e[0], e[1]) in directed}
    for edge in sorted(edges - reciprocal):
        if all(n in by_name for n, _ in edge):
            issues.append({"type": "one_way_lldp", "endpoints": edge})
    targets = edges | (expected or set())
    discovered = []
    for edge in sorted(targets):
        ends = []
        for name, p in edge:
            status = by_name.get(name, {}).get("ports", {}).get(p)
            if status is None:
                incomplete.append({"type": "port_state_unverified", "switch": name, "port": p})
                status = {"state": "unverified", "speed": "unverified"}
            elif status["state"] == "unverified":
                incomplete.append({"type": "port_state_unverified", "switch": name, "port": p})
            elif status["state"] != "connected":
                issues.append({"type": "port_down", "switch": name, "port": p, "state": status["state"]})
            ends.append({"switch": name, "port": p, **status})
        if edge in edges:
            discovered.append({"ends": ends, "reciprocal": edge in reciprocal})
            speeds = {end["speed"] for end in ends}
            if "unverified" in speeds or "auto" in speeds:
                incomplete.append({"type": "link_speed_unverified", "endpoints": edge})
            elif len(speeds) != 1:
                issues.append({"type": "link_speed_mismatch", "endpoints": edge})
    if expected is not None:
        for edge in sorted(expected - reciprocal):
            if all(n in by_name for n, _ in edge):
                issues.append({"type": "expected_cable_missing_or_not_reciprocal", "endpoints": edge})
        for edge in sorted(edges - expected):
            issues.append({"type": "unexpected_cable", "endpoints": edge})
        expectation = "exact endpoint map from supplied cabling plan"
    else:
        expectation = "two reciprocal links per spine-to-leaf pair; exact port intent not asserted"
        spines = [n for n in names if SWITCH_ROLES[n] == "spine"]
        leaves = [n for n in names if SWITCH_ROLES[n] == "leaf"]
        for s in spines:
            for l in leaves:
                if s not in by_name or l not in by_name:
                    continue
                count = sum({a, b} == {s, l} for (a, _), (b, _) in reciprocal)
                if count != 2:
                    issues.append({"type": "pair_link_count", "spine": s, "leaf": l, "expected": 2, "observed": count})
    return {"fabric": fabric, "expectation": expectation, "discovered_connections": discovered,
            "reciprocal_connections": len(reciprocal), "issues": issues, "incomplete_evidence": incomplete,
            "physical_gate": "INCOMPLETE" if incomplete else "FAIL" if issues else "PASS",
            "bgp_required": False, "nd_deployment_performed": False}


def read_switch(inventory, host, fabric, pause=time.sleep, vault_file=None):
    if host not in FABRICS[fabric]:
        raise ValueError("Outside BE scope")
    switch = SWITCH_HOST_VARS[host]
    if switch["hostname"] != host or switch["fabric_key"] != fabric or switch["role"] != SWITCH_ROLES[host]:
        raise ValueError("Inventory identity mismatch")
    vault_path = Path(vault_file) if vault_file else inventory / "group_vars" / "vault.yml"
    if stat.S_IMODE(vault_path.stat().st_mode) & 0o077:
        raise ValueError("Vault access too broad")
    raw = vault_path.read_text()
    if raw.lstrip().startswith("$ANSIBLE_VAULT"):
        # Encrypted vaults may be committed; decrypt with the configured ANSIBLE_VAULT_PASSWORD_FILE.
        decrypted = subprocess.run(["ansible-vault", "view", str(vault_path)], capture_output=True, text=True,
                                   timeout=30)
        if decrypted.returncode != 0:
            raise ValueError("Vault could not be decrypted")
        raw = decrypted.stdout
    else:
        ignored = subprocess.run(["git", "check-ignore", "--quiet", str(vault_path.resolve())],
                                 cwd=inventory, capture_output=True, timeout=5)
        if ignored.returncode != 0:
            raise ValueError("Vault is not Git ignored")
    vault = yaml.safe_load(raw)
    password = vault.get("vault_" + switch["pass_ref"].lower())
    if not isinstance(password, str) or not password or password.startswith("<"):
        raise ValueError("Credential reference unresolved")
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(switch["mgmt_ip"], username=switch["username"], password=password,
                       look_for_keys=False, allow_agent=False, timeout=10, auth_timeout=10, banner_timeout=10)
        outputs = []
        for index, command in enumerate(COMMANDS):
            if index:
                pause(SPACING)
            stdin, stdout, stderr = client.exec_command(command, timeout=20)
            try:
                body, error = stdout.read(MAX_BYTES + 1), stderr.read(MAX_BYTES + 1)
                if len(body) > MAX_BYTES or len(error) > MAX_BYTES or error.strip() or stdout.channel.recv_exit_status() != 0:
                    raise ValueError("Read response rejected")
                outputs.append(body.decode("utf-8", errors="strict"))
                if index == 0 and outputs[0].strip().upper() != host:
                    raise ValueError("Live identity mismatch")
            finally:
                stdin.close()
                stdout.close()
                stderr.close()
        result = parse_outputs(host, outputs)
        declared = {port(p) for p in switch.get("fabric_link_interfaces", [])}
        result["inventory_core_ports"] = sorted(declared)
        return result
    finally:
        client.close()


def render_report(result):
    lines = ["# Backend fabric core connectivity", "", f"Read-only sample: {result['started_utc']} to {result['finished_utc']}.", "",
             "Spine–leaf core only. Unused and server-facing ports are excluded. This checks cabling before fabric-template deployment through the existing ND system, not ND installation or BGP, optics/counter, traffic or fabric-health sign-off.", "", "## Discovered connectivity", ""]
    for check in result["fabrics"]:
        lines += [f"### {check['fabric']}", "", f"{check['reciprocal_connections']} reciprocal connections. Physical gate: {check['physical_gate']}.", "",
                  "| Switch | Port | Peer | Peer port | State at both ends | Speed at both ends | Reciprocal |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for link in check["discovered_connections"]:
            a, b = link["ends"]
            lines.append(f"| {a['switch']} | {a['port']} | {b['switch']} | {b['port']} | {a['state']} / {b['state']} | {a['speed']} / {b['speed']} | {'yes' if link['reciprocal'] else 'no'} |")
        lines.append("")
    lines += ["## What does not seem right", ""]
    for check in result["fabrics"]:
        lines += [f"### {check['fabric']}", "", f"Expected: {check['expectation']}.", ""]
        findings = check["issues"] + check["incomplete_evidence"]
        lines += ["- " + json.dumps(f, sort_keys=True) for f in findings] if findings else ["No missing, down, one-way or unexpected core connections detected against this expectation."]
        lines.append("")
    if result["inventory_warnings"]:
        lines += ["### Inventory differs from supplied cabling plan", "",
                  "| Switch | Planned core ports omitted from inventory | Inventory ports outside the plan |",
                  "| --- | --- | --- |"]
        for warning in result["inventory_warnings"]:
            lines.append(f"| {warning['switch']} | {len(warning['plan_ports_missing_from_inventory'])} | {len(warning['inventory_ports_not_in_plan'])} |")
        lines += ["", "These are stale local automation inputs, not missing live cables or ND-discovered inventory. Reconcile the fabric port lists before fabric-template deployment through ND. Exact differences are retained in the JSON report. This check did not change them."]
    lines += ["", "## Check method", "", "Three fixed show commands per switch, serial switches, at least three seconds between commands/switches, no automatic retries. Known SSH host keys and Git-ignored vault references are required. Raw responses and credentials are not retained.", "",
              "Cabling-plan sources: " + json.dumps(result.get("sg2_plan"), sort_keys=True), "",
              "Cloud-scale pair count comes from the existing repository upgrade verifier. Exact cloud-scale port assignments are observations, not a separately confirmed cabling plan.", ""]
    return "\n".join(lines)


def deployment_status(result):
    """One fail-closed decision shared by report and deployment entry points."""
    if result["read_failures"] or any(c["incomplete_evidence"] for c in result["fabrics"]):
        return 2
    if any(c["issues"] for c in result["fabrics"]) or (result["require_inventory_match"] and result["inventory_warnings"]):
        return 1
    return 0


def load_inventory(inventory_dir):
    global FABRICS, FABRIC_NAMES, SWITCH_ROLES, ALL_NAMES, SWITCH_HOST_VARS
    root = Path(inventory_dir)
    if root.is_file():
        root = root.parent
    inventory = yaml.safe_load((root / "inventory.yml").read_text())
    fabric_data = yaml.safe_load((root / "group_vars" / "backend_fabric_switches.yml").read_text())
    records = fabric_data.get("be_fabrics")
    if not isinstance(records, list) or not records:
        raise ValueError("Inventory has no backend fabric definitions")
    names_by_key = {}
    for record in records:
        key, name = record.get("key"), record.get("name")
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", key) or not isinstance(name, str) or not name:
            raise ValueError("Invalid backend fabric definition")
        if key in names_by_key:
            raise ValueError("Duplicate backend fabric key")
        names_by_key[key] = name

    def group_hosts(group):
        result = set((group.get("hosts") or {}).keys())
        for child in (group.get("children") or {}).values():
            result.update(group_hosts(child))
        return result

    try:
        group = inventory["all"]["children"]["backend_fabric_switches"]
    except (KeyError, TypeError):
        raise ValueError("Inventory has no backend_fabric_switches group")
    switch_records = {}
    for inventory_host in sorted(group_hosts(group)):
        host_path = root / "host_vars" / (inventory_host + ".yml")
        data = yaml.safe_load(host_path.read_text())
        switch = data.get("be_switch") if isinstance(data, dict) else None
        if not isinstance(switch, dict):
            raise ValueError("Backend switch host_vars are missing")
        key, hostname, role = switch.get("fabric_key"), switch.get("hostname"), switch.get("role")
        if key not in names_by_key or not isinstance(hostname, str) or not hostname or not isinstance(role, str):
            raise ValueError("Invalid backend switch host_vars")
        hostname = hostname.upper()
        if hostname in switch_records:
            raise ValueError("Duplicate backend switch hostname")
        switch_records[hostname] = switch
        switch["hostname"] = hostname

    by_fabric = {key: [] for key in names_by_key}
    roles = {}
    for hostname, switch in switch_records.items():
        roles[hostname] = switch["role"]
        if switch["role"] in ("spine", "leaf"):
            by_fabric[switch["fabric_key"]].append(hostname)
    ordered = {}
    for key, hosts in by_fabric.items():
        spines = sorted(h for h in hosts if roles[h] == "spine")
        leaves = sorted(h for h in hosts if roles[h] == "leaf")
        if not spines or not leaves:
            raise ValueError("Every backend fabric needs spine and leaf switches")
        ordered[key] = tuple(spines + leaves)
    FABRICS = ordered
    FABRIC_NAMES = names_by_key
    SWITCH_ROLES = roles
    ALL_NAMES = {h for hosts in ordered.values() for h in hosts}
    SWITCH_HOST_VARS = switch_records
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory_dir", type=Path)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--fabric", help="One fabric key or all fabrics")
    selection.add_argument("--fabrics", nargs="+", help="Only selected fabric keys")
    parser.add_argument("--plan", action="append", default=[], metavar="KEY=PATH",
                        help="Cabling-plan CSV for a fabric; may be repeated")
    parser.add_argument("--sg2-plan", type=Path, help="Backward-compatible alias for --plan sg2=PATH")
    parser.add_argument("--vault-file", type=Path, help="Restricted, Git-ignored vault used by the deployment")
    parser.add_argument("--require-inventory-match", action="store_true",
                        help="Also block deployment if inventory core ports differ from supplied plans")
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument("--gate-json", action="store_true",
                        help="Fresh sanitized JSON on stdout for Ansible; no report files or cached results")
    output.add_argument("--report-prefix", type=Path,
                        help="New .json and .md paths; existing files are never overwritten")
    args = parser.parse_args()
    reserved = []
    try:
        inventory = load_inventory(args.inventory_dir)
        if args.fabrics:
            fabrics = args.fabrics
        elif not args.fabric or args.fabric == "both":
            fabrics = list(FABRICS)
        else:
            fabrics = [args.fabric]
        if len(set(fabrics)) != len(fabrics) or not fabrics or any(key not in FABRICS for key in fabrics):
            raise ValueError("Invalid or duplicate target fabric")
        plans = {}
        for item in args.plan:
            if "=" not in item:
                raise ValueError("Each --plan must be KEY=PATH")
            key, path = item.split("=", 1)
            if key not in FABRICS or not path or key in plans:
                raise ValueError("Invalid or duplicate cabling plan")
            plans[key] = Path(path)
        if args.sg2_plan:
            if "sg2" not in FABRICS or "sg2" in plans:
                raise ValueError("--sg2-plan conflicts with inventory or --plan")
            plans["sg2"] = args.sg2_plan
        expected, sources = {}, {}
        for key in fabrics:
            if key in plans:
                expected[key], sources[key] = load_cabling_plan(plans[key], key)
        for suffix in (() if args.gate_json else (".json", ".md")):
            fd = os.open(str(args.report_prefix) + suffix, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            reserved.append(os.fdopen(fd, "w"))
        started = datetime.now(timezone.utc).isoformat()
        observations, failures, warnings = [], [], []
        for fabric in fabrics:
            for host in FABRICS[fabric]:
                if observations or failures:
                    time.sleep(SPACING)
                try:
                    options = {"vault_file": args.vault_file} if args.vault_file else {}
                    observation = read_switch(inventory, host, fabric, **options)
                    observations.append(observation)
                    if fabric in expected:
                        planned = {p for edge in expected[fabric] for n, p in edge if n == host}
                        declared = set(observation["inventory_core_ports"])
                        if declared != planned:
                            warnings.append({"fabric_key": fabric, "switch": host,
                                             "inventory_ports_not_in_plan": sorted(declared - planned),
                                             "plan_ports_missing_from_inventory": sorted(planned - declared)})
                    if not args.gate_json:
                        print(host + ": physical reads completed", flush=True)
                except Exception as error:
                    failures.append({"fabric_key": fabric, "switch": host, "read_failed": True,
                                     "failure_type": type(error).__name__})
                    if not args.gate_json:
                        print(host + ": read/validation failed (details suppressed)", flush=True)
        checks = [evaluate(key, observations, expected.get(key)) for key in fabrics]
        sg2_warnings = [warning for warning in warnings if warning["fabric_key"] == "sg2"]
        result = {"started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
                  "fabrics": checks, "read_failures": failures, "cabling_plans": sources,
                  "sg2_plan": sources.get("sg2"), "inventory_warnings": warnings,
                  "commands_per_switch": len(COMMANDS),
                  "inventory_matches_cabling_plans": not warnings,
                  "inventory_matches_sg2_plan": not sg2_warnings,
                  "require_inventory_match": args.require_inventory_match,
                  "minimum_spacing_seconds": SPACING, "mutations_performed": False}
        code = deployment_status(result)
        result["deployment_ready"] = code == 0
        if args.gate_json:
            print(json.dumps(result))
        else:
            reserved[0].write(json.dumps(result, indent=2) + "\n")
            reserved[1].write(render_report(result))
            for check in checks:
                print("{}: {}, {} reciprocal core links, {} discrepancies, {} incomplete checks".format(
                    check["fabric"], check["physical_gate"], check["reciprocal_connections"],
                    len(check["issues"]), len(check["incomplete_evidence"])))
        return code
    except Exception:
        if args.gate_json:
            print(json.dumps({"deployment_ready": False, "input_error": True,
                              "mutations_performed": False}))
        else:
            print("Input/output preflight failed; no readiness sign-off. Details suppressed to protect secrets.")
        return 2
    finally:
        for handle in reserved:
            handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
