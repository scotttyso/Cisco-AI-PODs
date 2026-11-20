import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import cleanup_install_artifacts as cleanup  # noqa: E402

UUID = "96ed1e03-c3be-451b-be40-29d6aaec8c8c"
OTHER = "4e1684e1-40fb-48dc-bce0-55fe7394a7e9"


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.assisted, self.scratch, self.media, self.itool = (root / name for name in ("assisted", "tmp", "media", "itool"))
        for directory in (self.assisted / "manifests", self.scratch / "iserver/0fc66ba6be2c", self.media, self.itool / "openshift"):
            directory.mkdir(parents=True)
        (self.assisted / "server.json").write_text("passwords")
        (self.assisted / "manifests/a.yaml").write_text("x")
        (self.scratch / "iserver/0fc66ba6be2c/iserver.debug").write_text("pull secret")
        (self.scratch / "iserver/not-a-run").mkdir()
        (self.scratch / f"{UUID}.iso").write_text("iso")
        (self.scratch / f"{UUID}.kubeconfig").write_text("kc")
        (self.scratch / OTHER).write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n")
        (self.scratch / UUID).write_text("not a key, leave alone")
        (self.scratch / "unrelated.txt").write_text("keep")
        for name in (f"{UUID}.iso", f"image-{OTHER}.iso", OTHER, "ubuntu-26.04.iso", "dummy.iso"):
            (self.media / name).write_text("m")
        secret = self.itool / "openshift/pull_secret.txt"
        secret.write_text("secret")
        secret.chmod(0o644)

    def plan(self, keep_logs=False):
        return cleanup.build_plan(self.assisted, self.scratch, self.media, self.itool, keep_logs)

    def test_plan_selects_only_install_leftovers(self):
        names = {path.name for path in self.plan().remove}
        self.assertEqual(names, {"server.json", "manifests", "0fc66ba6be2c", f"{UUID}.iso", f"{UUID}.kubeconfig", OTHER,
                                 f"image-{OTHER}.iso"})
        self.assertNotIn("0fc66ba6be2c", {path.name for path in self.plan(keep_logs=True).remove})

    def test_dry_run_changes_nothing_and_apply_removes_and_tightens(self):
        lines = []
        self.assertEqual(cleanup.execute(self.plan(), False, lines.append), 0)
        self.assertTrue((self.assisted / "server.json").exists())
        self.assertTrue(any(line.startswith("would remove") for line in lines))
        self.assertEqual(cleanup.execute(self.plan(), True, lines.append), 0)
        self.assertTrue(self.assisted.is_dir())
        self.assertEqual(list(self.assisted.iterdir()), [])
        self.assertTrue((self.scratch / "unrelated.txt").exists())
        self.assertTrue((self.scratch / UUID).exists())
        self.assertEqual(sorted(path.name for path in self.media.iterdir()), ["dummy.iso", "ubuntu-26.04.iso"])
        self.assertEqual(stat.S_IMODE((self.itool / "openshift/pull_secret.txt").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((self.itool / "openshift").stat().st_mode) & 0o077, 0)

    def test_symlinks_are_not_followed(self):
        target = Path(self.tmp.name) / "precious.txt"
        target.write_text("keep")
        os.symlink(target, self.media / f"image-{UUID}.iso")
        cleanup.execute(self.plan(), True, lambda _line: None)
        self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()
