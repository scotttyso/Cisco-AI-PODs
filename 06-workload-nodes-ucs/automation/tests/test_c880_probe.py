"""Offline safety and pacing tests for the one-server C880 probe."""

import importlib.util
from pathlib import Path
import os
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "probe_c880_readonly.py"
SPEC = importlib.util.spec_from_file_location("probe_c880_readonly", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ProbeTests(unittest.TestCase):
    def test_live_probe_accepts_valid_c880_hosts_and_rejects_others(self):
        for host in ("ucs-c880-1", "ucs-c880-2", "ucs-c880-3", "ucs-c880-4"):
            with self.subTest(host=host):
                ip, user, pass_ref = MODULE._read_host(Path("inventories/example"), host)
                self.assertTrue(ip.startswith("203.0.113."))
                self.assertEqual(user, "admin")
        for bad_host in ("ucs-c880-5", "unknown-host", "nd-1"):
            with self.subTest(host=bad_host), self.assertRaises(ValueError):
                MODULE._read_host(Path("inventories/example"), bad_host)

    def test_inventory_vault_reference_is_resolved_without_a_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            vault_dir = Path(directory) / "group_vars"
            vault_dir.mkdir()
            vault_file = vault_dir / "vault.yml"
            vault_file.write_text("vault_fixture_ref: synthetic-fixture-only\n", encoding="utf-8")
            os.chmod(vault_file, 0o600)
            self.assertEqual(
                MODULE._read_vault_password(directory, "FIXTURE_REF"),
                "synthetic-fixture-only",
            )
            with self.assertRaises(ValueError):
                MODULE._read_vault_password(directory, "MISSING_REF")
            os.chmod(vault_file, 0o644)
            with self.assertRaises(ValueError):
                MODULE._read_vault_password(directory, "FIXTURE_REF")

    def test_five_serial_gets_are_paced_and_output_is_sanitized(self):
        responses = {
            "/redfish/v1/": {
                "Systems": {"@odata.id": "/redfish/v1/Systems"},
                "Managers": {"@odata.id": "/redfish/v1/Managers"},
            },
            "/redfish/v1/Systems": {
                "Members": [
                    {"@odata.id": "/redfish/v1/Systems/DGX"},
                    {"@odata.id": "/redfish/v1/Systems/HGX_Baseboard_0"},
                ]
            },
            "/redfish/v1/Systems/DGX": {
                "PowerState": "On",
                "BiosVersion": "C880M8.4.0.2.67",
                "Status": {"Health": "OK"},
                "ProcessorSummary": {"Count": 2, "Status": {"Health": "OK"}},
                "MemorySummary": {"Status": {"Health": "OK"}},
                "SerialNumber": "DO_NOT_EMIT",
            },
            "/redfish/v1/Managers": {
                "Members": [
                    {"@odata.id": "/redfish/v1/Managers/BMC"},
                    {"@odata.id": "/redfish/v1/Managers/HGX_BMC_0"},
                ]
            },
            "/redfish/v1/Managers/BMC": {
                "FirmwareVersion": "4.0(2.260022)",
                "Status": {"Health": "OK"},
                "Secret": "DO_NOT_EMIT",
            },
        }
        calls = []
        sleeps = []

        def fetch(path):
            calls.append(path)
            return responses[path]

        result = MODULE.probe(fetch, pause=sleeps.append)
        self.assertEqual(calls, list(responses))
        self.assertEqual(sleeps, [3, 3, 3, 3])
        self.assertTrue(all(result["checks"].values()))
        self.assertTrue(all(result["release_checks"].values()))
        self.assertFalse(result["live_execution_allowed"])
        self.assertNotIn("DO_NOT_EMIT", str(result))
        self.assertNotIn("C880M8.4.0.2.67", str(result))

    def test_rejects_external_or_ambiguous_resource_paths(self):
        for value in ["https://other/redfish/v1/Systems", "/redfish/v1/../secret", "//other/redfish/v1/Systems"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                MODULE._resource_path(value)

    def test_missing_documented_system_fails_before_additional_reads(self):
        calls = []
        sleeps = []

        def fetch(path):
            calls.append(path)
            if len(calls) == 1:
                return {"Systems": {"@odata.id": "/redfish/v1/Systems"}}
            return {"Members": [{"@odata.id": "/redfish/v1/Systems/HGX_Baseboard_0"}]}

        with self.assertRaises(ValueError):
            MODULE.probe(fetch, pause=sleeps.append)
        self.assertEqual(len(calls), 2)
        self.assertEqual(sleeps, [3])


if __name__ == "__main__":
    unittest.main()
