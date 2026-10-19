import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("probe_sg2_nd_readonly", SCRIPTS / "probe_sg2_nd_readonly.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture():
    expected = {host.upper(): {"mgmt_ip": "192.0.2." + str(index),
                              "role": "spine" if "-sp" in host else "leaf"}
                for index, host in enumerate(MODULE.HOSTS, 1)}
    records = [{"logicalName": name, "ipAddress": spec["mgmt_ip"],
                "switchRole": spec["role"], "model": "N9364E-SG2-O", "status": "ok",
                "serialNumber": "SECRET_NOT_TO_EMIT", "password": "SECRET_NOT_TO_EMIT"}
               for name, spec in expected.items()]
    return expected, records


class NdReadTests(unittest.TestCase):
    def test_healthy_controller_snapshot_does_not_claim_fabric_complete(self):
        expected, records = fixture()
        result = MODULE.summarize({"operStatus": "HEALTHY"}, records, expected)
        self.assertTrue(result["nd_fabric_oper_status_healthy"])
        self.assertTrue(all(item["nd_inventory_status_ok"] for item in result["switches"]))
        self.assertFalse(result["e2e_complete"])
        self.assertNotIn("SECRET", str(result))
        self.assertNotIn("192.0.2", str(result))

    def test_missing_or_duplicate_switch_rejected(self):
        expected, records = fixture()
        for wrong in (records[:3], records[:3] + records[:1]):
            with self.assertRaises(ValueError):
                MODULE.summarize({}, wrong, expected)

    def test_changed_role_address_or_status_remains_visible(self):
        expected, records = fixture()
        records[0].update(ipAddress="192.0.2.254", switchRole="leaf", status="error")
        result = MODULE.summarize({"operStatus": "UNKNOWN"}, records, expected)
        changed = next(item for item in result["switches"] if item["hostname"] == records[0]["logicalName"])
        self.assertFalse(changed["management_address_matches_inventory"])
        self.assertFalse(changed["role_matches_inventory"])
        self.assertFalse(changed["nd_inventory_status_ok"])
        self.assertFalse(result["nd_fabric_oper_status_healthy"])

    def test_redirects_are_never_followed(self):
        self.assertIsNone(MODULE.NoRedirect().redirect_request(None, None, 302, None, {}, "https://other.invalid"))

    def test_status_case_is_normalized_and_unknown_strings_not_emitted(self):
        expected, records = fixture()
        self.assertTrue(MODULE.summarize({"operStatus": "healthy"}, records, expected)["nd_fabric_oper_status_healthy"])
        result = MODULE.summarize({"operStatus": "SECRET_NOT_TO_EMIT"}, records, expected)
        self.assertEqual(result["nd_fabric_oper_status"], "UNRECOGNIZED")
        self.assertNotIn("SECRET", str(result))


if __name__ == "__main__":
    unittest.main()
