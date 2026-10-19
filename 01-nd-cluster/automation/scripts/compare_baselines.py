#!/usr/bin/env python3
"""Compare one manual ND baseline with one automated ND baseline."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR.resolve().parents[2]))

from shared.lib.nd_parity import compare_nd_baselines  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manual", required=True, type=Path)
    parser.add_argument("--automated", required=True, type=Path)
    args = parser.parse_args(argv)

    manual = json.loads(args.manual.read_text(encoding="utf-8"))
    automated = json.loads(args.automated.read_text(encoding="utf-8"))
    errors = compare_nd_baselines(manual, automated)
    if errors:
        print("ND baseline parity: FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("ND baseline parity: PASS")
    print(f"  manual:    {args.manual}")
    print(f"  automated: {args.automated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
