#!/usr/bin/env python3
"""Compatibility wrapper for 00-environment-prep/automation/scripts/build_initial_inventory.py."""

import runpy
from pathlib import Path

STAGE_SCRIPT = Path(__file__).resolve().parents[1] / "00-environment-prep/automation/scripts/build_initial_inventory.py"

if __name__ == "__main__":
    runpy.run_path(str(STAGE_SCRIPT), run_name="__main__")
else:
    globals().update({key: value for key, value in runpy.run_path(str(STAGE_SCRIPT)).items() if not key.startswith("__")})
