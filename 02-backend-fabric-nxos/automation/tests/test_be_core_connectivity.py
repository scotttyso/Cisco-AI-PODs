import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_be_core_connectivity.py"
SPEC = importlib.util.spec_from_file_location("be_core", SCRIPT)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
M.FABRICS = {
    "backend": ("EXAMPLE-BE-SPINE-1", "EXAMPLE-BE-SPINE-2", "EXAMPLE-BE-LEAF-1", "EXAMPLE-BE-LEAF-2"),
    "backend_800g": ("EXAMPLE-BE-800G-SPINE-1", "EXAMPLE-BE-800G-SPINE-2", "EXAMPLE-BE-800G-LEAF-1", "EXAMPLE-BE-800G-LEAF-2"),
}
M.FABRIC_NAMES = {"backend": "AIPOD-Backend", "backend_800g": "AIPOD-Backend-800G"}
M.SWITCH_ROLES = {host: ("spine" if "SPINE" in host else "leaf") for hosts in M.FABRICS.values() for host in hosts}
M.ALL_NAMES = {host for hosts in M.FABRICS.values() for host in hosts}
M.SWITCH_HOST_VARS = {}


def sample(name="EXAMPLE-BE-SPINE-1"):
    return [name + "\n", "Device ID Local Intf Hold-time Capability Port ID\n"
            "EXAMPLE-BE-LEAF-1 Eth1/1 120 BR Eth1/33\nTotal entries displayed: 1\n",
            "Port Name Status Vlan Duplex Speed Type\nEth1/1 -- connected routed full 400G QSFP-DD\n"]


def full_fabric(fabric="backend"):
    names = M.FABRICS[fabric]
    observations = [{"hostname": n, "links": [], "ports": {}} for n in names]
    expected = set()
    for si, s in enumerate(names[:2]):
        for li, l in enumerate(names[2:]):
            for lane in (1, 2):
                sp, lp = f"Eth1/{li * 2 + lane}", f"Eth1/{33 + si * 2 + lane}"
                expected.add(M.cable(s, sp, l, lp))
                for a, ap, b, bp in ((s, sp, l, lp), (l, lp, s, sp)):
                    o = next(o for o in observations if o["hostname"] == a)
                    o["links"].append({"local_port": ap, "peer": b, "peer_port": bp})
                    o["ports"][ap] = {"state": "connected", "speed": "400G"}
    return observations, expected


