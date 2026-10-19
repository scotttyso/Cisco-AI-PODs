import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))
from aipod_webui import custom_pages  # noqa: E402
from aipod_webui.environments import (  # noqa: E402
    REPO_VAULT_NAME, EnvironmentManager, EnvironmentProblem, GitSettings, check_name, describe, export_secrets,
    KEYS_VAULT_NAME, import_secrets, protect_private_keys, read_active, remove_exported, repository_visibility,
)
from aipod_webui.vault import TOP, VaultStore  # noqa: E402
from aipod_webui.panels import UiContext  # noqa: E402
import deploy_ai_pod  # noqa: E402


class EnvironmentManagerTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        base = UiContext(store=None, repository=REPOSITORY, output_dir=self.root, schema_path=self.root / "s.json",
                         schema_uri="/schema/s.json")
        self.manager = EnvironmentManager(self.root / "deployments", self.root / "app", self.root / "cfg" / "pw",
                                          lambda settings: [], base)

    def tearDown(self):
        self.directory.cleanup()

    def test_name_validation(self):
        for good in ("Production", "pre-production", "lab_2", "v1.0"):
            self.assertEqual(check_name(good), good)
        for bad in ("", "Pre Production", "../etc", "-x", ".hidden", "a/b", "x" * 64):
            with self.assertRaises(EnvironmentProblem):
                check_name(bad)

    def test_create_copy_and_contexts(self):
        self.manager.create("Production")
        production = self.manager.context("Production")
        production.store.save_inventory([{"hostname": "leaf-1", "ip": "198.18.0.1", "mac": "00:00:5e:00:53:01",
                                          "pid": "N9K", "serial_number": "X"}])
        production.vault.vault_file.write_text("$ANSIBLE_VAULT;1.1;AES256\n00\n")
        (production.host_vars_dir / "openshift").mkdir(parents=True)
        (production.host_vars_dir / "openshift/install.ezai.yaml").write_text("openshift: {}\n")

        self.manager.create("Pre-Production", copy_from="Production")
        copy = self.manager.context("Pre-Production")
        self.assertEqual(copy.store.inventory()[0]["hostname"], "leaf-1")
        self.assertTrue((copy.host_vars_dir / "openshift/install.ezai.yaml").is_file())
        self.assertFalse(copy.vault.vault_file.exists(), "secrets must not be copied")
        self.assertNotEqual(copy.jobs.root, production.jobs.root)
        self.assertEqual(copy.environment, "Pre-Production")
        self.assertIs(self.manager.context("Production"), production)
        self.assertEqual(self.manager.names(), ["Pre-Production", "Production"])
        self.assertEqual(describe(self.manager, "Production")["files"], ["host_vars/openshift/install.ezai.yaml"])
        with self.assertRaises(EnvironmentProblem):
            self.manager.create("production")
        self.assertIn("*.key", (self.root / "deployments/.gitignore").read_text())

    def test_migrate_legacy_copies_and_keeps_originals(self):
        workspace, output, vault = self.root / "ws", self.root / "out", self.root / "vault-ai-pod.yaml"
        (output / "host_vars/intersight").mkdir(parents=True)
        (output / "host_vars/intersight/system.ezai.yaml").write_text("intersight: {}\n")
        workspace.mkdir()
        (workspace / "site_settings.json").write_text("{}")
        vault.write_text("vault")
        self.assertEqual(self.manager.migrate_legacy(workspace, output, vault), "default")
        target = self.manager.path("default")
        self.assertTrue((target / "host_vars/intersight/system.ezai.yaml").is_file())
        self.assertTrue((target / "workspace/site_settings.json").is_file())
        self.assertEqual((target / "vault.yaml").read_text(), "vault")
        self.assertTrue(vault.exists() and (output / "host_vars").is_dir())
        self.assertIsNone(self.manager.migrate_legacy(workspace, output, vault))

    def test_read_active_falls_back(self):
        self.manager.create("Production")
        self.assertEqual(read_active({"environment": "missing"}, self.manager), "Production")
        self.assertEqual(read_active({"environment": "Production"}, self.manager), "Production")

    def test_git_settings_and_commit(self):
        with self.assertRaises(EnvironmentProblem):
            self.manager.save_git_settings(GitSettings(remote_url="file:///tmp/x"))
        with self.assertRaises(EnvironmentProblem):
            self.manager.git_commands("push")
        self.manager.save_git_settings(GitSettings("https://github.com/example/aipod-envs.git", "main", "octocat"))
        self.manager.create("Production")
        self.manager.path("Production").joinpath("tls.key").write_text("private")
        self.manager.path("Production").joinpath("vault.yaml").write_text("$ANSIBLE_VAULT;1.1;AES256\n00\n")
        commands = self.manager.git_commands("commit", "first commit", "admin", sys.executable)
        self.assertEqual(commands[0][2], "remove")
        for command in commands:
            subprocess.run(command, check=True, capture_output=True)
        tracked = subprocess.run(["git", "-C", str(self.manager.root), "ls-files"], capture_output=True, text=True,
                                 check=True).stdout.split()
        self.assertIn(".gitignore", tracked)
        self.assertNotIn("environments/Production/tls.key", tracked)
        self.assertNotIn("environments/Production/vault.yaml", tracked)
        output = subprocess.run(self.manager.git_commands("commit")[-1], capture_output=True, text=True).stdout
        self.assertIn("Nothing to commit", output)
        push = self.manager.git_commands("push")[0]
        self.assertEqual(push[-3:], ["--set-upstream", "origin", "HEAD:refs/heads/main"][-3:])
        env = self.manager.git_environment(REPOSITORY / "scripts/git_askpass.sh")
        self.assertEqual(env["AIPOD_GIT_USERNAME"], "octocat")
        askpass = subprocess.run([env["GIT_ASKPASS"], "Password for 'https://github.com':"], capture_output=True,
                                 text=True, env={"GIT_TOKEN": "tok-123"}).stdout.strip()
        self.assertEqual(askpass, "tok-123")
        self.assertEqual(len(self.manager.git_commands("pull")), 1)

    def test_settings_keep_store_secrets_and_untrack_old_vault(self):
        self.manager.save_git_settings(GitSettings("https://github.com/example/aipod-envs.git", store_secrets=True))
        self.assertIs(self.manager.git_settings().store_secrets, True)
        commands = self.manager.git_commands("commit", python=sys.executable)
        self.assertEqual(commands[0][2], "export")
        pull = self.manager.git_commands("pull", python=sys.executable)
        self.assertEqual(pull[-1][2], "import")
        # A repository that committed vault.yaml before it was ignored stops tracking it on the next commit.
        self.manager.create("Production")
        old = self.manager.path("Production") / "vault.yaml"
        old.write_text("$ANSIBLE_VAULT;1.1;AES256\n00\n")
        gitignore = self.manager.root / ".gitignore"
        gitignore.write_text("*.key\n")
        git = ["git", "-C", str(self.manager.root), "-c", "user.name=t", "-c", "user.email=t@x"]
        subprocess.run(git + ["add", "-f", "-A"], check=True, capture_output=True)
        subprocess.run(git + ["commit", "-qm", "old"], check=True, capture_output=True)
        self.manager.ensure_root()
        self.assertIn("vault.yaml", gitignore.read_text().splitlines())
        self.assertIn("*.key", gitignore.read_text().splitlines())
        subprocess.run(self.manager.git_commands("commit")[-1], check=True, capture_output=True)
        tracked = subprocess.run(git + ["ls-files"], capture_output=True, text=True, check=True).stdout.split()
        self.assertNotIn("environments/Production/vault.yaml", tracked)
        self.assertTrue(old.exists())

    def test_repository_visibility_parsing(self):
        self.assertEqual(repository_visibility("https://gitlab.example.com/a/b.git"), "unknown")
        self.assertEqual(repository_visibility(""), "unknown")


