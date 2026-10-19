from __future__ import annotations

from pathlib import Path
import sys


AUTOMATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AUTOMATION / "scripts"))

from sol_bootstrap import Sol  # noqa: E402


def test_skip_prompt_is_repainted_before_expect() -> None:
    sol = object.__new__(Sol)
    sol.cimc_host = "192.0.2.10"
    events: list[str] = []

    sol._nudge = lambda: events.append("nudge")
    sol._expect = lambda *_args, **_kwargs: events.append("expect") or "prompt"
    sol._send_line = lambda line, **_kwargs: events.append(f"send:{line}")

    assert sol.wait_and_send_skip(timeout_s=900) is True
    assert events == ["nudge", "expect", "send:skip"]
