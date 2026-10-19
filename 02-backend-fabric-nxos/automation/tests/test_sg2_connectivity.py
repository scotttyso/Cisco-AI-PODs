import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "probe_sg2_connectivity.py"
SPEC = importlib.util.spec_from_file_location("probe_sg2_connectivity", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def outputs(name="BE-SG2-SP1"):
    return [name + "\n",
            "Device ID Local Intf Hold-time Capability Port ID\nBE-SG2-LF1 Eth1/1/1 120 BR Eth1/14/1\nTotal entries displayed: 1\n",
            "Port Name Status Vlan Duplex Speed Type\nEth1/1/1 -- connected routed full 400G QSFP-DD\n",
            "IP Interface Status for VRF default\n10.0.0.1 Eth1/1/1 protocol-up/link-up/admin-up\n",
            "BGP summary information for VRF default\nNeighbor V AS MsgRcvd MsgSent TblVer InQ OutQ Up/Down State/PfxRcd\n10.0.0.2 4 65001 3 4 5 0 0 00:01:00 2\n"]


class ConnectivityTests(unittest.TestCase):
    def test_observes_link_and_peer_without_claiming_completion(self):
        result = MODULE.summarize("BE-SG2-SP1", outputs())
        self.assertEqual(result["lldp_links"][0]["state"], "connected")
        self.assertEqual(result["bgp_established_peer_rows"], 1)
        self.assertFalse(result["e2e_complete"])

    def test_hostname_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.summarize("BE-SG2-SP1", outputs("BE-SG2-SP2"))

    def test_zero_bgp_is_an_observation_not_health_pass(self):
        sample = outputs()
        sample[-1] = "BGP summary information for VRF default\n"
        result = MODULE.summarize("BE-SG2-SP1", sample)
        self.assertEqual(result["bgp_peer_rows"], 0)
        self.assertFalse(result["e2e_complete"])

    def test_unknown_or_failed_commands_rejected(self):
        for index in (1, 2, 4):
            sample = outputs()
            sample[index] = "unrecognized output"
            with self.subTest(index=index), self.assertRaises(ValueError):
                MODULE.summarize("BE-SG2-SP1", sample)

    def test_numeric_peer_state_is_required_for_established(self):
        sample = outputs()
        sample[-1] = sample[-1].replace("00:01:00 2", "00:01:00 Idle")
        self.assertEqual(MODULE.summarize("BE-SG2-SP1", sample)["bgp_established_peer_rows"], 0)

    def test_reciprocity_matches_both_ports_and_hostnames(self):
        first = MODULE.summarize("BE-SG2-SP1", outputs())
        second = {"hostname": "BE-SG2-LF1", "lldp_links": [
            {"local_port": "Eth1/14/1", "peer": "BE-SG2-SP1", "peer_port": "Eth1/1/1"}]}
        self.assertEqual(MODULE.reciprocal_summary([first, second])["reciprocal_physical_child_lanes"], 1)
        second["lldp_links"][0]["peer_port"] = "Eth1/2/1"
        self.assertEqual(MODULE.reciprocal_summary([first, second])["nonreciprocal_directed_links"], 2)


if __name__ == "__main__":
    unittest.main()
