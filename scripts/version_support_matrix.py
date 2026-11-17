#!/usr/bin/env python3
"""Supported OpenShift and Cilium (Isovalent Enterprise) versions for Cisco AI PODs.

``VERSION_SUPPORT`` is the maintained policy: which minor releases this stack supports and which patch release is
recommended. The install prep and the Cluster Deployment page only accept versions inside it.

Live lists come from:

* OpenShift - the latest stable release of each channel, with its support phase. Releases come from
  ``iserver get openshift ai version`` (the versions the Red Hat Assisted Installer accepts; needs the Console
  Registration token) or, without it, Red Hat's public update graph. Support phases and dates come from Red Hat's public
  product life cycle API. Neither public source needs a login.
* Cilium - a Helm repository index. Set ``--index-url`` (or ``CILIUM_VERSION_INDEX_URL``) to the index of the registry
  you use; the identity token is sent as a bearer token (``--token`` or ``isovalent_registry_token``). Without a URL,
  Isovalent's public index is used, which only lists releases up to 1.18.

Usage:
    python version_support_matrix.py channels [--json] [--offline]
    python version_support_matrix.py list openshift|cilium [--json] [--offline]
    python version_support_matrix.py validate openshift|cilium VERSION
    python version_support_matrix.py check [--json]

``check`` exits 1 when the policy needs review: a supported OpenShift channel reached end of life, a Cilium release newer
than the recommended one exists in your registry index, or the recommended Cilium version is no longer offered. It
also notes OpenShift channels that are generally available but not in the matrix. It can run from cron or CI.

To change the policy, edit ``VERSION_SUPPORT`` below.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Optional

import yaml

# Maintained policy. supported_minors: releases this stack supports. recommended (Cilium): the patch release to use;
# OpenShift always recommends the latest stable release of a supported channel. tested: patch releases to offer when no
# live list is reachable.
VERSION_SUPPORT = {
    "openshift": {
        "supported_minors": ["4.20"],
        "tested": ["4.20.16"],
    },
    "cilium": {
        "supported_minors": ["1.19"],
        "recommended": "1.19.7",
        "tested": ["1.19.7"],
    },
}

# iserver's default: install the latest production release the Assisted Installer offers.
LATEST_PRODUCTION = "the-latest-production-version"
LIFECYCLE_URL = "https://access.redhat.com/product-life-cycles/api/v2/products?name=Red+Hat+OpenShift+Container+Platform"
ACTIVE_SUPPORT = ("Full Support", "Maintenance Support")
CINCINNATI_URL = "https://api.openshift.com/api/upgrades_info/v1/graph"
PUBLIC_CILIUM_INDEX = "https://helm.isovalent.com/index.yaml"
CILIUM_CHART = "cilium"
VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
TIMEOUT = 20


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def minor_of(version: str) -> str:
    return ".".join(version.split(".")[:2])


def recommended(kind: str) -> str:
    """The recommended Cilium patch release; for OpenShift the newest tested one (used when nothing live is reachable)."""
    spec = VERSION_SUPPORT[kind]
    return spec.get("recommended") or spec["tested"][-1]


def recommendation(kind: str) -> str:
    minors = VERSION_SUPPORT[kind]["supported_minors"]
    if kind == "openshift":
        return f"the latest stable release of {', '.join(minors)}.x"
    return f"recommended {recommended(kind)}"


def is_supported(kind: str, version: str) -> tuple[bool, str]:
    """Whether ``version`` is inside the supported matrix, with the reason when it is not."""
    if kind not in VERSION_SUPPORT:
        return False, f"Unknown product '{kind}'"
    if not VERSION.match(str(version)):
        return False, f"'{version}' is not a version like {recommended(kind)}"
    minors = VERSION_SUPPORT[kind]["supported_minors"]
    if minor_of(version) not in minors:
        return False, (f"{kind} {version} is not supported; supported releases are {', '.join(minors)}.x "
                       f"({recommendation(kind)})")
    return True, ""


def latest_production() -> Optional[str]:
    """The release iserver installs for ``LATEST_PRODUCTION``; None when it cannot be looked up."""
    items = openshift_from_iserver(("production",))
    if not items:
        return None
    pool = [item for item in items if item["default"]] or items
    return max((item["version"] for item in pool), key=version_key)


def check_version(kind: str, version: str) -> tuple[bool, str]:
    """``is_supported`` plus the floating OpenShift default, which is checked against what it resolves to now."""
    if kind == "openshift" and version == LATEST_PRODUCTION:
        minors = ", ".join(f"{minor}.x" for minor in VERSION_SUPPORT["openshift"]["supported_minors"])
        resolved = latest_production()
        if resolved is None:
            return True, (f"{LATEST_PRODUCTION}: cannot look up the current release (iserver console login "
                          f"unavailable); supported releases are {minors}")
        ok, reason = is_supported("openshift", resolved)
        if ok:
            return True, f"{LATEST_PRODUCTION} resolves to {resolved}: supported"
        return False, (f"{LATEST_PRODUCTION} resolves to {resolved}, which Cisco AI PODs does not support yet; pin a "
                       f"supported release ({minors}) in cluster_version")
    return is_supported(kind, version)


def _json_value(text: str):
    """First JSON document in ``text`` (iserver prints status lines after its output)."""
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char in "[{":
            try:
                return decoder.raw_decode(text[index:])[0]
            except ValueError:
                continue
    return None


def openshift_from_iserver(levels: tuple[str, ...] = ("production", "maintenance")) -> Optional[list[dict]]:
    """Versions the Assisted Installer accepts, via iserver; None when iserver or its console login is unavailable."""
    executable = shutil.which("iserver")
    if not executable:
        return None
    found: dict[str, dict] = {}
    for level in levels:
        try:
            result = subprocess.run([executable, "get", "openshift", "ai", "version", "--type", level, "-o", "json"],
                                    capture_output=True, text=True, timeout=60, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
        data = _json_value(result.stdout)
        if result.returncode != 0 or data is None:
            return None
        entries = data.values() if isinstance(data, dict) else data
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("display_name") or entry.get("version") or "")
            if VERSION.match(name):
                found[name] = {"version": name, "support_level": entry.get("support_level", level),
                               "default": bool(entry.get("default"))}
    return list(found.values()) or None


def _get(url: str, headers: Optional[dict] = None) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "cisco-ai-pods", **(headers or {})})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 - https URLs only
        return response.read()


def openshift_from_public(minors: list[str]) -> list[dict]:
    """Release versions of the stable channels from Red Hat's public update graph."""
    found: dict[str, dict] = {}
    for minor in minors:
        url = f"{CINCINNATI_URL}?channel=stable-{minor}&arch=amd64"
        data = json.loads(_get(url, {"Accept": "application/json"}))
        for node in data.get("nodes", []):
            name = str(node.get("version", ""))
            if VERSION.match(name) and minor_of(name) == minor:
                found[name] = {"version": name, "support_level": "production", "default": False}
    return list(found.values())


