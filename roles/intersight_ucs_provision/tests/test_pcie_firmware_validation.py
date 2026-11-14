"""Unit tests for PCIe Connectivity Firmware Validation module."""
import sys
from pathlib import Path

# Add the library to the path
LIBRARY_PATH = Path(__file__).parent.parent / 'library' / 'src' / 'intersight'
sys.path.insert(0, str(LIBRARY_PATH))

import pytest
from validate_pcie_firmware import (
    parse_firmware_version,
    is_firmware_compatible,
    validate_pcie_connectivity_firmware,
    format_pcie_validation_report,
    PCIE_CONNECTIVITY_MIN_FIRMWARE
)


class TestParseFirmwareVersion:
    """Test firmware version parsing."""

    def test_valid_firmware_version(self):
        """Test parsing valid firmware version format."""
        result = parse_firmware_version("6.0(1.250120)")
        assert result == (6, 0, 1, 250120)

    def test_different_firmware_versions(self):
        """Test parsing different firmware versions."""
        assert parse_firmware_version("6.0(1.252039)") == (6, 0, 1, 252039)
        assert parse_firmware_version("5.2(3.100000)") == (5, 2, 3, 100000)
        assert parse_firmware_version("7.1(2.999999)") == (7, 1, 2, 999999)

    def test_invalid_firmware_version_format(self):
        """Test that invalid formats raise ValueError."""
        with pytest.raises(ValueError):
            parse_firmware_version("invalid")

        with pytest.raises(ValueError):
            parse_firmware_version("6.0-1.250120")

        with pytest.raises(ValueError):
            parse_firmware_version("6.0(1)")

        with pytest.raises(ValueError):
            parse_firmware_version("")


class TestIsFirmwareCompatible:
    """Test firmware compatibility checking."""

    def test_exact_version_match(self):
        """Test that exact version match is compatible."""
        assert is_firmware_compatible("6.0(1.252039)", "6.0(1.252039)")

    def test_newer_firmware_is_compatible(self):
        """Test that newer firmware is compatible."""
        assert is_firmware_compatible("6.0(1.252040)", "6.0(1.252039)")
        assert is_firmware_compatible("6.0(2.252039)", "6.0(1.252039)")
        assert is_firmware_compatible("6.1(1.252039)", "6.0(1.252039)")
        assert is_firmware_compatible("7.0(1.252039)", "6.0(1.252039)")

    def test_older_firmware_is_incompatible(self):
        """Test that older firmware is incompatible."""
        assert not is_firmware_compatible("6.0(1.250120)", "6.0(1.252039)")
        assert not is_firmware_compatible("6.0(1.200000)", "6.0(1.252039)")
        assert not is_firmware_compatible("5.2(1.252039)", "6.0(1.252039)")

    def test_invalid_current_version(self):
        """Test that invalid current version returns False (fail-safe)."""
        assert not is_firmware_compatible("invalid", "6.0(1.252039)")

    def test_invalid_required_version(self):
        """Test that invalid required version is treated as incompatible (fail-safe)."""
        # In the fail-safe approach, if we can't parse, we assume incompatible
        assert not is_firmware_compatible("6.0(1.252039)", "invalid")


