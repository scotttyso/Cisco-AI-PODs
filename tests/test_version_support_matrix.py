import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import version_support_matrix as matrix  # noqa: E402

HELM_INDEX = b"""
entries:
  cilium:
    - version: 1.19.7
    - version: 1.19.9
    - version: 1.19.10-pre.1
    - version: 1.18.15
  tetragon:
    - version: 1.19.9
"""

ISERVER_JSON = """[WARNING] ignored
{"4.20.16": {"display_name": "4.20.16", "support_level": "production", "default": true},
 "4.19.20": {"display_name": "4.19.20", "support_level": "maintenance"}}

Version: 0.31.04
Info: finished in 1 ms
"""


class SupportTests(unittest.TestCase):
    def test_only_supported_minors_with_well_formed_versions_validate(self):
        self.assertTrue(matrix.is_supported("openshift", "4.20.46")[0])
        self.assertTrue(matrix.is_supported("openshift", "5.0.1")[0])
        self.assertTrue(matrix.is_supported("cilium", "1.19.9")[0])
        for kind, version in (("openshift", "4.18.9"), ("cilium", "1.18.15"), ("cilium", "latest"), ("openshift", "4.20")):
            ok, reason = matrix.is_supported(kind, version)
            self.assertFalse(ok, version)
            self.assertTrue(reason)

    def test_version_ordering_is_numeric(self):
        self.assertGreater(matrix.version_key("4.20.10"), matrix.version_key("4.20.9"))


class OpenShiftTests(unittest.TestCase):
    def test_iserver_output_is_parsed_past_status_lines(self):
        result = Mock(returncode=0, stdout=ISERVER_JSON)
        with patch.object(matrix.shutil, "which", return_value="/usr/bin/iserver"), \
                patch.object(matrix.subprocess, "run", return_value=result):
            items = matrix.openshift_from_iserver(("production",))
        self.assertEqual({item["version"] for item in items}, {"4.20.16", "4.19.20"})
        self.assertTrue(next(item for item in items if item["version"] == "4.20.16")["default"])

    def test_iserver_failure_means_unavailable(self):
        with patch.object(matrix.shutil, "which", return_value="/usr/bin/iserver"), \
                patch.object(matrix.subprocess, "run", return_value=Mock(returncode=1, stdout="[ERROR] token")):
            self.assertIsNone(matrix.openshift_from_iserver())
        with patch.object(matrix.shutil, "which", return_value=None):
            self.assertIsNone(matrix.openshift_from_iserver())

    def test_versions_are_limited_to_supported_minors_newest_first(self):
        items = [{"version": "4.18.9", "support_level": "maintenance"}, {"version": "4.20.9", "support_level": "production"},
                 {"version": "4.20.16", "support_level": "production"}, {"version": "4.19.20", "support_level": "maintenance"}]
        with patch.object(matrix, "openshift_from_iserver", return_value=items):
            versions, source = matrix.openshift_versions()
        self.assertEqual([item["version"] for item in versions], ["4.20.16", "4.20.9", "4.19.20"])
        self.assertIn("iserver", source)

    def test_public_graph_is_the_fallback_then_the_matrix(self):
        public = [{"version": "4.20.45", "support_level": "production", "default": False}]
        with patch.object(matrix, "openshift_from_iserver", return_value=None), \
                patch.object(matrix, "openshift_from_public", return_value=public):
            versions, source = matrix.openshift_versions()
        self.assertEqual(versions[0]["version"], "4.20.45")
        self.assertIn("Red Hat", source)
        with patch.object(matrix, "openshift_from_iserver", return_value=None), \
                patch.object(matrix, "openshift_from_public", side_effect=OSError("offline")):
            versions, source = matrix.openshift_versions()
        self.assertEqual(versions[0]["version"], matrix.recommended("openshift"))
        self.assertTrue(source.startswith("matrix"))


