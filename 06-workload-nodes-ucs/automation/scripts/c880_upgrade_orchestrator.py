#!/usr/bin/env python3
"""C880 chapter workflow: offline plan, strict downgrade check, and in-memory OOB upgrade.

This module provides:
1. Offline deployment planning for C880-3 and C880-4.
2. Airtight component version parsing and downgrade prohibition (zero-tolerance).
3. Supervised, credential-safe in-memory OOB firmware execution driving the vendor
   upgrade engine without exposing passwords in the OS process table or CLI args.
4. Pre- and post-upgrade Redfish health verification against pre-window baselines.
"""

import argparse
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import re
import signal
import sys
import tarfile
import tempfile
import threading
import time
import uuid
import yaml

from plan_c880_deployment import build_plan
from c880_health_gate import make_baseline
from probe_c880_health_counts import probe_gate
from probe_c880_readonly import (
    MIN_REQUEST_SPACING_SECONDS,
    RedfishReader,
    _read_vault_password,
)
from c880_oob_replay import TIMEOUTS, POLL_SECONDS, INTER_COMPONENT_SECONDS
from probe_c880_huu_postcheck import (
    audit_huu_firmware,
    audit_settings_persistence,
    _read_host_spec,
    _read_shared_spec,
)

HOSTS = ("ucs-c880-1", "ucs-c880-2", "ucs-c880-3", "ucs-c880-4")
VALIDATED_REFERENCE_HOSTS = ("ucs-c880-3", "ucs-c880-4")
REQUIRED_CORE_COMPONENTS = ("BMC", "BIOS", "GPU")
PROCEDURES = (
    ("management", 1, "verify_existing_or_supervised_change"),
    ("console", 2, "verify_existing_or_supervised_change"),
    ("hardware_health", 3, "automated_read_only"),
    ("oob_firmware", 4, "automated_in_memory_safe"),
    ("huu_firmware", 5, "supervised_vkvm_candidate"),
    ("bios_nic_mode", 6, "verify_existing_or_supervised_change"),
    ("independent_postcheck", 6, "automated_read_only"),
)

DEFAULT_RUN_LOG_ROOT = Path(__file__).resolve().parents[1] / "run-logs"
RAW_LOG_NAME = "raw.log"
RUN_TELEMETRY_NAME = "telemetry.json"
RUN_STATUS_NAME = "status.json"
LATEST_LINK_NAME = "latest"
HEARTBEAT_INTERVAL_SECONDS = 10
RUN_RETENTION_COUNT = 20

DEFAULT_BUNDLE_PATH = Path(
    "/Users/asharma/Downloads/LAB-TEMP/AIPOD-INF/C880/ucs-c880a-m8-4.0.2.260009.tar.gz"
)
DEFAULT_SCRIPT_PATH = Path(
    "/Users/asharma/Downloads/LAB-TEMP/AIPOD-INF/C880/ucs-c880a-m8-upgrade-script-v1.2/ucs-c880a-m8-upgrade-v1.2.py"
)


