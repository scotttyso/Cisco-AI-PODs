#!/usr/bin/env python3
"""Query running firmware versions from standalone UCS C-Series servers via the Cisco IMC XML API.

Examples:
    export local_user_password_1='...'
    ./ucs_imc_firmware.py 192.168.65.106
    ./ucs_imc_firmware.py 192.168.65.106,192.168.65.107 -u admin
    ./ucs_imc_firmware.py 192.168.65.106,192.168.65.107 --system-only
    ./ucs_imc_firmware.py -f hosts.txt --json
    ./ucs_imc_firmware.py -f examples/ucs_imc/hosts.example.yaml --system-only
"""

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from xml.sax.saxutils import quoteattr

import requests
import urllib3
import yaml

try:
    from defusedxml.ElementTree import fromstring
except ImportError:
    from xml.etree.ElementTree import fromstring  # nosec B405 - response comes from the target IMC


class ImcError(Exception):
    pass


class ImcSession:
    def __init__(self, host, username, password, verify, timeout):
        self.url = f"https://{host}/nuova"
        self.username = username
        self.password = password
        self.verify = verify
        self.timeout = timeout
        self.cookie = None

    def _post(self, body):
        resp = requests.post(
            self.url,
            data=body,
            headers={"Content-Type": "application/xml"},
            verify=self.verify,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        root = fromstring(resp.text)
        if root.get("errorCode"):
            raise ImcError(f"{root.get('errorCode')}: {root.get('errorDescr')}")
        return root

    def __enter__(self):
        root = self._post(
            f"<aaaLogin inName={quoteattr(self.username)} inPassword={quoteattr(self.password)}></aaaLogin>"
        )
        self.cookie = root.get("outCookie")
        if not self.cookie:
            raise ImcError("Login failed: no session cookie returned")
        return self

    def __exit__(self, *exc):
        if self.cookie:
            try:
                self._post(f"<aaaLogout cookie={quoteattr(self.cookie)} inCookie={quoteattr(self.cookie)}></aaaLogout>")
            except (requests.RequestException, ImcError):
                pass
            self.cookie = None

    def resolve_class(self, class_id):
        root = self._post(
            f"<configResolveClass cookie={quoteattr(self.cookie)} inHierarchical='false' "
            f"classId={quoteattr(class_id)}/>"
        )
        return [el.attrib for el in root.iter(class_id)]


def get_firmware(host, username, password, verify, timeout):
    result = {"host": host, "model": None, "serial": None, "firmware": [], "error": None}
    try:
        with ImcSession(host, username, password, verify, timeout) as imc:
            units = imc.resolve_class("computeRackUnit")
            if units:
                result["model"] = units[0].get("model")
                result["serial"] = units[0].get("serial")
            for fw in imc.resolve_class("firmwareRunning"):
                result["firmware"].append(
                    {
                        "dn": fw.get("dn"),
                        "type": fw.get("type"),
                        "deployment": fw.get("deployment"),
                        "version": fw.get("version"),
                    }
                )
            result["firmware"].sort(key=lambda f: f["dn"] or "")
    except (requests.RequestException, ImcError, ValueError) as err:
        result["error"] = str(err)
    return result


def is_system_fw(fw):
    return re.fullmatch(r"sys/rack-unit-\d+/mgmt/fw-system", fw["dn"] or "") is not None


def print_system_table(results):
    rows = [("HOST", "MODEL", "SERIAL", "FW-SYSTEM")]
    for r in results:
        if r["error"]:
            version = f"ERROR: {r['error']}"
        else:
            version = next((f["version"] for f in r["firmware"] if is_system_fw(f)), "not found")
        rows.append((r["host"], r["model"] or "", r["serial"] or "", version))
    widths = [max(len(row[i]) for row in rows) for i in range(3)]
    for row in rows:
        print("  ".join(col.ljust(w) for col, w in zip(row[:3], widths)) + "  " + row[3])


def print_table(results):
    for r in results:
        print(f"\n=== {r['host']}  model={r['model']}  serial={r['serial']}")
        if r["error"]:
            print(f"  ERROR: {r['error']}")
            continue
        width = max((len(f["dn"] or "") for f in r["firmware"]), default=2)
        print(f"  {'DN'.ljust(width)}  {'DEPLOYMENT'.ljust(10)}  VERSION")
        for f in r["firmware"]:
            print(f"  {(f['dn'] or '').ljust(width)}  {(f['deployment'] or '').ljust(10)}  {f['version']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("hosts", nargs="*", help="IMC IPs/hostnames, comma and/or space separated")
    parser.add_argument(
        "-f", "--hosts-file",
        help="YAML file (.yaml/.yml) with a 'hosts' list, or a text file with one host per line",
    )
    parser.add_argument("-u", "--username", default="admin", help="IMC username (default: admin)")
    parser.add_argument(
        "-p", "--password-env", default="local_user_password_1",
        help="Environment variable holding the password (default: local_user_password_1)",
    )
    parser.add_argument("--verify", action="store_true", help="Verify TLS certificates (off by default for self-signed IMC certs)")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds (default: 30)")
    parser.add_argument("--workers", type=int, default=10, help="Parallel hosts (default: 10)")
    parser.add_argument("--system-only", action="store_true", help="Only report the fw-system (CIMC) version per server")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    entries = list(args.hosts)
    if args.hosts_file:
        with open(args.hosts_file, encoding="utf-8") as fh:
            if args.hosts_file.endswith((".yaml", ".yml")):
                data = yaml.safe_load(fh) or {}
                host_list = data.get("hosts", []) if isinstance(data, dict) else data
                if not isinstance(host_list, list):
                    sys.exit(f"{args.hosts_file}: 'hosts' must be a list")
                entries += [str(h) for h in host_list if h]
            else:
                entries += [ln.split("#", 1)[0] for ln in fh]
    hosts = list(dict.fromkeys(h.strip() for e in entries for h in e.split(",") if h.strip()))
    if not hosts:
        parser.error("provide at least one host or --hosts-file")

    password = os.environ.get(args.password_env)
    if not password:
        sys.exit(f"Environment variable {args.password_env} is not set")

    if not args.verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(
            pool.map(lambda h: get_firmware(h, args.username, password, args.verify, args.timeout), hosts)
        )

    if args.system_only:
        for r in results:
            r["firmware"] = [f for f in r["firmware"] if is_system_fw(f)]

    if args.json:
        print(json.dumps(results, indent=2))
    elif args.system_only:
        print_system_table(results)
    else:
        print_table(results)

    sys.exit(1 if any(r["error"] for r in results) else 0)


if __name__ == "__main__":
    main()
