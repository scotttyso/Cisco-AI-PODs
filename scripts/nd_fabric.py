#!/usr/bin/env python3
"""Nexus Dashboard fabric automation for the Automation UI fabric pages.

Reads one ``nexus_dashboard.fabrics`` file (schema ``fabrics``) and talks to Nexus Dashboard 4.x with the
login session cookie, using the same Manage and NDFC (lan-fabric) endpoints as the stage 02 backend workflow.

Commands:
  create       create the fabric, or update an existing one: fabric_settings and telemetry (out-of-band by default)
  poap         enable bootstrap (POAP) on the fabric from the ``poap`` block
  claim        wait for the switches in the POAP list, claim them by serial number, wait for the inventory, set roles
  add          discover switches that already have a configuration (no POAP) by management address
  ports        SSH to every switch and report the interfaces that have optics installed, plus LLDP neighbors
  apply-ports  configure each switch's hostInterfaces as host trunk ports
  deploy       recalculate and deploy the fabric configuration to every switch
  status       show the fabric, its switches, and the POAP list
  list         list every fabric on Nexus Dashboard (no --config needed)

Credentials come from the environment: ND_URL, ND_USERNAME, ND_PASSWORD (or nexus_dashboard_password /
ND_ADMIN_PASSWORD from the vault), SWITCH_USERNAME (default admin) and SWITCH_PASSWORD (or switch_password).
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

import yaml

NDFC = "/appcenter/cisco/ndfc/api/v1/lan-fabric/rest"
MANAGE = "/api/v1/manage"
POLL_SECONDS = 30
TELEMETRY_DEFAULTS = {"telemetryMode": "outofband", "telemetryVrf": "management", "telemetrySourceInterface": "mgmt0"}
BASE_MANAGEMENT = {
    "aaa": False, "advancedSshOption": False, "cdp": False, "day0Bootstrap": False,
    "interfaceStatisticsLoadInterval": 10, "localDhcpServer": False, "managementIpv4Prefix": 24,
    "managementIpv6Prefix": 64, "netflowSettings": {"netflow": False}, "powerRedundancyMode": "redundant",
    "ptp": False, "ptpDomainId": 0, "ptpLoopbackId": 0, "realTimeInterfaceStatisticsCollection": False,
    "snmpTrap": True,
}
CLASSIC_MANAGEMENT = {
    "coppPolicy": "manual", "inbandDay0Bootstrap": False, "inbandManagement": False, "mplsHandoff": False,
    "mplsLoopbackIdentifier": 101, "monitoredMode": False, "nxapi": False, "nxapiHttp": False, "nxapiHttpPort": 80,
    "nxapiHttpsPort": 443, "realTimeBackup": False, "scheduledBackup": False, "subInterfaceDot1qRange": "2-511",
}
VXLAN_MANAGEMENT = {
    "bgpAsn": "65000", "coppPolicy": "strict", "fabricMtu": 9216, "firstHopRedundancyProtocol": "hsrp",
    "intraFabricSubnetRange": "10.4.0.0/16", "l2HostInterfaceMtu": 9216, "networkVlanRange": "2300-2999",
    "nxapi": True, "nxapiHttp": True, "nxapiHttpPort": 80, "nxapiHttpsPort": 443, "vpcDomainIdRange": "1-1000",
}
AI_TYPES = ("aiVxlanEvpn", "aiRouted")
SWITCH_KEYS = ("ip", "hostname", "model", "serialNumber", "softwareVersion", "switchRole")


# --------------------------------------------------------------------------------------------- pure payload builders

def load_fabrics(path: str | Path) -> list[dict]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    fabrics = ((data.get("nexus_dashboard") or {}).get("fabrics")) or []
    return [fabric for fabric in fabrics if isinstance(fabric, dict) and fabric.get("name") and fabric.get("type")]


def telemetry_fields(fabric: dict) -> dict:
    """Top-level Manage record telemetry fields; out-of-band over mgmt0 in the management VRF unless set otherwise."""
    telemetry = {**TELEMETRY_DEFAULTS, **(fabric.get("telemetry") or {})}
    inband = telemetry.get("telemetryMode") == "inband"
    if inband and "telemetrySourceInterface" not in (fabric.get("telemetry") or {}):
        telemetry["telemetrySourceInterface"] = "loopback0"
    return {
        "telemetryCollection": bool(telemetry.get("telemetryCollection", True)),
        "telemetryCollectionType": "inBand" if inband else "outOfBand",
        "telemetrySourceInterface": telemetry["telemetrySourceInterface"],
        "telemetrySourceVrf": telemetry["telemetryVrf"],
        "telemetryStreamingProtocol": "ipv4",
    }


def management_settings(fabric: dict) -> dict:
    kind = fabric["type"]
    settings = dict(BASE_MANAGEMENT)
    if kind == "classicLan":
        settings.update(CLASSIC_MANAGEMENT)
    elif kind.startswith("vxlan") or kind in AI_TYPES:
        settings.update(VXLAN_MANAGEMENT)
    for key, value in (fabric.get("fabric_settings") or {}).items():
        if key != "performanceMonitoring":
            settings[key] = value
    for key in ("interfaceStatisticsLoadInterval", "realTimeInterfaceStatisticsCollection", "snmpTrap"):
        if key in (fabric.get("telemetry") or {}):
            settings[key] = fabric["telemetry"][key]
    settings.pop("performanceMonitoring", None)
    settings["type"] = kind
    return settings


def fabric_body(fabric: dict, current: dict | None = None) -> dict:
    """Manage API body: a new record, or the current record with this file's settings and telemetry applied."""
    location = (fabric.get("backend_settings") or {}).get("location") or {}
    if current:
        body = {key: value for key, value in current.items() if key != "location"}
        management = dict(current.get("management") or {})
        management.update({key: value for key, value in management_settings(fabric).items()
                           if key in (fabric.get("fabric_settings") or {}) or key == "type"})
        management.pop("performanceMonitoring", None)
        body["management"] = management
        if location.get("latitude") is not None:
            body["location"] = {"latitude": location["latitude"], "longitude": location["longitude"]}
        elif current.get("location"):
            body["location"] = current["location"]
    else:
        body = {"category": "fabric", "name": fabric["name"], "securityDomain": "all",
                "location": {"latitude": location.get("latitude", 37.33939),
                             "longitude": location.get("longitude", -121.89496)},
                "management": management_settings(fabric)}
    body["licenseTier"] = str(fabric.get("licenseTier") or body.get("licenseTier") or "essentials").lower()
    body.update(telemetry_fields(fabric))
    return body


