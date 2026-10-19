"""Schema-aware YAML editor element (Monaco + monaco-yaml) with server-side validation."""

import json
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from nicegui import app, ui

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_ROUTE = "/aipod-static"
SCHEMA_ROUTE = "/aipod-schemas"
_REGISTERED = {"static": False}


def register_static(schema_bundle: Path) -> None:
    """Serve the editor bundle and the bundled schema once per process."""
    if _REGISTERED["static"]:
        return
    app.add_static_files(STATIC_ROUTE, STATIC_DIR)
    if schema_bundle.is_file():
        app.add_static_file(local_file=schema_bundle, url_path=f"{SCHEMA_ROUTE}/{schema_bundle.name}")
    _REGISTERED["static"] = True


def _asset_version() -> str:
    bundle = STATIC_DIR / "yaml-editor" / "yaml-editor.js"
    return str(int(bundle.stat().st_mtime)) if bundle.is_file() else "0"


def add_head() -> None:
    # The version query busts browser caches after the bundle is rebuilt.
    version = _asset_version()
    ui.add_head_html(
        f'<link rel="stylesheet" href="{STATIC_ROUTE}/yaml-editor/yaml-editor.css?v={version}">'
        f'<script src="{STATIC_ROUTE}/yaml-editor/yaml-editor.js?v={version}"></script>'
    )


@lru_cache(maxsize=4)
def _validator(schema_path: str, mtime: float) -> Draft202012Validator:
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_yaml(text: str, schema_path: Path | None) -> tuple[object, list[str]]:
    """Parse YAML and validate it against the bundled schema; returns (document, problems)."""
    try:
        document = yaml.safe_load(text) if text.strip() else {}
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        where = f"line {mark.line + 1}, column {mark.column + 1}: " if mark else ""
        return None, [f"YAML syntax error: {where}{getattr(error, 'problem', error)}"]
    if schema_path is None or not Path(schema_path).is_file():
        return document, []
    validator = _validator(str(schema_path), Path(schema_path).stat().st_mtime)
    errors = sorted(validator.iter_errors(document), key=lambda error: list(map(str, error.absolute_path)))
    # unevaluatedProperties also fires for valid siblings when any other error exists; keep it only when alone.
    if any(error.validator != "unevaluatedProperties" for error in errors):
        errors = [error for error in errors if error.validator != "unevaluatedProperties"]
    problems = [f"{'.'.join(map(str, error.absolute_path)) or '(root)'}: {error.message[:400]}" for error in errors]
    return document, problems


class YamlEditor:
    """A Monaco editor. Values are fetched from the browser on demand."""

    def __init__(self, value: str = "", schema_uri: str | None = None, height: str = "420px", read_only: bool = False):
        self.id = f"yaml-editor-{uuid4().hex}"
        self.initial = value
        self.element = ui.element("div").props(f'id="{self.id}"').classes("yaml-editor w-full").style(
            f"height:{height};min-height:200px;border:1px solid var(--border);border-radius:4px;overflow:hidden")
        options = {"schemaUri": schema_uri, "readOnly": read_only}
        ui.timer(0, lambda: ui.run_javascript(
            f"window.aipodYamlEditor && window.aipodYamlEditor.create({json.dumps(self.id)}, "
            f"{json.dumps(value)}, {json.dumps(options)})"), once=True)

    async def get_value(self) -> str:
        value = await ui.run_javascript(f"window.aipodYamlEditor.getValue({json.dumps(self.id)})", timeout=5)
        return self.initial if value is None else value

    def set_value(self, value: str) -> None:
        self.initial = value
        ui.run_javascript(f"window.aipodYamlEditor.setValue({json.dumps(self.id)}, {json.dumps(value)})")

    async def browser_problems(self) -> list[dict]:
        return await ui.run_javascript(f"window.aipodYamlEditor.problems({json.dumps(self.id)})", timeout=5) or []
