#!/usr/bin/env python3
"""Commit the rendered OpenShift GitOps content (openshift.destination_directory) and push it to the GitOps repository.

The directory becomes a working copy of the repository: the remote branch is fetched, the rendered files are committed
on top of it (files that exist only in the remote are kept), and the commit is pushed. Credentials for HTTPS remotes
come from the environment: the token from ``gitops_git_token`` (vault, openshift section) and the user name from
``AIPOD_GIT_USERNAME``; they are handed to git through scripts/git_askpass.sh and never written to disk.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ASKPASS = Path(__file__).resolve().parent / "git_askpass.sh"
TOKEN_ENV = "gitops_git_token"


def git(directory: Path, *arguments: str, env: dict, check: bool = True) -> subprocess.CompletedProcess:
    print("+ git " + " ".join(arguments), flush=True)
    result = subprocess.run(["git", "-C", str(directory), *arguments], env=env, text=True, capture_output=True)
    output = (result.stdout + result.stderr).strip()
    if output:
        print(output, flush=True)
    if check and result.returncode:
        raise SystemExit(f"ERROR: git {arguments[0]} failed ({result.returncode})")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--directory", type=Path, required=True, help="openshift.destination_directory")
    parser.add_argument("--url", required=True, help="GitOps repository URL")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--message", default="Update OpenShift GitOps operators")
    parser.add_argument("--author-name", default="Cisco AI PODs UI")
    parser.add_argument("--author-email", default="aipod@localhost")
    args = parser.parse_args()

    if not re.fullmatch(r"(https://|ssh://|git@)\S+", args.url):
        print("ERROR: the GitOps repository URL must start with https://, ssh://, or git@", file=sys.stderr)
        return 1
    if not re.fullmatch(r"[A-Za-z0-9._/-]{1,100}", args.branch):
        print("ERROR: invalid branch name", file=sys.stderr)
        return 1
    directory = args.directory
    if not directory.is_dir() or not any(path.name != ".git" for path in directory.iterdir()):
        print(f"ERROR: {directory} has no rendered content. Run Deploy GitOps first.", file=sys.stderr)
        return 1

    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS=str(ASKPASS),
               GIT_TOKEN=os.environ.get(TOKEN_ENV, ""),
               AIPOD_GIT_USERNAME=os.environ.get("AIPOD_GIT_USERNAME") or "x-access-token",
               GIT_AUTHOR_NAME=args.author_name, GIT_AUTHOR_EMAIL=args.author_email,
               GIT_COMMITTER_NAME=args.author_name, GIT_COMMITTER_EMAIL=args.author_email)
    if args.url.startswith("https://") and not env["GIT_TOKEN"]:
        print("Note: no GitOps repository token is stored; pushing without credentials.", flush=True)

    if not (directory / ".git").exists():
        git(directory, "init", "--quiet", "--initial-branch", args.branch, env=env)
    if git(directory, "remote", "get-url", "origin", env=env, check=False).returncode:
        git(directory, "remote", "add", "origin", args.url, env=env)
    else:
        git(directory, "remote", "set-url", "origin", args.url, env=env)

    fetched = git(directory, "fetch", "--quiet", "origin", args.branch, env=env, check=False).returncode == 0
    if fetched:
        # Point the branch at the remote without touching the rendered files, then bring back remote-only files.
        git(directory, "checkout", "--quiet", "-B", args.branch, env=env, check=False)
        git(directory, "reset", "--quiet", "--mixed", "FETCH_HEAD", env=env)
        deleted = git(directory, "ls-files", "--deleted", "-z", env=env).stdout.split("\0")
        missing = [name for name in deleted if name]
        if missing:
            git(directory, "checkout", "--", *missing, env=env)
    else:
        print(f"Branch {args.branch} does not exist in the remote yet; it will be created.", flush=True)
        git(directory, "checkout", "--quiet", "-B", args.branch, env=env, check=False)

    git(directory, "add", "-A", env=env)
    if git(directory, "diff", "--cached", "--quiet", env=env, check=False).returncode == 0:
        print("Nothing to commit: the repository already matches the rendered content.")
    else:
        git(directory, "commit", "--quiet", "-m", args.message, env=env)
    git(directory, "push", "--set-upstream", "origin", f"HEAD:refs/heads/{args.branch}", env=env)
    print(f"Pushed {directory} to {args.url} ({args.branch}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
