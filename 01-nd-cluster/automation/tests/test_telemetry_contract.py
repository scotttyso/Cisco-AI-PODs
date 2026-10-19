import json
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "schemas/telemetry/nd-cluster.telemetry.schema.json"
EXAMPLE = ROOT / "schemas/telemetry/_examples/nd-cluster.telemetry.example.json"
SCRIPT = ROOT / "01-nd-cluster/automation/scripts/main.py"


def test_nd_cluster_example_matches_schema():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(example)


def test_telemetry_only_is_offline_and_requires_no_credentials():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "precheck", "--telemetry-only"],
        cwd=ROOT, check=True, capture_output=True, text=True,
        env={"PATH": "", "PYTHONPATH": str(ROOT)},
    )
    payload = json.loads(result.stdout)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(payload)
    assert payload["phase"] == "offline_plan"
    assert "artifacts" not in payload
