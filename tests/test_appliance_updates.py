import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import release_updates  # noqa: E402

UPDATER_PATH = ROOT / "automation-appliance" / "files" / "aipod-update"
loader = SourceFileLoader("aipod_update", str(UPDATER_PATH))
spec = importlib.util.spec_from_loader("aipod_update", loader)
updater = importlib.util.module_from_spec(spec)
loader.exec_module(updater)

COMMIT = "a" * 40
SERVICE_SHOW = {
    "User": updater.APP_USER,
    "WorkingDirectory": str(updater.REPO),
    "ExecStart": (f"{{ path={updater.REPO}/.venv/bin/python3 ; argv[]={updater.REPO}/.venv/bin/python3 "
                  f"{updater.REPO}/scripts/automation_ui.py --host 127.0.0.1 --port 8080 ; }}"),
}


class FakeSystem:
    """Records commands and answers the queries the updater makes."""

    def __init__(self, origin=updater.REPOSITORY + ".git", status="", local_tag=COMMIT,
                 ancestor=True, fail=None, service=None):
        self.calls = []
        self.origin, self.status, self.local_tag = origin, status, local_tag
        self.ancestor, self.fail = ancestor, fail
        self.service = dict(SERVICE_SHOW, **(service or {}))

    def __call__(self, *command, capture=False, cwd=None):
        self.calls.append(command)
        if self.fail and self.fail in command:
            raise subprocess.CalledProcessError(1, command)
        if command[:2] == ("systemctl", "show"):
            return self.service[command[3].split("=", 1)[1]]
        if command[:2] == ("git", "ls-remote"):
            return f"{'b' * 40}\trefs/tags/v1.2.3\n{COMMIT}\trefs/tags/v1.2.3^{{}}"
        if "config" in command and "remote.origin.url" in command:
            return self.origin
        if "status" in command:
            return self.status
        if "rev-parse" in command:
            return self.local_tag
        if "merge-base" in command and not self.ancestor:
            raise subprocess.CalledProcessError(1, command)
        return ""

    def commands(self, word):
        return [command for command in self.calls if word in command]


def fake_download(commit, path, limit=1024 * 1024):
    return b"v1.2.3\n" if path == "VERSION" else f"{commit}:{path}".encode()


class ReleaseUpdatesTests(unittest.TestCase):
    def test_release_details_and_instructions(self):
        details = release_updates.release_details({"tag_name": "v1.2.3", "body": "Notes"})
        self.assertEqual(details["url"], "https://github.com/scotttyso/Cisco-AI-PODs/releases/tag/v1.2.3")
        self.assertIn("sudo /usr/local/sbin/aipod-update --version v1.2.3", release_updates.install_instructions("v1.2.3"))
        for tag in ("1.2.3", "v1.2", "v1.2.3; rm -rf /", "0.0002"):
            with self.assertRaises(ValueError):
                release_updates.release_details({"tag_name": tag})
            with self.assertRaises(ValueError):
                release_updates.install_instructions(tag)

    def test_installed_version_reads_repository_file(self):
        self.assertEqual(release_updates.VERSION_FILE, ROOT / "VERSION")
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(release_updates, "VERSION_FILE", Path(folder) / "VERSION"):
                self.assertEqual(release_updates.installed_version(), "development")
                release_updates.VERSION_FILE.write_text("v9.9.9\n")
                self.assertEqual(release_updates.installed_version(), "v9.9.9")


