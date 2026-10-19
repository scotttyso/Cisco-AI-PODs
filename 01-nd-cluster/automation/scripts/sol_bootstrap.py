"""SOL (Serial Over LAN) expect flow for ND node 1 first-boot.

Cisco CIMC exposes the host serial console via SSH:
    ssh admin@<cimc>      # logs into CIMC
    > connect host        # attaches to host SOL
We use paramiko to invoke a shell, send 'connect host', then run an
expect-style loop to:
  1. Send 'skip' when the installer asks about CIMC-mounted vMedia.
  2. After the OS install completes and the node is powered back on, drive
     the first-boot interactive bootstrap (admin password, mgmt IP/mask,
     gateway).

This same flow handles two distinct scenarios with no code changes:

  * Fresh install: the installer runs end-to-end, the node power-cycles,
    and the SOL stream presents the first-boot dialog.
  * Post `acs reboot factory-reset` (docs/troubleshooting.md §10): the OS
    is preserved, only the bootstrap config was wiped. The node reboots
    in ~5 min and the SOL stream presents the SAME first-boot dialog.
    Caller decides which phases to skip via state/node1.json.

The PROMPT_* regexes near the top of this module are deliberately relaxed
to tolerate first-boot wording variations across ND minor releases. If
they stop matching for your release, edit the regexes — do NOT add
release-specific code paths.

Workspace rule codeguard-1-hardcoded-credentials: passwords are passed in;
never read from source. Workspace rule codeguard-0-logging: passwords are
not logged — we mark them as 'sent **REDACTED**' in the log line.
"""
from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import paramiko

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.lib.logging import get_logger  # noqa: E402

log = get_logger(__name__)


class SolError(RuntimeError):
    pass


@dataclass(frozen=True)
class BootstrapInputs:
    admin_password: str
    mgmt_ip: str
    mgmt_mask: int
    mgmt_gateway: str


# Patterns we look for in the SOL stream. Loose enough to tolerate ND release
# wording drift; the exact prompts are confirmed at run-time and easy to tune.
PROMPT_INSTALLER_SKIP = re.compile(
    r"(use\s+the\s+previously\s+CIMC\-mounted\s+image|type\s+['\"]?skip['\"]?\s+to)",
    re.IGNORECASE,
)
PROMPT_FIRSTBOOT = re.compile(
    r"(press\s+any\s+key\s+to\s+run\s+first[-\s]?boot|first[-\s]?boot\s+setup)",
    re.IGNORECASE,
)
PROMPT_BOOTSTRAP_PRIMARY = re.compile(
    r"(press\s+enter\s+to\s+manually\s+bootstrap|bootstrap\s+your\s+first\s+primary)",
    re.IGNORECASE,
)
PROMPT_ADMIN_PASSWORD = re.compile(r"(admin\s+password)", re.IGNORECASE)
PROMPT_INSTALL_COMPLETE = re.compile(
    # Anaconda-style and ND installer-style end-of-install indicators. Any one
    # of these tells us the OS install reached its terminal state. We deliberately
    # accept several wordings because ND minor releases shift the exact phrase.
    #
    # We also include the *first-boot* indicators here so a resumed run that
    # reattaches SOL after the install finished while the orchestrator was
    # offline will return immediately (rather than waiting up to 4 hours for
    # an install-complete message that has already scrolled past).
    r"("
    r"installation\s+(complete|finished|succeeded|successful)"
    r"|install(ation)?\s+is\s+(complete|finished)"
    r"|powering\s+off"
    r"|system\s+is\s+going\s+down\s+for\s+(poweroff|reboot)"
    r"|reboot(ing)?\s+(the\s+)?system"
    r"|please\s+remove.*(installation|installer)\s+media"
    r"|press\s+any\s+key\s+to\s+(reboot|continue)"
    # post-install / first-boot landmarks (resume safety):
    r"|press\s+any\s+key\s+to\s+run\s+first[-\s]?boot"
    r"|first[-\s]?boot\s+setup"
    r"|press\s+enter\s+to\s+manually\s+bootstrap"
    r"|bootstrap\s+your\s+first\s+primary"
    r"|admin\s+password"
    r")",
    re.IGNORECASE,
)
PROMPT_REENTER_PASSWORD = re.compile(r"(re-?enter|confirm).*password", re.IGNORECASE)
PROMPT_MGMT_IP = re.compile(
    # ND 4.2.1.10 prompt is literally "IP Address/Mask: " (case-insensitive,
    # trailing colon). The other alternatives are kept for forward/backward
    # compatibility across minor releases.
    r"("
    r"ip\s+address\s*/\s*mask\s*:"
    r"|management\s+(network\s+)?ip"
    r"|ip\s+address.*management"
    r")",
    re.IGNORECASE,
)
PROMPT_MGMT_GW = re.compile(
    # ND 4.2.1.10 prompt is literally "Gateway: " (just the word, colon).
    # Word-boundary anchored so we don't match the ECHOED "Gateway: x.x.x.x"
    # in the config-review screen that follows.
    r"\bgateway\s*:\s*$",
    re.IGNORECASE | re.MULTILINE,
)
PROMPT_CONFIRM_CONFIG = re.compile(
    # ND echoes the entered config and asks to re-enter (Y) or accept (N,
    # default). Empirically: "Re-enter config?(y/N): "
    r"re-?enter\s+config\s*\?\s*\(\s*y/N\s*\)\s*:",
    re.IGNORECASE,
)
PROMPT_BOOTSTRAP_DONE = re.compile(
    # Empirical landmarks observed on ND 4.2.1.10 first boot after the
    # config-review confirmation:
    #   - "System configured successfully"      (immediate, on accept)
    #   - "Nexus Dashboard setup complete"      (within ~60s, before reboot)
    #   - "GUI is available at https://..."     (post-boot, mgmt IP up)
    # We accept any of these as success; whichever appears first wins.
    r"("
    r"nexus\s+dashboard\s+setup\s+complete"
    r"|system\s+configured\s+successfully"
    r"|gui\s+is\s+available\s+at\s+https?://"
    r"|cluster\s+ready\s+to\s+install"
    r"|bootstrap\s+(is\s+)?(complete|finished|done)"
    r")",
    re.IGNORECASE,
)


