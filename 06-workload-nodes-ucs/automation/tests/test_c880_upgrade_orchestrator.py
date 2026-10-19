"""Offline-only tests for the future C880-4 chapter workflow and strict downgrade checks."""

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "c880_upgrade_orchestrator.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("c880_upgrade_orchestrator", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def pilot_signoff():
    return {
        "host": "ucs-c880-3",
        "manual_procedures_1_to_6_recorded": True,
        "independent_firmware_postcheck_passed": True,
        "independent_health_postcheck_passed": True,
        "upgrade_method_and_image_source_verified": True,
    }


class OrchestratorTests(unittest.TestCase):
    def test_offline_plan_selects_four_without_contact_or_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "host_vars").mkdir()
            (root / "group_vars").mkdir()
            (root / "group_vars" / "all.yml").write_text(
                "aipod:\n  dns_servers: [192.0.2.53]\n"
                "  ntp_servers: [192.0.2.123]\n",
                encoding="utf-8",
            )
            vault = root / "group_vars" / "vault.yml"
            vault.write_text("vault_c880_test_password: synthetic-only\n", encoding="utf-8")
            os.chmod(vault, 0o600)
            (root / "host_vars" / "ucs-c880-4.yml").write_text(
                "ucs:\n  platform: standalone\n  cimc:\n    ip: 192.0.2.44\n"
                "    user: private-user\n    pass_ref: C880_TEST_PASSWORD\n",
                encoding="utf-8",
            )
            plan = MODULE.offline_plan(root, "ucs-c880-4")
            self.assertFalse(plan["live_contact_allowed"])
            self.assertFalse(plan["firmware_execution_implemented"])
            self.assertTrue(plan["oob_offline_transition_replay_available"])
            self.assertFalse(plan["oob_live_backend_implemented"])
            self.assertEqual(plan["oob_task_poll_spacing_seconds"], 30)
            self.assertEqual(plan["oob_catalog_deadlines_seconds"]["BMC"], 2700)
            self.assertEqual(plan["minimum_health_probe_elapsed_seconds"], 45)
            for secret in ("192.0.2.44", "private-user", "synthetic-only"):
                self.assertNotIn(secret, str(plan))
            with self.assertRaises(ValueError):
                MODULE.offline_plan(root, "ucs-c845-1")

    def test_unknown_host_cannot_start_health_stage(self):
        calls = []

        def fetch(path):
            calls.append(path)
            raise AssertionError("No BMC request allowed")

        with self.assertRaises(ValueError):
            MODULE.run_get_only_health_stage(
                fetch,
                host="ucs-c845-1",
                pause=lambda _seconds: None,
            )
        self.assertEqual(calls, [])

    def test_four_synthetic_get_only_stage_is_paced_and_replayable(self):
        healthy = {
            "Status": {"Health": "OK", "State": "Enabled", "Conditions": []},
            "Secret": "DO_NOT_EMIT",
        }
        baseboard = "/redfish/v1/Systems/HGX_Baseboard_0"
        bmc = "/redfish/v1/Managers/HGX_BMC_0"
        processors = baseboard + "/Processors"
        switches = "/redfish/v1/Fabrics/HGX_NVLinkFabric_0/Switches"
        gpu_paths = [f"{processors}/{index}" for index in range(9)]
        switch_paths = [f"{switches}/{index}" for index in range(2)]
        responses = {
            "/redfish/v1/ServiceConditions": {"Conditions": []},
            baseboard: healthy,
            bmc: healthy,
            processors: {"Members": [{"@odata.id": p} for p in gpu_paths]},
            switches: {"Members": [{"@odata.id": p} for p in switch_paths]},
        }
        for path in gpu_paths[:8]:
            responses[path] = {**healthy, "ProcessorType": "GPU", "Model": "B300"}
        responses[gpu_paths[8]] = {**healthy, "ProcessorType": "FPGA"}
        for path in switch_paths:
            responses[path] = healthy
        calls, sleeps = [], []

        def fetch(path):
            calls.append(path)
            return responses[path]

        outcome = MODULE.run_get_only_health_stage(
            fetch,
            host="ucs-c880-4",
            pilot_evidence=pilot_signoff(),
            pause=sleeps.append,
        )
        self.assertEqual(outcome["baseline"]["host"], "ucs-c880-4")
        self.assertEqual(outcome["baseline"]["phase"], "pre_upgrade_reference")
        self.assertEqual(outcome["result"]["decision"], "pass_observed_snapshot")
        self.assertEqual(len(calls), 17)
        self.assertEqual(sleeps, [MODULE.MIN_REQUEST_SPACING_SECONDS] * 16)
        self.assertFalse(outcome["manual_or_firmware_actions_performed"])
        self.assertNotIn("DO_NOT_EMIT", str(outcome))


