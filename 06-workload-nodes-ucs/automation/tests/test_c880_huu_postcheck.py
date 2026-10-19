"""Unit tests for probe_c880_huu_postcheck."""

import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "probe_c880_huu_postcheck.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("probe_c880_huu_postcheck", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class C880HuuPostcheckTests(unittest.TestCase):
    def test_audit_huu_firmware_success(self):
        responses = {
            "/redfish/v1/Chassis/DGX/NetworkAdapters/NIC3": {
                "Controllers": [{"FirmwarePackageVersion": "32.47.1088"}],
                "Status": {"Health": "OK", "State": "Enabled"},
            },
            "/redfish/v1/Chassis/DGX/NetworkAdapters/NIC9": {
                "Controllers": [{"FirmwarePackageVersion": "32.47.1088"}],
                "Status": {"Health": "OK", "State": "Enabled"},
            },
            "/redfish/v1/Chassis/DGX/NetworkAdapters/NIC4": {
                "Controllers": [{"FirmwarePackageVersion": "1.3862.0"}],
                "Status": {"Health": "OK", "State": "Disabled"},
            },
            "/redfish/v1/Systems/DGX/Storage": {
                "Members": [
                    {"@odata.id": "/redfish/v1/Systems/DGX/Storage/StorageUnit_0"},
                    {"@odata.id": "/redfish/v1/Systems/DGX/Storage/StorageUnit_1"},
                ]
            },
            "/redfish/v1/Systems/DGX/Storage/StorageUnit_0": {
                "StorageControllers": [{"FirmwareVersion": "F3MU111"}],
                "Status": {"Health": "OK", "State": "Enabled"},
            },
            "/redfish/v1/Systems/DGX/Storage/StorageUnit_1": {
                "StorageControllers": [{"FirmwareVersion": "F3MU111"}],
                "Status": {"Health": "OK", "State": "Enabled"},
            },
        }

        def fake_reader(path):
            return responses[path]

        result = MODULE.audit_huu_firmware(fake_reader)
        self.assertTrue(result["all_passed"])
        self.assertTrue(result["adapters"]["NIC3"]["passed"])
        self.assertTrue(result["adapters"]["NIC9"]["passed"])
        self.assertTrue(result["adapters"]["NIC4"]["passed"])
        self.assertTrue(result["storage"]["StorageUnit_0"]["passed"])
        self.assertTrue(result["storage"]["StorageUnit_1"]["passed"])

    def test_audit_huu_firmware_version_mismatch(self):
        responses = {
            "/redfish/v1/Chassis/DGX/NetworkAdapters/NIC3": {
                "Controllers": [{"FirmwarePackageVersion": "28.39.1002"}],  # old version
                "Status": {"Health": "OK", "State": "Enabled"},
            },
            "/redfish/v1/Chassis/DGX/NetworkAdapters/NIC9": {
                "Controllers": [{"FirmwarePackageVersion": "32.47.1088"}],
                "Status": {"Health": "OK", "State": "Enabled"},
            },
            "/redfish/v1/Chassis/DGX/NetworkAdapters/NIC4": {
                "Controllers": [{"FirmwarePackageVersion": "1.3862.0"}],
                "Status": {"Health": "OK", "State": "Disabled"},
            },
            "/redfish/v1/Systems/DGX/Storage": {
                "Members": [
                    {"@odata.id": "/redfish/v1/Systems/DGX/Storage/StorageUnit_0"},
                    {"@odata.id": "/redfish/v1/Systems/DGX/Storage/StorageUnit_1"},
                ]
            },
            "/redfish/v1/Systems/DGX/Storage/StorageUnit_0": {
                "StorageControllers": [{"FirmwareVersion": "F3MU111"}],
                "Status": {"Health": "OK", "State": "Enabled"},
            },
            "/redfish/v1/Systems/DGX/Storage/StorageUnit_1": {
                "StorageControllers": [{"FirmwareVersion": "F3MU111"}],
                "Status": {"Health": "OK", "State": "Enabled"},
            },
        }

        def fake_reader(path):
            return responses[path]

        result = MODULE.audit_huu_firmware(fake_reader)
        self.assertFalse(result["all_passed"])
        self.assertFalse(result["adapters"]["NIC3"]["passed"])

    def test_audit_settings_persistence_success(self):
        responses = {
            "/redfish/v1/Managers/BMC/EthernetInterfaces/eth0": {
                "HostName": "AIPOD-UCS-C880-4",
                "FQDN": "AIPOD-UCS-C880-4.aipod.local",
                "StaticNameServers": ["192.0.2.53", "192.0.2.54"],
                "IPv4Addresses": [
                    {"Address": "203.0.113.84", "SubnetMask": "255.255.255.0", "Gateway": "203.0.113.254"}
                ],
            },
            "/redfish/v1/Managers/BMC/NetworkProtocol": {
                "NTP": {"NTPServers": ["198.51.100.124", "198.51.100.125"], "ProtocolEnabled": True},
                "SSH": {"Port": 22, "ProtocolEnabled": True},
            },
            "/redfish/v1/Managers/BMC": {
                "DateTimeLocalOffset": "-04:00"
            },
        }

        def fake_reader(path):
            return responses[path]

        host_spec = {
            "hostname": "AIPOD-UCS-C880-4",
            "ip": "203.0.113.84",
            "netmask": "255.255.255.0",
            "gateway": "203.0.113.254",
        }
        shared_spec = {
            "domain_name": "aipod.local",
            "dns_servers": ["192.0.2.53", "192.0.2.54"],
            "ntp_servers": ["198.51.100.124", "198.51.100.125"],
            "timezone": "America/New_York",
        }

        result = MODULE.audit_settings_persistence(fake_reader, host_spec, shared_spec)
        self.assertTrue(result["all_passed"])
        for check in result["details"].values():
            self.assertTrue(check["passed"])

    def test_audit_settings_persistence_reverted(self):
        # Factory defaults reverted: DHCP or blank IP, factory hostname, NTP disabled
        responses = {
            "/redfish/v1/Managers/BMC/EthernetInterfaces/eth0": {
                "HostName": "C880A-WIH3022000P",
                "FQDN": None,
                "StaticNameServers": ["::", "::"],
                "IPv4Addresses": [
                    {"Address": "192.168.1.100", "SubnetMask": "255.255.255.0", "Gateway": "192.168.1.1"}
                ],
            },
            "/redfish/v1/Managers/BMC/NetworkProtocol": {
                "NTP": {"NTPServers": [], "ProtocolEnabled": False},
                "SSH": {"Port": 22, "ProtocolEnabled": True},
            },
            "/redfish/v1/Managers/BMC": {
                "DateTimeLocalOffset": "+00:00"
            },
        }

        def fake_reader(path):
            return responses[path]

        host_spec = {
            "hostname": "AIPOD-UCS-C880-4",
            "ip": "203.0.113.84",
            "netmask": "255.255.255.0",
            "gateway": "203.0.113.254",
        }
        shared_spec = {
            "domain_name": "aipod.local",
            "dns_servers": ["192.0.2.53", "192.0.2.54"],
            "ntp_servers": ["198.51.100.124", "198.51.100.125"],
            "timezone": "America/New_York",
        }

        result = MODULE.audit_settings_persistence(fake_reader, host_spec, shared_spec)
        self.assertFalse(result["all_passed"])
        self.assertFalse(result["details"]["ipv4_address"]["passed"])
        self.assertFalse(result["details"]["ntp_servers"]["passed"])
        self.assertFalse(result["details"]["hostname"]["passed"])


if __name__ == "__main__":
    unittest.main()
