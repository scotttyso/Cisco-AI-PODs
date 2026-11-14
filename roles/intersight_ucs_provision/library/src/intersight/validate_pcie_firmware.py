"""PCIe Connectivity Policy Firmware Validation Module.

This module validates that servers running PCIe connectivity policies have
compatible firmware versions by comparing against the known minimum required
version.

Typical usage:
    from validate_pcie_firmware import (
        validate_pcie_connectivity_firmware,
        format_pcie_validation_report
    )
    
    is_compatible, incompatible_servers = validate_pcie_connectivity_firmware(
        ["PCIe-Connectivity"],
        servers_data
    )
    
    report = format_pcie_validation_report(
        is_compatible,
        incompatible_servers,
        1
    )
"""
# =============================================================================
# Source Modules
# =============================================================================
from typing import Dict, List, Tuple


# PCIe Connectivity Policy Minimum Firmware Requirements
PCIE_CONNECTIVITY_MIN_FIRMWARE = "6.0(1.252039)"


def parse_firmware_version(version_str: str) -> Tuple[int, int, int, int]:
    """Parse firmware version string into comparable tuple.

    Format: "6.0(1.250120)" -> (6, 0, 1, 250120)

    Args:
        version_str: Firmware version string like "6.0(1.250120)"

    Returns:
        Tuple of (major, minor, release, build)

    Raises:
        ValueError: If version string format is invalid
    """
    try:
        # Split on parenthesis: "6.0(1.250120)" -> ["6.0", "1.250120)"]
        major_minor_part = version_str.split('(')[0]  # "6.0"
        release_build_part = version_str.split('(')[1].rstrip(')')  # "1.250120"

        # Parse each part
        major, minor = major_minor_part.split('.')
        release, build = release_build_part.split('.')

        return (int(major), int(minor), int(release), int(build))
    except (IndexError, ValueError) as e:
        raise ValueError(
            f"Invalid firmware version format: '{version_str}'. "
            f"Expected format: 'X.Y(Z.NNNNN)'"
        ) from e


def is_firmware_compatible(current_version: str, required_version: str) -> bool:
    """Check if current firmware version meets minimum requirement.

    Args:
        current_version: Current firmware version string
        required_version: Minimum required firmware version string

    Returns:
        True if current >= required, False otherwise
    """
    try:
        current_tuple = parse_firmware_version(current_version)
        required_tuple = parse_firmware_version(required_version)
        return current_tuple >= required_tuple
    except ValueError:
        # If we can't parse, assume incompatible (fail-safe)
        return False


def validate_pcie_connectivity_firmware(
    pcie_policies: List[str],
    servers_data: Dict[str, Dict],
    min_firmware: str = PCIE_CONNECTIVITY_MIN_FIRMWARE
) -> Tuple[bool, List[Dict]]:
    """Validate PCIe connectivity policies against server firmware versions.

    Args:
        pcie_policies: List of PCIe connectivity policy names that will be deployed
        servers_data: Dictionary mapping server serial numbers to their properties
                      Expected format: {
                          "FCH2345ABCD": {
                              "name": "server-name",
                              "firmware_version": "6.0(1.250120)",
                              "model": "UCSX-215C-M8"
                          }
                      }
        min_firmware: Minimum required firmware version (default from constant)

    Returns:
        Tuple of (all_compatible: bool, incompatible_servers: list)
        where incompatible_servers contains dicts with:
            {
                "serial": "FCH2345ABCD",
                "name": "server-name",
                "model": "UCSX-215C-M8",
                "current_firmware": "6.0(1.250120)",
                "required_firmware": "6.0(1.252039)",
                "policies": ["PCIe-Connectivity"]
            }
    """
    incompatible_servers = []

    # Only validate if PCIe policies are defined
    if not pcie_policies:
        return True, []

    # Check each server
    for serial, server_info in servers_data.items():
        firmware = server_info.get("firmware_version", "Unknown")

        # If firmware is unknown, add to incompatible list (fail-safe)
        if firmware == "Unknown":
            incompatible_servers.append({
                "serial": serial,
                "name": server_info.get("name", "Unknown"),
                "model": server_info.get("model", "Unknown"),
                "current_firmware": firmware,
                "required_firmware": min_firmware,
                "policies": pcie_policies,
                "reason": "Firmware version could not be determined"
            })
            continue

        # Check compatibility
        if not is_firmware_compatible(firmware, min_firmware):
            incompatible_servers.append({
                "serial": serial,
                "name": server_info.get("name", "Unknown"),
                "model": server_info.get("model", "Unknown"),
                "current_firmware": firmware,
                "required_firmware": min_firmware,
                "policies": pcie_policies,
                "reason": f"Current firmware {firmware} is below minimum {min_firmware}"
            })

    all_compatible = len(incompatible_servers) == 0
    return all_compatible, incompatible_servers


def format_pcie_validation_report(
    is_compatible: bool,
    incompatible_servers: List[Dict],
    pcie_policy_count: int
) -> str:
    """Format validation results as human-readable report.

    Args:
        is_compatible: Whether all servers are compatible
        incompatible_servers: List of incompatible server dicts
        pcie_policy_count: Number of PCIe policies to be deployed

    Returns:
        Formatted report string
    """
    if is_compatible:
        return (
            "\n╔════════════════════════════════════════════════════════════╗\n"
            "║  ✅ PCIe CONNECTIVITY FIRMWARE COMPATIBILITY CHECK         ║\n"
            f"║  Policies to Deploy: {pcie_policy_count:<38} ║\n"
            "║  Status: All servers compatible                            ║\n"
            "╚════════════════════════════════════════════════════════════╝\n"
        )

    # Format incompatible servers report
    report = (
        "\n╔════════════════════════════════════════════════════════════╗\n"
        "║  ⚠️  PCIe CONNECTIVITY FIRMWARE COMPATIBILITY WARNINGS     ║\n"
        f"║  Policies to Deploy: {pcie_policy_count:<38} ║\n"
        f"║  Incompatible Servers: {len(incompatible_servers):<36} ║\n"
        "╠════════════════════════════════════════════════════════════╣\n"
    )

    for server in incompatible_servers:
        report += (
            f"║  Serial: {server['serial']:<48} ║\n"
            f"║  Name: {server['name']:<50} ║\n"
            f"║  Model: {server['model']:<50} ║\n"
            f"║  Current Firmware: {server['current_firmware']:<40} ║\n"
            f"║  Required Firmware: {server['required_firmware']:<40} ║\n"
            f"║  Policy: {server['policies'][0] if server['policies'] else 'N/A':<48} ║\n"
            f"║  Issue: {server['reason']:<49} ║\n"
            "║  Action: Upgrade firmware or disable PCIe policy        ║\n"
            "╠════════════════════════════════════════════════════════════╣\n"
        )

    report += "╚════════════════════════════════════════════════════════════╝\n"
    return report