def poap_settings(fabric: dict) -> dict:
    poap = {"enabled": True, "dhcp": "external", **(fabric.get("poap") or {})}
    if poap.get("gateway"):
        interface = ipaddress.ip_interface(str(poap["gateway"]))
        poap["gateway_ip"], poap["prefix"] = str(interface.ip), interface.network.prefixlen
    return poap


def bootstrap_nvpairs(fabric: dict, nvpairs: dict) -> dict:
    """Partial lan-fabric update that enables bootstrap (POAP), the payload shape cisco.dcnm.dcnm_fabric sends."""
    if str(nvpairs.get("IS_READ_ONLY", "false")).lower() == "true":
        raise ValueError(f"{fabric['name']} is in monitor mode (read-only); set fabric_settings.monitoredMode: false "
                         "and run Create fabric before enabling POAP")
    poap = poap_settings(fabric)
    local_dhcp = bool(poap["enabled"]) and poap["dhcp"] == "nexus_dashboard"
    # NDFC fabric nvPairs are strings.
    body = {"FABRIC_NAME": fabric["name"], "BOOTSTRAP_ENABLE": str(bool(poap["enabled"])).lower(),
            "DHCP_ENABLE": str(local_dhcp).lower()}
    if local_dhcp:
        missing = [name for name in ("dhcp_start", "dhcp_end", "gateway") if not poap.get(name)]
        if missing:
            raise ValueError(f"{fabric['name']}: poap.dhcp nexus_dashboard needs {', '.join(missing)}")
        body.update({"DHCP_START": poap["dhcp_start"], "DHCP_END": poap["dhcp_end"],
                     "MGMT_GW": poap["gateway_ip"], "MGMT_PREFIX": str(poap["prefix"])})
    return body


