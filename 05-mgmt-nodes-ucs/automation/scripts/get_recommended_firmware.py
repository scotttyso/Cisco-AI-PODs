#!/usr/bin/env python
"""Read Cisco-recommended server firmware from Intersight without changing policies or servers.

Credentials use the same environment variables as collect_intersight_macs.py.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile

import requests

from check_intersight_domain_ports import query
from collect_intersight_macs import session


IMAGE_TYPES = {"FIAttached": "Intersight Managed Mode Server", "Standalone": "Standalone Server"}


def model_family(model: str) -> str:
    """Match catalog PIDs that differ only by the server's hardware variant suffix."""
    model = model.strip().upper()
    for suffix in ("L", "D", "X", "N", "S", "M", "SNEB", "S2"):
        model = model.removesuffix(suffix)
    return model


def parse_models(values: list[str]) -> list[tuple[str, str]]:
    models = set()
    for value in values:
        platform, separator, model = value.partition("=")
        if not separator or platform not in IMAGE_TYPES or not model.strip():
            raise ValueError(f"Invalid model {value!r}; use FIAttached=PID or Standalone=PID")
        models.add((platform, model.strip().upper()))
    if not models:
        raise ValueError("Provide at least one server model")
    return sorted(models)


def recommendations(client: requests.Session, base: str, models: list[tuple[str, str]]) -> list[dict]:
    result = []
    for platform in sorted({platform for platform, _model in models}):
        image_type = IMAGE_TYPES[platform]
        images = query(client, base, "firmware/Distributables",
                       f"RecommendedBuild eq 'Y' and ImageType eq '{image_type}'")
        exact: dict[str, set[str]] = {}
        families: dict[str, set[str]] = {}
        for image in images:
            if not isinstance(image, dict):
                raise ValueError("Firmware catalog: expected image objects")
            version, supported = image.get("Version"), image.get("SupportedModels")
            if not isinstance(version, str) or not version.strip():
                raise ValueError("Firmware catalog: image has no Version")
            # SupportedModels is nullable in the API; an image without models cannot match a PID.
            if supported is None:
                supported = []
            if not isinstance(supported, list) or any(
                    not isinstance(model, str) or not model.strip() for model in supported):
                raise ValueError("Firmware catalog: expected SupportedModels to contain PIDs")
            for model in supported:
                exact.setdefault(model.strip().upper(), set()).add(version.strip())
                families.setdefault(model_family(model), set()).add(version.strip())
        for target_platform, model in models:
            if target_platform == platform:
                versions = sorted(exact.get(model) or families.get(model_family(model), set()))
                result.append({"model": model, "platform": platform, "versions": versions})
    return result


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="append", required=True, help="FIAttached=PID or Standalone=PID; repeatable")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default=os.environ.get("intersight_fqdn", "intersight.com"))
    args = parser.parse_args()
    base = args.url.rstrip("/")
    if not base.startswith(("https://", "http://")):
        base = f"https://{base}"
    try:
        models = parse_models(args.model)
        with session() as client:
            rows = recommendations(client, base, models)
        report = {"source": base, "collected": datetime.now(timezone.utc).isoformat(), "models": rows}
        write_report(args.output, report)
        for row in rows:
            versions = ", ".join(row["versions"]) or "WARNING: no recommended build found"
            print(f"{row['model']} ({row['platform']}): {versions}", flush=True)
        print(f"Saved recommendations to {args.output}. No firmware or policies were changed.", flush=True)
        return 0
    except (OSError, ValueError, requests.RequestException) as error:
        print(f"Recommended firmware lookup failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
