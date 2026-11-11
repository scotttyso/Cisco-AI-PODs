"""Resumable state files.

Each phase writes a small JSON file under state_dir/. Re-running the orchestrator
reads these and skips completed phases.

Designed so the same files can later be loaded by Ansible (set_fact / cache) when
we migrate to phase 2.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _path(state_dir: str | os.PathLike[str], name: str) -> Path:
    p = Path(state_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{name}.json"


def load(state_dir: str | os.PathLike[str], name: str) -> dict[str, Any]:
    p = _path(state_dir, name)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save(state_dir: str | os.PathLike[str], name: str, data: dict[str, Any]) -> None:
    """Atomic write so a crash mid-write doesn't corrupt the file."""
    p = _path(state_dir, name)
    fd, tmp = tempfile.mkstemp(prefix=f".{p.name}.", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True, default=str)
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def mark(state_dir: str | os.PathLike[str], name: str, phase: str, **fields: Any) -> dict[str, Any]:
    data = load(state_dir, name)
    data.setdefault("phases", {})[phase] = {"status": "complete", **fields}
    save(state_dir, name, data)
    return data


def is_complete(state_dir: str | os.PathLike[str], name: str, phase: str) -> bool:
    data = load(state_dir, name)
    return data.get("phases", {}).get(phase, {}).get("status") == "complete"


def clear_phases(
    state_dir: str | os.PathLike[str],
    name: str,
    *phases: str,
) -> dict[str, Any]:
    """Remove obsolete downstream markers before starting a new phase chain."""
    data = load(state_dir, name)
    phase_state = data.setdefault("phases", {})
    changed = False
    for phase in phases:
        if phase in phase_state:
            phase_state.pop(phase)
            changed = True
    if changed:
        save(state_dir, name, data)
    return data
