#!/usr/bin/env python3
"""Wait for an accepted Nexus Dashboard setup job to reach completion.

ND restarts services while forming the cluster. A long-lived Ansible HTTPAPI
socket can disappear during that expected restart, so this helper creates a
fresh authenticated HTTPS session for every status check. Cluster creation
itself remains owned by ``cisco.nd.nd_setup``; this is only the reconnecting
wait for its ``/clusterstatus/install`` status endpoint.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import requests

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[2]
sys.path.insert(0, str(REPO_ROOT))

from shared.lib.inventory import load_ansible  # noqa: E402
from shared.lib.secrets import resolve  # noqa: E402


def classify_status(payload: dict[str, Any]) -> str:
    """Return ``complete``, ``failed``, or ``pending`` for an ND status body."""
    state = str(payload.get("state") or "").strip().casefold()
    overall = str(payload.get("overallStatus") or "").strip().casefold()
    if state == "completed" or overall in {"completed", "success", "successful"}:
        return "complete"
    failed = {"failed", "failure", "error", "errored", "aborted"}
    if state in failed or overall in failed:
        return "failed"
    return "pending"


def wait_for_completion(inv, *, timeout_s: int, poll_s: int) -> dict[str, Any]:
    password = resolve(inv.admin_pass_ref)
    host = inv.bootstrap_node.mgmt.ip
    verify = inv.runtime.ca_bundle or inv.runtime.verify_tls
    deadline = time.monotonic() + timeout_s
    attempt = 0
    last_summary = ""

    while True:
        attempt += 1
        session = requests.Session()
        try:
            login = session.post(
                f"https://{host}/login",
                json={
                    "userName": inv.admin_username,
                    "userPasswd": password,
                    "domain": "DefaultAuth",
                },
                verify=verify,
                timeout=30,
            )
            if login.status_code != 200:
                raise RuntimeError(f"login returned HTTP {login.status_code}")
            response = session.get(
                f"https://{host}/clusterstatus/install",
                verify=verify,
                timeout=30,
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"clusterstatus/install returned HTTP {response.status_code}"
                )
            payload = response.json()
            classification = classify_status(payload)
            summary = (
                f"state={payload.get('state')!r} "
                f"overallStatus={payload.get('overallStatus')!r} "
                f"overallProgress={payload.get('overallProgress')!r}"
            )
            if summary != last_summary:
                print(f"ND setup status: {summary}", flush=True)
                last_summary = summary
            if classification == "complete":
                return payload
            if classification == "failed":
                raise RuntimeError(f"ND setup reported failure: {summary}")
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            if isinstance(exc, RuntimeError) and str(exc).startswith(
                "ND setup reported failure:"
            ):
                raise
            print(
                f"ND setup status attempt {attempt} unavailable: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
        finally:
            session.close()

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"ND setup did not complete within {timeout_s} seconds"
            )
        time.sleep(min(poll_s, remaining))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ansible-inventory",
        default=str(REPO_ROOT / "inventories" / "lab" / "inventory.yml"),
    )
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--poll", type=int, default=30)
    args = parser.parse_args(argv)
    try:
        inv = load_ansible(args.ansible_inventory)
        timeout_s = args.timeout or inv.runtime.cluster_bringup_timeout_s
        wait_for_completion(inv, timeout_s=timeout_s, poll_s=args.poll)
    except Exception as exc:  # noqa: BLE001 - normalized CLI failure
        print(f"ERROR: ND setup wait failed: {exc}", file=sys.stderr)
        return 2
    print("ND setup completed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
