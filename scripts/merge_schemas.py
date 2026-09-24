"""Bundle the split Cisco AI POD JSON schemas into one VS Code-friendly schema."""

import argparse
import json
import posixpath
from pathlib import Path
from urllib.parse import unquote


ROOT_FILE = "cisco-ai-pods.json"
INTERSIGHT_ROOT = "intersight.json"
NAMESPACE_BY_FILE = {
    "shared.json": "abstract",
    "everpure.json": "everpure",
    "intersight.json": "intersight",
    "notifications.json": "notifications",
    "openshift.json": "openshift",
    "splunk_observability.json": "splunk_observability",
    "nexus-dashboard.json": "nexus_dashboard",
}


def json_pointer_tokens(fragment):
    if not fragment:
        return []
    fragment = fragment.lstrip("#")
    if fragment.startswith("definitions/"):
        fragment = "/" + fragment
    if not fragment.startswith("/"):
        raise ValueError(f"JSON Pointer must start with '/': #{fragment}")
    return [unquote(token).replace("~1", "/").replace("~0", "~") for token in fragment[1:].split("/")]


def pointer_from_tokens(tokens):
    escaped = [str(token).replace("~", "~0").replace("/", "~1") for token in tokens]
    return "#" + ("/" + "/".join(escaped) if escaped else "")


def load_sources(source_dir):
    documents = {}
    for path in sorted(source_dir.rglob("*.json")):
        relative_path = path.relative_to(source_dir).as_posix()
        if relative_path == "nexus-dashboard.json":
            continue
        with path.open(encoding="utf-8") as stream:
            documents[relative_path] = json.load(stream)
    if ROOT_FILE not in documents:
        raise ValueError(f"Missing composition root: {source_dir / ROOT_FILE}")
    return documents


def namespace_for_file(source_file):
    if source_file == ROOT_FILE:
        return None
    path = Path(source_file)
    if path.parts and path.parts[0] == "intersight":
        return "intersight"
    namespace = NAMESPACE_BY_FILE.get(path.name)
    if namespace is None:
        raise ValueError(f"No namespace configured for {source_file}")
    return namespace


def resolve_source_file(source_file, target, documents):
    relative_target = Path(source_file).parent / target
    target_path = posixpath.normpath(relative_target.as_posix())
    if target_path in documents:
        return target_path

    # Intersight files were originally flat beside shared.json. Keep those
    # references valid after moving the files into source/intersight/.
    root_target = Path(target).as_posix()
    if Path(source_file).parts[:1] == ("intersight",) and root_target in documents:
        return root_target
    return target_path


def files_in_namespace(namespace, documents):
    return [
        filename
        for filename in documents
        if namespace_for_file(filename) == namespace
    ]


def intersight_definitions(documents):
    """Return the nested Intersight overlay over the legacy Intersight root."""
    definitions = {}
    origins = {}
    ordered_files = [INTERSIGHT_ROOT] + sorted(
        filename for filename in documents if filename.startswith("intersight/")
    )
    for filename in ordered_files:
        for name, definition in documents[filename].get("definitions", {}).items():
            if filename == INTERSIGHT_ROOT:
                logical_name = name
            else:
                child_namespace = Path(filename).stem
                logical_name = f"{child_namespace}.{name}"
            definitions[logical_name] = definition
            origins[logical_name] = filename
    return definitions, origins


def build_definition_map(documents):
    merged = {}
    locations = {}
    logical_intersight, intersight_origins = intersight_definitions(documents)
    source_documents = [(INTERSIGHT_ROOT, logical_intersight, intersight_origins)]
    source_documents.extend(
        (filename, document.get("definitions", {}), {name: filename for name in document.get("definitions", {})})
        for filename, document in documents.items()
        if filename != ROOT_FILE
        and filename != INTERSIGHT_ROOT
        and not filename.startswith("intersight/")
    )
    root_definitions = documents[ROOT_FILE].get("definitions", {})
    source_documents.insert(0, (ROOT_FILE, root_definitions, {name: ROOT_FILE for name in root_definitions}))

    for logical_file, definitions, origins in source_documents:
        namespace = namespace_for_file(logical_file)
        for name, definition in definitions.items():
            merged_name = name if namespace is None else f"{namespace}.{name}"
            if merged_name in locations:
                previous = locations[merged_name]
                if namespace == "intersight":
                    locations[merged_name] = f"{origins[name]}#/definitions/{name}"
                    merged[merged_name] = rewrite_schema(definition, origins[name], documents)
                    continue
                raise ValueError(
                    f"Duplicate merged definition {merged_name!r}: "
                    f"{previous} and {origins[name]}#/definitions/{name}"
                )
            merged[merged_name] = rewrite_schema(definition, origins[name], documents)
            locations[merged_name] = f"{origins[name]}#/definitions/{name}"
    return dict(sorted(merged.items()))


