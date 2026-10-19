"""Offline tests for the sanitized C880 firmware inventory comparison."""

import importlib.util
from pathlib import Path
import sys
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "probe_c880_firmware_readonly.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("probe_c880_firmware_readonly", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FirmwareTests(unittest.TestCase):
    def test_serial_reads_and_sanitized_output(self):
        responses = {
            "/redfish/v1/UpdateService/FirmwareInventory": {
                "Members": [
                    {"@odata.id": "/redfish/v1/UpdateService/FirmwareInventory/GPU"},
                    {"@odata.id": "/redfish/v1/UpdateService/FirmwareInventory/OTHER"},
                ]
            },
            "/redfish/v1/UpdateService/FirmwareInventory/GPU": {
                "Version": MODULE.TARGET_VERSIONS["gpu"],
                "Status": {"Health": "OK"},
                "Secret": "DO_NOT_EMIT",
            },
            "/redfish/v1/UpdateService/FirmwareInventory/OTHER": {
                "Version": "synthetic-fixture",
                "Status": {"Health": "Warning"},
            },
        }
        calls, sleeps = [], []

        def fetch(path):
            calls.append(path)
            return responses[path]

        result = MODULE.probe(fetch, pause=sleeps.append)
        self.assertEqual(calls, list(responses))
        self.assertEqual(sleeps, [3, 3])
        self.assertTrue(result["target_version_presence"]["gpu"])
        self.assertEqual(result["members_reporting_non_ok_health"], 1)
        self.assertNotIn("DO_NOT_EMIT", str(result))
        self.assertNotIn("synthetic-fixture", str(result))

    def test_pagination_and_excessive_inventory_fail_closed(self):
        with self.assertRaises(ValueError):
            MODULE.probe(lambda path: {"Members": [], "Members@odata.nextLink": "private"})
        with self.assertRaises(ValueError):
            MODULE.probe(lambda path: {"Members": [{}] * (MODULE.MAX_MEMBERS + 1)})


if __name__ == "__main__":
    unittest.main()