class ParserTests(unittest.TestCase):
    def test_parse_identity_status_speed(self):
        o = M.parse_outputs("EXAMPLE-BE-SPINE-1", sample())
        self.assertEqual(o["ports"]["Eth1/1"], {"state": "connected", "speed": "400G"})

    def test_port_aliases(self):
        for value in ("e1/1/2", "Ethernet1/1/2", "Eth1/1/2"):
            self.assertEqual(M.port(value), "Eth1/1/2")

    def test_hostname_mismatch(self):
        with self.assertRaises(ValueError):
            M.parse_outputs("EXAMPLE-BE-SPINE-1", sample("EXAMPLE-BE-SPINE-2"))

    def test_count_mismatch(self):
        bodies = sample()
        bodies[1] = bodies[1].replace("displayed: 1", "displayed: 2")
        with self.assertRaises(ValueError):
            M.parse_outputs("EXAMPLE-BE-SPINE-1", bodies)

    def test_duplicate_neighbor(self):
        bodies = sample()
        bodies[1] = bodies[1].replace("Total entries", "EXAMPLE-BE-LEAF-2 Eth1/1 120 BR Eth1/33\nTotal entries").replace("displayed: 1", "displayed: 2")
        with self.assertRaises(ValueError):
            M.parse_outputs("EXAMPLE-BE-SPINE-1", bodies)

    def test_unparsed_row_fails_closed(self):
        bodies = sample()
        bodies[1] = bodies[1].replace("EXAMPLE-BE-LEAF-1 Eth1/1 120 BR Eth1/33", "EXAMPLE-BE-LEAF-1")
        with self.assertRaises(ValueError):
            M.parse_outputs("EXAMPLE-BE-SPINE-1", bodies)

    def test_cli_error_or_pagination(self):
        for text in ("Invalid command", "--More--", "Authorization failed"):
            bodies = sample()
            bodies[2] += text
            with self.assertRaises(ValueError):
                M.parse_outputs("EXAMPLE-BE-SPINE-1", bodies)

    def test_zero_lldp_is_valid_observation(self):
        bodies = sample()
        bodies[1] = "Device ID Local Intf Hold-time Capability Port ID\nTotal entries displayed: 0\n"
        self.assertEqual(M.parse_outputs("EXAMPLE-BE-SPINE-1", bodies)["links"], [])

    def test_unknown_switch_identity_not_retained(self):
        bodies = sample()
        bodies[1] = bodies[1].replace("EXAMPLE-BE-LEAF-1", "PRIVATE-FDO0000000123")
        o = M.parse_outputs("EXAMPLE-BE-SPINE-1", bodies)
        self.assertEqual(o["links"][0]["peer"], "outside_be_core")
        self.assertNotIn("PRIVATE", str(o))

    def test_unknown_status_retained_as_unverified(self):
        bodies = sample()
        bodies[2] = bodies[2].replace("connected", "mystery")
        self.assertEqual(M.parse_outputs("EXAMPLE-BE-SPINE-1", bodies)["ports"]["Eth1/1"]["state"], "unverified")

    def test_truncated_absent_transceiver_state(self):
        bodies = sample()
        bodies[2] = bodies[2].replace("connected", "xcvrAbsen")
        self.assertEqual(M.parse_outputs("EXAMPLE-BE-SPINE-1", bodies)["ports"]["Eth1/1"]["state"], "xcvrAbsent")

    def test_unknown_spare_state_preserves_core(self):
        bodies = sample()
        bodies[2] += "Eth1/64 -- unknownState 1 auto auto --\n"
        result = M.parse_outputs("EXAMPLE-BE-SPINE-1", bodies)
        self.assertEqual(result["ports"]["Eth1/1"]["state"], "connected")
        self.assertEqual(result["ports"]["Eth1/64"]["state"], "unverified")

    def test_wrapped_neighbor_name(self):
        bodies = sample()
        bodies[1] = bodies[1].replace("EXAMPLE-BE-LEAF-1 Eth1/1", "EXAMPLE-BE-LEAF-1\nEth1/1")
        self.assertEqual(M.parse_outputs("EXAMPLE-BE-SPINE-1", bodies)["links"][0]["peer"], "EXAMPLE-BE-LEAF-1")

    def test_wrapped_unknown_name_not_retained(self):
        bodies = sample()
        bodies[1] = bodies[1].replace("EXAMPLE-BE-LEAF-1 Eth1/1", "PRIVATE-LONG-IDENTIFIER\nEth1/1")
        self.assertNotIn("PRIVATE", str(M.parse_outputs("EXAMPLE-BE-SPINE-1", bodies)))

    def test_dangling_wrapped_name_rejected(self):
        bodies = sample()
        bodies[1] = bodies[1].replace("EXAMPLE-BE-LEAF-1 Eth1/1 120 BR Eth1/33", "EXAMPLE-BE-LEAF-1")
        with self.assertRaises(ValueError):
            M.parse_outputs("EXAMPLE-BE-SPINE-1", bodies)