def resolve_definition(source_file, definition_name, documents):
    source_namespace = namespace_for_file(source_file)
    if source_namespace == "intersight":
        logical_definitions = intersight_definitions(documents)[0]
        if definition_name in logical_definitions:
            return f"intersight.{definition_name}"
        if source_file.startswith("intersight/"):
            child_namespace = Path(source_file).stem
            child_name = f"{child_namespace}.{definition_name}"
            if child_name in logical_definitions:
                return f"intersight.{child_name}"
    if definition_name in documents[source_file].get("definitions", {}):
        return definition_name if source_namespace is None else f"{source_namespace}.{definition_name}"

    if source_namespace is not None:
        matching_files = [
            filename
            for filename in files_in_namespace(source_namespace, documents)
            if definition_name in documents[filename].get("definitions", {})
        ]
        if len(matching_files) == 1:
            return f"{source_namespace}.{definition_name}"
        if len(matching_files) > 1:
            raise ValueError(
                f"Ambiguous definition {definition_name!r} in namespace "
                f"{source_namespace}: {matching_files}"
            )

    prefix, separator, remainder = definition_name.partition(".")
    if separator:
        matching_files = [
            filename
            for filename in files_in_namespace(prefix, documents)
            if remainder in documents[filename].get("definitions", {})
        ]
        if len(matching_files) == 1:
            return f"{prefix}.{remainder}"
        if len(matching_files) > 1:
            raise ValueError(
                f"Ambiguous definition {definition_name!r}: {matching_files}"
            )

    raise ValueError(f"Cannot resolve definition {definition_name!r} from {source_file}")


def rewrite_ref(raw_ref, source_file, documents):
    if not isinstance(raw_ref, str):
        raise ValueError(f"$ref must be a string, got {raw_ref!r}")

    target, separator, fragment = raw_ref.partition("#")
    target_file = source_file if not target else resolve_source_file(source_file, target, documents)
    if target_file not in documents:
        raise ValueError(f"{source_file}: reference targets unknown schema {target!r}")

    tokens = json_pointer_tokens(fragment)
    if not tokens:
        raise ValueError(f"{source_file}: reference has no definition target: {raw_ref}")
    if tokens[0] != "definitions" or len(tokens) < 2:
        raise ValueError(f"{source_file}: unsupported reference shape: {raw_ref}")

    merged_name = resolve_definition(target_file, tokens[1], documents)
    tokens[1] = merged_name
    return pointer_from_tokens(tokens)


def rewrite_schema(node, source_file, documents):
    if isinstance(node, dict):
        rewritten = {}
        for key, value in node.items():
            if key == "$ref":
                rewritten[key] = rewrite_ref(value, source_file, documents)
            else:
                rewritten[key] = rewrite_schema(value, source_file, documents)
        return rewritten
    if isinstance(node, list):
        return [rewrite_schema(value, source_file, documents) for value in node]
    return node


def build_bundle(documents):
    root = rewrite_schema(documents[ROOT_FILE], ROOT_FILE, documents)
    root["definitions"] = build_definition_map(documents)
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "schemas" / "source",
        help="Directory containing the split JSON schemas.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "schema" / "cisco-ai-pods.json",
        help="Path for the generated bundled schema.",
    )
    args = parser.parse_args()

    documents = load_sources(args.source_dir)
    bundle = build_bundle(documents)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as stream:
        json.dump(bundle, stream, indent=4, ensure_ascii=False)
        stream.write("\n")
    print(f"Wrote {args.output} with {len(bundle['definitions'])} definitions")


if __name__ == "__main__":
    main()