class UiUpdateLaunchTests(unittest.TestCase):
    def test_update_runs_in_its_own_systemd_unit(self):
        unit = release_updates.update_unit("v0.2.0", now=0)
        self.assertRegex(unit, r"^aipod-update-v0_2_0-\d{14}$")
        command = release_updates.update_command("v0.2.0", unit)
        self.assertEqual(command[:4], ["sudo", "-A", "-p", ""])
        self.assertIn("systemd-run", command)
        self.assertIn(f"--unit={unit}", command)
        self.assertIn(f"--property=StandardOutput=append:/var/log/aipod-update/{unit}.log", command)
        self.assertEqual(command[-4:], [str(release_updates.UPDATER), "--version", "v0.2.0", "--yes"])
        for bad_tag, bad_unit in (("v1.0; rm -rf /", unit), ("v0.2.0", "x; reboot")):
            with self.assertRaises(ValueError):
                release_updates.update_command(bad_tag, bad_unit)
        with self.assertRaises(ValueError):
            release_updates.update_unit("latest")

    def test_latest_update_log(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(release_updates, "UPDATE_LOG_DIR", Path(folder)):
            self.assertEqual(release_updates.latest_update_log(), ("", ""))
            old, new = Path(folder, "aipod-update-v0_1_0-1.log"), Path(folder, "aipod-update-v0_2_0-2.log")
            old.write_text("old")
            new.write_text("Update complete")
            import os
            os.utime(old, (1, 1))
            self.assertEqual(release_updates.latest_update_log(), (new.name, "Update complete"))


class UpdaterTests(unittest.TestCase):
    def test_arguments_require_release_tag(self):
        self.assertEqual(updater.parse_args(["--version", "v1.2.3-rc.1", "--yes"]).version, "v1.2.3-rc.1")
        for value in ("main", "1.2.3", "v1.2.3;id", "../v1.2.3"):
            with self.assertRaises(SystemExit), patch("sys.stderr", io.StringIO()):
                updater.parse_args(["--version", value])

    def test_remote_tag_prefers_peeled_commit(self):
        system = FakeSystem()
        with patch.object(updater, "run", system):
            self.assertEqual(updater.remote_tag_commit("v1.2.3"), COMMIT)
        with patch.object(updater, "run", return_value=""):
            with self.assertRaisesRegex(ValueError, "not found"):
                updater.remote_tag_commit("v1.2.3")

    def preflight(self, system):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            repo, state = home / "Cisco-AI-PODs", home / ".automation-ui"
            (repo / ".git").mkdir(parents=True)
            state.mkdir()
            system.service.update(WorkingDirectory=str(repo), ExecStart=system.service["ExecStart"].replace(
                str(updater.REPO), str(repo)))
            with patch.multiple(updater, APP_HOME=home, REPO=repo, STATE=state, run=system), \
                    patch.object(updater.pwd, "getpwnam") as user:
                user.return_value.pw_uid = repo.stat().st_uid
                updater.preflight()

    def test_preflight_accepts_standard_installation(self):
        self.preflight(FakeSystem())
        self.preflight(FakeSystem(origin=updater.REPOSITORY + "/"))

    def test_preflight_rejects_nonstandard_installations(self):
        cases = (
            (FakeSystem(origin="https://github.com/someone/Cisco-AI-PODs.git"), "forks"),
            (FakeSystem(status=" M scripts/automation_ui.py"), "local changes"),
            (FakeSystem(service={"User": "root"}), "Custom service"),
        )
        for system, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                self.preflight(system)
        system = FakeSystem()
        system.service["ExecStart"] = SERVICE_SHOW["ExecStart"].replace("8080", "9090")
        with self.assertRaisesRegex(ValueError, "127.0.0.1:8080"):
            self.preflight(system)

    def test_resolve_release_verifies_tag_and_downloads_root_files(self):
        system = FakeSystem()
        with patch.object(updater, "run", system), patch.object(updater, "download", fake_download), \
                patch.object(updater.Path, "exists", return_value=False):
            commit, files = updater.resolve_release("v1.2.3")
        self.assertEqual(commit, COMMIT)
        self.assertEqual(set(files), {Path("/usr/local/sbin/aipod-update"),
                                      Path("/etc/systemd/system/automation-ui.service")})
        self.assertEqual(files[Path("/usr/local/sbin/aipod-update")][1], 0o755)
        fetch = system.commands("fetch")[0]
        self.assertIn("refs/tags/v1.2.3:refs/tags/v1.2.3", fetch)
        self.assertNotIn("+refs/tags/v1.2.3:refs/tags/v1.2.3", fetch)
        self.assertTrue(all(command[:5] == ("runuser", "-u", updater.APP_USER, "--", "env")
                            for command in system.calls if "git" in command and "-C" in command))

    def test_resolve_release_rejects_mismatches(self):
        cases = (
            (FakeSystem(local_tag="c" * 40), fake_download, "differs from GitHub"),
            (FakeSystem(ancestor=False), fake_download, "main branch"),
            (FakeSystem(), lambda commit, path, limit=0: b"v9.9.9", "does not match"),
        )
        for system, downloader, message in cases:
            with self.subTest(message=message), patch.object(updater, "run", system), \
                    patch.object(updater, "download", downloader), \
                    self.assertRaisesRegex(ValueError, message):
                updater.resolve_release("v1.2.3")

    def test_install_system_files_is_atomic_with_modes(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "sbin" / "aipod-update"
            updater.install_system_files({target: (b"new", 0o755)})
            self.assertEqual(target.read_bytes(), b"new")
            self.assertEqual(target.stat().st_mode & 0o777, 0o755)
            self.assertEqual([path.name for path in target.parent.iterdir()], ["aipod-update"])

    def test_install_update_order(self):
        system = FakeSystem()
        files = {Path("/usr/local/sbin/aipod-update"): (b"x", 0o755)}
        with tempfile.TemporaryDirectory() as folder, patch.object(updater, "run", system), \
                patch.object(updater, "make_backups") as backups, \
                patch.object(updater, "install_system_files") as install, \
                patch.object(updater, "relabel"), patch.object(updater, "wait_ready") as ready:
            updater.install_update(COMMIT, files, "f" * 40, Path(folder))
        flat = [" ".join(command) for command in system.calls]
        order = [next(index for index, line in enumerate(flat) if marker in line) for marker in (
            "systemctl stop", f"checkout --detach {COMMIT}", "setup.sh --skip-apt --skip-iserver",
            "requirements-webui.txt", "import automation_ui", "daemon-reload", "systemctl start")]
        self.assertEqual(order, sorted(order))
        backups.assert_called_once()
        install.assert_called_once_with(files)
        ready.assert_called_once()

    def test_install_failure_stops_service_and_prints_recovery(self):
        system = FakeSystem(fail="./scripts/setup.sh")
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as folder, patch.object(updater, "run", system), \
                patch.object(updater, "make_backups"), patch.object(updater, "install_system_files") as install, \
                patch("sys.stderr", stderr):
            with self.assertRaises(subprocess.CalledProcessError):
                updater.install_update(COMMIT, {}, "f" * 40, Path(folder))
        install.assert_not_called()
        self.assertEqual(system.calls[-1], ("systemctl", "stop", updater.SERVICE))
        self.assertIn("checkout --detach " + "f" * 40, stderr.getvalue())
        self.assertIn("No automatic rollback", stderr.getvalue())

    def test_main_requires_root(self):
        with patch.object(updater.os, "geteuid", return_value=1000), patch("sys.stderr", io.StringIO()):
            self.assertEqual(updater.main(["--version", "v1.2.3"]), 1)


if __name__ == "__main__":
    unittest.main()
