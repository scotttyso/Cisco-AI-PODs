"""Structured JSON logging with secret redaction.

Workspace rule codeguard-0-logging: structured fields, redact passwords/tokens,
sanitize against log injection (CR/LF stripped from values).
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import uuid
from typing import Any, Mapping

# Field/value patterns we always redact, case-insensitive.
_REDACT_KEYS = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|authorization|cookie)"
)
_REDACT_VALUE = "***REDACTED***"

# Strip CR/LF/control chars from string values (log-injection sanitization).
_CTRL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")


def _sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return _CTRL.sub(" ", value)
    if isinstance(value, Mapping):
        return {k: _redact(k, v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    return value


def _redact(key: str, value: Any) -> Any:
    if isinstance(key, str) and _REDACT_KEYS.search(key):
        return _REDACT_VALUE
    return _sanitize(value)


_STD_LOGRECORD_ATTRS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
})


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per record with stable fields.

    The first six fields (`ts`, `level`, `logger`, `msg`, plus any present
    correlation fields) are emitted in a stable order; any additional
    `extra=` fields the caller passed in are emitted afterwards (redacted by
    key, sanitized by value). Standard LogRecord attributes are filtered out
    so we never echo Python internals.
    """

    _PRIMARY_ORDER = ("run_id", "section", "node", "phase", "event", "result")

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": _sanitize(record.getMessage()),
        }
        for k in self._PRIMARY_ORDER:
            v = getattr(record, k, None)
            if v is not None:
                payload[k] = _redact(k, v)
        for k, v in record.__dict__.items():
            if k in _STD_LOGRECORD_ATTRS or k in payload or k.startswith("_"):
                continue
            payload[k] = _redact(k, v)
        if record.args and isinstance(record.args, Mapping):
            for k, v in record.args.items():
                payload.setdefault(k, _redact(k, v))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure(level: str = "INFO", run_id: str | None = None) -> str:
    """Configure root logger to emit JSON to stderr. Returns the run_id."""
    run_id = run_id or os.environ.get("AIPOD_RUN_ID") or uuid.uuid4().hex[:12]
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())

    old_factory = logging.getLogRecordFactory()

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        rec = old_factory(*args, **kwargs)
        rec.run_id = run_id
        return rec

    logging.setLogRecordFactory(factory)
    return run_id


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
