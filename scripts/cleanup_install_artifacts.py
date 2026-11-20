"""Remove the sensitive leftovers of an OpenShift install, and tighten the permissions of what has to stay.

What iServer and the install prep leave behind:

  assisted-installer/   server.json holds the Fabric Interconnect and BMC passwords in clear text; cluster.json,
                        web.json, proxy.json, ssh.pub and the manifests describe the cluster. Prepare install writes
                        all of it again, so it is safe to delete after the install.
  /tmp/iserver/<run>/   one folder per iServer command with debug logs. They contain the Red Hat pull secret and token
                        and, for the install run, the kubeadmin password and the kubeconfig.
  /tmp/<uuid>.iso|.kubeconfig and /tmp/<uuid> private key files   scratch files iServer creates and may leave behind.
  <media dir>/          the OpenShift discovery ISO (<uuid>.iso) embeds credentials for the install, and iServer's
                        test files (image-<uuid>.iso, <uuid>) are left behind. The directory is served publicly.
  ~/.itool/             iServer's own settings: the Red Hat token, the pull secret, the Isovalent registry token and
                        each cluster's kubeconfig. Needed for day 2 operations, so it is kept but made private.

Without --yes nothing is changed; the plan is printed.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
MEDIA_PATTERNS = (re.compile(rf"^{UUID}\.iso$"), re.compile(rf"^image-{UUID}\.iso$"), re.compile(rf"^{UUID}$"))
TMP_PATTERNS = (re.compile(rf"^{UUID}\.(iso|kubeconfig)$"),)
RUN_FOLDER = re.compile(r"^[0-9a-f]{12}$")


@dataclass
class Plan:
    remove: list[Path] = field(default_factory=list)
    tighten: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def owned(path: Path) -> bool:
    return path.lstat().st_uid == os.getuid()


def children(directory: Path):
    try:
        return sorted(directory.iterdir())
    except OSError:
        return []


def looks_like_private_key(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            return stream.read(11) == b"-----BEGIN "
    except OSError:
        return False


def build_plan(assisted_dir: Path, tmp_dir: Path, media_dir: Path | None, itool_dir: Path, keep_logs: bool) -> Plan:
    plan = Plan()
    if assisted_dir.is_dir():
        plan.remove += children(assisted_dir)
    if not keep_logs:
        logs = tmp_dir / "iserver"
        plan.remove += [path for path in children(logs) if RUN_FOLDER.match(path.name) and path.is_dir()
                        and not path.is_symlink() and owned(path)]
    for path in children(tmp_dir):
        if path.is_symlink() or not path.is_file() or not owned(path):
            continue
        if any(pattern.match(path.name) for pattern in TMP_PATTERNS) or (
                re.match(rf"^{UUID}$", path.name) and looks_like_private_key(path)):
            plan.remove.append(path)
    if media_dir and media_dir.is_dir():
        plan.remove += [path for path in children(media_dir) if not path.is_symlink() and path.is_file()
                        and any(pattern.match(path.name) for pattern in MEDIA_PATTERNS)]
    if itool_dir.is_dir():
        plan.tighten.append(itool_dir)
    else:
        plan.notes.append(f"{itool_dir} does not exist; nothing to tighten")
    return plan


def remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path, ignore_errors=False)


def tighten(root: Path) -> int:
    """Remove group and other access below ``root`` (files 0600, folders 0700). Returns how many items changed."""
    changed = 0
    for current, folders, files in os.walk(root):
        for name in [*folders, *files]:
            path = Path(current) / name
            if path.is_symlink():
                continue
            mode = stat.S_IMODE(path.lstat().st_mode)
            wanted = mode & 0o700
            if wanted != mode:
                path.chmod(wanted)
                changed += 1
    mode = stat.S_IMODE(root.lstat().st_mode)
    if mode & 0o077:
        root.chmod(mode & 0o700)
        changed += 1
    return changed


def execute(plan: Plan, yes: bool, out=print) -> int:
    failures = 0
    for path in plan.remove:
        out(f"{'remove' if yes else 'would remove'}: {path}")
        if yes:
            try:
                remove(path)
            except OSError as error:
                failures += 1
                out(f"  could not remove {path}: {error}")
    for root in plan.tighten:
        if yes:
            out(f"tightened {tighten(root)} item(s) under {root} (owner access only)")
        else:
            out(f"would make {root} private (owner access only)")
    for note in plan.notes:
        out(note)
    if not plan.remove:
        out("nothing to remove")
    return 1 if failures else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="delete (without it only the plan is printed)")
    parser.add_argument("--assisted-dir", type=Path, default=REPO_ROOT / "assisted-installer")
    parser.add_argument("--tmp-dir", type=Path, default=Path("/tmp"))
    parser.add_argument("--media-dir", type=Path, default=Path(os.environ.get("AI_PODS_MEDIA_DIR", "/var/www/html/os-images")))
    parser.add_argument("--itool-dir", type=Path, default=Path.home() / ".itool")
    parser.add_argument("--keep-logs", action="store_true", help="keep the iServer run logs in /tmp/iserver")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    plan = build_plan(args.assisted_dir, args.tmp_dir, args.media_dir, args.itool_dir, args.keep_logs)
    if not args.yes:
        print("Dry run: nothing is changed. Add --yes to apply.\n")
    return execute(plan, args.yes)


if __name__ == "__main__":
    sys.exit(main())