def _date(text: str) -> Optional[datetime.date]:
    try:
        return datetime.datetime.strptime(str(text)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def lifecycle(today: Optional[datetime.date] = None) -> dict[str, dict]:
    """Support phase of each OpenShift minor from Red Hat's public product life cycle API (no login needed)."""
    today = today or datetime.date.today()
    products = json.loads(_get(LIFECYCLE_URL, {"Accept": "application/json"})).get("data") or []
    cycle = {}
    for item in (products[0].get("versions") or []) if products else []:
        name = str(item.get("name", ""))
        if not re.match(r"^\d+\.\d+$", name):
            continue
        current = None
        for phase in item.get("phases") or []:
            start, end = _date(phase.get("start_date", "")), _date(phase.get("end_date", ""))
            if end and today <= end and (start is None or start <= today):
                current = (phase.get("name", ""), end)
        cycle[name] = {"support": item.get("type", ""), "phase": current[0] if current else "",
                       "until": current[1].isoformat() if current else ""}
    return cycle


def openshift_channels(offline: bool = False, today: Optional[datetime.date] = None) -> tuple[list[dict], str]:
    """Latest stable release of each active OpenShift channel, newest channel first, and where the data came from.

    Channels are those in Full or Maintenance support plus the ones this stack supports. The release is the newest one
    iserver (the Assisted Installer) offers for the channel, else the public update graph, else the tested versions."""
    supported = VERSION_SUPPORT["openshift"]["supported_minors"]
    cycle: dict[str, dict] = {}
    if not offline:
        try:
            cycle = lifecycle(today)
        except (OSError, ValueError, IndexError, urllib.error.URLError):
            cycle = {}
    minors = {minor for minor, info in cycle.items() if info["support"] in ACTIVE_SUPPORT} | set(supported)
    from_iserver = None if offline else openshift_from_iserver(("production", "maintenance"))
    rows, sources = [], set()
    for minor in sorted(minors, key=lambda value: version_key(value + ".0"), reverse=True):
        latest, via = "", ""
        if from_iserver:
            found = [item["version"] for item in from_iserver if minor_of(item["version"]) == minor]
            if found:
                latest, via = max(found, key=version_key), "iserver (Assisted Installer)"
        if not latest and not offline:
            try:
                found = [item["version"] for item in openshift_from_public([minor])]
                if found:
                    latest, via = max(found, key=version_key), "Red Hat update graph"
            except (OSError, ValueError, urllib.error.URLError):
                pass
        if not latest and minor in supported:
            found = [v for v in VERSION_SUPPORT["openshift"]["tested"] if minor_of(v) == minor]
            if found:
                latest, via = max(found, key=version_key), "matrix (tested versions)"
        if not latest:
            continue
        info = cycle.get(minor, {})
        sources.add(via)
        rows.append({"channel": f"stable-{minor}", "minor": minor, "latest": latest, "support": info.get("support", ""),
                     "phase": info.get("phase", ""), "until": info.get("until", ""), "supported": minor in supported})
    note = "; support phases from Red Hat's life cycle API" if cycle else ""
    return rows, ("; ".join(sorted(sources)) or "matrix (tested versions)") + note


def openshift_versions(offline: bool = False) -> tuple[list[dict], str]:
    """Supported OpenShift versions, newest first, and where they came from."""
    minors = VERSION_SUPPORT["openshift"]["supported_minors"]
    items, source = None, ""
    if not offline:
        items, source = openshift_from_iserver(), "iserver (Assisted Installer)"
        if items is None:
            try:
                items, source = openshift_from_public(minors), "Red Hat update graph (stable channels)"
            except (OSError, ValueError, urllib.error.URLError):
                items = None
    if not items:
        items = [{"version": v, "support_level": "tested", "default": False}
                 for v in VERSION_SUPPORT["openshift"]["tested"]]
        source = "matrix (tested versions)"
    items = [item for item in items if is_supported("openshift", item["version"])[0]]
    return sorted(items, key=lambda item: version_key(item["version"]), reverse=True), source


def cilium_from_index(index_url: str, token: str = "") -> list[str]:
    """Stable release versions of the Cilium chart in a Helm repository index."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    index = yaml.safe_load(_get(index_url, headers)) or {}
    entries = (index.get("entries") or {}).get(CILIUM_CHART) or []
    return sorted({str(entry["version"]) for entry in entries if VERSION.match(str(entry.get("version", "")))},
                  key=version_key)


def cilium_versions(index_url: str = "", token: str = "", offline: bool = False) -> tuple[list[str], str]:
    """Supported Cilium versions, newest first, and where they came from."""
    index_url = index_url or os.environ.get("CILIUM_VERSION_INDEX_URL", "")
    token = token or os.environ.get("isovalent_registry_token", "")
    versions, source = [], ""
    if not offline:
        url = index_url or PUBLIC_CILIUM_INDEX
        try:
            versions = cilium_from_index(url, token if index_url else "")
            source = "registry index" if index_url else "Isovalent public index (releases up to 1.18)"
        except (OSError, ValueError, yaml.YAMLError, urllib.error.URLError):
            versions = []
    versions = [v for v in versions if is_supported("cilium", v)[0]]
    if not versions:
        versions, source = list(VERSION_SUPPORT["cilium"]["tested"]), "matrix (tested versions)"
    return sorted(versions, key=version_key, reverse=True), source


def check(index_url: str = "", token: str = "") -> dict:
    """Policy drift: what in the matrix needs a maintainer's review."""
    report = {"problems": [], "notes": []}
    supported = VERSION_SUPPORT["openshift"]["supported_minors"]
    try:
        cycle = lifecycle()
    except (OSError, ValueError, IndexError, urllib.error.URLError):
        cycle = {}
    if not cycle:
        report["notes"].append("openshift: the Red Hat life cycle API is not reachable; nothing to compare")
    for minor in supported:
        if cycle.get(minor, {}).get("support") == "End of life":
            report["problems"].append(f"openshift: {minor} has reached end of life; update supported_minors")
    newest = max((version_key(minor + ".0") for minor in supported), default=())
    for minor, info in cycle.items():
        if info["support"] in ACTIVE_SUPPORT and version_key(minor + ".0") > newest:
            report["notes"].append(f"openshift: {minor} is in {info['support']} but not in the matrix "
                                   f"(until {info['until'] or 'unknown'})")
    channels, source = openshift_channels()
    report["openshift"] = {"source": source, "supported_minors": supported,
                           "channels": {row["minor"]: row["latest"] for row in channels}}

    versions, source = cilium_versions(index_url, token)
    wanted = recommended("cilium")
    report["cilium"] = {"source": source, "recommended": wanted, "versions": versions}
    if source.startswith("matrix"):
        report["notes"].append("cilium: no live list with a supported release; nothing to compare")
    elif source.startswith("Isovalent public"):
        report["notes"].append("cilium: only the public index (up to 1.18) is reachable; set --index-url to your "
                               "registry index to check 1.19 and newer")
    else:
        newer = [v for v in versions if minor_of(v) == minor_of(wanted) and version_key(v) > version_key(wanted)]
        if newer:
            report["problems"].append(f"cilium: {newer[0]} is available in {minor_of(wanted)}.x (recommended is "
                                      f"{wanted}); review the matrix")
        if wanted not in versions:
            report["problems"].append(f"cilium: recommended {wanted} is not offered by {source}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("channels", "list", "validate", "check"):
        sub = commands.add_parser(name)
        if name in ("list", "validate"):
            sub.add_argument("kind", choices=sorted(VERSION_SUPPORT))
        if name == "validate":
            sub.add_argument("version")
        if name != "validate":
            sub.add_argument("--json", action="store_true")
        if name in ("channels", "list"):
            sub.add_argument("--offline", action="store_true", help="use the matrix only")
        if name in ("list", "check"):
            sub.add_argument("--index-url", default="", help="Helm index URL of the Cilium registry")
            sub.add_argument("--token", default="", help="identity token for the index (default: isovalent_registry_token)")
    args = parser.parse_args()

    if args.command == "validate":
        ok, message = check_version(args.kind, args.version)
        print(message or f"{args.kind} {args.version}: supported")
        return 0 if ok else 1

    if args.command == "channels":
        rows, source = openshift_channels(args.offline)
        if args.json:
            print(json.dumps({"source": source, "channels": rows}, indent=2))
        else:
            print(f"Source: {source}")
            print(f"{'CHANNEL':<14}{'LATEST':<10}{'SUPPORT':<22}{'UNTIL':<12}CISCO AI PODS")
            for row in rows:
                print(f"{row['channel']:<14}{row['latest']:<10}{row['support']:<22}{row['until']:<12}"
                      f"{'supported' if row['supported'] else '-'}")
        return 0

    if args.command == "list":
        if args.kind == "openshift":
            items, source = openshift_versions(args.offline)
            versions = [item["version"] for item in items]
        else:
            versions, source = cilium_versions(args.index_url, args.token, args.offline)
        if args.json:
            print(json.dumps({"source": source, "recommended": recommended(args.kind), "versions": versions}))
        else:
            print(f"Source: {source}")
            for version in versions:
                print(f"{version}{'  (recommended)' if version == recommended(args.kind) else ''}")
        return 0

    report = check(args.index_url, args.token)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        info = report["openshift"]
        print(f"openshift: supported {', '.join(info['supported_minors'])}; latest "
              + ", ".join(f"{minor}: {latest}" for minor, latest in info["channels"].items()))
        info = report["cilium"]
        print(f"cilium: recommended {info['recommended']}; {len(info['versions'])} versions from {info['source']}")
        for note in report["notes"]:
            print(f"note: {note}")
        for problem in report["problems"]:
            print(f"DRIFT: {problem}")
    return 1 if report["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