def claim_payload(fabric: dict, poap_list: list[dict], password: str) -> tuple[list[dict], list[str]]:
    """Bootstrap entries for the fabric switches that are waiting in the POAP list, and the switches still missing."""
    poap = poap_settings(fabric)
    if not poap.get("gateway"):
        raise ValueError(f"{fabric['name']}: set poap.gateway (management gateway/prefix) to claim switches")
    waiting = {str(item.get("serialNumber", "")).upper(): item for item in poap_list}
    entries, missing = [], []
    for switch in fabric.get("switches") or []:
        serial = str(switch.get("serialNumber") or "").upper()
        if not serial:
            raise ValueError(f"{switch.get('hostname')}: serialNumber is required to claim a POAP switch")
        found = waiting.get(serial)
        if not found:
            missing.append(f"{switch.get('hostname')} ({serial})")
            continue
        try:
            data = json.loads(found.get("data") or "{}")
        except (TypeError, ValueError):
            data = {}
        modules = data.get("modulesModel") or [found.get("model") or switch.get("model")]
        entries.append({
            "ipAddress": str(switch["ip"]), "discoveryAuthProtocol": "0", "password": password,
            "hostname": switch["hostname"], "model": found.get("model") or switch.get("model", ""),
            "serialNumber": found.get("serialNumber"), "version": found.get("version") or switch.get("softwareVersion", ""),
            "data": json.dumps({"modulesModel": modules, "gateway": str(poap["gateway"])}),
            "publicKey": found.get("publicKey", ""), "fingerprint": found.get("fingerprint", ""),
            "reAdd": found.get("reAdd", False), "imagePolicy": poap.get("image_policy") or "",
        })
    return entries, missing


def role_updates(fabric: dict, inventory: list[dict]) -> list[dict]:
    by_serial = {str(item.get("serialNumber", "")).upper(): item for item in inventory}
    by_ip = {str(item.get("ipAddress", "")): item for item in inventory}
    updates = []
    for switch in fabric.get("switches") or []:
        if not switch.get("switchRole"):
            continue
        found = by_serial.get(str(switch.get("serialNumber") or "").upper()) or by_ip.get(str(switch.get("ip")))
        if found and str(found.get("switchRole", "")).lower() != switch["switchRole"].lower():
            updates.append({"role": switch["switchRole"], "switchId": found["serialNumber"]})
    return updates


def host_port_payload(fabric: dict, serial: str, interfaces: list[str]) -> dict:
    """int_trunk_host policy for host-facing ports (jumbo MTU; PFC on AI fabrics), as cisco.dcnm.dcnm_interface sends."""
    ai = fabric["type"] in AI_TYPES
    entries = []
    for name in interfaces:
        entries.append({"serialNumber": serial, "interfaceType": "INTERFACE_ETHERNET", "ifName": name,
                        "fabricName": fabric["name"], "nvPairs": {
                            "INTF_NAME": name, "BPDUGUARD_ENABLED": "true", "PORTTYPE_FAST_ENABLED": "true",
                            "MTU": "jumbo", "SPEED": "Auto", "ALLOWED_VLANS": "all", "NATIVE_VLAN": "",
                            "ENABLE_ORPHAN_PORT": "false", "CDP_ENABLE": "true", "ENABLE_PFC": str(ai).lower(),
                            "ENABLE_MONITOR": "false", "PORT_DUPLEX_MODE": "auto", "ENABLE_QOS": "false",
                            "QOS_POLICY": "", "QUEUING_POLICY": "", "FEC": "auto", "DESC": "AI POD host port",
                            "CONF": "", "ADMIN_STATE": "true"}})
    return {"policy": "int_trunk_host", "interfaceType": "INTERFACE_ETHERNET", "interfaces": entries,
            "skipResourceCheck": "false"}


