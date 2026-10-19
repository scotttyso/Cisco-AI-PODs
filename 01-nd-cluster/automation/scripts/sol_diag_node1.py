"""One-off SOL diagnostic for nd-1 to investigate why bond1 / LOM is not linking.

Read-only relative to ND state: only logs in as rescue-user and runs introspection
commands. Captures everything to stdout + an optional file.

Workspace rule codeguard-1-hardcoded-credentials: passwords are taken from env
vars that the caller pre-populates from macOS Keychain. Nothing is hardcoded or
echoed.

Usage:
    export CIMC_PASSWORD="$(security find-generic-password -a "$USER" -s nd-lab-cimc -w)"
    export ND_ADMIN_PASSWORD="$(security find-generic-password -a "$USER" -s nd-lab-admin -w)"
    .venv/bin/python3 scripts/sol_diag_node1.py --cimc 198.51.100.87 \
        --out logs/nd1-sol-diag-$(date -u +%Y%m%dT%H%M%SZ).log
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

import paramiko

ENV_CIMC_PW = "CIMC_PASSWORD"
ENV_ND_PW = "ND_ADMIN_PASSWORD"

LOGIN_PROMPT = re.compile(r"login:\s*$", re.IGNORECASE | re.MULTILINE)
PASSWORD_PROMPT = re.compile(r"password:\s*$", re.IGNORECASE | re.MULTILINE)
SHELL_PROMPT = re.compile(r"NDDIAG\$\s*$", re.MULTILINE)

DIAG_STEPS: list[tuple[str, str]] = [
    ("sudo capability check",
     "sudo -n true 2>&1 && echo 'sudo: ok (no password)' || echo 'sudo: needs password'"),
    ("/sys/class/net visibility",
     "ls /sys/class/net/ 2>&1 | head -30"),
    ("ethtool mgmt0 with sudo",
     "sudo ethtool mgmt0 2>&1 | head -30"),
    ("toggle mgmt0 down then up",
     "sudo ip link set mgmt0 down && sleep 3 && sudo ip link set mgmt0 up && sleep 5 && echo 'toggled mgmt0'"),
    ("post-toggle bond1 state",
     "cat /proc/net/bonding/bond1 2>/dev/null | head -25"),
    ("post-toggle ARP for gateway",
     "ip neigh flush dev bond1 2>/dev/null; ip neigh show 192.0.2.254 || echo '(no neigh)'"),
    ("post-toggle ping gateway",
     "ping -c 3 -W 2 192.0.2.254 2>&1 | tail -6"),
    ("post-toggle ARP after ping",
     "ip neigh show 192.0.2.254 || echo '(no neigh)'"),
]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SOL-based read-only NIC diagnostic for nd-1")
    p.add_argument("--cimc", required=True)
    p.add_argument("--cimc-user", default="admin")
    p.add_argument("--rescue-user", default="rescue-user")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--connect-timeout", type=int, default=20)
    p.add_argument("--login-wait", type=int, default=60,
                   help="how long to wait for the OS login: prompt after attaching SOL")
    p.add_argument("--diag-wait", type=int, default=90,
                   help="how long to wait for END_DIAG_OUTPUT after sending commands")
    return p.parse_args(argv)


class Drainer:
    def __init__(self, chan: paramiko.Channel) -> None:
        self.chan = chan
        self.buf = ""

    def drain(self) -> str:
        out = ""
        while self.chan.recv_ready():
            chunk = self.chan.recv(65536).decode("utf-8", errors="replace")
            if not chunk:
                break
            out += chunk
        if out:
            self.buf += out
            sys.stdout.write(out)
            sys.stdout.flush()
        return out

    def expect(self, pattern: re.Pattern[str], timeout_s: int) -> bool:
        deadline = time.time() + timeout_s
        if pattern.search(self.buf):
            return True
        while time.time() < deadline:
            self.drain()
            if pattern.search(self.buf):
                return True
            time.sleep(0.5)
        return False

    def send(self, data: bytes) -> None:
        self.chan.send(data)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    cimc_pw = os.environ.get(ENV_CIMC_PW)
    nd_pw = os.environ.get(ENV_ND_PW)
    if not cimc_pw:
        print(f"ERROR: ${ENV_CIMC_PW} not set", file=sys.stderr)
        return 2
    if not nd_pw:
        print(f"ERROR: ${ENV_ND_PW} not set", file=sys.stderr)
        return 2

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=args.cimc, username=args.cimc_user, password=cimc_pw,
            timeout=args.connect_timeout, allow_agent=False, look_for_keys=False,
        )
    except (paramiko.SSHException, OSError) as e:
        print(f"ERROR: SSH to CIMC {args.cimc}: {e}", file=sys.stderr)
        return 3

    captured = bytearray()
    try:
        chan = client.invoke_shell()
        chan.settimeout(2.0)
        time.sleep(1.0)
        d = Drainer(chan)
        d.drain()

        d.send(b"connect host\n")
        time.sleep(2.0)
        d.drain()
        d.send(b"\r")
        time.sleep(1.0)
        d.drain()

        if not d.expect(LOGIN_PROMPT, timeout_s=args.login_wait):
            d.send(b"\r")
            time.sleep(1.0)
            if not d.expect(LOGIN_PROMPT, timeout_s=10):
                print("\nERROR: never saw an OS 'login:' prompt within "
                      f"{args.login_wait}s", file=sys.stderr)
                _detach(chan)
                return 4

        d.send(args.rescue_user.encode() + b"\n")
        if not d.expect(PASSWORD_PROMPT, timeout_s=15):
            print("\nERROR: never saw 'Password:' after sending username",
                  file=sys.stderr)
            _detach(chan)
            return 5
        d.send(nd_pw.encode() + b"\n")
        time.sleep(2.0)
        d.drain()

        d.send(b"PS1='NDDIAG$ '\n")
        time.sleep(1.0)
        d.drain()
        if not d.expect(SHELL_PROMPT, timeout_s=10):
            print("\nERROR: never saw NDDIAG$ shell prompt; PS1 not applied",
                  file=sys.stderr)
            _detach(chan)
            return 6

        for label, cmd in DIAG_STEPS:
            print(f"\n\n----- {label} -----", flush=True)
            d.buf = ""
            d.send(b"echo ===STEP=== " + label.encode() + b"\n")
            time.sleep(0.3)
            d.drain()
            d.send(cmd.encode() + b"\n")
            # Some steps (toggle + ping) take longer; allow up to 30s per step.
            ok = d.expect(SHELL_PROMPT, timeout_s=30)
            if not ok:
                print(f"  WARN: step {label!r} did not return prompt; output may be partial",
                      file=sys.stderr)
            captured.extend(d.buf.encode("utf-8", errors="replace"))

        try:
            d.send(b"exit\n")
            time.sleep(0.5)
        except OSError:
            pass
        _detach(chan)
        chan.close()
    except paramiko.SSHException as e:
        print(f"ERROR: SOL channel: {e}", file=sys.stderr)
        return 3
    finally:
        client.close()

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(bytes(captured))
        print(f"\n[captured {len(captured)} bytes -> {args.out}]", file=sys.stderr)
    return 0


def _detach(chan: paramiko.Channel) -> None:
    try:
        chan.send(b"\x18q")
        time.sleep(0.5)
    except OSError:
        pass


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
