"""Diagnostic probe of plausible cleanup endpoints on nd-1.

Tries every method/path combination that could plausibly clear the
"Pending cluster bootstrap exists" record (the 500 returned by
POST /v2/bootstrap/cluster after a partial wizard flow). Each attempt is
bounded to 8s. Read-only on success/failure — no side effects beyond what
the endpoint itself defines.

Empirical findings (ND 4.2.1.10) — KEEP IN SYNC with
docs/troubleshooting.md §1, which renders this matrix for human consumption:

    DELETE /v2/bootstrap/cluster                         -> 405 Method Not Allowed
    DELETE /bootstrap/cluster                            -> 405
    POST   /bootstrap/reset                              -> 500 (only valid in 'failed' state)
    POST   /v2/bootstrap/recover                         -> 500 (same)
    POST   /bootstrap/abort                              -> 404
    POST   /bootstrap/cancel                             -> 404
    POST   /bootstrap/cleanup                            -> 404
    POST   /bootstrap/clear                              -> 404
    POST   /bootstrap/discard                            -> 404
    POST   /v2/bootstrap/abort                           -> 404
    POST   /v2/bootstrap/cancel                          -> 404
    POST   /v2/bootstrap/cleanup                         -> 404
    PUT    /v2/bootstrap/cluster                         -> 405
    POST   /v2/bootstrap/cluster?force=true              -> 500 (same pending error)
    POST   /v2/bootstrap/cluster?reconfigureBootstrap=t  -> 500 (same)
    POST   /v2/bootstrap/node?force=true                 -> 500

Conclusion: there is no API path. Use `acs reboot factory-reset` on nd-1
(docs/troubleshooting.md §10).

Re-run this probe after every ND release to confirm the matrix still holds.
If a new endpoint appears that DOES clear pending state, update both this
docstring and docs/troubleshooting.md §1.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import urllib3

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.lib.inventory import load_ansible  # noqa: E402
from shared.lib.secrets import resolve  # noqa: E402

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ansible-inventory",
        type=Path,
        default=repo_root / "inventories" / "lab" / "inventory.yml",
        help="Canonical Ansible inventory path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inv = load_ansible(args.ansible_inventory)
    leader = inv.bootstrap_node
    nd_url = f"https://{leader.mgmt.ip}"
    password = resolve(inv.admin_pass_ref)

    s = requests.Session()
    s.verify = inv.runtime.ca_bundle or inv.runtime.verify_tls
    r = s.post(
        f"{nd_url}/login",
        json={
            "userName": inv.admin_username,
            "userPasswd": password,
            "domain": "DefaultAuth",
        },
        timeout=15,
    )
    print(f"login status={r.status_code}")
    if r.status_code != 200:
        return 1

    candidates = [
        ("DELETE", "/v2/bootstrap/cluster"),
        ("DELETE", "/bootstrap/cluster"),
        ("DELETE", "/v2/bootstrap"),
        ("DELETE", "/bootstrap"),
        ("POST",   "/v2/bootstrap/cleanup"),
        ("POST",   "/bootstrap/cleanup"),
        ("POST",   "/v2/bootstrap/abort"),
        ("POST",   "/bootstrap/abort"),
        ("POST",   "/v2/bootstrap/cancel"),
        ("POST",   "/bootstrap/cancel"),
        ("POST",   "/v2/bootstrap/discard"),
        ("POST",   "/bootstrap/discard"),
        ("POST",   "/v2/bootstrap/clear"),
        ("POST",   "/bootstrap/clear"),
        ("POST",   "/bootstrap/reset"),
        ("POST",   "/v2/bootstrap/reset"),
        ("POST",   "/v2/bootstrap/recover"),
        ("POST",   "/bootstrap/recover"),
        ("DELETE", "/v2/bootstrap/cluster?force=true"),
        ("POST",   "/v2/bootstrap/cluster?force=true"),
        ("PUT",    "/v2/bootstrap/cluster"),
        ("PATCH",  "/v2/bootstrap/cluster"),
    ]
    for method, path in candidates:
        try:
            r = s.request(method, f"{nd_url}{path}", json={}, timeout=8)
            body = r.text[:160].replace("\n", " ")
            print(f"  {method:6s} {path:40s}  -> {r.status_code}  {body}")
        except Exception as e:
            print(f"  {method:6s} {path:40s}  -> ERR  {e!r}")

    print("\nfinal status check:")
    r = s.get(f"{nd_url}/bootstrap/status", timeout=10)
    print(f"  GET /bootstrap/status -> {r.status_code}  {r.text[:300]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
