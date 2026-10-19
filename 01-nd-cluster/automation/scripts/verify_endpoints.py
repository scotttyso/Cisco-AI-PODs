"""verify_endpoints.py — confirm ND 4.2.x REST contract on a live appliance.

Run this once nd-1's mgmt IP is up, BEFORE driving the cluster_bringup phase.
It will:

  1. Probe HTTPS reachability on the nd-1 mgmt IP.
  2. POST /api/v1/infra/login and report jwttoken / AuthCookie behavior.
  3. GET /api/v1/infra/cluster/status and print top-level keys + state.
  4. GET /api/v1/infra/cluster/nodes and print per-node summary.
  5. GET /nexus/infra/api/platform/v1/clusters/<candidate spec names> to
     discover what spec name the platform API expects.
  6. Try to fetch the live OpenAPI spec from a few common locations
     (/help-center/swagger/spec.json, /api/v1/infra/openapi.json, ...).
  7. POST /api/v1/infra/logout.

Read-only: this script never POSTs anything mutating. Safe to run on the
running cluster. Output is structured JSON + a final human summary.

Usage:
  ND_ADMIN_PASSWORD=... python scripts/verify_endpoints.py \
      --host 192.0.2.7 --insecure

Workspace rules: the admin password is taken from the env var (never
hardcoded, never logged). With self-signed certs, pass --insecure.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(THIS_DIR.resolve().parents[2]))

from nd_api import ENDPOINTS  # noqa: E402

# Candidate paths where ND may expose its OpenAPI/Swagger document.
OPENAPI_PROBE_PATHS = (
    "/help-center/swagger/spec.json",
    "/help-center/swagger/openapi.json",
    "/api/v1/infra/openapi.json",
    "/api/v1/infra/swagger.json",
    "/openapi.json",
)


def _truncate(value: Any, n: int = 240) -> str:
    s = json.dumps(value, default=str)
    return s if len(s) <= n else s[: n - 3] + "..."


def _print(event: str, **fields: Any) -> None:
    """Plain JSON-line output so this is greppable in CI logs."""
    payload = {"event": event}
    payload.update(fields)
    print(json.dumps(payload, default=str))


def _get(s: requests.Session, url: str, *, verify: bool) -> tuple[int, Any]:
    r = s.get(url, verify=verify, timeout=15)
    body: Any
    try:
        body = r.json()
    except ValueError:
        body = r.text[:300]
    return r.status_code, body


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", required=True, help="nd-1 mgmt IP or hostname")
    p.add_argument("--user", default="admin")
    p.add_argument("--domain", default="local",
                   help="Auth domain. Common values: 'local', 'DefaultAuth'")
    p.add_argument("--insecure", action="store_true",
                   help="Skip TLS verification (lab only).")
    p.add_argument("--timeout", type=int, default=15)
    p.add_argument("--cluster-spec-candidates", default="",
                   help="Comma-separated candidate spec names to GET on the "
                        "platform /clusters/{specName} endpoint. "
                        "Defaults: <hostname>, AIPOD-ND-CLUSTER, default")
    args = p.parse_args(argv)

    pw = os.environ.get("ND_ADMIN_PASSWORD")
    if not pw:
        print("ERROR: ND_ADMIN_PASSWORD env var not set.", file=sys.stderr)
        return 2

    verify = not args.insecure
    if args.insecure:
        from urllib3 import disable_warnings
        from urllib3.exceptions import InsecureRequestWarning
        disable_warnings(InsecureRequestWarning)

    base = f"https://{args.host}"
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Accept": "application/json",
    })

    findings: dict[str, Any] = {"endpoints": {}, "openapi": None,
                                "platformSpecCandidates": {}}

    # ----- 1. reachable -------------------------------------------------------
    try:
        r = session.get(f"{base}/", verify=verify, timeout=args.timeout)
        _print("nd.reachable.ok", status=r.status_code)
    except requests.RequestException as e:
        _print("nd.reachable.err", err=str(e))
        return 3

    # ----- 2. login -----------------------------------------------------------
    # Verified live on ND 4.2.1.10 (192.0.2.7): login is at /login (NOT
    # under /api/v1/infra/). Returns {jwttoken, csrfToken, token, rbac, ...}
    # and Set-Cookie: AuthCookie=<jwt>.
    login_url = f"{base}{ENDPOINTS['login']}"
    body = {"userName": args.user, "userPasswd": pw, "domain": args.domain}
    try:
        r = session.post(login_url, json=body, verify=verify, timeout=args.timeout)
    except requests.RequestException as e:
        _print("nd.login.err", err=str(e))
        return 4
    login_ok = r.status_code == 200
    auth_cookie_set = "AuthCookie" in session.cookies
    try:
        login_body = r.json()
    except ValueError:
        login_body = {}
    has_jwt = bool(login_body.get("jwttoken") or login_body.get("token"))
    _print(
        "nd.login.result",
        ok=login_ok, status=r.status_code,
        cookieSet=auth_cookie_set, hasJwtToken=has_jwt,
        responseKeys=sorted(list(login_body.keys())) if isinstance(login_body, dict) else [],
        bodyPreview=_truncate(login_body, 160),
    )
    if not login_ok or (not auth_cookie_set and not has_jwt):
        return 5
    findings["endpoints"]["login"] = {
        "path": login_url, "ok": True, "cookieSet": auth_cookie_set, "jwt": has_jwt,
    }

    # CSRF token from the login response is required for any state-changing call
    # (verified live: the bootstrap endpoint enforces it). Read-only GETs work
    # without it but it's harmless to send.
    csrf = login_body.get("csrfToken") if isinstance(login_body, dict) else None
    if csrf:
        session.headers["X-Nd-Csrf-Token"] = csrf
        session.headers["X-Csrf-Token"] = csrf

    # ----- 3. bootstrap status (pre-cluster) ----------------------------------
    # Verified live on ND 4.2.1.10: /bootstrap/status returns
    # {bootstrapped: bool, message: str}. This is the gate that tells us
    # whether to drive the cluster_bringup phase or treat the cluster as
    # already formed (in which case we use /api/v1/infra/cluster/status).
    sc, body = _get(session, f"{base}{ENDPOINTS['bootstrap_status']}", verify=verify)
    bootstrapped = bool(body.get("bootstrapped")) if isinstance(body, dict) else False
    _print(
        "nd.bootstrap.status",
        status=sc, bootstrapped=bootstrapped,
        message=(body.get("message") if isinstance(body, dict) else None),
    )
    findings["endpoints"]["bootstrap_status"] = {
        "path": f"{base}{ENDPOINTS['bootstrap_status']}",
        "status": sc, "bootstrapped": bootstrapped,
    }

    # ----- 4. bootstrap cluster doc (the POST template) -----------------------
    # Verified live: GET /bootstrap/cluster returns
    # {schemaversion, nodes[], clusterConfig, cloudConfig}. The same shape is
    # POSTed back (with hostNames, all 3 nodes incl. CIMC creds for non-self,
    # full clusterConfig including ntpConfig/dnsConfig/persistentIPs/etc.) to
    # actually trigger the cluster bring-up.
    sc, body = _get(session, f"{base}{ENDPOINTS['bootstrap_cluster']}", verify=verify)
    nodes = body.get("nodes") or [] if isinstance(body, dict) else []
    self_node = next((n for n in nodes if isinstance(n, dict) and n.get("self")), {})
    cluster_cfg = body.get("clusterConfig") or {} if isinstance(body, dict) else {}
    _print(
        "nd.bootstrap.cluster.template",
        status=sc,
        schemaversion=(body.get("schemaversion") if isinstance(body, dict) else None),
        nodeCount=len(nodes),
        selfSerialNumber=self_node.get("serialNumber"),
        selfStatus=self_node.get("status"),
        selfMgmtIP=(self_node.get("managementNetwork") or {}).get("ipSubnet"),
        clusterConfigKeys=sorted(list(cluster_cfg.keys())),
    )
    findings["endpoints"]["bootstrap_cluster"] = {
        "path": f"{base}{ENDPOINTS['bootstrap_cluster']}",
        "status": sc,
        "schemaversion": body.get("schemaversion") if isinstance(body, dict) else None,
    }

    # Capture the live template to disk so cluster_bringup can diff against it.
    template_dump = Path("logs") / f"bootstrap-template-{args.host}.json"
    template_dump.parent.mkdir(parents=True, exist_ok=True)
    template_dump.write_text(json.dumps(body, indent=2, default=str))
    _print("nd.bootstrap.cluster.template.saved", path=str(template_dump))

    # ----- 5. legacy infra/cluster status (post-cluster sanity) ---------------
    # Will return 404 pre-cluster; documented here so we know it's expected.
    sc, body = _get(
        session, f"{base}/api/v1/infra{ENDPOINTS['cluster_status']}", verify=verify,
    )
    _print("nd.cluster.status.legacy", status=sc, expected="404 pre-cluster")
    findings["endpoints"]["cluster_status_legacy"] = {
        "path": f"{base}/api/v1/infra{ENDPOINTS['cluster_status']}",
        "status": sc,
    }

    # ----- 6. logout ----------------------------------------------------------
    logout_url = f"{base}{ENDPOINTS['logout']}"
    try:
        r = session.post(logout_url, verify=verify, timeout=args.timeout)
        _print("nd.logout", status=r.status_code)
    except requests.RequestException as e:
        _print("nd.logout.err", err=str(e))

    # ----- summary ------------------------------------------------------------
    _print("nd.verify.summary", findings=findings)
    print("\nHuman summary:")
    print(f"  login                : OK (cookie={auth_cookie_set}, jwt={has_jwt}, csrf={bool(csrf)})")
    print(f"  /bootstrap/status    : HTTP {findings['endpoints']['bootstrap_status']['status']}, "
          f"bootstrapped={findings['endpoints']['bootstrap_status']['bootstrapped']}")
    print(f"  /bootstrap/cluster   : HTTP {findings['endpoints']['bootstrap_cluster']['status']}, "
          f"schemaversion={findings['endpoints']['bootstrap_cluster']['schemaversion']}")
    print(f"  /api/v1/infra/cluster/status (legacy) : HTTP "
          f"{findings['endpoints']['cluster_status_legacy']['status']} (404 expected pre-cluster)")
    print(f"  Live template saved  : {template_dump}")
    print("\nNext step:")
    print("  - If bootstrapped=false, drive cluster_bringup.py which will POST")
    print("    /bootstrap/cluster with the full 3-node spec from inventory.")
    print("  - If bootstrapped=true, switch to runtime cluster API (probe further).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
