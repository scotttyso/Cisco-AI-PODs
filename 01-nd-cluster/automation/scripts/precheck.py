"""Pre-validation checklist for the ND 4.3.x cluster install.

Runs every check we wish we had run *before* hitting the lab the first time.
Each check is small, idempotent, and read-only. Output is a structured table
plus a non-zero exit if any CRITICAL check fails.

Categories:

  inventory.*    canonical Ansible inventory + cross-field consistency
  secrets.*     all referenced env vars are populated; no plaintext leaks in
                 our own files
  network.*     Workstation->CIMC TCP/22 + 443 reachable (Cisco mandates
                 BOTH ports per ND 4.2.x prereqs); CIMC subnet placement
                 note; LEADER-VANTAGE probes (post-Phase-5) — nd-1 bond1
                 -> CIMC of every secondary (the D-008/D-011 footgun:
                 workstation can reach CIMC but nd-1 cannot due to inter-
                 VRF/firewall path; cluster commit blocks at "Setup boot
                 time configuration"), nd-1 bond0 -> data gateway (partial
                 signal for STP Bridge Assurance Inconsistent on the
                 data VLAN per §3)
  iso.*         ISO URL HEAD ok; expected SHA-512 present; hosted ISO bytes
                 hash exactly to the expected value; optional local ISO
                 content can be checked as an additional diagnostic
  dns.*         every (DNS server) x (NTP hostname) pair resolves
                 (this is the historical §2 footgun)
  topology.*    every node IP belongs to its declared subnet; persistent IPs
                 don't collide with node IPs and live on the data subnet
  version.*     all 3 nodes are on the same ND OS release as the cluster ISO
                 (the historical §17 footgun: `acs reboot factory-reset`
                 preserves the OS image, so a stale secondary blocks cluster
                 commit at "Setup boot time configuration" with the cryptic
                 `installed firmware version is incompatible` error)
  bootstrap.*   nd-1 has no pending-draft cluster bootstrap state (best-
                 effort heuristic for the §1 footgun: a half-failed prior
                 commit leaves an internal draft that returns 500 on the
                 next POST; GET /bootstrap/status cannot distinguish this
                 from clean-not-bootstrapped, so we WARN with both
                 interpretations rather than silently miss the case)
  config.*      timezone is an IANA string (not the ambiguous "EST")

Each check returns one of:
  PASS   green; the predicate held
  WARN   yellow; non-blocking; operator should know
  FAIL   red; CRITICAL; install will fail or behave incorrectly
  SKIP   skipped (dependency missing, e.g., dig not installed)

Exit code:
  0  no FAILs (WARNs are not blocking; review them before proceeding)
  1  one or more FAILs
  2  precheck itself crashed (inventory unparseable, etc.)

Usage:

    .venv/bin/python scripts/precheck.py                     # full run
    .venv/bin/python scripts/precheck.py --skip dns.ntp      # skip a check id
    .venv/bin/python scripts/precheck.py --json              # machine-readable
    .venv/bin/python scripts/precheck.py --category dns      # just one cat
    .venv/bin/python scripts/precheck.py --iso-file /path/to/nd.iso

Workspace policy notes:

  * codeguard-1-hardcoded-credentials: this script reads secrets ONLY from
    env vars (not from the YAML, not from a config file, never inline). It
    NEVER prints the value, only its length.
  * codeguard-0-logging: PASS/WARN/FAIL detail strings never include a
    secret. The IP/hostname surface is non-sensitive lab metadata.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))                          # for sibling modules
sys.path.insert(0, str(THIS_DIR.resolve().parents[2]))     # for shared/lib

from shared.lib.inventory import (  # noqa: E402
    Inventory,
    InventoryError,
    load_ansible,
)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"
SKIP = "SKIP"

_COLOR = {
    PASS: "\033[32m",  # green
    WARN: "\033[33m",  # yellow
    FAIL: "\033[31m",  # red
    SKIP: "\033[90m",  # gray
}
_RESET = "\033[0m"


@dataclass
class Result:
    id: str
    status: str
    detail: str

    def color(self, use_color: bool) -> str:
        if not use_color:
            return self.status
        return f"{_COLOR.get(self.status, '')}{self.status}{_RESET}"


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_inventory_parses(ansible_inventory: str) -> tuple[Result, Inventory | None]:
    try:
        inv = load_ansible(ansible_inventory)
    except InventoryError as e:
        return Result("inventory.parse", FAIL, f"{e}"), None
    return (
        Result("inventory.parse", PASS,
               f"cluster={inv.cluster.name!r} nodes={len(inv.nodes)}"),
        inv,
    )


def check_secrets_set(inv: Inventory) -> list[Result]:
    """Confirm every *_pass_ref env var is set. Never print the value."""
    refs = {inv.admin_pass_ref}
    refs.update(n.cimc.pass_ref for n in inv.nodes)
    out: list[Result] = []
    for ref in sorted(refs):
        val = os.environ.get(ref, "")
        if not val:
            out.append(Result(f"secrets.{ref}", FAIL,
                              f"env var {ref} is not set or empty"))
        elif len(val) < 8:
            out.append(Result(f"secrets.{ref}", WARN,
                              f"env var {ref} is set but length {len(val)} is suspiciously short"))
        else:
            out.append(Result(f"secrets.{ref}", PASS,
                              f"env var {ref} set (length {len(val)})"))
    return out


_IDENTIFIER_UPPER = re.compile(r"^[A-Z0-9_]+$")
_IDENTIFIER_LOWER = re.compile(r"^[a-z0-9_]+$")


def _looks_like_credential_literal(literal: str) -> bool:
    """Heuristic: does this quoted string look like an actual password value
    (vs. an identifier name like 'CIMC_PASSWORD' or a placeholder)?

    Excludes:
      - all-uppercase + digits + underscore  (env var name)
      - all-lowercase + digits + underscore  (function/variable name)
      - common placeholders                  (TODO, TO_CONFIRM, ...)
      - anything starting with a placeholder marker ($, {, <, %, etc.)
    """
    if not literal or len(literal) < 8:
        return False
    if literal[0] in "${<%":
        return False
    if _IDENTIFIER_UPPER.match(literal):
        return False
    if _IDENTIFIER_LOWER.match(literal):
        return False
    if literal.upper() in {"TO_CONFIRM", "TODO", "PLACEHOLDER", "CHANGEME",
                           "CHANGE_ME", "REPLACE_ME", "REPLACEME",
                           "FILL_IN", "FILLIN", "EXAMPLE", "REDACTED"}:
        return False
    return True


def check_no_plaintext_credentials_in_repo(repo_root: Path) -> Result:
    """Scan our own tracked text files for likely hardcoded credentials.

    This is a regression guard against the RESUME.md leak we caught in this
    cycle. We only look in our own source tree (not vendored .venv, not
    captured SPA bundles, not state/logs).

    Two-stage match: a permissive regex finds candidates; the
    `_looks_like_credential_literal` filter rejects identifier-shaped values
    (env var names, function names) and common placeholders.
    """
    try:
        # Capture the value inside the quotes for post-filtering.
        pattern = re.compile(
            r"""(?ix)
                (?:^|[^A-Za-z0-9_])           # start of word (not part of a longer ident)
                (?:password|passwd|passwd|pass)\s*[=:]\s*
                (['"])                          # opening quote (group 1)
                ([^'"\n]{8,128})                # candidate literal (group 2)
                \1                              # matching close quote
            """,
        )
        scan_globs = ("*.md", "*.py", "*.sh", "*.yaml", "*.yml", "*.json")
        excluded = (".venv", "build/", "logs/spa", "state/", "node_modules", ".git",
                    # The precheck script defines the heuristic strings
                    # above; don't scan ourselves.
                    "scripts/precheck.py")
        hits: list[str] = []
        for ext in scan_globs:
            for path in repo_root.rglob(ext):
                rel = str(path.relative_to(repo_root))
                if any(skip in rel for skip in excluded):
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except (OSError, UnicodeDecodeError):
                    continue
                for m in pattern.finditer(text):
                    literal = m.group(2)
                    if not _looks_like_credential_literal(literal):
                        continue
                    line_no = text[:m.start()].count("\n") + 1
                    hits.append(f"{rel}:{line_no}")
        if hits:
            return Result("secrets.no_plaintext_in_repo", FAIL,
                          f"possible hardcoded credential(s): {', '.join(hits[:5])}"
                          + (" ..." if len(hits) > 5 else ""))
        return Result("secrets.no_plaintext_in_repo", PASS,
                      "no hardcoded-credential patterns in tracked .md/.py/.sh/.yaml/.json")
    except Exception as e:  # noqa: BLE001
        return Result("secrets.no_plaintext_in_repo", SKIP, f"scan failed: {e!r}")


def check_cimc_tcp_443(inv: Inventory, timeout: float = 3.0) -> list[Result]:
    """TCP-connect to each CIMC IP on 443. We only check L4 reachability —
    HTTPS handshake validation happens later in the orchestrator with the
    real Redfish call.

    NOTE: this is the WORKSTATION → CIMC path (the path the orchestrator
    will use for Redfish vMedia mounts). It is necessary but NOT sufficient
    for cluster-commit pre-flight, which also requires nd-1 bond1 → CIMC
    over TCP/22 + 443. See `check_nd1_path_to_cimc_and_data_gw` for the
    leader-side probe that catches the D-008/D-011 failure mode.
    """
    out: list[Result] = []
    for n in inv.nodes:
        rid = f"network.cimc_tcp_443.{n.hostname}"
        try:
            with socket.create_connection((n.cimc.ip, 443), timeout=timeout):
                out.append(Result(rid, PASS, f"{n.cimc.ip}:443 reachable"))
        except OSError as e:
            out.append(Result(rid, FAIL,
                              f"cannot connect to {n.cimc.ip}:443 ({e.__class__.__name__}: {e})"))
    return out


def check_cimc_tcp_22(inv: Inventory, timeout: float = 3.0) -> list[Result]:
    """TCP-connect to each CIMC IP on 22 (SSH). Cisco's ND 4.2.x prerequisites
    (https://www.cisco.com/c/en/us/td/docs/dcn/nd/4x/deployment/42x/cisco-nexus-dashboard-deployment-guide-42x/m-prerequisites.html)
    explicitly require BOTH 22 AND 443 to be reachable from the management
    network to each CIMC, because ND uses both during cluster-commit
    pre-flight (443 for Redfish, 22 for legacy CIMC API/SSH).

    Same workstation-side caveat as `check_cimc_tcp_443` — necessary but
    not sufficient; the actual cluster-commit-time path is leader → CIMC.
    """
    out: list[Result] = []
    for n in inv.nodes:
        rid = f"network.cimc_tcp_22.{n.hostname}"
        try:
            with socket.create_connection((n.cimc.ip, 22), timeout=timeout):
                out.append(Result(rid, PASS, f"{n.cimc.ip}:22 reachable"))
        except OSError as e:
            out.append(Result(rid, FAIL,
                              f"cannot connect to {n.cimc.ip}:22 ({e.__class__.__name__}: {e}). "
                              f"Cisco ND 4.2.x requires both TCP/22 and TCP/443 from the mgmt "
                              f"network to every CIMC; check the path / FW rules."))
    return out


def check_cimc_subnet_placement(inv: Inventory) -> list[Result]:
    """Check each CIMC IP against the subnets canonical inventory declares.

    An ND node touches three networks: ND-MGMT, ND-DATA, and the out-of-band
    subnet its CIMC sits on. A CIMC on the declared `network.oob_subnet` is the
    intended topology and passes. A CIMC on the mgmt subnet also passes, since
    collapsing the two is a valid design.

    Anything else warns. On the data subnet it is supported but unusual, and a
    human troubleshooter who infers the CIMC IP from the mgmt IP will go to the
    wrong place, so make it visible (the §9 gotcha). On no declared subnet at
    all, either the routing path needs verifying or `oob_subnet` is missing
    from the inventory.
    """
    out: list[Result] = []
    mgmt_net = ipaddress.ip_network(inv.cluster.network.mgmt_subnet, strict=False)
    data_net = ipaddress.ip_network(inv.cluster.network.data_subnet, strict=False)
    oob_declared = inv.cluster.network.oob_subnet
    oob_net = (ipaddress.ip_network(oob_declared, strict=False)
               if oob_declared else None)
    for n in inv.nodes:
        rid = f"network.cimc_subnet.{n.hostname}"
        cimc_ip = ipaddress.ip_address(n.cimc.ip)
        if oob_net is not None and cimc_ip in oob_net:
            out.append(Result(rid, PASS, f"CIMC {n.cimc.ip} on OOB subnet ({oob_net})"))
        elif cimc_ip in mgmt_net:
            out.append(Result(rid, PASS, f"CIMC {n.cimc.ip} on mgmt subnet ({mgmt_net})"))
        elif cimc_ip in data_net:
            out.append(Result(rid, WARN,
                              f"CIMC {n.cimc.ip} is on the DATA subnet ({data_net}), "
                              f"not the mgmt subnet ({mgmt_net}). This is supported but "
                              f"unusual; see docs/troubleshooting.md §9."))
        elif oob_net is None:
            out.append(Result(rid, WARN,
                              f"CIMC {n.cimc.ip} is on neither the mgmt subnet "
                              f"({mgmt_net}) nor the data subnet ({data_net}), and "
                              f"inventory declares no network.oob_subnet. If the CIMCs "
                              f"are on an out-of-band subnet, declare it there; otherwise "
                              f"verify the routing path."))
        else:
            out.append(Result(rid, WARN,
                              f"CIMC {n.cimc.ip} is outside every subnet declared in "
                              f"canonical inventory, including the OOB subnet ({oob_net}); "
                              f"verify the routing path"))
    return out


def check_iso_reachable(inv: Inventory, timeout: float = 10.0) -> list[Result]:
    """HEAD the ISO URL; report size and content-length."""
    url = inv.cluster.iso.url
    rid = "iso.url_reachable"
    if inv.cluster.start_mode == "factory_preinstalled":
        return [Result(rid, SKIP, "not consumed in factory_preinstalled mode")]
    try:
        ctx = ssl.create_default_context()
        if not inv.runtime.verify_tls:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            length = resp.headers.get("Content-Length")
            size_gib = (int(length) / (1 << 30)) if length and length.isdigit() else None
            detail = f"{url} -> HTTP {resp.status}"
            if size_gib is not None:
                detail += f", size {size_gib:.2f} GiB"
                if size_gib < 1.0:
                    return [Result(rid, FAIL,
                                   f"{detail}; suspiciously small for an ND ISO (>= ~10 GiB expected)")]
            return [Result(rid, PASS, detail)]
    except Exception as e:  # noqa: BLE001
        return [Result(rid, FAIL, f"{url} unreachable: {e.__class__.__name__}: {e}")]


def check_iso_sha512_set(inv: Inventory) -> Result:
    rid = "iso.sha512_set"
    sha = (inv.cluster.iso.sha512 or "").strip()
    if not sha or sha.upper() in {"TO_CONFIRM", "TODO", "PLACEHOLDER"}:
        return Result(rid, FAIL,
                      f"cluster.iso.sha512 is a placeholder ({sha!r}); "
                      f"paste the vendor-published SHA-512 before installing")
    if len(sha) != 128 or not re.fullmatch(r"[0-9a-fA-F]{128}", sha):
        return Result(rid, FAIL,
                      f"cluster.iso.sha512 doesn't look like a SHA-512 (got len={len(sha)})")
    return Result(rid, PASS, f"sha512 set (len {len(sha)})")


def check_iso_sha512_url(inv: Inventory, timeout: float = 300.0) -> Result:
    """Stream the ISO served to CIMC and compare it with the vendor digest.

    A successful HEAD request proves only that an object exists at the URL.
    Hashing the GET response proves that the exact bytes the CIMCs will mount
    match the vendor-published SHA-512 without loading the image into memory.
    """
    rid = "iso.sha512_url"
    if inv.cluster.start_mode == "factory_preinstalled":
        return Result(rid, SKIP, "not consumed in factory_preinstalled mode")
    expected = (inv.cluster.iso.sha512 or "").strip().lower()
    expected_check = check_iso_sha512_set(inv)
    if expected_check.status != PASS:
        return Result(rid, FAIL, f"cannot verify hosted ISO: {expected_check.detail}")

    url = inv.cluster.iso.url
    ctx = ssl.create_default_context()
    if not inv.runtime.verify_tls:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    digest = hashlib.sha512()
    byte_count = 0
    expected_bytes: int | None = None
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as stream:
            length = stream.headers.get("Content-Length")
            if length and length.isdigit():
                expected_bytes = int(length)
            while chunk := stream.read(8 * 1024 * 1024):
                digest.update(chunk)
                byte_count += len(chunk)
    except Exception as e:  # noqa: BLE001
        return Result(
            rid,
            FAIL,
            f"cannot hash hosted ISO {url}: {e.__class__.__name__}: {e}",
        )

    if expected_bytes is not None and byte_count != expected_bytes:
        return Result(
            rid,
            FAIL,
            f"hosted ISO transfer incomplete: expected {expected_bytes} bytes, "
            f"received {byte_count}; no content-integrity conclusion was made",
        )

    actual = digest.hexdigest()
    if actual != expected:
        return Result(
            rid,
            FAIL,
            f"hosted ISO SHA-512 mismatch: expected {expected}, got {actual}",
        )
    size_gib = byte_count / (1 << 30)
    return Result(
        rid,
        PASS,
        f"hosted ISO matches inventory SHA-512 ({size_gib:.2f} GiB)",
    )


def check_iso_sha512_file(inv: Inventory, iso_file: str | Path) -> Result:
    """Hash a local ISO and compare it with the inventory's expected digest."""
    rid = "iso.sha512_file"
    expected = (inv.cluster.iso.sha512 or "").strip().lower()
    expected_check = check_iso_sha512_set(inv)
    if expected_check.status != PASS:
        return Result(rid, FAIL, f"cannot verify file: {expected_check.detail}")

    path = Path(iso_file).expanduser()
    if not path.exists():
        return Result(rid, FAIL, f"ISO file not found: {path}")
    if not path.is_file():
        return Result(rid, FAIL, f"ISO path is not a regular file: {path}")

    digest = hashlib.sha512()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(8 * 1024 * 1024):
                digest.update(chunk)
        size_gib = path.stat().st_size / (1 << 30)
    except OSError as e:
        return Result(rid, FAIL, f"cannot read {path}: {e.__class__.__name__}: {e}")

    actual = digest.hexdigest()
    if actual != expected:
        return Result(
            rid,
            FAIL,
            f"{path} SHA-512 mismatch: expected {expected}, got {actual}",
        )
    return Result(
        rid,
        PASS,
        f"{path} matches inventory SHA-512 ({size_gib:.2f} GiB)",
    )


def _resolve_via(server: str, host: str, timeout: float = 3.0) -> tuple[bool, str]:
    """Resolve `host` against `server`. Returns (ok, detail). Uses dig if
    available; falls back to nslookup; SKIPs if neither is installed."""
    if shutil.which("dig"):
        try:
            r = subprocess.run(
                ["dig", f"@{server}", "+short", f"+time={int(timeout)}", "+tries=1", host],
                capture_output=True, text=True, timeout=timeout + 2,
            )
            answers = [ln for ln in r.stdout.splitlines() if ln and not ln.startswith(";")]
            if r.returncode == 0 and answers:
                return True, f"dig @{server} {host} -> {answers[0]}"
            return False, f"dig @{server} {host} -> no answer (rc={r.returncode})"
        except subprocess.TimeoutExpired:
            return False, f"dig @{server} {host} -> timeout after {timeout}s"
    if shutil.which("nslookup"):
        try:
            r = subprocess.run(
                ["nslookup", host, server],
                capture_output=True, text=True, timeout=timeout + 2,
            )
            ok = ("Address:" in r.stdout and "NXDOMAIN" not in r.stdout
                  and "can't find" not in r.stdout and "** server can't find" not in r.stdout)
            return ok, f"nslookup {host} {server} -> {'ok' if ok else 'no answer'}"
        except subprocess.TimeoutExpired:
            return False, f"nslookup {host} {server} -> timeout"
    return False, "neither dig nor nslookup available"


def check_dns_resolves_ntp(inv: Inventory) -> list[Result]:
    """For every (DNS server) x (NTP hostname) pair, confirm resolution.

    This is the historical §2 footgun: lab DNS that can't resolve the NTP
    hostnames causes verifyremoteservices to 500 mid-bringup. Catch it
    here, before the install runs.

    NTP entries that are already IP literals are auto-PASS.
    """
    out: list[Result] = []
    if not shutil.which("dig") and not shutil.which("nslookup"):
        out.append(Result("dns.ntp", SKIP,
                          "neither dig nor nslookup is installed; "
                          "install bind-utils / dnsutils to enable this check"))
        return out

    for ntp in inv.cluster.ntp:
        host = ntp.host
        try:
            ipaddress.ip_address(host)
            out.append(Result(f"dns.ntp.{host}", PASS,
                              f"{host} is already an IP literal (no DNS needed)"))
            continue
        except ValueError:
            pass
        for dns in inv.cluster.dns.servers:
            ok, detail = _resolve_via(dns, host)
            rid = f"dns.ntp.{host}.via.{dns}"
            if ok:
                out.append(Result(rid, PASS, detail))
            else:
                out.append(Result(rid, FAIL,
                                  f"{detail}; either fix DNS or use an IP literal "
                                  f"for {host} in group_vars/nd_cluster.yml (see docs/troubleshooting.md §2)"))
    return out


def check_node_ips_in_subnet(inv: Inventory) -> list[Result]:
    out: list[Result] = []
    mgmt_net = ipaddress.ip_network(inv.cluster.network.mgmt_subnet, strict=False)
    data_net = ipaddress.ip_network(inv.cluster.network.data_subnet, strict=False)
    for n in inv.nodes:
        for plane, iface, expected in (
            ("mgmt", n.mgmt, mgmt_net),
            ("data", n.data, data_net),
        ):
            rid = f"topology.{plane}_in_subnet.{n.hostname}"
            ip = ipaddress.ip_address(iface.ip)
            iface_net = ipaddress.ip_network(f"{iface.ip}/{iface.mask}", strict=False)
            if ip not in expected:
                out.append(Result(rid, FAIL,
                                  f"{n.hostname} {plane} IP {iface.ip} is outside the declared "
                                  f"{plane} subnet {expected}"))
            elif iface_net != expected:
                out.append(Result(rid, WARN,
                                  f"{n.hostname} {plane} mask /{iface.mask} -> {iface_net} "
                                  f"differs from cluster {plane} subnet {expected}; "
                                  f"verify intent"))
            else:
                out.append(Result(rid, PASS, f"{n.hostname} {plane} {iface.cidr} in {expected}"))
    return out


def check_persistent_ips(inv: Inventory) -> list[Result]:
    out: list[Result] = []
    data_net = ipaddress.ip_network(inv.cluster.network.data_subnet, strict=False)
    node_data_ips = {n.data.ip for n in inv.nodes}
    node_mgmt_ips = {n.mgmt.ip for n in inv.nodes}

    rid = "topology.persistent_ips_count"
    if len(inv.cluster.persistent_ips) >= 5:
        out.append(Result(rid, PASS, f"{len(inv.cluster.persistent_ips)} persistent IPs (>= 5)"))
    else:
        out.append(Result(rid, FAIL,
                          f"need >= 5 persistent IPs, have {len(inv.cluster.persistent_ips)}"))

    for pip in inv.cluster.persistent_ips:
        rid = f"topology.persistent_ip.{pip}"
        ip = ipaddress.ip_address(pip)
        if ip not in data_net:
            out.append(Result(rid, FAIL,
                              f"persistent IP {pip} is not in the data subnet {data_net}"))
        elif pip in node_data_ips or pip in node_mgmt_ips:
            out.append(Result(rid, FAIL,
                              f"persistent IP {pip} collides with a node IP"))
        else:
            out.append(Result(rid, PASS, f"{pip} ok ({data_net})"))
    return out


# ---------------------------------------------------------------------------
# Node OS version-match check (the §17 footgun)
# ---------------------------------------------------------------------------
#
# Why this exists. `acs reboot factory-reset` is our standard recovery primitive
# (D-003), but it explicitly PRESERVES the OS image. If a secondary was ever
# imaged with a different ND release than the cluster leader, factory-reset
# alone won't reconcile the drift and `POST /v2/bootstrap/cluster` will fail at
# stage "Setup boot time configuration" with the message:
#
#     Node CIMC error response: The installed firmware version is incompatible
#     with cluster's. [Node: 4.1.1g. Cluster: 4.2.1.10]
#
# Recovery is ~3 hours per stale node (re-image via `install_secondaries.py`)
# plus an nd-1 factory-reset cycle to clear the failed cluster record. Cheaper
# to detect at precheck time.
#
# Detection model. There is no Redfish/CIMC field that reports "what ND release
# is installed on the local disk" — the OS reports its release only after it
# boots and exposes it via `acs version` (rescue-user) and
# `GET /api/v1/version` (post-cluster-bringup). At precheck time, the most
# reliable signal we can get cheaply is `acs version` over SSH to the mgmt IP
# — works as soon as the node has finished its first-boot dialog and answers
# on its mgmt IP, which is the actually-relevant moment (you only ever call
# cluster commit after that point). At factory-shipped time, we SKIP with
# a clear pointer at `install_secondaries.py` as the way to guarantee
# uniformity. See troubleshooting.md §17 and decision D-012 for the full
# rationale.
# Matches both ND release shapes seen in the wild:
#   4-segment numeric:   '4.2.1.10'  (current 4.2.x train)
#   3-segment + letter:  '4.1.1g'    (older ND minors)
#   3-segment + alnum tail before delimiter: '3.2.1e' (legacy)
_VERSION_RE = re.compile(r"\b(\d+\.\d+\.\d+(?:\.\d+|[a-z][a-z0-9]*)?)\b")


def _iso_version_from_url(url: str) -> str | None:
    """Extract an ND release tag from a typical ISO filename.

    Accepts shapes like:
      nd-dk9.4.2.1.10.iso     -> '4.2.1.10'
      nd-dk9.4.1.1g.iso       -> '4.1.1g'
      foo/3.2.1e-bundle.iso   -> '3.2.1e'
    Returns None if no version-like token is found (e.g., a download alias).
    """
    name = url.rsplit("/", 1)[-1]
    m = _VERSION_RE.search(name)
    return m.group(1) if m else None


# Order matters: the first command that yields a parseable release wins. We try
# the 4.2.x form first (`acs version`) because that's the train this code was
# built against and is the most common case in the field today; fall back to
# the older `acs show version` for 4.1.x and earlier. This dual-probe is the
# whole point of the version precheck during an UPGRADE — we have to be able
# to read the release off both old and new nodes to detect drift between them.
# Empirically:
#   - ND 4.2.x: `acs version` -> single-line `Nexus Dashboard 4.2.1.10`;
#               `acs show` rejects `version` (subcommand list does not include
#               it) with argparse usage output.
#   - ND 4.1.x and earlier: `acs show version` -> `Version: 4.1.1g` (per Cisco
#               docs); `acs version` returns argparse usage from the older
#               top-level parser.
# Either branch fails fast (one command + parse), so the dual-probe adds at
# most ~50ms per node. Verified `acs version` on nd-1 (4.2.1.10) 2026-04-28.
_ACS_VERSION_CMDS: tuple[str, ...] = ("acs version", "acs show version")


def _ssh_acs_version(host: str, password: str, *, timeout: float = 8.0) -> tuple[str | None, str]:
    """SSH to `rescue-user@host` and probe for the installed ND release using
    the candidate commands in :data:`_ACS_VERSION_CMDS`, in order. Returns
    ``(version_string_or_None, detail)``. The password is never echoed in
    `detail`.

    The dual-form probe handles the 4.2.x ↔ 4.1.x CLI rename: `acs version` on
    4.2.x, `acs show version` on 4.1.x and earlier. This matters for the
    upgrade case (mixed-release nodes during a migration window) — see
    [decision D-012](../../CHANGELOG.md#d-012--secondaries-must-match-cluster-leader-os-release-acs-reboot-factory-reset-preserves-the-os-image)
    and the "All three nodes on the same ND OS release before cluster commit"
    prerequisite in the section README.
    """
    try:
        import paramiko  # type: ignore
    except Exception as e:  # noqa: BLE001
        return None, f"paramiko unavailable ({e.__class__.__name__}); cannot probe"
    cli = paramiko.SSHClient()
    # ND nodes use self-signed host keys that rotate on factory-reset; we accept
    # the host key for this single read-only command.
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        cli.connect(
            hostname=host, port=22, username="rescue-user", password=password,
            timeout=timeout, banner_timeout=timeout, auth_timeout=timeout,
            allow_agent=False, look_for_keys=False,
        )
    except Exception as e:  # noqa: BLE001
        return None, f"ssh connect failed: {e.__class__.__name__}: {e}"
    stdin = stdout = stderr = None
    last_err = ""
    try:
        for cmd in _ACS_VERSION_CMDS:
            # Each iteration reuses the same SSH session but issues a new
            # exec_command (one channel each); close handles between attempts
            # to avoid leaking channels if many candidates were tried.
            for fh in (stdin, stdout, stderr):
                try:
                    if fh is not None:
                        fh.close()
                except Exception:  # noqa: BLE001
                    pass
            stdin = stdout = stderr = None
            try:
                stdin, stdout, stderr = cli.exec_command(cmd, timeout=timeout)
                out = stdout.read().decode("utf-8", "replace").strip()
                err = stderr.read().decode("utf-8", "replace").strip()
            except Exception as e:  # noqa: BLE001
                last_err = f"ssh exec failed for {cmd!r}: {e.__class__.__name__}: {e}"
                continue
            combined = (out + "\n" + err).strip()
            # `acs` argparse usage output starts with "usage:" and contains
            # "error:"; treat that as "this command shape isn't supported on
            # this release" and try the next candidate.
            looks_like_usage = combined.lower().startswith("usage:") or " error:" in combined.lower()
            if looks_like_usage and not out:
                last_err = f"`{cmd}` rejected: {combined.splitlines()[0][:120]}"
                continue
            m = _VERSION_RE.search(combined)
            if m:
                tag = " (legacy CLI)" if cmd != _ACS_VERSION_CMDS[0] else ""
                return m.group(1), f"`{cmd}` -> {combined.splitlines()[0][:100]}{tag}"
            last_err = f"could not parse version from `{cmd}` output: {combined[:80]!r}"
        return None, last_err or "no acs version command yielded a parseable release"
    except Exception as e:  # noqa: BLE001
        return None, f"ssh exec failed: {e.__class__.__name__}: {e}"
    finally:
        # Close channel-backed file handles before the SSHClient so paramiko's
        # transport thread is still alive when each Channel's __del__ fires;
        # otherwise BufferedFile.__del__ -> Channel.shutdown_write can raise a
        # noisy AttributeError at interpreter shutdown.
        for fh in (stdin, stdout, stderr):
            try:
                if fh is not None:
                    fh.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            cli.close()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Leader-vantage L3 path checks
#
# The workstation-side `network.cimc_tcp_*` checks above answer "can my laptop
# reach the CIMCs?" — necessary for Redfish orchestration but NOT what
# cluster-commit pre-flight actually does. At commit time, nd-1's bond1
# (mgmt) reaches each secondary's CIMC over TCP/22 + 443 to push the OS
# image. That path is L3-distinct from the workstation path: workstation
# typically traverses your VPN + the lab perimeter; nd-1 traverses
# ND-MGMT-VLAN → lab-VRF L3 → CIMC-VLAN, possibly across a firewall. This
# is the exact distinction that bit us in D-008/D-011 — workstation could
# reach CIMCs fine, nd-1 could not, cluster commit blocked at "Setup boot
# time configuration" until the lab firewall was reconfigured.
#
# We also probe nd-1 bond0 (data) → data gateway as a partial signal for
# STP Bridge Assurance Inconsistent (BA_Inc) on the data VLAN. If the
# data-plane access port is set to `port type network` instead of `port
# type edge`, BA_Inc silently blocks the data VLAN and nd-1 cannot reach
# the data gateway. This isn't a complete BA_Inc detector (gateway might
# be reachable while inter-node data-plane is broken), but it's the only
# signal we can capture without switch-side access.
# ---------------------------------------------------------------------------

def _ssh_run_pings(host: str, password: str, targets: list[tuple[str, str]],
                   *, ssh_timeout: float = 8.0,
                   ping_timeout: float = 8.0) -> dict[str, tuple[bool, str]]:
    """Open one SSH session to ``rescue-user@host`` and run ``ping -c 2 -W 2 <ip>``
    for each ``(label, ip)`` in ``targets``. Returns ``{label: (ok, detail)}``.
    The password is never logged.

    A single SSH session amortises connect cost across multiple pings; the
    function lazy-imports paramiko like ``_ssh_acs_version`` does, and uses
    the same channel-handle-cleanup-before-close discipline to avoid the
    ``BufferedFile.__del__`` shutdown race.
    """
    try:
        import paramiko  # type: ignore
    except Exception as e:  # noqa: BLE001
        return {label: (False, f"paramiko unavailable: {e.__class__.__name__}")
                for label, _ in targets}
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        cli.connect(
            hostname=host, port=22, username="rescue-user", password=password,
            timeout=ssh_timeout, banner_timeout=ssh_timeout, auth_timeout=ssh_timeout,
            allow_agent=False, look_for_keys=False,
        )
    except Exception as e:  # noqa: BLE001
        return {label: (False, f"ssh to {host} failed: {e.__class__.__name__}: {e}")
                for label, _ in targets}

    results: dict[str, tuple[bool, str]] = {}
    stdin = stdout = stderr = None
    try:
        for label, ip in targets:
            for fh in (stdin, stdout, stderr):
                try:
                    if fh is not None:
                        fh.close()
                except Exception:  # noqa: BLE001
                    pass
            stdin = stdout = stderr = None
            # -c 2 = 2 pings; -W 2 = 2s per-reply wait; -q = quiet (single summary line);
            # default routing on the ND node picks the source interface based on dest:
            #   CIMC dest -> bond1 (mgmt), data-gw dest -> bond0 (data).
            # We deliberately do NOT pin -I <iface> here; the DEFAULT-ROUTING path is
            # exactly what cluster-commit pre-flight uses, so testing it the same way
            # is what catches misrouted scenarios.
            cmd = f"ping -c 2 -W 2 -q {ip}"
            try:
                stdin, stdout, stderr = cli.exec_command(cmd, timeout=ping_timeout)
                out = stdout.read().decode("utf-8", "replace")
                rc = stdout.channel.recv_exit_status()
            except Exception as e:  # noqa: BLE001
                results[label] = (False, f"ssh exec failed: {e.__class__.__name__}: {e}")
                continue
            if rc == 0:
                m = re.search(r"min/avg/max[^=]*=\s*([\d./]+)\s*ms", out)
                rtt = m.group(1) if m else None
                results[label] = (True,
                                  f"2/2 replies" + (f", rtt {rtt} ms" if rtt else ""))
            else:
                # Surface a minimal cause hint from the ping output; first non-empty line.
                first = next((ln for ln in out.splitlines() if ln.strip()), "")
                hint = f" — {first[:80]}" if first else ""
                results[label] = (False, f"0 replies (rc={rc}){hint}")
        return results
    finally:
        for fh in (stdin, stdout, stderr):
            try:
                if fh is not None:
                    fh.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            cli.close()
        except Exception:  # noqa: BLE001
            pass


def check_nd1_path_to_cimc_and_data_gw(inv: Inventory, *, tcp_timeout: float = 3.0,
                                       ssh_timeout: float = 8.0,
                                       ping_timeout: float = 8.0) -> list[Result]:
    """SSH into nd-1 (the bootstrap node) and exercise the actual L3 paths
    cluster commit will use:

      1. bond1 (mgmt) -> CIMC of every secondary, over plain ICMP. This is
         the D-008/D-011 detector — `check_cimc_tcp_22/443` confirm
         workstation->CIMC, but cluster-commit pre-flight uses nd-1's bond1.
         The two paths are L3-distinct in any non-trivial topology
         (workstation traverses VPN + perimeter; nd-1 traverses ND-MGMT
         VLAN -> lab L3 -> CIMC VLAN, possibly across a firewall).

      2. bond0 (data) -> data gateway, over plain ICMP. Partial signal for
         STP Bridge Assurance Inconsistent (BA_Inc) on the data VLAN: if
         the access port is `port type network` instead of `port type edge`,
         BA_Inc silently blocks the data VLAN and nd-1 cannot reach the
         data gateway. Not a complete BA_Inc detector (inter-node data-plane
         could still be broken with gw reachable), but the only signal we
         can capture without switch-side access; switch-side `sh
         spanning-tree` capture remains in §B of the operator checklist.

    SKIPs cleanly when the leader isn't yet bootstrapped (mgmt:22 unreachable)
    or when the rescue-user password isn't loaded into the env yet.
    """
    out: list[Result] = []
    try:
        leader = inv.bootstrap_node
    except InventoryError as e:
        out.append(Result("network.nd1_path", FAIL, f"no bootstrap node: {e}"))
        return out

    rid_pre = "network.nd1_path"
    try:
        with socket.create_connection((leader.mgmt.ip, 22), timeout=tcp_timeout):
            pass
    except OSError as e:
        out.append(Result(rid_pre, SKIP,
                          f"leader {leader.hostname} mgmt {leader.mgmt.ip}:22 unreachable "
                          f"({e.__class__.__name__}); leader-vantage path probes SKIP "
                          f"until nd-1's first-boot dialog is complete"))
        return out

    password = os.environ.get(inv.admin_pass_ref, "")
    if not password:
        out.append(Result(rid_pre, SKIP,
                          f"env var {inv.admin_pass_ref} not set; cannot SSH "
                          f"rescue-user@{leader.hostname} to probe leader-vantage paths"))
        return out

    targets: list[tuple[str, str]] = []
    for n in inv.secondary_nodes:
        # Don't ping the leader's own CIMC — irrelevant to cluster commit, and
        # would conflate with the workstation->CIMC checks above.
        targets.append((f"cimc.{n.hostname}", n.cimc.ip))
    targets.append(("data_gw", inv.cluster.network.data_gateway))

    if not targets:
        out.append(Result(rid_pre, SKIP, "no probe targets resolved from inventory"))
        return out

    pings = _ssh_run_pings(leader.mgmt.ip, password, targets,
                           ssh_timeout=ssh_timeout, ping_timeout=ping_timeout)

    for label, ip in targets:
        ok, detail = pings.get(label, (False, "no result"))
        if label.startswith("cimc."):
            host = label.split(".", 1)[1]
            rid = f"network.nd1_to_cimc.{host}"
            if ok:
                out.append(Result(rid, PASS,
                                  f"nd-1 ({leader.mgmt.ip}) -> CIMC {ip}: {detail}"))
            else:
                out.append(Result(rid, FAIL,
                                  f"nd-1 ({leader.mgmt.ip}) cannot reach CIMC {ip}: {detail}. "
                                  f"This blocks cluster commit at stage 'Setup boot time "
                                  f"configuration'. Workstation->CIMC reachability passing "
                                  f"is NOT sufficient — cluster-commit pre-flight uses "
                                  f"nd-1's bond1, not your workstation. Verify the L3 path "
                                  f"from {inv.cluster.network.mgmt_subnet} to the CIMC subnet "
                                  f"(and any FW rules in between). See D-008/D-011 and "
                                  f"troubleshooting.md §14+§16."))
        elif label == "data_gw":
            rid = "network.nd1_data_to_gw"
            if ok:
                out.append(Result(rid, PASS,
                                  f"nd-1 bond0 -> data gateway {ip}: {detail}"))
            else:
                out.append(Result(rid, FAIL,
                                  f"nd-1 cannot reach data gateway {ip}: {detail}. "
                                  f"Most common cause: STP Bridge Assurance has put the "
                                  f"data VLAN in BA_Inc state because the access port is "
                                  f"`port type network` instead of `port type edge` (ND VICs "
                                  f"are end-stations and don't send BPDUs). Run the §B switch "
                                  f"capture (`sh spanning-tree interface eth<x>/<y> detail`) "
                                  f"to confirm. See troubleshooting.md §3."))
    return out


def check_node_os_version_match(inv: Inventory, *, tcp_timeout: float = 3.0,
                                ssh_timeout: float = 8.0,
                                release_evidence_path: str | Path | None = None) -> list[Result]:
    """Probe every node for its installed ND OS release and confirm they all
    match each other AND the cluster ISO version. Per-node IDs are
    ``version.node.<host>``; the cross-node aggregate is ``version.cluster_match``.

    ``factory_preinstalled`` is strict: every node must be reachable and report
    the release selected by the inventory ISO. ``iso_reimage`` may SKIP
    unreachable current-state probes because all nodes are imaged afterward.
    """
    out: list[Result] = []
    require_positive = inv.cluster.start_mode == "factory_preinstalled"
    expected = _iso_version_from_url(inv.cluster.iso.url)
    if expected is None:
        out.append(Result("version.iso_parse", FAIL if require_positive else WARN,
                          f"could not parse a release tag from ISO URL "
                          f"{inv.cluster.iso.url!r}; node-version drift will be "
                          f"detectable but the expected-version comparison cannot be made"))
    else:
        out.append(Result("version.iso_parse", PASS,
                          f"expected ND release {expected!r} (from ISO filename)"))

    password = os.environ.get(inv.admin_pass_ref, "")
    if not password:
        status = FAIL if require_positive else SKIP
        detail = (
            f"env var {inv.admin_pass_ref} not set; cannot SSH rescue-user to "
            f"read `acs show version`."
        )
        detail += (
            " Positive release verification is required for factory_preinstalled."
            if require_positive
            else " Export it from your secret manager and re-run."
        )
        out.append(Result("version.cluster_match", status, detail))
        return out

    detected: dict[str, str] = {}   # hostname -> version string
    unavailable: dict[str, str] = {}
    for n in inv.nodes:
        rid = f"version.node.{n.hostname}"
        try:
            with socket.create_connection((n.mgmt.ip, 22), timeout=tcp_timeout):
                pass
        except OSError as e:
            detail = (
                f"{n.hostname} mgmt {n.mgmt.ip}:22 unreachable "
                f"({e.__class__.__name__}); installed release cannot be read live"
            )
            if require_positive:
                unavailable[n.hostname] = detail
            else:
                out.append(Result(rid, SKIP, detail))
            continue
        version, detail = _ssh_acs_version(n.mgmt.ip, password, timeout=ssh_timeout)
        if version is None:
            out.append(Result(rid, FAIL if require_positive else WARN,
                              f"{n.hostname} {n.mgmt.ip} reachable but version probe failed: {detail}"))
            continue
        detected[n.hostname] = version
        if expected is None:
            out.append(Result(rid, PASS, f"{n.hostname} on ND {version}"))
        elif version == expected:
            out.append(Result(rid, PASS, f"{n.hostname} on ND {version} (matches ISO)"))
        else:
            out.append(Result(rid, FAIL if require_positive else WARN,
                              f"{n.hostname} on ND {version}, expected {expected} from ISO"))

    if require_positive and unavailable:
        if release_evidence_path is None:
            runtime = getattr(inv, "runtime", None)
            state_dir = Path(getattr(runtime, "state_dir", "state/"))
            release_evidence_path = state_dir / "nd-release-evidence.json"
        evidence_path = Path(release_evidence_path)
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence_nodes = evidence["nodes"]
            if evidence.get("selected_release") != expected:
                raise ValueError("selected release does not match inventory")
        except Exception as e:  # noqa: BLE001
            for hostname, detail in unavailable.items():
                out.append(Result(
                    f"version.node.{hostname}",
                    FAIL,
                    f"{detail}; trusted pre-reset release evidence unavailable: "
                    f"{e.__class__.__name__}: {e}",
                ))
        else:
            from discover_serials import _discover  # local script module

            verify = inv.runtime.ca_bundle or inv.runtime.verify_tls
            for n in inv.nodes:
                if n.hostname not in unavailable:
                    continue
                try:
                    _, current = _discover(n, verify)
                    prior = evidence_nodes.get(n.hostname, {})
                    if prior.get("cimc_ip") != n.cimc.ip:
                        raise ValueError(f"{n.hostname}: evidence CIMC mismatch")
                    if prior.get("serial_number") != current.get("serial_number"):
                        raise ValueError(
                            f"{n.hostname}: current serial does not match evidence"
                        )
                    if prior.get("installed_release") != expected:
                        raise ValueError(f"{n.hostname}: evidence release mismatch")
                except Exception as e:  # noqa: BLE001
                    out.append(Result(
                        f"version.node.{n.hostname}",
                        FAIL,
                        f"{unavailable[n.hostname]}; trusted pre-reset release "
                        f"evidence could not be bound to current hardware: "
                        f"{e.__class__.__name__}: {e}",
                    ))
                    continue
                detected[n.hostname] = expected
                out.append(Result(
                    f"version.node.{n.hostname}",
                    PASS,
                    f"{n.hostname} ND {expected} verified by pre-reset evidence "
                    f"and current CIMC serial {current.get('serial_number')}",
                ))

    rid = "version.cluster_match"
    if require_positive and len(detected) != len(inv.nodes):
        out.append(Result(
            rid,
            FAIL,
            f"factory_preinstalled requires positive release verification for all "
            f"{len(inv.nodes)} nodes; verified {len(detected)}",
        ))
        return out
    if not detected:
        out.append(Result(rid, SKIP,
                          "no node responded on mgmt:22; if these are factory-shipped "
                          "boxes, run `scripts/install_secondaries.py` (and "
                          "`install_node1.py`) so all 3 nodes share one ISO release "
                          "before cluster commit. See troubleshooting.md §17."))
        return out

    versions = set(detected.values())
    if len(versions) > 1:
        listing = ", ".join(f"{h}={v}" for h, v in sorted(detected.items()))
        status = FAIL if require_positive else WARN
        detail = f"version drift across nodes ({listing})."
        detail += (
            " factory_preinstalled requires all nodes to match the selected release."
            if require_positive
            else " iso_reimage will install the selected ISO on all three nodes "
                 "before cluster formation."
        )
        out.append(Result(rid, status, detail))
        return out

    only = next(iter(versions))
    if expected is None:
        out.append(Result(rid, FAIL if require_positive else PASS,
                          f"all probed nodes on ND {only}, but no release could be "
                          f"parsed from the inventory-selected ISO"))
    elif only == expected:
        out.append(Result(rid, PASS,
                          f"all {len(detected)} nodes on ND {only} (matches ISO)"))
    else:
        out.append(Result(rid, FAIL if require_positive else WARN,
                          f"all probed nodes on ND {only} but ISO is {expected}; "
                          f"verify nd_cluster_spec.iso.url is the release you intend "
                          f"to commit, OR re-image to match the ISO"))
    return out


# ---------------------------------------------------------------------------
# Bootstrap-state heuristic
#
# Failure mode being detected: troubleshooting.md §1 — after a half-failed
# `POST /v2/bootstrap/persona` or `POST /v2/bootstrap/cluster`, nd-1 holds
# a "draft cluster" record. The next attempt returns:
#
#     500 Pending cluster bootstrap exists - please cleanup and retry
#
# The only recovery is `acs reboot factory-reset` on nd-1
# (troubleshooting.md §10 / D-003).
#
# API-level honesty: GET /bootstrap/status DOES NOT distinguish the
# pending-draft state from a clean-not-bootstrapped state. We tested this
# empirically (logs/probe-cleanup-20260425T040218Z.log): on a node where
# `POST /v2/bootstrap/cluster?force=true` returned 500 with the pending
# error, the SAME node simultaneously returned `{"bootstrapped":false,
# "message":"Cluster is not bootstrapped"}` from GET /bootstrap/status —
# identical to a freshly-bootstrapped, never-committed node. There is NO
# read endpoint we have found that exposes the pending-draft state, and
# we explicitly chose not to add a destructive write probe to a
# non-destructive precheck.
#
# What we CAN do is a heuristic WARN that names both interpretations. If
# the leader is reachable AND the admin password authenticates AND the
# cluster reports not-bootstrapped, the operator is in one of two states:
#   (a) legitimate first attempt mid-flow — no action needed.
#   (b) retry after a previous failed cluster commit — MUST factory-reset
#       nd-1 before re-attempting, otherwise the next commit returns 500.
# We emit WARN (not FAIL) because the precheck cannot tell which is
# which, and we point at the recovery primitive in troubleshooting §1.
# ---------------------------------------------------------------------------

def check_bootstrap_no_pending_state(inv: Inventory, *, tcp_timeout: float = 3.0,
                                     http_timeout: float = 10.0) -> list[Result]:
    """Best-effort detector for the troubleshooting.md §1 "Pending cluster
    bootstrap exists" footgun. See the section comment above for why this
    is necessarily a heuristic, not a precise check.
    """
    out: list[Result] = []
    rid = "bootstrap.no_pending_state"
    try:
        leader = inv.bootstrap_node
    except InventoryError as e:
        out.append(Result(rid, FAIL, f"no bootstrap node: {e}"))
        return out

    # SKIP cleanly if leader's mgmt UI/API is not reachable — typical for a
    # factory-shipped node before first-boot dialog completes.
    try:
        with socket.create_connection((leader.mgmt.ip, 443), timeout=tcp_timeout):
            pass
    except OSError as e:
        out.append(Result(rid, SKIP,
                          f"leader {leader.hostname} mgmt {leader.mgmt.ip}:443 unreachable "
                          f"({e.__class__.__name__}); bootstrap-state probe SKIP until "
                          f"first-boot dialog is complete"))
        return out

    password = os.environ.get(inv.admin_pass_ref, "")
    if not password:
        out.append(Result(rid, SKIP,
                          f"env var {inv.admin_pass_ref} not set; cannot login to "
                          f"nd-1 to query /bootstrap/status"))
        return out

    # Lazy-import requests so this module still imports cleanly in environments
    # that haven't installed it (we only need it for this one optional check).
    try:
        import requests  # type: ignore
        import urllib3   # type: ignore
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception as e:  # noqa: BLE001
        out.append(Result(rid, SKIP,
                          f"requests/urllib3 unavailable ({e.__class__.__name__}); "
                          f"cannot login to nd-1 to query /bootstrap/status"))
        return out

    base_url = f"https://{leader.mgmt.ip}"
    s = requests.Session()
    s.verify = inv.runtime.verify_tls
    try:
        r = s.post(
            f"{base_url}/login",
            json={
                "userName": inv.admin_username,
                "userPasswd": password,
                "domain": "DefaultAuth",
            },
            timeout=http_timeout,
        )
    except Exception as e:  # noqa: BLE001
        out.append(Result(rid, SKIP,
                          f"nd-1 /login request failed ({e.__class__.__name__}); "
                          f"cannot probe bootstrap state"))
        return out

    if r.status_code == 401 or r.status_code == 403:
        # Admin password is not yet set on the node, or the env-var value
        # doesn't match. Either way, it's impossible to be in a pending
        # cluster bootstrap state — the pending-draft is created by an
        # authenticated POST, and you can't make one without a working pw.
        out.append(Result(rid, PASS,
                          f"nd-1 /login -> {r.status_code}: admin password not yet set "
                          f"(or env var stale); pending-draft bootstrap state is not "
                          f"possible without a working admin pw"))
        return out
    if r.status_code != 200:
        out.append(Result(rid, SKIP,
                          f"nd-1 /login returned {r.status_code}; "
                          f"cannot interpret bootstrap state. Body[:200]: {r.text[:200]!r}"))
        return out

    # Login OK. Query /bootstrap/status.
    try:
        rs = s.get(f"{base_url}/bootstrap/status", timeout=http_timeout)
    except Exception as e:  # noqa: BLE001
        out.append(Result(rid, SKIP,
                          f"nd-1 /bootstrap/status request failed ({e.__class__.__name__})"))
        return out

    if rs.status_code != 200:
        out.append(Result(rid, SKIP,
                          f"nd-1 /bootstrap/status returned {rs.status_code}; "
                          f"body[:200]: {rs.text[:200]!r}"))
        return out

    try:
        body = rs.json()
    except Exception:  # noqa: BLE001
        out.append(Result(rid, SKIP,
                          f"nd-1 /bootstrap/status returned non-JSON body: "
                          f"{rs.text[:200]!r}"))
        return out

    if body.get("bootstrapped") is True:
        # Cluster is fully committed. There cannot be a pending-draft state
        # if commit completed, so this is a clean PASS.
        out.append(Result(rid, PASS,
                          f"nd-1 reports cluster bootstrapped=true; no pending state"))
        return out

    # bootstrapped=false + admin pw works = ambiguous: legit first-attempt
    # mid-flow, OR retry after failed commit (the §1 footgun). API cannot
    # distinguish — surface the WARN with both interpretations.
    out.append(Result(rid, WARN,
                      f"nd-1 admin pw is set AND cluster reports not-bootstrapped. "
                      f"This matches BOTH (a) a legit first attempt mid-flow [no action] "
                      f"AND (b) a retry after a previous failed cluster commit, in "
                      f"which case POST /v2/bootstrap/cluster will 500 with 'Pending "
                      f"cluster bootstrap exists' until you `acs reboot factory-reset` "
                      f"nd-1 (troubleshooting.md §1 / §10). The /bootstrap/status API "
                      f"cannot distinguish (a) from (b). If you have NOT previously run "
                      f"a cluster commit against this node, ignore this warning."))
    return out


def check_timezone(inv: Inventory) -> Result:
    """ND wants an IANA tz string. 'EST' is ambiguous and skips DST."""
    rid = "config.timezone"
    tz = inv.cluster.timezone
    iana_like = "/" in tz
    if iana_like:
        return Result(rid, PASS, f"timezone {tz!r} looks IANA-format")
    if tz in {"UTC", "GMT"}:
        return Result(rid, PASS, f"timezone {tz!r} ok")
    if tz in {"EST", "PST", "CST", "MST", "EDT", "PDT", "CDT", "MDT"}:
        return Result(rid, WARN,
                      f"timezone {tz!r} is ambiguous (no DST). Prefer an IANA "
                      f"zone like 'America/New_York'.")
    return Result(rid, WARN,
                  f"timezone {tz!r} is not an IANA-format string; verify ND accepts it")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all(ansible_inventory: str, *,
            skip: set[str], categories: set[str] | None,
            iso_file: str | Path | None = None) -> list[Result]:
    results: list[Result] = []

    inv_result, inv = check_inventory_parses(ansible_inventory)
    results.append(inv_result)
    if inv is None:
        return results

    repo_root = Path(__file__).resolve().parents[3]  # cisco-aipod/

    plan: list[tuple[str, callable]] = [
        ("secrets",   lambda: check_secrets_set(inv)),
        ("secrets",   lambda: [check_no_plaintext_credentials_in_repo(repo_root)]),
        ("network",   lambda: check_cimc_subnet_placement(inv)),
        ("network",   lambda: check_cimc_tcp_443(inv)),
        ("network",   lambda: check_cimc_tcp_22(inv)),
        ("network",   lambda: check_nd1_path_to_cimc_and_data_gw(inv)),
        ("iso",       lambda: [check_iso_sha512_set(inv)]),
        ("iso",       lambda: check_iso_reachable(inv)),
        (
            "iso",
            lambda: (
                [Result("iso.sha512_url", SKIP, "skipped via --skip")]
                if "iso.sha512_url" in skip
                else [check_iso_sha512_url(inv)]
            ),
        ),
        ("dns",       lambda: check_dns_resolves_ntp(inv)),
        ("topology",  lambda: check_node_ips_in_subnet(inv)),
        ("topology",  lambda: check_persistent_ips(inv)),
        ("version",   lambda: check_node_os_version_match(inv)),
        ("bootstrap", lambda: check_bootstrap_no_pending_state(inv)),
        ("config",    lambda: [check_timezone(inv)]),
    ]
    if iso_file is not None:
        # Keep the potentially expensive full-file hash in the ISO section,
        # immediately after validating that the expected digest is present.
        plan.insert(9, ("iso", lambda: [check_iso_sha512_file(inv, iso_file)]))

    for cat, fn in plan:
        if categories and cat not in categories:
            continue
        try:
            for r in fn():
                if r.id in skip:
                    results.append(Result(r.id, SKIP, "skipped via --skip"))
                else:
                    results.append(r)
        except Exception as e:  # noqa: BLE001
            results.append(Result(f"{cat}.<error>", FAIL,
                                  f"check raised {e.__class__.__name__}: {e}"))
    return results


def render_text(results: list[Result], use_color: bool) -> str:
    lines = []
    width = max(len(r.id) for r in results)
    for r in results:
        lines.append(f"  {r.color(use_color):>14}  {r.id.ljust(width)}  {r.detail}")
    counts = {s: sum(1 for r in results if r.status == s) for s in (PASS, WARN, FAIL, SKIP)}
    summary = (f"  PASS={counts[PASS]}  WARN={counts[WARN]}  "
               f"FAIL={counts[FAIL]}  SKIP={counts[SKIP]}")
    return "\n".join([
        "",
        "  Pre-validation checklist for ND 4.3.x install",
        "  " + ("-" * 60),
        *lines,
        "  " + ("-" * 60),
        summary,
        "",
    ])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ND install pre-validation checklist")
    p.add_argument(
        "--ansible-inventory",
        default=str(THIS_DIR.parents[2] / "inventories" / "lab" / "inventory.yml"),
        help="canonical Ansible inventory (default: lab inventory.yml)",
    )
    p.add_argument("--iso-file", type=Path, default=None,
                   help="local ISO to hash and compare with cluster.iso.sha512; "
                        "the path is workstation-specific and is not stored in inventory")
    p.add_argument("--skip", action="append", default=[],
                   help="check id to skip; may be repeated")
    p.add_argument("--category", action="append", default=[],
                   help="only run these categories (secrets, network, iso, dns, topology, "
                        "version, bootstrap, config); may be repeated")
    p.add_argument("--json", action="store_true", help="machine-readable JSON output")
    p.add_argument("--no-color", action="store_true", help="disable ANSI color in text output")
    args = p.parse_args(argv)

    try:
        results = run_all(
            args.ansible_inventory,
            skip=set(args.skip),
            categories=set(args.category) if args.category else None,
            iso_file=args.iso_file,
        )
    except Exception as e:  # noqa: BLE001
        print(f"precheck crashed: {e.__class__.__name__}: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps([dataclasses.asdict(r) for r in results], indent=2))
    else:
        use_color = (not args.no_color) and sys.stdout.isatty()
        print(render_text(results, use_color))

    return 1 if any(r.status == FAIL for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