class GateTests(unittest.TestCase):
    def test_cloud_pass_without_bgp(self):
        obs, _ = full_fabric()
        result = M.evaluate("backend", obs)
        self.assertEqual(result["physical_gate"], "PASS")
        self.assertEqual(result["reciprocal_connections"], 8)
        self.assertFalse(result["bgp_required"])

    def test_exact_backend_800g_plan_pass(self):
        obs, expected = full_fabric("backend_800g")
        self.assertEqual(M.evaluate("backend_800g", obs, expected)["physical_gate"], "PASS")

    def test_missing_cable_detected_even_with_port_up(self):
        obs, expected = full_fabric("backend_800g")
        for o in obs:
            o["links"] = [l for l in o["links"] if M.cable(o["hostname"], l["local_port"], l["peer"], l["peer_port"]) != next(iter(expected))]
        result = M.evaluate("backend_800g", obs, expected)
        self.assertEqual(result["physical_gate"], "FAIL")
        self.assertIn("expected_cable_missing_or_not_reciprocal", str(result["issues"]))

    def test_down_expected_port_without_lldp(self):
        obs, expected = full_fabric("backend_800g")
        endpoint = next(iter(expected))[0]
        o = next(o for o in obs if o["hostname"] == endpoint[0])
        o["ports"][endpoint[1]]["state"] = "notconnect"
        self.assertIn("port_down", str(M.evaluate("backend_800g", obs, expected)["issues"]))

    def test_one_way_neighbor(self):
        obs, _ = full_fabric()
        obs[0]["links"].pop()
        self.assertIn("one_way_lldp", str(M.evaluate("backend", obs)["issues"]))

    def test_missing_switch_not_success(self):
        obs, _ = full_fabric()
        self.assertEqual(M.evaluate("backend", obs[:-1])["physical_gate"], "INCOMPLETE")

    def test_failed_switch_not_reported_as_missing_cables(self):
        obs, expected = full_fabric("backend_800g")
        result = M.evaluate("backend_800g", obs[:-1], expected)
        self.assertEqual(result["physical_gate"], "INCOMPLETE")
        self.assertFalse(result["issues"])

    def test_cabling_plan_is_optional_for_any_fabric(self):
        obs, _ = full_fabric("backend_800g")
        self.assertEqual(M.evaluate("backend_800g", obs)["physical_gate"], "PASS")

    def test_duplicate_observation_rejected(self):
        obs, _ = full_fabric()
        with self.assertRaises(ValueError):
            M.evaluate("backend", obs + [obs[0]])

    def test_unknown_port_state_not_success(self):
        obs, _ = full_fabric()
        obs[0]["ports"].clear()
        self.assertEqual(M.evaluate("backend", obs)["physical_gate"], "INCOMPLETE")

    def test_unknown_core_state_never_passes(self):
        obs, _ = full_fabric()
        next(iter(obs[0]["ports"].values()))["state"] = "unverified"
        self.assertEqual(M.evaluate("backend", obs)["physical_gate"], "INCOMPLETE")

    def test_cross_fabric_neighbor(self):
        obs, _ = full_fabric()
        obs[0]["links"][0]["peer"] = "EXAMPLE-BE-800G-LEAF-1"
        self.assertIn("unexpected_core_peer", str(M.evaluate("backend", obs)["issues"]))

    def test_spare_down_ports_ignored(self):
        obs, _ = full_fabric()
        obs[0]["ports"]["Eth1/64"] = {"state": "notconnect", "speed": "auto"}
        self.assertEqual(M.evaluate("backend", obs)["physical_gate"], "PASS")

    def test_server_facing_leaf_links_ignored(self):
        obs, _ = full_fabric()
        obs[2]["links"].append({"local_port": "Eth1/2", "peer": "outside_be_core", "peer_port": None})
        self.assertEqual(M.evaluate("backend", obs)["physical_gate"], "PASS")

    def test_non_core_spine_uplinks_not_invented_as_faults(self):
        obs, _ = full_fabric()
        obs[0]["links"].append({"local_port": "Eth1/65", "peer": "outside_be_core", "peer_port": None})
        self.assertEqual(M.evaluate("backend", obs)["physical_gate"], "PASS")

    def test_speed_mismatch(self):
        obs, _ = full_fabric()
        next(iter(obs[0]["ports"].values()))["speed"] = "100G"
        self.assertIn("link_speed_mismatch", str(M.evaluate("backend", obs)["issues"]))

    def test_swapped_ports_fail_exact_map(self):
        obs, expected = full_fabric("backend_800g")
        for o in obs:
            for l in o["links"]:
                if o["hostname"] == "EXAMPLE-BE-800G-SPINE-1":
                    l["local_port"] = "Eth1/99" if l["local_port"] == "Eth1/1" else l["local_port"]
                if l["peer"] == "EXAMPLE-BE-800G-SPINE-1" and l["peer_port"] == "Eth1/1":
                    l["peer_port"] = "Eth1/99"
        obs[0]["ports"]["Eth1/99"] = obs[0]["ports"]["Eth1/1"]
        result = M.evaluate("backend_800g", obs, expected)
        self.assertEqual(result["physical_gate"], "FAIL")
        self.assertIn("unexpected_cable", str(result["issues"]))


