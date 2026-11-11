#!/usr/bin/env python
"""Build the automation appliance using credentials from an Ansible Vault file."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

APPLIANCE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_VAULT_FILE = Path.home() / ".config" / "cisco-ai-pods" / "appliance-build.yml"
DEFAULT_VAULT_PASSWORD_FILE = Path.home() / ".config" / "cisco-ai-pods" / "vault-password"


class BuildError(RuntimeError):
    """Raised when credentials cannot be loaded or a build command fails."""


def load_build_environment(vault_file: Path, password_file: Path) -> dict[str, str]:
    ansible_vault = shutil.which("ansible-vault")
    openssl = shutil.which("openssl")
    if ansible_vault is None:
        raise BuildError("ansible-vault was not found on PATH")
    if openssl is None:
        raise BuildError("openssl was not found on PATH")
    if not vault_file.is_file():
        raise BuildError(f"vault file not found: {vault_file}")
    if not password_file.is_file():
        raise BuildError(f"vault password file not found: {password_file}")
    permissions = password_file.stat().st_mode & 0o777
    if permissions != 0o600:
        raise BuildError(
            f"vault password file must have 0600 permissions: {password_file} "
            f"currently has {permissions:04o}. Run: chmod 600 {password_file}"
        )

    try:
        decrypted = subprocess.run(
            [ansible_vault, "view", "--vault-password-file", str(password_file), str(vault_file)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except subprocess.CalledProcessError as error:
        raise BuildError(f"could not decrypt vault file: {vault_file}") from error

    try:
        values: Any = yaml.safe_load(decrypted)
    except yaml.YAMLError as error:
        raise BuildError(f"vault file is not valid YAML: {vault_file}") from error
    if not isinstance(values, dict):
        raise BuildError("vault content must be a YAML mapping")

    secrets = {}
    for name in ("vsphere_password", "build_password"):
        pkr_name = f"PKR_VAR_{name}"
        value = values.get(pkr_name, values.get(name))
        if not isinstance(value, str) or not value:
            raise BuildError(
                f"vault must contain a non-empty {name!r} or {pkr_name!r} string"
            )
        if name in values and pkr_name in values and values[name] != values[pkr_name]:
            raise BuildError(f"vault contains conflicting values for {name!r} and {pkr_name!r}")
        secrets[name] = value

    try:
        password_hash = subprocess.run(
            [openssl, "passwd", "-6", "-stdin"],
            input=secrets["build_password"] + "\n",
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as error:
        raise BuildError("could not hash the build password with openssl") from error
    if not password_hash:
        raise BuildError("openssl returned an empty build password hash")

    return {
        "PKR_VAR_vsphere_password": secrets["vsphere_password"],
        "PKR_VAR_build_password": secrets["build_password"],
        "PKR_VAR_build_password_hash": password_hash,
    }


def run(command: list[str], environment: dict[str, str]) -> None:
    print(f"\n==> {' '.join(command)}", flush=True)
    try:
        subprocess.run(command, cwd=APPLIANCE_DIR, env=environment, check=True)
    except subprocess.CalledProcessError as error:
        raise BuildError(f"command failed with exit code {error.returncode}: {command[0]}") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="1.0.1", help="appliance version (default: %(default)s)")
    parser.add_argument("--vault-file", type=Path, default=DEFAULT_VAULT_FILE)
    parser.add_argument("--vault-password-file", type=Path, default=DEFAULT_VAULT_PASSWORD_FILE)
    arguments = parser.parse_args()

    try:
        environment = os.environ.copy()
        environment.update(load_build_environment(arguments.vault_file, arguments.vault_password_file))
        run(["packer", "init", "."], environment)
        run(["packer", "validate", "-var", f"appliance_version={arguments.version}", "."], environment)
        run(
            [
                "packer", "build", "-force", "-on-error=ask",
                "-var", f"appliance_version={arguments.version}", ".",
            ],
            environment,
        )
    except BuildError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except FileNotFoundError as error:
        print(f"error: required command not found: {error.filename}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