class RunLog:
    """Collects orchestrator and vendor log lines for one invocation.

    Lines are always held in memory for the telemetry console drawer. When a run
    directory is configured they are also appended to raw.log and flushed per
    line, so a supervising process can tail a firmware upgrade while it runs
    instead of waiting for the single end-of-run JSON document.
    """

    def __init__(self, run_dir=None, secrets=()):
        self.lines = []
        self.run_dir = Path(run_dir) if run_dir else None
        self.raw_log_path = None
        self._secrets = [str(s) for s in secrets if s]
        self._handle = None
        if self.run_dir:
            self.run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.run_dir, 0o700)
            self.raw_log_path = self.run_dir / RAW_LOG_NAME
            fd = os.open(self.raw_log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            self._handle = os.fdopen(fd, "a", encoding="utf-8")
            os.chmod(self.raw_log_path, 0o600)

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        self.close()

    def add_secret(self, secret):
        if secret:
            value = str(secret)
            if value not in self._secrets:
                self._secrets.append(value)

    def scrub(self, text):
        for secret in self._secrets:
            text = text.replace(secret, "[REDACTED_SECRET]")
        return text

    def __call__(self, msg):
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        line = f"[{ts}] {self.scrub(str(msg))}"
        self.lines.append(line)
        if self._handle:
            self._handle.write(line + "\n")
            self._handle.flush()
        return line

    def close(self):
        if self._handle:
            self._handle.close()
            self._handle = None


class RunLogStream(io.TextIOBase):
    """Route vendor stdout/stderr lines through the same scrubbed run logger."""

    def __init__(self, run_log, prefix=""):
        self.run_log = run_log
        self.prefix = prefix
        self.pending = ""

    def write(self, text):
        self.pending += str(text)
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            if line:
                self.run_log(f"{self.prefix}{line}")
        return len(text)

    def flush(self):
        if self.pending:
            self.run_log(f"{self.prefix}{self.pending}")
            self.pending = ""


@contextmanager
def capture_vendor_output(run_log):
    stdout_stream = RunLogStream(run_log, "[vendor] ")
    stderr_stream = RunLogStream(run_log, "[vendor stderr] ")
    handler = logging.Handler()
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    handler.emit = lambda record: run_log(f"[vendor log] {handler.format(record)}")
    root_logger = logging.getLogger()
    previous_level = root_logger.level
    root_logger.setLevel(logging.NOTSET)
    root_logger.addHandler(handler)
    try:
        with redirect_stdout(stdout_stream), redirect_stderr(stderr_stream):
            yield
    finally:
        stdout_stream.flush()
        stderr_stream.flush()
        root_logger.removeHandler(handler)
        root_logger.setLevel(previous_level)


def _atomic_json_write(path, payload, *, private_parent=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700 if private_parent else 0o777)
    if private_parent:
        os.chmod(path.parent, 0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def write_run_status(run_dir, state, exit_code=None, error=None, started_utc=None,
                     heartbeat_utc=None, scrubber=None):
    """Record the run's lifecycle state so an abnormal exit is distinguishable.

    telemetry.json is a result payload and may be absent on operational errors;
    status.json is written `running` up front and
    rewritten with a terminal state on every exit path, including signals.

    A SIGKILL or power loss leaves `running` behind. Readers use heartbeat_utc
    expiry, rather than a progress value or PID alone, to identify stale runs.
    """
    if not run_dir:
        return None
    now = datetime.now(timezone.utc).isoformat()
    safe_error = scrubber.scrub(error) if error and scrubber else error
    payload = {
        "run_id": Path(run_dir).name,
        "state": state,
        "pid": os.getpid(),
        "started_utc": started_utc,
        "ended_utc": None if state == "running" else now,
        "heartbeat_utc": heartbeat_utc or now,
        "exit_code": exit_code,
        "error": safe_error,
    }
    _atomic_json_write(Path(run_dir) / RUN_STATUS_NAME, payload)
    return payload


def run_state_for_exit(exit_code, raised=False):
    """Only a clean zero exit is a successful run lifecycle state."""
    return "succeeded" if exit_code == 0 and not raised else "failed"


def make_run_dir(root, host, action):
    """Create a timestamped run directory and repoint the `latest` symlink at it.

    The symlink gives a supervising process one stable path to read without
    having to sort directory names.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    base = f"{stamp}-{host}-{action}"
    run_dir = root / base
    try:
        run_dir.mkdir(mode=0o700)
    except FileExistsError:
        run_dir = root / f"{base}-{uuid.uuid4().hex[:8]}"
        run_dir.mkdir(mode=0o700)
    os.chmod(run_dir, 0o700)
    link = root / LATEST_LINK_NAME
    temp_link = root / f".{LATEST_LINK_NAME}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    try:
        temp_link.symlink_to(run_dir.name)
        os.replace(temp_link, link)
    except OSError:
        # A missing convenience symlink must never fail a firmware run.
        try:
            temp_link.unlink()
        except OSError:
            pass
    return run_dir


def prune_completed_runs(root, host, keep=RUN_RETENTION_COUNT):
    """Keep the newest completed runs for one host; preserve running/unknown runs."""
    root = Path(root)
    if not root.is_dir():
        return []
    completed = []
    for candidate in root.iterdir():
        if candidate.is_symlink() or not candidate.is_dir() or f"-{host}-" not in candidate.name:
            continue
        try:
            status = json.loads((candidate / RUN_STATUS_NAME).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if status.get("state") in ("succeeded", "failed"):
            completed.append(candidate)
    completed.sort(key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True)
    removed = []
    for stale in completed[max(0, keep):]:
        # Never recursively follow symlinks while removing a retained run.
        for item in stale.iterdir():
            if item.is_symlink() or item.is_file():
                item.unlink()
            elif item.is_dir():
                import shutil
                shutil.rmtree(item)
        stale.rmdir()
        removed.append(stale)
    return removed


class RunStatusHeartbeat:
    def __init__(self, run_dir, started_utc, scrubber=None):
        self.run_dir = run_dir
        self.started_utc = started_utc
        self.scrubber = scrubber
        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        if self.run_dir:
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def _run(self):
        while not self.stop_event.wait(HEARTBEAT_INTERVAL_SECONDS):
            write_run_status(
                self.run_dir, "running", started_utc=self.started_utc,
                heartbeat_utc=datetime.now(timezone.utc).isoformat(), scrubber=self.scrubber,
            )

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join()


class DowngradeBlockedError(RuntimeError):
    """Raised when running firmware is newer than target, strictly forbidding rollback."""
    pass


class UnverifiedVersionError(ValueError):
    """Raised when version formatting cannot be verified unequivocally."""
    pass


def parse_component_version(component, value):
    """Parse component version strings into numeric tuples for strict comparison.
    
    Supports:
    - BMC: 4.0(2.260022), 4.0.2.260022
    - BIOS: 4.0.2.67
    - GPU: 97.10.7E.00.03-G540.0216.00.03
    - CPLD: 0.1.0.1, 0.1.2.8, 0.1.0.7
    - EROT: 4.0.15
    """
    if not isinstance(value, str):
        return None
    val = value.strip()
    if not val or val.upper() in ("N/A", "UNKNOWN", "NONE"):
        return None
    
    if component == "BMC":
        m = re.fullmatch(r"(\d+)\.(\d+)\((\d+)\.(\d+)\)", val)
        if m:
            return tuple(int(x) for x in m.groups())
        m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)\.(\d+)", val)
        if m:
            return tuple(int(x) for x in m.groups())
    elif component == "GPU":
        m = re.fullmatch(r"([0-9A-Fa-f]{2}(?:\.[0-9A-Fa-f]{2}){4})-G(\d+)\.(\d+)\.(\d+)\.(\d+)", val)
        if m:
            hex_part = tuple(int(x, 16) for x in m.group(1).split("."))
            g_part = tuple(int(x) for x in m.groups()[1:])
            return hex_part + g_part
    elif component.startswith("EROT"):
        m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", val)
        if m:
            return tuple(int(x) for x in m.groups())
        m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)\.(\d+)", val)
        if m:
            return tuple(int(x) for x in m.groups())
    else:  # BIOS, CPLDs, and standard dotted components
        m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)\.(\d+)", val)
        if m:
            return tuple(int(x) for x in m.groups())
        m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", val)
        if m:
            return tuple(int(x) for x in m.groups())
    return None


def check_downgrade_safety(components_info, required_components=None):
    """Strict downgrade prevention across all components.
    
    Zero-tolerance: if running > packaged on ANY component, execution is blocked.
    If running == packaged on ALL components, no flash is attempted (idempotent skip).
    If running is unparseable or unrecognized, execution fails closed.
    If required_components is specified, verifies that all listed components are present
    in components_info to prevent partial discovery from evaluating as ALL_ALREADY_TARGET.
    """
    if not components_info or not isinstance(components_info, dict):
        return {
            "decision": "BLOCKED_NO_COMPONENTS",
            "is_safe": False,
            "reason": "Component inventory is empty or invalid.",
            "components": {},
        }

    if required_components:
        missing = [c for c in required_components if c not in components_info]
        if missing:
            return {
                "decision": "BLOCKED_INCOMPLETE_INVENTORY",
                "is_safe": False,
                "missing_components": missing,
                "components": {},
                "reason": f"Inventory discovery incomplete; missing required core components: {', '.join(missing)}.",
            }
    
    results = {}
    downgrades = []
    unverified = []
    upgradable = []

    for comp, versions in components_info.items():
        if not isinstance(versions, (tuple, list)) or len(versions) != 2:
            results[comp] = {"status": "BLOCKED_MALFORMED", "versions": versions}
            unverified.append(comp)
            continue
        
        running_str, packaged_str = str(versions[0]), str(versions[1])
        running_t = parse_component_version(comp, running_str)
        packaged_t = parse_component_version(comp, packaged_str)

        if running_t is None or packaged_t is None:
            results[comp] = {
                "running": running_str, "packaged": packaged_str,
                "status": "BLOCKED_VERSION_UNVERIFIED"
            }
            unverified.append(comp)
        elif running_t > packaged_t:
            results[comp] = {
                "running": running_str, "packaged": packaged_str,
                "status": "BLOCKED_DOWNGRADE"
            }
            downgrades.append(comp)
        elif running_t == packaged_t:
            results[comp] = {
                "running": running_str, "packaged": packaged_str,
                "status": "SKIP_ALREADY_TARGET"
            }
        else:
            results[comp] = {
                "running": running_str, "packaged": packaged_str,
                "status": "UPGRADE_REQUIRED"
            }
            upgradable.append(comp)

    if downgrades:
        return {
            "decision": "BLOCKED_DOWNGRADE",
            "is_safe": False,
            "blocked_components": downgrades,
            "components": results,
            "reason": f"Downgrade strictly prohibited: {', '.join(downgrades)} running newer firmware than bundle.",
        }
    if unverified:
        return {
            "decision": "BLOCKED_VERSION_UNVERIFIED",
            "is_safe": False,
            "unverified_components": unverified,
            "components": results,
            "reason": f"Version strings could not be verified unequivocally for: {', '.join(unverified)}.",
        }
    if not upgradable:
        return {
            "decision": "ALL_ALREADY_TARGET",
            "is_safe": True,
            "components": results,
            "reason": "All discovered components match target version. Zero flash/reboot operations required.",
        }
    return {
        "decision": "UPGRADE_CANDIDATE",
        "is_safe": True,
        "components": results,
        "upgradable_components": upgradable,
        "reason": f"Components to update: {', '.join(upgradable)}.",
    }


def generate_component_table(components_dict, required_components=REQUIRED_CORE_COMPONENTS):
    """Generate structured table rows with badge metadata for web UI rendering.

    Each row contains:
    - component: Name of component (e.g. BMC, BIOS, GPU, CPLD)
    - running_version: Current running firmware version
    - target_version: Packaged firmware version in bundle
    - status: Internal status token (e.g. UPGRADE_REQUIRED, SKIP_ALREADY_TARGET, BLOCKED_DOWNGRADE)
    - badge: Visual styling dict with label and color variant (success, warning, danger, secondary)
    - action: FLASH, SKIP, ABORT, PLANNED, UNKNOWN
    - critical: Boolean indicating if component is part of core health baseline
    """
    table = []
    status_map = {
        "UPGRADE_REQUIRED": {
            "label": "Upgrade Required",
            "variant": "warning",
            "action": "FLASH",
        },
        "SKIP_ALREADY_TARGET": {
            "label": "Up to Date",
            "variant": "success",
            "action": "SKIP",
        },
        "BLOCKED_DOWNGRADE": {
            "label": "Downgrade Prohibited",
            "variant": "danger",
            "action": "ABORT",
        },
        "BLOCKED_VERSION_UNVERIFIED": {
            "label": "Version Unverified",
            "variant": "secondary",
            "action": "ABORT",
        },
        "BLOCKED_MALFORMED": {
            "label": "Malformed Spec",
            "variant": "danger",
            "action": "ABORT",
        },
        "OFFLINE_PLANNED": {
            "label": "Target Baseline",
            "variant": "info",
            "action": "PLANNED",
        },
    }

    for comp, data in components_dict.items():
        st = data.get("status", "BLOCKED_VERSION_UNVERIFIED")
        meta = status_map.get(
            st,
            {
                "label": st,
                "variant": "secondary",
                "action": "UNKNOWN",
            },
        )
        table.append(
            {
                "component": comp,
                "running_version": str(data.get("running", "N/A")),
                "target_version": str(data.get("packaged", "N/A")),
                "status": st,
                "badge": {
                    "label": meta["label"],
                    "variant": meta["variant"],
                },
                "action": meta["action"],
                "critical": comp in required_components,
            }
        )

    def sort_key(item):
        is_core = 0 if item["component"] in required_components else 1
        return (is_core, item["component"])

    table.sort(key=sort_key)
    return table


def build_structured_telemetry(
    host,
    phase,
    components_dict=None,
    safety_decision="UNKNOWN",
    reason="",
    pre_health=None,
    post_health=None,
    settings_persistence=None,
    log_lines=None,
    power_cycle_required=False,
    required_components=REQUIRED_CORE_COMPONENTS,
):
    """Build structured telemetry payload for two-tier web UI pattern."""
    components_table = generate_component_table(
        components_dict or {}, required_components=required_components
    )

    total = len(components_table)
    upgradable_count = sum(1 for c in components_table if c["action"] == "FLASH")
    up_to_date_count = sum(1 for c in components_table if c["action"] == "SKIP")
    blocked_count = sum(1 for c in components_table if c["action"] == "ABORT")

    decision_badges = {
        "ALL_ALREADY_TARGET": {"label": "Up to Date", "variant": "success"},
        "UPGRADE_CANDIDATE": {"label": "Upgrade Ready", "variant": "primary"},
        "BLOCKED_DOWNGRADE": {"label": "Downgrade Blocked", "variant": "danger"},
        "BLOCKED_VERSION_UNVERIFIED": {"label": "Unverified Version", "variant": "warning"},
        "BLOCKED_INCOMPLETE_INVENTORY": {"label": "Incomplete Inventory", "variant": "danger"},
        "OFFLINE_PLAN": {"label": "Planned Baseline", "variant": "info"},
        "PERSISTENCE_AUDIT": {
            "label": (
                "Persistence Verified"
                if (settings_persistence and settings_persistence.get("all_passed"))
                else "Persistence Failed"
            ),
            "variant": (
                "success"
                if (settings_persistence and settings_persistence.get("all_passed"))
                else "danger"
            ),
        },
    }
    badge = decision_badges.get(
        safety_decision, {"label": safety_decision, "variant": "secondary"}
    )

    lines = list(log_lines or [])

    return {
        "schema_version": "1.0",
        "telemetry_type": "c880_upgrade_telemetry",
        "host": host,
        "phase": phase,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "decision": safety_decision,
            "badge": badge,
            "reason": reason,
            "total_components": total,
            "upgradable_count": upgradable_count,
            "up_to_date_count": up_to_date_count,
            "blocked_count": blocked_count,
            "power_cycle_required": power_cycle_required,
            "pre_health": pre_health,
            "post_health": post_health,
        },
        "components_table": components_table,
        "settings_persistence": settings_persistence,
        "console_drawer": {
            "title": "Raw Orchestrator & Vendor Logs",
            "total_lines": len(lines),
            "lines": lines,
            "collapsible": True,
            "default_expanded": False,
        },
    }


def _host_checks(inventory_dir, host):
    if host not in HOSTS:
        raise ValueError(f"Host {host} is outside C880 workflow")
    matches = [item for item in build_plan(inventory_dir)["hosts"]
               if item["host"] == host]
    if len(matches) != 1:
        raise ValueError(f"Selected C880 host {host} inventory is missing or duplicated")
    return matches[0]["inventory_checks"]


def offline_plan(inventory_dir, host):
    """Plan C880 host without connecting to BMC or using credentials."""
    checks = _host_checks(inventory_dir, host)
    planned_components = {
        "BMC": {"running": "Planned", "packaged": "4.0(2.260022)", "status": "OFFLINE_PLANNED"},
        "BIOS": {"running": "Planned", "packaged": "4.0.2.67", "status": "OFFLINE_PLANNED"},
        "GPU": {"running": "Planned", "packaged": "97.10.7E.00.03-G540.0216.00.03", "status": "OFFLINE_PLANNED"},
        "CPLD": {"running": "Planned", "packaged": "0.1.0.1", "status": "OFFLINE_PLANNED"},
        "EROT": {"running": "Planned", "packaged": "4.0.15", "status": "OFFLINE_PLANNED"},
    }
    telemetry = build_structured_telemetry(
        host=host,
        phase="offline_plan",
        components_dict=planned_components,
        safety_decision="OFFLINE_PLAN",
        reason="Offline deployment plan generated; zero live network probes or credentials used.",
        log_lines=[
            f"Generated offline deployment plan for {host}",
            f"Procedures planned: {len(PROCEDURES)}",
            f"Core health components required: {', '.join(REQUIRED_CORE_COMPONENTS)}",
        ],
    )
    return {
        "host": host,
        "mode": "offline_plan",
        "inventory_checks": checks,
        "procedures": [
            {"id": name, "chapter_procedure": number, "implementation": mode}
            for name, number, mode in PROCEDURES
        ],
        "minimum_health_probe_requests": 16,
        "minimum_health_probe_spacing_seconds": MIN_REQUEST_SPACING_SECONDS,
        "minimum_health_probe_elapsed_seconds": 15 * MIN_REQUEST_SPACING_SECONDS,
        "downgrade_or_reflash_for_test": False,
        "live_contact_allowed": False,
        "firmware_execution_implemented": False,
        "oob_offline_transition_replay_available": True,
        "oob_live_backend_implemented": False,
        "oob_catalog_deadlines_seconds": dict(TIMEOUTS),
        "oob_task_poll_spacing_seconds": POLL_SECONDS,
        "oob_inter_component_spacing_seconds": INTER_COMPONENT_SECONDS,
        "oob_activation_initial_settle_seconds": 300,
        "oob_activation_bmc_timeout_seconds": 1800,
        "oob_activation_host_timeout_seconds": 900,
        "oob_activation_poll_interval_seconds": 30,
        "unattended_huu_verified": False,
        "telemetry": telemetry,
    }


def _read_c880_host(inventory_dir, host):
    if host not in HOSTS:
        raise ValueError(f"Host {host} is outside C880 workflow")
    path = Path(inventory_dir) / "host_vars" / f"{host}.yml"
    if not path.is_file():
        raise FileNotFoundError(f"Host inventory file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    ucs = data.get("ucs", {})
    if ucs.get("platform") != "standalone" or ucs.get("role") != "gpu":
        raise ValueError(f"Selected host {host} is not a standalone GPU server")
    cimc = ucs.get("cimc", {})
    if not isinstance(cimc, dict) or not cimc.get("ip") or not cimc.get("user") or not cimc.get("pass_ref"):
        raise ValueError(f"Host {host} has incomplete CIMC configuration")
    return cimc["ip"], cimc["user"], cimc["pass_ref"]


def wait_for_bmc_and_host_ready(
    reader,
    *,
    initial_settle_seconds=300,
    bmc_timeout_seconds=1800,
    host_timeout_seconds=900,
    poll_interval_seconds=30,
    pause=time.sleep,
    time_fn=time.time,
    logger=None,
):
    """Deterministically wait for BMC HTTPS (port 443) and host POST after activation.

    Timing mechanics (derived from vendor upgrade engine and C880 hardware specifications):
    1. Chassis AC power cycle and BMC cold reboot take approximately 6 to 8 minutes.
       An initial settle period avoids hammering the BMC while it is resetting.
    2. Redfish root (/redfish/v1/) is polled over HTTPS every poll_interval_seconds (default 30s)
       with a timeout of 1800s (30m). No SSH or SOL probes are ever used for management liveness.
    3. Host system (/redfish/v1/Systems/DGX) is polled until PowerState is 'On' and
       Status.Health is populated (timeout 900s / 15m), confirming BIOS POST completion.
    """
    if initial_settle_seconds > 0:
        if logger:
            logger(f"Activation initiated. Waiting {initial_settle_seconds}s settle period for BMC reboot...")
        pause(initial_settle_seconds)

    start_time = time_fn()
    bmc_online = False
    while (time_fn() - start_time) < bmc_timeout_seconds:
        try:
            root = reader("/redfish/v1/")
            if isinstance(root, dict) and "Systems" in root:
                bmc_online = True
                if logger:
                    logger("BMC HTTPS Redfish service is online.")
                break
        except Exception:
            pass
        pause(poll_interval_seconds)

    if not bmc_online:
        raise TimeoutError(
            f"BMC HTTPS Redfish service did not come online within {bmc_timeout_seconds} seconds"
        )

    host_start = time_fn()
    host_ready = False
    while (time_fn() - host_start) < host_timeout_seconds:
        try:
            dgx = reader("/redfish/v1/Systems/DGX")
            if isinstance(dgx, dict) and dgx.get("PowerState") == "On":
                status = dgx.get("Status", {})
                if status.get("Health") in ("OK", "Warning", "Critical"):
                    host_ready = True
                    if logger:
                        logger("Host DGX system is powered On and reporting status.")
                    break
        except Exception:
            pass
        pause(poll_interval_seconds)

    if not host_ready:
        raise TimeoutError(
            f"Host DGX subsystem did not reach PowerState 'On' within {host_timeout_seconds} seconds"
        )

    return True


def run_get_only_health_stage(fetch, *, host, baseline=None,
                              pilot_evidence=None, pause):
    """Injectable stage for offline tests and future gated read-only use.

    If no pre-window baseline exists, a new baseline is captured first. The
    resulting comparison proves only what the sampled GETs observed.
    """
    if host not in HOSTS:
        raise ValueError(f"Host {host} is outside C880 workflow")
    if baseline is None:
        conditions = fetch("/redfish/v1/ServiceConditions").get("Conditions")
        baseline = make_baseline(conditions)
        baseline.update({"host": host, "phase": "pre_upgrade_reference",
                         "captured_utc": datetime.now(timezone.utc).isoformat()})
        pause(MIN_REQUEST_SPACING_SECONDS)
    elif (not isinstance(baseline, dict) or baseline.get("host") != host
          or baseline.get("phase") != "pre_upgrade_reference"):
        raise ValueError("Baseline host or phase mismatch")
    result = probe_gate(fetch, baseline=baseline, pause=pause)
    return {
        "baseline": baseline,
        "result": result,
        "manual_or_firmware_actions_performed": False,
        "upgrade_window_verified": False,
    }


def _run_live_oob_upgrade_impl(
    inventory_dir,
    host,
    *,
    bundle_path=DEFAULT_BUNDLE_PATH,
    script_path=DEFAULT_SCRIPT_PATH,
    allow_self_signed_lab=True,
    pause=MIN_REQUEST_SPACING_SECONDS,
    initial_settle_seconds=300,
    bmc_timeout_seconds=1800,
    host_timeout_seconds=900,
    poll_interval_seconds=30,
    confirm_host=None,
    required_components=REQUIRED_CORE_COMPONENTS,
    discover_only=False,
    run_dir=None,
    capture_log=None,
):
    """Execute credential-safe, in-memory OOB firmware evaluation and upgrade.
    
    1. Validates host scope and platform configuration in inventory.
    2. Protects validated reference nodes from accidental live re-flash.
    3. Runs Redfish pre-upgrade health check against /redfish/v1/ServiceConditions.
    4. Loads vendor upgrade engine in-memory, discovers components without exposing secrets.
    5. Evaluates downgrade safety with zero tolerance (strictly rejects rollbacks) and complete inventory.
    6. If all components are up to date, skips flashing and avoids all power cycles.
    7. If safe upgrade candidates exist, executes upgrade and verifies health post-upgrade.
    """
    if host in VALIDATED_REFERENCE_HOSTS and confirm_host != host:
        raise RuntimeError(
            f"Host '{host}' is a validated reference node. Live upgrade is locked to prevent "
            f"accidental re-flashing or power disruption. "
            f"Explicit confirmation required: pass confirm_host='{host}' to proceed."
        )

    bundle_path = Path(bundle_path)
    script_path = Path(script_path)
    if not bundle_path.is_file():
        raise FileNotFoundError(f"Bundle file not found: {bundle_path}")
    if not script_path.is_file():
        raise FileNotFoundError(f"Vendor upgrade script not found: {script_path}")

    address, username, pass_ref = _read_c880_host(inventory_dir, host)
    password = _read_vault_password(inventory_dir, pass_ref)

    capture_log.add_secret(password)
    log_lines = capture_log.lines

    capture_log(f"Starting OOB firmware workflow on host {host} (CIMC {address})")
    reader = RedfishReader(address, username, password, allow_self_signed_lab=allow_self_signed_lab)

    # Stage 1: Pre-upgrade Health Check (Procedure 3)
    conditions = reader("/redfish/v1/ServiceConditions").get("Conditions", [])
    baseline = make_baseline(conditions)
    baseline.update({
        "host": host,
        "phase": "pre_upgrade_reference",
        "captured_utc": datetime.now(timezone.utc).isoformat(),
    })
    time.sleep(pause)

    pre_gate = probe_gate(reader, baseline=baseline, pause=lambda _s: time.sleep(pause))
    capture_log(f"Stage 1: Pre-upgrade health check decision: {pre_gate['decision']}")
    if pre_gate["decision"] not in ("pass_observed_snapshot", "baseline_required"):
        raise RuntimeError(f"Pre-upgrade health gate failed: {pre_gate['decision']}")

    # Stage 2: In-Memory Discovery & Version Safety Evaluation (Procedure 4)
    spec = importlib.util.spec_from_file_location("c880_vendor_engine", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with capture_vendor_output(capture_log):
        mod.init_logger()

    upgrade_obj = mod.Upgrade(str(bundle_path), username, password, address, force_update=False)

    try:
        with tarfile.open(str(bundle_path), "r") as tf:
            tf.extractall(path=upgrade_obj.tmp_dir)
        with open(upgrade_obj.tmp_dir + "/Catalog.json", "r", encoding="utf-8") as fd:
            upgrade_obj.catalog = json.load(fd)
            upgrade_obj.bundle_version = upgrade_obj.catalog.get("bundle_version")

        with capture_vendor_output(capture_log):
            upgrade_obj.validate_login_details()
            upgrade_obj.get_bmc_serial_number()
            upgrade_obj.get_hostname()
            upgrade_obj.get_host_power_state()
            upgrade_obj.get_gpu_model_number()
            upgrade_obj.table = upgrade_obj.create_table_model()
            upgrade_obj.inventory()

        components_info = {}
        for row in upgrade_obj.table.rows:
            comp_name = row[1]
            running_ver = row[2]
            packaged_ver = row[3]
            if comp_name == "GPU" and running_ver == "Not discovered" and packaged_ver == "N/A":
                try:
                    gpu_entry = reader("/redfish/v1/UpdateService/FirmwareInventory/NVIDIA-B300-GPU")
                    if gpu_entry.get("Version"):
                        running_ver = gpu_entry.get("Version")
                        packaged_ver = upgrade_obj.get_packaged_version("NVIDIA-B300-GPU")
                except Exception:
                    pass
            components_info[comp_name] = (running_ver, packaged_ver)
            capture_log(f"Discovered: {comp_name} running={running_ver} target={packaged_ver}")
    finally:
        upgrade_obj.cleanup()

    safety = check_downgrade_safety(components_info, required_components=required_components)
    capture_log(f"Downgrade safety decision: {safety['decision']} - {safety['reason']}")

    if not safety["is_safe"]:
        if safety["decision"] == "BLOCKED_DOWNGRADE":
            raise DowngradeBlockedError(safety["reason"])
        raise UnverifiedVersionError(safety["reason"])

    if discover_only:
        telemetry = build_structured_telemetry(
            host=host,
            phase="pre_upgrade_discovery",
            components_dict=safety["components"],
            safety_decision=safety["decision"],
            reason=safety["reason"],
            pre_health=pre_gate["decision"],
            log_lines=log_lines,
        )
        return {
            "host": host,
            "mode": "discover_only",
            "downgrade_safety": safety["decision"],
            "components": safety["components"],
            "pre_upgrade_health": pre_gate["decision"],
            "is_safe": safety["is_safe"],
            "upgradable_components": safety.get("upgradable_components", []),
            "reason": safety["reason"],
            "discovered_utc": datetime.now(timezone.utc).isoformat(),
            "telemetry": telemetry,
        }

    # Stage 3: Execution / Idempotent Skip
    mutation_performed = False
    power_cycle_performed = False

    if safety["decision"] == "ALL_ALREADY_TARGET":
        capture_log("All components verified at target baseline. Flashing skipped cleanly.")
    elif safety["decision"] == "UPGRADE_CANDIDATE":
        upgradable = safety["upgradable_components"]
        capture_log(f"Stage 3: Upgrading components: {', '.join(upgradable)}")
        re_obj = mod.Upgrade(str(bundle_path), username, password, address, force_update=False)
        try:
            with tarfile.open(str(bundle_path), "r") as tf:
                tf.extractall(path=re_obj.tmp_dir)
            with open(re_obj.tmp_dir + "/Catalog.json", "r", encoding="utf-8") as fd:
                re_obj.catalog = json.load(fd)
                re_obj.bundle_version = re_obj.catalog.get("bundle_version")
            re_obj.validate_login_details()
            re_obj.get_bmc_serial_number()
            re_obj.get_hostname()
            re_obj.get_host_power_state()
            re_obj.get_gpu_model_number()
            re_obj.table = re_obj.create_table_model()
            re_obj.inventory()

            with capture_vendor_output(capture_log):
                update_status, all_skipped = re_obj.update()
                # Cisco vendor script always activates staged components regardless of partial exceptions
                re_obj.activate()
            mutation_performed = True
            power_cycle_performed = True
            capture_log(f"Vendor engine update status={update_status}, all_skipped={all_skipped}")
            capture_log("Vendor activation triggered. System undergoing reboot/power cycle.")
            if not update_status:
                capture_log("[WARNING] Vendor update reported partial exceptions; activation completed.")
        finally:
            re_obj.cleanup()

    # Stage 4: Post-upgrade Health Verification
    if power_cycle_performed:
        wait_for_bmc_and_host_ready(
            reader,
            initial_settle_seconds=initial_settle_seconds,
            bmc_timeout_seconds=bmc_timeout_seconds,
            host_timeout_seconds=host_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            pause=time.sleep,
            logger=capture_log,
        )
    else:
        time.sleep(pause)

    post_gate = probe_gate(reader, baseline=baseline, pause=lambda _s: time.sleep(pause))
    capture_log(f"Stage 4: Post-upgrade health gate decision: {post_gate['decision']}")
    if post_gate["decision"] not in ("pass_observed_snapshot", "baseline_required"):
        raise RuntimeError(f"Post-upgrade health verification failed: {post_gate['decision']}")

    # Stage 5: Procedure 1 & 2 Settings Persistence Audit (end of automation before HUU)
    host_spec = _read_host_spec(inventory_dir, host)
    shared_spec = _read_shared_spec(inventory_dir)
    persist_res = audit_settings_persistence(reader, host_spec, shared_spec, pause=lambda _s: time.sleep(pause))
    capture_log(f"Stage 5: Procedure 1 settings persistence audit all_passed: {persist_res.get('all_passed')}")
    if not persist_res.get("all_passed"):
        failed_checks = [k for k, v in persist_res.get("details", {}).items() if not v.get("passed")]
        raise RuntimeError(
            f"Procedure 1 settings persistence check failed on {host} at end of automation (before HUU): {failed_checks}. "
            f"Details: {persist_res.get('details')}"
        )

    telemetry = build_structured_telemetry(
        host=host,
        phase="upgrade_execution",
        components_dict=safety["components"],
        safety_decision=safety["decision"],
        reason=safety["reason"],
        pre_health=pre_gate["decision"],
        post_health=post_gate["decision"],
        settings_persistence=persist_res,
        power_cycle_required=power_cycle_performed,
        log_lines=log_lines,
    )
    return {
        "host": host,
        "status": "success",
        "downgrade_safety": safety["decision"],
        "components": safety["components"],
        "pre_upgrade_health": pre_gate["decision"],
        "post_upgrade_health": post_gate["decision"],
        "settings_persistence": persist_res,
        "mutation_performed": mutation_performed,
        "power_cycle_performed": power_cycle_performed,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "telemetry": telemetry,
    }


def run_live_oob_upgrade(*args, capture_log=None, **kwargs):
    """Run the live workflow with guaranteed logger cleanup for direct callers."""
    if capture_log is not None:
        return _run_live_oob_upgrade_impl(*args, capture_log=capture_log, **kwargs)
    with RunLog(run_dir=kwargs.get("run_dir")) as owned_log:
        try:
            return _run_live_oob_upgrade_impl(*args, capture_log=owned_log, **kwargs)
        except Exception as err:
            owned_log(f"Live workflow failed: {type(err).__name__}: {err}")
            raise


def run_persistence_audit(inventory_dir, host, *, allow_self_signed_lab=True, capture_log=None):
    """Audit Procedure 1 & 2 settings persistence on host (end of automation before HUU)."""
    if host not in HOSTS:
        raise ValueError(f"Host {host} is outside C880 workflow")
    host_spec = _read_host_spec(inventory_dir, host)
    shared_spec = _read_shared_spec(inventory_dir)
    password = _read_vault_password(inventory_dir, host_spec["pass_ref"])
    if capture_log:
        capture_log.add_secret(password)

    reader = RedfishReader(
        host_spec["ip"],
        host_spec["user"],
        password,
        allow_self_signed_lab=allow_self_signed_lab,
    )

    persist_res = audit_settings_persistence(reader, host_spec, shared_spec)
    telemetry = build_structured_telemetry(
        host=host,
        phase="persistence_audit",
        safety_decision="PERSISTENCE_AUDIT",
        reason="Procedure 1 & 2 settings persistence audited via Redfish.",
        settings_persistence=persist_res,
        log_lines=[
            f"Audited Procedure 1 & 2 settings persistence on {host}",
            f"Persistence audit all_passed: {persist_res.get('all_passed', False)}",
        ],
    )
    return {
        "host": host,
        "all_passed": persist_res.get("all_passed", False),
        "settings_persistence": persist_res,
        "audited_utc": datetime.now(timezone.utc).isoformat(),
        "telemetry": telemetry,
    }


def run_huu_postcheck(inventory_dir, host, *, allow_self_signed_lab=True, capture_log=None):
    """Audit Procedure 5 (HUU) firmware baselines and Procedure 1 settings persistence."""
    if host not in HOSTS:
        raise ValueError(f"Host {host} is outside C880 workflow")
    host_spec = _read_host_spec(inventory_dir, host)
    shared_spec = _read_shared_spec(inventory_dir)
    password = _read_vault_password(inventory_dir, host_spec["pass_ref"])
    if capture_log:
        capture_log.add_secret(password)

    reader = RedfishReader(
        host_spec["ip"],
        host_spec["user"],
        password,
        allow_self_signed_lab=allow_self_signed_lab,
    )

    huu_res = audit_huu_firmware(reader)
    persist_res = audit_settings_persistence(reader, host_spec, shared_spec)

    all_passed = bool(huu_res.get("all_passed") and persist_res.get("all_passed"))

    huu_components = {}
    for comp_item in huu_res.get("components", []):
        name = comp_item.get("name", "Unknown")
        ver = comp_item.get("version", "Unknown")
        target = comp_item.get("target_baseline", "Unknown")
        match = comp_item.get("matches_baseline", False)
        huu_components[name] = {
            "running": ver,
            "packaged": target,
            "status": "SKIP_ALREADY_TARGET" if match else "UPGRADE_REQUIRED",
        }

    telemetry = build_structured_telemetry(
        host=host,
        phase="post_upgrade_verification",
        components_dict=huu_components,
        safety_decision="ALL_ALREADY_TARGET" if all_passed else "UPGRADE_CANDIDATE",
        reason="HUU post-upgrade firmware and Procedure 1 persistence audited via Redfish.",
        settings_persistence=persist_res,
        log_lines=[
            f"Audited Procedure 5 (HUU) baselines on {host}: all_passed={huu_res.get('all_passed')}",
            f"Audited Procedure 1 persistence on {host}: all_passed={persist_res.get('all_passed')}",
        ],
    )

    return {
        "host": host,
        "all_passed": all_passed,
        "huu_firmware": huu_res,
        "settings_persistence": persist_res,
        "audited_utc": datetime.now(timezone.utc).isoformat(),
        "telemetry": telemetry,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory_dir", type=Path)
    parser.add_argument("--host", choices=HOSTS, required=True)
    parser.add_argument(
        "--live-upgrade",
        action="store_true",
        help="Execute live in-memory OOB firmware upgrade and health verification.",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Execute in-memory discovery, inventory, and downgrade safety check without mutating.",
    )
    parser.add_argument(
        "--confirm-host",
        type=str,
        default=None,
        help="Explicit confirmation required to target validated reference nodes (ucs-c880-3, ucs-c880-4).",
    )
    parser.add_argument(
        "--audit-huu",
        action="store_true",
        help="Execute post-HUU firmware and Procedure 1 settings persistence audit.",
    )
    parser.add_argument(
        "--audit-persistence",
        action="store_true",
        help="Audit Procedure 1 & 2 settings persistence (end of automation before HUU).",
    )
    parser.add_argument("--bundle-path", type=Path, default=DEFAULT_BUNDLE_PATH)
    parser.add_argument("--script-path", type=Path, default=DEFAULT_SCRIPT_PATH)
    parser.add_argument(
        "--telemetry-file",
        type=Path,
        default=None,
        help="Write structured JSON telemetry payload to specified file.",
    )
    parser.add_argument(
        "--telemetry-only",
        action="store_true",
        help="Output only the structured telemetry JSON object.",
    )
    parser.add_argument(
        "--run-log-root",
        type=Path,
        default=DEFAULT_RUN_LOG_ROOT,
        help="Root directory for per-run artifact directories (raw.log, telemetry.json).",
    )
    parser.add_argument(
        "--no-run-logs",
        action="store_true",
        help="Keep logs in memory only; write no per-run directory.",
    )
    args = parser.parse_args()

    action = (
        "audit-persistence" if args.audit_persistence
        else "audit-huu" if args.audit_huu
        else "discover" if args.discover
        else "live-upgrade" if args.live_upgrade
        else "plan"
    )
    run_dir = None if args.no_run_logs else make_run_dir(args.run_log_root, args.host, action)
    started_utc = datetime.now(timezone.utc).isoformat()
    capture_log = RunLog(run_dir=run_dir)
    heartbeat = RunStatusHeartbeat(run_dir, started_utc, scrubber=capture_log)
    errors = {"message": None}
    capture_log(f"Starting {action} run for host {args.host}")
    write_run_status(run_dir, "running", started_utc=started_utc, scrubber=capture_log)
    heartbeat.start()

    def _on_signal(signum, _frame):
        # A terminated run must not look like one still in progress.
        message = f"terminated by signal {signum}"
        capture_log(message)
        errors["message"] = message
        write_run_status(run_dir, "failed", exit_code=128 + signum,
                         error=message, started_utc=started_utc, scrubber=capture_log)
        raise SystemExit(128 + signum)

    def output_result(result, exit_code=0):
        if isinstance(result, dict) and "telemetry" in result and run_dir:
            # Tells a reader where this run's retained artifacts live.
            result["telemetry"]["artifacts"] = {
                "run_id": run_dir.name,
                "run_dir": str(run_dir),
                "raw_log": str(run_dir / RAW_LOG_NAME),
                "telemetry_file": str(run_dir / RUN_TELEMETRY_NAME),
                "status_file": str(run_dir / RUN_STATUS_NAME),
            }
            _atomic_json_write(run_dir / RUN_TELEMETRY_NAME, result["telemetry"])
        if args.telemetry_file and isinstance(result, dict) and "telemetry" in result:
            _atomic_json_write(args.telemetry_file, result["telemetry"], private_parent=False)
        out_obj = (
            result["telemetry"]
            if (args.telemetry_only and isinstance(result, dict) and "telemetry" in result)
            else result
        )
        print(json.dumps(out_obj, indent=2, sort_keys=True))
        return exit_code

    def _dispatch():
        def report_error(context, err=None):
            message = (
                f"{context}: {type(err).__name__}: {err}"
                if err is not None else context
            )
            errors["message"] = capture_log.scrub(message)
            capture_log(message)
            print(f"[ERROR] {capture_log.scrub(message)}", file=sys.stderr)

        if args.audit_persistence:
            try:
                res = run_persistence_audit(args.inventory_dir, args.host, capture_log=capture_log)
                return output_result(res, 0 if res["all_passed"] else 1)
            except Exception as err:
                report_error("Settings persistence audit failed", err)
                return 2

        if args.audit_huu:
            try:
                res = run_huu_postcheck(args.inventory_dir, args.host, capture_log=capture_log)
                return output_result(res, 0 if res["all_passed"] else 1)
            except Exception as err:
                report_error("Post-HUU audit failed", err)
                return 2

        if args.discover:
            try:
                result = run_live_oob_upgrade(
                    args.inventory_dir,
                    args.host,
                    bundle_path=args.bundle_path,
                    script_path=args.script_path,
                    confirm_host=args.confirm_host,
                    discover_only=True,
                    run_dir=run_dir,
                    capture_log=capture_log,
                )
                return output_result(result, 0 if result["is_safe"] else 1)
            except DowngradeBlockedError as err:
                report_error("Downgrade blocked", err)
                return 3
            except Exception as err:
                report_error("Live discovery failed", err)
                return 2

        if args.live_upgrade:
            try:
                result = run_live_oob_upgrade(
                    args.inventory_dir,
                    args.host,
                    bundle_path=args.bundle_path,
                    script_path=args.script_path,
                    confirm_host=args.confirm_host,
                    run_dir=run_dir,
                    capture_log=capture_log,
                )
            except DowngradeBlockedError as err:
                report_error("Downgrade blocked", err)
                return 3
            except Exception as err:
                report_error("Live upgrade failed", err)
                return 2
        else:
            try:
                result = offline_plan(args.inventory_dir, args.host)
            except Exception as err:
                report_error("C880 workflow plan failed; inspect inventory privately", err)
                return 2

        return output_result(result, 0)

    exit_code, failure = 2, None
    try:
        for _sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(_sig, _on_signal)
        exit_code = _dispatch()
        return exit_code
    except BaseException as err:
        failure = capture_log.scrub(f"{type(err).__name__}: {err}")
        errors["message"] = failure
        capture_log(f"Unhandled run error: {failure}")
        if isinstance(err, SystemExit) and isinstance(err.code, int):
            # Signal handlers exit with 128+signum; keep that, not the default.
            exit_code = err.code
        raise
    finally:
        heartbeat.stop()
        capture_log(f"Run finished with exit code {exit_code}")
        final_state = run_state_for_exit(exit_code, raised=bool(failure))
        try:
            write_run_status(
                run_dir,
                final_state,
                exit_code=exit_code, error=failure or errors["message"],
                started_utc=started_utc, scrubber=capture_log,
            )
            if run_dir:
                try:
                    prune_completed_runs(args.run_log_root, args.host)
                except OSError as err:
                    capture_log(f"[WARNING] Run retention cleanup failed: {err}")
        finally:
            capture_log.close()


if __name__ == "__main__":
    raise SystemExit(main())