class TestValidatePCIeConnectivityFirmware:
    """Test PCIe connectivity firmware validation."""

    def test_no_pcie_policies(self):
        """Test that no validation happens when no PCIe policies exist."""
        is_compatible, incompatible = validate_pcie_connectivity_firmware(
            [],
            {"FCH2345ABCD": {"name": "server1", "firmware_version": "6.0(1.250120)"}}
        )
        assert is_compatible is True
        assert incompatible == []

    def test_all_servers_compatible(self):
        """Test validation when all servers have compatible firmware."""
        servers_data = {
            "FCH2345ABCD": {
                "name": "server1",
                "firmware_version": "6.0(1.252039)",
                "model": "UCSX-215C-M8"
            },
            "FCH2345ABCE": {
                "name": "server2",
                "firmware_version": "6.0(2.260040)",
                "model": "UCSX-215C-M8"
            }
        }
        is_compatible, incompatible = validate_pcie_connectivity_firmware(
            ["PCIe-Connectivity"],
            servers_data
        )
        assert is_compatible is True
        assert incompatible == []

    def test_all_servers_incompatible(self):
        """Test validation when all servers have incompatible firmware."""
        servers_data = {
            "FCH2345ABCD": {
                "name": "server1",
                "firmware_version": "6.0(1.250120)",
                "model": "UCSX-215C-M8"
            },
            "FCH2345ABCE": {
                "name": "server2",
                "firmware_version": "6.0(1.250000)",
                "model": "UCSX-215C-M8"
            }
        }
        is_compatible, incompatible = validate_pcie_connectivity_firmware(
            ["PCIe-Connectivity"],
            servers_data
        )
        assert is_compatible is False
        assert len(incompatible) == 2
        assert incompatible[0]["serial"] == "FCH2345ABCD"
        assert incompatible[1]["serial"] == "FCH2345ABCE"

    def test_mixed_compatibility(self):
        """Test validation with mixed compatible/incompatible servers."""
        servers_data = {
            "FCH2345ABCD": {
                "name": "server1",
                "firmware_version": "6.0(1.252039)",
                "model": "UCSX-215C-M8"
            },
            "FCH2345ABCE": {
                "name": "server2",
                "firmware_version": "6.0(1.250120)",
                "model": "UCSX-215C-M8"
            }
        }
        is_compatible, incompatible = validate_pcie_connectivity_firmware(
            ["PCIe-Connectivity"],
            servers_data
        )
        assert is_compatible is False
        assert len(incompatible) == 1
        assert incompatible[0]["serial"] == "FCH2345ABCE"

    def test_unknown_firmware_version(self):
        """Test that unknown firmware is treated as incompatible."""
        servers_data = {
            "FCH2345ABCD": {
                "name": "server1",
                "firmware_version": "Unknown",
                "model": "UCSX-215C-M8"
            }
        }
        is_compatible, incompatible = validate_pcie_connectivity_firmware(
            ["PCIe-Connectivity"],
            servers_data
        )
        assert is_compatible is False
        assert len(incompatible) == 1
        assert "could not be determined" in incompatible[0]["reason"]

    def test_missing_firmware_field(self):
        """Test handling of missing firmware_version field."""
        servers_data = {
            "FCH2345ABCD": {
                "name": "server1",
                "model": "UCSX-215C-M8"
            }
        }
        is_compatible, incompatible = validate_pcie_connectivity_firmware(
            ["PCIe-Connectivity"],
            servers_data
        )
        assert is_compatible is False
        assert len(incompatible) == 1

    def test_multiple_pcie_policies(self):
        """Test validation with multiple PCIe policies."""
        servers_data = {
            "FCH2345ABCD": {
                "name": "server1",
                "firmware_version": "6.0(1.250120)",
                "model": "UCSX-215C-M8"
            }
        }
        is_compatible, incompatible = validate_pcie_connectivity_firmware(
            ["PCIe-Policy-1", "PCIe-Policy-2"],
            servers_data
        )
        assert is_compatible is False
        assert len(incompatible) == 1
        assert incompatible[0]["policies"] == ["PCIe-Policy-1", "PCIe-Policy-2"]

    def test_custom_min_firmware_version(self):
        """Test validation with custom minimum firmware version."""
        servers_data = {
            "FCH2345ABCD": {
                "name": "server1",
                "firmware_version": "5.0(1.100000)",
                "model": "UCSX-215C-M8"
            }
        }
        # Custom minimum is lower, so should be compatible
        is_compatible, incompatible = validate_pcie_connectivity_firmware(
            ["PCIe-Connectivity"],
            servers_data,
            min_firmware="5.0(1.000000)"
        )
        assert is_compatible is True
        assert incompatible == []


class TestFormatPCIeValidationReport:
    """Test report formatting."""

    def test_compatible_report(self):
        """Test report when all servers are compatible."""
        report = format_pcie_validation_report(
            is_compatible=True,
            incompatible_servers=[],
            pcie_policy_count=1
        )
        assert "✅" in report
        assert "All servers compatible" in report
        assert "Policies to Deploy: 1" in report

    def test_incompatible_report_single_server(self):
        """Test report with single incompatible server."""
        incompatible = [{
            "serial": "FCH2345ABCD",
            "name": "server1",
            "model": "UCSX-215C-M8",
            "current_firmware": "6.0(1.250120)",
            "required_firmware": "6.0(1.252039)",
            "policies": ["PCIe-Connectivity"],
            "reason": "Current firmware 6.0(1.250120) is below minimum 6.0(1.252039)"
        }]
        report = format_pcie_validation_report(
            is_compatible=False,
            incompatible_servers=incompatible,
            pcie_policy_count=1
        )
        assert "⚠️" in report
        assert "FCH2345ABCD" in report
        assert "6.0(1.250120)" in report
        assert "6.0(1.252039)" in report
        assert "Incompatible Servers: 1" in report

    def test_incompatible_report_multiple_servers(self):
        """Test report with multiple incompatible servers."""
        incompatible = [
            {
                "serial": "FCH2345ABCD",
                "name": "server1",
                "model": "UCSX-215C-M8",
                "current_firmware": "6.0(1.250120)",
                "required_firmware": "6.0(1.252039)",
                "policies": ["PCIe-Connectivity"],
                "reason": "Current firmware 6.0(1.250120) is below minimum 6.0(1.252039)"
            },
            {
                "serial": "FCH2345ABCE",
                "name": "server2",
                "model": "UCSX-215C-M8",
                "current_firmware": "6.0(1.250000)",
                "required_firmware": "6.0(1.252039)",
                "policies": ["PCIe-Connectivity"],
                "reason": "Current firmware 6.0(1.250000) is below minimum 6.0(1.252039)"
            }
        ]
        report = format_pcie_validation_report(
            is_compatible=False,
            incompatible_servers=incompatible,
            pcie_policy_count=1
        )
        assert "Incompatible Servers: 2" in report
        assert "FCH2345ABCD" in report
        assert "FCH2345ABCE" in report


class TestMinimumFirmwareConstant:
    """Test the minimum firmware constant."""

    def test_pcie_min_firmware_version(self):
        """Test that the PCIe minimum firmware is set correctly."""
        assert PCIE_CONNECTIVITY_MIN_FIRMWARE == "6.0(1.252039)"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
