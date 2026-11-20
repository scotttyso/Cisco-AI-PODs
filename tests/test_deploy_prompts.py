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

FAKE = '''#!/usr/bin/env python3
import sys
print("[ERROR] Redfish vmedia mapping failed")
answer = input("Continue [Y/N]? ")
print("answered", answer)
sys.exit(1 if answer == "N" else 0)
'''


class PromptAnswerTests(unittest.TestCase):
    def run_fake(self, name):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / name
            path.write_text(FAKE)
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
            output = StringIO()
            with redirect_stdout(output), self.assertRaises(deploy.DeploymentError):
                deploy.run_command([str(path)], dict(os.environ))
            return output.getvalue()

    def test_iserver_prompts_are_answered_n_and_the_vmedia_hint_is_shown(self):
        output = self.run_fake("iserver")
        self.assertIn("answered N", output)
        self.assertNotIn("EOFError", output)
        self.assertIn("vmedia_diagnose.py", output)

    def test_other_commands_get_no_input(self):
        self.assertNotIn("answered N", self.run_fake("other-tool"))


if __name__ == "__main__":
    unittest.main()
