import copy
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("nd_stage_nexus_updates", ROOT / "scripts/nd_stage_nexus_updates.py")
staging = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = staging
SPEC.loader.exec_module(staging)


class CatalogClient:
    def __init__(self):
        self.calls = []
        self.group = {}
        self.catalog = [
            {
                "reportCheckName": name,
                "checkType": "advanced" if "stability" in name else "basic",
                "cliCommand": "show vpc" if "vpc" in name.casefold() else "show module",
                "postUpdateDelay": 0,
                "advancedChecks": [{"checkMustContains": ["preserve-me"]}],
            }
            for name in staging.REQUESTED_CHECK_NAMES
        ]

    def request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if "/updateGroups/" in path:
            if method == "PUT":
                self.group = payload
            return self.group
        if method == "POST" and path == staging.REPORT_CHECKS:
            self.catalog.extend(payload["updateChecks"])
        if method == "PUT" and path.startswith(staging.REPORT_CHECKS):
            self.catalog = [
                payload if item["reportCheckName"] == payload["reportCheckName"] else item
                for item in self.catalog
            ]
        if method == "GET" and path != staging.REPORT_CHECKS:
            return next(item for item in self.catalog
                        if item["reportCheckName"] == path.rsplit("/", 1)[-1])
        return {"updateChecks": self.catalog}


