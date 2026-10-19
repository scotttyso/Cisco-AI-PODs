import json
from pathlib import Path
import stat

from jsonschema import Draft202012Validator

from shared.lib.orchestrator_telemetry import (
    RunLog,
    make_run_dir,
    prune_completed_runs,
    run_state_for_exit,
    write_run_status,
)


ROOT = Path(__file__).resolve().parents[3]
STATUS_SCHEMA = ROOT / "schemas/telemetry/run-status.schema.json"


def test_run_bundle_is_private_and_raw_log_is_live_and_scrubbed(tmp_path):
    run_dir = make_run_dir(tmp_path / "run-logs", "test-host", "phase")
    needle = "scrub-marker-7q9"
    with RunLog(run_dir, secrets=[needle]) as log:
        log("startup " + needle)
        assert "[REDACTED_SECRET]" in (run_dir / "raw.log").read_text()
        assert needle not in (run_dir / "raw.log").read_text()
        write_run_status(run_dir, "running", started_utc="2026-01-01T00:00:00+00:00",
                         scrubber=log)
        status = json.loads((run_dir / "status.json").read_text())
        Draft202012Validator(json.loads(STATUS_SCHEMA.read_text()),
                             format_checker=Draft202012Validator.FORMAT_CHECKER).validate(status)
        assert status["state"] == "running"
    assert stat.S_IMODE(run_dir.stat().st_mode) == 0o700
    for name in ("raw.log", "status.json"):
        assert stat.S_IMODE((run_dir / name).stat().st_mode) == 0o600
    assert (tmp_path / "run-logs" / "latest").resolve() == run_dir


def test_retention_keeps_twenty_completed_and_every_running_run(tmp_path):
    root = tmp_path / "run-logs"
    for index in range(21):
        run_dir = make_run_dir(root, "test-host", f"phase-{index}")
        write_run_status(run_dir, "succeeded", exit_code=0,
                         started_utc="2026-01-01T00:00:00+00:00")
    running = make_run_dir(root, "test-host", "still-running")
    write_run_status(running, "running", started_utc="2026-01-01T00:00:00+00:00")

    removed = prune_completed_runs(root, "test-host")
    remaining = [path for path in root.iterdir()
                 if path.is_dir() and not path.is_symlink()]
    assert len(removed) == 1
    assert len([path for path in remaining
                if json.loads((path / "status.json").read_text())["state"] != "running"]) == 20
    assert running.exists()
    assert run_state_for_exit(0) == "succeeded"
    assert all(run_state_for_exit(code) == "failed" for code in (1, 2, 3))
