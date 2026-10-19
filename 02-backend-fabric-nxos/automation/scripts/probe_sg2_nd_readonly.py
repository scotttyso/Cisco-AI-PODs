#!/usr/bin/env python3
"""Two paced API-key GETs for SG2 fabric/inventory; no ND login or mutation."""

import argparse
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import ssl
import stat
import time
import urllib.error
import urllib.request

import yaml

from probe_sg2_connectivity import HOSTS, SPACING


FABRIC = "AIPOD-BE-SG2-Fabric"
FABRIC_PATH = "/appcenter/cisco/ndfc/api/v1/lan-fabric/rest/control/fabrics/" + FABRIC
PATHS = (FABRIC_PATH, FABRIC_PATH + "/inventory/switchesByFabric")
MAX_BYTES = 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        return None


def summarize(fabric, records, expected):
    if (not isinstance(fabric, dict) or not isinstance(records, list) or len(records) != 4
            or set(expected) != {host.upper() for host in HOSTS}):
        raise ValueError("Unexpected SG2 fabric/inventory shape")
    if fabric.get("fabricName", fabric.get("FABRIC_NAME", FABRIC)) != FABRIC:
        raise ValueError("Fabric identity mismatch")
    names = [item.get("logicalName") if isinstance(item, dict) else None for item in records]
    if len(set(names)) != 4 or set(names) != set(expected):
        raise ValueError("ND SG2 hostnames differ from inventory")
    output = []
    for item in records:
        name = item["logicalName"]
        spec = expected[name]
        output.append({"hostname": name,
                       "management_address_matches_inventory": item.get("ipAddress") == spec["mgmt_ip"],
                       "role_matches_inventory": item.get("switchRole") == spec["role"],
                       "model_matches_sg2": item.get("model") == "N9364E-SG2-O",
                       "nd_inventory_status_ok": item.get("status") == "ok"})
    status = fabric.get("operStatus")
    normalized = status.upper() if isinstance(status, str) else "MISSING"
    allowed = {"HEALTHY", "UNHEALTHY", "WARNING", "CRITICAL", "UNKNOWN", "DEGRADED",
               "NOT_READY", "NA", "N/A", "OUT_OF_SYNC", "OUT-OF-SYNC", "MISSING"}
    return {"fabric": FABRIC, "requests": 2,
            "nd_fabric_oper_status_healthy": normalized == "HEALTHY",
            "nd_fabric_oper_status": normalized if normalized in allowed else "UNRECOGNIZED",
            "nd_fabric_oper_status_present": isinstance(fabric.get("operStatus"), str),
            "switches": sorted(output, key=lambda entry: entry["hostname"]),
            "intended_cabling_verified": False, "e2e_complete": False,
            "nd_rollup_does_not_override_zero_bgp_peers": True,
            "configuration_mutations_performed": False}


def read_once(inventory_dir, allow_self_signed_lab=False, pause=time.sleep):
    inventory_dir = inventory_dir.resolve()
    if allow_self_signed_lab and inventory_dir.name != "lab":
        raise ValueError("TLS exception is lab-only")
    endpoint = yaml.safe_load((inventory_dir / "host_vars" / "nd-1.yml").read_text())
    address = str(ipaddress.ip_address(endpoint["nd_node"]["mgmt"]["ip"]))
    fabrics = yaml.safe_load((inventory_dir / "group_vars" / "backend_fabric_switches.yml").read_text())
    sg2 = [item for item in fabrics["be_fabrics"] if item.get("key") == "sg2"]
    if len(sg2) != 1 or sg2[0].get("name") != FABRIC:
        raise ValueError("SG2 fabric identity changed")
    expected = {}
    for host in HOSTS:
        item = yaml.safe_load((inventory_dir / "host_vars" / (host + ".yml")).read_text())["be_switch"]
        if item["fabric_key"] != "sg2" or item["hostname"] != host.upper():
            raise ValueError("Canonical SG2 host identity changed")
        expected[item["hostname"]] = item
    vault_path = inventory_dir / "group_vars" / "vault.yml"
    if stat.S_IMODE(vault_path.stat().st_mode) & 0o077:
        raise ValueError("Vault permissions too broad")
    vault = yaml.safe_load(vault_path.read_text())
    username, key = vault.get("vault_nd_api_username"), vault.get("vault_nd_api_key")
    if any(not isinstance(value, str) or not value or value.startswith("<") for value in (username, key)):
        raise ValueError("API-key reference unresolved")
    context = ssl._create_unverified_context() if allow_self_signed_lab else ssl.create_default_context()
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context),
                                        urllib.request.ProxyHandler({}), NoRedirect())
    replies = []
    for index, path in enumerate(PATHS):
        if index:
            pause(SPACING)
        request = urllib.request.Request("https://" + address + path, method="GET",
                                         headers={"Accept": "application/json",
                                                  "X-Nd-Username": username, "X-Nd-Apikey": key})
        with opener.open(request, timeout=20) as response:
            if response.status != 200:
                raise ValueError("Unexpected ND HTTP status")
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError("ND response too large")
            replies.append(json.loads(body))
    return summarize(*replies, expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory_dir", type=Path)
    parser.add_argument("--allow-self-signed-lab", action="store_true")
    args = parser.parse_args()
    try:
        result = read_once(args.inventory_dir, args.allow_self_signed_lab)
    except urllib.error.HTTPError as error:
        result = {"read_pass_failed": True, "http_status": error.code, "response_body_retained": False}
    except Exception:
        result = {"read_pass_failed": True, "response_body_retained": False}
    result["captured_utc"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result.get("read_pass_failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