class StageNexusUpdatesTests(unittest.TestCase):
    def switch(self, model="N9K-C9508", peer="peer", role="primary"):
        return staging.Switch("SERIAL", "switch", "192.0.2.1", model, "10.3(8)",
                              "n9k", peer, role, "Management")

    def test_custom_replacements_leave_defaults_unchanged(self):
        client = CatalogClient()
        original = copy.deepcopy(client.catalog)
        current, checks = staging.load_check_catalog(client)
        self.assertEqual(len(checks), 21)
        self.assertTrue(all(check["reportCheckName"].startswith("nxos_") for check in checks))
        self.assertEqual(client.catalog, original)
        self.assertTrue(all(method == "GET" for method, _, _ in client.calls))
        staging.ensure_check_catalog(client, current, checks)
        source_count = len(original)
        self.assertEqual(client.catalog[:source_count], original)
        for before, after in zip(original, client.catalog[source_count:]):
            self.assertEqual(after, dict(before, postUpdateDelay=360, checkType="custom",
                                        reportCheckName="nxos_" + before["reportCheckName"]))
        added = {item["reportCheckName"]: item for item in client.catalog[2 * source_count:]}
        self.assertEqual(added["nxos_Running_config"]["cliCommand"], "show running-config")
        self.assertEqual(added["nxos_Default_route"]["cliCommand"], "show ip route 0.0.0.0 vrf all")
        self.assertTrue(all(item["postUpdateDelay"] == 360 for item in added.values()))
        create = next(payload for method, _, payload in client.calls if method == "POST")
        self.assertTrue(all(check["postUpdateDelay"] == 0 for check in create["updateChecks"]))
        before_retry = len(client.calls)
        current, checks = staging.load_check_catalog(client)
        staging.ensure_check_catalog(client, current, checks)
        self.assertTrue(all(method == "GET" for method, _, _ in client.calls[before_retry:]))

    def test_mac_address_check_does_not_require_existing_definition(self):
        client = CatalogClient()
        client.catalog = [check for check in client.catalog if check["reportCheckName"] != "mac_address"]
        original = copy.deepcopy(client.catalog)
        current, checks = staging.load_check_catalog(client)
        mac_check = next(check for check in checks if check["reportCheckName"] == "nxos_mac_address")
        self.assertEqual(mac_check["cliCommand"], "show mac address dynamic | sort")
        self.assertEqual(mac_check["checkType"], "custom")
        self.assertEqual(mac_check["postUpdateDelay"], 360)
        self.assertEqual(mac_check["advancedChecks"], [])
        staging.ensure_check_catalog(client, current, checks)
        self.assertEqual(client.catalog[:len(original)], original)
        self.assertEqual(next(check for check in client.catalog
                              if check["reportCheckName"] == "nxos_mac_address"), mac_check)

    def test_existing_mac_address_definition_is_unchanged(self):
        client = CatalogClient()
        client.catalog = [check for check in client.catalog if check["reportCheckName"] != "mac_address"]
        existing = dict(client.catalog[0], reportCheckName="mac_address",
                        cliCommand="show mac address dynamic | sort")
        client.catalog.append(copy.deepcopy(existing))
        current, checks = staging.load_check_catalog(client)
        staging.ensure_check_catalog(client, current, checks)
        self.assertEqual(next(check for check in client.catalog
                              if check["reportCheckName"] == "mac_address"), existing)

    def test_missing_check_fails_without_creating_it(self):
        client = CatalogClient()
        client.catalog.pop()
        with self.assertRaisesRegex(ValueError, "OSPF_state"):
            staging.load_check_catalog(client)
        self.assertEqual(len(client.calls), 1)

    def test_device_specific_selection(self):
        _, checks = staging.load_check_catalog(CatalogClient())
        chassis = self.switch()
        self.assertTrue(all(staging.check_applies_to_switch(check, chassis) for check in checks))
        standalone = self.switch("N9K-C93108TC-EX", "none", "none")
        names = [check["reportCheckName"] for check in checks
                 if staging.check_applies_to_switch(check, standalone)]
        self.assertEqual(len(names), 17)
        self.assertIn("nxos_Interface_status", names)
        self.assertIn("nxos_Running_config", names)
        self.assertIn("nxos_Default_route", names)
        self.assertIn("nxos_mac_address", names)
        self.assertFalse(any("vpc" in name.casefold() for name in names))
        self.assertNotIn("nxos_Dual_supervisor_redundancy", names)

    def test_group_report_request_uses_existing_names(self):
        client = CatalogClient()
        switch = self.switch()
        names = tuple("nxos_" + name for name in staging.REQUESTED_CHECK_NAMES)
        plan = staging.Plan((switch,), "10.6.4", "image.bin", "group", names)
        staging.apply_plan(client, plan, client.catalog, [], True)
        methods_and_paths = [(method, path) for method, path, _ in client.calls]
        self.assertFalse(any("prePostCustomReport" in path for _, path in methods_and_paths))
        self.assertTrue(client.calls[2][1].endswith("startPreReport"))
        self.assertTrue(client.calls[-1][1].endswith("actions/stage"))
        self.assertEqual(client.calls[0][2]["updateReportChecks"],
                         [{"reportCheckName": name} for name in names])

    def test_overlapping_default_selection_blocks_staging(self):
        client = CatalogClient()
        switch = self.switch()
        names = tuple("nxos_" + name for name in staging.REQUESTED_CHECK_NAMES)
        plan = staging.Plan((switch,), "10.6.4", "image.bin", "group", names)
        original_request = client.request

        def with_default(method, path, payload=None):
            result = original_request(method, path, payload)
            if method == "GET" and "/updateGroups/" in path:
                result = dict(result, updateReportChecks=result["updateReportChecks"]
                              + [{"reportCheckName": "Diag_module"}])
            return result

        client.request = with_default
        with self.assertRaisesRegex(RuntimeError, "custom-only"):
            staging.apply_plan(client, plan, client.catalog, [], True)
        self.assertFalse(any(method == "POST" for method, _, _ in client.calls))

    def test_named_group_plan_and_validation(self):
        _, checks = staging.load_check_catalog(CatalogClient())
        images = [{"imageName": "nxos64-cs.10.6.4.M.bin", "releaseVersion": "10.6.4", "platform": "N9K"}]
        a = staging.Switch("S1", "leaf1", "192.0.2.1", "N9K-C93180YC-FX", "10.3(8)", "n9k", "leaf2", "primary", "F1")
        b = staging.Switch("S2", "leaf2", "192.0.2.2", "N9K-C93180YC-FX", "10.3(8)", "n9k", "leaf1", "secondary", "F1")
        plan = staging.make_plan("leaf-pair", [a, b], checks, images)
        self.assertEqual(plan.serials, ["S1", "S2"])
        self.assertEqual(plan.image_name, "nxos64-cs.10.6.4.M.bin")
        standalone = staging.Switch("S3", "leaf3", "192.0.2.3", "N9K-C93180YC-FX", "10.3(8)", "n9k", "", "", "F1")
        with self.assertRaisesRegex(ValueError, "different checks"):
            staging.make_plan("mixed", [a, standalone], checks, images)
        other_fabric = staging.Switch("S4", "leaf4", "192.0.2.4", "N9K-C93180YC-FX", "10.3(8)", "n9k", "x", "primary", "F2")
        with self.assertRaisesRegex(ValueError, "spans fabrics"):
            staging.make_plan("split", [a, other_fabric], checks, images)

    def test_default_upgrade_rules_preserve_targets(self):
        cases = [
            ("N9K-C93240YC-FX2", "9.3(8)", "9.3.16"),
            ("N9K-C93180YC-EX", "10.3(8)", "10.3.10"),
            ("N9K-C93108TC-EX", "10.3.8", "10.3.10"),
            ("N9K-C93240YC-FX2", "10.3(8)", "10.6.4"),
            ("N9K-C93240YC-FX2", "10.6(3)", None),
            ("N9K-C93240YC-FX2", "10.30(3)", None),
        ]
        for model, version, expected in cases:
            with self.subTest(model=model, version=version):
                switch = staging.Switch("S1", "leaf", "", model, version, "n9k", "", "", "F1")
                self.assertEqual(staging.target_for(switch), expected)
        self.assertEqual(staging.parse_args([]).upgrade_rules, staging.DEFAULT_UPGRADE_RULES)

    def test_yaml_upgrade_rules_replace_defaults_and_first_match_wins(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "rules.yaml"
            config.write_text(yaml.safe_dump({"upgrade_rules": [
                {"models": ["n9k-c93240yc-fx2"], "source_version": "10.6", "target_version": "10.6.4"},
                {"models": ["N9K*"], "source_version": "10.6", "target_version": "10.6.5"},
            ]}))
            rules = staging.parse_args(["--config", str(config)]).upgrade_rules
        switch = staging.Switch("S1", "r143b-sw1", "192.0.2.1", "N9K-C93240YC-FX2",
                                "10.6(3)", "n9k", "", "", "F1")
        self.assertIsNone(staging.make_plan("test", [switch], [], []))
        images = [{"imageName": "nxos64-cs.10.6.4.M.bin", "releaseVersion": "10.6.4", "platform": "N9K"}]
        plan = staging.make_plan("test", [switch], [], images, rules)
        self.assertEqual(plan.target_version, "10.6.4")
        self.assertEqual(plan.image_name, "nxos64-cs.10.6.4.M.bin")
        for version, expected in (("10.6.3", "10.6.4"), ("10.60(3)", None), ("10.3(8)", None)):
            other = staging.Switch("S2", "other", "", switch.model, version, "n9k", "", "", "F1")
            self.assertEqual(staging.target_for(other, rules), expected)
        other_model = staging.Switch("S2", "other", "", "N9K-C9508", "10.6(3)", "n9k", "", "", "F1")
        self.assertEqual(staging.target_for(other_model, rules), "10.6.5")
        non_n9k = staging.Switch("S3", "other", "", "N7K-C7009", "10.6(3)", "n7k", "", "", "F1")
        wildcard = [staging.UpgradeRule(("*",), "10.6", "10.6.4")]
        self.assertIsNone(staging.target_for(non_n9k, wildcard))
        with self.assertRaisesRegex(ValueError, "Expected one uploaded"):
            staging.make_plan("test", [switch], [], [], rules)

    def test_invalid_yaml_upgrade_rules(self):
        valid = {"models": ["N9K*"], "source_version": "10.6", "target_version": "10.6.4"}
        invalid = [
            None, [], {}, "10.6", [None], [{}],
            [dict(valid, unexpected=True)], [dict(valid, models=[])],
            [dict(valid, models="N9K*")], [dict(valid, models=[" "])],
            [dict(valid, models=[1])], [dict(valid, source_version=10.6)],
            [dict(valid, source_version="10.*")], [dict(valid, source_version="")],
            [dict(valid, target_version=None)], [dict(valid, target_version="bad")],
        ]
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "rules.yaml"
            for rules in invalid:
                with self.subTest(rules=rules):
                    config.write_text(yaml.safe_dump({"upgrade_rules": rules}))
                    with patch("sys.stderr"), self.assertRaises(SystemExit):
                        staging.parse_args(["--config", str(config)])

    def test_example_upgrade_rules_match_defaults(self):
        args = staging.parse_args([
            "--config", str(ROOT / "examples/nexus_dashboard/nxos_update_groups.example.yaml"),
        ])
        self.assertEqual(args.upgrade_rules, staging.DEFAULT_UPGRADE_RULES)

    def test_main_uses_custom_upgrade_rules_for_planning_and_apply(self):
        client = CatalogClient()
        original_request = client.request

        def request(method, path, payload=None):
            if path == staging.SWITCHES:
                return {"switches": [{"switchId": "S1", "switchName": "r143b-sw1", "fabricName": "F1",
                                      "switchModel": "N9K-C93240YC-FX2", "switchVersion": "10.6(3)",
                                      "switchPlatform": "n9k"}]}
            if path == staging.IMAGES:
                return [{"imageName": "nxos64-cs.10.6.4.M.bin", "releaseVersion": "10.6.4"}]
            if path == staging.fabric_path("F1", "updateGroups"):
                return []
            return original_request(method, path, payload)

        client.request = request
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "rules.yaml"
            config.write_text(yaml.safe_dump({
                "switches": {"hosts": ["r143b-sw1"]},
                "upgrade_rules": [{"models": ["N9K-C93240YC-FX2"],
                                   "source_version": "10.6", "target_version": "10.6.4"}],
            }))
            with patch.object(sys, "argv", ["nd_stage_nexus_updates.py", "--config", str(config), "--apply"]), \
                    patch.object(staging, "NexusDashboard", return_value=client), \
                    patch.dict(staging.os.environ, {"NEXUS_PASSWORD": "test-only"}):
                self.assertEqual(staging.main(), 0)
        self.assertEqual(client.group["installImageData"]["nosImageName"], "nxos64-cs.10.6.4.M.bin")
        self.assertTrue(any(method == "POST" and path.endswith("/actions/stage")
                            for method, path, _ in client.calls))

    def test_yaml_update_groups(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "groups.yaml"
            config.write_text(yaml.safe_dump({"update_groups": {"leaf-pair": {"hosts": ["leaf1", "leaf2"]}}}))
            args = staging.parse_args(["--config", str(config)])
            self.assertEqual(args.update_groups, [("leaf-pair", ["leaf1", "leaf2"])])
            for document in (
                {"update_groups": {"bad name": {"hosts": ["leaf1"]}}},
                {"update_groups": {"empty": {"hosts": []}}},
                {"update_groups": {"g": {"hosts": ["a"]}}, "switches": {"hosts": ["b"]}},
            ):
                config.write_text(yaml.safe_dump(document))
                with patch("sys.stderr"), self.assertRaises(SystemExit):
                    staging.parse_args(["--config", str(config)])

    def test_vault_decryption_and_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            vault = Path(folder) / "vault"
            password_file = Path(folder) / "password"
            vault.write_text("$ANSIBLE_VAULT;1.1;AES256\nfixture\n")
            password_file.write_text("test-only\n")
            password_file.chmod(0o600)
            result = subprocess.CompletedProcess([], 0, "nexus_dashboard:\n  nexus_dashboard_password: test-only\n", "")
            with patch.object(staging.shutil, "which", return_value="ansible-vault"), \
                    patch.object(staging.subprocess, "run", return_value=result) as decrypt:
                self.assertEqual(staging.load_vault_password(vault, password_file), "test-only")
                self.assertTrue(decrypt.call_args.kwargs["capture_output"])
                password_file.chmod(0o644)
                with self.assertRaisesRegex(ValueError, "0600"):
                    staging.load_vault_password(vault, password_file)
                self.assertEqual(decrypt.call_count, 1)

    def test_yaml_settings_and_cli_overrides(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "environment.yaml"
            config.write_text(yaml.safe_dump({
                "nexus_dashboard": {
                    "host": "nd.other.example", "username": "operator", "domain": "ldap",
                    "verify_ssl": False, "timeout": 900, "password_env": "OTHER_ND_PASSWORD",
                    "vault_file": "secrets/vault.yaml", "vault_password_file": "secrets/password",
                },
                "switches": {"hosts": ["switch01", "192.0.2.2"]},
            }))
            args = staging.parse_args(["--config", str(config)])
            self.assertEqual(args.nd_url, "https://nd.other.example")
            self.assertEqual((args.username, args.domain), ("operator", "ldap"))
            self.assertEqual(args.request_timeout, 900)
            self.assertEqual(args.password_env, "OTHER_ND_PASSWORD")
            self.assertTrue(args.insecure)
            self.assertFalse(args.apply)
            self.assertEqual(args.device, ["switch01", "192.0.2.2"])
            self.assertEqual(args.vault_file, Path(folder) / "secrets/vault.yaml")
            self.assertEqual(args.vault_password_file, Path(folder) / "secrets/password")
            overridden = staging.parse_args([
                "--config", str(config), "--nd-url", "https://override.example",
                "--username", "admin", "--domain", "local", "--verify-tls",
                "--request-timeout", "700", "--device", "SERIAL",
                "--vault-file", "cli-vault.yaml",
            ])
            self.assertEqual(overridden.nd_url, "https://override.example")
            self.assertEqual((overridden.username, overridden.domain), ("admin", "local"))
            self.assertFalse(overridden.insecure)
            self.assertEqual(overridden.request_timeout, 700)
            self.assertEqual(overridden.device, ["SERIAL"])
            self.assertEqual(overridden.vault_file, Path("cli-vault.yaml"))

    def test_yaml_validation_and_legacy_defaults(self):
        defaults = staging.parse_args([])
        self.assertEqual(defaults.username, "admin")
        self.assertEqual(defaults.domain, "local")
        self.assertEqual(defaults.password_env, "NEXUS_PASSWORD")
        self.assertFalse(defaults.insecure)
        invalid_settings = [
            {"password": "do-not-use"}, {"verify_ssl": "false"}, {"timeout": -1},
            {"host": "http://nd.example"}, {"domain": []},
        ]
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "invalid.yaml"
            for settings in invalid_settings:
                config.write_text(yaml.safe_dump({"nexus_dashboard": settings}))
                with patch("sys.stderr"), self.assertRaises(SystemExit):
                    staging.parse_args(["--config", str(config)])


if __name__ == "__main__":
    unittest.main()