#!/usr/bin/env python3
"""Run Cisco AI POD deployment stages with live output.

Existing roles remain the implementation. This module owns role selection,
ordering, sensitive-variable validation, and live child-process output.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOST_VARS = REPO_ROOT / "host_vars"
PYTHON = sys.executable
ROLE_ORDER = ("everpure", "intersight", "openshift", "observability")
OPENSHIFT_STAGES = ("phase1", "iserver", "phase2")
VAULT_SECTIONS = ("everpure", "intersight", "openshift", "splunk_observability")
DEFAULT_VAULT_FILE = REPO_ROOT / "vault-ai-pod.yaml"
DEFAULT_VAULT_PASSWORD_FILE = Path.home() / ".config" / "cisco-ai-pods" / "vault-password"


class DeploymentError(RuntimeError):
    """Raised when a deployment stage cannot be completed."""


def merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    result = dict(left)
    for key, value in right.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def load_models(host_vars_dir: Path) -> dict[str, Any]:
    files = sorted(host_vars_dir.rglob("*.ezai.yaml"))
    if not files:
        raise DeploymentError(f"no *.ezai.yaml files found under {host_vars_dir}")
    merged: dict[str, Any] = {}
    for path in files:
        with path.open(encoding="utf-8") as stream:
            model = yaml.safe_load(stream) or {}
        if not isinstance(model, dict):
            raise DeploymentError(f"model file is not a mapping: {path}")
        merged = merge_dicts(merged, model)
    return merged


def load_vault_environment(vault_file: Path, password_file: Path) -> dict[str, str]:
    """Decrypt the vault and return its four environment-variable sections."""
    ansible_vault = shutil.which("ansible-vault")
    if ansible_vault is None:
        raise DeploymentError("ansible-vault was not found on PATH")
    if not vault_file.is_file():
        raise DeploymentError(f"vault file not found: {vault_file}")
    if not password_file.is_file():
        raise DeploymentError(
            f"vault password file not found: {password_file}\n"
            "Create the password file under your home directory, protect it with "
            "chmod 600, then rerun deploy_ai_pod.py."
        )
    permissions = password_file.stat().st_mode & 0o777
    if permissions != 0o600:
        raise DeploymentError(
            f"vault password file must have 0600 permissions: {password_file} "
            f"currently has {permissions:04o}. Run: chmod 600 {password_file}"
        )

    try:
        result = subprocess.run(
            [ansible_vault, "view", "--vault-password-file", str(password_file), str(vault_file)],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        raise DeploymentError(f"could not decrypt vault file: {vault_file}") from error

    vault = yaml.safe_load(result.stdout) or {}
    if not isinstance(vault, dict):
        raise DeploymentError("vault content must be a YAML mapping")

    environment: dict[str, str] = {}
    for section in VAULT_SECTIONS:
        values = vault.get(section, {})
        if values is None:
            continue
        if not isinstance(values, dict):
            raise DeploymentError(f"vault section {section!r} must be a mapping")
        for name, value in values.items():
            if not isinstance(name, str):
                raise DeploymentError(f"vault variable name in {section!r} must be a string")
            if isinstance(value, (dict, list, tuple, set)):
                raise DeploymentError(f"vault variable {name!r} must be a scalar value")
            if value is not None:
                environment[name] = str(value).lower() if isinstance(value, bool) else str(value)
    return environment


def run_command(command: list[str], env: dict[str, str], cwd: Path = REPO_ROOT) -> None:
    """Run a child process without buffering its combined terminal output."""
    print(f"\n==> {' '.join(command)}", flush=True)
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="", flush=True)
    return_code = process.wait()
    if return_code:
        raise DeploymentError(f"command failed with exit code {return_code}")


def validate_models(models: dict[str, Any], env: dict[str, str]) -> None:
    validator = REPO_ROOT / "scripts" / "validate_sensitive_variables.py"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as stream:
        json.dump(models, stream, indent=2, sort_keys=True)
        model_path = Path(stream.name)
    try:
        run_command([PYTHON, str(validator), "--models", str(model_path)], env)
    finally:
        model_path.unlink(missing_ok=True)


def role_is_configured(models: dict[str, Any], role: str) -> bool:
    config = models.get("splunk_observability" if role == "observability" else role, {})
    if not isinstance(config, dict):
        return False
    if role == "everpure":
        return bool((config.get("flash_arrays") or config.get("flash_blades")) and config.get("settings"))
    if role == "intersight":
        return "system" in config or "configure" in config
    if role == "openshift":
        return isinstance(config.get("install"), dict) and "bare_metal" in config["install"]
    return all(config.get(key) is not None for key in (
        "access_token", "openshift_cluster", "otel_collector", "splunk_platform"))


def bare_metal_install(models: dict[str, Any]) -> bool:
    install = models.get("openshift", {}).get("install", {})
    return isinstance(install, dict) and isinstance(install.get("bare_metal"), dict)


def iserver_command() -> list[str]:
    assisted_installer = REPO_ROOT / "assisted-installer"
    if shutil.which("iserver") is None:
        raise DeploymentError(
            "iserver not found on PATH. Install iServer, or rerun with "
            "--openshift-stage phase2 once the cluster is installed."
        )
    if not assisted_installer.is_dir():
        raise DeploymentError(f"assisted-installer directory not found: {assisted_installer}")
    return ["iserver", "create", "ocp", "cluster", "bm", "--dir", str(assisted_installer), "--mode", "install"]


def openshift_commands(
    models: dict[str, Any], check: bool, stages: tuple[str, ...]
) -> list[tuple[list[str], Path]]:
    commands: list[tuple[list[str], Path]] = []
    for stage in stages:
        if stage == "iserver":
            if not bare_metal_install(models):
                print("\n==> Skipping iServer: openshift.install.bare_metal is not configured", flush=True)
                continue
            if check:
                print("\n==> Skipping iServer: check mode", flush=True)
                continue
            commands.append((iserver_command(), REPO_ROOT / "assisted-installer"))
            continue
        command = ["ansible-playbook", str(REPO_ROOT / "playbooks" / f"deploy_openshift_{stage}.yaml")]
        if check:
            command.append("--check")
        commands.append((command, REPO_ROOT))
    return commands


def command_for_role(role: str, host_vars_dir: Path, check: bool) -> list[str]:
    if role == "intersight":
        command = [
            PYTHON,
            str(REPO_ROOT / "roles/intersight_ucs_provision/library/deploy_intersight_ucs.py"),
            "--dir", str(host_vars_dir / "intersight"),
            "--non-interactive",
        ]
        if check:
            command.append("--check")
        return command

    playbooks = {
        "everpure": ("deploy_storage.yaml", "everpure"),
        "observability": ("deploy_observability.yaml", None),
    }
    playbook, tag = playbooks[role]
    command = ["ansible-playbook", str(REPO_ROOT / "playbooks" / playbook)]
    if tag:
        command.extend(["--tags", tag])
    if check:
        command.append("--check")
    return command


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy Cisco AI Pod roles with live output.")
    parser.add_argument(
        "--role", action="append", choices=ROLE_ORDER, dest="roles",
        help="run one role; repeat for multiple roles (default: all)",
    )
    parser.add_argument(
        "--host-vars-dir", default=DEFAULT_HOST_VARS, type=Path,
        help=f"directory containing *.ezai.yaml files (default: {DEFAULT_HOST_VARS})",
    )
    parser.add_argument(
        "--vault-file", default=DEFAULT_VAULT_FILE, type=Path,
        help=f"encrypted Ansible Vault file (default: {DEFAULT_VAULT_FILE})",
    )
    parser.add_argument(
        "--vault-password-file", default=DEFAULT_VAULT_PASSWORD_FILE, type=Path,
        help=f"file containing the Ansible Vault password (default: {DEFAULT_VAULT_PASSWORD_FILE})",
    )
    parser.add_argument("--check", action="store_true", help="pass check mode where supported")
    parser.add_argument(
        "--openshift-stage", choices=OPENSHIFT_STAGES, default="phase1",
        help="openshift stage to start from, then continue through the rest (default: phase1)",
    )
    parser.add_argument(
        "--openshift-only-stage", choices=OPENSHIFT_STAGES, dest="only_stage",
        help="run a single openshift stage and stop",
    )
    args = parser.parse_args(argv)
    args.roles = set(args.roles or ROLE_ORDER)
    if args.only_stage:
        args.openshift_stages = (args.only_stage,)
    else:
        args.openshift_stages = OPENSHIFT_STAGES[OPENSHIFT_STAGES.index(args.openshift_stage):]
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        host_vars_dir = args.host_vars_dir.expanduser().resolve()
        vault_file = args.vault_file.expanduser().resolve()
        vault_password_file = args.vault_password_file.expanduser().resolve()
        models = load_models(host_vars_dir)
        env = os.environ.copy()
        env.update(load_vault_environment(vault_file, vault_password_file))
        env["PYTHONUNBUFFERED"] = "1"
        validate_models(models, env)
        for role in ROLE_ORDER:
            if role not in args.roles:
                continue
            if not role_is_configured(models, role):
                print(f"\n==> Skipping {role}: no matching configuration", flush=True)
                continue
            print(f"\n==> Starting {role}", flush=True)
            if role == "openshift":
                for command, cwd in openshift_commands(models, args.check, args.openshift_stages):
                    run_command(command, env, cwd)
            else:
                run_command(command_for_role(role, host_vars_dir, args.check), env)
        return 0
    except (DeploymentError, OSError, yaml.YAMLError) as error:
        print(f"deployment failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
