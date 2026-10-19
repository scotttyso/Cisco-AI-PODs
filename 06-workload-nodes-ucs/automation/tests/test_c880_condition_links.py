"""Offline tests for bounded, sanitized condition-log classification."""

import importlib.util
from pathlib import Path
import sys
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "probe_c880_condition_links.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("probe_c880_condition_links", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ConditionLinkTests(unittest.TestCase):
    def test_classifies_resolution_without_exposing_logs(self):
        path_a = "/redfish/v1/Managers/HGX_BMC_0/LogServices/SEL/Entries/A"
        path_b = "/redfish/v1/Managers/HGX_BMC_0/LogServices/SEL/Entries/B"
        responses = {
            MODULE.CONDITIONS_PATH: {"Conditions": [
                {"LogEntry": {"@odata.id": path_a}, "Message": "private"},
                {"LogEntry": {"@odata.id": path_b}, "Message": "private"},
                {"LogEntry": {"@odata.id": path_a}, "Message": "private"},
            ]},
            path_a: {"Resolved": True, "Secret": "DO_NOT_EMIT"},
            path_b: {"Resolved": False, "Secret": "DO_NOT_EMIT"},
        }
        calls, sleeps = [], []

        def fetch(path):
            calls.append(path)
            return responses[path]

        result = MODULE.probe(fetch, pause=sleeps.append)
        self.assertEqual(calls, [MODULE.CONDITIONS_PATH, path_a, path_b])
        self.assertEqual(sleeps, [MODULE.MIN_REQUEST_SPACING_SECONDS] * 2)
        self.assertEqual(result["conditions"], 3)
        self.assertEqual(result["linked_log_resolved_counts"],
                         {"true": 1, "false": 1, "unreported": 0})
        self.assertTrue(result["linked_log_resolution_is_not_current_component_health"])
        self.assertNotIn("private", str(result))
        self.assertNotIn("DO_NOT_EMIT", str(result))

    def test_rejects_excessive_conditions(self):
        with self.assertRaises(ValueError):
            MODULE.probe(lambda _path: {"Conditions": [{}] * (MODULE.MAX_LINKS + 1)})


if __name__ == "__main__":
    unittest.main()
