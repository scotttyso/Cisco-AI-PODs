"""Offline tests for the read-only C880 inventory planner."""

import importlib.util
from pathlib import Path
import os
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "plan_c880_deployment.py"
SPEC = importlib.util.spec_from_file_location("plan_c880_deployment", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PlanTests(unittest.TestCase):
    def test_plan_is_offline_and_never_exposes_inventory_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "host_vars").mkdir()
            (root / "group_vars").mkdir()
            (root / "group_vars" / "all.yml").write_text(
                "aipod:\n  dns_servers: [192.0.2.53]\n  ntp_servers: [192.0.2.123]\n",
                encoding="utf-8",
            )
            vault_path = root / "group_vars" / "vault.yml"
            vault_path.write_text("vault_private_secret_ref: synthetic-fixture-only\n", encoding="utf-8")
            os.chmod(vault_path, 0o600)
            (root / "host_vars" / "ucs-c880-1.yml").write_text(
                "ucs:\n  platform: C880A M8\n  cimc:\n    ip: 192.0.2.10\n    user: private-user\n    pass_ref: PRIVATE_SECRET_REF\n",
                encoding="utf-8",
            )
            plan = MODULE.build_plan(root)
            self.assertFalse(plan["live_execution_allowed"])
            self.assertTrue(all(plan["hosts"][0]["inventory_checks"].values()))
            rendered = str(plan)
            self.assertNotIn("private-user", rendered)
            self.assertNotIn("PRIVATE_SECRET_REF", rendered)
            self.assertNotIn("synthetic-fixture-only", rendered)
            self.assertNotIn("192.0.2.10", rendered)

    def test_invalid_address_blocks_inventory_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "host_vars").mkdir()
            (root / "group_vars").mkdir()
            (root / "group_vars" / "all.yml").write_text("aipod: {}\n", encoding="utf-8")
            (root / "host_vars" / "ucs-c880-1.yml").write_text(
                "ucs:\n  platform: C880A M8\n  cimc:\n    ip: invalid\n",
                encoding="utf-8",
            )
            plan = MODULE.build_plan(root)
            self.assertFalse(plan["hosts"][0]["inventory_checks"]["bmc_address_valid"])
            self.assertFalse(plan["hosts"][0]["inventory_checks"]["shared_dns_present"])
            self.assertFalse(plan["hosts"][0]["inventory_checks"]["credential_reference_resolves"])


if __name__ == "__main__":
    unittest.main()