def _rows(data: dict, table: str, row: str) -> list[dict]:
    rows = ((data or {}).get(table) or {}).get(row) or []
    return [rows] if isinstance(rows, dict) else list(rows)


def parse_ports(transceivers: dict, lldp: dict | None = None, status: dict | None = None) -> list[dict]:
    """Interfaces with optics present from NX-OS ``show interface transceiver | json`` (+ LLDP / status JSON)."""
    neighbors = {row.get("l_port_id"): row for row in _rows(lldp or {}, "TABLE_nbor", "ROW_nbor")}
    states = {row.get("interface"): row for row in _rows(status or {}, "TABLE_interface", "ROW_interface")}
    ports = []
    for row in _rows(transceivers, "TABLE_interface", "ROW_interface"):
        name = row.get("interface")
        if not name or str(row.get("sfp", "")).lower() != "present":
            continue
        neighbor = neighbors.get(name) or {}
        state = states.get(name) or {}
        ports.append({"name": name, "transceiver": row.get("type") or row.get("partnum") or "",
                      "part": row.get("partnum", ""), "vendor": row.get("name", ""),
                      "state": state.get("state", ""), "speed": state.get("speed", ""),
                      "neighbor": neighbor.get("chassis_id", ""), "neighbor_port": neighbor.get("port_id", "")})
    return ports


# --------------------------------------------------------------------------------------------- Nexus Dashboard client

class NexusDashboard:
    def __init__(self, url: str, username: str, password: str, verify: bool = False):
        import requests
        import urllib3

        if not verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.base = url.rstrip("/")
        self.session = requests.Session()
        self.session.verify = verify
        response = self.session.post(f"{self.base}/api/v1/infra/login", timeout=30,
                                     json={"userName": username, "userPasswd": password, "domain": "DefaultAuth"})
        if response.status_code != 200:
            raise RuntimeError(f"Nexus Dashboard login failed: HTTP {response.status_code}")

    def call(self, method: str, path: str, body=None, ok=(200, 201, 202, 207), timeout: int = 120):
        response = self.session.request(method, f"{self.base}{path}", json=body, timeout=timeout)
        if response.status_code == 404 and method == "GET":
            return None
        if response.status_code not in ok:
            raise RuntimeError(f"{method} {path}: HTTP {response.status_code} {response.text[:500]}")
        try:
            return response.json() if response.text else {}
        except ValueError:
            return {"text": response.text}

    def fabric(self, name: str):
        return self.call("GET", f"{MANAGE}/fabrics/{quote(name)}")

    def legacy_fabric(self, name: str) -> dict:
        record = self.call("GET", f"{NDFC}/control/fabrics/{quote(name)}")
        if not record:
            raise RuntimeError(f"Fabric {name} does not exist; run Create fabric first")
        return record

    def inventory(self, name: str) -> list[dict]:
        return self.call("GET", f"{NDFC}/control/fabrics/{quote(name)}/inventory/switchesByFabric") or []

    def poap_list(self, name: str) -> list[dict]:
        response = self.call("GET", f"{NDFC}/control/fabrics/{quote(name)}/inventory/poap") or []
        return response.get("DATA", []) if isinstance(response, dict) else response


# --------------------------------------------------------------------------------------------- commands

def log(message: str) -> None:
    print(message, flush=True)


