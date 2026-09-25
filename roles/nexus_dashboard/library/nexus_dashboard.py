#!/usr/bin/env python3
"""
Nexus Dashboard Fabric Manager

This module provides functionality to:
1. Create classic-lan and VXLAN fabrics in Nexus Dashboard
2. Add switches to fabrics with configurable settings
3. Manage fabric configurations and device credentials
4. Validate configurations against JSON schema
5. Load credentials from vault

Author: Cisco AI PODs
Version: 2.0.0
"""

import json
import argparse
import sys
import yaml
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
import requests

from urllib3 import disable_warnings
from jsonschema import validate, ValidationError

# Disable SSL warnings for self-signed certificates
disable_warnings()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ConfigValidator:
    """Validate configurations against JSON schema"""

    def __init__(self, schema_path: Optional[str] = None):
        """
        Initialize validator with schema

        Args:
            schema_path: Path to JSON schema file
        """
        self.schema = None
        if schema_path and Path(schema_path).exists():
            with open(schema_path, 'r') as f:
                self.schema = json.load(f)

    def validate(self, config: Dict[str, Any], fabric_type: str) -> bool:
        """
        Validate configuration

        Args:
            config: Configuration dictionary
            fabric_type: Type of fabric (classic-lan, vxlan-ebgp, etc.)

        Returns:
            True if valid

        Raises:
            ValidationError: If validation fails
        """
        if not self.schema:
            logger.warning("No schema loaded, skipping validation")
            return True

        try:
            validate(instance=config, schema=self.schema)
            logger.info(f"Configuration validated successfully for {fabric_type}")
            return True
        except ValidationError as e:
            logger.error(f"Validation error: {e.message}")
            raise