class Sol:
    """SOL session via SSH-into-CIMC + 'connect host'."""

    def __init__(self, cimc_host: str, cimc_user: str, cimc_pass: str, timeout: int = 30) -> None:
        self.cimc_host = cimc_host
        self.cimc_user = cimc_user
        self._cimc_pass = cimc_pass
        self.timeout = timeout
        self._client: paramiko.SSHClient | None = None
        self._chan: paramiko.Channel | None = None
        self._buf: str = ""

    def __enter__(self) -> "Sol":
        client = paramiko.SSHClient()
        # CIMC presents a self-signed key; AutoAddPolicy is acceptable for lab.
        # In production, use known_hosts pinning via load_system_host_keys().
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.cimc_host,
            username=self.cimc_user,
            password=self._cimc_pass,
            timeout=self.timeout,
            allow_agent=False,
            look_for_keys=False,
        )
        chan = client.invoke_shell()
        chan.settimeout(self.timeout)
        self._client = client
        self._chan = chan
        time.sleep(1.0)
        self._drain()
        log.info("sol connected", extra={"event": "sol.connect", "node": self.cimc_host})
        # Attach to host serial.
        self._send_line("connect host")
        time.sleep(1.0)
        self._drain()
        return self

    def __exit__(self, *_exc: object) -> None:
        try:
            if self._chan is not None:
                # Detach: ^x then exit (CIMC convention is Ctrl+x, q to leave host SOL).
                try:
                    self._chan.send("\x18q")  # Ctrl-X then q
                    time.sleep(0.5)
                except OSError:
                    pass
                self._chan.close()
        finally:
            if self._client is not None:
                self._client.close()
            log.info("sol disconnected", extra={"event": "sol.disconnect", "node": self.cimc_host})

    # ---------- I/O ----------

    def _drain(self) -> str:
        assert self._chan is not None
        out = ""
        while self._chan.recv_ready():
            chunk = self._chan.recv(65536).decode("utf-8", errors="replace")
            out += chunk
        if out:
            self._buf += out
        return out

    def _send_line(self, line: str, *, redact: bool = False) -> None:
        assert self._chan is not None
        self._chan.send(line + "\n")
        what = "***REDACTED***" if redact else line
        log.info("sol send", extra={"event": "sol.send", "node": self.cimc_host, "data": what})

    def _send_keys(self, keys: str) -> None:
        assert self._chan is not None
        self._chan.send(keys)
        log.info("sol send keys", extra={"event": "sol.keys", "node": self.cimc_host, "len": len(keys)})

    def _expect(self, pattern: re.Pattern[str], *, timeout_s: int,
                heartbeat_s: int = 60) -> str:
        """Block until the SOL stream matches `pattern` or `timeout_s` elapses.

        Returns the buffer contents up to and including the match.

        On long waits (notably `wait_for_install_complete`, which can take
        hours on slow vMedia transfers) the function emits a structured
        heartbeat every `heartbeat_s` seconds with the last non-blank line
        seen on serial. That gives the operator visibility without flooding
        the log: one event per heartbeat, regardless of how chatty the box
        is. The heartbeat never matches the expect pattern itself - it's
        purely observability.
        """
        idx, tail = self._expect_one_of([pattern], timeout_s=timeout_s,
                                        heartbeat_s=heartbeat_s)
        assert idx == 0
        return tail

    def _expect_one_of(self, patterns: list[re.Pattern[str]], *, timeout_s: int,
                       heartbeat_s: int = 60) -> tuple[int, str]:
        """Like _expect but accepts the first of N patterns to match.

        Returns (index_of_matched_pattern, buffer_up_to_and_including_match).

        Use this when the same logical step can be reached from more than one
        OS-side screen (e.g. resume-after-factory-reset can land us at the
        first-boot banner, the bootstrap menu, or the admin-password prompt
        depending on whether the user already tapped a key on KVM). The
        caller routes its subsequent send/expect sequence based on which
        pattern matched, so we never blindly send Enter against a screen
        that's already past the "press any key" stage.
        """
        if not patterns:
            raise ValueError("patterns must be non-empty")
        start = time.time()
        deadline = start + timeout_s
        next_heartbeat = start + heartbeat_s
        # Scan whatever is already buffered. Earliest-position match wins; on
        # ties, earlier index wins (matches Python's stable sort semantics).
        idx, tail = self._scan_buffer(patterns)
        if idx >= 0:
            return idx, tail
        while time.time() < deadline:
            chunk = self._drain()
            if chunk:
                idx, tail = self._scan_buffer(patterns)
                if idx >= 0:
                    return idx, tail
            now = time.time()
            if now >= next_heartbeat:
                # Log the alternation as a single combined string for clarity.
                combined = " | ".join(p.pattern for p in patterns)
                self._emit_heartbeat(elapsed_s=int(now - start),
                                     timeout_s=timeout_s,
                                     pattern_str=combined)
                next_heartbeat = now + heartbeat_s
            time.sleep(2.0)
        combined = " | ".join(p.pattern for p in patterns)
        raise SolError(
            f"sol expect timed out after {timeout_s}s waiting for any of: {combined!r}"
        )

    def _scan_buffer(self, patterns: list[re.Pattern[str]]) -> tuple[int, str]:
        """Return (idx, tail) for the earliest-positioned pattern match in
        self._buf, or (-1, '') if none. Consumes the buffer up to match end on
        success.
        """
        best_idx = -1
        best_end = -1
        for i, p in enumerate(patterns):
            m = p.search(self._buf)
            if m is None:
                continue
            if best_end < 0 or m.end() < best_end:
                best_end = m.end()
                best_idx = i
        if best_idx < 0:
            return -1, ""
        tail = self._buf[:best_end]
        self._buf = self._buf[best_end:]
        return best_idx, tail

    @staticmethod
    def _last_meaningful_line(buf: str) -> str:
        """Return the last non-blank, non-whitespace-only line of the buffer,
        truncated for log safety. Useful as a tail-of-screen indicator.
        """
        for line in reversed(buf.splitlines()):
            stripped = line.strip()
            if stripped:
                return stripped[-160:]
        return ""

    def _emit_heartbeat(self, *, elapsed_s: int, timeout_s: int,
                        pattern_str: str) -> None:
        last = self._last_meaningful_line(self._buf)
        log.info(
            "sol expect heartbeat",
            extra={
                "event": "sol.expect.heartbeat",
                "node": self.cimc_host,
                "elapsedS": elapsed_s,
                "timeoutS": timeout_s,
                "pattern": pattern_str,
                "lastSerialLine": last,
            },
        )

    # ---------- high-level flows ----------

    def wait_and_send_skip(self, timeout_s: int = 600) -> bool:
        """At the installer's CIMC-mounted vMedia prompt, send 'skip' (CVD step 13).

        Returns True if the prompt was found and 'skip' was sent, False if the
        prompt never appeared within ``timeout_s`` (interpreted as: the installer
        is already past that stage on a resumed run, or the prompt was already
        answered in a prior attempt).

        This is intentionally non-fatal so the orchestrator can be resumed
        idempotently: on a fresh run we expect to send skip; on a resume the
        prompt will not reappear and we should simply continue waiting for the
        installer to finish.
        """
        log.info("waiting for installer skip prompt",
                 extra={"event": "sol.expect", "node": self.cimc_host, "phase": "installer.skip",
                        "timeoutS": timeout_s})
        # A resumed SOL session may attach to a prompt that was already
        # painted before the new channel connected. Ask the console to repaint
        # before waiting; a bare CR is harmless while the installer is busy.
        self._nudge()
        try:
            self._expect(PROMPT_INSTALLER_SKIP, timeout_s=timeout_s)
        except SolError:
            log.warning("installer skip prompt not seen; assuming already past skip stage",
                        extra={"event": "sol.expect.skip-prompt-absent",
                               "node": self.cimc_host, "phase": "installer.skip"})
            return False
        self._send_line("skip")
        return True

    def _nudge(self) -> None:
        """Send a single bare CR over SOL and drain. Harmless mid-install (just
        a blank line in serial output) but essential after a resume: if nd-1 is
        sitting at an interactive prompt ("Press any key...") with no further
        output, the SOL stream stays silent until we tap the keyboard. The
        nudge forces the box to repaint whatever prompt is currently shown so
        the expect-loop has something to match on.
        """
        assert self._chan is not None
        try:
            self._chan.send("\r")
        except OSError as e:
            log.warning("sol nudge send failed",
                        extra={"event": "sol.nudge.err", "node": self.cimc_host,
                               "err": str(e)})
            return
        time.sleep(1.0)
        self._drain()
        log.info("sol nudge sent",
                 extra={"event": "sol.nudge", "node": self.cimc_host})

    def wait_for_install_complete(self, timeout_s: int = 14400) -> None:
        """Wait until the installer prints completion / power-off (CVD step 14).

        Default timeout is 4 hours: empirically, ND 4.2.1.10 streams the ~11.6
        GiB ISO through CIMC vMedia at ~1 MB/s on UCS-C SE-NODE-G2 hardware,
        which puts the typical install at ~2.5-3 hours wall time. A 4-hour
        budget leaves margin for slower disks or transient transfer dips.

        Resume safety: PROMPT_INSTALL_COMPLETE also matches first-boot
        indicators, so if the install finished while the orchestrator was
        offline we return as soon as the first-boot prompt is on screen.
        We also send a one-shot CR to repaint the current prompt; this is
        harmless mid-install but unblocks an idle "Press any key" screen.
        """
        log.info("waiting for install complete",
                 extra={"event": "sol.expect", "node": self.cimc_host,
                        "phase": "installer.complete", "timeoutS": timeout_s})
        self._nudge()
        self._expect(PROMPT_INSTALL_COMPLETE, timeout_s=timeout_s, heartbeat_s=120)

    def bootstrap_first_primary(self, inp: BootstrapInputs, timeout_s: int = 1200) -> None:
        """Drive the interactive first-boot dialog on ND 4.2.x (CVD steps 15-17).

        Empirically, ND 4.2.1.10's first-boot dialog has only FIVE prompts
        (verified via logs/firstboot-explore/ on 2026-04-25):

          1. "Admin Password: "
          2. "Re-enter Admin Password: "
          3. "IP Address/Mask: "
          4. "Gateway: "
          5. "<config echo>\n\nRe-enter config?(y/N): "

        DNS, NTP, hostname, search domain, and timezone are NOT prompted on
        the console - they're configured AFTER first boot via the wizard or
        REST (POST /v2/bootstrap/cluster). Earlier ND minors had longer
        dialogs; we deliberately keep this minimal and let the API carry the
        rest of the config.

        Resume safety (post-`acs reboot factory-reset` recovery, see
        docs/troubleshooting.md §10): the OS install is preserved but the
        bootstrap config is wiped, so on resume the box reboots and lands at
        ONE of three early screens depending on what (if anything) the
        operator tapped on KVM:

          A. PROMPT_FIRSTBOOT          ("Press any key to run first-boot")
          B. PROMPT_BOOTSTRAP_PRIMARY  ("Press Enter to manually bootstrap")
          C. PROMPT_ADMIN_PASSWORD     (skipped past A and B already)

        SOL is silent on a quiescent screen (it only forwards live output)
        and the screen never repaints by itself. So we send a one-shot CR
        nudge to force a redraw, then accept any of the three patterns and
        branch into the rest of the flow at the matched step.

        IMPORTANT: do NOT nudge once we're past the admin-password step.
        Prompts 3-5 strictly validate input - a bare CR triggers
        "error: Invalid ip address - expecting A.B.C.D" and re-prompts. The
        nudge is bounded to the entry-screen disambiguation only.
        """
        log.info("waiting for first-boot prompt",
                 extra={"event": "sol.expect", "node": self.cimc_host, "phase": "firstboot.start"})
        # Repaint whatever screen is currently shown. A bare CR is harmless on
        # any of the three entry screens: at FIRSTBOOT it satisfies the
        # "press any key" prompt; at BOOTSTRAP_PRIMARY it selects the default
        # ("manually bootstrap"); at ADMIN_PASSWORD it just blanks the input
        # field (the OS will re-prompt). Once we move past these, NO MORE
        # nudges - the IP/Mask, Gateway, and confirmation prompts strictly
        # validate input.
        self._nudge()
        idx, _ = self._expect_one_of(
            [PROMPT_FIRSTBOOT, PROMPT_BOOTSTRAP_PRIMARY, PROMPT_ADMIN_PASSWORD],
            timeout_s=timeout_s,
        )
        screen = ("firstboot", "bootstrap_primary", "admin_password")[idx]
        log.info("first-boot screen detected",
                 extra={"event": "sol.firstboot.detected",
                        "node": self.cimc_host, "screen": screen})

        if idx == 0:  # PROMPT_FIRSTBOOT
            self._send_keys("\r")  # press any key
            self._expect(PROMPT_BOOTSTRAP_PRIMARY, timeout_s=120)
            self._send_keys("\r")  # press Enter on bootstrap menu
            self._expect(PROMPT_ADMIN_PASSWORD, timeout_s=120)
        elif idx == 1:  # PROMPT_BOOTSTRAP_PRIMARY
            self._send_keys("\r")  # press Enter on bootstrap menu
            self._expect(PROMPT_ADMIN_PASSWORD, timeout_s=120)
        else:           # PROMPT_ADMIN_PASSWORD - already at password prompt
            pass

        # Prompt 1-2: admin password + reenter
        self._send_line(inp.admin_password, redact=True)
        self._expect(PROMPT_REENTER_PASSWORD, timeout_s=60)
        self._send_line(inp.admin_password, redact=True)

        # Prompt 3: "IP Address/Mask: " - slash-CIDR is accepted.
        self._expect(PROMPT_MGMT_IP, timeout_s=120)
        self._send_line(f"{inp.mgmt_ip}/{inp.mgmt_mask}")

        # Prompt 4: "Gateway: " - bare IP, no mask.
        self._expect(PROMPT_MGMT_GW, timeout_s=60)
        self._send_line(inp.mgmt_gateway)

        # Prompt 5: "Re-enter config?(y/N): " - default is N (accept). We
        # send 'n' explicitly rather than a bare CR; the OS's read loop is
        # picky about empty input on some builds, and 'n' is unambiguous.
        self._expect(PROMPT_CONFIRM_CONFIG, timeout_s=60)
        self._send_line("n")
        log.info("first-boot config accepted; OS now initializing",
                 extra={"event": "sol.firstboot.accepted",
                        "node": self.cimc_host,
                        "mgmtIp": inp.mgmt_ip,
                        "mgmtMask": inp.mgmt_mask,
                        "mgmtGw": inp.mgmt_gateway})

    def wait_for_bootstrap_complete(self, timeout_s: int = 1200) -> None:
        """Wait for any of the post-bootstrap success landmarks.

        Empirically (ND 4.2.1.10): "System configured successfully" appears
        within ~1s of the confirmation answer; "Nexus Dashboard setup
        complete" within ~30-60s; "GUI is available at https://..." appears
        only after the OS finishes the post-config reboot and the mgmt bond
        is up - typically 5-8 minutes wall-clock from the answer.

        We accept the earliest of those three. The caller can additionally
        confirm health via Redfish power-state and HTTPS reachability on the
        mgmt IP, which is a more reliable signal than scanning serial.
        """
        log.info("waiting for bootstrap complete",
                 extra={"event": "sol.expect", "node": self.cimc_host, "phase": "firstboot.done",
                        "timeoutS": timeout_s})
        self._expect(PROMPT_BOOTSTRAP_DONE, timeout_s=timeout_s, heartbeat_s=60)
