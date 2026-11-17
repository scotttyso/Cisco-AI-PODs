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


if __name__ == "__main__":
    unittest.main()
