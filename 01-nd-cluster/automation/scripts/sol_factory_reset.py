"""Factory-reset an ND node via its CIMC SOL when no host network is available.

Sequence:
  1. SSH to CIMC as admin/CIMC_PASSWORD
  2. `connect host` to enter SOL
  3. Send CR to evoke login prompt
  4. Login as rescue-user/ND_ADMIN_PASSWORD
  5. Run `acs reboot factory-reset` and confirm with 'y'
  6. Disconnect (server will reboot)

Idempotent: if the OS is already at first-boot prompt instead of login, this script bails and exits 2 (the node is already fresh).
"""
from __future__ import annotations
import os, sys, time, argparse, paramiko

def log(msg):
    sys.stdout.write(msg.rstrip()+"\n"); sys.stdout.flush()

def drain(ch, secs=1.0):
    end = time.time()+secs
    buf = bytearray()
    while time.time() < end:
        if ch.recv_ready():
            buf.extend(ch.recv(65536))
        else:
            time.sleep(0.1)
    return buf.decode("utf-8", errors="replace")

def expect(ch, *needles, timeout=30):
    end = time.time()+timeout
    buf = ""
    while time.time() < end:
        if ch.recv_ready():
            buf += ch.recv(65536).decode("utf-8", errors="replace")
            for n in needles:
                if n in buf:
                    return n, buf
        else:
            time.sleep(0.2)
    return None, buf

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cimc", required=True)
    ap.add_argument("--user", default="admin")
    args = ap.parse_args()
    cimc_pw = os.environ["CIMC_PASSWORD"]
    nd_pw = os.environ["ND_ADMIN_PASSWORD"]

    log(f"[{args.cimc}] connecting to CIMC...")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(args.cimc, username=args.user, password=cimc_pw,
              timeout=15, allow_agent=False, look_for_keys=False)
    ch = c.invoke_shell()
    ch.settimeout(2.0)
    drain(ch, 1.5)

    log(f"[{args.cimc}] entering SOL...")
    ch.send(b"connect host\n")
    drain(ch, 1.5)
    # Nudge once to elicit prompt
    ch.send(b"\r")

    hit, buf = expect(ch,
        "login:",
        "Press Enter to manually bootstrap",
        "Welcome to Nexus Dashboard",
        timeout=20)
    log(f"[{args.cimc}] expect hit={hit!r}")
    if hit and "Press Enter" in hit:
        log(f"[{args.cimc}] node is ALREADY at first-boot prompt — fresh state, skipping reset")
        ch.close(); c.close()
        sys.exit(2)
    if not hit or "login:" not in hit:
        log(f"[{args.cimc}] did not see login prompt; tail buf:")
        log(buf[-400:])
        ch.close(); c.close()
        sys.exit(3)

    log(f"[{args.cimc}] logging in as rescue-user...")
    ch.send(b"rescue-user\n")
    hit, buf = expect(ch, "Password:", "password:", timeout=10)
    if not hit:
        log(f"[{args.cimc}] no password prompt; tail:"); log(buf[-400:])
        sys.exit(4)
    ch.send(nd_pw.encode()+b"\n")
    hit, buf = expect(ch, "$", "#", "incorrect", "Last login", timeout=15)
    log(f"[{args.cimc}] login result={hit!r}")
    if hit and "incorrect" in (hit or ""):
        log(f"[{args.cimc}] login incorrect"); sys.exit(5)

    log(f"[{args.cimc}] sending: acs reboot factory-reset")
    ch.send(b"acs reboot factory-reset\n")
    hit, buf = expect(ch, "(y/n)", "Proceed", "yes/no", timeout=15)
    log(f"[{args.cimc}] confirm prompt hit={hit!r}")
    ch.send(b"y\n")
    drain(ch, 5.0)
    log(f"[{args.cimc}] factory-reset confirmed; SOL session will drop as host reboots")

    # Best-effort: leave SOL — connection drop on reboot is expected
    try:
        ch.close()
    except Exception:
        pass
    try:
        c.close()
    except Exception:
        pass
    log(f"[{args.cimc}] DONE")

if __name__ == "__main__":
    main()
