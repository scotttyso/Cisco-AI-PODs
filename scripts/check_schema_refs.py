"""Check JSON schemas for broken $ref targets across the schema directories.

Split source trees (any directory holding the composition root) are validated
with the same resolution rules the bundler uses, so namespaced references such
as ``./intersight.json#/definitions/intersight.system`` are not false failures.
Every other JSON file is validated on its own, following relative file refs.
"""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import merge_schemas

DEFAULT_DIRECTORIES = ("schemas", "schema")
REMOTE_SCHEMES = ("http", "https", "urn")


def repository_root():
    return Path(__file__).resolve().parents[1]


def discover_files(directories):
    files = []
    seen = set()
    for directory in directories:
        if not directory.is_dir():
            raise SystemExit(f"Not a directory: {directory}")
        for path in sorted(directory.rglob("*.json")):
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                files.append(resolved)
    return files


def pointer_tokens(fragment):
    fragment = unquote(fragment)
    if not fragment or fragment == "/":
        return []
    if not fragment.startswith("/"):
        raise ValueError(f"JSON Pointer must start with '/': {fragment}")
    return [token.replace("~1", "/").replace("~0", "~") for token in fragment[1:].split("/")]


def resolve_pointer(document, fragment):
    current = document
    for token in pointer_tokens(fragment):
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return False
    return True


def iter_refs(value, location="#"):
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str):
            yield location, ref
        for key, child in value.items():
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            yield from iter_refs(child, f"{location}/{escaped}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_refs(child, f"{location}/{index}")


def display_path(path, root):
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def is_split_source(document):
    """A composition root is split when it still points at sibling schema files."""
    return any(urlsplit(entry[1]).path for entry in iter_refs(document))


def check_document(label, document, base_dir, documents, allow_remote):
    problems = []
    count = 0
    for location, ref in iter_refs(document):
        count += 1
        split = urlsplit(ref)
        if split.scheme in REMOTE_SCHEMES:
            if not allow_remote:
                problems.append((label, location, ref, "remote reference"))
            continue
        target = document
        if split.path:
            if base_dir is None:
                problems.append((label, location, ref, "reference left the bundle"))
                continue
            target_path = (base_dir / split.path).resolve()
            if target_path not in documents:
                problems.append((label, location, ref, f"missing file {split.path}"))
                continue
            target = documents[target_path]
        try:
            resolved = resolve_pointer(target, split.fragment)
        except ValueError as error:
            problems.append((label, location, ref, str(error)))
            continue
        if not resolved:
            problems.append((label, location, ref, "unresolved pointer"))
    return count, problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directories",
        nargs="*",
        type=Path,
        help="Directories to scan recursively (default: schemas schema).",
    )
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Treat http, https, and urn references as acceptable.",
    )
    parser.add_argument("--quiet", action="store_true", help="Only print problems.")
    arguments = parser.parse_args()

    root = repository_root()
    requested = arguments.directories or [Path(name) for name in DEFAULT_DIRECTORIES]
    directories = [path if path.is_absolute() else root / path for path in requested]

    documents = {}
    problems = []

    for path in discover_files(directories):
        try:
            documents[path] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            problems.append((display_path(path, root), "#", "", f"invalid JSON: {error}"))

    total_refs = 0
    bundled = set()
    source_dirs = sorted(
        path.parent
        for path, document in documents.items()
        if path.name == merge_schemas.ROOT_FILE and is_split_source(document)
    )

    for source_dir in source_dirs:
        members = {path for path in documents if source_dir in path.parents or path.parent == source_dir}
        if not members - bundled:
            continue
        bundled |= members
        label = f"{display_path(source_dir, root)} (bundled)"
        try:
            bundle = merge_schemas.build_bundle(merge_schemas.load_sources(source_dir))
        except (ValueError, KeyError) as error:
            problems.append((label, "#", "", f"bundle failed: {error}"))
            continue
        count, found = check_document(label, bundle, None, documents, arguments.allow_remote)
        total_refs += count
        problems.extend(found)

    for path, document in sorted(documents.items()):
        if path in bundled:
            continue
        count, found = check_document(
            display_path(path, root), document, path.parent, documents, arguments.allow_remote
        )
        total_refs += count
        problems.extend(found)

    for label, location, ref, detail in problems:
        suffix = f" -> {ref}" if ref else ""
        print(f"BROKEN {label} {location}{suffix} ({detail})")

    if not arguments.quiet:
        status = "FAIL" if problems else "OK"
        print(f"{status} files={len(documents)} refs={total_refs} problems={len(problems)}")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
