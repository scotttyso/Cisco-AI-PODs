"""Named deployment environments (for example production / pre-production) stored in one git repository.

Layout of the deployments repository::

    <root>/.gitignore
    <root>/environments/<name>/workspace/   initial inventory, shared services, page state
    <root>/environments/<name>/host_vars/   page YAML files (*.ezai.yaml)
    <root>/environments/<name>/vault.yaml   Ansible Vault with this environment's secrets, encrypted with this server's
                                            vault password. Never committed.
    <root>/environments/<name>/secrets.vault.yaml   optional copy of those secrets re-encrypted with the repository
                                            vault password chosen on the Git panel; committed only when enabled.
    <root>/environments/<name>/...          generated inventories, DHCP render, collected MACs

Run history stays outside the repository under ``<app dir>/jobs/<name>``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from .jobs import JobManager
from .panels import UiContext
from .site_settings import WorkspaceStore, load_json, write_json
from .vault import SECTIONS, TOP, SecretField, VaultStore

NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}")
DEFAULT_ENVIRONMENT = "default"
VAULT_NAME = "vault.yaml"
REPO_VAULT_NAME = "secrets.vault.yaml"
REPO_PASSWORD_ENV = "GIT_REPO_PASSWORD"
GIT_TOKEN = SecretField("vault_git_token", "Git access token (GitHub personal access token)",
                        ((TOP, "vault_git_token"),),
                        help="Used only for HTTPS push / pull. Stored in a local vault that is never committed.")
REPO_PASSWORD = SecretField("vault_git_repo_password", "Repository vault password", ((TOP, "vault_git_repo_password"),),
                            help="Encrypts the secrets committed to the repository. Keep a copy somewhere safe: it is "
                                 "needed to restore them on another server. It is not the automation vault password.",
                            min_length=12)
GITIGNORE = """\
# Managed by the Cisco AI PODs UI. The automation vault (vault.yaml) is encrypted with this server's own
# password and is never committed; secrets.vault.yaml (repository vault password) is committed only when
# enabled on the Git panel. Vault passwords, private keys, kubeconfigs, and scratch files are never committed.
vault.yaml
*vault-password*
*.vault-pass
*.key
*id_rsa*
*id_ed25519*
kubeconfig*
**/auth/
*.part
.*.tmp
__pycache__/
"""


class EnvironmentProblem(ValueError):
    pass


def check_name(name: str) -> str:
    name = (name or "").strip()
    if not NAME_PATTERN.fullmatch(name) or name in (".", ".."):
        raise EnvironmentProblem("Use 1-63 letters, numbers, dots, underscores, or hyphens (no spaces), starting with a "
                               "letter or number, for example Production or pre-production")
    return name


@dataclass
class GitSettings:
    remote_url: str = ""
    branch: str = "main"
    username: str = ""
    author_name: str = ""
    author_email: str = ""
    store_secrets: bool = False


class EnvironmentManager:
    """Creates environments and hands out one cached UiContext per environment."""

    def __init__(self, root: Path, app_dir: Path, password_file: Path, validate: Callable[[dict], list[str]],
                 base: UiContext):
        self.root = Path(root)
        self.app_dir = Path(app_dir)
        self.password_file = Path(password_file)
        self.validate = validate
        self.base = base
        self._contexts: dict[str, UiContext] = {}
        self._lock = threading.Lock()
        self.git_vault = VaultStore(self.app_dir / "vault-git.yaml", self.password_file)
        self.git_jobs = JobManager(self.app_dir / "jobs" / "_git")
        self.settings_path = self.app_dir / "git-settings.json"

    @property
    def environments_dir(self) -> Path:
        return self.root / "environments"

    def path(self, name: str) -> Path:
        return self.environments_dir / check_name(name)

    def names(self) -> list[str]:
        if not self.environments_dir.is_dir():
            return []
        return sorted((path.name for path in self.environments_dir.iterdir()
                       if path.is_dir() and NAME_PATTERN.fullmatch(path.name)), key=str.casefold)

    def exists(self, name: str) -> bool:
        try:
            return self.path(name).is_dir()
        except EnvironmentProblem:
            return False

    def ensure_root(self) -> None:
        self.environments_dir.mkdir(parents=True, exist_ok=True)
        gitignore = self.root / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(GITIGNORE, encoding="utf-8")
            return
        current = gitignore.read_text(encoding="utf-8")
        lines = set(current.splitlines())
        missing = [line for line in GITIGNORE.splitlines() if line and not line.startswith("#") and line not in lines]
        if missing:
            gitignore.write_text(current.rstrip("\n") + "\n" + "\n".join(missing) + "\n", encoding="utf-8")

    def create(self, name: str, copy_from: str = "") -> str:
        name = check_name(name)
        target = self.path(name)
        if any(existing.casefold() == name.casefold() for existing in self.names()):
            raise EnvironmentProblem(f"Environment {name} already exists")
        self.ensure_root()
        if copy_from:
            # Inventory, shared services, and page files carry over; secrets do not.
            shutil.copytree(self.path(copy_from), target, ignore=shutil.ignore_patterns(VAULT_NAME))
        else:
            (target / "workspace").mkdir(parents=True)
        return name

    def migrate_legacy(self, workspace_dir: Path, output_dir: Path, vault_file: Path) -> str | None:
        """Copy the pre-environment workspace, output folder, and vault into ``default`` (originals are kept)."""
        if self.names():
            return None
        sources = [path for path in (workspace_dir, output_dir, vault_file) if path.exists()]
        has_data = any(path.is_file() or any(path.iterdir()) for path in sources)
        target = self.path(DEFAULT_ENVIRONMENT)
        self.ensure_root()
        (target / "workspace").mkdir(parents=True, exist_ok=True)
        if not has_data:
            return DEFAULT_ENVIRONMENT
        if output_dir.is_dir():
            shutil.copytree(output_dir, target, dirs_exist_ok=True)
        if workspace_dir.is_dir():
            shutil.copytree(workspace_dir, target / "workspace", dirs_exist_ok=True)
        if vault_file.is_file():
            shutil.copy2(vault_file, target / VAULT_NAME)
        return DEFAULT_ENVIRONMENT

    def context(self, name: str) -> UiContext:
        name = check_name(name)
        with self._lock:
            if name not in self._contexts:
                folder = self.path(name)
                (folder / "workspace").mkdir(parents=True, exist_ok=True)
                self._contexts[name] = replace(
                    self.base, store=WorkspaceStore(folder / "workspace", self.validate), output_dir=folder,
                    vault=VaultStore(folder / VAULT_NAME, self.password_file),
                    jobs=JobManager(self.app_dir / "jobs" / name), environment=name)
            return self._contexts[name]

    # --- git -------------------------------------------------------------------------------------------------------

    def git_settings(self) -> GitSettings:
        data = load_json(self.settings_path, {})
        known = GitSettings.__dataclass_fields__
        return GitSettings(**{key: bool(value) if key == "store_secrets" else str(value)
                              for key, value in (data if isinstance(data, dict) else {}).items() if key in known})

    def save_git_settings(self, settings: GitSettings) -> None:
        if settings.remote_url and not re.fullmatch(r"(https://|ssh://|git@)[^\s]+", settings.remote_url):
            raise EnvironmentProblem("The remote URL must start with https://, ssh://, or git@")
        if not re.fullmatch(r"[A-Za-z0-9._/-]{1,100}", settings.branch or ""):
            raise EnvironmentProblem("Enter a valid branch name, for example main")
        write_json(self.settings_path, settings.__dict__)
        self.ensure_repository()
        self._git("remote", "remove", "origin", check=False)
        if settings.remote_url:
            self._git("remote", "add", "origin", settings.remote_url)

    def _git(self, *arguments: str, check: bool = True) -> str:
        result = subprocess.run(["git", "-C", str(self.root), *arguments], capture_output=True, text=True, timeout=60)
        if check and result.returncode:
            raise EnvironmentProblem(result.stderr.strip() or result.stdout.strip() or f"git {arguments[0]} failed")
        return result.stdout

    def ensure_repository(self) -> None:
        self.ensure_root()
        if not (self.root / ".git").exists():
            branch = self.git_settings().branch or "main"
            self._git("init", "--quiet", "--initial-branch", branch)

    def git_status(self) -> str:
        if not (self.root / ".git").exists():
            return "Not a git repository yet. Save the repository settings to initialize it."
        return self._git("status", "--short", "--branch", check=False).strip() or "Clean"

    def repo_vault_command(self, operation: str, python: str) -> list[str]:
        return [python, str(Path(__file__).resolve().parents[1] / "repo_vault.py"), operation, "--root", str(self.root),
                "--password-file", str(self.password_file)]

    def git_commands(self, operation: str, message: str = "", author: str = "", python: str = "python3") -> list[list[str]]:
        settings = self.git_settings()
        branch = settings.branch or "main"
        name = settings.author_name or author or "Cisco AI PODs UI"
        email = settings.author_email or f"{re.sub(r'[^A-Za-z0-9._-]', '', name) or 'aipod'}@localhost"
        git = ["git", "-C", str(self.root), "-c", f"user.name={name}", "-c", f"user.email={email}"]
        if operation == "commit":
            self.ensure_repository()
            # Older repositories committed vault.yaml; untrack it so only the repository-password copy is shared.
            # A clean tree is not an error: report it instead of failing the job.
            script = ("git rm -r -q --cached --ignore-unmatch -- ':(glob)environments/*/vault.yaml' && "
                      'git add -A && git status --short && if git diff --cached --quiet; then echo "Nothing to commit"; '
                      'else git commit -m "$AIPOD_COMMIT_MESSAGE"; fi')
            commit = ["env", f"AIPOD_COMMIT_MESSAGE={message or 'Update deployment environments'}",
                      f"GIT_AUTHOR_NAME={name}", f"GIT_AUTHOR_EMAIL={email}", f"GIT_COMMITTER_NAME={name}",
                      f"GIT_COMMITTER_EMAIL={email}", "sh", "-c", f"cd {shell_quote(str(self.root))} && {script}"]
            return [self.repo_vault_command("export" if settings.store_secrets else "remove", python), commit]
        if not settings.remote_url:
            raise EnvironmentProblem("Set the remote repository URL first")
        if operation == "push":
            return [git + ["push", "--set-upstream", "origin", f"HEAD:refs/heads/{branch}"]]
        if operation == "pull":
            pull = [git + ["pull", "--ff-only", "origin", branch]]
            return pull + ([self.repo_vault_command("import", python)] if settings.store_secrets else [])
        raise EnvironmentProblem(f"Unknown git operation {operation}")

    def git_environment(self, askpass: Path) -> dict[str, str]:
        settings = self.git_settings()
        return {"GIT_ASKPASS": str(askpass), "GIT_TERMINAL_PROMPT": "0",
                "AIPOD_GIT_USERNAME": settings.username or "x-access-token"}


# --- repository vault -----------------------------------------------------------------------------------------------

def _flatten(data: dict) -> dict[tuple[str, str], str]:
    changes = {}
    for key, value in data.items():
        if key in SECTIONS and isinstance(value, dict):
            changes.update({(key, name): item for name, item in value.items()})
        elif isinstance(key, str) and not isinstance(value, dict):
            changes[(TOP, key)] = value
    return changes


class _PasswordFile:
    """A 0600 temporary file holding a vault password, removed on exit."""

    def __init__(self, password: str):
        self.password = password

    def __enter__(self) -> Path:
        descriptor, name = tempfile.mkstemp(prefix=".aipod-repo-")
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(self.password + "\n")
        os.chmod(name, 0o600)
        self.path = Path(name)
        return self.path

    def __exit__(self, *_) -> None:
        self.path.unlink(missing_ok=True)


def _environment_dirs(root: Path) -> list[Path]:
    folder = Path(root) / "environments"
    return sorted(path for path in folder.iterdir() if path.is_dir()) if folder.is_dir() else []


def export_secrets(root: Path, password_file: Path, repo_password: str) -> list[str]:
    """Re-encrypt each environment's vault.yaml with the repository password into secrets.vault.yaml."""
    if len(repo_password or "") < 12:
        raise EnvironmentProblem("Store a repository vault password (at least 12 characters) first")
    report = []
    with _PasswordFile(repo_password) as repo_file:
        for folder in _environment_dirs(root):
            local, target = folder / VAULT_NAME, folder / REPO_VAULT_NAME
            if not local.is_file():
                target.unlink(missing_ok=True)
                continue
            data = VaultStore(local, password_file).load()
            target.unlink(missing_ok=True)
            VaultStore(target, repo_file).update(_flatten(data))
            report.append(f"{folder.name}: {len(_flatten(data))} secrets")
    return report


