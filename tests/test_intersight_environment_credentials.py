import os
import site
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "roles/intersight_ucs_provision/library/deploy_intersight_ucs.py"
pytest.importorskip("dotmap")


class LegacyVaultTests(unittest.TestCase):
    def run_cli(self, **credentials):
        with tempfile.TemporaryDirectory() as home:
            env = {key: value for key, value in os.environ.items()
                   if key not in ("intersight_api_key_id", "intersight_secret_key", "INTERSIGHT_ENVIRONMENT")}
            env.update(HOME=home, PYTHONUSERBASE=site.getuserbase(), **credentials)
            return subprocess.run([sys.executable, str(SCRIPT), "--dir", home, "--non-interactive", "--check"],
                                  capture_output=True, text=True, env=env, check=False)

    def test_environment_credentials_do_not_need_the_per_user_vault_file(self):
        result = self.run_cli(intersight_api_key_id="key", intersight_secret_key="secret")
        self.assertNotIn("Vault file not found", result.stdout + result.stderr)
        self.assertIn("Using SAAS environment", result.stdout)

    def test_missing_credentials_are_reported_without_a_traceback(self):
        result = self.run_cli()
        self.assertIn("No Intersight credentials", result.stdout)
        self.assertEqual(result.returncode, 1)
