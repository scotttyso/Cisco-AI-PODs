import json
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "schemas/telemetry/backend-fabric-nxos.telemetry.schema.json"
EXAMPLE = ROOT / "schemas/telemetry/_examples/backend-fabric-nxos.telemetry.example.json"
SCRIPT = ROOT / "02-backend-fabric-nxos/automation/scripts/sg2_nd_paired_upgrade.py"


def test_backend_fabric_example_matches_schema():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(example)


def test_telemetry_only_is_offline_and_requires_no_credentials():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--telemetry-only", "--profile", "sg2"],
        cwd=ROOT, check=True, capture_output=True, text=True,
        env={"PATH": "", "PYTHONPATH": str(ROOT)},
    )
    payload = json.loads(result.stdout)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(payload)
    assert payload["phase"] == "offline_plan"
    assert "artifacts" not in payload
    assert len(payload["switches_table"]) == 4