class DowngradeSafetyTests(unittest.TestCase):
    """Airtight tests ensuring zero loopholes exist to downgrade firmware or hardware."""

    def test_version_parser_handles_all_c880_component_formats(self):
        # BMC formats
        self.assertEqual(
            MODULE.parse_component_version("BMC", "4.0(2.260022)"), (4, 0, 2, 260022)
        )
        self.assertEqual(
            MODULE.parse_component_version("BMC", "4.0.2.260022"), (4, 0, 2, 260022)
        )
        self.assertEqual(
            MODULE.parse_component_version("BMC", "4.0(1.260014)"), (4, 0, 1, 260014)
        )

        # BIOS formats
        self.assertEqual(MODULE.parse_component_version("BIOS", "4.0.2.67"), (4, 0, 2, 67))
        self.assertEqual(MODULE.parse_component_version("BIOS", "4.0.2.73"), (4, 0, 2, 73))

        # GPU format: composite hex + G-build
        self.assertEqual(
            MODULE.parse_component_version("GPU", "97.10.7E.00.03-G540.0216.00.03"),
            (151, 16, 126, 0, 3, 540, 216, 0, 3),
        )

        # CPLDs
        self.assertEqual(MODULE.parse_component_version("MB-CPLD", "0.1.2.8"), (0, 1, 2, 8))
        self.assertEqual(
            MODULE.parse_component_version("DCSCM-CPLD", "0.1.0.1"), (0, 1, 0, 1)
        )
        self.assertEqual(MODULE.parse_component_version("BP-CPLD", "0.1.0.7"), (0, 1, 0, 7))

        # EROT
        self.assertEqual(MODULE.parse_component_version("EROT-BMC", "4.0.15"), (4, 0, 15))
        self.assertEqual(MODULE.parse_component_version("EROT-BIOS", "4.0.15"), (4, 0, 15))

        # Invalid/unparseable values fail closed to None
        self.assertIsNone(MODULE.parse_component_version("BMC", "UNKNOWN"))
        self.assertIsNone(MODULE.parse_component_version("BIOS", "N/A"))
        self.assertIsNone(MODULE.parse_component_version("GPU", "bad-format"))
        self.assertIsNone(MODULE.parse_component_version("BMC", None))
        self.assertIsNone(MODULE.parse_component_version("BMC", ""))

    def test_all_components_already_at_target_skips_cleanly(self):
        c880_target_inventory = {
            "BMC": ("4.0(2.260022)", "4.0(2.260022)"),
            "BIOS": ("4.0.2.67", "4.0.2.67"),
            "GPU": (
                "97.10.7E.00.03-G540.0216.00.03",
                "97.10.7E.00.03-G540.0216.00.03",
            ),
            "DCSCM-CPLD": ("0.1.0.1", "0.1.0.1"),
            "MB-CPLD": ("0.1.2.8", "0.1.2.8"),
            "E1S-BP-CPLD": ("0.1.0.7", "0.1.0.7"),
            "BP-CPLD": ("0.1.0.7", "0.1.0.7"),
            "EROT-BMC": ("4.0.15", "4.0.15"),
            "EROT-BIOS": ("4.0.15", "4.0.15"),
        }
        res = MODULE.check_downgrade_safety(c880_target_inventory)
        self.assertTrue(res["is_safe"])
        self.assertEqual(res["decision"], "ALL_ALREADY_TARGET")
        for comp, details in res["components"].items():
            self.assertEqual(details["status"], "SKIP_ALREADY_TARGET")

    def test_bmc_running_newer_strictly_blocks_downgrade(self):
        # Running patch version is higher than bundle
        inventory = {
            "BMC": ("4.0(2.260022)", "4.0(2.260009)"),
            "BIOS": ("4.0.2.67", "4.0.2.67"),
        }
        res = MODULE.check_downgrade_safety(inventory)
        self.assertFalse(res["is_safe"])
        self.assertEqual(res["decision"], "BLOCKED_DOWNGRADE")
        self.assertIn("BMC", res["blocked_components"])
        self.assertEqual(res["components"]["BMC"]["status"], "BLOCKED_DOWNGRADE")

    def test_bios_running_newer_strictly_blocks_downgrade(self):
        inventory = {
            "BMC": ("4.0(2.260022)", "4.0(2.260022)"),
            "BIOS": ("4.0.2.73", "4.0.2.67"),
        }
        res = MODULE.check_downgrade_safety(inventory)
        self.assertFalse(res["is_safe"])
        self.assertEqual(res["decision"], "BLOCKED_DOWNGRADE")
        self.assertIn("BIOS", res["blocked_components"])

    def test_gpu_running_newer_strictly_blocks_downgrade(self):
        inventory = {
            "GPU": (
                "97.10.7E.00.03-G540.0216.00.03",
                "97.10.64.00.0C-G540.0216.00.03",
            ),
        }
        res = MODULE.check_downgrade_safety(inventory)
        self.assertFalse(res["is_safe"])
        self.assertEqual(res["decision"], "BLOCKED_DOWNGRADE")
        self.assertIn("GPU", res["blocked_components"])

    def test_cpld_or_erot_running_newer_strictly_blocks_downgrade(self):
        inventory = {
            "MB-CPLD": ("0.1.2.9", "0.1.2.8"),
            "EROT-BMC": ("4.0.16", "4.0.15"),
        }
        res = MODULE.check_downgrade_safety(inventory)
        self.assertFalse(res["is_safe"])
        self.assertEqual(res["decision"], "BLOCKED_DOWNGRADE")
        self.assertIn("MB-CPLD", res["blocked_components"])
        self.assertIn("EROT-BMC", res["blocked_components"])

    def test_unverified_or_malformed_version_fails_closed(self):
        inventory = {
            "BMC": ("4.0(2.260022)", "UNKNOWN_REVISION"),
            "BIOS": ("4.0.2.67", "4.0.2.67"),
        }
        res = MODULE.check_downgrade_safety(inventory)
        self.assertFalse(res["is_safe"])
        self.assertEqual(res["decision"], "BLOCKED_VERSION_UNVERIFIED")
        self.assertIn("BMC", res["unverified_components"])

    def test_safe_upgrade_candidate_recognized_when_running_older(self):
        inventory = {
            "BMC": ("4.0(1.260014)", "4.0(2.260022)"),
            "BIOS": ("4.0.2.50", "4.0.2.67"),
            "GPU": (
                "97.10.7E.00.03-G540.0216.00.03",
                "97.10.7E.00.03-G540.0216.00.03",
            ),
        }
        res = MODULE.check_downgrade_safety(inventory)
        self.assertTrue(res["is_safe"])
        self.assertEqual(res["decision"], "UPGRADE_CANDIDATE")
        self.assertEqual(res["upgradable_components"], ["BMC", "BIOS"])

    def test_check_downgrade_safety_incomplete_inventory_blocked(self):
        # Discovery returned BMC and BIOS, but GPU was missing
        inventory = {
            "BMC": ("4.0(2.260022)", "4.0(2.260022)"),
            "BIOS": ("4.0.2.67", "4.0.2.67"),
        }
        res = MODULE.check_downgrade_safety(inventory, required_components=("BMC", "BIOS", "GPU"))
        self.assertFalse(res["is_safe"])
        self.assertEqual(res["decision"], "BLOCKED_INCOMPLETE_INVENTORY")
        self.assertIn("GPU", res["missing_components"])
        self.assertIn("missing required core components", res["reason"])


