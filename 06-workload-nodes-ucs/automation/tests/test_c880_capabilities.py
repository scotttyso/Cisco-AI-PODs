"""Offline tests for the sanitized C880 capability probe."""

import importlib.util
from pathlib import Path
import sys
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "probe_c880_capabilities.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("probe_c880_capabilities", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CapabilityTests(unittest.TestCase):
    def test_paced_reads_emit_only_allowlisted_capabilities(self):
        responses = {
            "/redfish/v1/Managers/BMC": {
                "Actions": {"Oem": {"#AMIVirtualMedia.EnableRMedia": {"target": "private"}}},
                "Secret": "DO_NOT_EMIT",
            },
            "/redfish/v1/Managers/BMC/VirtualMedia": {
                "Members": [{"@odata.id": "/redfish/v1/Managers/BMC/VirtualMedia/CD1"}]
            },
            "/redfish/v1/UpdateService/FirmwareInventory": {
                "Members": [{"@odata.id": "/redfish/v1/UpdateService/FirmwareInventory/private"}]
            },
            "/redfish/v1/Systems/DGX": {
                "@Redfish.Settings": {"SettingsObject": {"@odata.id": "/redfish/v1/Systems/DGX/Settings"}}
            },
            "/redfish/v1/Systems/DGX/Settings": {
                "Boot": {"BootSourceOverrideTarget@Redfish.AllowableValues": ["Cd", "Pxe"]}
            },
            "/redfish/v1/Managers/BMC/VirtualMedia/CD1": {
                "Inserted": False,
                "Actions": {"#VirtualMedia.InsertMedia": {"target": "private"}},
            },
        }
        calls, sleeps = [], []

        def fetch(path):
            calls.append(path)
            return responses[path]

        result = MODULE.probe(fetch, pause=sleeps.append)
        self.assertEqual(calls, list(responses))
        self.assertEqual(sleeps, [3] * 5)
        self.assertEqual(result["requests"], 6)
        self.assertTrue(result["capabilities"]["one_time_cd_boot_allowed"])
        self.assertFalse(result["capabilities"]["cd1_currently_inserted"])
        self.assertNotIn("DO_NOT_EMIT", str(result))
        self.assertNotIn("private", str(result))


if __name__ == "__main__":
    unittest.main()
