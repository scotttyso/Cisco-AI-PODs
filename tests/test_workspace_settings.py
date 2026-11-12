import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from nicegui.app.app import App


REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))
sys.path.insert(0, str(REPOSITORY / "00-environment-prep" / "automation" / "scripts"))
import build_initial_inventory as builder  # noqa: E402
import merge_schemas  # noqa: E402
from aipod_webui import dhcp_model, site_settings, yaml_editor  # noqa: E402
from aipod_webui.yaml_editor import validate_yaml  # noqa: E402


SCHEMA = REPOSITORY / "schemas" / "source" / "cisco-ai-pods.json"
BUNDLE = REPOSITORY / "schema" / "cisco-ai-pods.json"


def validate(settings):
    return builder.validate_shared_services(settings, SCHEMA)


def fake_root(folder: Path) -> Path:
    files = {
        "etc/resolv.conf": "nameserver 127.0.0.53\nsearch example.com\n",
        "run/systemd/resolve/resolv.conf": "# upstream\nnameserver 10.0.0.53\nnameserver 10.0.0.54\nsearch lab.example.com example.com\n",
        "etc/chrony.conf": "pool 2.pool.ntp.org iburst\n# server ignored.example.com\n",
        "etc/chrony.d/site.conf": "server 10.0.0.123 iburst\n",
        "etc/timezone": "America/New_York\n",
        "etc/environment": 'HTTP_PROXY="http://user:secret@proxy.example.com:8080/"\nno_proxy=localhost,.example.com\n',
    }
    for name, text in files.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return folder


class HostDetectionTests(unittest.TestCase):
    def test_detects_settings_from_files(self):
        with tempfile.TemporaryDirectory() as folder:
            detected = site_settings.detect_host_defaults(fake_root(Path(folder)), environ={})
        self.assertEqual(detected["dns_servers"], ["10.0.0.53", "10.0.0.54"])
        self.assertEqual(detected["dns_search_domains"], ["lab.example.com", "example.com"])
        self.assertEqual(detected["domain_name"], "lab.example.com")
        self.assertEqual(detected["ntp_servers"], ["2.pool.ntp.org", "10.0.0.123"])
        self.assertEqual(detected["timezone"], "America/New_York")
        # Credentials are never copied out of proxy URLs.
        self.assertEqual(detected["proxy_servers"], {"http_proxy": "http://proxy.example.com:8080", "username": "user",
                                                     "no_proxy": ["localhost", ".example.com"]})

    def test_environment_proxy_overrides_file(self):
        with tempfile.TemporaryDirectory() as folder:
            proxy = site_settings.detect_proxy({"https_proxy": "http://other.example.com:3128"}, fake_root(Path(folder)))
        self.assertEqual(proxy["https_proxy"], "http://other.example.com:3128")
        self.assertEqual(proxy["http_proxy"], "http://proxy.example.com:8080")


