import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("probe_c880_oem_versions", SCRIPTS / "probe_c880_oem_versions.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture():
    entries = [{"Name": name, "Version": target, "Secret": "DO_NOT_EMIT"}
               for name, target in MODULE.TARGETS.items()]
    for index in range(8):
        entries += [{"Name": f"HGX_FW_GPU_{index}", "Version": MODULE.GPU_VBIOS},
                    {"Name": f"HGX_InfoROM_GPU_{index}", "Version": MODULE.GPU_INFOROM}]
    return {"Oem": {"Ami": {"FirmwareInventory": entries}}}


class OemVersionTests(unittest.TestCase):
    def test_all_instances_and_platform_targets_match_without_full_signoff(self):
        result = MODULE.summarize(fixture())
        self.assertTrue(result["all_listed_oob_versions_match"])
        self.assertEqual(len(result["gpu_instances"]), 8)
        self.assertFalse(result["full_upgrade_signoff"])
        self.assertFalse(result["huu_components_verified"])
        self.assertNotIn("DO_NOT_EMIT", str(result))

    def test_gpu_zero_is_not_enough(self):
        data = fixture()
        data["Oem"]["Ami"]["FirmwareInventory"] = data["Oem"]["Ami"]["FirmwareInventory"][:10]
        self.assertFalse(MODULE.summarize(data)["all_listed_oob_versions_match"])

    def test_wrong_inforom_on_one_instance_remains_visible(self):
        data = fixture()
        data["Oem"]["Ami"]["FirmwareInventory"][-1]["Version"] = "different"
        result = MODULE.summarize(data)
        self.assertFalse(result["gpu_instances"][7]["composite_matches_target"])
        self.assertTrue(result["gpu_instances"][7]["vbios_matches_target"])

    def test_duplicate_expected_instance_fails_closed(self):
        data = fixture()
        data["Oem"]["Ami"]["FirmwareInventory"].append(data["Oem"]["Ami"]["FirmwareInventory"][-1])
        with self.assertRaises(ValueError):
            MODULE.summarize(data)

    def test_missing_oem_inventory_fails_without_raw_response(self):
        for data in ({}, {"Oem": {"Ami": {"FirmwareInventory": None}}}):
            with self.assertRaises(ValueError):
                MODULE.summarize(data)

    def test_unrelated_identity_or_secret_fields_are_not_emitted(self):
        data = fixture()
        data["Oem"]["Ami"]["FirmwareInventory"].append({"Name": "private-identity", "Version": "DO_NOT_EMIT"})
        self.assertNotIn("DO_NOT_EMIT", str(MODULE.summarize(data)))
        self.assertNotIn("private-identity", str(MODULE.summarize(data)))


if __name__ == "__main__":
    unittest.main()
