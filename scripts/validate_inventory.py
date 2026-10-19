#!/usr/bin/env python3
"""validate_inventory.py - validate an inventory YAML against a JSON Schema.

Used in CI and locally to verify per-subsystem and AI POD-wide inventory files.
Resolves $ref references against the local filesystem so we never make
network calls during validation.

Usage (composed root):
    python3 scripts/validate_inventory.py \
        --schema schemas/aipod.schema.json \
        --inventory schemas/_examples/aipod.yaml.example

Usage (per-subsystem convenience):
    python3 scripts/validate_inventory.py \
        --subsystem nd-cluster \
        --inventory inventories/aipod-prod.yaml

Exits 0 on valid, non-zero on failure (prints all errors).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012


def load_schema_tree(root_schema: Path) -> tuple[dict, Registry]:
    """Load the root schema and walk relative $refs to populate a Registry.

    The schemas in this repo use relative $refs (e.g. ../_shared/foo.schema.json)
    so they can be moved together without rewriting URIs. We canonicalize each
    schema's $id and register it in the Registry under both its $id and a
    file:// URI so the validator can resolve refs deterministically.
    """
    seen: dict[Path, dict] = {}
    registry = Registry()

    def _load(path: Path) -> dict:
        path = path.resolve()
        if path in seen:
            return seen[path]
        with open(path) as f:
            doc = json.load(f)
        seen[path] = doc

        nonlocal registry
        resource = Resource(contents=doc, specification=DRAFT202012)
        # Register under the schema's $id (canonical) and under the file URI
        # (so relative $ref resolution against a file:// base finds it).
        if "$id" in doc:
            registry = registry.with_resource(uri=doc["$id"], resource=resource)
        registry = registry.with_resource(uri=path.as_uri(), resource=resource)

        # Recurse into any $ref values that look like local paths.
        def _walk(node):
            if isinstance(node, dict):
                ref = node.get("$ref")
                if isinstance(ref, str) and not ref.startswith(("#", "http://", "https://")):
                    # Strip JSON pointer fragment for the file lookup.
                    target = ref.split("#", 1)[0]
                    if target:
                        _load(path.parent / target)
                for v in node.values():
                    _walk(v)
            elif isinstance(node, list):
                for v in node:
                    _walk(v)

        _walk(doc)
        return doc

    root = _load(root_schema)
    return root, registry


# Default home for AI POD subsystem schemas. Resolved from this script's
# location: cisco-aipod/scripts/validate_inventory.py
# -> cisco-aipod/schemas/. Used by --subsystem to map a name to a file.
SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    schema_group = parser.add_mutually_exclusive_group(required=True)
    schema_group.add_argument("--schema", type=Path,
                              help="Path to a JSON Schema file (any location).")
    schema_group.add_argument("--subsystem", type=str,
                              help="Subsystem name; resolves to schemas/<name>.schema.json. "
                                   "Convenience for the common case.")
    parser.add_argument("--inventory", required=True, type=Path,
                        help="Path to inventory YAML to validate.")
    args = parser.parse_args()

    if args.subsystem:
        args.schema = SCHEMAS_DIR / f"{args.subsystem}.schema.json"

    if not args.schema.exists():
        print(f"ERROR: schema not found: {args.schema}", file=sys.stderr)
        return 2
    if not args.inventory.exists():
        print(f"ERROR: inventory not found: {args.inventory}", file=sys.stderr)
        return 2

    root_schema, registry = load_schema_tree(args.schema)

    with open(args.inventory) as f:
        instance = yaml.safe_load(f)

    # We validate via a $ref to the root schema's file:// URI so that any
    # relative $refs inside the schema tree resolve against the schema file's
    # parent directory. The registry was populated by walking the tree, so
    # everything resolves locally with zero network access.
    root_uri = args.schema.resolve().as_uri()
    schema_via_ref = {"$ref": root_uri}
    validator = Draft202012Validator(schema_via_ref, registry=registry)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))

    if not errors:
        print(f"OK  {args.inventory}  validates against  {args.schema.name}")
        return 0

    print(f"FAIL  {args.inventory}  ({len(errors)} error(s))", file=sys.stderr)
    for err in errors:
        loc = "/".join(str(p) for p in err.absolute_path) or "(root)"
        print(f"  at {loc}: {err.message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