class SharedServicesTests(unittest.TestCase):
    def test_sanitize_drops_schema_invalid_values(self):
        detected = {"dns_servers": ["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4", "10.0.0.5"],
                    "timezone": "Not/A_Zone", "ntp_servers": ["10.0.0.123"]}
        clean, dropped = site_settings.sanitize(detected, validate)
        self.assertEqual(clean["dns_servers"], ["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4"])
        self.assertNotIn("timezone", clean)
        self.assertEqual(clean["ntp_servers"], ["10.0.0.123"])
        self.assertIn("dns_servers: 10.0.0.5", dropped)
        self.assertIn("timezone: Not/A_Zone", dropped)

    def test_overrides_round_trip(self):
        detected = {"dns_servers": ["10.0.0.53"], "ntp_servers": ["10.0.0.123"],
                    "proxy_servers": {"http_proxy": "http://proxy:8080", "no_proxy": ["localhost"]}}
        effective = {"dns_servers": ["10.0.0.53"], "ntp_servers": ["10.9.9.9"],
                     "proxy_servers": {"no_proxy": ["localhost", ".cluster.local"]}}
        overrides = site_settings.overrides_from(effective, detected)
        self.assertEqual(overrides, {"ntp_servers": ["10.9.9.9"],
                                     "proxy_servers": {"http_proxy": None, "no_proxy": ["localhost", ".cluster.local"]}})
        self.assertEqual(site_settings.merge(detected, overrides), effective)

    def test_store_saves_only_overrides(self):
        detected = {"dns_servers": ["10.0.0.53"], "ntp_servers": ["10.0.0.123"], "timezone": "UTC"}
        with tempfile.TemporaryDirectory() as folder:
            store = site_settings.WorkspaceStore(Path(folder), validate, detect=lambda: detected)
            self.assertEqual(store.shared_services(), detected)
            with self.assertRaises(ValueError):
                store.save_shared_services({"timezone": "Not/A_Zone"})
            store.save_shared_services({**detected, "ntp_servers": ["10.9.9.9"]})
            saved = json.loads((Path(folder) / "site_settings.json").read_text())
            self.assertEqual(saved, {"shared_services_overrides": {"ntp_servers": ["10.9.9.9"]}})
            self.assertEqual((Path(folder) / "site_settings.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual(store.shared_services()["ntp_servers"], ["10.9.9.9"])
            store.save_page_state("dhcp", {"network": "198.18.0.0/24"})
            store.reset_shared_services()
            self.assertEqual(store.shared_services(), detected)
            self.assertEqual(store.page_state("dhcp"), {"network": "198.18.0.0/24"})
            store.save_inventory([{"hostname": "fi-a", "ip": "198.18.0.10", "mac": "00:25:B5:00:00:01", "extra": "x"}])
            self.assertEqual(store.inventory(), [{"hostname": "fi-a", "ip": "198.18.0.10", "mac": "00:25:B5:00:00:01",
                                                  "pid": "", "serial_number": ""}])


class DhcpModelTests(unittest.TestCase):
    def test_pool_ip_skips_dhcp_even_with_stale_address(self):
        rows = [dict(hostname="fi-a", ip="198.18.0.10", mac="00:25:b5:00:00:01"),
                dict(hostname="blade1", ip="198.18.0.10", mac="00:25:b5:00:00:02", pool_ip=True),
                dict(hostname="blade2", ip="", mac="00:25:b5:00:00:03", pool_ip=True)]
        model, _unused_value = dhcp_model.build_dhcp_model(rows, {}, {})
        self.assertEqual([row["hostname"] for row in model["dhcp"]["reservations"]], ["fi-a"])
        with tempfile.TemporaryDirectory() as folder:
            store = site_settings.WorkspaceStore(Path(folder), validate, detect=lambda: {})
            store.save_inventory(rows)
            self.assertTrue(store.inventory()[1]["pool_ip"])
            self.assertEqual(store.inventory()[1]["ip"], "")

    INVENTORY = [
        {"hostname": "fi-a", "ip": "198.18.0.10", "mac": "00:25:B5:00:00:01"},
        {"hostname": "unknown", "ip": "198.18.0.11", "mac": "00:25:b5:00:00:02"},
        {"hostname": "far", "ip": "10.1.1.1", "mac": "00:25:b5:00:00:03"},
        {"hostname": "nomac", "ip": "198.18.0.12", "mac": ""},
    ]
    SERVICES = {"domain_name": "example.com", "dns_servers": ["10.0.0.53", "2001:db8::53"],
                "ntp_servers": ["10.0.0.123"], "dns_search_domains": ["example.com", "lab.example.com"]}

    def test_builds_reservations_inside_network(self):
        model, warnings = dhcp_model.build_dhcp_model(self.INVENTORY, self.SERVICES,
                                                      {"routers": ["198.18.0.1"], "interfaces": ["ens224"]})
        dhcp = model["dhcp"]
        self.assertEqual(dhcp["interfaces"], ["ens224"])
        self.assertEqual(dhcp["domain_name_servers"], ["10.0.0.53"])
        self.assertEqual(dhcp["global_options"], [{"name": "domain-search", "value": "example.com, lab.example.com"}])
        self.assertEqual(dhcp["subnets"], [{"name": "bootstrap", "network": "198.18.0.0", "netmask": "255.255.255.0",
                                            "routers": ["198.18.0.1"], "deny_unknown_clients": True}])
        self.assertEqual(dhcp["reservations"], [
            {"subnet": "bootstrap", "mac": "00:25:b5:00:00:01", "ip": "198.18.0.10", "hostname": "fi-a"},
            {"subnet": "bootstrap", "mac": "00:25:b5:00:00:02", "ip": "198.18.0.11"},
        ])
        self.assertTrue(any("2001:db8::53" in warning for warning in warnings))
        self.assertTrue(any("far: 10.1.1.1 is outside" in warning for warning in warnings))

    def test_rejects_bad_options(self):
        for options in ({"routers": ["10.1.1.1"]}, {"pool_start": "198.18.0.100"},
                        {"pool_start": "198.18.0.200", "pool_end": "198.18.0.100"}, {"tftp_server": "not-an-ip"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                dhcp_model.build_dhcp_model(self.INVENTORY, self.SERVICES, options)
        with self.assertRaises(ValueError):
            dhcp_model.build_dhcp_model(self.INVENTORY + [{"ip": "198.18.0.13", "mac": "00:25:b5:00:00:01"}],
                                        self.SERVICES, {})
        with self.assertRaises(ValueError):
            dhcp_model.build_dhcp_model([], self.SERVICES, {})

    def test_pool_without_reservations(self):
        model, _unused_value = dhcp_model.build_dhcp_model([], {}, {"pool_start": "198.18.0.100", "pool_end": "198.18.0.200",
                                                                    "deny_unknown_clients": False})
        self.assertEqual(model["dhcp"]["subnets"][0]["ranges"], [{"start": "198.18.0.100", "end": "198.18.0.200"}])
        self.assertEqual(model["dhcp"]["reservations"], [])

    def test_suggests_network_from_interfaces_or_inventory(self):
        self.assertEqual(dhcp_model.covering_network(["198.18.0.10", "198.18.0.200"]), "198.18.0.0/24")
        self.assertEqual(dhcp_model.covering_network(["198.18.0.10", "198.18.3.1"]), "198.18.0.0/22")
        self.assertEqual(dhcp_model.covering_network(["10.0.0.1", "198.18.0.1"]), "")
        interfaces = [{"name": "ens224", "network": "198.18.0.0/23"}]
        self.assertEqual(dhcp_model.suggest_network(interfaces, ["198.18.1.5"]), ("198.18.0.0/23", "host interface ens224"))
        self.assertEqual(dhcp_model.suggest_network(interfaces, ["10.9.9.9"]),
                         ("10.9.9.0/24", "the Initial Inventory addresses"))
        self.assertEqual(dhcp_model.suggest_network([], [])[0], dhcp_model.DEFAULT_BOOTSTRAP_NETWORK)

    def test_generated_model_matches_schema(self):
        import yaml
        from aipod_webui.yaml_editor import validate_yaml
        schema = REPOSITORY / "schema/cisco-ai-pods.json"
        model, _unused_value = dhcp_model.build_dhcp_model(self.INVENTORY, self.SERVICES, {"routers": ["198.18.0.1"]})
        self.assertEqual(validate_yaml(yaml.safe_dump(model), schema)[1], [])
        model["dhcp"]["subnets"][0]["unexpected"] = True
        self.assertNotEqual(validate_yaml(yaml.safe_dump(model), schema)[1], [])


class YamlValidationTests(unittest.TestCase):
    def test_empty_source_reports_path_and_preserves_previous_bundle(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "sources"
            source.mkdir()
            broken = source / "cisco-ai-pods.json"
            broken.write_text("", encoding="utf-8")
            output = Path(folder) / "schema.json"
            previous = '{"type": "object"}\n'
            output.write_text(previous, encoding="utf-8")
            with patch.object(sys, "argv", [
                    "merge_schemas.py", "--source-dir", str(source), "--output", str(output)]):
                with self.assertRaisesRegex(ValueError, "Invalid JSON") as caught:
                    merge_schemas.main()
            self.assertIn(str(broken), str(caught.exception))
            self.assertEqual(output.read_text(encoding="utf-8"), previous)

    def test_failed_bundle_write_preserves_previous_schema(self):
        previous = '{"type": "object"}\n'
        for partial in ("", '{"partial":'):
            with self.subTest(partial=partial), tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / "schema.json"
                output.write_text(previous, encoding="utf-8")

                def failed_write(_bundle, stream, **_options):
                    stream.write(partial)
                    raise OSError("simulated interrupted write")

                with patch.object(sys, "argv", ["merge_schemas.py", "--output", str(output)]), \
                        patch.object(merge_schemas, "load_sources", return_value={}), \
                        patch.object(merge_schemas, "build_bundle", return_value={"definitions": {}}), \
                        patch.object(merge_schemas.json, "dump", side_effect=failed_write):
                    with self.assertRaisesRegex(OSError, "interrupted write"):
                        merge_schemas.main()
                self.assertEqual(output.read_text(encoding="utf-8"), previous)
                self.assertEqual(list(Path(folder).iterdir()), [output])

    def test_bundle_write_replaces_schema_and_preserves_permissions(self):
        for existing_mode in (None, 0o640):
            with self.subTest(existing_mode=existing_mode), tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / "schema.json"
                if existing_mode is not None:
                    output.write_text("old", encoding="utf-8")
                    output.chmod(existing_mode)
                bundle = {"definitions": {}, "type": "object"}
                with patch.object(sys, "argv", ["merge_schemas.py", "--output", str(output)]), \
                        patch.object(merge_schemas, "load_sources", return_value={}), \
                        patch.object(merge_schemas, "build_bundle", return_value=bundle):
                    merge_schemas.main()
                self.assertEqual(json.loads(output.read_text(encoding="utf-8")), bundle)
                self.assertEqual(output.stat().st_mode & 0o777, existing_mode or 0o644)

    def test_schema_endpoint_revalidates_updated_content(self):
        with tempfile.TemporaryDirectory() as folder:
            schema = Path(folder) / "schema.json"
            schema.write_text('{"type": "object"}', encoding="utf-8")
            application = App()
            with patch.object(yaml_editor, "app", application), \
                    patch.dict(yaml_editor._REGISTERED, {"static": False}):
                yaml_editor.register_static(schema)
            client = TestClient(application)
            response = client.get("/aipod-schemas/schema.json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"type": "object"})
            self.assertIn("max-age=0", response.headers["cache-control"])
            schema.write_text('{"type": "array"}', encoding="utf-8")
            self.assertEqual(client.get("/aipod-schemas/schema.json").json(), {"type": "array"})

    def test_bundled_schema_definition_is_valid(self):
        Draft202012Validator.check_schema(json.loads(BUNDLE.read_text(encoding="utf-8")))

    def test_cdn_values_enforce_character_and_length_limits(self):
        definitions = json.loads(BUNDLE.read_text(encoding="utf-8"))["definitions"]
        fields = (
            definitions["intersight.policies.lan_connectivity.vnics_from_template"]["properties"]["cdn_value"],
            definitions["intersight.templates.vnic_template"]["allOf"][1]["properties"]["cdn_value"],
        )
        for field in fields:
            validator = Draft202012Validator(field)
            for value in ("a", "eth-0._:1", "a" * 31):
                with self.subTest(field=field["description"], value=value):
                    self.assertTrue(validator.is_valid(value))
            for value in ("", "a" * 32, "eth/0", "eth 0"):
                with self.subTest(field=field["description"], value=value):
                    self.assertFalse(validator.is_valid(value))

    def test_reports_syntax_and_schema_problems(self):
        _unused_value, problems = validate_yaml("a: [1,\n", BUNDLE)
        self.assertTrue(problems[0].startswith("YAML syntax error"))
        _unused_value, problems = validate_yaml("nexus_dashboard:\n  fabrics: 5\nbogus_root_key: 1\n", BUNDLE)
        self.assertTrue(any(problem.startswith("nexus_dashboard.fabrics") for problem in problems))
        self.assertFalse(any("Unevaluated" in problem for problem in problems))
        document, problems = validate_yaml("shared_services:\n  timezone: UTC\n", BUNDLE)
        self.assertEqual((document, problems), ({"shared_services": {"timezone": "UTC"}}, []))


if __name__ == "__main__":
    unittest.main()
