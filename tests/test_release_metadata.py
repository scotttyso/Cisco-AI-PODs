import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_bundled_schema_is_stamped_with_the_current_version(self):
        version = (REPO / "VERSION").read_text(encoding="utf-8").strip()
        schema = json.loads((REPO / "schema/cisco-ai-pods.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["x-schema-version"], version,
                         "run python scripts/merge_schemas.py after changing VERSION (the release workflow checks this)")


if __name__ == "__main__":
    unittest.main()
