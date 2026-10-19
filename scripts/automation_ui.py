#!/usr/bin/env python3
"""Authenticated inventory and installation-media workspace for Cisco AI PODs."""

import argparse
import asyncio
import ipaddress
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import tempfile
import sys
import threading
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import requests
from nicegui import app, run, ui

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ENV_PREP_SCRIPTS = REPOSITORY_ROOT / "00-environment-prep/automation/scripts"
if ENV_PREP_SCRIPTS.is_dir() and str(ENV_PREP_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(ENV_PREP_SCRIPTS))

from build_initial_inventory import (  # noqa: E402
    DEFAULT_SCHEMA, build_inventory_document, normalize_mac, read_inventory_files, validate_shared_services,
)
from release_updates import (  # noqa: E402
    install_instructions, installed_version, latest_release, latest_update_log, update_command, update_unit,
    updater_available,
)
from aipod_webui import pages, seeds  # noqa: E402
from aipod_webui.dhcp_model import DEFAULT_BOOTSTRAP_NETWORK, host_interfaces  # noqa: E402
from aipod_webui.environments import (  # noqa: E402
    GIT_TOKEN, REPO_PASSWORD, EnvironmentManager, EnvironmentProblem, GitSettings, check_name, describe, read_active, repository_visibility,
)
from aipod_webui.jobs import JobManager  # noqa: E402
from aipod_webui.panels import (  # noqa: E402
    Action, CredentialsPanel, JobConsole, UiContext, ask_sudo_password, sudo_environment,
)
from aipod_webui.vault import VaultError  # noqa: E402
from aipod_webui.yaml_editor import SCHEMA_ROUTE, add_head, register_static  # noqa: E402


APP_DIR = Path(os.environ.get("AI_PODS_APP_DIR", Path(__file__).resolve().parent))
MEDIA_DIR = Path(os.environ.get("AI_PODS_MEDIA_DIR", "/var/www/html/os-images"))
SCHEMA_PATH = Path(os.environ.get("AI_PODS_SCHEMA", DEFAULT_SCHEMA))
BUNDLED_SCHEMA = Path(os.environ.get("AI_PODS_BUNDLED_SCHEMA", REPOSITORY_ROOT / "schema/cisco-ai-pods.json"))
DEPLOYMENTS_DIR = Path(os.environ.get("AI_PODS_DEPLOYMENTS_DIR", APP_DIR / "deployments"))
VAULT_PASSWORD_FILE = Path(os.environ.get("AI_PODS_VAULT_PASSWORD_FILE",
                                          Path.home() / ".config/cisco-ai-pods/vault-password"))
# Pre-environment locations, copied once into the "default" environment.
LEGACY_OUTPUT_DIR = Path(os.environ.get("AI_PODS_OUTPUT_DIR", "/home/automation-ui/playbooks/vars"))
LEGACY_WORKSPACE_DIR = Path(os.environ.get("AI_PODS_WORKSPACE_DIR", APP_DIR / "workspace"))
LEGACY_VAULT_FILE = Path(os.environ.get("AI_PODS_VAULT_FILE", APP_DIR / "vault-ai-pod.yaml"))
GIT_ASKPASS = REPOSITORY_ROOT / "scripts/git_askpass.sh"
ENVIRONMENTS = EnvironmentManager(
    DEPLOYMENTS_DIR, APP_DIR, VAULT_PASSWORD_FILE, lambda settings: validate_shared_services(settings, SCHEMA_PATH),
    UiContext(store=None, repository=REPOSITORY_ROOT, output_dir=DEPLOYMENTS_DIR, schema_path=BUNDLED_SCHEMA,
              schema_uri=f"{SCHEMA_ROUTE}/{BUNDLED_SCHEMA.name}", media_dir=MEDIA_DIR))
RECOMMENDED_NO_PROXY = ("localhost", "127.0.0.1", ".cluster.local", ".svc.cluster.local", "198.18.0.0/16")
LDAP_INPUTS = (("url", "LDAP URL", "ldaps://ad.example.com:636"), ("base_dn", "Base DN", "DC=example,DC=com"),
               ("bind_dn", "Bind DN", "CN=Service Account,OU=Service Accounts,DC=example,DC=com"),
               ("base_dn_users", "Users base DN (optional)", "OU=Users,DC=example,DC=com"),
               ("base_dn_groups", "Groups base DN (optional)", "OU=Groups,DC=example,DC=com"))