def connect() -> NexusDashboard:
    url = os.environ.get("ND_URL", "")
    password = next((os.environ[name] for name in ("ND_PASSWORD", "nexus_dashboard_password", "ND_ADMIN_PASSWORD")
                     if os.environ.get(name)), "")
    if not url or not password:
        raise SystemExit("ND_URL and the Nexus Dashboard admin password are required")
    verify = os.environ.get("ND_VERIFY_TLS", "false").lower() in ("1", "true", "yes")
    return NexusDashboard(url, os.environ.get("ND_USERNAME", "admin"), password, verify)


def switch_password() -> str:
    password = os.environ.get("SWITCH_PASSWORD") or os.environ.get("switch_password") or ""
    if not password:
        raise SystemExit("The fabric switch admin password is not set (Passwords and secrets)")
    return password


def cmd_create(nd: NexusDashboard, fabric: dict, args) -> None:
    current = nd.fabric(fabric["name"])
    body = fabric_body(fabric, current)
    if current:
        nd.call("PUT", f"{MANAGE}/fabrics/{quote(fabric['name'])}", body)
        log(f"Updated fabric {fabric['name']} ({fabric['type']})")
    else:
        nd.call("POST", f"{MANAGE}/fabrics", body)
        log(f"Created fabric {fabric['name']} ({fabric['type']})")
    log(f"  telemetry {body['telemetryCollectionType']} source {body['telemetrySourceInterface']} "
        f"vrf {body['telemetrySourceVrf']} (collection {'on' if body['telemetryCollection'] else 'off'})")
    if poap_settings(fabric)["enabled"]:
        cmd_poap(nd, fabric, args)


def cmd_poap(nd: NexusDashboard, fabric: dict, args) -> None:
    record = nd.legacy_fabric(fabric["name"])
    body = bootstrap_nvpairs(fabric, record.get("nvPairs") or {})
    nd.call("PUT", f"{NDFC}/control/fabrics/{quote(fabric['name'])}/{quote(record['templateName'])}", body)
    if body["DHCP_ENABLE"] == "true":
        log(f"POAP enabled on {fabric['name']}; Nexus Dashboard serves DHCP {body['DHCP_START']} - {body['DHCP_END']}")
    elif body["BOOTSTRAP_ENABLE"] == "true":
        log(f"POAP enabled on {fabric['name']} with external DHCP. The DHCP Bootstrap (Kea) scope must set option 66 "
            "(TFTP server) to the Nexus Dashboard address and option 67 (boot file) to poap_dcnm.py.")
    else:
        log(f"POAP disabled on {fabric['name']}")


def cmd_claim(nd: NexusDashboard, fabric: dict, args) -> None:
    password = switch_password()
    poap = poap_settings(fabric)
    wanted = {str(item.get("serialNumber") or "").upper() for item in fabric.get("switches") or []}
    deadline = time.monotonic() + int(args.timeout or poap.get("timeout") or 1800)
    claimed: set[str] = set()
    while True:
        present = {str(item.get("serialNumber", "")).upper() for item in nd.inventory(fabric["name"])}
        pending = [switch for switch in fabric.get("switches") or []
                   if str(switch.get("serialNumber") or "").upper() not in present | claimed]
        if not pending:
            break
        entries, missing = claim_payload({**fabric, "switches": pending}, nd.poap_list(fabric["name"]), password)
        if entries:
            nd.call("POST", f"{NDFC}/control/fabrics/{quote(fabric['name'])}/inventory/poap", entries, timeout=600)
            claimed.update(entry["serialNumber"].upper() for entry in entries)
            log("Claimed " + ", ".join(f"{entry['hostname']} ({entry['serialNumber']})" for entry in entries))
        if missing:
            log(f"Waiting for {len(missing)} switches to appear in the POAP list: {', '.join(missing)}")
        if time.monotonic() > deadline:
            raise SystemExit(f"Timed out; still waiting for {', '.join(missing) or 'claimed switches'}")
        time.sleep(POLL_SECONDS)
    log("Waiting for every switch to finish bootstrap and join the fabric inventory")
    while True:
        inventory = nd.inventory(fabric["name"])
        present = {str(item.get("serialNumber", "")).upper() for item in inventory}
        if wanted <= present:
            break
        if time.monotonic() > deadline:
            raise SystemExit(f"Timed out; not in the fabric yet: {', '.join(sorted(wanted - present))}")
        time.sleep(POLL_SECONDS)
    updates = role_updates(fabric, inventory)
    if updates:
        nd.call("POST", f"{MANAGE}/inventory/switchActions/changeRoles", {"switchRoles": updates})
        log("Set roles: " + ", ".join(f"{item['switchId']}={item['role']}" for item in updates))
    log(f"All {len(wanted)} switches are in {fabric['name']}. Next: Discover ports, then Apply port roles and Deploy.")


