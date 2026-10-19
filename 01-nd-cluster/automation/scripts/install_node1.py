"""Phase: install + bootstrap of ND node 1 (Redfish + SOL).

Idempotent: each step checks state file and skips if already complete.

Phases (recorded in `state/node1.json`):

    1. mount_and_boot          — Redfish: insert ISO, set one-time UEFI vDVD boot
    2. installer_skip_sent     — SOL: send 'skip' at the CIMC-vMedia prompt
    3. installer_complete      — SOL: wait for installer to finish + power off
    4. post_install_poweron    — Redfish: eject vMedia, power on
    5. bootstrap               — SOL: drive first-boot dialog
                                 (admin pw, mgmt IP/mask, gateway)

Recovery pattern after `acs reboot factory-reset`
(docs/troubleshooting.md §10):

    The factory-reset wipes only the bootstrap config; the OS install on
    disk is preserved. To re-drive ONLY the SOL first-boot dialog without
    re-running the OS install (saves ~3 hours), remove the 'bootstrap' phase
    from state/node1.json BEFORE re-running this script:

        python -c '
        import json, pathlib
        p = pathlib.Path("state/node1.json")
        s = json.loads(p.read_text())
        s.setdefault("phases", {}).pop("bootstrap", None)
        p.write_text(json.dumps(s, indent=2))
        '

    Then re-run this script; phases 1-4 are skipped (state-marked complete),
    only phase 5 executes. See automation/RESUME.md "Scenario B".

Secrets — never inline in this script or its callers. CIMC and ND admin
passwords are resolved from env vars (which the operator populates from
macOS Keychain in lab; from Vault in production). See
shared/lib/secrets.py and the workspace credentials policy
(codeguard-1-hardcoded-credentials).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.lib.inventory import Inventory  # noqa: E402
from shared.lib.logging import get_logger  # noqa: E402
from shared.lib.secrets import resolve  # noqa: E402
from shared.lib.state import clear_phases, is_complete, mark  # noqa: E402

from cimc_redfish import CimcRedfish  # noqa: E402
from sol_bootstrap import BootstrapInputs, Sol  # noqa: E402

log = get_logger(__name__)

STATE_NAME = "node1"


def run(inv: Inventory, *, dry_run: bool = False) -> bool:
    """Install + bootstrap ND node 1.

    Returns True if any mutating phase actually executed, False if every phase
    was skipped via its state marker (fully idempotent no-op) or this was a
    dry run. The orchestrator surfaces this as a ``changed=`` marker so the
    Ansible wedge can report ``changed`` honestly (see main.py / image_node.yml).
    """
    node = inv.bootstrap_node
    state_dir = inv.runtime.state_dir
    verify = inv.runtime.ca_bundle if inv.runtime.ca_bundle else inv.runtime.verify_tls

    cimc_pass = resolve(node.cimc.pass_ref)
    admin_pass = resolve(inv.admin_pass_ref)

    log.info("install_node1 begin",
             extra={"event": "node1.begin", "node": node.hostname, "cimc": node.cimc.ip,
                    "mgmt": node.mgmt.cidr, "dryRun": dry_run})

    if dry_run:
        _print_plan(node, inv)
        return False

    changed = False
    cimc = CimcRedfish(node.cimc.ip, node.cimc.user, cimc_pass, verify=verify)
    with cimc.session():
        # Phase 1: mount ISO + boot to vDVD + power-cycle.
        if not is_complete(state_dir, STATE_NAME, "mount_and_boot"):
            # A new image invalidates every completion marker produced by the
            # prior installed image, especially a stale bootstrap marker from
            # a factory-reset/configuration-only run.
            clear_phases(
                state_dir,
                STATE_NAME,
                "installer_skip_sent",
                "installer_complete",
                "post_install_poweron",
                "bootstrap",
            )
            cimc.eject_iso()
            cimc.insert_iso(inv.cluster.iso.url)
            cimc.set_one_time_boot_vdvd()
            if cimc.power_state() == "On":
                cimc.force_restart()
            else:
                cimc.power_on()
            mark(state_dir, STATE_NAME, "mount_and_boot",
                 iso=inv.cluster.iso.url, boot="UEFI vDVD once")
            changed = True
        else:
            log.info("skip mount_and_boot (state)", extra={"event": "phase.skip"})

        # Phase 2 + 3: SOL skip + wait for installer + power-off.
        # Two independent state markers so a resumed run that already past the
        # vMedia 'skip' prompt doesn't fail just because the prompt is gone.
        if not is_complete(state_dir, STATE_NAME, "installer_complete"):
            with Sol(node.cimc.ip, node.cimc.user, cimc_pass) as sol:
                if not is_complete(state_dir, STATE_NAME, "installer_skip_sent"):
                    # Fresh UCS-C vMedia boots can take 4-7 minutes to reach
                    # this prompt. Match the proven secondary-node allowance;
                    # 120 seconds can falsely mark a fresh install as resumed
                    # and leave the node waiting indefinitely for "skip".
                    sent = sol.wait_and_send_skip(timeout_s=900)
                    mark(state_dir, STATE_NAME, "installer_skip_sent",
                         result=("sent" if sent else "absent_assumed_already_skipped"))
                else:
                    log.info("skip installer_skip_sent (state)", extra={"event": "phase.skip"})
                sol.wait_for_install_complete(timeout_s=14400)
            mark(state_dir, STATE_NAME, "installer_complete", status="complete")
            changed = True
        else:
            log.info("skip installer (state)", extra={"event": "phase.skip"})

        # Phase 4: eject vMedia + power-on for first-boot.
        if not is_complete(state_dir, STATE_NAME, "post_install_poweron"):
            # Streaming the ISO can exceed the CIMC token lifetime. Replace
            # the pre-install session before the first post-install mutation.
            cimc.refresh_session()
            cimc.eject_iso()
            # Give CIMC a moment after install power-off before we power back on.
            time.sleep(15)
            cimc.power_on()
            mark(state_dir, STATE_NAME, "post_install_poweron", status="complete")
            changed = True
        else:
            log.info("skip post_install_poweron (state)", extra={"event": "phase.skip"})

        # Phase 5: SOL first-boot bootstrap.
        changed |= _bootstrap_first_primary(
            inv,
            node=node,
            cimc_pass=cimc_pass,
            admin_pass=admin_pass,
        )

    log.info("install_node1 done",
             extra={"event": "node1.done", "node": node.hostname,
                    "mgmtIp": node.mgmt.ip, "changed": changed})
    return changed


def bootstrap_only(inv: Inventory, *, dry_run: bool = False) -> bool:
    """Bootstrap ND-1 without reinstalling its already verified ND image.

    This is the configuration-only path used after ``acs reboot
    factory-reset`` and for factory-preinstalled appliances. The caller must
    positively verify the installed release before invoking this function.
    """
    node = inv.bootstrap_node
    state_dir = inv.runtime.state_dir
    if is_complete(state_dir, STATE_NAME, "bootstrap"):
        log.info(
            "skip bootstrap-only (state)",
            extra={"event": "phase.skip", "node": node.hostname},
        )
        return False

    verify = inv.runtime.ca_bundle if inv.runtime.ca_bundle else inv.runtime.verify_tls
    cimc_pass = resolve(node.cimc.pass_ref)
    admin_pass = resolve(inv.admin_pass_ref)

    if dry_run:
        print("DRY RUN: would retain the installed ND image and bootstrap ND-1")
        print(f"  CIMC:           {node.cimc.ip} (user {node.cimc.user})")
        print(f"  SOL bootstrap:  mgmt {node.mgmt.cidr} gw {node.mgmt.gateway}")
        return False

    changed = False
    cimc = CimcRedfish(node.cimc.ip, node.cimc.user, cimc_pass, verify=verify)
    with cimc.session():
        if cimc.power_state() != "On":
            cimc.power_on()
            changed = True

    changed |= _bootstrap_first_primary(
        inv,
        node=node,
        cimc_pass=cimc_pass,
        admin_pass=admin_pass,
    )
    log.info(
        "bootstrap-only done",
        extra={
            "event": "node1.bootstrap_only.done",
            "node": node.hostname,
            "mgmtIp": node.mgmt.ip,
            "changed": changed,
            "stateDir": state_dir,
        },
    )
    return changed


def _bootstrap_first_primary(
    inv: Inventory,
    *,
    node,
    cimc_pass: str,
    admin_pass: str,
) -> bool:
    """Drive the shared ND-1 first-boot dialog exactly once per run state."""
    state_dir = inv.runtime.state_dir
    if is_complete(state_dir, STATE_NAME, "bootstrap"):
        log.info("skip bootstrap (state)", extra={"event": "phase.skip"})
        return False

    with Sol(node.cimc.ip, node.cimc.user, cimc_pass) as sol:
        sol.bootstrap_first_primary(
            BootstrapInputs(
                admin_password=admin_pass,
                mgmt_ip=node.mgmt.ip,
                mgmt_mask=node.mgmt.mask,
                mgmt_gateway=node.mgmt.gateway,
            ),
            timeout_s=1200,
        )
        sol.wait_for_bootstrap_complete(timeout_s=1200)
    mark(state_dir, STATE_NAME, "bootstrap", mgmtIp=node.mgmt.ip)
    return True


def _print_plan(node: object, inv: Inventory) -> None:
    n = inv.bootstrap_node
    print("DRY RUN: would perform the following on node 1 only:")
    print(f"  CIMC:           {n.cimc.ip} (user {n.cimc.user})")
    print(f"  ISO URL:        {inv.cluster.iso.url}")
    print(f"  Boot override:  UEFI: Cisco CIMC-Mapped vDVD (one-time)")
    print(f"  After install:  SOL bootstrap -> mgmt {n.mgmt.cidr} gw {n.mgmt.gateway}")
    print(f"  Then verify:    https://{n.mgmt.ip}/ reachable")