class PlanSafetyTests(unittest.TestCase):
    def write_plan(self, directory, duplicate=False):
        _, expected = full_fabric("backend_800g")
        text = "Fabric,Source switch,Source port,Destination switch,Destination port\n"
        rows = [f"AIPOD-Backend-800G,{a},{ap},{b},{bp}\n" for (a, ap), (b, bp) in sorted(expected)]
        path = Path(directory) / "plan.csv"
        path.write_text(text + "".join(rows) + (rows[0] if duplicate else ""), encoding="utf-8-sig")
        return path

    def test_plan_hash_and_explicit_endpoints(self):
        with tempfile.TemporaryDirectory() as d:
            edges, source = M.load_cabling_plan(self.write_plan(d), "backend_800g")
            self.assertEqual(len(edges), 8)
            self.assertEqual(len(source["sha256"]), 64)

    def test_duplicate_plan_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                M.load_cabling_plan(self.write_plan(d, True), "backend_800g")

    def test_out_of_scope_rejected_before_network(self):
        with patch.object(M.paramiko, "SSHClient") as client:
            with self.assertRaises(ValueError):
                M.read_switch(Path("/missing"), "FE-SP1", "backend")
            client.assert_not_called()

    def test_encrypted_vault_is_decrypted_without_git_ignore(self):
        host = "EXAMPLE-BE-SPINE-1"
        switch = {"hostname": host, "fabric_key": "backend", "role": "spine", "mgmt_ip": "192.0.2.10",
                  "username": "admin", "pass_ref": "SWITCH_PASSWORD"}
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d) / "vault.yaml"
            vault.write_text("$ANSIBLE_VAULT;1.1;AES256\n00\n")
            vault.chmod(0o600)
            decrypted = M.subprocess.CompletedProcess([], 0, "vault_switch_password: Secret-1\n", "")
            with patch.dict(M.SWITCH_HOST_VARS, {host: switch}), \
                    patch.object(M.subprocess, "run", return_value=decrypted) as run, \
                    patch.object(M.paramiko, "SSHClient") as client:
                client.return_value.connect.side_effect = OSError("stop")
                with self.assertRaises(OSError):
                    M.read_switch(Path(d), host, "backend", vault_file=vault)
            self.assertEqual(run.call_args.args[0][:2], ["ansible-vault", "view"])
            self.assertEqual(client.return_value.connect.call_args.kwargs["password"], "Secret-1")

    def test_commands_are_only_three_physical_reads(self):
        self.assertEqual(M.COMMANDS, ("show switchname", "show lldp neighbors", "show interface status"))
        self.assertGreaterEqual(M.SPACING, 3)

    def test_existing_report_never_overwritten_or_live_read(self):
        with tempfile.TemporaryDirectory() as d:
            prefix = Path(d) / "report"
            prefix.with_suffix(".json").write_text("keep")
            with patch("sys.argv", [str(SCRIPT), d, "--fabric", "backend", "--report-prefix", str(prefix)]), patch.object(M, "read_switch") as read, patch("sys.stdout", new=io.StringIO()):
                self.assertEqual(M.main(), 2)
                read.assert_not_called()
            self.assertEqual(prefix.with_suffix(".json").read_text(), "keep")

    def test_strict_inventory_blocks_deployment_without_physical_faults(self):
        with tempfile.TemporaryDirectory() as d:
            plan = self.write_plan(d)
            obs, _ = full_fabric("backend_800g")
            for o in obs:
                o["inventory_core_ports"] = []
            def fake_read(inv, name, fabric):
                return next(o for o in obs if o["hostname"] == name)
            args = [str(SCRIPT), d, "--fabric", "backend_800g", "--plan", "backend_800g=" + str(plan), "--require-inventory-match", "--report-prefix", str(Path(d) / "report")]
            with patch("sys.argv", args), patch.object(M, "load_inventory", return_value=Path(d)), patch.object(M, "read_switch", side_effect=fake_read), patch.object(M.time, "sleep"), patch("sys.stdout", new=io.StringIO()):
                self.assertEqual(M.main(), 1)
            import json
            result = json.loads((Path(d) / "report.json").read_text())
            self.assertEqual(result["fabrics"][0]["physical_gate"], "PASS")
            self.assertFalse(result["inventory_matches_cabling_plans"])


