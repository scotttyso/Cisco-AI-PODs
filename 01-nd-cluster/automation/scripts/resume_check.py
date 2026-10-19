"""resume_check.py -- pre-flight before resuming `python scripts/main.py node1`.

Use case: the orchestrator was killed (e.g. you closed your laptop) while
nd-1 was still installing. nd-1 keeps installing autonomously over CIMC
vMedia. By the time you come back, nd-1 may be:

  (a) still installing               -> normal resume catches up
  (b) already at the first-boot screen waiting for admin pw / mgmt IP
      -- the "install complete" message scrolled past while you were gone,
      so the orchestrator's `wait_for_install_complete` would never see it
      and would burn its 4-hour budget for nothing.

This script connects SOL once, nudges the console with a CR, and looks at
what's currently on screen. If it sees a first-boot prompt (or a "press
any key" reboot prompt) it marks the `installer_complete` state so the
next `python scripts/main.py node1` skips straight into the first-boot
phase. It is read-only against the box (just one CR) and idempotent on the
state file: it only writes the marker if it isn't already there.

Usage:
  CIMC_PASSWORD=... .venv/bin/python scripts/resume_check.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(THIS_DIR.resolve().parents[3]))

from shared.lib.inventory import load_ansible  # noqa: E402
from shared.lib.logging import get_logger  # noqa: E402
from shared.lib.state import is_complete, mark  # noqa: E402

from sol_bootstrap import (  # noqa: E402
    PROMPT_BOOTSTRAP_PRIMARY,
    PROMPT_FIRSTBOOT,
    PROMPT_INSTALL_COMPLETE,
    Sol,
)

log = get_logger(__name__)

STATE_NAME = "node1"

# How long to listen on SOL after the nudge before deciding "still installing".
LISTEN_S = 30


def main() -> int:
    inventory_path = THIS_DIR.parents[2] / "inventories" / "lab" / "inventory.yml"
    inv = load_ansible(inventory_path)
    nd1 = inv.bootstrap_node
    cimc_pw = os.environ.get(nd1.cimc.pass_ref)
    if not cimc_pw:
        print(f"ERROR: {nd1.cimc.pass_ref} env var not set.", file=sys.stderr)
        return 2

    state_dir = inv.runtime.state_dir

    if is_complete(state_dir, STATE_NAME, "installer_complete"):
        print("state already shows installer_complete; nothing to do.")
        print("just run:  .venv/bin/python scripts/main.py node1")
        return 0

    print(f"connecting SOL to {nd1.cimc.ip} for {LISTEN_S}s of observation ...")
    seen_chunks: list[str] = []

    with Sol(nd1.cimc.ip, nd1.cimc.user, cimc_pw) as sol:
        # One CR to wake the console; many installer/firstboot screens only
        # repaint on input.
        sol._send_keys("\r")  # noqa: SLF001  -- intentional internal nudge
        deadline = time.time() + LISTEN_S
        while time.time() < deadline:
            chunk = sol._chan.recv(4096) if sol._chan.recv_ready() else b""  # noqa: SLF001
            if chunk:
                text = chunk.decode("utf-8", errors="replace")
                seen_chunks.append(text)
                # Print live-ish so the operator can see what's happening.
                sys.stdout.write(text)
                sys.stdout.flush()
            else:
                time.sleep(0.5)

    blob = "".join(seen_chunks)
    saw_firstboot = bool(
        PROMPT_FIRSTBOOT.search(blob) or PROMPT_BOOTSTRAP_PRIMARY.search(blob)
    )
    saw_install_complete = bool(PROMPT_INSTALL_COMPLETE.search(blob))

    print("\n--- resume_check verdict ---")
    print(f"  saw first-boot prompt        : {saw_firstboot}")
    print(f"  saw install-complete prompt  : {saw_install_complete}")
    print(f"  bytes captured               : {len(blob)}")

    if saw_firstboot or saw_install_complete:
        # Mark both sub-markers so install_node1 skips both wait_and_send_skip
        # and wait_for_install_complete on resume.
        if not is_complete(state_dir, STATE_NAME, "installer_skip_sent"):
            mark(state_dir, STATE_NAME, "installer_skip_sent",
                 result="absent_assumed_already_skipped")
        mark(state_dir, STATE_NAME, "installer_complete",
             status="complete", source="resume_check.py",
             evidence=("firstboot_prompt" if saw_firstboot else "install_complete_msg"))
        print("\n  -> marked installer_complete in state.")
        print("  -> resume with:  .venv/bin/python scripts/main.py node1")
        return 0

    # Heuristic: if we saw curl progress lines, the OS install is still
    # downloading the ISO. That's the normal mid-install case.
    looks_like_install_in_progress = any(
        s in blob for s in (
            "curl", "100 ", "M    0", "Time  Time", "Total    %",
            "anaconda", "Installing", "Performing post-install",
        )
    )
    print(f"  install still in progress?   : {looks_like_install_in_progress}")
    print("\n  -> NOT marking state. Just resume normally:")
    print("     .venv/bin/python scripts/main.py node1")
    print("     (the orchestrator's 4-hour wait will catch the prompt as it appears.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
