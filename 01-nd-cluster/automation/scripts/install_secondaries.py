"""Install ND OS on secondary nodes (nd-2, nd-3) in parallel.

Background — why this script exists:
  nd-1's cluster orchestrator refuses to admit a secondary whose installed
  firmware version differs from the primary's (observed error:
  "BootstrapStageIdFirstBootSetup ... Node CIMC error response:
   The installed firmware version is incompatible with cluster's.
   [Node: 4.1.1g. Cluster: 4.2.1.10]").
  `acs reboot factory-reset` clears bootstrap config but PRESERVES the OS image.
  Therefore secondaries that booted a stale (older) ND OS must be re-imaged
  with the same ISO that was used for nd-1 before the cluster commit will
  proceed past stage "Setup boot time configuration".

What this script does (per secondary, in parallel):
  Phase 1: Redfish — eject old vMedia, insert ISO, set one-time UEFI vDVD boot,
           force-restart (or power-on if Off).
  Phase 2: SOL    — at the CIMC vMedia "Press <Enter> to install/skip" prompt,
                    send 'skip' (re-use of installer skip step).
  Phase 3: SOL    — wait for installer to complete (it powers the box off).
  Phase 4: Redfish — eject vMedia, power back on. The node will boot into the
                    freshly-installed ND OS and present
                    "Press Enter to manually bootstrap your first primary node"
                    on its console — this is the "fresh state" nd-1's
                    orchestrator requires.

What this script does NOT do:
  Phase 5 (first-boot dialog over SOL) is intentionally skipped. nd-1's
  cluster bootstrap will SSH into each secondary's CIMC SOL and drive the
  first-boot dialog itself — that is exactly what stage
  "Setup boot time configuration" exists to do.

Idempotency: each phase is recorded in state/node2.json or state/node3.json
using the same scheme as state/node1.json. A re-run skips completed phases.

Secrets: never inline. Resolved from env vars via shared.lib.secrets.resolve
(which reads macOS Keychain in lab; Vault in prod). See
codeguard-1-hardcoded-credentials and shared/lib/secrets.py.
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.lib.inventory import Inventory, Node, load_ansible  # noqa: E402
from shared.lib.logging import get_logger  # noqa: E402
from shared.lib.secrets import resolve  # noqa: E402
from shared.lib.state import clear_phases, is_complete, mark  # noqa: E402

from cimc_redfish import CimcRedfish  # noqa: E402
from sol_bootstrap import Sol  # noqa: E402

log = get_logger(__name__)


def _state_name(node: Node) -> str:
    """state/node2.json, state/node3.json (matches existing state/node1.json)."""
    digit = node.hostname.split("-")[-1]
    return f"node{digit}"


def install_one(inv: Inventory, node: Node) -> tuple[str, bool, str, bool]:
    """Run phases 1-4 for one secondary.

    Returns ``(hostname, success, message, changed)``.
    """
    state_dir = inv.runtime.state_dir
    state_name = _state_name(node)
    cimc_pass = resolve(node.cimc.pass_ref)
    verify = inv.runtime.ca_bundle if inv.runtime.ca_bundle else inv.runtime.verify_tls

    iso_url = inv.cluster.iso.url

    log.info(
        "secondary install begin",
        extra={"event": "secondary.begin", "node": node.hostname,
               "cimc": node.cimc.ip, "iso": iso_url, "stateName": state_name},
    )

    changed = False
    try:
        cimc = CimcRedfish(node.cimc.ip, node.cimc.user, cimc_pass, verify=verify)
        with cimc.session():
            if not is_complete(state_dir, state_name, "mount_and_boot"):
                # A new image invalidates downstream markers from any prior
                # install while preserving idempotent resume after mounting.
                clear_phases(
                    state_dir,
                    state_name,
                    "installer_skip_sent",
                    "installer_complete",
                    "post_install_poweron",
                )
                cimc.eject_iso()
                cimc.insert_iso(iso_url)
                cimc.set_one_time_boot_vdvd()
                if cimc.power_state() == "On":
                    cimc.force_restart()
                else:
                    cimc.power_on()
                mark(state_dir, state_name, "mount_and_boot",
                     iso=iso_url, boot="UEFI vDVD once")
                changed = True
            else:
                log.info("skip mount_and_boot (state)",
                         extra={"event": "phase.skip", "node": node.hostname})

            if not is_complete(state_dir, state_name, "installer_complete"):
                with Sol(node.cimc.ip, node.cimc.user, cimc_pass) as sol:
                    if not is_complete(state_dir, state_name, "installer_skip_sent"):
                        # Empirically, the "Type 'skip' to use local media:"
                        # prompt appears 4-7 min after force-restart on
                        # UCS-C SE-NODE-G2 (kernel boot + udev settle). The
                        # original 120s ceiling here let this script declare
                        # "absent_assumed_already_skipped" and proceed to
                        # wait_for_install_complete BEFORE the prompt ever
                        # appeared, leaving the box stuck for hours waiting
                        # on a human at SOL. 900s gives margin without
                        # blocking forever on a genuinely-stuck node.
                        sent = sol.wait_and_send_skip(timeout_s=900)
                        mark(state_dir, state_name, "installer_skip_sent",
                             result=("sent" if sent else "absent_assumed_already_skipped"))
                    else:
                        log.info("skip installer_skip_sent (state)",
                                 extra={"event": "phase.skip", "node": node.hostname})
                    sol.wait_for_install_complete(timeout_s=14400)
                mark(state_dir, state_name, "installer_complete", status="complete")
                changed = True
            else:
                log.info("skip installer (state)",
                         extra={"event": "phase.skip", "node": node.hostname})

            if not is_complete(state_dir, state_name, "post_install_poweron"):
                # Streaming the ISO can exceed the CIMC token lifetime. Replace
                # the pre-install session before the first post-install mutation.
                cimc.refresh_session()
                cimc.eject_iso()
                time.sleep(15)
                cimc.power_on()
                mark(state_dir, state_name, "post_install_poweron", status="complete")
                changed = True
            else:
                log.info("skip post_install_poweron (state)",
                         extra={"event": "phase.skip", "node": node.hostname})

        log.info(
            "secondary install done",
            extra={"event": "secondary.done", "node": node.hostname,
                   "mgmtIp": node.mgmt.ip},
        )
        return (node.hostname, True, "ok", changed)
    except Exception as exc:
        log.error(
            "secondary install failed",
            extra={"event": "secondary.error", "node": node.hostname,
                   "error": repr(exc)},
        )
        return (node.hostname, False, repr(exc), changed)


def run_one(inv: Inventory, node: Node) -> bool:
    """Install one inventory node whose cluster role is secondary."""
    if node.role == "bootstrap":
        raise ValueError(f"{node.hostname} is the bootstrap node, not a secondary")
    host, ok, message, changed = install_one(inv, node)
    if not ok:
        raise RuntimeError(f"secondary install failed for {host}: {message}")
    return changed


def run(inv: Inventory) -> bool:
    secondaries = inv.secondary_nodes
    if not secondaries:
        log.info("no secondaries to install", extra={"event": "secondaries.none"})
        return False

    log.info(
        "secondary installs starting in parallel",
        extra={"event": "secondaries.parallel", "count": len(secondaries),
               "nodes": [n.hostname for n in secondaries]},
    )

    results: list[tuple[str, bool, str, bool]] = []
    with ThreadPoolExecutor(max_workers=len(secondaries)) as pool:
        futs = {pool.submit(install_one, inv, n): n for n in secondaries}
        for fut in as_completed(futs):
            results.append(fut.result())

    for host, ok, msg, changed in results:
        log.info("secondary result", extra={"event": "secondary.result",
                                            "node": host, "ok": ok, "msg": msg,
                                            "changed": changed})

    failed = [r for r in results if not r[1]]
    if failed:
        names = ", ".join(r[0] for r in failed)
        raise SystemExit(f"secondary install failed for: {names}")
    return any(r[3] for r in results)


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    inv = load_ansible(repo_root / "inventories" / "lab" / "inventory.yml")
    run(inv)