class DeploymentCliTests(unittest.TestCase):
    def run_gate(self, fabric="backend", change=None, extra=()):
        with tempfile.TemporaryDirectory() as d:
            obs, expected = full_fabric(fabric)
            for o in obs:
                o["inventory_core_ports"] = sorted(p for edge in expected for n, p in edge if n == o["hostname"])
            if change:
                change(obs)
            args = [str(SCRIPT), d, "--gate-json", "--require-inventory-match", "--fabrics", fabric, *extra]
            if fabric == "backend_800g":
                plan = PlanSafetyTests().write_plan(d)
                args += ["--plan", "backend_800g=" + str(plan)]
            stream = io.StringIO()
            def fake_read(inv, name, selected, **kwargs):
                return next(o for o in obs if o["hostname"] == name)
            with patch("sys.argv", args), patch.object(M, "load_inventory", return_value=Path(d)), patch.object(M, "read_switch", side_effect=fake_read) as read, patch.object(M.time, "sleep") as pause, patch("sys.stdout", stream):
                code = M.main()
            return code, json.loads(stream.getvalue()), read.call_args_list, pause.call_args_list

    def test_gate_json_scopes_reads_and_returns_fresh_pass(self):
        code, result, calls, pauses = self.run_gate()
        self.assertEqual(code, 0)
        self.assertTrue(result["deployment_ready"])
        self.assertEqual([c.args[1] for c in calls], list(M.FABRICS["backend"]))
        self.assertEqual(len(pauses), 3)
        self.assertTrue(all(c.args == (M.SPACING,) for c in pauses))
        self.assertFalse(result["mutations_performed"])

    def test_backend_800g_gate_requires_inventory_and_exact_cables(self):
        code, result, _, _ = self.run_gate("backend_800g")
        self.assertEqual(code, 0)
        self.assertTrue(result["deployment_ready"])
        self.assertTrue(result["require_inventory_match"])

    def test_stale_inventory_is_not_a_physical_fault_but_holds_deployment(self):
        code, result, _, _ = self.run_gate("backend_800g", lambda obs: obs[0].update(inventory_core_ports=[]))
        self.assertEqual(code, 1)
        self.assertEqual(result["fabrics"][0]["physical_gate"], "PASS")
        self.assertFalse(result["deployment_ready"])

    def test_down_port_holds_deployment(self):
        def down(obs):
            next(iter(obs[0]["ports"].values()))["state"] = "notconnect"
        code, result, _, _ = self.run_gate(change=down)
        self.assertEqual(code, 1)
        self.assertFalse(result["deployment_ready"])

    def test_unknown_port_holds_deployment(self):
        code, result, _, _ = self.run_gate(change=lambda obs: obs[0]["ports"].clear())
        self.assertEqual(code, 2)
        self.assertFalse(result["deployment_ready"])

    def test_duplicate_targets_fail_before_any_switch_read(self):
        args = [str(SCRIPT), "/missing", "--gate-json", "--fabrics", "backend", "backend"]
        stream = io.StringIO()
        with patch("sys.argv", args), patch.object(M, "read_switch") as read, patch("sys.stdout", stream):
            self.assertEqual(M.main(), 2)
            read.assert_not_called()
        self.assertFalse(json.loads(stream.getvalue())["deployment_ready"])

    def test_unplanned_fabric_is_validated_from_live_topology(self):
        obs, _ = full_fabric("backend_800g")
        def fake_read(inv, name, fabric):
            return next(item for item in obs if item["hostname"] == name)
        args = [str(SCRIPT), "/inventory", "--gate-json", "--fabrics", "backend_800g"]
        stream = io.StringIO()
        with patch("sys.argv", args), patch.object(M, "load_inventory", return_value=Path("/inventory")), patch.object(M, "read_switch", side_effect=fake_read), patch.object(M.time, "sleep"), patch("sys.stdout", stream):
            self.assertEqual(M.main(), 0)
        self.assertTrue(json.loads(stream.getvalue())["deployment_ready"])

    def test_selected_vault_path_is_forwarded_without_secret_arguments(self):
        _, _, calls, _ = self.run_gate(extra=("--vault-file", "/site/restricted/vault.yml"))
        self.assertTrue(all(c.kwargs == {"vault_file": Path("/site/restricted/vault.yml")} for c in calls))

    def test_read_failure_is_sanitized_and_never_passes(self):
        stream = io.StringIO()
        args = [str(SCRIPT), "/site", "--gate-json", "--fabrics", "backend"]
        with patch("sys.argv", args), patch.object(M, "read_switch", side_effect=RuntimeError("SECRET-RAW-RESPONSE")), patch.object(M.time, "sleep"), patch("sys.stdout", stream):
            self.assertEqual(M.main(), 2)
        self.assertNotIn("SECRET", stream.getvalue())
        self.assertFalse(json.loads(stream.getvalue())["deployment_ready"])


if __name__ == "__main__":
    unittest.main()
