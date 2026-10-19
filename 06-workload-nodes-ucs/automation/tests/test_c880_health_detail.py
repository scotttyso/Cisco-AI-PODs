"""Offline tests for bounded, sanitized C880 chassis health reads."""

import importlib.util
from pathlib import Path
import sys
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "probe_c880_health_detail.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("probe_c880_health_detail", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class HealthDetailTests(unittest.TestCase):
    def test_paced_reads_emit_only_health_summary(self):
        responses = {
            MODULE.PATHS[0]: {"Status": {"Health": "OK"}, "Secret": "DO_NOT_EMIT"},
            MODULE.PATHS[1]: {"Status": {"Health": "OK"}},
            MODULE.PATHS[2]: {"Members": [{} for _ in range(12)]},
            MODULE.PATHS[3]: {"Status": {"Health": "OK"}},
            MODULE.PATHS[4]: {"Conditions": [{"Severity": "OK", "Message": "private"}]},
        }
        calls, sleeps = [], []

        def fetch(path):
            calls.append(path)
            return responses[path]

        result = MODULE.probe(fetch, pause=sleeps.append)
        self.assertEqual(calls, list(MODULE.PATHS))
        self.assertEqual(sleeps, [MODULE.MIN_REQUEST_SPACING_SECONDS] * 4)
        self.assertEqual(result["requests"], 5)
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(result["active_condition_count"], 1)
        self.assertNotIn("DO_NOT_EMIT", str(result))
        self.assertNotIn("private", str(result))

    def test_warning_condition_fails_gate(self):
        responses = [
            {"Status": {"Health": "OK"}},
            {"Status": {"Health": "OK"}},
            {"Members": [{} for _ in range(12)]},
            {"Status": {"Health": "OK"}},
            {"Conditions": [{"Severity": "Warning", "Message": "private"}]},
        ]
        result = MODULE.probe(lambda _path: responses.pop(0), pause=lambda _seconds: None)
        self.assertFalse(result["checks"]["no_active_warning_or_critical_conditions"])
        self.assertNotIn("private", str(result))


if __name__ == "__main__":
    unittest.main()