class HostGateTests(unittest.TestCase):
    def test_read_c880_host_succeeds_for_any_valid_standalone_gpu_server(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "host_vars").mkdir()
            (root / "group_vars").mkdir()
            vault = root / "group_vars" / "vault.yml"
            vault.write_text("vault_c880_test_password: secret\n", encoding="utf-8")
            os.chmod(vault, 0o600)

            for host, ip in (("ucs-c880-1", "203.0.113.81"), ("ucs-c880-4", "203.0.113.84")):
                (root / "host_vars" / f"{host}.yml").write_text(
                    f"ucs:\n  platform: standalone\n  role: gpu\n  cimc:\n    ip: {ip}\n"
                    "    user: admin\n    pass_ref: C880_TEST_PASSWORD\n",
                    encoding="utf-8",
                )
                ip_read, user, pref = MODULE._read_c880_host(root, host)
                self.assertEqual(ip_read, ip)
                self.assertEqual(user, "admin")
                self.assertEqual(pref, "C880_TEST_PASSWORD")

    def test_read_c880_host_rejects_non_standalone_or_non_gpu(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "host_vars").mkdir()
            (root / "host_vars" / "ucs-c880-1.yml").write_text(
                "ucs:\n  platform: domain\n  role: gpu\n  cimc:\n    ip: 203.0.113.81\n"
                "    user: admin\n    pass_ref: TEST_PW\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as ctx:
                MODULE._read_c880_host(root, "ucs-c880-1")
            self.assertIn("not a standalone GPU server", str(ctx.exception))

    def test_read_c880_host_rejects_unknown_host(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError) as ctx:
                MODULE._read_c880_host(root, "ucs-c845-1")
            self.assertIn("outside C880 workflow", str(ctx.exception))

    def test_target_exclusion_lock_protects_reference_hosts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for host in ("ucs-c880-3", "ucs-c880-4"):
                with self.assertRaises(RuntimeError) as ctx:
                    MODULE.run_live_oob_upgrade(root, host)
                self.assertIn("validated reference node", str(ctx.exception))
                self.assertIn(f"confirm_host='{host}'", str(ctx.exception))

    def test_run_huu_postcheck_invokes_audits_cleanly(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "host_vars").mkdir()
            (root / "group_vars").mkdir()
            (root / "group_vars" / "all.yml").write_text(
                "aipod:\n  dns_servers: [192.0.2.53]\n  domain_name: example.test\n"
                "  timezone: UTC\n  ntp_servers: [198.51.100.124, 198.51.100.125]\n",
                encoding="utf-8",
            )
            vault = root / "group_vars" / "vault.yml"
            vault.write_text("vault_c880_test_pw: synthetic-pass\n", encoding="utf-8")
            os.chmod(vault, 0o600)

            (root / "host_vars" / "ucs-c880-1.yml").write_text(
                "ucs:\n  platform: standalone\n  role: gpu\n  cimc:\n    ip: 203.0.113.81\n"
                "    user: admin\n    pass_ref: C880_TEST_PW\n",
                encoding="utf-8",
            )

            mock_huu = {"all_passed": True, "adapters": {}, "storage": {}}
            mock_persist = {"all_passed": True, "details": {}}

            with patch.object(MODULE, "RedfishReader"), \
                 patch.object(MODULE, "audit_huu_firmware", return_value=mock_huu) as mock_huu_fn, \
                 patch.object(MODULE, "audit_settings_persistence", return_value=mock_persist) as mock_persist_fn:
                
                res = MODULE.run_huu_postcheck(root, "ucs-c880-1")
                self.assertTrue(res["all_passed"])
                self.assertEqual(res["host"], "ucs-c880-1")
                self.assertEqual(res["huu_firmware"], mock_huu)
                self.assertEqual(res["settings_persistence"], mock_persist)
                mock_huu_fn.assert_called_once()
                mock_persist_fn.assert_called_once()

    def test_run_persistence_audit_invokes_audit_cleanly(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "host_vars").mkdir()
            (root / "group_vars").mkdir()
            (root / "group_vars" / "all.yml").write_text(
                "aipod:\n  dns_servers: [192.0.2.53]\n  domain_name: example.test\n"
                "  timezone: UTC\n  ntp_servers: [198.51.100.124, 198.51.100.125]\n",
                encoding="utf-8",
            )
            vault = root / "group_vars" / "vault.yml"
            vault.write_text("vault_c880_test_pw: synthetic-pass\n", encoding="utf-8")
            os.chmod(vault, 0o600)

            (root / "host_vars" / "ucs-c880-1.yml").write_text(
                "ucs:\n  platform: standalone\n  role: gpu\n  hostname: AIPOD-UCS-C880-1\n  cimc:\n    ip: 203.0.113.81\n"
                "    user: admin\n    pass_ref: C880_TEST_PW\n",
                encoding="utf-8",
            )

            mock_persist = {"all_passed": True, "details": {}}

            with patch.object(MODULE, "RedfishReader"), \
                 patch.object(MODULE, "audit_settings_persistence", return_value=mock_persist) as mock_persist_fn:

                res = MODULE.run_persistence_audit(root, "ucs-c880-1")
                self.assertTrue(res["all_passed"])
                self.assertEqual(res["host"], "ucs-c880-1")
                self.assertEqual(res["settings_persistence"], mock_persist)
                mock_persist_fn.assert_called_once()


class PostActivationWaitTests(unittest.TestCase):
    def test_wait_succeeds_after_settle_and_retries(self):
        calls = []
        sleeps = []
        current_time = [1000.0]

        def fake_time():
            return current_time[0]

        def fake_pause(seconds):
            sleeps.append(seconds)
            current_time[0] += seconds

        bmc_attempts = [0]
        host_attempts = [0]

        def fake_reader(path):
            calls.append(path)
            if path == "/redfish/v1/":
                bmc_attempts[0] += 1
                if bmc_attempts[0] < 3:
                    raise ConnectionResetError("Connection reset by peer")
                return {"Systems": {"@odata.id": "/redfish/v1/Systems"}}
            if path == "/redfish/v1/Systems/DGX":
                host_attempts[0] += 1
                if host_attempts[0] < 2:
                    return {"PowerState": "Off"}
                return {"PowerState": "On", "Status": {"Health": "OK"}}
            raise ValueError(f"Unexpected path: {path}")

        logs = []
        result = MODULE.wait_for_bmc_and_host_ready(
            fake_reader,
            initial_settle_seconds=300,
            bmc_timeout_seconds=600,
            host_timeout_seconds=600,
            poll_interval_seconds=30,
            pause=fake_pause,
            time_fn=fake_time,
            logger=logs.append,
        )
        self.assertTrue(result)
        self.assertEqual(sleeps[0], 300)  # 5-minute settle period respected
        self.assertEqual(sleeps[1:], [30, 30, 30])  # Retries respected
        self.assertIn("/redfish/v1/", calls)
        self.assertIn("/redfish/v1/Systems/DGX", calls)
        self.assertTrue(any("online" in m.lower() for m in logs))
        self.assertTrue(any("on" in m.lower() for m in logs))

    def test_wait_bmc_timeout_raises_timeout_error(self):
        current_time = [1000.0]

        def fake_time():
            return current_time[0]

        def fake_pause(seconds):
            current_time[0] += seconds

        def fake_reader(path):
            raise ConnectionRefusedError("Offline")

        with self.assertRaises(TimeoutError) as ctx:
            MODULE.wait_for_bmc_and_host_ready(
                fake_reader,
                initial_settle_seconds=0,
                bmc_timeout_seconds=120,
                host_timeout_seconds=120,
                poll_interval_seconds=30,
                pause=fake_pause,
                time_fn=fake_time,
            )
        self.assertIn("BMC HTTPS Redfish service did not come online", str(ctx.exception))

    def test_wait_host_timeout_raises_timeout_error(self):
        current_time = [1000.0]

        def fake_time():
            return current_time[0]

        def fake_pause(seconds):
            current_time[0] += seconds

        def fake_reader(path):
            if path == "/redfish/v1/":
                return {"Systems": {"@odata.id": "/redfish/v1/Systems"}}
            if path == "/redfish/v1/Systems/DGX":
                return {"PowerState": "Off"}
            raise ValueError(path)

        with self.assertRaises(TimeoutError) as ctx:
            MODULE.wait_for_bmc_and_host_ready(
                fake_reader,
                initial_settle_seconds=0,
                bmc_timeout_seconds=120,
                host_timeout_seconds=120,
                poll_interval_seconds=30,
                pause=fake_pause,
                time_fn=fake_time,
            )
        self.assertIn("Host DGX subsystem did not reach PowerState 'On'", str(ctx.exception))


class TelemetrySchemaAndExportTests(unittest.TestCase):
    """Airtight tests verifying D52 structured JSON telemetry and two-tier web UI schema contract."""

    @classmethod
    def setUpClass(cls):
        schema_path = (
            Path(__file__).resolve().parents[3]
            / "schemas"
            / "telemetry"
            / "workload-nodes-ucs.telemetry.schema.json"
        )
        cls.schema = json.loads(schema_path.read_text(encoding="utf-8"))

    def test_generate_component_table_maps_badges_and_actions(self):
        components_input = {
            "BMC": {"running": "4.0(1.260014)", "packaged": "4.0(2.260022)", "status": "UPGRADE_REQUIRED"},
            "BIOS": {"running": "4.0.2.67", "packaged": "4.0.2.67", "status": "SKIP_ALREADY_TARGET"},
            "GPU": {"running": "97.10.7E.00.03", "packaged": "97.10.64.00.0C", "status": "BLOCKED_DOWNGRADE"},
            "CPLD": {"running": "0.1.0.1", "packaged": "0.1.0.1", "status": "SKIP_ALREADY_TARGET"},
        }
        table = MODULE.generate_component_table(components_input)
        self.assertEqual(len(table), 4)

        # Core components (BMC, BIOS, GPU) must be sorted to the front and marked critical
        self.assertTrue(table[0]["critical"])
        self.assertTrue(table[1]["critical"])
        self.assertTrue(table[2]["critical"])
        self.assertFalse(table[3]["critical"])

        by_comp = {row["component"]: row for row in table}
        self.assertEqual(by_comp["BMC"]["action"], "FLASH")
        self.assertEqual(by_comp["BMC"]["badge"]["variant"], "warning")
        self.assertEqual(by_comp["BIOS"]["action"], "SKIP")
        self.assertEqual(by_comp["BIOS"]["badge"]["variant"], "success")
        self.assertEqual(by_comp["GPU"]["action"], "ABORT")
        self.assertEqual(by_comp["GPU"]["badge"]["variant"], "danger")

    def test_build_structured_telemetry_validates_against_schema(self):
        import jsonschema

        components_input = {
            "BMC": {"running": "4.0(1.260014)", "packaged": "4.0(2.260022)", "status": "UPGRADE_REQUIRED"},
            "BIOS": {"running": "4.0.2.67", "packaged": "4.0.2.67", "status": "SKIP_ALREADY_TARGET"},
            "GPU": {"running": "97.10.7E.00.03-G540.0216.00.03", "packaged": "97.10.7E.00.03-G540.0216.00.03", "status": "SKIP_ALREADY_TARGET"},
        }
        telemetry = MODULE.build_structured_telemetry(
            host="ucs-c880-1",
            phase="upgrade_execution",
            components_dict=components_input,
            safety_decision="UPGRADE_CANDIDATE",
            reason="Components to update: BMC.",
            pre_health="pass_observed_snapshot",
            post_health="pass_observed_snapshot",
            settings_persistence={"all_passed": True, "details": {}},
            log_lines=[
                "[22:00:00.000] Discovered BMC running 4.0(1.260014)",
                "[22:00:05.123] Invoking vendor flash update",
                "[22:15:30.456] Power cycle completed successfully",
            ],
            power_cycle_required=True,
        )

        # Strict JSON Schema validation
        jsonschema.validate(instance=telemetry, schema=self.schema)

        # Inspect summary cards structure
        summary = telemetry["summary"]
        self.assertEqual(summary["decision"], "UPGRADE_CANDIDATE")
        self.assertEqual(summary["badge"]["label"], "Upgrade Ready")
        self.assertEqual(summary["badge"]["variant"], "primary")
        self.assertEqual(summary["total_components"], 3)
        self.assertEqual(summary["upgradable_count"], 1)
        self.assertEqual(summary["up_to_date_count"], 2)
        self.assertEqual(summary["blocked_count"], 0)
        self.assertTrue(summary["power_cycle_required"])
        self.assertEqual(summary["pre_health"], "pass_observed_snapshot")
        self.assertEqual(summary["post_health"], "pass_observed_snapshot")

        # Inspect raw console drawer
        drawer = telemetry["console_drawer"]
        self.assertEqual(drawer["total_lines"], 3)
        self.assertTrue(drawer["collapsible"])
        self.assertFalse(drawer["default_expanded"])

    def test_offline_plan_generates_schema_compliant_telemetry(self):
        import jsonschema

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "host_vars").mkdir()
            (root / "group_vars").mkdir()
            (root / "group_vars" / "all.yml").write_text(
                "aipod:\n  dns_servers: [192.0.2.53]\n  ntp_servers: [192.0.2.123]\n",
                encoding="utf-8",
            )
            vault = root / "group_vars" / "vault.yml"
            vault.write_text("vault_c880_test_pw: synthetic-pass\n", encoding="utf-8")
            os.chmod(vault, 0o600)
            (root / "host_vars" / "ucs-c880-4.yml").write_text(
                "ucs:\n  platform: standalone\n  role: gpu\n  cimc:\n    ip: 203.0.113.84\n"
                "    user: admin\n    pass_ref: C880_TEST_PW\n",
                encoding="utf-8",
            )

            plan = MODULE.offline_plan(root, "ucs-c880-4")
            self.assertIn("telemetry", plan)
            telemetry = plan["telemetry"]
            jsonschema.validate(instance=telemetry, schema=self.schema)
            self.assertEqual(telemetry["phase"], "offline_plan")
            self.assertEqual(telemetry["summary"]["decision"], "OFFLINE_PLAN")
            self.assertEqual(telemetry["summary"]["badge"]["variant"], "info")
            self.assertEqual(telemetry["summary"]["total_components"], 5)
            self.assertFalse(telemetry["summary"]["power_cycle_required"])

    def test_downgrade_blocked_telemetry_generation(self):
        import jsonschema

        components_input = {
            "BMC": {"running": "4.0(2.260022)", "packaged": "4.0(2.260009)", "status": "BLOCKED_DOWNGRADE"},
            "BIOS": {"running": "4.0.2.67", "packaged": "4.0.2.67", "status": "SKIP_ALREADY_TARGET"},
        }
        telemetry = MODULE.build_structured_telemetry(
            host="ucs-c880-3",
            phase="pre_upgrade_discovery",
            components_dict=components_input,
            safety_decision="BLOCKED_DOWNGRADE",
            reason="Downgrade strictly prohibited: BMC running newer firmware than bundle.",
            pre_health="pass_observed_snapshot",
            log_lines=["[22:00:00.000] Blocked downgrade detected on BMC"],
        )

        jsonschema.validate(instance=telemetry, schema=self.schema)
        self.assertEqual(telemetry["summary"]["decision"], "BLOCKED_DOWNGRADE")
        self.assertEqual(telemetry["summary"]["badge"]["label"], "Downgrade Blocked")
        self.assertEqual(telemetry["summary"]["badge"]["variant"], "danger")
        self.assertEqual(telemetry["summary"]["blocked_count"], 1)

    def test_telemetry_file_and_telemetry_only_cli_flags(self):
        import subprocess

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "host_vars").mkdir()
            (root / "group_vars").mkdir()
            (root / "group_vars" / "all.yml").write_text(
                "aipod:\n  dns_servers: [192.0.2.53]\n  ntp_servers: [192.0.2.123]\n",
                encoding="utf-8",
            )
            vault = root / "group_vars" / "vault.yml"
            vault.write_text("vault_c880_test_pw: synthetic-pass\n", encoding="utf-8")
            os.chmod(vault, 0o600)
            (root / "host_vars" / "ucs-c880-2.yml").write_text(
                "ucs:\n  platform: standalone\n  role: gpu\n  cimc:\n    ip: 203.0.113.82\n"
                "    user: admin\n    pass_ref: C880_TEST_PW\n",
                encoding="utf-8",
            )

            telemetry_out = root / "telemetry.json"
            cmd = [
                sys.executable,
                str(MODULE.Path(MODULE.__file__)),
                str(root),
                "--host",
                "ucs-c880-2",
                "--telemetry-file",
                str(telemetry_out),
                "--telemetry-only",
                # Keep run artifacts inside the temp dir; the default root is in the repo.
                "--run-log-root",
                str(root / "run-logs"),
            ]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(proc.returncode, 0, f"Process failed: {proc.stderr}")

            # Verify stdout is pure telemetry object
            stdout_data = json.loads(proc.stdout)
            self.assertEqual(stdout_data["telemetry_type"], "c880_upgrade_telemetry")
            self.assertEqual(stdout_data["host"], "ucs-c880-2")
            self.assertEqual(stdout_data["phase"], "offline_plan")

            # Verify file was written
            self.assertTrue(telemetry_out.is_file())
            self.assertEqual(oct(telemetry_out.stat().st_mode)[-3:], "600")
            file_data = json.loads(telemetry_out.read_text(encoding="utf-8"))
            self.assertEqual(file_data, stdout_data)

            # Per-run artifacts: the directory, the run-complete telemetry copy,
            # and the `latest` symlink a supervising process reads.
            artifacts = stdout_data["artifacts"]
            self.assertTrue(artifacts["run_id"].endswith("-ucs-c880-2-plan"))
            self.assertTrue(Path(artifacts["telemetry_file"]).is_file())
            self.assertEqual(oct(Path(artifacts["telemetry_file"]).stat().st_mode)[-3:], "600")
            self.assertEqual(
                json.loads(Path(artifacts["telemetry_file"]).read_text(encoding="utf-8")),
                stdout_data,
            )
            self.assertEqual(
                (root / "run-logs" / "latest").resolve(),
                Path(artifacts["run_dir"]).resolve(),
            )

    def test_no_run_logs_writes_nothing_and_omits_artifacts(self):
        telemetry = MODULE.build_structured_telemetry(
            host="ucs-c880-2",
            phase="offline_plan",
            components_dict={},
            safety_decision="SAFE",
            reason="synthetic",
        )
        self.assertNotIn("artifacts", telemetry)

    def test_run_log_writes_through_and_scrubs_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            log = MODULE.RunLog(run_dir=run_dir, secrets=["synthetic-pass"])
            log("connecting with synthetic-pass")

            # Readable before the run ends — this is what makes a live log view possible.
            raw = log.raw_log_path.read_text(encoding="utf-8")
            self.assertIn("[REDACTED_SECRET]", raw)
            self.assertNotIn("synthetic-pass", raw)
            self.assertEqual(oct(log.raw_log_path.stat().st_mode)[-3:], "600")
            log.close()

    def test_run_log_context_closes_handle_when_work_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            handle = None
            with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                with MODULE.RunLog(run_dir=run_dir) as log:
                    handle = log._handle
                    raise RuntimeError("synthetic failure")
            self.assertTrue(handle.closed)

    def test_vendor_output_and_logging_are_scrubbed_into_raw_log(self):
        with tempfile.TemporaryDirectory() as directory:
            log = MODULE.RunLog(Path(directory) / "run", secrets=["synthetic-pass"])
            try:
                with MODULE.capture_vendor_output(log):
                    print("vendor synthetic-pass")
                    sys.stderr.write("vendor error synthetic-pass\n")
                    import logging
                    logging.getLogger("vendor.test").warning("warning synthetic-pass")
            finally:
                log.close()
            raw = log.raw_log_path.read_text("utf-8")
            self.assertIn("[vendor] vendor [REDACTED_SECRET]", raw)
            self.assertIn("[vendor stderr] vendor error [REDACTED_SECRET]", raw)
            self.assertIn("[vendor log] vendor.test: warning [REDACTED_SECRET]", raw)
            self.assertNotIn("synthetic-pass", raw)

    def test_run_log_without_run_dir_stays_in_memory(self):
        log = MODULE.RunLog(secrets=["synthetic-pass"])
        log("connecting with synthetic-pass")
        self.assertIsNone(log.raw_log_path)
        self.assertIn("[REDACTED_SECRET]", log.lines[0])

    def test_run_status_marks_a_clean_finish_succeeded(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            run_dir.mkdir()
            MODULE.write_run_status(run_dir, "succeeded", exit_code=0, started_utc="t0")
            status = json.loads((run_dir / "status.json").read_text("utf-8"))
            self.assertEqual(status["state"], "succeeded")
            self.assertEqual(status["exit_code"], 0)
            self.assertIsNotNone(status["ended_utc"])

    def test_run_status_running_has_no_end_time(self):
        """A run in progress must be distinguishable from one that finished."""
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            run_dir.mkdir()
            MODULE.write_run_status(run_dir, "running", started_utc="t0")
            status = json.loads((run_dir / "status.json").read_text("utf-8"))
            self.assertEqual(status["state"], "running")
            self.assertIsNone(status["ended_utc"])
            self.assertEqual(status["pid"], os.getpid())
            self.assertTrue(status["heartbeat_utc"].endswith("+00:00"))

    def test_run_status_error_is_scrubbed(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            run_dir.mkdir()
            scrubber = MODULE.RunLog(secrets=["synthetic-pass"])
            status = MODULE.write_run_status(
                run_dir, "failed", exit_code=2, error="failed with synthetic-pass",
                started_utc="2026-01-01T00:00:00+00:00", scrubber=scrubber,
            )
            self.assertEqual(status["error"], "failed with [REDACTED_SECRET]")

    def test_only_zero_exit_is_succeeded(self):
        self.assertEqual(MODULE.run_state_for_exit(0), "succeeded")
        for code in (1, 2, 3, 130, 143):
            self.assertEqual(MODULE.run_state_for_exit(code), "failed")

    def test_run_directories_are_unique_private_and_latest_is_repointed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run-logs"
            first = MODULE.make_run_dir(root, "ucs-c880-2", "plan")
            second = MODULE.make_run_dir(root, "ucs-c880-2", "plan")
            self.assertNotEqual(first, second)
            self.assertIn(".", first.name.split("Z")[0])
            self.assertEqual(oct(root.stat().st_mode)[-3:], "700")
            self.assertEqual(oct(first.stat().st_mode)[-3:], "700")
            self.assertEqual((root / "latest").resolve(), second.resolve())

    def test_retention_keeps_twenty_completed_and_all_running_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run-logs"
            root.mkdir(mode=0o700)
            completed = []
            for index in range(22):
                run = root / f"20260101T0000{index:02d}.000000Z-ucs-c880-2-plan"
                run.mkdir(mode=0o700)
                MODULE.write_run_status(run, "failed", exit_code=2, started_utc="t0")
                os.utime(run, (index, index))
                completed.append(run)
            running = root / "20260102T000000.000000Z-ucs-c880-2-live-upgrade"
            running.mkdir(mode=0o700)
            MODULE.write_run_status(running, "running", started_utc="t0")

            removed = MODULE.prune_completed_runs(root, "ucs-c880-2", keep=20)

            self.assertEqual(len(removed), 2)
            self.assertTrue(running.exists())
            self.assertEqual(sum(path.exists() for path in completed), 20)

    def test_crashed_run_is_not_mistaken_for_a_running_one(self):
        """The gap this file exists to close: a run that dies partway through
        must not look identical to one still working."""
        import subprocess

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_root = root / "run-logs"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(MODULE.Path(MODULE.__file__)),
                    "/nonexistent/inventory",
                    "--host",
                    "ucs-c880-2",
                    "--run-log-root",
                    str(run_root),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)

            status = json.loads((run_root / "latest" / "status.json").read_text("utf-8"))
            self.assertEqual(status["state"], "failed")
            self.assertEqual(status["exit_code"], proc.returncode)
            self.assertIn("Starting plan run for host ucs-c880-2", (run_root / "latest" / "raw.log").read_text("utf-8"))
            self.assertIsNotNone(status["error"])
            self.assertEqual(oct((run_root / "latest").stat().st_mode)[-3:], "700")
            self.assertEqual(oct((run_root / "latest" / "status.json").stat().st_mode)[-3:], "600")
            # Operational errors can leave telemetry absent; status is authoritative.
            self.assertFalse((run_root / "latest" / "telemetry.json").exists())

    def test_run_status_example_matches_its_schema(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "20260101T000000Z-ucs-c880-2-plan"
            run_dir.mkdir()
            MODULE.write_run_status(run_dir, "failed", exit_code=143,
                                    error="SystemExit: 143", started_utc="2026-01-01T00:00:00+00:00")
            repo = Path(MODULE.__file__).resolve().parents[3]
            schema = json.loads(
                (repo / "schemas/telemetry/run-status.schema.json").read_text("utf-8")
            )
            jsonschema.validate(
                json.loads((run_dir / "status.json").read_text("utf-8")), schema
            )

    def test_published_example_matches_the_schema(self):
        """The example payload is what the front end codes against, so it must
        stay valid and must never carry a real path or address."""
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")
        repo = Path(MODULE.__file__).resolve().parents[3]
        example = json.loads(
            (repo / "schemas/telemetry/_examples/workload-nodes-ucs.telemetry.example.json").read_text("utf-8")
        )
        schema = json.loads(
            (repo / "schemas/telemetry/workload-nodes-ucs.telemetry.schema.json").read_text("utf-8")
        )
        jsonschema.validate(example, schema)
        self.assertNotIn("/Users/", json.dumps(example))
        invalid = dict(example)
        invalid["settings_persistence"] = {"all_passed": True, "details": {}, "unexpected": 1}
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)


if __name__ == "__main__":
    unittest.main()
