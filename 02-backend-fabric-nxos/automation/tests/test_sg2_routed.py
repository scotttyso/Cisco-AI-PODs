import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("probe_sg2_routed", SCRIPTS / "probe_sg2_routed.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def sample():
    return ["BE-SG2-SP1\n", "!Command: show running-config bgp\nrouter bgp 65102\n  neighbor 21.0.0.2\n    password SECRET_NOT_TO_EMIT\n",
            "!Command: show running-config interface\ninterface Ethernet1/1/1\n  no switchport\n  ip address 21.0.0.1/31\n  no shutdown\n\ninterface Ethernet1/1/2\n  shutdown\n\ninterface Ethernet1/40/1\n  ip address 21.1.0.1/31\n"]


class RoutedTests(unittest.TestCase):
    def test_counts_observed_ports_only_and_never_emits_secrets_or_ips(self):
        result = MODULE.summarize_routed("BE-SG2-SP1", sample())
        self.assertTrue(result["router_bgp_configured"])
        self.assertEqual(result["distinct_ipv4_neighbor_addresses_all_vrfs"], 1)
        self.assertEqual(result["observed_lldp_ports_with_config_sections"], 2)
        self.assertEqual(result["observed_lldp_ports_with_ipv4_address"], 1)
        self.assertEqual(result["observed_lldp_ports_explicitly_shutdown"], 1)
        self.assertNotIn("SECRET", str(result))
        self.assertNotIn("21.0.", str(result))
        self.assertFalse(result["e2e_complete"])

    def test_empty_valid_config_is_not_a_health_pass(self):
        outputs = sample()
        outputs[1] = "!Command: show running-config bgp\n"
        outputs[2] = "!Command: show running-config interface\n"
        result = MODULE.summarize_routed("BE-SG2-SP1", outputs)
        self.assertFalse(result["router_bgp_configured"])
        self.assertEqual(result["observed_lldp_ports_with_ipv4_address"], 0)

    def test_bad_response_or_hostname_fails_closed(self):
        for index in (0, 1, 2):
            outputs = sample()
            outputs[index] = "Invalid command"
            with self.subTest(index=index), self.assertRaises(ValueError):
                MODULE.summarize_routed("BE-SG2-SP1", outputs)

    def test_duplicate_interface_rejected(self):
        outputs = sample()
        outputs[2] += "interface Ethernet1/1/1\n"
        with self.assertRaises(ValueError):
            MODULE.summarize_routed("BE-SG2-SP1", outputs)

    def test_observed_leaf_and_spine_port_sets_are_explicit(self):
        self.assertEqual(len(MODULE.observed_ports("BE-SG2-SP1")), 32)
        self.assertEqual(len(MODULE.observed_ports("BE-SG2-LF1")), 32)
        with self.assertRaises(ValueError):
            MODULE.observed_ports("BE-SP1")

    def test_transport_rejects_arbitrary_command_before_contact(self):
        with self.assertRaises(ValueError):
            MODULE._read_show_outputs(Path("/nonexistent"), "be-sg2-sp1", ("configure terminal",))


if __name__ == "__main__":
    unittest.main()
