"""Offline tests for sanitized health-count follow-up."""

import importlib.util
from pathlib import Path
import sys
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "probe_c880_health_counts.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("probe_c880_health_counts", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class HealthCountTests(unittest.TestCase):
    def test_gate_is_paced_bounded_and_never_emits_component_data(self):
        condition = {
            "Severity": "Critical", "Timestamp": "2024-02-01T00:00:00Z",
            "MessageId": "Test.Condition",
            "OriginOfCondition": {"@odata.id": MODULE.HGX_BASEBOARD},
            "LogEntry": {"@odata.id": "/redfish/v1/Managers/HGX_BMC_0/LogServices/SEL/Entries/1"},
        }
        healthy = {"Status": {"Health": "OK", "State": "Enabled", "Conditions": []},
                   "Secret": "DO_NOT_EMIT"}
        gpu_paths = [f"{MODULE.GPU_COLLECTION}/{i}" for i in range(9)]
        switch_paths = [f"{MODULE.SWITCH_COLLECTION}/{i}" for i in range(2)]
        responses = {
            MODULE.PATHS[1]: {"Conditions": [condition]},
            MODULE.HGX_BASEBOARD: healthy, MODULE.HGX_BMC: healthy,
            MODULE.GPU_COLLECTION: {"Members": [{"@odata.id": p} for p in gpu_paths]},
            MODULE.SWITCH_COLLECTION: {"Members": [{"@odata.id": p} for p in switch_paths]},
        }
        for path in gpu_paths[:8]:
            responses[path] = {**healthy, "ProcessorType": "GPU", "Model": "NVIDIA B300"}
        responses[gpu_paths[8]] = {**healthy, "ProcessorType": "FPGA"}
        for path in switch_paths:
            responses[path] = healthy
        calls, sleeps = [], []

        def fetch(path):
            calls.append(path)
            return responses[path]

        baseline = MODULE.capture_baseline(fetch)
        self.assertEqual(baseline["phase"], "post_manual_upgrade_reference")
        MODULE.validate_baseline_file(baseline)
        calls.clear()
        result = MODULE.probe_gate(fetch, baseline, pause=sleeps.append)
        self.assertEqual(result["decision"], "pass_observed_snapshot")
        self.assertFalse(result["upgrade_window_verified"])
        self.assertEqual(result["requests"], 16)
        self.assertEqual(len(calls), 16)
        self.assertEqual(sleeps, [MODULE.MIN_REQUEST_SPACING_SECONDS] * 15)
        self.assertNotIn("DO_NOT_EMIT", str(result))

    def test_baseline_identity_and_duplicate_members_fail_closed(self):
        baseline = {"schema": 1, "fingerprints": [], "host": "ucs-c880-4",
                    "phase": "post_manual_upgrade_reference", "captured_utc": "2026-10-03T00:00:00Z"}
        with self.assertRaises(ValueError):
            MODULE.validate_baseline_file(baseline)
        path = MODULE.GPU_COLLECTION + "/0"
        with self.assertRaises(ValueError):
            MODULE._read_members(lambda _p: {"Members": [{"@odata.id": path},
                                                       {"@odata.id": path}]},
                                 MODULE.GPU_COLLECTION, 10, lambda _s: None)

    def test_summary_omits_condition_details(self):
        calls, sleeps = [], []
        responses = {
            MODULE.PATHS[0]: {"Members": [{"Secret": "DO_NOT_EMIT"}]},
            MODULE.PATHS[1]: {"Conditions": [
                {"Severity": "Warning", "Message": "private", "Resolved": True,
                 "OriginOfCondition": {"@odata.id": "/redfish/v1/Chassis/DGX/Sensors/PRIVATE"},
                 "LogEntry": {"@odata.id": "/redfish/v1/Managers/BMC/LogServices/SEL/Entries/PRIVATE"}},
                {"Severity": "Critical", "Message": "private"},
            ]},
        }

        def fetch(path):
            calls.append(path)
            return responses[path]

        result = MODULE.probe(fetch, pause=sleeps.append)
        self.assertEqual(calls, list(MODULE.PATHS))
        self.assertEqual(sleeps, [MODULE.MIN_REQUEST_SPACING_SECONDS])
        self.assertEqual(result["power_supply_collection_members"], 1)
        self.assertEqual(result["service_condition_severity_counts"]["critical"], 1)
        self.assertTrue(result["conditions_expose_resolution_field"])
        self.assertEqual(result["condition_origin_group_counts"], {"missing": 1, "sensors": 1})
        self.assertEqual(result["conditions_with_log_link"], 1)
        self.assertNotIn("DO_NOT_EMIT", str(result))
        self.assertNotIn("private", str(result))


if __name__ == "__main__":
    unittest.main()
