import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GENERATOR = REPO / "roles/openshift_install/library/generate_server_and_nmstate_templates.py"
EXAMPLE = REPO / "examples/openshift/install.ezai.yaml"


class GeneratorTests(unittest.TestCase):
    def test_generates_the_install_files_from_the_example_into_the_output_dir(self):
        env = dict(os.environ, ssh_public_key_1="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l8GJDp t@x")
        for index in range(1, 65):
            env.setdefault(f"fabric_interconnect_password_{index}", "Passw0rd!Test")
            env.setdefault(f"redfish_password_{index}", "Passw0rd!Test")
        with tempfile.TemporaryDirectory() as output:
            result = subprocess.run(
                [sys.executable, str(GENERATOR), "--vars-file", str(EXAMPLE), "--output-dir", output],
                capture_output=True, text=True, env=env, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            files = {path.name for path in Path(output).iterdir()}
            self.assertIn("server.json", files)
            self.assertIn("ssh.pub", files)
            self.assertTrue(any(name.startswith("nmstate_") for name in files))
            self.assertTrue(json.loads((Path(output) / "server.json").read_text()))


class IserverTemplateTests(unittest.TestCase):
    """The iserver payload templates must render strictly valid JSON (newer Ansible parses them with from_json)."""

    def render(self, name, **web):
        import jinja2

        template = jinja2.Environment(trim_blocks=True, lstrip_blocks=True).from_string(
            (REPO / "roles/openshift_install/templates" / name).read_text())
        networking = {"api": {"v4": "10.0.0.1"}, "ingress": {"v4": "10.0.0.2"}, "dns_servers": ["10.0.0.3"],
                      "machine_network_gateway": {"v4": "10.0.0.254"}, "container_network_interface": "Cilium",
                      "container_network_version": "1.19.7"}
        install = {"servers": [1, 2, 3], "base_dns_domain": "example.com", "cluster_name": "c1",
                   "cluster_networking": networking, "ntp_servers": ["10.0.0.4"],
                   "iso_web_server": {"server_address": "10.0.0.5", "image_upload_directory": "/var/image", **web}}
        return json.loads(template.render(openshift_install=install, iso_web_server_password="pw",
                                          iso_web_server_ssh_public_key="ssh-ed25519 AAAA"))

    def test_cluster_json_carries_the_cilium_version_and_the_floating_default(self):
        payload = self.render("iserver-cluster.json.j2", image_base_url="http://h/x")
        self.assertEqual(payload["cilium"], {"version": "1.19.7"})
        self.assertEqual(payload["openshift_version"], "the-latest-production-version")

    def test_web_json_is_valid_for_http_https_and_remote_servers(self):
        self.assertNotIn("verify", self.render("iserver-web.json.j2", image_base_url="http://h/x"))
        self.assertFalse(self.render("iserver-web.json.j2", image_base_url="https://h/x")["verify"])
        remote = self.render("iserver-web.json.j2", image_base_url="https://h/x", username="u", ssh_public_key_file="k")
        self.assertEqual(remote["ssh_public_key"], "ssh-ed25519 AAAA")
        self.assertEqual(self.render("iserver-web.json.j2", image_base_url="http://h/x", username="u")["password"], "pw")


if __name__ == "__main__":
    unittest.main()
