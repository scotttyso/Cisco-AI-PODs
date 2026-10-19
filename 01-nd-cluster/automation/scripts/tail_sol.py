"""Read-only SOL tail helper (peek-with-nudge).

Connects to a CIMC over SSH, attaches to host SOL, optionally sends one
CR to repaint the current prompt (the "nudge"), drains output for a fixed
window, and prints the captured serial bytes. Useful for:

  * Confirming what the ND installer is currently displaying so we can tune
    the prompt regexes in sol_bootstrap.py before re-running install_node1.
  * Spot-checking the box state without holding a long-lived session.
  * Replacing the "ask a human to KVM in" reflex with a 12-second
    programmatic check (see docs/troubleshooting.md §11).

The nudge (one CR) is on by default because SOL only forwards live console
bytes - it does not replay history. Without a nudge, a quiescent console
shows nothing but the CIMC banner. The nudge causes most prompts to repaint.
However: prompts that strictly validate input (e.g. ND first-boot's IP
Address/Mask: and Gateway: prompts) treat empty input as an answer and emit
a validator error. Pass --no-nudge in those situations and just wait the
full --seconds window. See docs/troubleshooting.md §13.

Usage:
    # Direct (CIMC IP — example uses nd-1's CIMC at 198.51.100.87, see
    # inventories/<environment>/host_vars/nd-*.yml for current values):
    python -u scripts/tail_sol.py --cimc 198.51.100.87 --seconds 12
    python -u scripts/tail_sol.py --cimc 198.51.100.87 --seconds 30 --out /tmp/nd1.sol
    python -u scripts/tail_sol.py --cimc 198.51.100.87 --seconds 30 --no-nudge

    # Or via main.py orchestrator (resolves --node from inventory):
    python -u scripts/main.py tail-sol --node nd-1 --seconds 12

Env:
    CIMC_PASSWORD  Required. CIMC `admin` password.

Exit codes:
    0 success
    2 invalid arguments / missing env
    3 SSH/SOL failure
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import paramiko

# Workspace rule codeguard-1-hardcoded-credentials: read password from env only.
ENV_PASSWORD = "CIMC_PASSWORD"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Read-only SOL tail for a CIMC host.")
    p.add_argument("--cimc", required=True, help="CIMC management IP")
    p.add_argument("--user", default="admin", help="CIMC user (default: admin)")
    p.add_argument("--seconds", type=int, default=30,
                   help="How long to drain the SOL stream (default: 30)")
    p.add_argument("--out", type=Path, default=None,
                   help="Optional file to also write the captured stream to")
    p.add_argument("--connect-timeout", type=int, default=15)
    nudge_grp = p.add_mutually_exclusive_group()
    nudge_grp.add_argument("--nudge", dest="nudge", action="store_true", default=True,
                           help="Send one CR after attach to repaint quiescent prompts (default).")
    nudge_grp.add_argument("--no-nudge", dest="nudge", action="store_false",
                           help="Do NOT send a CR after attach. Use when the OS is at a "
                                "strictly-validating prompt where empty input would error "
                                "(e.g. ND first-boot IP/Mask or Gateway). See "
                                "docs/troubleshooting.md \u00a713.")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    pw = os.environ.get(ENV_PASSWORD)
    if not pw:
        print(f"ERROR: ${ENV_PASSWORD} is not set", file=sys.stderr)
        return 2

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=args.cimc,
            username=args.user,
            password=pw,
            timeout=args.connect_timeout,
            allow_agent=False,
            look_for_keys=False,
        )
    except (paramiko.SSHException, OSError) as e:
        print(f"ERROR: SSH connect to {args.cimc}: {e}", file=sys.stderr)
        return 3

    captured = bytearray()
    try:
        chan = client.invoke_shell()
        chan.settimeout(2.0)
        time.sleep(1.0)
        # Drain CIMC banner.
        while chan.recv_ready():
            chan.recv(65536)
        # Attach to host serial.
        chan.send(b"connect host\n")
        time.sleep(1.0)
        # Drain the "connect host" echo + CIMC's "Press Ctrl+x to Exit the
        # session" banner so the captured window only shows host output.
        while chan.recv_ready():
            chan.recv(65536)
        # Optional one-shot CR nudge to repaint any quiescent prompt. Off
        # explicitly via --no-nudge for prompts that strictly validate input
        # (see module docstring + docs/troubleshooting.md \u00a713).
        if args.nudge:
            try:
                chan.send(b"\r")
                time.sleep(0.5)
            except OSError:
                pass
        deadline = time.time() + args.seconds
        last_print = time.time()
        while time.time() < deadline:
            if chan.recv_ready():
                chunk = chan.recv(65536)
                if chunk:
                    captured.extend(chunk)
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.buffer.flush()
                    last_print = time.time()
            else:
                # Light heartbeat to stderr so the operator knows we're alive
                # even when the box is silent (which is itself a useful signal).
                if time.time() - last_print > 5:
                    print(".", end="", file=sys.stderr, flush=True)
                    last_print = time.time()
                time.sleep(0.5)
        # Detach cleanly: CIMC convention is Ctrl+X then q.
        try:
            chan.send(b"\x18q")
            time.sleep(0.5)
        except OSError:
            pass
        chan.close()
    except paramiko.SSHException as e:
        print(f"ERROR: SOL channel error: {e}", file=sys.stderr)
        return 3
    finally:
        client.close()

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(bytes(captured))
        print(f"\n[captured {len(captured)} bytes -> {args.out}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
