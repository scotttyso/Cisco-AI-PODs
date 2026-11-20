import os
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import deploy_ai_pod as deploy  # noqa: E402
from aipod_webui import ocp_access  # noqa: E402

PASSWORD = "Fake-Pass-1234"
KUBECONFIG = """apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: Q0FEQVRB
    server: https://api.aid.aipod.local:6443
  name: aid
contexts:
- context:
    cluster: aid
    user: admin
  name: admin
current-context: admin
kind: Config
users:
- name: admin
  user:
    client-certificate-data: Q0VSVA==
    client-key-data: S0VZREFUQQ=="""
OUTPUT = f"""Installation finished...
Collecting cluster information...
Cluster console access
----------------------
URL      : https://console-openshift-console.apps.aid.aipod.local
Username : kubeadmin
Password : {PASSWORD}
Kubeconfig
----------
{KUBECONFIG}
Create ocp connector: aid [kubeconfig:/tmp/x.kubeconfig] [domain:None]
Ocp connector created
[ERROR] SSH connection failed: core@10.124.1.61
"""


class FakeVault:
    def __init__(self):
        self.changes = {}

    def update(self, changes):
        self.changes.update(changes)

    def load(self):
        return {"openshift": {ocp_access.VAULT_KUBECONFIG_KEY: self.changes.get(("openshift", ocp_access.VAULT_KUBECONFIG_KEY), "")}}


def feed_all(text):
    capture, shown = ocp_access.AccessCapture(), []
    for line in text.splitlines(keepends=True):
        shown += capture.feed(line)
    return capture, "\n".join(shown)


class CaptureTests(unittest.TestCase):
    def test_access_details_are_captured_and_hidden_but_the_rest_of_the_output_is_kept(self):
        capture, shown = feed_all(OUTPUT)
        self.assertEqual(capture.password, PASSWORD)
        self.assertEqual(capture.username, "kubeadmin")
        self.assertEqual(capture.console_url, "https://console-openshift-console.apps.aid.aipod.local")
        self.assertEqual(capture.kubeconfig.strip(), KUBECONFIG)
        for secret in (PASSWORD, "S0VZREFUQQ==", "Q0VSVA==", "apiVersion"):
            self.assertNotIn(secret, shown)
        for kept in ("Installation finished", "URL      : https://console-openshift-console", "Username : kubeadmin",
                     "Create ocp connector", "SSH connection failed", ocp_access.HIDDEN_NOTE):
            self.assertIn(kept, shown)

    def test_stray_key_material_outside_the_block_is_masked(self):
        shown = feed_all("debug client-key-data: AAAABBBB\nplain line\n")[1]
        self.assertIn("client-key-data: ********", shown)
        self.assertNotIn("AAAABBBB", shown)

    def test_output_without_access_details_is_unchanged(self):
        capture, shown = feed_all("hello\nKubeconfig file failed\n")
        self.assertFalse(capture.captured)
        self.assertEqual(shown, "hello\nKubeconfig file failed")


class SaveTests(unittest.TestCase):
    def test_files_are_private_and_the_vault_gets_the_secrets(self):
        capture = feed_all(OUTPUT)[0]
        with tempfile.TemporaryDirectory() as folder:
            host_vars = Path(folder) / "environments/default/host_vars"
            host_vars.mkdir(parents=True)
            vault = FakeVault()
            notes = ocp_access.save_access(capture, host_vars, vault)
            path = ocp_access.kubeconfig_path(host_vars)
            self.assertEqual(path.read_text().strip(), KUBECONFIG)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            self.assertEqual(ocp_access.load_info(host_vars)["cluster"], "aid")
            self.assertNotIn(PASSWORD, (path.parent / ocp_access.INFO_FILE).read_text())
            self.assertEqual(vault.changes[("openshift", "kubeadmin_password")], PASSWORD)
            self.assertEqual(vault.changes[("openshift", "ocp_kubeconfig")].strip(), KUBECONFIG)
            self.assertTrue(any("vault" in note for note in notes))
            path.unlink()
            self.assertEqual(ocp_access.ensure_kubeconfig_file(host_vars, vault), path)
            self.assertEqual(path.read_text().strip(), KUBECONFIG)

    def test_a_vault_failure_keeps_the_file_and_reports_it(self):
        capture = feed_all(OUTPUT)[0]

        class Broken:
            def update(self, changes):
                raise RuntimeError("vault locked")

        with tempfile.TemporaryDirectory() as folder:
            host_vars = Path(folder) / "host_vars"
            host_vars.mkdir()
            notes = ocp_access.save_access(capture, host_vars, Broken())
            self.assertTrue(ocp_access.kubeconfig_path(host_vars).is_file())
            self.assertTrue(any("could not store" in note for note in notes))


class RunCommandTests(unittest.TestCase):
    def test_install_output_is_masked_and_saved_even_when_the_command_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = Path(folder) / "iserver"
            fake.write_text("#!/usr/bin/env python3\nimport sys\nsys.stdout.write(" + repr(OUTPUT) + ")\nsys.exit(1)\n")
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            host_vars = Path(folder) / "env/host_vars"
            host_vars.mkdir(parents=True)
            vault = FakeVault()
            output = StringIO()
            with redirect_stdout(output), self.assertRaises(deploy.DeploymentError):
                deploy.run_command([str(fake)], dict(os.environ),
                                   access_sink=lambda capture: ocp_access.save_access(capture, host_vars, vault))
            text = output.getvalue()
            self.assertNotIn(PASSWORD, text)
            self.assertNotIn("S0VZREFUQQ==", text)
            self.assertIn("SSH connection failed", text)
            self.assertEqual(vault.changes[("openshift", "kubeadmin_password")], PASSWORD)
            self.assertTrue(ocp_access.kubeconfig_path(host_vars).is_file())


if __name__ == "__main__":
    unittest.main()
