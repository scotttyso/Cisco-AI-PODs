"""Discover published GitHub releases and produce administrator CLI instructions."""

from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

import requests


REPOSITORY = "scotttyso/Cisco-AI-PODs"
RELEASES_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
VERSION_FILE = Path(__file__).resolve().parents[1] / "VERSION"
TAG_PATTERN = re.compile(r"v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?\Z")
UPDATER = Path("/usr/local/sbin/aipod-update")
UPDATE_LOG_DIR = Path("/var/log/aipod-update")


def installed_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip() or "development"
    except OSError:
        return "development"


def release_details(payload: dict) -> dict:
    tag = payload.get("tag_name", "")
    if not isinstance(tag, str) or not TAG_PATTERN.fullmatch(tag):
        raise ValueError("Latest GitHub release has an unsupported version tag")
    return {"tag": tag, "name": str(payload.get("name") or tag),
            "url": f"https://github.com/{REPOSITORY}/releases/tag/{tag}",
            "published_at": payload.get("published_at", ""),
            "notes": str(payload.get("body") or "No release notes provided.")}


def latest_release(timeout: float = 10.0) -> dict:
    response = requests.get(RELEASES_API, headers={"Accept": "application/vnd.github+json"}, timeout=timeout)
    if response.status_code == 404:
        raise ValueError("No published releases found for this repository yet")
    response.raise_for_status()
    return release_details(response.json())


def install_instructions(tag: str) -> str:
    if not TAG_PATTERN.fullmatch(tag):
        raise ValueError("Invalid release version")
    return f'''# Finish ALL active playbooks, uploads, and terminal work first.
# Run this on the appliance or server from a normal admin shell.
# The updater verifies the GitHub tag, confirms the outage, backs up UI state,
# playbooks, and system configuration, checks out the release, reruns setup,
# and validates the service. Failures leave the service stopped.
sudo /usr/local/sbin/aipod-update --version {tag}
'''


def updater_available() -> bool:
    """The UI can install updates on a standard appliance / bare-metal install (aipod-update and systemd)."""
    return UPDATER.is_file() and shutil.which("systemd-run") is not None and shutil.which("sudo") is not None


def update_unit(tag: str, now: float | None = None) -> str:
    if not TAG_PATTERN.fullmatch(tag):
        raise ValueError("Invalid release version")
    return f"aipod-update-{tag.replace('.', '_')}-{time.strftime('%Y%m%d%H%M%S', time.localtime(now))}"


def update_command(tag: str, unit: str) -> list[str]:
    """Start the updater as its own transient systemd unit.

    The updater stops automation-ui.service, which kills every process the UI started; running it in a separate unit
    lets it finish, restart the UI, and log to /var/log/aipod-update/<unit>.log for the UI to show afterwards.
    """
    if not TAG_PATTERN.fullmatch(tag) or not re.fullmatch(r"aipod-update-[A-Za-z0-9_-]+", unit):
        raise ValueError("Invalid release version")
    return ["sudo", "-A", "-p", "", "systemd-run", f"--unit={unit}", "--collect", "--quiet",
            "--property=LogsDirectory=aipod-update", f"--property=StandardOutput=append:{UPDATE_LOG_DIR}/{unit}.log",
            "--property=StandardError=inherit", str(UPDATER), "--version", tag, "--yes"]


def latest_update_log(limit: int = 60000) -> tuple[str, str]:
    """(file name, tail of the text) of the newest update log, or ("", "")."""
    try:
        logs = sorted(UPDATE_LOG_DIR.glob("aipod-update-*.log"), key=lambda path: path.stat().st_mtime)
    except OSError:
        return "", ""
    if not logs:
        return "", ""
    try:
        data = logs[-1].read_bytes()[-limit:]
    except OSError:
        return logs[-1].name, ""
    return logs[-1].name, data.decode("utf-8", "replace")
