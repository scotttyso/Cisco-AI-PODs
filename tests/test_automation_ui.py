import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import automation_ui as web


class AutomationUiTests(unittest.TestCase):
    def test_password_change(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(web, "AUTH_FILE", Path(folder) / "users.json"):
            users = {"test": web.password_hash("original-password-123"), "other": web.password_hash("other-password-123")}
            web.write_private_file(web.AUTH_FILE, json.dumps(users))
            for current, new, confirmation in (("wrong", "replacement-password-123", "replacement-password-123"),
                                               ("original-password-123", "short", "short"),
                                               ("original-password-123", "replacement-password-123", "mismatch")):
                with self.assertRaises(ValueError):
                    web.change_password("test", current, new, confirmation)
                self.assertEqual(json.loads(web.AUTH_FILE.read_text()), users)
            web.change_password("test", "original-password-123", "replacement-password-123", "replacement-password-123")
            updated = json.loads(web.AUTH_FILE.read_text())
            self.assertTrue(web.password_matches("replacement-password-123", updated["test"]))
            self.assertFalse(web.password_matches("original-password-123", updated["test"]))
            self.assertEqual(users["other"], updated["other"])
            self.assertEqual(web.AUTH_FILE.stat().st_mode & 0o777, 0o600)

    def test_media_paths_and_listing(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(web, "MEDIA_DIR", Path(folder)):
            for name in ("../outside.iso", "/tmp/outside.iso", "folder/file.iso", "folder\\file.iso", ".upload.part", ""):
                with self.assertRaises(ValueError):
                    web.media_path(name)
            (web.MEDIA_DIR / "test.iso").write_bytes(b"test")
            (web.MEDIA_DIR / ".upload.part").write_bytes(b"temporary")
            (web.MEDIA_DIR / "subfolder").mkdir()
            (web.MEDIA_DIR / "link.iso").symlink_to(web.MEDIA_DIR / "test.iso")
            with self.assertRaises(ValueError):
                web.media_path("link.iso")
            self.assertEqual([row["name"] for row in web.list_media()], ["test.iso"])

    def test_list_inputs(self):
        self.assertEqual(web.split_values("192.0.2.1, 192.0.2.2\n192.0.2.3"),
                         ["192.0.2.1", "192.0.2.2", "192.0.2.3"])

    def test_manual_inventory_defaults(self):
        first = web.new_inventory_row([])
        second = web.new_inventory_row([first])
        self.assertEqual(first["ip"], "198.18.0.1")
        self.assertEqual(second["ip"], "198.18.0.2")
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["mac"], "")
        self.assertEqual(web.new_inventory_row([dict(ip=f"198.18.0.{position}") for position in range(1, 255)])["ip"], "")

    def test_duplicate_inventory_rows_copies_selected_rows_with_new_ids(self):
        rows = [
            dict(id="manual", hostname="node1", ip="198.18.0.10", mac="00:00:00:00:00:01",
                 pid="UCSX-TEST", serial_number="SERIAL-1", pool_ip=False),
            dict(id="pool", hostname="blade1", ip="", mac="00:00:00:00:00:02",
                 pid="UCSX-BLADE", serial_number="SERIAL-2", pool_ip=True),
        ]

        result = web.duplicate_inventory_rows(rows, ["manual", "pool"])

        self.assertEqual([row["id"] for row in result][::2], ["manual", "pool"])
        self.assertEqual(result[0], rows[0])
        self.assertEqual(result[2], rows[1])
        for original, duplicate in ((result[0], result[1]), (result[2], result[3])):
            self.assertNotEqual(original["id"], duplicate["id"])
            self.assertEqual({key: value for key, value in duplicate.items() if key != "id"},
                             {key: value for key, value in original.items() if key != "id"})
        self.assertEqual(result[3]["ip"], "")
        self.assertTrue(result[3]["pool_ip"])
        self.assertEqual(rows[0]["id"], "manual")

    def test_duplicate_inventory_rows_rejects_missing_or_stale_selection(self):
        rows = [dict(id="row-1", hostname="node1")]
        for selected_ids in ([], ["missing"], ["row-1", "row-1"]):
            with self.subTest(selected_ids=selected_ids), self.assertRaises(ValueError):
                web.duplicate_inventory_rows(rows, selected_ids)

    def test_array_input_values(self):
        field = object.__new__(web.ArrayInput)
        from types import SimpleNamespace
        field.fields = [SimpleNamespace(value=" 192.0.2.1 "), SimpleNamespace(value=""),
                        SimpleNamespace(value="  "), SimpleNamespace(value="192.0.2.2")]
        self.assertEqual(field.value, ["192.0.2.1", "192.0.2.2"])

    def test_bulk_inventory_display_order_and_optional_fields(self):
        rows = [dict(id=str(index), hostname=f"old{index}", ip=f"192.0.2.{index}", role="",
                     mac=f"00:00:00:00:00:0{index}") for index in range(1, 5)]
        role = next(iter(web.seeds.ROLES))
        result = web.bulk_inventory_rows(rows, ["3", "1"], "node09.lab2.example.com", "192.0.2.254", role)
        self.assertEqual([row["id"] for row in result], ["1", "2", "3", "4"])
        self.assertEqual(result[2]["hostname"], "node09.lab2.example.com")
        self.assertEqual(result[0]["hostname"], "node10.lab2.example.com")
        self.assertEqual(result[2]["ip"], "192.0.2.254")
        self.assertEqual(result[0]["ip"], "192.0.2.255")
        self.assertEqual(result[0]["role"], role)
        self.assertEqual(result[1], rows[1])
        self.assertEqual(result[0]["mac"], rows[0]["mac"])
        self.assertEqual(rows[0]["hostname"], "old1")
        role_only = web.bulk_inventory_rows(rows, ["2", "4"], role=role)
        self.assertEqual(role_only[1], dict(rows[1], role=role))
        ip_only = web.bulk_inventory_rows(rows, ["2", "4"], ip="2001:db8::ff")
        self.assertEqual(ip_only[3]["ip"], "2001:db8::100")
        self.assertEqual(ip_only[3]["hostname"], "old4")
        host_only = web.bulk_inventory_rows(rows, ["1", "2"], hostname="node099")
        self.assertEqual(host_only[1]["hostname"], "node100")
        self.assertEqual(host_only[1]["ip"], rows[1]["ip"])

    def test_bulk_inventory_rejects_invalid_changes_atomically(self):
        rows = [dict(id="a", hostname="original", ip="192.0.2.1"),
                dict(id="b", hostname="node02", ip="192.0.2.2")]
        for selected, fields in (
                ([], {"role": next(iter(web.seeds.ROLES))}),
                (["a"], {}),
                (["missing"], {"hostname": "node01"}),
                (["a", "a"], {"hostname": "node01"}),
                (["a", "b"], {"hostname": "node"}),
                (["a", "b"], {"hostname": "node.lab2.example.com"}),
                (["a"], {"hostname": "bad_name"}),
                (["a"], {"pool_ip": True, "ip": "192.0.2.2"}),
                (["a"], {"ip": "not an IP"}),
                (["a", "b"], {"ip": "255.255.255.255"}),
                (["a"], {"role": "invalid-role"})):
            with self.subTest(selected=selected, fields=fields), self.assertRaises(ValueError):
                web.bulk_inventory_rows(rows, selected, **fields)
            self.assertEqual(rows[0]["hostname"], "original")
            self.assertEqual(rows[0]["ip"], "192.0.2.1")

    def test_bulk_allows_temporary_duplicates_for_later_validation(self):
        rows = [dict(id=str(index), hostname="unknown", ip=f"198.18.0.{index}")
                for index in range(1, 7)]
        result = web.bulk_inventory_rows(rows, ["1", "2"], hostname="ucsai-1", ip="198.18.0.5")
        self.assertEqual([(row["hostname"], row["ip"]) for row in result[:2]],
                         [("ucsai-1", "198.18.0.5"), ("ucsai-2", "198.18.0.6")])
        self.assertEqual(result[2:], rows[2:])

    def test_pool_bulk_clear_and_skip_ip_sequence(self):
        rows = [dict(id="a", hostname="node1", ip="198.18.0.1"),
                dict(id="b", hostname="blade1", ip="", pool_ip=True),
                dict(id="c", hostname="node2", ip="198.18.0.3")]
        result = web.bulk_inventory_rows(rows, ["a", "b", "c"], "ucsai-1", "198.18.0.5")
        self.assertEqual([row["ip"] for row in result], ["198.18.0.5", "", "198.18.0.6"])
        self.assertEqual([row["hostname"] for row in result], ["ucsai-1", "ucsai-2", "ucsai-3"])
        pooled = web.bulk_inventory_rows(rows, ["a", "c"], pool_ip=True)
        self.assertTrue(all(row["pool_ip"] for row in pooled))
        self.assertTrue(all(row["ip"] == "" for row in pooled))
        manual = web.bulk_inventory_rows(pooled, ["a", "c"], ip="198.18.0.5", pool_ip=False)
        self.assertEqual([row["ip"] for row in manual], ["198.18.0.5", "", "198.18.0.6"])

    def test_hgx_bmc_password_is_required_only_when_the_inventory_has_hgx_nodes(self):
        from types import SimpleNamespace
        from aipod_webui import pages

        fabric = {"hostname": "fi-a", "ip": "10.0.0.1", "pid": "UCS-FI-6454", "role": "fabric-interconnect",
                  "serial_number": "A"}
        hgx = {"hostname": "hgx1", "ip": "10.0.0.2", "pid": "HGX-C885A", "role": "hgx-node", "serial_number": "B"}

        def handle(rows):
            store = SimpleNamespace(inventory=lambda: rows, page_state=lambda key: {})
            return SimpleNamespace(context=SimpleNamespace(store=store), models=lambda: [])

        self.assertEqual(pages.hgx_secrets(handle([fabric]), only_used=True), [])
        self.assertEqual(len(pages.hgx_secrets(handle([fabric, hgx]), only_used=True)), 1)
        # The HGX page itself always offers the default password.
        self.assertEqual([item.label for item in pages.hgx_secrets(handle([fabric]))], ["HGX BMC password"])

    def test_compute_credentials_do_not_block_the_openshift_install(self):
        from types import SimpleNamespace
        from aipod_webui import pages

        rows = [{"hostname": "fi-a", "ip": "10.0.0.1", "pid": "UCS-FI-6454", "role": "fabric-interconnect",
                 "serial_number": "A"},
                {"hostname": "hgx1", "ip": "10.0.0.2", "pid": "HGX-C885A", "role": "hgx-node", "serial_number": "B"}]
        store = SimpleNamespace(inventory=lambda: rows, page_state=lambda key: {})
        handle = SimpleNamespace(context=SimpleNamespace(store=store), models=lambda: [])
        fields = pages.ocp_cluster_secrets(handle)
        self.assertTrue(fields)
        self.assertTrue(all(item.optional for item in fields))

    def test_cilium_registry_host_validation(self):
        from aipod_webui import custom_pages

        for good in ("registry.isovalent.com", "registry.example.com:5000", "localhost"):
            self.assertEqual(custom_pages.registry_host_problem(good), "", good)
        for bad in ("", "https://registry.example.com", "registry.example.com/path", "bad host", "-bad.example.com"):
            self.assertTrue(custom_pages.registry_host_problem(bad), bad)

    def test_cilium_registry_command_uses_the_saved_host(self):
        from types import SimpleNamespace
        from aipod_webui import pages

        ui = SimpleNamespace(python=lambda: "python", repository=Path("/repo"))

        def command(state):
            return pages.cilium_registry(SimpleNamespace(ui=ui, state=state))[0]

        default = command({})
        self.assertEqual(default[default.index("--registry") + 1], "registry.isovalent.com")
        custom = command({"registry": "registry.example.com"})
        self.assertEqual(custom[custom.index("--registry") + 1], "registry.example.com")
        self.assertNotIn("token", " ".join(custom).lower().replace("isovalent", ""))
        with self.assertRaises(ValueError):
            command({"registry": "https://registry.example.com"})

    def test_install_checks_the_cilium_registry_first_only_when_cilium_is_configured(self):
        from types import SimpleNamespace
        from aipod_webui import pages

        with tempfile.TemporaryDirectory() as folder:
            host_vars = Path(folder)
            (host_vars / "openshift").mkdir()
            ui = SimpleNamespace(python=lambda: "python", repository=Path("/repo"), host_vars_dir=host_vars)
            rc = SimpleNamespace(ui=ui, state={})
            install = pages.with_cilium_registry_check(lambda _rc: [["install"]])

            self.assertEqual(install(rc), [["install"]])
            install_file = host_vars / "openshift/install.ezai.yaml"
            install_file.write_text("openshift:\n  install:\n    bare_metal:\n      cluster_networking:\n"
                                    "        container_network_interface: OVNKubernetes\n")
            self.assertEqual(install(rc), [["install"]])
            install_file.write_text("openshift:\n  install:\n    bare_metal:\n      cluster_networking:\n"
                                    "        container_network_interface: Cilium\n"
                                    "        container_network_version: 1.19.7\n")
            commands = install(rc)
            self.assertEqual(len(commands), 2)
            self.assertIn("isovalent-check", commands[0])
            self.assertEqual(commands[1], ["install"])

    def test_version_choices_mark_the_recommended_and_keep_an_unsupported_current_value(self):
        from aipod_webui import custom_pages

        options = custom_pages.version_choices(["4.20.46", "4.20.16"], "4.20.16", "4.19.5", "the-latest-production-version")
        self.assertEqual(list(options)[0], "the-latest-production-version")
        self.assertEqual(options["4.20.16"], "4.20.16 (recommended)")
        self.assertEqual(options["4.19.5"], "4.19.5 (not supported)")
        self.assertEqual(custom_pages.version_choices(["1.19.7"], "1.19.7"), {"1.19.7": "1.19.7 (recommended)"})

    def test_channel_choices_offer_the_latest_stable_of_supported_channels_only(self):
        from aipod_webui import custom_pages

        channels = [{"minor": "4.21", "latest": "4.21.42", "supported": False},
                    {"minor": "4.20", "latest": "4.20.46", "supported": True}]
        ok = lambda version: version.startswith("4.20.")  # noqa: E731
        options = custom_pages.channel_choices(channels, "4.20.16", "the-latest-production-version", ok)
        self.assertEqual(list(options), ["the-latest-production-version", "4.20.46", "4.20.16"])
        self.assertEqual(options["4.20.46"], "4.20.46 (latest stable 4.20)")
        self.assertEqual(options["4.20.16"], "4.20.16 (older patch)")
        self.assertEqual(custom_pages.channel_choices(channels, "4.19.5", "", ok)["4.19.5"], "4.19.5 (not supported)")


if __name__ == "__main__":
    unittest.main()
