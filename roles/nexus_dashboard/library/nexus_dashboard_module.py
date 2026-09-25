#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Ansible module for Nexus Dashboard Fabric Management

This module provides Ansible integration for creating and managing fabrics
in Cisco Nexus Dashboard. It wraps the nexus_dashboard.py CLI tool
to provide Ansible-native operations.

Module Options:
  - action: Operation to perform (create_fabric, add_devices, list_fabrics, list_switches)
  - nd_url: Nexus Dashboard URL
  - nd_username: Nexus Dashboard username
  - nd_password: Nexus Dashboard password
  - fabric_name: Name of the fabric
  - fabric_type: Type of fabric (classicLan, vxlanIbgp, vxlanEbgp)
  - fabric_settings: Dictionary of fabric settings
  - switches: List of switches to add
  - platform_type: Platform type (nx-os, ios-xe, ios-xr, sonic, apic, other)
  - snmp_auth_protocol: SNMPv3 authentication protocol
  - switch_username: Username for switch discovery
  - switch_password: Password for switch discovery
  - preserve_config: Preserve switch configuration (default: True)

Author: Cisco AI PODs
Version: 2.0.0
"""

from ansible.module_utils.basic import AnsibleModule
import json
import yaml
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
import requests
from urllib3 import disable_warnings
from jsonschema import validate, ValidationError

# Disable SSL warnings
disable_warnings()


class ConfigValidator:
    """Validate configurations against JSON schema"""

    def __init__(self, schema_path: Optional[str] = None):
        self.schema = None
        if schema_path and Path(schema_path).exists():
            with open(schema_path, 'r') as f:
                self.schema = json.load(f)

    def validate(self, config: Dict[str, Any], fabric_type: str) -> bool:
        if not self.schema:
            return True
        try:
            validate(instance=config, schema=self.schema)
            return True
        except ValidationError as e:
            raise Exception(f"Validation error: {e.message}")


class VaultCredentials:
    """Load credentials from vault file"""

    def __init__(self, vault_file: str):
        self.vault_file = vault_file
        self.credentials = {}
        self._load_vault()

    def _load_vault(self):
        if Path(self.vault_file).exists():
            with open(self.vault_file, 'r') as f:
                self.credentials = yaml.safe_load(f) or {}

    def get_credential(self, path: str, default: Optional[str] = None) -> Optional[str]:
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
        self.nd_url = nd_url.rstrip("/")
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.verify = verify_ssl

    def _make_request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Dict] = None,
        expected_status: int = 200,
    ) -> Dict[str, Any]:
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
                raise Exception(f"API request failed: {response.status_code} - {response.text}")

            if response.status_code == 202 or not response.text:
                return {"status": "accepted"}

            return response.json()

        except requests.exceptions.RequestException as e:
            raise Exception(f"Request error: {str(e)}")

    def list_fabrics(self, fabric_name: Optional[str] = None) -> List[Dict]:
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
        endpoint = f"/fabrics/{fabric_name}/switches"
        response = self._make_request("GET", endpoint, expected_status=200)
        return response.get("switches", [])


def main():
    module = AnsibleModule(
        argument_spec=dict(
            action=dict(
                type='str',
                required=True,
                choices=['create_fabric', 'add_devices', 'list_fabrics', 'list_switches']
            ),
            nd_url=dict(type='str', required=True),
            nd_username=dict(type='str', required=True),
            nd_password=dict(type='str', no_log=True),
            fabric_name=dict(type='str'),
            fabric_type=dict(
                type='str',
                choices=['classicLan', 'vxlanIbgp', 'vxlanEbgp']
            ),
            fabric_settings=dict(type='dict', default={}),
            switches=dict(type='list', elements='dict', default=[]),
            platform_type=dict(
                type='str',
                default='nx-os',
                choices=['nx-os', 'ios-xe', 'ios-xr', 'sonic', 'apic', 'other']
            ),
            snmp_auth_protocol=dict(type='str', default='md5-aes'),
            switch_username=dict(type='str', default='admin'),
            switch_password=dict(type='str', no_log=True),
            preserve_config=dict(type='bool', default=True),
            use_credential_for_write=dict(type='bool', default=True),
        ),
        required_if=[
            ('action', 'create_fabric', ['fabric_name', 'fabric_type']),
            ('action', 'add_devices', ['fabric_name', 'switches']),
            ('action', 'list_switches', ['fabric_name']),
        ],
    )

    action = module.params['action']
    nd_url = module.params['nd_url']
    nd_username = module.params['nd_username']
    nd_password = module.params['nd_password']

    if not nd_password:
        module.fail_json(msg="nd_password is required")

    try:
        client = NexusDashboardClient(nd_url, nd_username, nd_password)

        if action == 'create_fabric':
            fabric_name = module.params['fabric_name']
            fabric_type = module.params['fabric_type']
            fabric_settings = module.params.get('fabric_settings', {})

            result = client.create_fabric(
                fabric_name=fabric_name,
                fabric_type=fabric_type,
                fabric_settings=fabric_settings,
            )

            module.exit_json(
                changed=True,
                fabric_name=fabric_name,
                fabric_type=fabric_type,
                result=result,
                msg=f"Fabric '{fabric_name}' created successfully"
            )

        elif action == 'add_devices':
            fabric_name = module.params['fabric_name']
            switches = module.params['switches']
            platform_type = module.params['platform_type']
            snmp_auth = module.params['snmp_auth_protocol']
            switch_user = module.params['switch_username']
            switch_pass = module.params['switch_password']
            preserve = module.params['preserve_config']
            use_cred = module.params['use_credential_for_write']

            if not switch_pass:
                module.fail_json(msg="switch_password is required for add_devices")

            result = client.add_switches_to_fabric(
                fabric_name=fabric_name,
                switches=switches,
                platform_type=platform_type,
                preserve_config=preserve,
                snmp_auth_protocol=snmp_auth,
                username=switch_user,
                password=switch_pass,
                use_credential_for_write=use_cred,
            )

            module.exit_json(
                changed=True,
                fabric_name=fabric_name,
                switches_count=len(switches),
                result=result,
                msg=f"Added {len(switches)} switch(es) to fabric '{fabric_name}'"
            )

        elif action == 'list_fabrics':
            fabrics = client.list_fabrics()

            module.exit_json(
                changed=False,
                fabrics=fabrics,
                fabric_count=len(fabrics),
                msg=f"Found {len(fabrics)} fabric(s)"
            )

        elif action == 'list_switches':
            fabric_name = module.params['fabric_name']
            switches = client.list_fabric_switches(fabric_name)

            module.exit_json(
                changed=False,
                fabric_name=fabric_name,
                switches=switches,
                switches_count=len(switches),
                msg=f"Found {len(switches)} switch(es) in fabric '{fabric_name}'"
            )

    except Exception as e:
        module.fail_json(msg=f"Error: {str(e)}")


if __name__ == '__main__':
    main()
