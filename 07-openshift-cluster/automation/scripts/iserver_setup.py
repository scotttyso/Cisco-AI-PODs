#!/usr/bin/env python3
"""Configure iserver access to the Red Hat OpenShift console and the Isovalent registry.

Secrets come from the environment (the Automation UI provides them from the vault):

* ``ocp_console_token`` - OpenShift Cluster Manager API token (https://console.redhat.com/openshift/token)
* ``ocp_pull_secret`` - pull secret JSON (https://console.redhat.com/openshift/install/pull-secret)
* ``isovalent_registry_token`` - Isovalent registry identity token

The console token and pull secret are written to 0600 temporary files that are removed after iserver copies them
into its settings directory (``~/.itool``). See https://github.com/datacenter/iserver/blob/main/doc/ocp/Console.md
and https://github.com/datacenter/iserver/blob/main/doc/ocp/IEP.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def iserver() -> str:
    path = shutil.which("iserver")
    if not path:
        sys.exit("iserver is not installed or not on PATH (https://github.com/datacenter/iserver)")
    return path


def secret(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"{name} is not set; store it in the vault on this page first")
    return value


SECRET_LINE = re.compile(r'(?i)^(\s*(?:identity token|token|secret)\s*:\s*).+$|("(?:access_token|token_id|refresh_token)"\s*:\s*)"[^"]*"')


def mask(line: str) -> str:
    """Hide the identity and access tokens that iserver prints."""
    return SECRET_LINE.sub(lambda match: f"{match.group(1)}********" if match.group(1) is not None
                           else f'{match.group(2)}"********"', line)


def run(*arguments: str) -> int:
    shown = ["********" if previous == "--token" and not Path(value).is_file() else value
             for previous, value in zip(("",) + arguments[1:], arguments[1:])]
    print("$ iserver " + " ".join(shown), flush=True)
    with subprocess.Popen(list(arguments), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                          errors="replace") as process:
        for line in process.stdout:
            print(mask(line.rstrip("\n")), flush=True)
    return process.returncode


def console(_: argparse.Namespace) -> int:
    token, pull_secret = secret("ocp_console_token"), secret("ocp_pull_secret")
    try:
        json.loads(pull_secret)
    except ValueError:
        sys.exit("ocp_pull_secret is not valid JSON; paste the pull secret exactly as downloaded")
    with tempfile.TemporaryDirectory(prefix="iserver-console-") as scratch:
        token_file, secret_file = Path(scratch) / "token.txt", Path(scratch) / "pull-secret.txt"
        for path, value in ((token_file, token), (secret_file, pull_secret)):
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(value + "\n")
        status = run(iserver(), "set", "ocp", "console", "--token", str(token_file), "--secret", str(secret_file))
    return status or console_check(_)


def console_check(_: argparse.Namespace) -> int:
    return run(iserver(), "get", "openshift", "login")


def isovalent(args: argparse.Namespace) -> int:
    return run(iserver(), "set", "ocp", "cilium", "registry", "--registry", args.registry,
               "--token", secret("isovalent_registry_token"))


def isovalent_check(_: argparse.Namespace) -> int:
    return run(iserver(), "get", "ocp", "cilium", "registry")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("console", help="store the console token and pull secret, then test the login").set_defaults(func=console)
    commands.add_parser("console-check", help="test the stored console login").set_defaults(func=console_check)
    registry = commands.add_parser("isovalent", help="store and verify the Isovalent registry identity token")
    registry.add_argument("--registry", default="registry.isovalent.com", help="registry host name only")
    registry.set_defaults(func=isovalent)
    commands.add_parser("isovalent-check", help="verify the stored Isovalent registry access").set_defaults(func=isovalent_check)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