LDAP_FIELDS = tuple(name for name, _, _ in LDAP_INPUTS)
AUTH_FILE = APP_DIR / "users.json"
AUTH_LOCK = threading.Lock()
MEDIA_LOCK = asyncio.Lock()

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700&display=swap');
:root {--workspace:#f0f1f2;--surface:#fff;--sidebar:#fff;--border:#d0d4d9;
 --ink:#23282e;--muted:#656c75;--accent:#0d5cbd;--subtle:#e3eeff;}
.body--dark {--workspace:#0f1824;--surface:#151c24;--sidebar:#0a1119;
 --border:#2d3743;--ink:#e1e4e8;--muted:#a7adb5;--accent:#33bbf5;--subtle:#172c40;}
body {font-family:'Public Sans',sans-serif;background:var(--workspace);color:var(--ink);letter-spacing:0;}
.nicegui-content {padding:0;gap:0;}
.topbar {background:linear-gradient(100deg,#283f66,#0d274d 60%,#091b33);color:#fff;height:58px;padding:0 16px;}
.topbar-inner {width:100%;height:100%;gap:12px;flex-wrap:nowrap;}
.brand {font-size:19px;font-weight:600;white-space:nowrap;}
.brand-divider {width:1px;height:24px;background:#ffffff35;margin:0 12px;}
.account-name {font-size:13px;color:#d0d4d9;}
.q-drawer {background:var(--sidebar);border-right:1px solid var(--border);}
.nav-section .q-item {min-height:40px;padding:4px 12px;}
.nav-section .q-expansion-item__content {padding:0 0 6px;}
.nav-page {width:100%;min-height:34px;font-size:13px;color:var(--ink) !important;border-radius:4px;padding-left:28px;
 white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.nav-page .q-btn__content {flex-wrap:nowrap;}
.nav-page.nav-grouped {padding-left:42px;}
.nav-group {font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;
 padding:10px 12px 2px 28px;}
.nav-page:hover {background:var(--subtle);}
.nav-page.nav-active {background:var(--subtle);color:var(--accent) !important;font-weight:600;}
.page-select {min-width:320px;max-width:100%;}
.environment-select {min-width:170px;}
.env-card {border:1px solid var(--border);border-radius:4px;background:var(--surface);}
.page-section {margin-top:16px;}
.page-section > .q-expansion-item__container > .q-item {min-height:48px;font-weight:600;font-size:15px;}
.stage-readme {max-height:420px;overflow:auto;font-size:13px;}
.nav-heading {font-size:11px;color:var(--muted);font-weight:600;text-transform:uppercase;padding:24px 12px 12px;}
.nav-button {width:100%;min-height:40px;color:var(--ink);border-radius:4px;}
.nav-button:hover {background:var(--subtle);}
.work-area {width:100%;max-width:1680px;margin:0 auto;padding:24px 30px;min-width:0;}
.page-title {font-size:23px;font-weight:600;line-height:1.3;}
.env-banner {display:inline-flex;align-items:center;gap:6px;padding:3px 12px;border-radius:999px;font-size:13px;
  font-weight:500;background:rgba(2,123,193,.12);color:var(--q-primary);border:1px solid rgba(2,123,193,.45);
  white-space:nowrap;}
.env-banner-name {font-weight:700;}
.git-warning {background:rgba(193,21,21,.12);border:1px solid rgba(193,21,21,.55);border-radius:8px;padding:8px 12px;}
.section-title {font-size:17px;font-weight:600;}
.muted {color:var(--muted);}
.workspace-tabs {border-bottom:1px solid var(--border);margin-top:16px;}
.q-tab {text-transform:none;min-height:42px;letter-spacing:0;}
.q-tab-panels,.q-tab-panel {background:transparent;}
.q-tab-panel {padding:20px 0;}
.metrics {display:flex;width:100%;gap:32px;padding:0 0 20px;border-bottom:1px solid var(--border);margin-bottom:20px;}
.metric-value {font-size:24px;font-weight:600;}
.metric-label {font-size:12px;color:var(--muted);}
.toolbar {width:100%;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px;}
.q-uploader {background:var(--surface);border:1px solid var(--border);box-shadow:none;border-radius:4px;}
.q-uploader__header {background:var(--subtle);color:var(--ink);}
.q-uploader__list {min-height:56px;}
.q-btn {letter-spacing:0;border-radius:4px;text-transform:none;}
.q-field--outlined .q-field__control:before {border-color:var(--border);}
.q-field__control {background:var(--surface);}
.q-table__container {background:var(--surface);border:1px solid var(--border);box-shadow:none;border-radius:4px;}
.q-table th {font-weight:600;color:var(--muted);}
.q-table td,.q-table th {border-color:var(--border);}
.inventory-grid {height:410px;width:100%;min-width:0;border:1px solid var(--border);}
.ag-theme-balham,.ag-theme-balham-dark {--ag-font-family:'Public Sans',sans-serif;
 --ag-font-size:13px;--ag-background-color:var(--surface);--ag-foreground-color:var(--ink);
 --ag-header-background-color:var(--surface);--ag-header-foreground-color:var(--muted);
 --ag-border-color:var(--border);--ag-row-border-color:var(--border);
 --ag-odd-row-background-color:var(--surface);--ag-row-hover-color:var(--subtle);
 --ag-selected-row-background-color:var(--subtle);--ag-input-focus-border-color:var(--accent);}
.ag-theme-balham-dark .ag-root-wrapper,.ag-theme-balham-dark .ag-header,
.ag-theme-balham-dark .ag-row {background:var(--surface);color:var(--ink);}
.ag-theme-balham-dark .ag-row-selected {background:var(--subtle);}
.services-section {width:100%;border-top:1px solid var(--border);margin-top:28px;padding-top:22px;}
.services-grid {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;width:100%;}
.proxy-grid {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;width:100%;}
.media-grid {display:grid;grid-template-columns:minmax(230px,300px) minmax(0,1fr);gap:24px;width:100%;}
.validation-errors {border-left:3px solid #fa5762;padding:10px 14px;width:100%;background:var(--surface);}
.login-layout {min-height:calc(100vh - 58px);display:flex;justify-content:center;align-items:center;padding:24px;width:100%;}
.login-form {width:360px;max-width:100%;background:var(--surface);padding:30px;border:1px solid var(--border);border-radius:4px;}
.login-title {font-size:22px;font-weight:600;margin:12px 0 20px;}
.dialog-surface {background:var(--surface);color:var(--ink);border-radius:4px;}
@media(max-width:800px) {.services-grid {grid-template-columns:repeat(2,minmax(0,1fr));}.media-grid {grid-template-columns:1fr;}}
@media(max-width:560px) {.work-area {padding:18px 14px;}.services-grid,.proxy-grid {grid-template-columns:1fr;}
 .account-name,.brand-divider {display:none;}.brand {font-size:17px;}.metrics {gap:22px;}
 .toolbar {align-items:flex-start;}.inventory-grid {height:400px;}.topbar-inner {gap:6px;}}
"""


def password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600000).hex()
    return f"pbkdf2_sha256$600000${salt}${digest}"


def password_matches(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def write_private_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def change_password(username: str, current: str, new: str, confirmation: str) -> None:
    if len(new) < 12:
        raise ValueError("The new password must contain at least 12 characters")
    if new != confirmation:
        raise ValueError("New passwords do not match")
    with AUTH_LOCK:
        users = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
        if not password_matches(current, users.get(username, "")):
            raise ValueError("Current password is incorrect")
        if password_matches(new, users[username]):
            raise ValueError("Choose a different password")
        users[username] = password_hash(new)
        write_private_file(AUTH_FILE, json.dumps(users))


def password_dialog():
    with ui.dialog() as dialog, ui.card().classes("dialog-surface").style("width:400px;max-width:94vw"):
        ui.label("Change password").classes("section-title")
        current = ui.input("Current password", password=True, password_toggle_button=True).props("outlined autocomplete=current-password").classes("w-full")
        new = ui.input("New password", password=True, password_toggle_button=True).props("outlined autocomplete=new-password").classes("w-full")
        confirmation = ui.input("Confirm new password", password=True).props("outlined autocomplete=new-password").classes("w-full")

        async def save():
            try:
                await run.io_bound(change_password, app.storage.user["username"], current.value or "", new.value or "", confirmation.value or "")
                current.set_value("")
                new.set_value("")
                confirmation.set_value("")
                dialog.close()
                ui.notify("Password changed", type="positive")
            except (OSError, ValueError) as error:
                ui.notify(str(error), type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Save password", icon="lock", on_click=save)
    dialog.open()


def updates_dialog():
    with ui.dialog() as dialog, ui.card().classes("dialog-surface").style("width:min(900px,94vw);max-width:900px"):
        ui.label("Software updates").classes("section-title")
        ui.label(f"Installed release: {installed_version()}").classes("muted")
        status = ui.label("Check GitHub for the latest published release.").classes("muted")
        result = ui.column().classes("w-full gap-3")

        async def check_updates():
            check_button.disable()
            status.text = "Checking GitHub Releases..."
            result.clear()
            try:
                release = await run.io_bound(latest_release)
                if not app.storage.user.get("authenticated", False):
                    return
                current = installed_version()
                if current == release["tag"]:
                    status.text = f"{release['tag']} is the latest published release."
                else:
                    status.text = f"Latest release: {release['tag']} (installed: {current})"
                with result:
                    ui.link("View release notes on GitHub", release["url"], new_tab=True)
                    ui.label(release["notes"][:12000]).classes("w-full").style("white-space:pre-wrap")
                    if current != release["tag"]:
                        if updater_available():
                            ui.label("Installing stops the automation UI for a few minutes, backs up the UI state "
                                     "and playbooks, checks out the release, reruns setup, and restarts the service. "
                                     "Finish all running automation and uploads first.").classes("muted")
                            ui.button(f"Install {release['tag']} now", icon="system_update_alt",
                                      on_click=lambda tag=release["tag"]: install_update(tag))
                            with ui.expansion("Or install from the server CLI", icon="terminal").classes("w-full"):
                                ui.code(install_instructions(release["tag"]), language="bash").classes("w-full")
                        else:
                            ui.label("This server is not a standard appliance or bare-metal install (no "
                                     "/usr/local/sbin/aipod-update), so update it from the server CLI after finishing "
                                     "all active work.").classes("muted")
                            ui.code(install_instructions(release["tag"]), language="bash").classes("w-full")
            except (ValueError, requests.RequestException) as error:
                status.text = str(error)
            except Exception:
                status.text = "Unable to check GitHub releases; verify server connectivity and try again."
            finally:
                check_button.enable()

        async def install_update(tag: str):
            busy = JobManager.all_running()
            if busy:
                ui.notify("Wait for these jobs to finish first: " + ", ".join(f"{job.page}: {job.label}" for job in busy),
                          type="warning", multi_line=True)
                return
            with ui.dialog() as confirm, ui.card().classes("dialog-surface").style("width:min(560px,94vw)"):
                ui.label(f"Install {tag}").classes("section-title")
                ui.label("The automation UI stops during the update; everyone signed in is disconnected and any "
                         "unsaved edits are lost. Type UPDATE to continue.").classes("text-sm")
                typed = ui.input("Confirmation").props("outlined dense autofocus").classes("w-full")
                with ui.row().classes("w-full justify-end"):
                    ui.button("Cancel", on_click=lambda: confirm.submit(False)).props("flat")
                    ui.button("Install", icon="system_update_alt", color="negative",
                              on_click=lambda: confirm.submit((typed.value or "").strip() == "UPDATE"))
            if not await confirm:
                return
            password = await ask_sudo_password(f"Install {tag}")
            if password is None:
                return
            unit = update_unit(tag)
            try:
                started = await run.io_bound(subprocess.run, update_command(tag, unit), capture_output=True, text=True,
                                            timeout=60, stdin=subprocess.DEVNULL,
                                            env={**os.environ, **sudo_environment(password)})
            except (OSError, subprocess.SubprocessError, ValueError) as error:
                ui.notify(f"Could not start the update: {error}", type="negative", multi_line=True)
                return
            if started.returncode != 0:
                ui.notify("Could not start the update: " + (started.stderr or started.stdout).strip()[-800:],
                          type="negative", multi_line=True)
                return
            status.text = (f"Updating to {tag} (systemd unit {unit}). The UI restarts during the update and this page "
                           "reconnects when it is back; the log stays available under Last update log.")
            result.clear()
            with result:
                progress = ui.log(max_lines=2000).classes("w-full job-log")
            shown = {"size": 0}

            def follow():
                name, text = latest_update_log()
                if name.startswith(unit) and len(text) > shown["size"]:
                    progress.push(text[shown["size"]:].rstrip("\n"))
                    shown["size"] = len(text)

            ui.timer(2.0, follow)

        name, text = latest_update_log()
        if name:
            with ui.expansion(f"Last update log ({name})", icon="history").classes("w-full"):
                ui.code(text[-20000:] or "(empty)", language="text").classes("w-full")

        with ui.row().classes("w-full justify-end"):
            ui.button("Close", on_click=dialog.close).props("flat")
            check_button = ui.button("Check for updates", icon="system_update", on_click=check_updates)
    dialog.open()


# Files the server hands to installers and devices. Browser-executable types (HTML, SVG, JS) are never served.
MEDIA_SUFFIXES = (".iso", ".img", ".bin", ".raw", ".qcow2", ".vmdk", ".ova", ".ovf", ".tar", ".tgz", ".gz", ".xz",
                  ".bz2", ".zst", ".zip", ".rpm", ".deb", ".ign", ".cfg", ".conf", ".txt", ".json", ".yaml", ".yml",
                  ".pem", ".crt", ".cer", ".md5", ".sha256", ".sha512", ".sig")


def media_path(name: str) -> Path:
    if not name or name.startswith(".") or Path(name).name != name or "\\" in name:
        raise ValueError("Invalid file name")
    path = MEDIA_DIR / name
    if path.is_symlink():
        raise ValueError("Symbolic links cannot be managed")
    return path


def media_url() -> str:
    """Base URL that servers use to download images from this appliance."""
    if os.environ.get("AI_PODS_MEDIA_URL"):
        return os.environ["AI_PODS_MEDIA_URL"].rstrip("/")
    interfaces = host_interfaces()
    bootstrap = [item for item in interfaces
                 if ipaddress.ip_address(item["address"]) in ipaddress.ip_network(DEFAULT_BOOTSTRAP_NETWORK)]
    chosen = (bootstrap or interfaces or [None])[0]
    return f"http://{chosen['address']}/os-images" if chosen else ""


def list_media() -> list[dict]:
    rows = []
    for path in sorted(MEDIA_DIR.iterdir(), key=lambda path: path.name.casefold()):
        if path.name.startswith(".") or path.is_symlink() or not path.is_file():
            continue
        info = path.stat()
        rows.append(dict(name=path.name, bytes=info.st_size,
                         size=f"{info.st_size / 1024 ** 3:.2f} GB" if info.st_size >= 1024 ** 3 else f"{info.st_size / 1024 ** 2:.2f} MB",
                         modified=datetime.fromtimestamp(info.st_mtime).strftime("%Y-%m-%d %H:%M"),
                         url=f"/os-images/{quote(path.name)}"))
    return rows


def split_values(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,\n]", value or "") if part.strip()]


def new_inventory_row(rows: list[dict]) -> dict:
    used_ips = {row.get("ip", "") for row in rows}
    address = next((f"198.18.0.{position}" for position in range(1, 255)
                    if f"198.18.0.{position}" not in used_ips), "")
    return dict(id=uuid4().hex, hostname="unknown", ip=address, mac="", pid="", serial_number="")


class ArrayInput:
    def __init__(self, label: str, placeholder: str = "", max_items: int = 100, values: list[str] | None = None):
        self.label = label
        self.placeholder = placeholder
        self.max_items = max_items
        self.fields = []
        with ui.column().classes("w-full gap-2").style("min-width:0"):
            with ui.row().classes("w-full items-center justify-between no-wrap"):
                ui.label(label).classes("text-sm font-medium")
                self.add_button = ui.button(icon="add", on_click=lambda: self.add_value()).props(f'flat round dense aria-label="Add {label} value"')
                self.add_button.tooltip(f"Add {label} value")
            self.container = ui.column().classes("w-full gap-2")
        self.set_values(values or [])

    def set_values(self, values: list[str]):
        self.container.clear()
        self.fields = []
        for value in list(values)[:self.max_items]:
            self.add_value(value)
        if not self.fields:
            self.add_value()

    def add_value(self, value: str = ""):
        if len(self.fields) >= self.max_items:
            return
        with self.container:
            with ui.row().classes("w-full items-center no-wrap gap-2") as row:
                field = ui.input(self.label, value=value if isinstance(value, str) else "", placeholder=self.placeholder).props("outlined dense").classes("flex-1").style("min-width:0")
                ui.button(icon="remove", on_click=lambda: self.remove_value(field, row)).props(f'flat round dense aria-label="Remove {self.label} value"').tooltip(f"Remove {self.label} value")
        self.fields.append(field)
        self.add_button.set_enabled(len(self.fields) < self.max_items)

    def remove_value(self, field, row):
        self.fields.remove(field)
        row.delete()
        if not self.fields:
            self.add_value()
        self.add_button.set_enabled(len(self.fields) < self.max_items)

    @property
    def value(self) -> list[str]:
        return [field.value.strip() for field in self.fields if field.value and field.value.strip()]


def configure_theme():
    ui.colors(primary="#0d8bd4", negative="#d93843", positive="#398519", warning="#bd7202")
    dark = ui.dark_mode(app.storage.user.get("theme", "dark") == "dark")

    def toggle_theme():
        dark.toggle()
        app.storage.user["theme"] = "dark" if dark.value else "light"
        theme_button.props(f"icon={'light_mode' if dark.value else 'dark_mode'}")

    theme_button = ui.button(icon="light_mode" if dark.value else "dark_mode", on_click=toggle_theme).props("flat round")
    theme_button.tooltip("Switch dark / light theme")


@ui.page("/login")
def login_page():
    if app.storage.user.get("authenticated", False):
        ui.navigate.to("/")
        return
    with ui.header().classes("topbar"):
        with ui.row().classes("topbar-inner items-center"):
            ui.icon("hub", size="26px")
            ui.label("Cisco AI PODs").classes("brand")
            ui.space()
            configure_theme()
    with ui.element("main").classes("login-layout"):
        with ui.column().classes("login-form"):
            ui.icon("account_circle", size="38px").style("color:var(--accent)")
            ui.label("Sign in").classes("login-title")
            username = ui.input("Username").props("outlined autocomplete=username").classes("w-full")
            password = ui.input("Password", password=True, password_toggle_button=True).props("outlined autocomplete=current-password").classes("w-full")

            async def login():
                try:
                    users = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
                    valid = await run.io_bound(password_matches, password.value or "", users.get(username.value, ""))
                except (OSError, ValueError):
                    valid = False
                if valid:
                    app.storage.user.update(authenticated=True, username=username.value)
                    ui.navigate.to("/")
                else:
                    ui.notify("Invalid username or password", type="negative")

            password.on("keydown.enter", login)
            ui.button("Sign in", icon="login", on_click=login).classes("w-full mt-3")


def environment_section(active):
    """Environment create / copy and the optional git repository that stores every environment."""
    names = ENVIRONMENTS.names()
    info = describe(ENVIRONMENTS, active)
    with ui.expansion(f"Environment: {active}", icon="layers", value=len(names) <= 1).classes("w-full env-card mb-4"):
        ui.label(f"Inventory, shared services, page files, and the vault for {active} are saved under {info['path']}. "
                 f"{info['devices']} devices, {len(info['files'])} variable files, vault "
                 f"{'present' if info['vault'] else 'not created yet'}. Switch environments from the header.").classes(
            "muted text-xs")
        with ui.row().classes("w-full items-start gap-3 mt-2"):
            name = ui.input("New environment name", placeholder="Production",
                            validation={"Letters, numbers, . _ - only (no spaces)":
                                        lambda value: not value or bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}", value))}
                            ).props("outlined dense").style("width:260px")
            source = ui.select({"": "Start empty", **{item: f"Copy from {item}" for item in names}}, value="",
                               label="Starting point").props("outlined dense").style("width:240px")

            def create():
                try:
                    created = ENVIRONMENTS.create(check_name(name.value), source.value or "")
                except (EnvironmentProblem, OSError) as error:
                    ui.notify(str(error), type="negative")
                    return
                app.storage.user["environment"] = created
                ui.notify(f"Created {created}" + (" (vault secrets are not copied)" if source.value else ""), type="positive")
                ui.navigate.reload()

            ui.button("Create and switch", icon="add", on_click=create).classes("mt-1")
    git_section()


def git_section():
    settings = ENVIRONMENTS.git_settings()
    git_context = replace(ENVIRONMENTS.base, store=None, output_dir=DEPLOYMENTS_DIR, vault=ENVIRONMENTS.git_vault,
                          jobs=ENVIRONMENTS.git_jobs)
    with ui.expansion("Git repository (optional)", icon="cloud_upload").classes("w-full env-card mb-4"):
        with ui.row().classes("w-full items-start gap-2 no-wrap git-warning"):
            ui.icon("lock", size="sm").classes("text-negative")
            ui.markdown("**Use a private repository.** These files describe your infrastructure: addresses, hostnames, "
                        "usernames, and certificates. Create the repository as *Private* and only grant access to the "
                        "people who deploy this environment.").classes("text-sm")
        ui.label(f"Every environment lives in one repository at {DEPLOYMENTS_DIR}, one folder per environment. "
                 "The automation vault (vault.yaml) is encrypted with this server's own password and is never "
                 "committed, nor are vault passwords, private keys, or kubeconfigs (see .gitignore).").classes("muted text-xs")
        with ui.element("div").classes("proxy-grid mt-2"):
            remote = ui.input("Remote URL", value=settings.remote_url,
                              placeholder="https://github.com/<owner>/<repository>.git").props("outlined dense")
            branch = ui.input("Branch", value=settings.branch or "main").props("outlined dense")
            username = ui.input("Username (HTTPS)", value=settings.username,
                                placeholder="GitHub username").props("outlined dense")
            author = ui.input("Commit author name", value=settings.author_name,
                              placeholder=app.storage.user.get("username", "")).props("outlined dense")
            email = ui.input("Commit author email", value=settings.author_email,
                             placeholder="user@example.com").props("outlined dense")
        store_secrets = ui.switch("Store secrets in the repository (encrypted with a repository vault password)",
                                  value=settings.store_secrets).classes("mt-2")
        ui.label("When enabled, Commit re-encrypts each environment's secrets into secrets.vault.yaml with the "
                 "repository vault password below, and Pull merges them back into this server's vault. That password "
                 "only protects the copy in git; the automation keeps using this server's vault password, so a "
                 "teammate or a rebuilt server only needs the repository vault password to restore the secrets."
                 ).classes("muted text-xs")
        visibility = ui.label("").classes("text-sm")
        status = ui.code(ENVIRONMENTS.git_status(), language="text").classes("w-full mt-2")

        async def check_visibility(url):
            result = await run.io_bound(repository_visibility, url) if url else "unknown"
            if result == "public":
                visibility.set_text("WARNING: this GitHub repository is PUBLIC. Anyone can read what you push. "
                                    "Make it private before pushing.")
                visibility.classes(replace="text-sm text-negative text-weight-bold")
                ui.notify("This GitHub repository is PUBLIC. Make it private before pushing.", type="negative",
                          multi_line=True, timeout=0, close_button=True)
            elif result == "private":
                visibility.set_text("Repository is not publicly visible.")
                visibility.classes(replace="text-sm text-positive")
            else:
                visibility.set_text("")

        async def save():
            try:
                await run.io_bound(ENVIRONMENTS.save_git_settings, GitSettings(
                    (remote.value or "").strip(), (branch.value or "").strip(), (username.value or "").strip(),
                    (author.value or "").strip(), (email.value or "").strip(), bool(store_secrets.value)))
            except (EnvironmentProblem, OSError, subprocess.SubprocessError) as error:
                ui.notify(f"Git settings not saved: {error}", type="negative", multi_line=True)
                return
            status.set_content(await run.io_bound(ENVIRONMENTS.git_status))
            ui.notify("Saved the repository settings", type="positive")
            await check_visibility((remote.value or "").strip())

        async def refresh():
            status.set_content(await run.io_bound(ENVIRONMENTS.git_status))

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(icon="refresh", on_click=refresh).props("flat round dense").tooltip("Refresh git status")
            ui.button("Save repository settings", icon="save", on_click=save).props("outline")
        credentials = CredentialsPanel(git_context, lambda: [GIT_TOKEN] + ([REPO_PASSWORD] if store_secrets.value else []),
                                       title="Repository credentials")
        store_secrets.on_value_change(lambda _: credentials.render())
        message = ui.input("Commit message", value="Update deployment environments").props("outlined dense").classes("w-full")
        user = app.storage.user.get("username", "")
        environment = {"env": lambda run_context: ENVIRONMENTS.git_environment(GIT_ASKPASS)}
        JobConsole(git_context, "git", (
            Action("commit", "Commit", "commit", lambda rc: ENVIRONMENTS.git_commands("commit", rc.state["message"], user,
                                                                                       sys.executable),
                   group="Tools", files=False, tooltip="Stage and commit every environment"),
            Action("pull", "Pull", "cloud_download", lambda rc: ENVIRONMENTS.git_commands("pull", python=sys.executable),
                   group="Tools",
                   files=False, confirm="Fast-forward the local environments from the remote branch?", **environment),
            Action("push", "Push", "cloud_upload", lambda rc: ENVIRONMENTS.git_commands("push"), group="Deploy",
                   files=False, tooltip="Push commits to the remote branch", **environment),
        ), state=lambda: {"message": message.value or ""}, credentials=credentials)


@ui.page("/")
def workspace_page():
    if not app.storage.user.get("authenticated", False):
        ui.navigate.to("/login")
        return
    add_head()
    environment = read_active(app.storage.user, ENVIRONMENTS)
    app.storage.user["environment"] = environment
    context = replace(ENVIRONMENTS.context(environment), media_url=media_url())
    STORE, VAULT = context.store, context.vault
    state = {"rows": [dict(row, id=uuid4().hex, role=seeds.row_role(row)) for row in STORE.inventory()], "files": set()}
    settings_now = STORE.shared_services()
    detected_now, rejected_defaults = STORE.detected()
    section_of = {page.key: section.key for section in pages.SECTIONS for page in section.pages}
    sections = {section.key: section for section in pages.SECTIONS}
    nav_buttons = {}
    last_page = {}
    shared_inputs = {}
    proxy_inputs = {}
    ldap_inputs = {}

    def logout():
        app.storage.user.update(authenticated=False, username="")
        ui.navigate.to("/login")

    def switch_environment(name):
        if name and name != environment and ENVIRONMENTS.exists(name):
            app.storage.user["environment"] = name
            ui.navigate.reload()

    start_page = app.storage.user.get("page", "inventory")
    if start_page not in pages.PAGES:
        start_page = "inventory"
    with ui.left_drawer(value=True).props("width=290 breakpoint=1000 show-if-above") as drawer:
        ui.label("Deployment workflow").classes("nav-heading")
        for section in pages.SECTIONS:
            with ui.expansion(section.title, icon=section.icon, value=section.key == section_of[start_page]).classes("w-full nav-section"):
                group = ""
                for spec in section.pages:
                    if spec.group != group:
                        group = spec.group
                        if group:
                            ui.label(group).classes("nav-group")
                    nav_buttons[spec.key] = ui.button(spec.title, on_click=lambda key=spec.key: show_page(key)).props(
                        "flat align=left no-caps").classes("nav-page" + (" nav-grouped" if spec.group else ""))
        ui.space()
        ui.label("Cisco AI PODs").classes("muted text-xs p-3")
    with ui.header().classes("topbar"):
        with ui.row().classes("topbar-inner items-center"):
            ui.button(icon="menu", on_click=drawer.toggle).props("flat round").tooltip("Navigation")
            ui.icon("hub", size="25px")
            ui.label("Cisco AI PODs").classes("brand")
            ui.element("div").classes("brand-divider")
            ui.label("Deployment workspace").classes("account-name")
            ui.space()
            ui.select(ENVIRONMENTS.names() or [environment], value=environment,
                      on_change=lambda event: switch_environment(event.value)).props(
                "dense dark standout options-dense").classes("environment-select").tooltip(
                "Active environment: every page reads and saves this environment's files and vault")
            ui.label(app.storage.user["username"]).classes("account-name")
            configure_theme()
            ui.button(icon="system_update", on_click=updates_dialog).props("flat round").tooltip("Check for software updates")
            ui.button(icon="manage_accounts", on_click=password_dialog).props("flat round").tooltip("Change password")
            ui.button(icon="logout", on_click=logout).props("flat round").tooltip("Sign out")

    async def current_rows():
        await grid.run_grid_method("stopEditing")
        state["rows"] = await grid.get_client_data(timeout=5)
        return state["rows"]

    def update_counts():
        node_count.set_text(str(len(state["rows"])))
        workbook_count.set_text(str(len(state["files"])))

    def update_grid():
        grid.options["rowData"] = state["rows"]
        grid.update()
        update_counts()

    async def add_row():
        await current_rows()
        state["rows"].append(new_inventory_row(state["rows"]))
        search.set_value("")
        update_grid()
        errors.clear()
        await grid.run_grid_method("ensureIndexVisible", len(state["rows"]) - 1)

    async def import_workbooks(event):
        try:
            await current_rows()
            with tempfile.TemporaryDirectory(prefix="ai-pods-workbooks-") as folder:
                files = []
                names = set()
                for uploaded in event.files:
                    name = uploaded.name
                    if Path(name).name != name or "\\" in name or not name.lower().endswith(".xlsx"):
                        raise ValueError("Only .xlsx workbooks are accepted")
                    if name in state["files"] or name in names:
                        raise ValueError(f"Already imported: {name}")
                    path = Path(folder) / name
                    await uploaded.save(path)
                    files.append(path)
                    names.add(name)
                imported = await run.io_bound(read_inventory_files, files)
            known_macs = {normalize_mac(row["mac"]) for row in state["rows"] if row["mac"].strip()}
            used_ips = {row["ip"] for row in state["rows"]}
            available_ips = iter(f"198.18.0.{position}" for position in range(1, 255)
                                 if f"198.18.0.{position}" not in used_ips)
            new_rows = []
            for row in imported:
                if row["mac"] in known_macs:
                    continue
                row["ip"] = next(available_ips, None)
                if row["ip"] is None:
                    raise ValueError("The default 198.18.0.X pool is exhausted")
                row["id"] = uuid4().hex
                known_macs.add(row["mac"])
                new_rows.append(row)
            state["rows"].extend(new_rows)
            state["files"].update(names)
            update_grid()
            errors.clear()
            ui.notify(f"Imported {len(new_rows)} nodes from {len(names)} workbooks", type="positive")
            workbook_upload.reset()
        except Exception as error:
            ui.notify(f"Import failed: {error}", type="negative")

    async def remove_rows():
        await current_rows()
        selected = await grid.get_selected_rows()
        if not selected:
            ui.notify("No rows selected", type="warning")
            return
        ids = {row["id"] for row in selected}
        state["rows"] = [row for row in state["rows"] if row["id"] not in ids]
        update_grid()
        errors.clear()

    def shared_services():
        settings = {}
        for name, field in shared_inputs.items():
            value = field.value
            if isinstance(value, list):
                if value:
                    settings[name] = value
            elif value and value.strip():
                settings[name] = value.strip()
        proxy = {}
        for name in ("http_proxy", "https_proxy", "username"):
            value = proxy_inputs[name].value
            if value and value.strip():
                proxy[name] = value.strip()
        bypass = proxy_inputs["no_proxy"].value
        if bypass:
            proxy["no_proxy"] = bypass
        reference = proxy_inputs["reference"].value
        if reference is not None:
            if int(reference) != reference:
                raise ValueError("Proxy password reference must be an integer")
            proxy["password"] = int(reference)
        if proxy_inputs["password"].value:
            proxy.setdefault("password", 1)
        if proxy:
            settings["proxy_servers"] = proxy
        ldap = {name: ldap_inputs[name].value.strip() for name in LDAP_FIELDS if (ldap_inputs[name].value or "").strip()}
        if ldap:
            ldap["secure_ldap"] = bool(ldap_inputs["secure_ldap"].value)
            settings["ldap"] = ldap
        return settings

    async def validate_form():
        errors.clear()
        try:
            rows = await current_rows()
            settings = shared_services()
            problems = validate_shared_services(settings, SCHEMA_PATH)
            if problems:
                raise ValueError("\n".join(problems))
            return await run.io_bound(build_inventory_document, rows, settings, SCHEMA_PATH)
        except Exception as error:
            with errors:
                with ui.column().classes("validation-errors"):
                    for message in str(error).splitlines():
                        ui.label(message)
            ui.notify("Validation failed", type="negative")
            return None

    async def validate_click():
        if await validate_form():
            ui.notify("Inventory and shared services are valid", type="positive")

    def persist(document, proxy_password="", ldap_password=""):
        reference = (document["shared_services"].get("proxy_servers") or {}).get("password")
        updates = {}
        if proxy_password and reference:
            updates[("openshift", f"proxy_password_{reference}")] = proxy_password
        if ldap_password:
            updates[("openshift", "ldap_bind_password")] = ldap_password
        if updates:
            VAULT.update(updates)
        STORE.save_inventory(document["initial_inventory"])
        return STORE.save_shared_services(document["shared_services"])

    async def save_click():
        document = await validate_form()
        if document is None:
            return
        try:
            overrides = await run.io_bound(persist, document, proxy_inputs["password"].value or "",
                                           ldap_inputs["password"].value or "")
            for field in (proxy_inputs["password"], ldap_inputs["password"]):
                if field.value:
                    field.set_value("")
            ldap_status.refresh()
            ui.notify(f"Saved {len(document['initial_inventory'])} devices and {len(overrides)} shared-service overrides. "
                      "The DHCP, Nexus Dashboard, Compute, and OpenShift pages pre-fill from them.", type="positive",
                      multi_line=True)
        except VaultError as error:
            ui.notify(f"Password not stored in the vault: {error}", type="negative", multi_line=True)
        except Exception as error:
            ui.notify(f"Save failed: {error}", type="negative")

    def fill_shared_services(settings):
        for name in ("dns_servers", "dns_search_domains", "ntp_servers"):
            shared_inputs[name].set_values(settings.get(name, []))
        shared_inputs["domain_name"].set_value(settings.get("domain_name", ""))
        shared_inputs["timezone"].set_value(settings.get("timezone"))
        proxy = settings.get("proxy_servers", {})
        for name in ("http_proxy", "https_proxy", "username"):
            proxy_inputs[name].set_value(proxy.get(name, ""))
        proxy_inputs["no_proxy"].set_values(proxy.get("no_proxy", []))
        proxy_inputs["reference"].set_value(proxy.get("password"))
        ldap = settings.get("ldap", {})
        for name in LDAP_FIELDS:
            ldap_inputs[name].set_value(ldap.get(name, ""))
        ldap_inputs["secure_ldap"].set_value(ldap.get("secure_ldap", True))

    def reset_defaults():
        STORE.reset_shared_services()
        fill_shared_services(STORE.shared_services())
        ui.notify("Shared services reset to the values detected on this server", type="info")

    def suggest_no_proxy():
        domain = (shared_inputs["domain_name"].value or "").strip()
        wanted = list(RECOMMENDED_NO_PROXY) + ([f".{domain}"] if domain else [])
        current = proxy_inputs["no_proxy"].value
        proxy_inputs["no_proxy"].set_values(current + [entry for entry in wanted if entry not in current])
        ui.notify("Added recommended bypass entries. The OpenShift page adds apps.<cluster>.<domain> and "
                  ".<cluster>.<domain> once the cluster name is known.", type="info", multi_line=True)

    def refresh_media():
        try:
            media_table.rows = list_media()
            media_table.selected = []
            media_table.update()
            media_count.set_text(str(len(media_table.rows)))
        except OSError as error:
            ui.notify(f"Cannot list media: {error}", type="negative")

    async def save_iso(event):
        temporary = None
        try:
            target = media_path(event.file.name)
            if not target.name.lower().endswith(MEDIA_SUFFIXES):
                raise ValueError("Unsupported file type. Allowed: " + " ".join(MEDIA_SUFFIXES))
            async with MEDIA_LOCK:
                if target.exists():
                    raise ValueError("A file with this name already exists")
                temporary = MEDIA_DIR / f".upload-{uuid4().hex}.part"
                await event.file.save(temporary)
                temporary.replace(target)
            refresh_media()
            iso_upload.reset()
            ui.notify(f"Saved {target.name}", type="positive")
        except Exception as error:
            ui.notify(f"Upload failed: {error}", type="negative")
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    def confirm_delete():
        names = [row["name"] for row in media_table.selected]
        if not names:
            ui.notify("No files selected", type="warning")
            return

        async def delete_files():
            try:
                async with MEDIA_LOCK:
                    paths = [media_path(name) for name in names]
                    if any(not path.is_file() for path in paths):
                        raise ValueError("One or more selected files no longer exist")
                    for path in paths:
                        await run.io_bound(path.unlink)
                refresh_media()
                dialog.close()
                ui.notify(f"Deleted {len(names)} files", type="positive")
            except Exception as error:
                ui.notify(f"Delete failed: {error}", type="negative")

        with ui.dialog() as dialog, ui.card().classes("dialog-surface"):
            ui.label(f"Delete {len(names)} files?").classes("section-title")
            with ui.column().style("max-height:40vh;overflow:auto;max-width:80vw"):
                for name in names:
                    ui.label(name).classes("break-all")
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button("Delete", icon="delete", color="negative", on_click=delete_files)
        dialog.open()

    with ui.element("main").classes("work-area"):
        with ui.row().classes("w-full items-end justify-between gap-3"):
            with ui.column().classes("gap-0"):
                section_label = ui.label().classes("muted text-sm")
                with ui.row().classes("items-center gap-3 no-wrap"):
                    page_title = ui.label().classes("page-title")
                    with ui.element("div").classes("env-banner").tooltip(
                            "Every page reads and saves this environment's files and vault. Change it in the top bar or "
                            "on Environment Preparation > Initial Inventory."):
                        ui.icon("layers", size="18px")
                        ui.label("Environment:")
                        ui.label(environment).classes("env-banner-name")
            page_select = ui.select({}, label="Page").props("outlined dense options-dense").classes("page-select")
        with ui.tabs().props("align=left outside-arrows mobile-arrows").classes("workspace-tabs w-full") as section_tabs:
            for section in pages.SECTIONS:
                ui.tab(section.key, label=section.title, icon=section.icon)
        with ui.tab_panels(value=start_page, animated=False).classes("w-full") as panels:
            with ui.tab_panel("inventory"):
                environment_section(environment)
                with ui.expansion("Initial inventory", icon="inventory_2", value=True).classes("w-full env-card mb-4"):
                    with ui.column().classes("w-full gap-0 p-4"):
                        with ui.element("div").classes("metrics"):
                            with ui.column().classes("gap-0"):
                                node_count = ui.label("0").classes("metric-value")
                                ui.label("Inventory nodes").classes("metric-label")
                            with ui.column().classes("gap-0"):
                                workbook_count = ui.label("0").classes("metric-value")
                                ui.label("Spreadsheets").classes("metric-label")
                        workbook_upload = ui.upload(label="Order spreadsheets", multiple=True, auto_upload=True,
                                                    max_files=25, max_file_size=25 * 1024 ** 2,
                                                    on_multi_upload=import_workbooks).props("accept=.xlsx").classes("w-full mb-5")
                        with ui.row().classes("toolbar justify-end"):
                            with ui.row().classes("items-center"):
                                search = ui.input(placeholder="Search inventory").props("dense outlined clearable").style("width:210px;max-width:100%")
                                ui.button("Add node", icon="add", on_click=add_row).props("outline")
                                ui.button(icon="delete", color="negative", on_click=remove_rows).props("outline round dense").tooltip("Delete selected rows")
                        grid = ui.aggrid({
                            "defaultColDef": {"editable": True, "resizable": True, "sortable": True, "filter": True, "minWidth": 145},
                            "columnDefs": [dict(headerName="Hostname", field="hostname", width=220),
                                           dict(headerName="IP address", field="ip", width=165),
                                           dict(headerName="MAC address", field="mac", width=185),
                                           dict(headerName="Product ID", field="pid", width=170),
                                           dict(headerName="Serial number", field="serial_number", width=170),
                                           dict(headerName="Role", field="role", width=230, cellEditor="agSelectCellEditor",
                                                cellEditorParams={"values": list(seeds.ROLES)},
                                                **{":valueFormatter": "p => (" + json.dumps(seeds.ROLES) + ")[p.value] || p.value"})],
                            "rowData": state["rows"], "rowSelection": {"mode": "multiRow", "enableClickSelection": False},
                            "selectionColumnDef": {"width": 44, "pinned": "left"}, "rowHeight": 36, "headerHeight": 38,
                            "stopEditingWhenCellsLoseFocus": True, "singleClickEdit": True,
                            ":getRowId": "params => params.data.id",
                        }, theme="balham").classes("inventory-grid")
                        search.on_value_change(lambda event: grid.run_grid_method("setGridOption", "quickFilterText", event.value or ""))

                        def cell_changed(event):
                            data = event.args.get("data", {})
                            if not str(data.get("mac", "")).strip():
                                return
                            try:
                                normalized = normalize_mac(data["mac"])
                                if normalized != data["mac"]:
                                    data["mac"] = normalized
                                    grid.run_grid_method("applyTransaction", {"update": [data]})
                            except (KeyError, ValueError):
                                ui.notify("Invalid MAC address", type="negative")

                        grid.on("cellValueChanged", cell_changed, args=["data"])
                with ui.expansion("Shared services", icon="dns", value=True).classes("w-full env-card mb-4"):
                    with ui.column().classes("w-full gap-0 p-4"):
                        with ui.row().classes("toolbar"):
                            with ui.column().classes("gap-0"):
                                ui.label("Defaults are detected from this server. Only the values you change are saved, and "
                                         "every workflow page reuses them.").classes("muted text-xs")
                            ui.button("Reset to server defaults", icon="restart_alt", on_click=reset_defaults).props("flat")
                        if rejected_defaults:
                            ui.label("Detected values rejected by the schema: " + "; ".join(rejected_defaults)).classes("muted text-xs")
                        with ui.element("div").classes("services-grid"):
                            schema = json.loads((SCHEMA_PATH.parent / "shared.json").read_text())
                            for name, label, placeholder in (
                                ("dns_servers", "DNS servers", "192.0.2.53"),
                                ("dns_search_domains", "DNS search domains", "example.com"),
                                ("ntp_servers", "NTP servers", "0.pool.ntp.org"),
                            ):
                                shared_inputs[name] = ArrayInput(label, placeholder, schema["definitions"][name]["maxItems"],
                                                                 settings_now.get(name, []))
                            shared_inputs["domain_name"] = ui.input("Domain name", value=settings_now.get("domain_name", ""), placeholder="example.com").props("outlined dense").classes("w-full")
                            zones = schema["definitions"]["timezone"]["enum"]
                            shared_inputs["timezone"] = ui.select(zones, value=settings_now.get("timezone", "UTC") if settings_now.get("timezone", "UTC") in zones else "UTC", label="Timezone", with_input=True, clearable=True).props("outlined dense").classes("w-full")
                        proxy_now = settings_now.get("proxy_servers", {})
                        with ui.expansion("Proxy settings", icon="settings_ethernet", value=bool(proxy_now)).classes("w-full mt-4"):
                            with ui.element("div").classes("proxy-grid"):
                                for name, label in (("http_proxy", "HTTP proxy"), ("https_proxy", "HTTPS proxy"), ("username", "Proxy username")):
                                    proxy_inputs[name] = ui.input(label, value=proxy_now.get(name, "")).props("outlined dense").classes("w-full")
                                proxy_inputs["password"] = ui.input("Proxy password", password=True, password_toggle_button=True).props("outlined dense autocomplete=new-password").classes("w-full")
                                proxy_inputs["reference"] = ui.number("Password reference", min=1, max=64, precision=0, value=proxy_now.get("password")).props("outlined dense").classes("w-full")
                                proxy_schema = schema["definitions"]["proxy_servers"]["allOf"][0]["properties"]
                                proxy_inputs["no_proxy"] = ArrayInput("Proxy bypass list", "localhost", proxy_schema["no_proxy"]["maxItems"],
                                                                      proxy_now.get("no_proxy", []))
                            with ui.row().classes("w-full items-center gap-2 mt-2"):
                                ui.button("Add recommended bypass entries", icon="playlist_add", on_click=suggest_no_proxy).props("outline dense")
                                ui.label("When a proxy is set, bypass the cluster, service, bootstrap, and site domains.").classes("muted text-xs")
                        ldap_now = settings_now.get("ldap", {})
                        with ui.expansion("LDAP / Active Directory", icon="groups", value=bool(ldap_now)).classes("w-full mt-2"):
                            ui.label("Used by OpenShift - LDAP (identity provider and group sync). The bind password is "
                                     "stored in Ansible Vault, not with the shared services.").classes("muted text-xs")
                            with ui.element("div").classes("proxy-grid"):
                                for name, label, placeholder in LDAP_INPUTS:
                                    ldap_inputs[name] = ui.input(label, value=ldap_now.get(name, ""), placeholder=placeholder).props("outlined dense").classes("w-full")
                                ldap_inputs["password"] = ui.input("Bind password", password=True, password_toggle_button=True).props("outlined dense autocomplete=new-password").classes("w-full")
                                ldap_inputs["secure_ldap"] = ui.switch("Secure LDAP (LDAPS)", value=ldap_now.get("secure_ldap", True))

                            @ui.refreshable
                            def ldap_status():
                                try:
                                    stored = VAULT.is_set(VAULT.load(), "openshift", "ldap_bind_password")
                                except VaultError:
                                    stored = False
                                ui.label("Bind password stored in Ansible Vault - leave blank to keep it." if stored else
                                         "Bind password not stored yet.").classes("muted text-xs")

                            ldap_status()
                errors = ui.column().classes("w-full mt-4")
                with ui.row().classes("w-full justify-end mt-4"):
                    ui.button("Validate", icon="fact_check", on_click=validate_click).props("outline")
                    ui.button("Save", icon="save", on_click=save_click)
            with ui.tab_panel("dhcp"):
                pages.dhcp_page(context)
            with ui.tab_panel("iso"):
                with ui.row().classes("toolbar"):
                    with ui.row().classes("items-center"):
                        ui.label("File server").classes("section-title")
                        media_count = ui.label("0").classes("muted")
                    with ui.row():
                        ui.button(icon="refresh", on_click=refresh_media).props("flat round dense").tooltip("Refresh files")
                        ui.button(icon="delete", color="negative", on_click=confirm_delete).props("outline round dense").tooltip("Delete selected files")
                with ui.element("div").classes("media-grid"):
                    with ui.column().classes("w-full gap-2"):
                        iso_upload = ui.upload(label="Upload Files", auto_upload=True, max_files=1,
                                               max_file_size=15000 * 1024 ** 2, on_upload=save_iso).props(
                            "accept=" + ",".join(MEDIA_SUFFIXES)).classes("w-full")
                        ui.label("Served over HTTP to installers and devices (ISO images, firmware, ignition and "
                                 "config files).").classes("muted text-xs")
                    with ui.column().classes("w-full gap-3").style("min-width:0"):
                        media_search = ui.input(placeholder="Search files").props("outlined dense clearable").classes("w-full")
                        media_table = ui.table(rows=[], columns=[
                            dict(name="name", label="File name", field="name", align="left", sortable=True),
                            dict(name="size", label="Size", field="bytes", align="right", sortable=True),
                            dict(name="modified", label="Modified", field="modified", align="left", sortable=True),
                        ], row_key="name", selection="multiple", pagination=10).classes("w-full")
                        media_table.add_slot("body-cell-name", '<q-td :props="props"><a :href="props.row.url" target="_blank" rel="noopener" style="color:var(--accent)">{{ props.row.name }}</a></q-td>')
                        media_table.add_slot("body-cell-size", '<q-td :props="props">{{ props.row.size }}</q-td>')
                        media_search.bind_value(media_table, "filter")
            for spec in pages.PAGES.values():
                if spec.key in ("inventory", "dhcp", "iso"):
                    continue
                with ui.tab_panel(spec.key):
                    pages.stage_page(context, spec)

    switching = {"active": False}

    def show_page(key):
        if switching["active"] or key not in pages.PAGES:
            return
        switching["active"] = True
        try:
            spec, section = pages.PAGES[key], sections[section_of[key]]
            last_page[section.key] = key
            app.storage.user["page"] = key
            section_tabs.set_value(section.key)
            options = {page.key: page.full_title for page in section.pages}
            if page_select.options != options:
                page_select.set_options(options, value=key)
            else:
                page_select.set_value(key)
            page_select.set_visibility(len(options) > 1)
            section_label.set_text(section.title)
            page_title.set_text(spec.full_title)
            panels.set_value(key)
            for name, button in nav_buttons.items():
                if name == key:
                    button.classes(add="nav-active")
                else:
                    button.classes(remove="nav-active")
            if key == "iso":
                refresh_media()
        finally:
            switching["active"] = False

    section_tabs.on_value_change(lambda event: show_page(last_page.get(event.value) or sections[event.value].pages[0].key))
    page_select.on_value_change(lambda event: show_page(event.value))
    update_counts()
    show_page(start_page)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create-user", help="Create or update an account with a prompted password")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    arguments = parser.parse_args()
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if arguments.create_user:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", arguments.create_user):
            parser.error("Username must contain only letters, numbers, underscores or hyphens")
        password = getpass.getpass("Password: ")
        if len(password) < 12 or password != getpass.getpass("Confirm password: "):
            parser.error("Passwords must match and contain at least 12 characters")
        with AUTH_LOCK:
            users = json.loads(AUTH_FILE.read_text()) if AUTH_FILE.exists() else {}
            users[arguments.create_user] = password_hash(password)
            write_private_file(AUTH_FILE, json.dumps(users))
        print(f"Updated account: {arguments.create_user}")
        return
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    secret_file = APP_DIR / ".storage-secret"
    if not secret_file.exists():
        write_private_file(secret_file, secrets.token_urlsafe(48))
    migrated = ENVIRONMENTS.migrate_legacy(LEGACY_WORKSPACE_DIR, LEGACY_OUTPUT_DIR, LEGACY_VAULT_FILE)
    if migrated:
        print(f"Created environment {migrated} in {DEPLOYMENTS_DIR / 'environments'}")
    register_static(BUNDLED_SCHEMA)
    ui.add_css(CSS, shared=True)
    ui.run(host=arguments.host, port=arguments.port, storage_secret=secret_file.read_text().strip(),
           title="Cisco AI PODs", show=False, reload=False)


if __name__ == "__main__":
    main()