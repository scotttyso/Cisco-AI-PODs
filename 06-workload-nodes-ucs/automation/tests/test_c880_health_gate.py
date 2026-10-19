"""Offline tests for condition deltas and live-component gate semantics."""

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "c880_health_gate.py"
SPEC = importlib.util.spec_from_file_location("c880_health_gate", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def condition(index, timestamp="2024-02-01T00:00:00Z"):
    return {
        "Severity": "Critical", "Timestamp": timestamp,
        "MessageId": "Test.Condition", "Message": "DO_NOT_EMIT",
        "OriginOfCondition": {"@odata.id": "/redfish/v1/Systems/HGX_Baseboard_0"},
        "LogEntry": {"@odata.id": f"/redfish/v1/Managers/HGX_BMC_0/LogServices/EventLog/Entries/{index}"},
    }


def healthy_components():
    return {"hgx_baseboard": True, "hgx_bmc": True,
            "eight_gpus": True, "two_switches": True}


def log_entry(index, stream="/redfish/v1/Managers/HGX_BMC_0/LogServices/EventLog/Entries"):
    return {"Id": str(index), "@odata.id": f"{stream}/{index}",
            "Created": "1999-12-31T00:00:00Z"}


class HealthGateTests(unittest.TestCase):
    def test_sequence_order_survives_incorrect_clock(self):
        early = condition(36, timestamp="2024-02-01T00:00:00Z")
        later = condition(211, timestamp="2020-01-01T00:00:00Z")
        entries = [log_entry(value) for value in (36, 211, 14441, 15321)]
        result = MODULE.compare_same_log_sequence([early, later], entries)
        self.assertEqual(result["newest_linked_sequence"], 211)
        self.assertEqual(result["newer_entries_in_same_stream"], 2)
        self.assertFalse(result["timestamp_used_for_order"])
        self.assertFalse(result["upgrade_completion_proven"])
        with self.assertRaises(ValueError):
            MODULE.compare_same_log_sequence([early, later], entries[:1])

    def test_sequence_rejects_cross_stream_numeric_id_collision(self):
        other_stream = "/redfish/v1/Chassis/DGX/LogServices/Logs/Entries"
        for entries in ([log_entry(36, other_stream)],
                        [log_entry(36), log_entry(15321, other_stream)]):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                MODULE.compare_same_log_sequence([condition(36)], entries)

    def test_sequence_rejects_missing_or_inconsistent_resource_identity(self):
        for entry in ({"Id": "36"}, {**log_entry(36), "Id": "37"},
                      {**log_entry(36), "@odata.id": None},
                      {**log_entry(36), "@odata.id": log_entry(36)["@odata.id"] + "?page=1"}):
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                MODULE.compare_same_log_sequence([condition(36)], [entry])
        malformed = condition(36)
        malformed["LogEntry"]["@odata.id"] = 36
        with self.assertRaises(ValueError):
            MODULE.compare_same_log_sequence([malformed], [log_entry(36)])

    def test_historical_conditions_with_healthy_components_do_not_fail(self):
        old = [condition(i) for i in range(38)]
        baseline = MODULE.make_baseline(old)
        result = MODULE.evaluate_gate(old, healthy_components(), baseline)
        self.assertEqual(result["decision"], "pass_observed_snapshot")
        self.assertEqual(result["current_condition_count"], 38)
        self.assertEqual(result["new_observed_conditions"], 0)
        self.assertNotIn("DO_NOT_EMIT", str(result))
        self.assertNotIn("HGX_Baseboard_0", str(baseline))

    def test_new_condition_or_duplicate_observation_fails(self):
        old = [condition(1)]
        baseline = MODULE.make_baseline(old)
        for current in (old + [condition(2)], old + [condition(1)]):
            with self.subTest(count=len(current)):
                result = MODULE.evaluate_gate(current, healthy_components(), baseline)
                self.assertEqual(result["decision"], "fail")
                self.assertEqual(result["new_observed_conditions"], 1)

    def test_component_condition_fails_even_without_new_service_condition(self):
        old = [condition(1)]
        checks = healthy_components()
        checks["eight_gpus"] = False
        result = MODULE.evaluate_gate(old, checks, MODULE.make_baseline(old))
        self.assertEqual(result["decision"], "fail")

    def test_no_baseline_is_indeterminate_not_a_false_pass(self):
        result = MODULE.evaluate_gate([condition(1)], healthy_components())
        self.assertEqual(result["decision"], "baseline_required")
        self.assertIsNone(result["new_observed_conditions"])
        self.assertTrue(result["no_unobserved_transient_claim"])

    def test_component_inventory_checks_all_instances(self):
        status = {"Status": {"Health": "OK", "State": "Enabled", "Conditions": []}}
        gpu = lambda: {**status, "ProcessorType": "GPU", "Model": "NVIDIA B300"}
        fpga = {**status, "ProcessorType": "FPGA"}
        processors = [gpu() for _ in range(8)] + [fpga]
        checks = MODULE.evaluate_components(status, status, processors, [status, status])
        self.assertTrue(all(checks.values()))
        processors[0] = {**gpu(), "Status": {"Health": "OK", "State": "Enabled",
                                              "Conditions": [{"Message": "DO_NOT_EMIT"}]}}
        checks = MODULE.evaluate_components(status, status, processors, [status, status])
        self.assertFalse(checks["eight_b300_gpus_ok_and_no_conditions"])
        self.assertFalse(checks["all_processor_resources_ok_and_no_conditions"])

    def test_incomplete_or_untrusted_baseline_fails_closed(self):
        with self.assertRaises(ValueError):
            MODULE.make_baseline([{"Severity": "Critical"}])
        with self.assertRaises(ValueError):
            MODULE.compare_conditions([], {"schema": 1, "fingerprints": ["BAD"]})


if __name__ == "__main__":
    unittest.main()
