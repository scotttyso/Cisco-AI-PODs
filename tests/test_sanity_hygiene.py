"""Cheap guards for the failures the nightly ansible-test sanity run reports.

The full run is `scripts/run_sanity.sh`; these checks catch the usual mistakes in seconds, before a tag."""
import subprocess
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
FRAGMENT_SECTIONS = {"release_summary", "major_changes", "minor_changes", "breaking_changes", "deprecated_features",
                     "removed_features", "security_fixes", "bugfixes", "known_issues", "trivial"}
# Privileged appliance helpers keep a fixed interpreter and are listed in tests/sanity/ignore-*.txt.
SHEBANG_ALLOWED = {"automation-appliance/files/aipod-config", "automation-appliance/files/aipod-update"}


def tracked(suffix: str) -> list[str]:
    output = subprocess.run(["git", "ls-files", f"*{suffix}"], cwd=REPO, capture_output=True, text=True, check=True)
    return [name for name in output.stdout.splitlines() if (REPO / name).is_file()]


class SanityHygieneTests(unittest.TestCase):
    def test_no_trailing_whitespace_in_python_files(self):
        offenders = []
        for name in tracked(".py"):
            for number, line in enumerate((REPO / name).read_text(encoding="utf-8").splitlines(), 1):
                if line != line.rstrip():
                    offenders.append(f"{name}:{number}")
                    break
        self.assertEqual(offenders, [], "trailing whitespace (pycodestyle W291/W293)")

    def test_executable_python_files_use_the_shebang_ansible_test_allows(self):
        output = subprocess.run(["git", "ls-files", "-s", "*.py"], cwd=REPO, capture_output=True, text=True, check=True)
        executable = [line.split("\t", 1)[1] for line in output.stdout.splitlines() if line.split()[0] == "100755"]
        offenders = [name for name in executable if name not in SHEBANG_ALLOWED
                     and (REPO / name).read_text(encoding="utf-8").split("\n", 1)[0].startswith("#!")
                     and (REPO / name).read_text(encoding="utf-8").split("\n", 1)[0] != "#!/usr/bin/env python"]
        self.assertEqual(offenders, [], "ansible-test 'shebang' allows only '#!/usr/bin/env python' on executable scripts")

    def test_changelog_config_and_fragments_follow_antsibull_rules(self):
        config = yaml.safe_load((REPO / "changelogs/config.yaml").read_text(encoding="utf-8"))
        self.assertEqual(config.get("changes_format"), "combined")
        for fragment in (REPO / "changelogs/fragments").glob("*.y*ml"):
            data = yaml.safe_load(fragment.read_text(encoding="utf-8")) or {}
            self.assertLessEqual(set(data), FRAGMENT_SECTIONS, f"{fragment.name}: invalid section")
            for section, value in data.items():
                if section != "release_summary":
                    self.assertIsInstance(value, list, f"{fragment.name}: {section} must be a list")

    def test_sanity_ignore_files_are_in_sync(self):
        self.assertEqual((REPO / "tests/sanity/ignore-2.16.txt").read_text(encoding="utf-8"),
                         (REPO / "tests/sanity/ignore-2.20.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
