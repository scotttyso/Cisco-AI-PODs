"""Shared run lifecycle and scrubbed output capture for AI POD orchestrators."""
from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import io
import json
import logging
import os
from pathlib import Path
import shutil
import tempfile
import threading
import uuid


RAW_LOG_NAME = "raw.log"
RUN_STATUS_NAME = "status.json"
RUN_TELEMETRY_NAME = "telemetry.json"
LATEST_LINK_NAME = "latest"
HEARTBEAT_INTERVAL_SECONDS = 10
RUN_RETENTION_COUNT = 20


class RunLog:
    """Hold scrubbed log lines in memory and append them to a private raw.log."""

    def __init__(self, run_dir=None, secrets=()):
        self.lines = []
        self.run_dir = Path(run_dir) if run_dir else None
        self.raw_log_path = None
        self._secrets = [str(secret) for secret in secrets if secret]
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
        text = str(text)
        for secret in self._secrets:
            text = text.replace(secret, "[REDACTED_SECRET]")
        return text

    def __call__(self, message):
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] {self.scrub(message)}"
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
    """Capture text for parsing while recording complete scrubbed log lines."""

    def __init__(self, run_log, prefix=""):
        self.run_log = run_log
        self.prefix = prefix
        self.pending = ""
        self._captured = io.StringIO()

    def write(self, text):
        value = str(text)
        self._captured.write(value)
        self.pending += value
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            if line:
                self.run_log(f"{self.prefix}{line}")
        return len(value)

    def flush(self):
        if self.pending:
            self.run_log(f"{self.prefix}{self.pending}")
            self.pending = ""

    def getvalue(self):
        return self._captured.getvalue()


@contextmanager
def capture_run_output(run_log):
    """Capture stdout, stderr, and Python logging through the same scrubber."""
    stdout_stream = RunLogStream(run_log, "[stdout] ")
    stderr_stream = RunLogStream(run_log, "[stderr] ")
    root_logger = logging.getLogger()
    old_handlers = list(root_logger.handlers)
    old_level = root_logger.level
    handler = logging.StreamHandler(stderr_stream)
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    root_logger.handlers[:] = [handler]
    root_logger.setLevel(logging.NOTSET)
    try:
        with redirect_stdout(stdout_stream), redirect_stderr(stderr_stream):
            yield stdout_stream, stderr_stream
    finally:
        stdout_stream.flush()
        stderr_stream.flush()
        root_logger.handlers[:] = old_handlers
        root_logger.setLevel(old_level)


def _atomic_json_write(path, payload, *, private_parent=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True,
                      mode=0o700 if private_parent else 0o777)
    if private_parent:
        os.chmod(path.parent, 0o700)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
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


def write_run_status(run_dir, state, exit_code=None, error=None,
                     started_utc=None, heartbeat_utc=None, scrubber=None):
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
    return "succeeded" if exit_code == 0 and not raised else "failed"


def make_run_dir(root, host, action):
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
    temporary_link = root / f".{LATEST_LINK_NAME}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    try:
        temporary_link.symlink_to(run_dir.name)
        os.replace(temporary_link, link)
    except OSError:
        try:
            temporary_link.unlink()
        except OSError:
            pass
    return run_dir


def prune_completed_runs(root, host, keep=RUN_RETENTION_COUNT):
    root = Path(root)
    if not root.is_dir():
        return []
    completed = []
    for candidate in root.iterdir():
        if (candidate.is_symlink() or not candidate.is_dir()
                or f"-{host}-" not in candidate.name):
            continue
        try:
            status = json.loads(
                (candidate / RUN_STATUS_NAME).read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            continue
        if status.get("state") in ("succeeded", "failed"):
            completed.append(candidate)
    completed.sort(key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True)
    removed = []
    for stale in completed[max(0, keep):]:
        for item in stale.iterdir():
            if item.is_symlink() or item.is_file():
                item.unlink()
            elif item.is_dir():
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
                heartbeat_utc=datetime.now(timezone.utc).isoformat(),
                scrubber=self.scrubber,
            )

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join()
