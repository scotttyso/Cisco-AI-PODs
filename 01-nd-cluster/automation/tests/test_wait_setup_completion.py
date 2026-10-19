"""Reconnect-safe ND setup status classification tests."""
from __future__ import annotations

import sys
from pathlib import Path

AUTOMATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AUTOMATION / "scripts"))

from wait_setup_completion import classify_status  # noqa: E402


def test_setup_status_completed():
    assert classify_status({"state": "Completed"}) == "complete"


def test_setup_status_in_progress():
    assert classify_status(
        {"state": "InProgress", "overallProgress": 42}
    ) == "pending"


def test_setup_status_failed():
    assert classify_status({"state": "Failed"}) == "failed"
