"""Wizard-flow retry against nd-1.

Sequence (mirrors the SPA wizard's POST order, with extended timeouts on the
DNS/NTP probe step that historically times out before the network is clean):

    1. GET  /bootstrap/status                    (snapshot state for log)
    2. POST /bootstrap/verifyexternalservice     (300s, stateless)
    3. POST /bootstrap/verifyclustersubnets      (300s, stateless)
    4. POST /bootstrap/verifyremoteservices      (300s, stateless; common
                                                  fail point — see notes)
    5. POST /v2/bootstrap/persona                (300s, --commit only;
                                                  WRITES STATE — see notes)
    6. POST /v2/bootstrap/cluster                (600s, --commit only; final)
    7. GET  /bootstrap/status                    (snapshot final state)

Reads the full 3-node payload from logs/bootstrap-final-payload.json and
substitutes CIMC / admin passwords from macOS Keychain at runtime. Never
logs secrets.

Operator notes (validated empirically against ND 4.2.1.10):

    * Steps 2-4 are stateless probes — safe to call repeatedly without
      side-effects. Use them to validate inventory and network reachability
      before committing.

    * Steps 5-6 WRITE STATE. The moment /v2/bootstrap/persona accepts a
      payload, ND creates a "draft" cluster record. There is NO REST endpoint
      to delete that draft (we tested every plausible path; see
      scripts/probe_cleanup.py and docs/troubleshooting.md §1). A subsequent
      attempt returns:
          500 Pending cluster bootstrap exists - please cleanup and retry
      The only way out is `acs reboot factory-reset` on nd-1
      (docs/troubleshooting.md §10) which clears bootstrap state without
      reinstalling the OS.

    * Therefore: this script defaults to verify-only. Pass --commit only
      when you've reconciled the verify output and are ready to write state.

    * If verifyremoteservices returns ntpErrors / "Could not resolve host",
      your DNS can't resolve the NTP hostnames. Switch the failing entries
      to IP literals in inventories/<site>/group_vars/nd_cluster.yml. See docs/troubleshooting.md §2.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib3

import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def keychain(service: str, account: str | None = None) -> str:
    cmd = ["security", "find-generic-password", "-s", service]
    if account:
        cmd += ["-a", account]
    cmd += ["-w"]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    return out.rstrip("\n")


def jwt_csrf(jwt: str) -> str | None:
    """Extract csrf claim from the AuthCookie JWT (no signature verify)."""
    try:
        _, payload_b64, _ = jwt.split(".")
        # base64url with padding
        pad = "=" * ((4 - len(payload_b64) % 4) % 4)
        decoded = base64.urlsafe_b64decode(payload_b64 + pad)
        return json.loads(decoded).get("csrf")
    except Exception:
        return None


def ts() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nd", default="192.0.2.7", help="nd-1 mgmt IP")
    ap.add_argument("--user", default="admin", help="ND admin user")
    ap.add_argument(
        "--payload",
        default=os.path.join(
            os.path.dirname(__file__), "..", "logs", "bootstrap-final-payload.json"
        ),
        help="Path to bootstrap payload JSON template",
    )
    ap.add_argument(
        "--commit",
        action="store_true",
        help="If set, run step 6 (final cluster commit). "
             "Otherwise dry-stop after step 5 and print what would commit.",
    )
    args = ap.parse_args()

    nd_pass = keychain("nd-lab-admin")
    cimc_pass = keychain("nd-lab-cimc", "asharma")

    with open(args.payload) as fh:
        payload = json.load(fh)

    for n in payload["nodes"]:
        nc = n.get("nodeController") or {}
        if nc.get("loginPassword", "").startswith("<CIMC"):
            nc["loginPassword"] = cimc_pass

    base_url = f"https://{args.nd}"
    s = requests.Session()
    s.verify = False

    def hit(method: str, path: str, *, body=None, timeout: int = 60, hdr=None):
        url = f"{base_url}{path}"
        t0 = time.monotonic()
        try:
            r = s.request(method, url, json=body, headers=hdr, timeout=timeout)
            dur = time.monotonic() - t0
            print(f"  {method} {path}  status={r.status_code}  {dur:.1f}s")
            txt = r.text
            print(f"    body: {txt[:600]}")
            return r
        except requests.exceptions.ReadTimeout:
            dur = time.monotonic() - t0
            print(f"  {method} {path}  TIMEOUT after {dur:.1f}s (limit {timeout}s)")
            return None
        except Exception as e:
            dur = time.monotonic() - t0
            print(f"  {method} {path}  ERROR after {dur:.1f}s: {e!r}")
            return None

    print(f"[{ts()}] login as {args.user!r} -> {base_url}/login")
    r = s.post(
        f"{base_url}/login",
        json={"userName": args.user, "userPasswd": nd_pass, "domain": "DefaultAuth"},
        timeout=30,
    )
    print(f"  status={r.status_code}")
    if r.status_code != 200:
        print(f"  body: {r.text[:400]}")
        return 1

    auth = s.cookies.get("AuthCookie")
    csrf = jwt_csrf(auth) if auth else None
    if not csrf:
        print("  WARN: no CSRF claim in AuthCookie; POSTs will likely 403/500")
    else:
        print("  CSRF token extracted (len=%d)" % len(csrf))
    hdr = {
        "Content-Type": "application/json",
        "X-Nd-Csrf-Token": csrf or "",
        "X-Csrf-Token": csrf or "",
    }

    print(f"\n[{ts()}] [0] GET /bootstrap/status (pre-state)")
    hit("GET", "/bootstrap/status", timeout=30, hdr=hdr)

    nodes = payload["nodes"]
    cc = payload["clusterConfig"]

    ves_body = {
        "externalServices": cc["externalServices"],
        "nodes": nodes,
        "enableBgp": False,
    }
    print(f"\n[{ts()}] [1] POST /bootstrap/verifyexternalservice (300s)")
    r1 = hit("POST", "/bootstrap/verifyexternalservice", body=ves_body, timeout=300, hdr=hdr)
    if not r1 or r1.status_code >= 400:
        print("  ABORT: step 1 failed")
        return 2

    vcs_body = {
        "appNetwork": cc["appNetwork"],
        "serviceNetwork": cc["serviceNetwork"],
        "nodes": nodes,
    }
    print(f"\n[{ts()}] [2] POST /bootstrap/verifyclustersubnets (300s)")
    r2 = hit("POST", "/bootstrap/verifyclustersubnets", body=vcs_body, timeout=300, hdr=hdr)
    if not r2 or r2.status_code >= 400:
        print("  ABORT: step 2 failed")
        return 3

    vrs_body = {
        "ntpServers": [s["host"] for s in cc["ntpConfig"]["servers"]],
        "ntpConfig": cc["ntpConfig"],
        "nameServers": cc["nameServers"],
        "searchDomains": cc.get("searchDomains", []),
    }
    print(f"\n[{ts()}] [3] POST /bootstrap/verifyremoteservices (300s) [PRIOR FAIL POINT]")
    r3 = hit("POST", "/bootstrap/verifyremoteservices", body=vrs_body, timeout=300, hdr=hdr)
    if not r3 or r3.status_code >= 400:
        print("  ABORT: step 3 failed -- this means data path to DNS/NTP still broken")
        return 4

    # IMPORTANT: /v2/bootstrap/persona is the first STATE-WRITING call. The
    # moment ND accepts it, a draft cluster record exists with no REST way to
    # delete it (see docs/troubleshooting.md \u00a71). Therefore the --commit gate
    # MUST sit BEFORE persona, not before /v2/bootstrap/cluster as the prior
    # implementation did. A verify-only run that ran persona would create the
    # exact "Pending cluster bootstrap exists" trap this script's docstring
    # warns about - which is what bit us in the prior session and forced an
    # `acs reboot factory-reset` recovery.
    if not args.commit:
        print(f"\n[{ts()}] [4] DRY-STOP before /v2/bootstrap/persona (FIRST state-writing step)")
        print("  Verify steps 1-3 PASSED. The next call (POST /v2/bootstrap/persona)")
        print("  would create a draft cluster record with no REST recovery path.")
        print("  Re-run with --commit to push persona + cluster commit.")
        return 0

    persona_body = {
        "persona": cc.get("persona", "LAN"),
        "deploymentScaleProfile": cc.get("deploymentScaleProfile", {}),
        "clusterSize": len(nodes),
    }
    print(f"\n[{ts()}] [4] POST /v2/bootstrap/persona (300s, STATE-WRITING)")
    r4 = hit("POST", "/v2/bootstrap/persona", body=persona_body, timeout=300, hdr=hdr)
    if not r4 or r4.status_code >= 400:
        print("  step 4 (persona) failed; if it returned 'Pending cluster bootstrap exists'")
        print("  see docs/troubleshooting.md \u00a71 + \u00a710 (acs reboot factory-reset).")
        return 5

    print(f"\n[{ts()}] [5] POST /v2/bootstrap/cluster (600s, FINAL COMMIT)")
    r5 = hit("POST", "/v2/bootstrap/cluster", body=payload, timeout=600, hdr=hdr)
    if not r5 or r5.status_code >= 400:
        print("  step 5 (cluster commit) failed; recovery: acs reboot factory-reset on nd-1")
        print("  (see docs/troubleshooting.md \u00a710). Then re-run --commit.")
        return 6

    print(f"\n[{ts()}] [6] GET /bootstrap/status (post-state)")
    hit("GET", "/bootstrap/status", timeout=30, hdr=hdr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
