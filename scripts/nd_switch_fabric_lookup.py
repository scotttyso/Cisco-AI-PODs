#!/usr/bin/env python3
"""Look up the Nexus Dashboard fabric name for each switch IP in a YAML input sheet.

The input sheet uses the same nexus_dashboard and switches sections as nxos_bootflash_stage.yaml;
other sections are ignored, so the bootflash staging sheet can be passed as-is.

Password comes from NEXUS_DASHBOARD_PASSWORD (prompted when unset).
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

import requests
import urllib3
import yaml

ENV_ND = "NEXUS_DASHBOARD_PASSWORD"
API_PREFIX = "/api/v1"
INVENTORY = "/manage/inventory/switches"
PAGE_SIZE = 100
IP_FIELDS = ("fabricManagementIp", "managementIp", "switchIp", "ipAddress", "managementIpAddress")


class NexusDashboard:
    def __init__(self, url: str, username: str, password: str, verify_tls: bool, timeout: int, domain: str):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.verify = verify_tls
        if not verify_tls:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = self.session.post(
            f"{self.url}{API_PREFIX}/infra/login",
            json={"domain": domain, "userName": username, "userPasswd": password},
            timeout=(10, timeout),
        )
        self._check(response)
        try:
            token = response.json().get("jwttoken") or response.json().get("token")
        except ValueError:
            token = None
        if token and "AuthCookie" not in self.session.cookies:
            self.session.cookies.set("AuthCookie", token)
        if "AuthCookie" not in self.session.cookies:
            raise RuntimeError("ND login succeeded but did not return an AuthCookie token")

    @staticmethod
    def _check(response: requests.Response) -> None:
        if not response.ok:
            raise RuntimeError(f"ND API returned HTTP {response.status_code}: {response.text[:1200]}")

    def get(self, path: str):
        response = self.session.get(f"{self.url}{API_PREFIX}{path}", timeout=(10, self.timeout))
        self._check(response)
        return response.json() if response.content else None


def field(item: dict, *names: str) -> str:
    lowered = {str(key).lower(): value for key, value in item.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def get_inventory(client: NexusDashboard) -> list:
    records, offset = [], 0
    while True:
        payload = client.get(f"{INVENTORY}?max={PAGE_SIZE}&offset={offset}&sort=hostname%3Aasc")
        page = payload.get("switches") if isinstance(payload, dict) else payload
        page = [r for r in page or [] if isinstance(r, dict)]
        records.extend(page)
        if len(page) < PAGE_SIZE:
            return records
        offset += PAGE_SIZE


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    nd = cfg.get("nexus_dashboard") or {}
    hosts = (cfg.get("switches") or {}).get("hosts") or []
    if not nd.get("host") or not nd.get("username"):
        raise SystemExit(f"{path}: nexus_dashboard.host and nexus_dashboard.username are required")
    if not isinstance(hosts, list) or not hosts:
        raise SystemExit(f"{path}: switches.hosts must be a non-empty list of IPs")
    if not isinstance(nd.get("verify_ssl", False), bool):
        raise SystemExit(f"{path}: nexus_dashboard.verify_ssl must be true or false")
    return {"nd": nd, "hosts": [str(h).strip() for h in hosts]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Get the ND fabric name for a list of switch IPs.")
    parser.add_argument("--config", type=Path, required=True, help="YAML input sheet")
    parser.add_argument("--domain", help="ND login domain; overrides nexus_dashboard.domain (default: local)")
    parser.add_argument("--yaml", action="store_true", help="Print results as YAML instead of a table")
    args = parser.parse_args()

    cfg = load_config(args.config.expanduser())
    nd = cfg["nd"]
    url = nd["host"] if str(nd["host"]).startswith("https://") else f"https://{nd['host']}"
    password = os.environ.get(ENV_ND) or getpass.getpass(f"ND password for {nd['username']}: ")

    try:
        client = NexusDashboard(
            url,
            nd["username"],
            password,
            nd.get("verify_ssl", False),
            int(nd.get("timeout", 120)),
            args.domain or nd.get("domain", "local"),
        )
        inventory = get_inventory(client)
    except (requests.RequestException, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    by_ip = {}
    for item in inventory:
        ip = field(item, *IP_FIELDS).split("/")[0]
        fabric = field(item, "fabricName")
        if ip and fabric:
            by_ip[ip] = {"hostname": field(item, "hostname", "switchName", "name"), "fabric": fabric}

    results = [{"ip": ip, **by_ip.get(ip, {"hostname": "", "fabric": ""})} for ip in cfg["hosts"]]
    missing = [r["ip"] for r in results if not r["fabric"]]

    if args.yaml:
        print(yaml.safe_dump({"switches": results}, sort_keys=False), end="")
    else:
        print(f"{'IP':<18} {'HOSTNAME':<30} FABRIC")
        for r in results:
            print(f"{r['ip']:<18} {r['hostname'] or '-':<30} {r['fabric'] or 'NOT FOUND'}")
    if missing:
        print(f"WARNING: not found in ND: {', '.join(missing)}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
