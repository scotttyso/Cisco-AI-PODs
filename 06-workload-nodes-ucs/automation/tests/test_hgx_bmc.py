import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("configure_hgx_bmc", SCRIPTS / "configure_hgx_bmc.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

SETTINGS = {"dns_servers": ["192.0.2.53"], "ntp_servers": ["192.0.2.123"], "domain_name": "example.com",
            "timezone": "America/New_York"}
WINTER = datetime(2025, 1, 15, tzinfo=timezone.utc)


class Response:
    def __init__(self, status=200, text=""):
        self.status_code, self.text = status, text


class FakeRedfish:
    def __init__(self):
        self.state = {
            "/m/1/NetworkProtocol": {"NTP": {"NTPServers": [], "ProtocolEnabled": False}, "SSH": {"ProtocolEnabled": True}},
            "/m/1": {"DateTimeLocalOffset": "+00:00"},
            "/m/1/eth/0": {"HostName": "old", "FQDN": "old.local", "StaticNameServers": []},
        }
        self.patches = []

    def manager(self):
        return "/m/1"

    def manager_interface(self, address):
        return "/m/1/eth/0", self.state["/m/1/eth/0"]

    def get(self, path):
        return self.state[path]

    def patch(self, path, body):
        self.patches.append((path, body))
        self.state[path].update(body)
        return Response()


class HgxBmcTests(unittest.TestCase):
    def test_offset_follows_daylight_saving(self):
        self.assertEqual(MODULE.timezone_offset("America/New_York", WINTER), "-05:00")
        self.assertEqual(MODULE.timezone_offset("America/New_York", datetime(2025, 7, 1, tzinfo=timezone.utc)), "-04:00")
        self.assertEqual(MODULE.timezone_offset("Asia/Kolkata", WINTER), "+05:30")

    def test_c880_keeps_ipv6_dns_slot(self):
        target = MODULE.desired(SETTINGS, {"hostname": "hgx-1", "model": "C880A"}, WINTER)
        self.assertEqual(target["dns"], ["192.0.2.53", "::"])
        self.assertEqual(target["fqdn"], "hgx-1.example.com")
        self.assertEqual(MODULE.desired(SETTINGS, {"hostname": "hgx-2", "model": "C845A"}, WINTER)["dns"], ["192.0.2.53"])

    def test_disabled_settings_are_skipped(self):
        settings = dict(SETTINGS, configure={"ntp": False, "timezone": False})
        changes = MODULE.differences(MODULE.desired(settings, {"hostname": "hgx-1"}, WINTER),
                                     {"hostname": "x", "fqdn": "x", "dns": [], "ntp": [], "ntp_enabled": False, "offset": "+00:00"})
        self.assertEqual(set(changes), {"interface"})

    def test_check_mode_does_not_patch(self):
        client, lines = FakeRedfish(), []
        bmc = MODULE.Bmc(client, "192.0.2.10", 0, sleep=lambda _: None)
        self.assertTrue(MODULE.configure(bmc, MODULE.desired(SETTINGS, {"hostname": "hgx-1"}, WINTER), False, lines.append))
        self.assertEqual(client.patches, [])
        self.assertTrue(any("would set interface" in line for line in lines))

    def test_apply_patches_and_verifies(self):
        client, lines = FakeRedfish(), []
        bmc = MODULE.Bmc(client, "192.0.2.10", 0, sleep=lambda _: None)
        target = MODULE.desired(SETTINGS, {"hostname": "hgx-1", "model": "C880A"}, WINTER)
        self.assertTrue(MODULE.configure(bmc, target, True, lines.append))
        self.assertEqual([path for path, _ in client.patches], ["/m/1/NetworkProtocol", "/m/1", "/m/1/eth/0"])
        self.assertIn("    verified", lines)
        lines.clear()
        self.assertTrue(MODULE.configure(bmc, target, True, lines.append))
        self.assertEqual(lines, ["    already configured"])

    def test_already_set_response_is_success(self):
        client = FakeRedfish()
        client.patch = lambda path, body: Response(400, '{"error": "PatchValueAlreadyExists"}')
        MODULE.Bmc(client, "192.0.2.10", 0, sleep=lambda _: None).patch("manager", {"DateTimeLocalOffset": "+00:00"})

    def test_load_filters_hosts_and_requires_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hgx.yaml"
            path.write_text("hgx_servers:\n  bmc_settings: {dns_servers: [192.0.2.53], ntp_servers: [192.0.2.123],"
                            " domain_name: example.com, timezone: UTC}\n  servers:\n"
                            "  - {hostname: a, bmc: {ip: 192.0.2.1}}\n  - {hostname: b, bmc: {ip: 192.0.2.2}}\n")
            _, servers = MODULE.load_servers(path, ["B"])
            self.assertEqual([server["hostname"] for server in servers], ["b"])
            path.write_text("hgx_servers:\n  bmc_settings: {}\n")
            with self.assertRaises(ValueError):
                MODULE.load_servers(path, [])

    def test_missing_password_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hgx.yaml"
            path.write_text("hgx_servers:\n  bmc_settings: {dns_servers: [192.0.2.53], ntp_servers: [192.0.2.123],"
                            " domain_name: example.com, timezone: UTC, password_ref: HGX_TEST_UNSET}\n"
                            "  servers:\n  - {hostname: a, bmc: {ip: 192.0.2.1}}\n")
            self.assertEqual(MODULE.main(["--vars", str(path)]), 1)


if __name__ == "__main__":
    unittest.main()