def remove_exported(root: Path) -> list[str]:
    removed = []
    for folder in _environment_dirs(root):
        if (folder / REPO_VAULT_NAME).is_file():
            (folder / REPO_VAULT_NAME).unlink()
            removed.append(folder.name)
    return removed


def import_secrets(root: Path, password_file: Path, repo_password: str) -> list[str]:
    """Merge each environment's secrets.vault.yaml into its local vault.yaml; repository values win."""
    if len(repo_password or "") < 12:
        raise EnvironmentProblem("Store the repository vault password (at least 12 characters) first")
    report = []
    with _PasswordFile(repo_password) as repo_file:
        for folder in _environment_dirs(root):
            source = folder / REPO_VAULT_NAME
            if not source.is_file():
                continue
            changes = _flatten(VaultStore(source, repo_file).load())
            if changes:
                VaultStore(folder / VAULT_NAME, password_file).update(changes)
            report.append(f"{folder.name}: {len(changes)} secrets")
    return report


def repository_visibility(url: str, timeout: float = 5.0) -> str:
    """'public', 'private' (not visible without credentials), or 'unknown' for a GitHub HTTPS / SSH remote URL."""
    match = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", url or "")
    if not match:
        return "unknown"
    request = urllib.request.Request(f"https://api.github.com/repos/{match.group(1)}/{match.group(2)}",
                                     headers={"Accept": "application/vnd.github+json", "User-Agent": "aipod-ui"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return "private" if json.load(response).get("private") else "public"
    except urllib.error.HTTPError as error:
        return "private" if error.code == 404 else "unknown"
    except (OSError, ValueError):
        return "unknown"


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def read_active(storage: dict, manager: EnvironmentManager) -> str:
    name = storage.get("environment", "")
    if manager.exists(name):
        return name
    names = manager.names()
    return DEFAULT_ENVIRONMENT if DEFAULT_ENVIRONMENT in names or not names else names[0]


def describe(manager: EnvironmentManager, name: str) -> dict:
    folder = manager.path(name)
    files = sorted(path.relative_to(folder).as_posix() for path in folder.rglob("*.ezai.yaml")) if folder.is_dir() else []
    inventory = load_json(folder / "workspace" / "initial_inventory.json", [])
    return {"files": files, "devices": len(inventory) if isinstance(inventory, list) else 0,
            "vault": (folder / VAULT_NAME).is_file(), "path": str(folder)}


__all__ = ["EnvironmentManager", "EnvironmentProblem", "GitSettings", "GIT_TOKEN", "REPO_PASSWORD", "check_name",
           "describe", "export_secrets", "import_secrets", "read_active", "remove_exported", "repository_visibility"]
