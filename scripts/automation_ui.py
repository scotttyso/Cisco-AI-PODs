#!/usr/bin/env python3
"""Authenticated inventory and installation-media workspace for Cisco AI PODs."""

import argparse
import asyncio
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import yaml
from nicegui import app, run, ui

from build_initial_inventory import (
    DEFAULT_SCHEMA, IndentedDumper, build_inventory_document, normalize_mac,
    read_inventory_files, validate_shared_services, write_inventory,
)


APP_DIR = Path(os.environ.get("AI_PODS_APP_DIR", Path(__file__).resolve().parent))
MEDIA_DIR = Path(os.environ.get("AI_PODS_MEDIA_DIR", "/var/www/html/os-images"))
OUTPUT_DIR = Path(os.environ.get("AI_PODS_OUTPUT_DIR", "/home/automation-ui/playbooks/vars"))
SCHEMA_PATH = Path(os.environ.get("AI_PODS_SCHEMA", DEFAULT_SCHEMA))
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
.topbar {background:linear-gradient(100deg,#283f66,#0d274d 60%,#091b33);color:#fff;height:58px;}
.topbar-inner {width:100%;height:58px;gap:12px;flex-wrap:nowrap;}
.brand {font-size:19px;font-weight:600;white-space:nowrap;}
.brand-divider {width:1px;height:24px;background:#ffffff35;margin:0 12px;}
.account-name {font-size:13px;color:#d0d4d9;}
.q-drawer {background:var(--sidebar);border-right:1px solid var(--border);}
.nav-heading {font-size:11px;color:var(--muted);font-weight:600;text-transform:uppercase;padding:24px 12px 12px;}
.nav-button {width:100%;min-height:40px;color:var(--ink);border-radius:4px;}
.nav-button:hover {background:var(--subtle);}
.work-area {width:100%;max-width:1680px;margin:0 auto;padding:24px 30px;min-width:0;}
.page-title {font-size:23px;font-weight:600;line-height:1.3;}
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


def media_path(name: str) -> Path:
    if not name or name.startswith(".") or Path(name).name != name or "\\" in name:
        raise ValueError("Invalid file name")
    path = MEDIA_DIR / name
    if path.is_symlink():
        raise ValueError("Symbolic links cannot be managed")
    return path


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
    def __init__(self, label: str, placeholder: str = "", max_items: int = 100):
        self.label = label
        self.placeholder = placeholder
        self.max_items = max_items
        self.fields = []
        with ui.column().classes("w-full gap-2").style("min-width:0"):
            with ui.row().classes("w-full items-center justify-between no-wrap"):
                ui.label(label).classes("text-sm font-medium")
                self.add_button = ui.button(icon="add", on_click=self.add_value).props(f'flat round dense aria-label="Add {label} value"')
                self.add_button.tooltip(f"Add {label} value")
            self.container = ui.column().classes("w-full gap-2")
        self.add_value()

    def add_value(self):
        if len(self.fields) >= self.max_items:
            return
        with self.container:
            with ui.row().classes("w-full items-center no-wrap gap-2") as row:
                field = ui.input(self.label, placeholder=self.placeholder).props("outlined dense").classes("flex-1").style("min-width:0")
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


@ui.page("/")
def workspace_page():
    if not app.storage.user.get("authenticated", False):
        ui.navigate.to("/login")
        return
    client = ui.context.client
    state = {"rows": [], "files": set()}
    shared_inputs = {}
    proxy_inputs = {}
    export_path = OUTPUT_DIR / app.storage.user["username"] / client.id / "initial_inventory.ezai.yaml"

    def logout():
        app.storage.user.update(authenticated=False, username="")
        ui.navigate.to("/login")

    with ui.left_drawer(value=True).props("width=208 breakpoint=1000 show-if-above") as drawer:
        ui.label("Operate").classes("nav-heading")
        ui.button("Inventory", icon="dns", on_click=lambda: tabs.set_value("Inventory")).props("flat align=left").classes("nav-button")
        ui.button("ISO library", icon="storage", on_click=lambda: tabs.set_value("ISO library")).props("flat align=left").classes("nav-button")
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
            ui.label(app.storage.user["username"]).classes("account-name")
            configure_theme()
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

    async def generate():
        document = await validate_form()
        if document is None:
            return
        try:
            await run.io_bound(write_inventory, document["initial_inventory"], document["shared_services"], export_path, SCHEMA_PATH)
            content = yaml.dump(document, Dumper=IndentedDumper, sort_keys=False, explicit_start=True)
            secret_content = None
            secret_path = export_path.with_name("initial_inventory.secrets.yaml")
            if proxy_inputs["password"].value:
                reference = document["shared_services"]["proxy_servers"]["password"]
                secret_content = yaml.safe_dump({f"proxy_password_{reference}": proxy_inputs["password"].value})
                await run.io_bound(write_private_file, secret_path, secret_content)
            else:
                secret_path.unlink(missing_ok=True)
            with ui.dialog() as dialog, ui.card().classes("dialog-surface w-full").style("max-width:900px"):
                ui.label("Inventory generated").classes("section-title")
                ui.label(str(export_path)).classes("muted text-xs break-all")
                ui.code(content, language="yaml").classes("w-full").style("max-height:55vh;overflow:auto")
                with ui.row().classes("w-full justify-end"):
                    ui.button("Download YAML", icon="download", on_click=lambda: ui.download.content(content, export_path.name))
                    if secret_content:
                        ui.button("Download secrets", icon="key", on_click=lambda: ui.download.content(secret_content, "initial_inventory.secrets.yaml")).props("outline").tooltip("Contains the proxy password")
                    ui.button("Close", on_click=dialog.close).props("flat")
            dialog.open()
        except Exception as error:
            ui.notify(f"Export failed: {error}", type="negative")

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
            if target.suffix.lower() != ".iso":
                raise ValueError("Only ISO files are accepted")
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
        ui.label("Deployment workspace").classes("page-title")
        with ui.tabs().props("align=left").classes("workspace-tabs w-full") as tabs:
            inventory_tab = ui.tab("Inventory", icon="dns")
            media_tab = ui.tab("ISO library", icon="storage")
        with ui.tab_panels(tabs, value=inventory_tab).classes("w-full"):
            with ui.tab_panel(inventory_tab):
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
                with ui.row().classes("toolbar"):
                    ui.label("Initial inventory").classes("section-title")
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
                                   dict(headerName="Serial number", field="serial_number", width=170)],
                    "rowData": [], "rowSelection": {"mode": "multiRow", "enableClickSelection": False},
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
                with ui.column().classes("services-section"):
                    ui.label("Shared services").classes("section-title mb-3")
                    with ui.element("div").classes("services-grid"):
                        schema = json.loads((SCHEMA_PATH.parent / "shared.json").read_text())
                        for name, label, placeholder in (
                            ("dns_servers", "DNS servers", "192.0.2.53"),
                            ("dns_search_domains", "DNS search domains", "example.com"),
                            ("ntp_servers", "NTP servers", "0.pool.ntp.org"),
                        ):
                            shared_inputs[name] = ArrayInput(label, placeholder, schema["definitions"][name]["maxItems"])
                        shared_inputs["domain_name"] = ui.input("Domain name", placeholder="example.com").props("outlined dense").classes("w-full")
                        zones = schema["definitions"]["timezone"]["enum"]
                        shared_inputs["timezone"] = ui.select(zones, value="UTC", label="Timezone", with_input=True, clearable=True).props("outlined dense").classes("w-full")
                    with ui.expansion("Proxy settings", icon="settings_ethernet").classes("w-full mt-4"):
                        with ui.element("div").classes("proxy-grid"):
                            for name, label in (("http_proxy", "HTTP proxy"), ("https_proxy", "HTTPS proxy"), ("username", "Proxy username")):
                                proxy_inputs[name] = ui.input(label).props("outlined dense").classes("w-full")
                            proxy_inputs["password"] = ui.input("Proxy password", password=True, password_toggle_button=True).props("outlined dense autocomplete=new-password").classes("w-full")
                            proxy_inputs["reference"] = ui.number("Password reference", min=1, max=64, precision=0, value=None).props("outlined dense").classes("w-full")
                            proxy_schema = schema["definitions"]["proxy_servers"]["allOf"][0]["properties"]
                            proxy_inputs["no_proxy"] = ArrayInput("Proxy bypass list", "localhost", proxy_schema["no_proxy"]["maxItems"])
                errors = ui.column().classes("w-full mt-4")
                with ui.row().classes("w-full justify-end mt-4"):
                    ui.button("Validate", icon="fact_check", on_click=validate_click).props("outline")
                    ui.button("Generate YAML", icon="description", on_click=generate)
            with ui.tab_panel(media_tab):
                with ui.row().classes("toolbar"):
                    with ui.row().classes("items-center"):
                        ui.label("ISO library").classes("section-title")
                        media_count = ui.label("0").classes("muted")
                    with ui.row():
                        ui.button(icon="refresh", on_click=refresh_media).props("flat round dense").tooltip("Refresh files")
                        ui.button(icon="delete", color="negative", on_click=confirm_delete).props("outline round dense").tooltip("Delete selected files")
                with ui.element("div").classes("media-grid"):
                    iso_upload = ui.upload(label="Installation media", auto_upload=True, max_files=1,
                                          max_file_size=15000 * 1024 ** 2, on_upload=save_iso).props("accept=.iso").classes("w-full")
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
    tabs.on_value_change(lambda event: refresh_media() if event.value == "ISO library" else None)
    refresh_media()


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
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    secret_file = APP_DIR / ".storage-secret"
    if not secret_file.exists():
        write_private_file(secret_file, secrets.token_urlsafe(48))
    ui.add_css(CSS, shared=True)
    ui.run(host=arguments.host, port=arguments.port, storage_secret=secret_file.read_text().strip(),
           title="Cisco AI PODs", show=False, reload=False)


if __name__ == "__main__":
    main()