@unittest.skipUnless(shutil.which("ansible-vault"), "ansible-vault is not installed")
class RepositoryVaultTest(unittest.TestCase):
    def test_export_import_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            local_pw, other_pw = root / "local-pw", root / "other-pw"
            local_pw.write_text("local-password-123\n")
            other_pw.write_text("other-server-pass-456\n")
            local_pw.chmod(0o600)
            other_pw.chmod(0o600)
            production = root / "environments/Production"
            production.mkdir(parents=True)
            (root / "environments/Empty").mkdir()
            VaultStore(production / "vault.yaml", local_pw).update({
                ("intersight", "api_key_id"): "key-1", (TOP, "vault_extra"): "x"})
            with self.assertRaises(EnvironmentProblem):
                export_secrets(root, local_pw, "short")
            self.assertEqual(export_secrets(root, local_pw, "repo-password-789"), ["Production: 2 secrets"])
            shared = production / REPO_VAULT_NAME
            self.assertTrue(shared.read_text().startswith("$ANSIBLE_VAULT"))
            # A different server: its own vault password, one local-only secret, and a stale value to overwrite.
            (production / "vault.yaml").unlink()
            VaultStore(production / "vault.yaml", other_pw).update({
                ("intersight", "api_key_id"): "stale", ("splunk_observability", "token"): "local"})
            self.assertEqual(import_secrets(root, other_pw, "repo-password-789"), ["Production: 2 secrets"])
            data = VaultStore(production / "vault.yaml", other_pw).load()
            self.assertEqual(data["intersight"]["api_key_id"], "key-1")
            self.assertEqual(data["vault_extra"], "x")
            self.assertEqual(data["splunk_observability"]["token"], "local")
            env = dict(os.environ, GIT_REPO_PASSWORD="wrong-password-000")
            result = subprocess.run([sys.executable, str(REPOSITORY / "scripts/repo_vault.py"), "import", "--root",
                                     str(root), "--password-file", str(other_pw)], capture_output=True, text=True,
                                    env=env)
            self.assertEqual(result.returncode, 1)
            self.assertIn("ERROR", result.stderr)
            self.assertEqual(remove_exported(root), ["Production"])
            self.assertFalse(shared.exists())


    def test_certificate_private_keys_are_committed_only_encrypted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            local_pw = root / "local-pw"
            local_pw.write_text("local-password-123\n")
            local_pw.chmod(0o600)
            production = root / "environments/Production"
            key_text = "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n"
            for relative in ("certificates/ocp1/api.key", "certificates/everpure/array01.pem"):
                (production / relative).parent.mkdir(parents=True, exist_ok=True)
                (production / relative).write_text(key_text)
            (production / "certificates/everpure/array01.crt").write_text(
                "-----BEGIN CERTIFICATE-----\nx\n-----END CERTIFICATE-----\n")
            self.assertEqual(protect_private_keys(root), 2)
            ignore = (production / "certificates/.gitignore").read_text()
            self.assertIn("/everpure/array01.pem", ignore)
            self.assertIn("/ocp1/api.key", ignore)
            self.assertNotIn("array01.crt", ignore)
            self.assertEqual(export_secrets(root, local_pw, "repo-password-789"),
                             ["Production: 2 certificate private keys"])
            bundle = production / KEYS_VAULT_NAME
            self.assertTrue(bundle.read_text().startswith("$ANSIBLE_VAULT"))
            self.assertNotIn("PRIVATE KEY", bundle.read_text())
            (production / "certificates/ocp1/api.key").unlink()
            self.assertIn("Production: 1 certificate private keys restored",
                          import_secrets(root, local_pw, "repo-password-789"))
            restored = production / "certificates/ocp1/api.key"
            self.assertEqual(restored.read_text(), key_text)
            self.assertEqual(restored.stat().st_mode & 0o777, 0o600)
            self.assertEqual(remove_exported(root), ["Production"])
            self.assertFalse(bundle.exists())

    def test_git_commit_never_stages_a_pem_private_key(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            production = root / "environments/Production/certificates/everpure"
            production.mkdir(parents=True)
            (production / "array01.pem").write_text("-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----\n")
            (production / "array01.crt").write_text("-----BEGIN CERTIFICATE-----\nx\n-----END CERTIFICATE-----\n")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            protect_private_keys(root)
            subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
            staged = subprocess.run(["git", "-C", str(root), "diff", "--cached", "--name-only"], capture_output=True,
                                    text=True, check=True).stdout.split()
            self.assertIn("environments/Production/certificates/everpure/array01.crt", staged)
            self.assertNotIn("environments/Production/certificates/everpure/array01.pem", staged)


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class GitopsPushTest(unittest.TestCase):
    def run_push(self, directory: Path, url: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(REPOSITORY / "scripts/gitops_push.py"), "--directory", str(directory),
                               "--url", url, "--branch", "main"], capture_output=True, text=True,
                              env=dict(os.environ, gitops_git_token="secret-token-1"))

    def test_push_creates_branch_then_keeps_remote_only_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            remote = root / "remote.git"
            subprocess.run(["git", "init", "-q", "--bare", "--initial-branch", "main", str(remote)], check=True)
            url = f"ssh://localhost{remote}"
            work = root / "gitops"
            (work / "apps/lldpd").mkdir(parents=True)
            (work / "apps/lldpd/config.json").write_text("{}\n")
            # A file:// remote is not an accepted URL; point git at the bare repository through insteadOf.
            env_home = root / "home"
            env_home.mkdir()
            (env_home / ".gitconfig").write_text(f'[url "{remote}"]\n\tinsteadOf = {url}\n')
            os.environ["HOME_BACKUP"] = os.environ.get("HOME", "")
            os.environ["HOME"] = str(env_home)
            try:
                first = self.run_push(work, url)
                self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
                self.assertNotIn("secret-token-1", first.stdout + first.stderr)
                # Someone adds a file directly in the repository; the next push keeps it.
                clone = root / "clone"
                subprocess.run(["git", "clone", "-q", str(remote), str(clone)], check=True)
                (clone / "README.md").write_text("team notes\n")
                subprocess.run(["git", "-C", str(clone), "add", "README.md"], check=True)
                subprocess.run(["git", "-C", str(clone), "-c", "user.name=t", "-c", "user.email=t@x", "commit", "-qm",
                                "notes"], check=True)
                subprocess.run(["git", "-C", str(clone), "push", "-q", "origin", "HEAD:main"], check=True)
                (work / "apps/lldpd/config.json").write_text('{"deploymentWave": "-40"}\n')
                second = self.run_push(work, url)
                self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
                files = subprocess.run(["git", "--git-dir", str(remote), "ls-tree", "-r", "--name-only", "main"],
                                       capture_output=True, text=True, check=True).stdout.split()
                self.assertEqual(sorted(files), ["README.md", "apps/lldpd/config.json"])
                content = subprocess.run(["git", "--git-dir", str(remote), "show", "main:apps/lldpd/config.json"],
                                         capture_output=True, text=True, check=True).stdout
                self.assertIn("-40", content)
            finally:
                os.environ["HOME"] = os.environ.pop("HOME_BACKUP")

    def test_rejects_missing_content_and_bad_url(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(self.run_push(Path(folder), "https://example.com/r.git").returncode, 1)
            self.assertEqual(self.run_push(Path(folder), "file:///tmp/x").returncode, 1)


class IntersightScopeTest(unittest.TestCase):
    def test_scoped_copy_keeps_shared_files_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "host_vars/intersight"
            for relative in ("system.ezai.yaml", "domains/profiles.ezai.yaml", "domains/uploads/mine.ezai.yaml",
                             "servers/profiles.ezai.yaml", "system/uploads/orgs.ezai.yaml"):
                (source / relative).parent.mkdir(parents=True, exist_ok=True)
                (source / relative).write_text("intersight: {}\n")
            target = root / "scoped"
            target.mkdir()
            deploy_ai_pod.scoped_intersight_dir(root / "host_vars", "domains", target)
            found = sorted(path.relative_to(target).as_posix() for path in target.rglob("*.ezai.yaml"))
            self.assertEqual(found, ["domains/profiles.ezai.yaml", "domains/uploads/mine.ezai.yaml", "system.ezai.yaml",
                                     "system/uploads/orgs.ezai.yaml"])
            system = root / "system-only"
            system.mkdir()
            deploy_ai_pod.scoped_intersight_dir(root / "host_vars", "system", system)
            self.assertEqual(sorted(path.relative_to(system).as_posix() for path in system.rglob("*.ezai.yaml")),
                             ["system.ezai.yaml", "system/uploads/orgs.ezai.yaml"])
            command = deploy_ai_pod.command_for_role("intersight", root / "host_vars", True, target)
            self.assertEqual(command[command.index("--dir") + 1], str(target))
            empty = root / "empty"
            empty.mkdir()
            (source / "servers/profiles.ezai.yaml").unlink()
            with self.assertRaises(deploy_ai_pod.DeploymentError):
                deploy_ai_pod.scoped_intersight_dir(root / "host_vars", "servers", empty)


class VaultPrecedenceTest(unittest.TestCase):
    def test_role_section_wins_shared_names(self):
        sections = {"everpure": {"local_user_password_1": "pure", "everpure_api_token_1": "token"},
                    "intersight": {"local_user_password_1": "ucs"}}
        self.assertEqual(deploy_ai_pod.vault_environment(sections, "everpure")["local_user_password_1"], "pure")
        self.assertEqual(deploy_ai_pod.vault_environment(sections, "intersight")["local_user_password_1"], "ucs")
        self.assertEqual(deploy_ai_pod.vault_environment(sections)["everpure_api_token_1"], "token")


class GiteaUrlTest(unittest.TestCase):
    def test_url_from_cluster(self):
        url = custom_pages.gitea_repo_url("ocp1", "example.com")
        self.assertEqual(url, "https://gitea-with-admin-gitea-operator.apps.ocp1.example.com/"
                              "lab-user/openshift-gitops-repo.git")


if __name__ == "__main__":
    unittest.main()
