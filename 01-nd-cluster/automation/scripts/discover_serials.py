"""Verify ND node power and discover appliance serials through CIMC.

The result is a run-specific, gitignored artifact. Editable inventory keeps
addresses and credential references; physical identity is refreshed at
runtime so a chassis swap or cabling mismatch cannot silently reuse a stale
serial number. The same artifact records Redfish ``PowerState`` so the role
can require every node to be ``On`` before ``cisco.nd.nd_setup`` commits a
one-shot cluster bringup.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[2]
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(REPO_ROOT))

from shared.lib.inventory import load_ansible  # noqa: E402
from shared.lib.secrets import resolve  # noqa: E402

from cimc_redfish import CimcRedfish, RedfishTransient  # noqa: E402


def _discover(node, verify: bool | str) -> tuple[str, dict[str, str]]:
    password = resolve(node.cimc.pass_ref)
    client = CimcRedfish(
        node.cimc.ip,
        node.cimc.user,
        password,
        verify=verify,
    )
    try:
        with client.session():
            power_state = client.power_state().strip()
            serial = client.serial_number().strip()
    except RedfishTransient:
        # Discovery is GET-only. CIMC may refuse token-session creation for a
        # period after host factory reset while standards-compliant HTTP Basic
        # reads remain available. Never use this fallback for CIMC mutations.
        with client.basic_session():
            power_state = client.power_state().strip()
            serial = client.serial_number().strip()
    if not serial:
        raise RuntimeError(f"{node.hostname}: CIMC returned an empty serial")
    return node.hostname, {
        "cimc_ip": node.cimc.ip,
        "power_state": power_state,
        "serial_number": serial,
    }


def discover(inv) -> dict[str, Any]:
    verify = inv.runtime.ca_bundle or inv.runtime.verify_tls
    records: dict[str, dict[str, str]] = {}
    with ThreadPoolExecutor(max_workers=len(inv.nodes)) as pool:
        futures = {pool.submit(_discover, node, verify): node for node in inv.nodes}
        for future in as_completed(futures):
            host, record = future.result()
            records[host] = record
    return {
        "schema_version": 1,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "nodes": {node.hostname: records[node.hostname] for node in inv.nodes},
    }


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify ND node power and discover serials via CIMC Redfish"
    )
    parser.add_argument(
        "--ansible-inventory",
        default=str(REPO_ROOT / "inventories" / "lab" / "inventory.yml"),
    )
    parser.add_argument("--out", default="state/nd-serials.json")
    args = parser.parse_args(argv)
    try:
        inv = load_ansible(args.ansible_inventory)
        payload = discover(inv)
        _write_atomic(Path(args.out), payload)
    except Exception as exc:  # noqa: BLE001 - normalized CLI failure
        print(f"ERROR: serial discovery failed: {exc}", file=sys.stderr)
        return 2
    for host, record in payload["nodes"].items():
        print(
            f"{host}: CIMC {record['cimc_ip']} -> "
            f"power {record['power_state']}, serial {record['serial_number']}"
        )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
