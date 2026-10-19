"""Offline tests for the allowlisted C880 HGX summary."""

import importlib.util
from pathlib import Path
import sys
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "probe_c880_hgx_summary.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("probe_c880_hgx_summary", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class HGXSummaryTests(unittest.TestCase):
    def test_paced_reads_emit_only_allowlisted_status(self):
        calls, sleeps = [], []
        responses = {
            MODULE.PATHS[0]: {
                "Status": {"Health": "Critical"},
                "ProcessorSummary": {"Count": 8},
                "Secret": "DO_NOT_EMIT",
            },
            MODULE.PATHS[1]: {"Status": {"Health": "Warning"}, "Message": "private"},
        }

        def fetch(path):
            calls.append(path)
            return responses[path]

        result = MODULE.probe(fetch, pause=sleeps.append)
        self.assertEqual(calls, list(MODULE.PATHS))
        self.assertEqual(sleeps, [MODULE.MIN_REQUEST_SPACING_SECONDS])
        self.assertEqual(result["hgx_baseboard_health"], "Critical")
        self.assertEqual(result["hgx_bmc_health"], "Warning")
        self.assertEqual(result["hgx_processor_count"], 8)
        self.assertNotIn("DO_NOT_EMIT", str(result))
        self.assertNotIn("private", str(result))


if __name__ == "__main__":
    unittest.main()
