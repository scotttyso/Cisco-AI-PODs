#!/usr/bin/env python3
"""Share environment secrets through the deployments git repository.

export  re-encrypt each environment's vault.yaml with the repository vault password into secrets.vault.yaml
import  merge each secrets.vault.yaml back into the local vault.yaml (repository values win)
remove  delete the secrets.vault.yaml copies (secrets are no longer stored in the repository)

The repository vault password is read from the GIT_REPO_PASSWORD environment variable.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aipod_webui.environments import (  # noqa: E402
    REPO_PASSWORD_ENV, EnvironmentProblem, export_secrets, import_secrets, remove_exported,
)
from aipod_webui.vault import VaultError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("operation", choices=("export", "import", "remove"))
    parser.add_argument("--root", type=Path, required=True, help="deployments repository")
    parser.add_argument("--password-file", type=Path, required=True, help="this server's automation vault password file")
    args = parser.parse_args()
    try:
        if args.operation == "remove":
            removed = remove_exported(args.root)
            print("Secrets are not stored in the repository" + (f"; removed copies for {', '.join(removed)}" if removed else ""))
            return 0
        action = export_secrets if args.operation == "export" else import_secrets
        report = action(args.root, args.password_file, os.environ.get(REPO_PASSWORD_ENV, ""))
    except (EnvironmentProblem, VaultError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    verb = "Encrypted with the repository vault password" if args.operation == "export" else "Imported into the local vault"
    print(f"{verb}: " + ("; ".join(report) if report else "no environment secrets"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