class CiliumTests(unittest.TestCase):
    def test_index_lists_stable_cilium_releases_only(self):
        with patch.object(matrix, "_get", return_value=HELM_INDEX):
            self.assertEqual(matrix.cilium_from_index("https://registry.example/index.yaml"), ["1.18.15", "1.19.7", "1.19.9"])

    def test_token_goes_only_to_the_configured_registry_index(self):
        with patch.object(matrix, "_get", return_value=HELM_INDEX) as get:
            matrix.cilium_versions("https://registry.example/index.yaml", "secret")
            self.assertEqual(get.call_args.args[1], {"Authorization": "Bearer secret"})
            matrix.cilium_versions("", "secret")
            self.assertEqual(get.call_args.args[0], matrix.PUBLIC_CILIUM_INDEX)
            self.assertEqual(get.call_args.args[1], {})

    def test_versions_are_limited_to_supported_minors_with_a_matrix_fallback(self):
        with patch.object(matrix, "_get", return_value=HELM_INDEX):
            versions, _unused = matrix.cilium_versions("https://registry.example/index.yaml")
        self.assertEqual(versions, ["1.19.9", "1.19.7"])
        with patch.object(matrix, "_get", side_effect=OSError("unreachable")):
            versions, source = matrix.cilium_versions("https://registry.example/index.yaml")
        self.assertEqual(versions, matrix.VERSION_SUPPORT["cilium"]["tested"])
        self.assertTrue(source.startswith("matrix"))


class FloatingDefaultTests(unittest.TestCase):
    def check(self, items):
        with patch.object(matrix, "openshift_from_iserver", return_value=items):
            return matrix.check_version("openshift", matrix.LATEST_PRODUCTION)

    def test_supported_latest_production_passes(self):
        ok, message = self.check([{"version": "4.20.16", "default": True}, {"version": "4.20.9", "default": False}])
        self.assertTrue(ok)
        self.assertIn("4.20.16", message)

    def test_the_default_flag_wins_over_the_newest_version(self):
        ok, message = self.check([{"version": "4.21.2", "default": False}, {"version": "4.20.16", "default": True}])
        self.assertTrue(ok, message)

    def test_unsupported_latest_production_is_rejected_with_the_way_out(self):
        ok, message = self.check([{"version": "4.18.2", "default": True}])
        self.assertFalse(ok)
        self.assertIn("4.18.2", message)
        self.assertIn("cluster_version", message)

    def test_unresolvable_latest_production_passes_with_a_note(self):
        ok, message = self.check(None)
        self.assertTrue(ok)
        self.assertIn("cannot look up", message)

    def test_other_values_use_the_strict_check(self):
        self.assertFalse(matrix.check_version("openshift", "latest")[0])
        self.assertTrue(matrix.check_version("openshift", "4.20.46")[0])
        self.assertFalse(matrix.check_version("cilium", matrix.LATEST_PRODUCTION)[0])


LIFECYCLE = json.dumps({"data": [{"name": "Red Hat OpenShift Container Platform", "versions": [
    {"name": "5.0", "type": "Full Support", "phases": [
        {"name": "Full support", "start_date": "2026-11-03T00:00:00.000Z", "end_date": "2027-11-30T00:00:00.000Z"}]},
    {"name": "4.20", "type": "Maintenance Support", "phases": [
        {"name": "Full support", "start_date": "2025-10-21T00:00:00.000Z", "end_date": "2026-05-03T00:00:00.000Z"},
        {"name": "Maintenance support", "start_date": "2026-05-04T00:00:00.000Z", "end_date": "2027-04-21T00:00:00.000Z"},
        {"name": "Extended update support", "start_date": "N/A", "end_date": "N/A"}]},
    {"name": "4.17", "type": "End of life", "phases": []},
    {"name": "not-a-version", "type": "x", "phases": []}]}]}).encode()
TODAY = matrix.datetime.date(2026, 11, 17)


