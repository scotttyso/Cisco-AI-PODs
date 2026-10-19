import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "c880_oob_replay.py"
SPEC = importlib.util.spec_from_file_location("c880_oob_replay", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def accepted():
    return {"http_status": 202, "body": {"Secret": "DO_NOT_EMIT", "Messages": [
        {"MessageId": "Task.1.0.New", "MessageArgs": ["/redfish/v1/TaskService/Tasks/10"]}]}}


class OobReplayTests(unittest.TestCase):
    def test_same_version_is_skipped_without_upload_or_reactivation(self):
        result = MODULE.replay("BMC", "4.0(2.260022)", "4.0.2.260022")
        self.assertEqual(result["decision"], "skip_already_target")
        self.assertEqual(result["simulated_uploads"], 0)

    def test_newer_running_bmc_and_bios_are_never_downgraded(self):
        for component, current, target in (("BMC", "4.0(2.260022)", "4.0(1.260014)"),
                                           ("BIOS", "4.0.2.67", "4.0.2.66")):
            result = MODULE.replay(component, current, target)
            self.assertEqual(result["decision"], "blocked_downgrade")
            self.assertEqual(result["simulated_uploads"], 0)

    def test_ambiguous_upload_does_not_trigger_any_task_read_or_retry(self):
        result = MODULE.replay("BIOS", "4.0.2.66", "4.0.2.67", {"outcome": "ambiguous"})
        self.assertEqual(result["decision"], "stop_submission_ambiguous_no_retry")
        self.assertFalse(result["resubmit_permitted"])
        self.assertEqual(result["simulated_task_reads"], 0)

    def test_successful_task_is_not_activation_or_upgrade_signoff(self):
        result = MODULE.replay("BIOS", "4.0.2.66", "4.0.2.67", accepted(), [
            {"elapsed_seconds": 30, "TaskState": "Running", "TaskStatus": "OK", "PercentComplete": 20},
            {"elapsed_seconds": 60, "TaskState": "Completed", "TaskStatus": "OK", "PercentComplete": 100}])
        self.assertEqual(result["decision"], "task_completed_activation_readback_still_required")
        self.assertEqual(result["simulated_task_reads"], 2)
        self.assertFalse(result["upgrade_signoff"])
        self.assertFalse(result["automatic_activation_permitted"])
        self.assertEqual(result["network_requests"], 0)
        self.assertNotIn("DO_NOT_EMIT", str(result))

    def test_completed_with_critical_or_missing_status_fails_closed(self):
        for status in ("Critical", None):
            result = MODULE.replay("BIOS", "4.0.2.66", "4.0.2.67", accepted(), [
                {"elapsed_seconds": 30, "TaskState": "Completed", "TaskStatus": status, "PercentComplete": 100}])
            self.assertTrue(result["decision"].startswith("stop_"))

    def test_untrusted_or_duplicated_task_paths_cannot_be_followed(self):
        submission = accepted()
        submission["body"]["Messages"][0]["MessageArgs"] = ["https://other.invalid/private"]
        self.assertEqual(MODULE.replay("BIOS", "4.0.2.66", "4.0.2.67", submission)["simulated_task_reads"], 0)
        submission = accepted()
        submission["body"]["Messages"] *= 2
        self.assertEqual(MODULE.replay("BIOS", "4.0.2.66", "4.0.2.67", submission)["decision"], "stop_submission_unverified_no_retry")

    def test_poll_spacing_and_catalog_deadlines_are_enforced(self):
        with self.assertRaises(ValueError):
            MODULE.replay("BIOS", "4.0.2.66", "4.0.2.67", accepted(), [
                {"elapsed_seconds": 1, "TaskState": "Running"}])
        result = MODULE.replay("EROT-BMC", "4.0.14", "4.0.15", accepted(), [
            {"elapsed_seconds": 300, "TaskState": "Running"}])
        self.assertEqual(result["decision"], "stop_deadline_no_retry")

    def test_unknown_versions_and_gpu_order_require_review(self):
        self.assertEqual(MODULE.choose_action("BIOS", "0.0.0.0", "4.0.2.67"), "blocked_version_unverified")
        self.assertEqual(MODULE.choose_action("GPU", "97.10.64.00.0C-G540.0216.00.03", "97.10.7E.00.03-G540.0216.00.03"), "blocked_gpu_order_review")
        with self.assertRaises(ValueError):
            MODULE.replay("HUU", "1", "2")


if __name__ == "__main__":
    unittest.main()