class VaultCredentials:
    """Load credentials from vault file"""

    def __init__(self, vault_file: str):
        """
        Initialize vault credentials loader

        Args:
            vault_file: Path to vault-ai-pod.yaml file
        """
        self.vault_file = vault_file
        self.credentials = {}
        self._load_vault()

    def _load_vault(self):
        """Load vault file"""
        if Path(self.vault_file).exists():
            with open(self.vault_file, 'r') as f:
                self.credentials = yaml.safe_load(f) or {}
            logger.info(f"Loaded vault from {self.vault_file}")
        else:
            logger.warning(f"Vault file not found: {self.vault_file}")

    def get_credential(self, path: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get credential from vault using dot notation path

        Args:
            path: Path to credential (e.g., 'nexus_dashboard.nd_password_1')
            default: Default value if not found

        Returns:
            Credential value or default
        """
        keys = path.split('.')
        value = self.credentials
        
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
        
        return value if value else default


class NexusDashboardClient:
    """Client for interacting with Nexus Dashboard API"""

    def __init__(self, nd_url: str, username: str, password: str, verify_ssl: bool = False):
        """
        Initialize Nexus Dashboard client

        Args:
            nd_url: Nexus Dashboard URL (e.g., https://nd-lan.rich.ciscolabs.com)
            username: API username
            password: API password
            verify_ssl: Whether to verify SSL certificates (default: False)
        """
        self.nd_url = nd_url.rstrip("/")
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.verify = verify_ssl
        self.token = None

    def _make_request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Dict] = None,
        expected_status: int = 200,
    ) -> Dict[str, Any]:
        """
        Make API request to Nexus Dashboard

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., /fabrics)
            payload: Request body
            expected_status: Expected HTTP status code

        Returns:
            Response JSON

        Raises:
            Exception: If API request fails
        """
        url = f"{self.nd_url}/api/v1/manage{endpoint}"
        headers = {"Content-Type": "application/json"}

        try:
            response = self.session.request(
                method=method,
                url=url,
                json=payload,
                headers=headers,
                timeout=30,
            )

            if response.status_code not in [expected_status, 202]:
                error_msg = f"API request failed: {response.status_code} - {response.text}"
                raise Exception(error_msg)

            if response.status_code == 202 or not response.text:
                return {"status": "accepted"}

            return response.json()

        except requests.exceptions.RequestException as e:
            raise Exception(f"Request error: {str(e)}")

    def list_fabrics(self, fabric_name: Optional[str] = None) -> List[Dict]:
        """List all fabrics"""
        endpoint = "/fabrics"
        if fabric_name:
            endpoint += f"?filter=name eq {fabric_name}"

        response = self._make_request("GET", endpoint, expected_status=200)
        return response.get("fabrics", [])

    def create_fabric(
        self,
        fabric_name: str,
        fabric_type: str,
        fabric_settings: Optional[Dict[str, Any]] = None,
        location: Optional[Dict[str, float]] = None,
        security_domain: str = "all",
        telemetry_collection: bool = False,
    ) -> Dict[str, Any]:
        """
        Create a new fabric (classic-lan or VXLAN)

        Args:
            fabric_name: Name of the fabric
            fabric_type: Type of fabric (classicLan, vxlanIbgp, vxlanEbgp, etc.)
            fabric_settings: Dictionary of fabric management settings
            location: Location with latitude and longitude
            security_domain: Security domain (default: "all")
            telemetry_collection: Enable telemetry collection

        Returns:
            API response
        """
        # Default settings by fabric type
        default_settings = self._get_default_settings(fabric_type)
        
        if fabric_settings:
            default_settings.update(fabric_settings)

        if location is None:
            location = {"latitude": 37.33939, "longitude": -121.89496}

        payload = {
            "category": "fabric",
            "licenseTier": "essentials",
            "location": location,
            "management": default_settings,
            "name": fabric_name,
            "securityDomain": security_domain,
            "telemetryCollection": telemetry_collection,
        }

        response = self._make_request("POST", "/fabrics", payload=payload, expected_status=200)
        return response

    def _get_default_settings(self, fabric_type: str) -> Dict[str, Any]:
        """Get default settings for fabric type"""
        base_settings = {
            "aaa": False,
            "advancedSshOption": False,
            "cdp": False,
            "day0Bootstrap": False,
            "interfaceStatisticsLoadInterval": 10,
            "localDhcpServer": False,
            "managementIpv4Prefix": 24,
            "managementIpv6Prefix": 64,
            "netflowSettings": {"netflow": False},
            "performanceMonitoring": False,
            "powerRedundancyMode": "redundant",
            "ptp": False,
            "ptpDomainId": 0,
            "ptpLoopbackId": 0,
            "realTimeInterfaceStatisticsCollection": False,
            "snmpTrap": True,
        }

        if fabric_type == "classicLan":
            base_settings.update({
                "type": "classicLan",
                "coppPolicy": "manual",
                "inbandDay0Bootstrap": False,
                "inbandManagement": False,
                "mplsHandoff": False,
                "mplsLoopbackIdentifier": 101,
                "monitoredMode": True,
                "nxapi": False,
                "nxapiHttp": False,
                "nxapiHttpPort": 80,
                "nxapiHttpsPort": 443,
                "realTimeBackup": False,
                "scheduledBackup": False,
                "subInterfaceDot1qRange": "2-511",
            })
        elif fabric_type.startswith("vxlan"):
            base_settings.update({
                "type": fabric_type,
                "bgpAsn": "65000",
                "coppPolicy": "strict",
                "fabricMtu": 9216,
                "firstHopRedundancyProtocol": "hsrp",
                "intraFabricSubnetRange": "10.4.0.0/16",
                "l2HostInterfaceMtu": 9216,
                "networkVlanRange": "2300-2999",
                "nxapi": True,
                "nxapiHttp": True,
                "nxapiHttpPort": 80,
                "nxapiHttpsPort": 443,
                "vpcDomainIdRange": "1-1000",
            })

        return base_settings

    def add_switches_to_fabric(
        self,
        fabric_name: str,
        switches: List[Dict[str, str]],
        platform_type: str = "nx-os",
        preserve_config: bool = True,
        snmp_auth_protocol: str = "md5-aes",
        username: str = "admin",
        password: str = None,
        use_credential_for_write: bool = True,
    ) -> Dict[str, Any]:
        """Add switches to a fabric"""
        if not password:
            raise ValueError("Password is required for switch discovery")

        valid_auth_protocols = [
            "md5", "sha", "md5-des", "md5-aes", "sha-aes", "sha-des",
            "sha-224", "sha-224-aes", "sha-256", "sha-256-aes",
            "sha-384", "sha-384-aes", "sha-512", "sha-512-aes",
        ]

        if snmp_auth_protocol not in valid_auth_protocols:
            raise ValueError(
                f"Invalid SNMP authentication protocol: {snmp_auth_protocol}. "
                f"Valid options: {', '.join(valid_auth_protocols)}"
            )

        payload = {
            "switches": switches,
            "platformType": platform_type,
            "preserveConfig": preserve_config,
            "snmpV3AuthProtocol": snmp_auth_protocol,
            "username": username,
            "password": password,
            "useCredentialForWrite": use_credential_for_write,
        }

        endpoint = f"/fabrics/{fabric_name}/switches"
        response = self._make_request("POST", endpoint, payload=payload, expected_status=200)
        return response

    def list_fabric_switches(self, fabric_name: str) -> List[Dict]:
        """List all switches in a fabric"""
        endpoint = f"/fabrics/{fabric_name}/switches"
        response = self._make_request("GET", endpoint, expected_status=200)
        return response.get("switches", [])


def load_yaml_config(config_file: str) -> Dict[str, Any]:
    """Load YAML configuration file"""
    with open(config_file, 'r') as f:
        return yaml.safe_load(f) or {}


def create_fabric(args: argparse.Namespace) -> None:
    """Create a new fabric"""
    print(f"\n{'='*60}")
    print(f"Creating Fabric: {args.fabric_name}")
    print(f"Fabric Type: {args.fabric_type}")
    print(f"{'='*60}\n")

    # Load credentials from vault
    vault = VaultCredentials(args.vault_file) if args.vault_file else None
    
    nd_password = args.nd_password
    if not nd_password and vault:
        nd_password = vault.get_credential('nexus_dashboard.nd_password')
    
    if not nd_password:
        print("Error: nd_password not provided and not found in vault")
        sys.exit(1)

    client = NexusDashboardClient(args.nd_url, args.nd_username, nd_password)

    # Load configuration from YAML if provided
    fabric_settings = {}
    if args.config_file:
        config = load_yaml_config(args.config_file)
        fabric_settings = config.get('fabric_settings', {})

    try:
        response = client.create_fabric(
            fabric_name=args.fabric_name,
            fabric_type=args.fabric_type,
            fabric_settings=fabric_settings,
        )

        print(f"✓ Fabric '{args.fabric_name}' created successfully!")
        print(f"\nResponse: {json.dumps(response, indent=2)}\n")

    except Exception as e:
        print(f"✗ Error creating fabric: {e}\n")
        sys.exit(1)


def add_devices(args: argparse.Namespace) -> None:
    """Add switches to a fabric"""
    print(f"\n{'='*60}")
    print(f"Adding Switches to Fabric: {args.fabric_name}")
    print(f"{'='*60}\n")

    # Load credentials from vault
    vault = VaultCredentials(args.vault_file) if args.vault_file else None
    
    nd_password = args.nd_password
    if not nd_password and vault:
        nd_password = vault.get_credential('nexus_dashboard.nd_password')
    
    switch_password = args.switch_password
    if not switch_password and vault:
        switch_password = vault.get_credential('nexus_dashboard.switch_password')

    if not nd_password:
        print("Error: nd_password not provided and not found in vault")
        sys.exit(1)

    if not switch_password:
        print("Error: switch_password not provided and not found in vault")
        sys.exit(1)

    client = NexusDashboardClient(args.nd_url, args.nd_username, nd_password)

    # Load switches from YAML configuration
    if args.config_file:
        config = load_yaml_config(args.config_file)
        switches = config.get('switches', [])
    else:
        print("Error: --config-file must be provided with switches configuration")
        sys.exit(1)

    if not switches:
        print("Error: No switches found in configuration")
        sys.exit(1)

    try:
        response = client.add_switches_to_fabric(
            fabric_name=args.fabric_name,
            switches=switches,
            platform_type=args.platform_type,
            preserve_config=args.preserve_config,
            snmp_auth_protocol=args.snmp_auth,
            username=args.switch_username,
            password=switch_password,
            use_credential_for_write=args.use_credential_for_write,
        )

        print(f"✓ Switches added to fabric '{args.fabric_name}' successfully!")
        print(f"\nResponse: {json.dumps(response, indent=2)}\n")

        print("\nAdded Switches:")
        print("-" * 60)
        for switch in switches:
            print(f"  IP: {switch.get('ip'):<20} Hostname: {switch.get('hostname'):<20}")
        print()

    except Exception as e:
        print(f"✗ Error adding switches: {e}\n")
        sys.exit(1)


def list_fabrics_cmd(args: argparse.Namespace) -> None:
    """List all fabrics"""
    print(f"\n{'='*60}")
    print("Listing Nexus Dashboard Fabrics")
    print(f"{'='*60}\n")

    # Load credentials from vault
    vault = VaultCredentials(args.vault_file) if args.vault_file else None
    
    nd_password = args.nd_password
    if not nd_password and vault:
        nd_password = vault.get_credential('nexus_dashboard.nd_password')
    
    if not nd_password:
        print("Error: nd_password not provided and not found in vault")
        sys.exit(1)

    client = NexusDashboardClient(args.nd_url, args.nd_username, nd_password)

    try:
        fabrics = client.list_fabrics()

        if not fabrics:
            print("No fabrics found.\n")
            return

        print(f"Found {len(fabrics)} fabric(s):\n")
        for fabric in fabrics:
            print(f"  Name: {fabric.get('name')}")
            print(f"  Type: {fabric.get('management', {}).get('type', 'N/A')}")
            print(f"  License Tier: {fabric.get('licenseTier', 'N/A')}")
            print(f"  Security Domain: {fabric.get('securityDomain', 'N/A')}")
            print()

    except Exception as e:
        print(f"✗ Error listing fabrics: {e}\n")
        sys.exit(1)


def list_switches_cmd(args: argparse.Namespace) -> None:
    """List switches in a fabric"""
    print(f"\n{'='*60}")
    print(f"Listing Switches in Fabric: {args.fabric_name}")
    print(f"{'='*60}\n")

    # Load credentials from vault
    vault = VaultCredentials(args.vault_file) if args.vault_file else None
    
    nd_password = args.nd_password
    if not nd_password and vault:
        nd_password = vault.get_credential('nexus_dashboard.nd_password')
    
    if not nd_password:
        print("Error: nd_password not provided and not found in vault")
        sys.exit(1)

    client = NexusDashboardClient(args.nd_url, args.nd_username, nd_password)

    try:
        switches = client.list_fabric_switches(args.fabric_name)

        if not switches:
            print(f"No switches found in fabric '{args.fabric_name}'.\n")
            return

        print(f"Found {len(switches)} switch(es):\n")
        print(f"{'Hostname':<20} {'IP':<20} {'Serial Number':<20} {'Role':<15}")
        print("-" * 75)
        for switch in switches:
            print(
                f"{switch.get('hostname', 'N/A'):<20} "
                f"{switch.get('ip', 'N/A'):<20} "
                f"{switch.get('serialNumber', 'N/A'):<20} "
                f"{switch.get('role', 'N/A'):<15}"
            )
        print()

    except Exception as e:
        print(f"✗ Error listing switches: {e}\n")
        sys.exit(1)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Nexus Dashboard Fabric Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create a classic-lan fabric
  python nexus_dashboard.py create-fabric \\
    --nd-url https://nd-lan.rich.ciscolabs.com \\
    --nd-username admin \\
    --vault-file vault-ai-pod.yaml \\
    --fabric-name my-fabric \\
    --fabric-type classicLan

  # Add switches from YAML configuration
  python nexus_dashboard.py add-devices \\
    --nd-url https://nd-lan.rich.ciscolabs.com \\
    --nd-username admin \\
    --vault-file vault-ai-pod.yaml \\
    --fabric-name my-fabric \\
    --config-file fabric_config.yaml

  # Create VXLAN fabric
  python nexus_dashboard.py create-fabric \\
    --nd-url https://nd-lan.rich.ciscolabs.com \\
    --nd-username admin \\
    --vault-file vault-ai-pod.yaml \\
    --fabric-name vxlan-fabric \\
    --fabric-type vxlanEbgp

  # List all fabrics
  python nexus_dashboard.py list-fabrics \\
    --nd-url https://nd-lan.rich.ciscolabs.com \\
    --nd-username admin \\
    --vault-file vault-ai-pod.yaml

  # List switches in a fabric
  python nexus_dashboard.py list-switches \\
    --nd-url https://nd-lan.rich.ciscolabs.com \\
    --nd-username admin \\
    --vault-file vault-ai-pod.yaml \\
    --fabric-name my-fabric
        """,
    )

    # Global arguments
    parser.add_argument(
        "--nd-url",
        required=True,
        help="Nexus Dashboard URL",
    )
    parser.add_argument("--nd-username", required=True, help="Nexus Dashboard API username")
    parser.add_argument(
        "--nd-password",
        help="Nexus Dashboard API password (or load from vault)",
    )
    parser.add_argument(
        "--vault-file",
        help="Path to vault-ai-pod.yaml for credential loading",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Create fabric subcommand
    create_parser = subparsers.add_parser("create-fabric", help="Create a new fabric")
    create_parser.add_argument("--fabric-name", required=True, help="Name for the new fabric")
    create_parser.add_argument(
        "--fabric-type",
        required=True,
        choices=["classicLan", "vxlanIbgp", "vxlanEbgp"],
        help="Type of fabric to create",
    )
    create_parser.add_argument(
        "--config-file",
        help="Path to YAML configuration file with fabric settings",
    )
    create_parser.set_defaults(func=create_fabric)

    # Add devices subcommand
    add_parser = subparsers.add_parser("add-devices", help="Add switches to a fabric")
    add_parser.add_argument("--fabric-name", required=True, help="Target fabric name")
    add_parser.add_argument(
        "--config-file",
        required=True,
        help="Path to YAML configuration file with switches",
    )
    add_parser.add_argument(
        "--platform-type",
        default="nx-os",
        choices=["nx-os", "ios-xe", "ios-xr", "sonic", "apic", "other"],
        help="Platform type (default: nx-os)",
    )
    add_parser.add_argument(
        "--preserve-config",
        action="store_true",
        default=True,
        help="Preserve switch configuration after import (default: True)",
    )
    add_parser.add_argument(
        "--snmp-auth",
        default="md5-aes",
        help="SNMPv3 authentication protocol (default: md5-aes)",
    )
    add_parser.add_argument(
        "--switch-username",
        default="admin",
        help="Switch username for discovery (default: admin)",
    )
    add_parser.add_argument(
        "--switch-password",
        help="Switch password for discovery (or load from vault)",
    )
    add_parser.add_argument(
        "--use-credential-for-write",
        action="store_true",
        default=True,
        help="Use discovery credentials for write operations (default: True)",
    )
    add_parser.set_defaults(func=add_devices)

    # List fabrics subcommand
    list_fabrics_parser = subparsers.add_parser("list-fabrics", help="List all fabrics")
    list_fabrics_parser.set_defaults(func=list_fabrics_cmd)

    # List switches subcommand
    list_switches_parser = subparsers.add_parser("list-switches", help="List switches in a fabric")
    list_switches_parser.add_argument("--fabric-name", required=True, help="Target fabric name")
    list_switches_parser.set_defaults(func=list_switches_cmd)

    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
