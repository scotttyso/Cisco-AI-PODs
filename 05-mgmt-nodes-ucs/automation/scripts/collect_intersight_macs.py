#!/usr/bin/env python3
"""Collect vNIC / host interface MAC addresses from Intersight for OpenShift node inventory.

For every ``--profile`` name the script reads the server profile vNICs (domain-attached X-Series and standalone
servers with a LAN connectivity policy). When ``--serial`` pairs are given and the profile has no vNICs, the
discovered VIC host Ethernet interfaces of that server are used instead.

Credentials come from ``intersight_api_key_id`` and ``intersight_secret_key`` (a PEM file path or PEM text) in the
environment, which the Automation UI provides from the vault.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests


def session() -> requests.Session:
    try:
        from intersight_auth import IntersightAuth
    except ImportError:
        sys.exit("The intersight-auth package is required: pip install intersight-auth")
    key_id = os.environ.get("intersight_api_key_id", "")
    secret = os.environ.get("intersight_secret_key", "")
    if not key_id or not secret:
        sys.exit("intersight_api_key_id and intersight_secret_key must be stored in the vault")
    client = requests.Session()
    client.auth = (IntersightAuth(api_key_id=key_id, secret_key_filename=secret) if os.path.isfile(secret)
                   else IntersightAuth(api_key_id=key_id, secret_key_string=secret))
    return client


def query(client: requests.Session, base: str, path: str, **params) -> list[dict]:
    response = client.get(f"{base}/api/v1/{path}", params={f"${key}": value for key, value in params.items()}, timeout=60)
    if response.status_code >= 400:
        raise RuntimeError(f"GET {path}: HTTP {response.status_code} {response.text[:200]}")
    return response.json().get("Results") or []


def _mac(value: str) -> str:
    return str(value or "").lower()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append", default=[], help="server profile name (inventory hostname)")
    parser.add_argument("--serial", action="append", default=[], help="NAME=SERIAL fallback for discovered VIC MACs")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default=os.environ.get("intersight_fqdn", "intersight.com"))
    args = parser.parse_args()
    base = args.url if args.url.startswith("http") else f"https://{args.url}"
    serials = dict(item.split("=", 1) for item in args.serial if "=" in item)
    names = list(dict.fromkeys(args.profile + list(serials)))
    if not names:
        print("No server profiles to query. Assign compute roles on the Initial Inventory page.")
        return 1
    client = session()
    result, failures = {}, 0
    for name in names:
        try:
            ports = {}
            profiles = query(client, base, "server/Profiles", filter=f"Name eq '{name}'", select="Name,Moid")
            if profiles:
                for vnic in query(client, base, "vnic/EthIfs", filter=f"Profile.Moid eq '{profiles[0]['Moid']}'",
                                  select="Name,MacAddress,Order", orderby="Order"):
                    if vnic.get("MacAddress"):
                        ports[vnic["Name"]] = _mac(vnic["MacAddress"])
            if not ports and serials.get(name):
                servers = query(client, base, "compute/PhysicalSummaries", filter=f"Serial eq '{serials[name]}'", select="Moid")
                if servers:
                    for interface in query(client, base, "adapter/HostEthInterfaces",
                                           filter=f"Ancestors/any(t:t/Moid eq '{servers[0]['Moid']}')",
                                           select="Name,MacAddress"):
                        if interface.get("MacAddress"):
                            ports[interface["Name"]] = _mac(interface["MacAddress"])
        except (RuntimeError, requests.RequestException) as error:
            failures += 1
            print(f"{name:<28} failed: {error}", flush=True)
            continue
        if not ports:
            print(f"{name:<28} no profile vNICs or VIC interfaces found", flush=True)
            continue
        result[name] = ports
        print(f"{name:<28} {len(ports)} interfaces", flush=True)
        for port, mac in ports.items():
            print(f"    {port:<24} {mac}", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    previous = {}
    if args.output.is_file():
        previous = json.loads(args.output.read_text(encoding="utf-8")).get("hosts", {})
    previous.update(result)
    args.output.write_text(json.dumps({"source": "intersight", "collected": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                       "hosts": previous}, indent=2), encoding="utf-8")
    print(f"\nSaved MAC addresses for {len(result)} hosts to {args.output}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
