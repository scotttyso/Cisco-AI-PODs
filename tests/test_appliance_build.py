import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "automation-appliance" / "scripts"))
import build_appliance  # noqa: E402


class ApplianceBuildTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.vault_file = Path(self.directory.name) / "appliance-build.yml"
        self.password_file = Path(self.directory.name) / "vault-password"
        self.vault_file.write_text("encrypted vault")
        self.password_file.write_text("vault password")
        self.password_file.chmod(0o600)

    def tearDown(self):
        self.directory.cleanup()

    def test_load_build_environment_decrypts_and_hashes_password(self):
        with patch.object(build_appliance.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"), \
                patch.object(
                    build_appliance.subprocess,
                    "run",
                    side_effect=[
                        subprocess.CompletedProcess(
                            ["ansible-vault"], 0,
                            "vsphere_password: vcenter-secret\nbuild_password: temporary-secret\n", "",
                        ),
                        subprocess.CompletedProcess(["openssl"], 0, "$6$hash\n", ""),
                    ],
        ) as run:
            environment = build_appliance.load_build_environment(self.vault_file, self.password_file)

        self.assertEqual(environment, {
            "PKR_VAR_vsphere_password": "vcenter-secret",
            "PKR_VAR_build_password": "temporary-secret",
            "PKR_VAR_build_password_hash": "$6$hash",
        })
        self.assertEqual(run.call_args_list[1], call(
            ["/usr/bin/openssl", "passwd", "-6", "-stdin"],
            input="temporary-secret\n",
            check=True,
            capture_output=True,
            text=True,
        ))

    def test_load_build_environment_accepts_packer_variable_names(self):
        with patch.object(build_appliance.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"), \
                patch.object(
                    build_appliance.subprocess,
                    "run",
                    side_effect=[
                        subprocess.CompletedProcess(
                            ["ansible-vault"], 0,
                            "PKR_VAR_vsphere_password: vcenter-secret\n"
                            "PKR_VAR_build_password: temporary-secret\n", "",
                        ),
                        subprocess.CompletedProcess(["openssl"], 0, "$6$hash\n", ""),
                    ],
        ):
            environment = build_appliance.load_build_environment(self.vault_file, self.password_file)

        self.assertEqual(environment["PKR_VAR_vsphere_password"], "vcenter-secret")
        self.assertEqual(environment["PKR_VAR_build_password"], "temporary-secret")
        self.assertEqual(environment["PKR_VAR_build_password_hash"], "$6$hash")

    def test_rejects_vault_password_file_with_permissive_mode(self):
        self.password_file.chmod(0o644)
        with self.assertRaisesRegex(build_appliance.BuildError, "must have 0600 permissions"):
            build_appliance.load_build_environment(self.vault_file, self.password_file)


if __name__ == "__main__":
    unittest.main()