class ChannelTests(unittest.TestCase):
    def test_lifecycle_reports_the_current_phase_and_its_end(self):
        with patch.object(matrix, "_get", return_value=LIFECYCLE):
            cycle = matrix.lifecycle(TODAY)
        self.assertEqual(cycle["4.20"], {"support": "Maintenance Support", "phase": "Maintenance support",
                                         "until": "2027-04-21"})
        self.assertEqual(cycle["4.17"]["support"], "End of life")
        self.assertNotIn("not-a-version", cycle)

    def channels(self, iserver=None, public=None):
        with patch.object(matrix, "_get", return_value=LIFECYCLE), \
                patch.object(matrix, "openshift_from_iserver", return_value=iserver), \
                patch.object(matrix, "openshift_from_public", side_effect=public or (lambda minors: [
                    {"version": f"{minors[0]}.7"}, {"version": f"{minors[0]}.12"}])):
            return matrix.openshift_channels(today=TODAY)

    def test_one_row_per_active_channel_newest_first_with_the_supported_one_marked(self):
        rows, source = self.channels()
        self.assertEqual([row["minor"] for row in rows], ["5.0", "4.22", "4.21", "4.20", "4.19"])
        self.assertEqual(rows[0]["latest"], "5.0.12")
        self.assertEqual([row["supported"] for row in rows], [True] * 5)
        self.assertEqual(rows[3]["until"], "2027-04-21")
        self.assertIn("life cycle", source)

    def test_iserver_releases_win_over_the_public_graph(self):
        rows, source = self.channels(iserver=[{"version": "4.20.9", "default": False},
                                              {"version": "4.20.3", "default": False}])
        self.assertEqual(next(row["latest"] for row in rows if row["minor"] == "4.20"), "4.20.9")
        self.assertIn("iserver", source)

    def test_offline_falls_back_to_the_tested_versions(self):
        rows, source = matrix.openshift_channels(offline=True)
        self.assertEqual([(row["minor"], row["latest"]) for row in rows], [("4.20", "4.20.46")])
        self.assertTrue(source.startswith("matrix"))


class CheckTests(unittest.TestCase):
    def report(self, cycle, cilium=("1.19.7",), cilium_source="registry index"):
        with patch.object(matrix, "lifecycle", return_value=cycle), \
                patch.object(matrix, "openshift_channels", return_value=([{"minor": "4.20", "latest": "4.20.46"}], "x")), \
                patch.object(matrix, "cilium_versions", return_value=(list(cilium), cilium_source)):
            return matrix.check()

    def test_a_supported_channel_reaching_end_of_life_is_drift(self):
        report = self.report({"4.20": {"support": "End of life", "until": ""}})
        self.assertTrue(any("end of life" in problem for problem in report["problems"]))

    def test_newer_active_channels_are_noted_but_not_drift(self):
        report = self.report({"4.20": {"support": "Maintenance Support", "until": "2027-04-21"},
                              "5.1": {"support": "Full Support", "until": "2027-01-01"},
                              "4.19": {"support": "Maintenance Support", "until": "2026-12-17"}})
        self.assertEqual(report["problems"], [])
        self.assertEqual(len(report["notes"]), 1)
        self.assertIn("5.1", report["notes"][0])

    def test_newer_cilium_patches_are_drift_and_the_public_index_is_not_compared(self):
        cycle = {"4.20": {"support": "Maintenance Support", "until": ""}}
        self.assertEqual(len(self.report(cycle, ("1.19.9", "1.19.7"))["problems"]), 1)
        self.assertTrue(any("not offered" in p for p in self.report(cycle, ("1.19.9",))["problems"]))
        report = self.report(cycle, ("1.19.9",), "Isovalent public index (releases up to 1.18)")
        self.assertEqual(report["problems"], [])
        self.assertTrue(report["notes"])


if __name__ == "__main__":
    unittest.main()
