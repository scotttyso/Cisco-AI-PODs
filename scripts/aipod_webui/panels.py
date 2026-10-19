"""Reusable page building blocks: vault credentials, YAML workbench, and the automation job console."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml
from nicegui import run, ui

from . import seeds, stage_inventory
from .jobs import Job, JobManager
from .site_settings import WorkspaceStore
from .vault import TOP, SecretField, VaultError, VaultStore, sensitive_fields
from .yaml_editor import YamlEditor, validate_yaml

GROUPS = ("Pre-check", "Deploy", "Post-check", "Tools")


@contextmanager
def collapsible(title: str, icon: str, value: bool = True, caption: str = "", classes: str = ""):
    """Bordered, collapsible page section (the Initial Inventory style); yields the padded body column."""
    frame = ui.expansion(title, icon=icon, value=value, caption=caption or None).classes(
        f"w-full env-card page-section {classes}".strip())
    with frame:
        with ui.column().classes("w-full gap-3 p-4") as body:
            yield body


@dataclass
class UiContext:
    store: WorkspaceStore
    repository: Path
    output_dir: Path
    schema_path: Path
    schema_uri: str
    vault: VaultStore | None = None
    jobs: JobManager | None = None
    media_dir: Path = Path("/var/www/html/os-images")
    media_url: str = ""
    environment: str = ""

    @property
    def host_vars_dir(self) -> Path:
        return self.output_dir / "host_vars"

    @property
    def inventory_path(self) -> Path:
        return self.output_dir / "inventory" / "inventory.yml"

    @property
    def macs_dir(self) -> Path:
        return self.output_dir / "macs"

    def python(self) -> str:
        return sys.executable

    def vault_args(self, *names: str) -> list[str]:
        """``-e name=<vault file>`` pairs for playbooks that load the vault through vars_files."""
        arguments = []
        for name in names:
            arguments += ["-e", f"{name}={self.vault.vault_file}"]
        return arguments

    def deploy_args(self) -> list[str]:
        return [self.python(), str(self.repository / "scripts/deploy_ai_pod.py"), "--host-vars-dir", str(self.host_vars_dir),
                "--vault-file", str(self.vault.vault_file), "--vault-password-file", str(self.vault.password_file)]

    def collected_macs(self) -> dict:
        macs: dict = {}
        for path in sorted(self.macs_dir.glob("*.json")) if self.macs_dir.is_dir() else []:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for host, interfaces in (data.get("hosts") or {}).items():
                if isinstance(interfaces, dict):
                    macs.setdefault(seeds.host_key(host), {}).update(interfaces)
        return macs

    def seed_context(self) -> seeds.SeedContext:
        files = sorted(path.name for path in self.media_dir.glob("*") if path.is_file()) if self.media_dir.is_dir() else []
        state = {key: self.store.page_state(key) for key in ("ocp-cluster", "intersight-registration")}
        return seeds.SeedContext(self.store.inventory(), self.store.shared_services(), state, self.media_url,
                                 str(self.media_dir), files, self.collected_macs())

    def build_inventory(self) -> Path:
        state = {"intersight-registration": self.store.page_state("intersight-registration")}
        return stage_inventory.build(self.output_dir, self.host_vars_dir, self.store.inventory(),
                                     self.store.shared_services(), state)


@dataclass(frozen=True)
class FileSpec:
    example: str
    target: str
    seed: str = ""
    label: str = ""
    optional: bool = False

    @property
    def title(self) -> str:
        return self.label or self.target


@dataclass
class RunContext:
    ui: UiContext
    page: str
    state: dict
    files: dict[str, Path] = field(default_factory=dict)

    @property
    def inventory(self) -> Path:
        return self.ui.inventory_path

    def model(self, target: str) -> dict:
        try:
            return yaml.safe_load(self.files[target].read_text(encoding="utf-8")) or {}
        except (KeyError, OSError, yaml.YAMLError):
            return {}


@dataclass(frozen=True)
class Action:
    key: str
    label: str
    icon: str
    build: Callable[[RunContext], list[list[str]]]
    group: str = "Deploy"
    secrets: tuple[str, ...] = ()
    confirm: str = ""
    inventory: bool = False
    files: bool = True
    env: Callable[[RunContext], dict[str, str]] | None = None
    tooltip: str = ""
    # Ask for the local sudo password when the job starts (only if sudo needs one). It is exported to that job as
    # BECOME_PASSWORD / AIPOD_SUDO_PASSWORD (with SUDO_ASKPASS) and is never saved.
    sudo: bool = False


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.chmod(temporary, 0o640)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def show_problems(container, problems: list[str], title: str = "") -> None:
    container.clear()
    if not problems:
        return
    with container, ui.column().classes("validation-errors gap-1"):
        if title:
            ui.label(title).classes("font-medium")
        for message in problems[:50]:
            ui.label(message).classes("text-sm break-all")
        if len(problems) > 50:
            ui.label(f"... {len(problems) - 50} more").classes("text-sm muted")


def secret(key: str, label: str, *targets: tuple[str, str], multiline: bool = False, help: str = "",
           min_length: int = 0) -> SecretField:
    return SecretField(key, label, targets or ((TOP, key),), multiline, help, min_length)


class CredentialsPanel:
    """Write-only inputs for the vault values a page needs. Stored values are never sent to the browser."""

    def __init__(self, context: UiContext, fields: Callable[[], list[SecretField]], title: str = "Passwords and secrets",
                 visible: bool = True, embedded: bool = False, on_change: Callable[[], None] | None = None,
                 hide: tuple[str, ...] | dict[str, str] = ()):
        self.context = context
        self.fields = fields
        self.title, self.visible, self.embedded, self.on_change = title, visible, embedded, on_change
        # Keys still checked before a run but entered on another page or panel (dict values say where).
        self.hide = hide
        self.inputs: dict[str, ui.element] = {}
        self.container = ui.column().classes("w-full gap-2")
        self.render()

    def current(self) -> list[SecretField]:
        unique: dict[str, SecretField] = {}
        for item in self.fields():
            unique.setdefault(item.key, item)
        return list(unique.values())

    def _data(self) -> tuple[dict, str]:
        try:
            return self.context.vault.load(), ""
        except VaultError as error:
            return {}, str(error)

    def is_set(self, data: dict, item: SecretField) -> bool:
        return all(self.context.vault.is_set(data, section, key) for section, key in item.targets)

    def missing(self, keys: tuple[str, ...]) -> list[str]:
        if not keys:
            return []
        data, _ = self._data()
        known = {item.key: item for item in self.current()}
        wanted = [known[key] for key in keys if key in known] if "*" not in keys else list(known.values())
        return [item.label + (f" ({self.hide[item.key]})" if isinstance(self.hide, dict) and self.hide.get(item.key) else "")
                for item in wanted if not self.is_set(data, item)]

    def render(self) -> None:
        self.container.clear()
        self.inputs = {}
        fields = [item for item in self.current() if item.key not in self.hide]
        if not fields or not self.visible:
            return
        status = self.context.vault.status()
        data, error = self._data() if status["ready"] else ({}, "")
        missing = sum(not self.is_set(data, item) for item in fields)
        heading = f"{self.title} ({len(fields) - missing}/{len(fields)} stored in Ansible Vault)"
        with self.container:
            if self.embedded:
                frame = ui.column().classes("w-full gap-2")
                with frame:
                    ui.label(heading).classes("font-medium")
            else:
                with ui.expansion(heading, icon="lock", value=True).classes("w-full env-card page-section credentials"):
                    frame = ui.column().classes("w-full gap-2 p-4")
                with frame:
                    ui.label(f"Values are encrypted into {status['vault_file']} and passed to the automation as "
                             "variables. Stored values are never displayed; type a new value to replace one.").classes(
                        "muted text-xs")
        with frame:
            for problem in status["problems"] + ([error] if error else []):
                ui.label(problem).classes("text-sm text-negative")
            if not Path(status["password_file"]).exists():
                ui.button("Create vault password file", icon="key", on_click=self.create_password).props("outline dense")
                return
            for item in fields:
                stored = self.is_set(data, item)
                with ui.row().classes("w-full items-start gap-3 no-wrap"):
                    ui.icon("check_circle" if stored else "error_outline",
                            color="positive" if stored else "warning").classes("mt-3")
                    if item.multiline:
                        box = ui.textarea(item.label, placeholder="stored" if stored else "not set").props(
                            "outlined dense autogrow input-style=font-family:monospace").classes("grow")
                        ui.upload(auto_upload=True, max_files=1, max_file_size=256 * 1024,
                                  on_upload=lambda event, target=box: self._load_file(event, target)).props(
                            "flat dense hide-upload-btn label=Upload").style("width:120px")
                    else:
                        hint = f"at least {item.min_length} characters" if item.min_length else ""
                        box = ui.input(item.label, placeholder="stored" if stored else "not set", password=True,
                                       password_toggle_button=True).props(
                            f"outlined dense autocomplete=new-password hint='{hint}'" if hint else
                            "outlined dense autocomplete=new-password").classes("grow")
                    if item.help:
                        box.tooltip(item.help)
                    self.inputs[item.key] = box
                    ui.button(icon="delete", on_click=lambda key=item.key: self.clear(key)).props(
                        "flat round dense").tooltip("Remove the stored value").set_enabled(stored)
            with ui.row().classes("w-full justify-end"):
                ui.button("Save to vault", icon="lock", on_click=self.save).props("outline")

    @staticmethod
    async def _load_file(event, target) -> None:
        content = await event.file.read() if hasattr(event, "file") else event.content.read()
        target.set_value(content.decode("utf-8", "replace").strip())

    def create_password(self) -> None:
        try:
            self.context.vault.create_password()
        except VaultError as error:
            ui.notify(str(error), type="negative")
            return
        ui.notify(f"Created {self.context.vault.password_file} (mode 0600). Back it up securely.", type="positive")
        self.render()

    async def save(self) -> None:
        fields = {item.key: item for item in self.current()}
        changes = {}
        short = [fields[key].label for key, box in self.inputs.items()
                 if box.value and len(box.value) < fields[key].min_length]
        if short:
            ui.notify("Too short (minimum length not met): " + ", ".join(short), type="negative", multi_line=True)
            return
        for key, box in self.inputs.items():
            value = (box.value or "").strip() if fields[key].multiline else (box.value or "")
            if value:
                for target in fields[key].targets:
                    changes[target] = value
        if not changes:
            ui.notify("Type at least one value to store", type="warning")
            return
        try:
            await run.io_bound(self.context.vault.update, changes)
        except VaultError as error:
            ui.notify(f"Vault update failed: {error}", type="negative")
            return
        ui.notify(f"Stored {len({key for key in self.inputs if self.inputs[key].value})} values in the vault", type="positive")
        self.render()
        if self.on_change:
            self.on_change()

    async def clear(self, key: str) -> None:
        item = next(item for item in self.current() if item.key == key)
        try:
            await run.io_bound(self.context.vault.update, {target: None for target in item.targets})
        except VaultError as error:
            ui.notify(f"Vault update failed: {error}", type="negative")
            return
        ui.notify(f"Removed {item.label}", type="info")
        self.render()
        if self.on_change:
            self.on_change()


class Workbench:
    """Schema-validated YAML editor for the files a page owns under ``host_vars``."""

    def __init__(self, context: UiContext, files: tuple[FileSpec, ...],
                 on_saved: Callable[[str, str], None] | None = None):
        self.context = context
        self.specs = {spec.target: spec for spec in files if (context.repository / spec.example).is_file()}
        self.on_saved = on_saved
        if not self.specs:
            self.editor = None
            return
        first = next(iter(self.specs))
        text, origin = self.load(first)
        with collapsible("Variables", "data_object"):
            with ui.row().classes("toolbar"):
                with ui.row().classes("items-center gap-3"):
                    self.selector = ui.select(self.options(), value=first,
                                              label="File").props("outlined dense").style("min-width:340px")
                with ui.row().classes("items-center gap-2"):
                    if any(spec.seed for spec in self.specs.values()):
                        self.seed_button = ui.button("Refresh from inventory", icon="sync", on_click=self.reseed).props("flat")
                    ui.button("Validate", icon="fact_check", on_click=self.validate).props("outline")
                    ui.button("Save", icon="save", on_click=self.save)
                    ui.button(icon="restart_alt", on_click=self.revert).props("flat round").tooltip(
                        "Replace the editor content with the repository example")
                    ui.button(icon="download", on_click=self.download).props("flat round").tooltip("Download YAML")
                    if any(spec.optional for spec in self.specs.values()):
                        self.remove_button = ui.button(icon="delete", on_click=self.remove).props(
                            "flat round color=negative").tooltip("Remove the saved file so it is not deployed")
            self.source = ui.label(origin).classes("muted text-xs break-all")
            ui.label("Hover for field descriptions, Ctrl+Space for completion. Validation uses the Cisco AI PODs JSON "
                     "schema, the same as the VS Code Red Hat YAML extension.").classes("muted text-xs")
            self.editor = YamlEditor(text, context.schema_uri, height="520px")
            self.problems = ui.column().classes("w-full")
        self.selector.on_value_change(self.change_file)

    def path(self, target: str) -> Path:
        return self.context.host_vars_dir / target

    def saved_paths(self) -> dict[str, Path]:
        return {target: self.path(target) for target in self.specs}

    def options(self) -> dict[str, str]:
        """Selector labels with the save state; unsaved optional files are not deployed."""
        labels = {}
        for target, spec in self.specs.items():
            if self.path(target).is_file():
                state = "saved"
            elif spec.optional:
                state = "optional, not deployed"
            else:
                state = "required, not saved"
            labels[target] = f"{spec.title} ({state})"
        return labels

    def refresh_options(self) -> None:
        self.selector.set_options(self.options(), value=self.selector.value)

    async def remove(self) -> None:
        target = self.selector.value
        spec, path = self.specs[target], self.path(target)
        if not spec.optional:
            ui.notify(f"{spec.title} is required by this page and cannot be removed", type="warning")
            return
        if not path.is_file():
            ui.notify(f"{spec.title} is not saved, so it is already left out of the deployment", type="info")
            return
        with ui.dialog() as dialog, ui.card().classes("dialog-surface"):
            ui.label(f"Remove {spec.title}").classes("section-title")
            ui.label(f"Deletes {path}. The automation will not deploy it until it is saved again.").classes("text-sm")
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("flat")
                ui.button("Remove", icon="delete", on_click=lambda: dialog.submit(True)).props("color=negative")
        if not await dialog:
            return
        await run.io_bound(path.unlink, True)
        text, origin = self.load(target)
        self.editor.set_value(text)
        self.source.set_text(origin)
        self.problems.clear()
        self.refresh_options()
        ui.notify(f"Removed {path.name}; it will not be deployed", type="positive")

    def load(self, target: str) -> tuple[str, str]:
        spec = self.specs[target]
        saved = self.path(target)
        if saved.is_file():
            return saved.read_text(encoding="utf-8"), f"Saved: {saved}"
        text = (self.context.repository / spec.example).read_text(encoding="utf-8")
        if spec.seed:
            try:
                return seeds.apply_seed(spec.seed, text, self.context.seed_context()), \
                    f"Example {spec.example} pre-filled from the initial inventory (not saved yet)"
            except Exception as error:  # a seeding problem must not block editing
                return text, f"Example {spec.example} (inventory pre-fill failed: {error})"
        return text, f"Example {spec.example} (not saved yet)"

    def models(self) -> list[dict]:
        """Saved files, or the (pre-filled) example of required files not saved yet, so their secrets can be entered early."""
        models = []
        for target, path in self.saved_paths().items():
            if not path.is_file() and self.specs[target].optional:
                continue
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8") if path.is_file() else self.load(target)[0])
            except (OSError, yaml.YAMLError):
                data = None
            if isinstance(data, dict):
                models.append(data)
        return models

    @property
    def current(self) -> str:
        return self.selector.value if self.specs else ""

    async def content(self, target: str) -> str:
        """Editor text when ``target`` is open, else the saved file or (seeded) example."""
        if target == self.current:
            return await self.editor.get_value()
        return self.load(target)[0]

    async def open(self, target: str) -> None:
        if target in self.specs and target != self.current:
            self.selector.set_value(target)

    def set_content(self, target: str, text: str, note: str = "Updated from the form (not saved yet)") -> None:
        if target != self.current:
            self.selector.set_value(target)
        self.editor.set_value(text)
        self.source.set_text(note)

    def change_file(self, event) -> None:
        content, label = self.load(event.value)
        self.editor.set_value(content)
        self.source.set_text(label)
        self.problems.clear()

    async def check(self) -> tuple[str, list[str]]:
        content = await self.editor.get_value()
        _, issues = await run.io_bound(validate_yaml, content, self.context.schema_path)
        return content, issues

    async def validate(self) -> None:
        _, issues = await self.check()
        show_problems(self.problems, issues, "Schema validation failed")
        ui.notify("Valid" if not issues else f"{len(issues)} schema problems", type="positive" if not issues else "negative")

    async def save(self, quiet: bool = False) -> bool:
        content, issues = await self.check()
        show_problems(self.problems, issues, "Saved with schema problems; fix them before running automation")
        target = self.path(self.selector.value)
        await run.io_bound(write_text, target, content)
        self.source.set_text(f"Saved: {target}")
        self.refresh_options()
        if not quiet:
            ui.notify(f"Saved {target.name}" + (f" with {len(issues)} schema problems" if issues else ""),
                      type="warning" if issues else "positive")
        if self.on_saved:
            self.on_saved(self.selector.value, content)
        return not issues

    async def reseed(self) -> None:
        spec = self.specs[self.selector.value]
        if not spec.seed:
            ui.notify("This file has no inventory pre-fill", type="info")
            return
        try:
            text = await run.io_bound(seeds.apply_seed, spec.seed, await self.editor.get_value(), self.context.seed_context())
        except Exception as error:
            ui.notify(f"Cannot apply the inventory: {error}", type="negative")
            return
        self.editor.set_value(text)
        self.source.set_text(f"Refreshed from the initial inventory (not saved yet): {self.path(spec.target)}")
        ui.notify("Inventory values applied. Review the changes, then Save.", type="info")

    def revert(self) -> None:
        spec = self.specs[self.selector.value]
        self.editor.set_value((self.context.repository / spec.example).read_text(encoding="utf-8"))
        self.source.set_text(f"Example {spec.example} (not saved yet)")
        self.problems.clear()

    async def download(self) -> None:
        ui.download.content(await self.editor.get_value(), Path(self.selector.value).name)

    async def ready(self) -> bool:
        """Save the open file, then require every page file to exist and pass the schema.

        An unsaved optional file is only saved when it was edited, so a removed file is not recreated."""
        if not self.specs:
            return True
        target = self.selector.value
        keep_out = (self.specs[target].optional and not self.path(target).is_file()
                    and await self.editor.get_value() == self.load(target)[0])
        if not keep_out and not await self.save(quiet=True):
            ui.notify("Fix the schema problems in the open file before running", type="negative")
            return False
        problems = []
        saved = [target for target, path in self.saved_paths().items() if path.is_file()]
        if not saved:
            problems.append("Save at least one variable file first.")
        for target, path in self.saved_paths().items():
            if not path.is_file():
                if not self.specs[target].optional:
                    problems.append(f"{target}: not saved yet. Open it in the File list and Save.")
                continue
            _, issues = await run.io_bound(validate_yaml, path.read_text(encoding="utf-8"), self.context.schema_path)
            problems += [f"{target}: {issue}" for issue in issues]
        show_problems(self.problems, problems, "Resolve these before running automation")
        if problems:
            ui.notify("Saved variable files are incomplete or invalid", type="negative")
        return not problems


SUDO_ASKPASS = Path(__file__).resolve().parents[1] / "sudo_askpass.sh"


def sudo_needs_password() -> bool:
    """False when this account has passwordless sudo (the appliance and bare-metal service account)."""
    if shutil.which("sudo") is None:
        raise RuntimeError("sudo is not installed on this server")
    return subprocess.run(["sudo", "-n", "true"], stdin=subprocess.DEVNULL, capture_output=True,
                          timeout=15).returncode != 0


def sudo_password_ok(password: str) -> bool:
    result = subprocess.run(["sudo", "-k", "-S", "-p", "", "true"], input=password + "\n", text=True,
                            capture_output=True, timeout=30)
    return result.returncode == 0


def sudo_environment(password: str) -> dict[str, str]:
    return {"BECOME_PASSWORD": password, "AIPOD_SUDO_PASSWORD": password, "SUDO_ASKPASS": str(SUDO_ASKPASS)}


async def ask_sudo_password(title: str, message: str = "") -> str | None:
    """'' when sudo is passwordless, the verified password, or None when cancelled or sudo is unavailable."""
    try:
        if not await run.io_bound(sudo_needs_password):
            if message:
                with ui.dialog() as dialog, ui.card().classes("dialog-surface"):
                    ui.label(title).classes("section-title")
                    ui.label(message).classes("text-sm")
                    with ui.row().classes("w-full justify-end"):
                        ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("flat")
                        ui.button("Run", icon="play_arrow", on_click=lambda: dialog.submit(True))
                if not await dialog:
                    return None
            return ""
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        ui.notify(f"Cannot use sudo: {error}", type="negative")
        return None
    with ui.dialog() as dialog, ui.card().classes("dialog-surface").style("width:min(520px,94vw)"):
        ui.label(title).classes("section-title")
        if message:
            ui.label(message).classes("text-sm")
        ui.label("This step runs with sudo. Enter your local sudo password; it is used for this run only and is "
                 "not saved.").classes("muted text-xs")
        password = ui.input("Sudo password", password=True, password_toggle_button=True).props(
            "outlined dense autocomplete=off autofocus").classes("w-full")
        problem = ui.label("").classes("text-negative text-xs")

        async def submit():
            if not password.value:
                problem.set_text("Enter the sudo password")
                return
            if not await run.io_bound(sudo_password_ok, password.value):
                problem.set_text("sudo rejected that password")
                return
            dialog.submit(password.value)

        password.on("keydown.enter", submit)
        with ui.row().classes("w-full justify-end"):
            ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat")
            ui.button("Run", icon="play_arrow", on_click=submit)
    result = await dialog
    password.set_value("")
    return result


def job_environment(context: UiContext, scratch: Path, extra: dict[str, str] | None = None) -> tuple[dict, list[str]]:
    env = dict(os.environ)
    redact: list[str] = []
    status = context.vault.status()
    if status["ready"] and status["exists"]:
        values, redact = context.vault.environment(scratch)
        env.update(values)
        env["ANSIBLE_VAULT_PASSWORD_FILE"] = str(context.vault.password_file)
    env.update(PYTHONUNBUFFERED="1", ANSIBLE_NOCOLOR="1", ANSIBLE_FORCE_COLOR="0", ANSIBLE_HOST_KEY_CHECKING="False",
               ANSIBLE_CONFIG=str(context.repository / "ansible.cfg"), ANSIBLE_RETRY_FILES_ENABLED="0")
    env["PATH"] = os.pathsep.join([str(Path(sys.executable).parent), env.get("PATH", "")])
    env.update(extra or {})
    return env, redact


class JobConsole:
    """Action buttons plus a live, redacted view of the page's automation output and history."""

    def __init__(self, context: UiContext, page: str, actions: tuple[Action, ...], state: Callable[[], dict],
                 ready: Callable | None = None, credentials: CredentialsPanel | None = None,
                 files: Callable[[], dict[str, Path]] | None = None):
        self.context, self.page, self.actions = context, page, {action.key: action for action in actions}
        self.state, self.ready, self.credentials, self.files = state, ready, credentials, files
        self.viewing: Job | None = None
        self.shown_status = ""
        self.offset = 0
        self.pending = ""
        if not actions:
            return
        with collapsible("Automation", "play_circle", classes="job-console"):
            with ui.element("div").classes("action-groups"):
                for group in GROUPS:
                    members = [action for action in actions if action.group == group]
                    if not members:
                        continue
                    with ui.column().classes("gap-1"):
                        ui.label(group).classes("muted text-xs uppercase")
                        with ui.row().classes("gap-2"):
                            for action in members:
                                button = ui.button(action.label, icon=action.icon,
                                                   on_click=lambda key=action.key: self.run(key))
                                button.props("outline" if group != "Deploy" else "")
                                if action.tooltip:
                                    button.tooltip(action.tooltip)
            with ui.row().classes("w-full items-center gap-2"):
                self.status = ui.badge("idle", color="grey").props("outline")
                self.history_select = ui.select({}, label="Run history", on_change=self.pick).props(
                    "outlined dense options-dense").classes("grow")
                self.cancel_button = ui.button("Stop", icon="stop", color="negative", on_click=self.cancel).props("outline dense")
                ui.button(icon="download", on_click=self.download).props("flat round dense").tooltip("Download this log")
            self.log = ui.log(max_lines=5000).classes("w-full job-log")
        self.refresh_history()
        history = context.jobs.history(page)
        if history:
            self.show(history[0])
        self.timer = ui.timer(1.0, self.poll)

    def refresh_history(self) -> None:
        options = {job.id: f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(job.started))}  {job.label}  [{job.status}]"
                   for job in self.context.jobs.history(self.page)}
        self.history_select.set_options(options, value=self.viewing.id if self.viewing and self.viewing.id in options else None)

    def pick(self, event) -> None:
        if self.viewing and event.value == self.viewing.id:
            return
        job = next((job for job in self.context.jobs.history(self.page) if job.id == event.value), None)
        if job:
            self.show(job)

    def show(self, job: Job) -> None:
        self.viewing, self.offset, self.pending = job, 0, ""
        self.shown_status = job.status
        self.log.clear()
        self.poll()

    def poll(self) -> None:
        running = self.context.jobs.running(self.page)
        self.cancel_button.set_enabled(running is not None)
        if not self.viewing:
            return
        text, self.offset = JobManager.read(self.viewing, self.offset)
        if text:
            text = self.pending + text
            complete, _, self.pending = text.rpartition("\n")
            if complete:
                self.log.push(complete)
        job = self.viewing
        if running and running.id == job.id:
            self.status.set_text(f"running: {job.label}")
            self.status.props("color=primary")
            if self.shown_status != "running":
                self.shown_status = "running"
                self.refresh_history()
        else:
            finished = next((item for item in self.context.jobs.history(self.page) if item.id == job.id), job)
            if finished.status != self.shown_status:
                self.viewing, self.shown_status = finished, finished.status
                if self.pending:
                    self.log.push(self.pending)
                    self.pending = ""
                text, self.offset = JobManager.read(finished, self.offset)
                if text:
                    self.log.push(text.rstrip("\n"))
                self.refresh_history()
                ui.notify(f"{finished.label}: {finished.status}", type="positive" if finished.status == "succeeded" else "negative")
            colors = {"succeeded": "positive", "failed": "negative", "cancelled": "warning"}
            self.status.set_text(f"{self.viewing.status}: {self.viewing.label}")
            self.status.props(f"color={colors.get(self.viewing.status, 'grey')}")

    def cancel(self) -> None:
        if self.context.jobs.cancel(self.page):
            ui.notify("Stopping the running job", type="warning")

    def download(self) -> None:
        if self.viewing and Path(self.viewing.log).is_file():
            ui.download.file(self.viewing.log, f"{self.page}-{self.viewing.id}.log")

    async def run(self, key: str) -> None:
        action = self.actions[key]
        if self.context.jobs.running(self.page):
            ui.notify("A job is already running on this page", type="warning")
            return
        status = self.context.vault.status()
        if action.secrets and not status["ready"]:
            ui.notify("Set up the vault in the Credentials panel first: " + "; ".join(status["problems"]), type="negative",
                      multi_line=True)
            return
        if action.files and self.ready and not await self.ready():
            return
        missing = self.credentials.missing(action.secrets) if self.credentials else []
        if missing:
            ui.notify("Store these credentials first: " + ", ".join(missing), type="negative", multi_line=True)
            return
        sudo_password = None
        if action.sudo:
            if not action.inventory:
                # Report problems (missing files, listen interfaces, ...) before asking for the password.
                try:
                    action.build(RunContext(self.context, self.page, self.state(), self.files() if self.files else {}))
                except (RuntimeError, ValueError, OSError) as error:
                    ui.notify(f"Cannot start {action.label}: {error}", type="negative", multi_line=True)
                    return
            sudo_password = await ask_sudo_password(action.label, action.confirm)
            if sudo_password is None:
                return
        elif action.confirm:
            with ui.dialog() as dialog, ui.card().classes("dialog-surface"):
                ui.label(action.label).classes("section-title")
                ui.label(action.confirm).classes("text-sm")
                with ui.row().classes("w-full justify-end"):
                    ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("flat")
                    ui.button("Run", icon="play_arrow", on_click=lambda: dialog.submit(True))
            if not await dialog:
                return
        try:
            if action.inventory:
                await run.io_bound(self.context.build_inventory)
            run_context = RunContext(self.context, self.page, self.state(), self.files() if self.files else {})
            commands = action.build(run_context)
            scratch = Path(tempfile.mkdtemp(prefix="aipod-job-"))
            extra = dict(action.env(run_context) if action.env else {})
            if sudo_password is not None:
                extra.update(sudo_environment(sudo_password))
            env, redact = await run.io_bound(job_environment, self.context, scratch, extra)
            if sudo_password:
                redact = [*redact, sudo_password]
            job = self.context.jobs.start(self.page, action.label, commands, env, self.context.repository, redact,
                                          cleanup=lambda: shutil.rmtree(scratch, ignore_errors=True))
        except (RuntimeError, ValueError, OSError, VaultError) as error:
            ui.notify(f"Cannot start {action.label}: {error}", type="negative", multi_line=True)
            return
        self.show(job)
        self.refresh_history()


def model_secret_fields(models: list[dict]) -> list[SecretField]:
    fields: dict[str, SecretField] = {}
    for model in models:
        try:
            found = sensitive_fields(model)
        except Exception:  # an unexpected model shape must not hide the rest of the page
            continue
        for item in found:
            fields.setdefault(item.key, item)
    return list(fields.values())
