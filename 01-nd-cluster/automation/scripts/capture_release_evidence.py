#!/usr/bin/env python3
"""Capture secret-free, pre-reset ND release evidence bound to CIMC serials."""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import tempfile
import time
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[2]
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(REPO_ROOT))

from precheck import _iso_version_from_url, _ssh_acs_version  # noqa: E402
from shared.lib.inventory import load_ansible  # noqa: E402
from shared.lib.secrets import resolve  # noqa: E402


def capture(inv, serial_artifact: dict) -> dict:
    expected = _iso_version_from_url(inv.cluster.iso.url)
    if expected is None:
        raise RuntimeError("cannot derive selected release from inventory ISO URL")
    serial_nodes = serial_artifact.get("nodes")
    if not isinstance(serial_nodes, dict):
        raise RuntimeError("serial artifact is missing nodes")

    admin_password = resolve(inv.admin_pass_ref)
    records = {}
    for node in inv.nodes:
        hardware = serial_nodes.get(node.hostname)
        if not isinstance(hardware, dict):
            raise RuntimeError(f"serial artifact is missing {node.hostname}")
        if hardware.get("cimc_ip") != node.cimc.ip:
            raise RuntimeError(f"{node.hostname}: serial artifact CIMC mismatch")
        with socket.create_connection((node.mgmt.ip, 22), timeout=8):
            pass
        release, detail = _ssh_acs_version(node.mgmt.ip, admin_password, timeout=12)
        if release != expected:
            raise RuntimeError(
                f"{node.hostname}: installed release {release!r} does not match "
                f"selected release {expected!r} ({detail})"
            )
        records[node.hostname] = {
            "cimc_ip": node.cimc.ip,
            "serial_number": hardware.get("serial_number"),
            "installed_release": release,
        }

    return {
        "schema_version": 1,
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "selected_release": expected,
        "nodes": records,
    }


def _write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ansible-inventory",
        default=str(REPO_ROOT / "inventories" / "lab" / "inventory.yml"),
    )
    parser.add_argument("--serial-artifact", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        inv = load_ansible(args.ansible_inventory)
        serials = json.loads(args.serial_artifact.read_text(encoding="utf-8"))
        payload = capture(inv, serials)
        _write_atomic(args.out, payload)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: release evidence capture failed: {exc}", file=sys.stderr)
        return 2
    print(f"verified {len(payload['nodes'])} nodes on {payload['selected_release']}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