def cmd_add(nd: NexusDashboard, fabric: dict, args) -> None:
    switches = [{key: switch[key] for key in SWITCH_KEYS if switch.get(key)} for switch in fabric.get("switches") or []]
    body = {"switches": switches, "platformType": "nx-os", "preserveConfig": True, "snmpV3AuthProtocol": "md5-aes",
            "username": os.environ.get("SWITCH_USERNAME", "admin"), "password": switch_password(),
            "useCredentialForWrite": True}
    nd.call("POST", f"{MANAGE}/fabrics/{quote(fabric['name'])}/switches", body, timeout=600)
    log(f"Discovery started for {len(switches)} switches in {fabric['name']}")


def ssh_json(host: str, username: str, password: str, commands: list[str]) -> list[dict]:
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=username, password=password, timeout=30, look_for_keys=False, allow_agent=False)
    try:
        results = []
        for command in commands:
            _, stdout, _ = client.exec_command(f"{command} | json", timeout=120)
            text = stdout.read().decode("utf-8", "replace").strip()
            results.append(json.loads(text) if text.startswith("{") else {})
        return results
    finally:
        client.close()


def cmd_ports(nd: NexusDashboard | None, fabric: dict, args) -> None:
    password = switch_password()
    report = {"fabric": fabric["name"], "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "switches": {}}
    if args.report and Path(args.report).is_file():
        try:
            report["switches"].update(json.loads(Path(args.report).read_text(encoding="utf-8")).get("switches") or {})
        except ValueError:
            pass
    failed = []
    for switch in fabric.get("switches") or []:
        name = switch.get("hostname", switch.get("ip"))
        try:
            transceivers, lldp, status = ssh_json(str(switch["ip"]), switch.get("username") or
                                                  os.environ.get("SWITCH_USERNAME", "admin"), password,
                                                  ["show interface transceiver", "show lldp neighbors",
                                                   "show interface status"])
        except Exception as error:  # noqa: BLE001 - report every unreachable switch and continue
            failed.append(name)
            log(f"{name}: cannot read interfaces over SSH ({error})")
            continue
        ports = parse_ports(transceivers, lldp, status)
        report["switches"][name] = {"ip": switch["ip"], "serialNumber": switch.get("serialNumber", ""), "ports": ports}
        log(f"{name}: {len(ports)} interfaces with optics")
        for port in ports:
            log(f"  {port['name']:<14} {port['transceiver']:<24} {port['state']:<10} {port['neighbor']} {port['neighbor_port']}")
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
        log(f"Port report written to {args.report}. Assign fabric/host roles on the page, Save, then Apply port roles.")
    if failed:
        raise SystemExit(f"Could not read {len(failed)} switches: {', '.join(failed)}")


def cmd_apply_ports(nd: NexusDashboard, fabric: dict, args) -> None:
    inventory = nd.inventory(fabric["name"])
    by_ip = {str(item.get("ipAddress")): item.get("serialNumber") for item in inventory}
    changed = 0
    for switch in fabric.get("switches") or []:
        interfaces = switch.get("hostInterfaces") or []
        if not interfaces:
            continue
        serial = by_ip.get(str(switch.get("ip"))) or switch.get("serialNumber")
        if not serial:
            raise SystemExit(f"{switch['hostname']} is not in {fabric['name']}; claim or add it first")
        nd.call("PUT", f"{NDFC}/interface", host_port_payload(fabric, serial, interfaces))
        changed += len(interfaces)
        log(f"{switch['hostname']}: {len(interfaces)} host ports ({', '.join(interfaces)})")
    log(f"Configured {changed} host ports. Fabric links are discovered from LLDP and get the fabric policy "
        "automatically. Run Deploy to push the configuration." if changed else "No hostInterfaces in this file.")


def cmd_deploy(nd: NexusDashboard, fabric: dict, args) -> None:
    name = quote(fabric["name"])
    nd.call("POST", f"{NDFC}/control/fabrics/{name}/config-save", timeout=600)
    log(f"Recalculated {fabric['name']}")
    for item in nd.inventory(fabric["name"]):
        nd.call("POST", f"{NDFC}/control/fabrics/{name}/config-deploy/{item['serialNumber']}?forceShowRun=false",
                timeout=600)
        log(f"Deployed {item.get('logicalName') or item.get('ipAddress')}")


def cmd_status(nd: NexusDashboard, fabric: dict, args) -> None:
    record = nd.fabric(fabric["name"])
    if not record:
        log(f"{fabric['name']}: not created")
        return
    log(f"{fabric['name']}: {record.get('management', {}).get('type', fabric['type'])}, telemetry "
        f"{record.get('telemetryCollectionType', '?')} {record.get('telemetrySourceInterface', '')} "
        f"vrf {record.get('telemetrySourceVrf', '')}")
    for item in nd.inventory(fabric["name"]):
        log(f"  {item.get('logicalName', ''):<24} {item.get('ipAddress', ''):<16} {item.get('serialNumber', ''):<14} "
            f"{item.get('switchRole', ''):<8} {item.get('mode', '')} {item.get('ccStatus', '')}")
    waiting = nd.poap_list(fabric["name"])
    if waiting:
        log("  POAP list: " + ", ".join(f"{item.get('serialNumber')} ({item.get('model', '')})" for item in waiting))


def cmd_list(nd: NexusDashboard) -> None:
    response = nd.call("GET", f"{MANAGE}/fabrics") or {}
    fabrics = response.get("fabrics", []) if isinstance(response, dict) else response
    if not fabrics:
        log("No fabrics on Nexus Dashboard")
    for record in fabrics:
        log(f"{record.get('name', ''):<28} {(record.get('management') or {}).get('type', ''):<14} "
            f"license {record.get('licenseTier', '')}, telemetry {record.get('telemetryCollectionType', '-')}")


COMMANDS = {"create": cmd_create, "poap": cmd_poap, "claim": cmd_claim, "add": cmd_add, "ports": cmd_ports,
            "apply-ports": cmd_apply_ports, "deploy": cmd_deploy, "status": cmd_status}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=sorted([*COMMANDS, "list"]))
    parser.add_argument("--config", help="nexus_dashboard fabrics YAML file (all commands except list)")
    parser.add_argument("--fabric", help="Only this fabric name")
    parser.add_argument("--report", help="ports: JSON report path")
    parser.add_argument("--timeout", type=int, help="claim: seconds to wait (default poap.timeout or 1800)")
    args = parser.parse_args(argv)
    if args.command == "list":
        cmd_list(connect())
        return 0
    if not args.config:
        parser.error("--config is required")
    fabrics = [fabric for fabric in load_fabrics(args.config) if not args.fabric or fabric["name"] == args.fabric]
    if not fabrics:
        raise SystemExit(f"No fabrics in {args.config}")
    nd = None if args.command == "ports" else connect()
    for fabric in fabrics:
        try:
            COMMANDS[args.command](nd, fabric, args)
        except (ValueError, RuntimeError) as error:
            raise SystemExit(f"{fabric['name']}: {error}") from error
    return 0


if __name__ == "__main__":
    sys.exit(main())
