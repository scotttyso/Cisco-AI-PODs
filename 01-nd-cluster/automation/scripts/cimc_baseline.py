"""Read-only Redfish baseline snapshot of all CIMCs in inventory.

Captures, per node:
  - Auth result (login/logout round-trip)
  - System: model, serial, BIOS version, PowerState, Boot config
  - Manager (CIMC): firmware version, model
  - Virtual media: each slot's MediaTypes / Inserted / Image
  - NIC inventory: each NetworkAdapter -> Ports -> LinkStatus + MAC
  - Sensor health rollup if present

Writes one JSON file per node into automation/state/baseline-<host>.json
and prints a compact summary to stdout. Failures on individual sub-paths
are caught and recorded as 'error' fields rather than aborting the snapshot.

Use:
  CIMC_PASSWORD=...  ./.venv/bin/python3 scripts/cimc_baseline.py
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import sys
import time
from pathlib import Path
from typing import Any

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(THIS_DIR.resolve().parents[2]))

from shared.lib.inventory import load_ansible                        # noqa: E402
from shared.lib.logging import configure, get_logger                 # noqa: E402
from shared.lib.secrets import resolve                               # noqa: E402

from cimc_redfish import CimcRedfish, RedfishError                   # noqa: E402

log = get_logger("cimc_baseline")


def _safe(label: str, fn) -> Any:
    """Invoke fn() and return its result, or {'error': str(e), 'label': label} on failure.

    Used to keep one failed sub-call (e.g., a missing path on older firmware)
    from killing the entire baseline.
    """
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}", "label": label}


def _collect_vmedia(c: CimcRedfish) -> list[dict[str, Any]]:
    mgr = c.manager_id()
    listing = c._get(f"/Managers/{mgr}/VirtualMedia")  # noqa: SLF001
    out: list[dict[str, Any]] = []
    for m in listing.get("Members", []):
        slot = c._get(m["@odata.id"])                  # noqa: SLF001
        out.append({
            "id": slot.get("Id"),
            "name": slot.get("Name"),
            "mediaTypes": slot.get("MediaTypes"),
            "inserted": slot.get("Inserted"),
            "image": slot.get("Image"),
            "connectedVia": slot.get("ConnectedVia"),
            "writeProtected": slot.get("WriteProtected"),
        })
    return out


def _collect_nics(c: CimcRedfish, sid: str) -> list[dict[str, Any]]:
    """Walk Systems/<sid>/NetworkInterfaces -> NetworkAdapter -> Ports.

    Captures MAC + LinkStatus + speed for every physical port the CIMC
    inventories. The mgmt LOM is what we care about for the L2 issue.
    """
    out: list[dict[str, Any]] = []
    try:
        netifs = c._get(f"/Systems/{sid}/NetworkInterfaces")  # noqa: SLF001
    except RedfishError as e:
        return [{"error": f"NetworkInterfaces: {e}"}]

    for ni in netifs.get("Members", []):
        ni_path = ni["@odata.id"]
        ni_doc = _safe(ni_path, lambda p=ni_path: c._get(p))  # noqa: SLF001
        if isinstance(ni_doc, dict) and "Links" in ni_doc:
            adapter_ref = (ni_doc.get("Links", {})
                                 .get("NetworkAdapter", {})
                                 .get("@odata.id"))
            if adapter_ref:
                adapter = _safe(adapter_ref,
                                lambda p=adapter_ref: c._get(p))  # noqa: SLF001
                ports_ref = None
                if isinstance(adapter, dict):
                    if "NetworkPorts" in adapter:
                        ports_ref = adapter["NetworkPorts"]["@odata.id"]
                    elif "Ports" in adapter:
                        ports_ref = adapter["Ports"]["@odata.id"]
                if ports_ref:
                    ports_listing = _safe(ports_ref,
                                          lambda p=ports_ref: c._get(p))  # noqa: SLF001
                    if isinstance(ports_listing, dict):
                        for pm in ports_listing.get("Members", []):
                            p_path = pm["@odata.id"]
                            p_doc = _safe(p_path,
                                          lambda pp=p_path: c._get(pp))  # noqa: SLF001
                            if isinstance(p_doc, dict):
                                out.append({
                                    "adapter": adapter.get("Model")
                                        if isinstance(adapter, dict) else None,
                                    "port_id": p_doc.get("Id"),
                                    "name": p_doc.get("Name"),
                                    "linkStatus": p_doc.get("LinkStatus"),
                                    "mac": (p_doc.get("AssociatedNetworkAddresses")
                                            or p_doc.get("Ethernet", {}).get(
                                                "AssociatedMACAddresses")),
                                    "currentSpeedMbps":
                                        p_doc.get("CurrentLinkSpeedMbps")
                                        or p_doc.get("CurrentSpeedGbps"),
                                    "supportedSpeedsGbps":
                                        p_doc.get("SupportedLinkCapabilities"),
                                })
    return out or [{"note": "no ports enumerated via NetworkInterfaces"}]


def baseline_one(host: str, ip: str, user: str, password: str,
                 *, verify: bool = False) -> dict[str, Any]:
    started = time.time()
    rec: dict[str, Any] = {
        "host": host,
        "cimc_ip": ip,
        "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "auth": {"ok": False},
    }
    try:
        c = CimcRedfish(ip, user, password, verify=verify)
        c.login()
    except Exception as e:  # noqa: BLE001
        rec["auth"]["error"] = f"{type(e).__name__}: {e}"
        rec["duration_s"] = round(time.time() - started, 2)
        return rec
    rec["auth"]["ok"] = True
    try:
        sid = _safe("system_id", c.system_id)
        if isinstance(sid, str):
            rec["system_id"] = sid
            sysdoc = _safe("system", c.system)
            if isinstance(sysdoc, dict):
                rec["system"] = {
                    "model": sysdoc.get("Model"),
                    "manufacturer": sysdoc.get("Manufacturer"),
                    "serial": sysdoc.get("SerialNumber"),
                    "sku": sysdoc.get("SKU"),
                    "biosVersion": sysdoc.get("BiosVersion"),
                    "powerState": sysdoc.get("PowerState"),
                    "boot": sysdoc.get("Boot"),
                    "memoryGiB": (sysdoc.get("MemorySummary", {})
                                       .get("TotalSystemMemoryGiB")),
                    "processors":
                        sysdoc.get("ProcessorSummary", {}).get("Count"),
                    "status": sysdoc.get("Status"),
                }
            rec["nics"] = _safe("nics", lambda: _collect_nics(c, sid))
        rec["manager_id"] = _safe("manager_id", c.manager_id)
        if isinstance(rec["manager_id"], str):
            mgr_doc = _safe(
                f"manager_doc",
                lambda: c._get(f"/Managers/{rec['manager_id']}"),  # noqa: SLF001
            )
            if isinstance(mgr_doc, dict):
                rec["manager"] = {
                    "model": mgr_doc.get("Model"),
                    "firmwareVersion": mgr_doc.get("FirmwareVersion"),
                    "managerType": mgr_doc.get("ManagerType"),
                    "status": mgr_doc.get("Status"),
                }
        rec["vmedia"] = _safe("vmedia", lambda: _collect_vmedia(c))
    finally:
        try:
            c.logout()
        except Exception:  # noqa: BLE001
            pass
    rec["duration_s"] = round(time.time() - started, 2)
    return rec


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Read-only Redfish baseline of CIMCs")
    ap.add_argument(
        "--ansible-inventory",
        default=str(THIS_DIR.parents[2] / "inventories" / "lab" / "inventory.yml"),
    )
    ap.add_argument("--out-dir", default="state")
    ap.add_argument("--node", action="append",
                    help="restrict to specific hostname (repeatable)")
    args = ap.parse_args(argv)

    configure(level="INFO")

    inv = load_ansible(args.ansible_inventory)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    nodes = inv.nodes
    if args.node:
        wanted = {hostname.casefold() for hostname in args.node}
        nodes = [n for n in nodes if n.hostname.casefold() in wanted]
        if not nodes:
            print(f"no nodes match {wanted}", file=sys.stderr)
            return 2

    verify = inv.runtime.ca_bundle if inv.runtime.ca_bundle \
        else inv.runtime.verify_tls

    results: list[dict[str, Any]] = []
    with cf.ThreadPoolExecutor(max_workers=min(4, len(nodes))) as ex:
        futs = {}
        for n in nodes:
            password = resolve(n.cimc.pass_ref)
            futs[ex.submit(baseline_one, n.hostname, n.cimc.ip,
                           n.cimc.user, password, verify=verify)] = n
        for fut in cf.as_completed(futs):
            n = futs[fut]
            try:
                rec = fut.result()
            except Exception as e:  # noqa: BLE001
                rec = {
                    "host": n.hostname,
                    "cimc_ip": n.cimc.ip,
                    "auth": {"ok": False,
                             "error": f"{type(e).__name__}: {e}"},
                }
            out_file = out_dir / f"baseline-{n.hostname}.json"
            out_file.write_text(json.dumps(rec, indent=2, sort_keys=True))
            results.append(rec)

    print()
    print("=" * 78)
    print("CIMC baseline summary")
    print("=" * 78)
    for rec in sorted(results, key=lambda r: r.get("host", "")):
        host = rec.get("host", "?")
        ip = rec.get("cimc_ip", "?")
        auth = rec.get("auth", {})
        if not auth.get("ok"):
            print(f"  {host:6s} ({ip}) AUTH FAIL: {auth.get('error')}")
            continue
        sysd = rec.get("system") or {}
        mgr = rec.get("manager") or {}
        nics = rec.get("nics") or []
        vmed = rec.get("vmedia") or []
        nic_summary = ", ".join(
            f"{n.get('port_id') or n.get('name')}"
            f"={n.get('linkStatus','?')}"
            for n in nics if isinstance(n, dict) and n.get("linkStatus")
        ) or "(no port LinkStatus)"
        v_note = []
        for v in vmed:
            if isinstance(v, dict):
                marker = "INSERTED" if v.get("inserted") else "empty"
                v_note.append(f"{v.get('id')}={marker}")
        print(f"  {host:6s} ({ip})")
        print(f"      power={sysd.get('powerState')}  "
              f"bios={sysd.get('biosVersion')}  "
              f"cimcfw={mgr.get('firmwareVersion')}  "
              f"sn={sysd.get('serial')}")
        print(f"      vmedia: {', '.join(v_note) or '(none)'}")
        print(f"      ports : {nic_summary}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
