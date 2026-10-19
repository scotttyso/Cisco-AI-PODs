import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("probe_c880_bios_readonly", SCRIPTS / "probe_c880_bios_readonly.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BiosTests(unittest.TestCase):
    def test_all_named_literals_match_without_overclaiming_procedure6(self):
        result = MODULE.summarize({"Attributes": dict(MODULE.EXPECTED)})
        self.assertTrue(result["all_chapter_literals_match"])
        self.assertFalse(result["procedure6_complete"])
        self.assertFalse(result["factory_defaults_independently_proven"])
        self.assertFalse(result["bluefield_both_adapters_nic_mode_verified"])

    def test_missing_tokens_are_unverified_not_silently_defaulted(self):
        result = MODULE.summarize({"Attributes": {}})
        self.assertEqual(result["missing_tokens"], len(MODULE.EXPECTED))
        self.assertFalse(result["all_chapter_literals_match"])

    def test_mismatches_and_unrelated_secrets_never_emit_actual_values(self):
        data = dict(MODULE.EXPECTED)
        data["NvidiaAcsEnable"] = "DO_NOT_EMIT"
        data["PrivatePassword"] = "DO_NOT_EMIT"
        result = MODULE.summarize({"Attributes": data})
        self.assertEqual(result["present_nonmatching_literals"], 1)
        self.assertNotIn("DO_NOT_EMIT", str(result))
        self.assertNotIn("PrivatePassword", str(result))

    def test_read_sequence_and_spacing_are_bounded(self):
        calls, pauses = [], []
        def fetch(path):
            calls.append(path)
            if len(calls) == 1:
                return {"Bios": {"@odata.id": "/redfish/v1/Systems/DGX/Bios"}}
            return {"Attributes": dict(MODULE.EXPECTED)}
        MODULE.probe(fetch, pause=pauses.append)
        self.assertEqual(calls, ["/redfish/v1/Systems/DGX", "/redfish/v1/Systems/DGX/Bios"])
        self.assertEqual(pauses, [3])

    def test_unreviewed_link_cannot_trigger_second_request(self):
        calls = []
        def fetch(path):
            calls.append(path)
            return {"Bios": {"@odata.id": "https://other.invalid/private"}}
        with self.assertRaises(ValueError):
            MODULE.probe(fetch, pause=lambda _seconds: None)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
