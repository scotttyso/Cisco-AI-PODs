"""Compatibility package for the collection-native shared Python helpers."""

from pathlib import Path

__path__ = [str(Path(__file__).resolve().parents[1] / "plugins" / "module_utils" / "shared")]
