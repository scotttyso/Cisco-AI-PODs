# Nexus Dashboard Fabric Manager

A comprehensive Python-based tool for creating and managing both classic-lan and VXLAN fabrics in Cisco Nexus Dashboard. This role supports YAML-based configuration, vault-based credential management, and JSON schema validation.

## Features

- **Multiple Fabric Types**: Support for classic-lan, VXLAN iBGP, and VXLAN eBGP fabrics
- **YAML Configuration**: Use YAML files (like other AI PODs examples) for fabric and switch configuration
- **Vault Integration**: Load credentials from vault-ai-pod.yaml using vault path notation
- **Schema Validation**: Configuration validation against JSON schema (schemas/source/nexus_dashboard.json)
- **Separate Operations**: Distinct steps for fabric creation and device import
- **SNMPv3 Support**: Flexible SNMP authentication/privacy protocols with MD5-AES default
- **Multi-Platform**: Support for NX-OS, IOS-XE, IOS-XR, SONIC, and APIC platforms

## Installation

### Prerequisites

- Python 3.6+
- Required Python packages:
  ```bash
  pip install requests pyyaml jsonschema
  ```

### Role Location

```
Cisco-AI-PODs/roles/nexus_dashboard/
├── library/
│   └── nexus_dashboard.py          # Main module
├── README.md                         # This file
```

## Configuration Files

### YAML Configuration Examples

Configuration files follow the same pattern as other Cisco AI PODs examples:

#### Classic-LAN Fabric
```yaml
# examples/nexus_dashboard/classic_lan_fabric.yaml
fabric_settings:
  monitoredMode: true
  performanceMonitoring: false
  snmpTrap: true
  cdp: false
  
switches:
  - ip: "10.1.1.10"
    hostname: "leaf1"
    model: "N9K-C93180YC-FX"
    serialNumber: "SAL1234ABCD"
    softwareVersion: "10.3(3)"
```

#### VXLAN Fabric
```yaml
# examples/nexus_dashboard/vxlan_fabric.yaml
fabric_settings:
  bgpAsn: "65001"
  fabricMtu: 9216
  firstHopRedundancyProtocol: hsrp
  networkVlanRange: "2300-2999"
  
switches:
  - ip: "10.1.1.10"
    hostname: "leaf-01"
    model: "N9K-C93180YC-FX"
    serialNumber: "SAL1234ABCD"
    softwareVersion: "10.3(3)"
    switchRole: "leaf"
```

### Vault Configuration

Add credentials to your `vault-ai-pod.yaml`:

```yaml
nexus_dashboard:
  nd_password: "your_nd_password"
  switch_password: "your_switch_password"
```

Then encrypt the vault file:
```bash
ansible-vault encrypt vault-ai-pod.yaml
```

## Usage

### Command Structure

```bash
python roles/nexus_dashboard/library/nexus_dashboard.py [command] [options]
```

### Create a Fabric

#### Classic-LAN Fabric
```bash
python nexus_dashboard.py create-fabric \
  --nd-url https://nd-lan.rich.ciscolabs.com \
  --nd-username admin \
  --vault-file vault-ai-pod.yaml \
  --fabric-name my-classic-lan \
  --fabric-type classicLan \
  --config-file examples/nexus_dashboard/classic_lan_fabric.yaml
```

#### VXLAN eBGP Fabric
```bash
python nexus_dashboard.py create-fabric \
  --nd-url https://nd-lan.rich.ciscolabs.com \
  --nd-username admin \
  --vault-file vault-ai-pod.yaml \
  --fabric-name my-vxlan \
  --fabric-type vxlanEbgp \
  --config-file examples/nexus_dashboard/vxlan_fabric.yaml
```

#### VXLAN iBGP Fabric
```bash
python nexus_dashboard.py create-fabric \
  --nd-url https://nd-lan.rich.ciscolabs.com \
  --nd-username admin \
  --vault-file vault-ai-pod.yaml \
  --fabric-name my-vxlan-ibgp \
  --fabric-type vxlanIbgp \
  --config-file examples/nexus_dashboard/vxlan_ibgp_fabric.yaml
```

### Add Switches to Fabric

```bash
python nexus_dashboard.py add-devices \
  --nd-url https://nd-lan.rich.ciscolabs.com \
  --nd-username admin \
  --vault-file vault-ai-pod.yaml \
  --fabric-name my-classic-lan \
  --config-file examples/nexus_dashboard/classic_lan_fabric.yaml \
  --platform-type nx-os \
  --snmp-auth md5-aes
```

### List Fabrics

```bash
python nexus_dashboard.py list-fabrics \
  --nd-url https://nd-lan.rich.ciscolabs.com \
  --nd-username admin \
  --vault-file vault-ai-pod.yaml
```

### List Switches in Fabric

```bash
python nexus_dashboard.py list-switches \
  --nd-url https://nd-lan.rich.ciscolabs.com \
  --nd-username admin \
  --vault-file vault-ai-pod.yaml \
  --fabric-name my-classic-lan
```

## Fabric Types

### Classic-LAN
- Traditional network configuration management
- Monitored mode available (monitoring without active deployment)
- Ideal for brownfield/legacy network integration
- Supports MPLS handoff for WAN integration
- Default settings optimize for monitoring

Example settings:
```yaml
monitoredMode: true
performanceMonitoring: false
snmpTrap: true
coppPolicy: manual
```

### VXLAN eBGP
- External BGP-based VXLAN overlay
- Multi-hop eBGP between leaf and spine
- Suitable for multi-site deployments
- Requires BGP ASN configuration
- Enterprise fabric with advanced features

Example settings:
```yaml
bgpAsn: "65001"
fabricMtu: 9216
firstHopRedundancyProtocol: hsrp
networkVlanRange: "2300-2999"
coppPolicy: strict
```

### VXLAN iBGP
- Internal BGP-based VXLAN overlay
- Single BGP domain architecture
- Simpler deployment than eBGP
- All devices in same ASN
- Preferred for single-site deployments

Example settings:
```yaml
bgpAsn: "65000"
l2VniRange: "30000-49000"
l3VniRange: "50000-59000"
fabricMtu: 9216
```

## SNMPv3 Authentication Protocols

Supported authentication and privacy combinations:

| Protocol | Authentication | Privacy | Recommended |
|----------|----------------|---------|-------------|
| md5 | MD5 | None | ❌ |
| sha | SHA-1 | None | ❌ |
| md5-des | MD5 | DES | ❌ |
| **md5-aes** | MD5 | AES | ✓ Default |
| sha-aes | SHA-1 | AES | ✓ Good |
| sha-des | SHA-1 | DES | ❌ |
| sha-224 | SHA-224 | None | ❌ |
| sha-224-aes | SHA-224 | AES | ✓ Good |
| sha-256 | SHA-256 | None | ❌ |
| sha-256-aes | SHA-256 | AES | ✓ Better |
| sha-384 | SHA-384 | None | ❌ |
| sha-384-aes | SHA-384 | AES | ✓ Better |
| sha-512 | SHA-512 | None | ❌ |
| sha-512-aes | SHA-512 | AES | ✓ Best |

### Using Different Auth Protocols

```bash
# SHA-256-AES (recommended for security)
python nexus_dashboard.py add-devices \
  --nd-url https://nd-lan.rich.ciscolabs.com \
  --nd-username admin \
  --vault-file vault-ai-pod.yaml \
  --fabric-name my-fabric \
  --config-file fabric_config.yaml \
  --snmp-auth sha-256-aes

# SHA-512-AES (maximum security)
python nexus_dashboard.py add-devices \
  --nd-url https://nd-lan.rich.ciscolabs.com \
  --nd-username admin \
  --vault-file vault-ai-pod.yaml \
  --fabric-name my-fabric \
  --config-file fabric_config.yaml \
  --snmp-auth sha-512-aes
```

## Configuration Examples

### Example 1: Basic Classic-LAN Fabric

**Configuration file** (classic_lan_fabric.yaml):
```yaml
fabric_settings:
  monitoredMode: true
  performanceMonitoring: false
  snmpTrap: true
  cdp: false

switches:
  - ip: "10.1.1.10"
    hostname: "leaf1"
    model: "N9K-C93180YC-FX"
    serialNumber: "SAL1234ABCD"
    softwareVersion: "10.3(3)"
  - ip: "10.1.1.11"
    hostname: "leaf2"
    model: "N9K-C93180YC-FX"
    serialNumber: "SAL1234ABCE"
    softwareVersion: "10.3(3)"
```

**Vault** (vault-ai-pod.yaml):
```yaml
nexus_dashboard:
  nd_password: "nd_admin_password"
  switch_password: "switch_admin_password"
```

**Commands**:
```bash
# Step 1: Create fabric
python nexus_dashboard.py create-fabric \
  --nd-url https://nd-lan.rich.ciscolabs.com \
  --nd-username admin \
  --vault-file vault-ai-pod.yaml \
  --fabric-name basic-classic-lan \
  --fabric-type classicLan

# Step 2: Add switches
python nexus_dashboard.py add-devices \
  --nd-url https://nd-lan.rich.ciscolabs.com \
  --nd-username admin \
  --vault-file vault-ai-pod.yaml \
  --fabric-name basic-classic-lan \
  --config-file classic_lan_fabric.yaml
```

### Example 2: Production VXLAN Fabric with High Security

**Configuration file** (prod_vxlan_fabric.yaml):
```yaml
fabric_settings:
  bgpAsn: "65000"
  fabricMtu: 9216
  firstHopRedundancyProtocol: hsrp
  networkVlanRange: "2300-2999"
  l2VniRange: "30000-49000"
  l3VniRange: "50000-59000"
  performanceMonitoring: true
  realTimeInterfaceStatisticsCollection: true
  snmpTrap: true
  coppPolicy: strict
  nxapi: true
  nxapiHttp: false
  nxapiHttpsPort: 443

switches:
  - ip: "10.1.1.10"
    hostname: "prod-leaf-01"
    model: "N9K-C93180YC-FX"
    serialNumber: "SAL2024ABCD"
    softwareVersion: "10.3(3)"
    switchRole: "leaf"
  - ip: "10.1.1.11"
    hostname: "prod-leaf-02"
    model: "N9K-C93180YC-FX"
    serialNumber: "SAL2024ABCE"
    softwareVersion: "10.3(3)"
    switchRole: "leaf"
  - ip: "10.1.1.20"
    hostname: "prod-spine-01"
    model: "N9K-C9364D-GX2A"
    serialNumber: "SAL2024ABCF"
    softwareVersion: "10.3(3)"
    switchRole: "spine"
  - ip: "10.1.1.21"
    hostname: "prod-spine-02"
    model: "N9K-C9364D-GX2A"
    serialNumber: "SAL2024ABCG"
    softwareVersion: "10.3(3)"
    switchRole: "spine"
```

**Commands**:
```bash
# Create production VXLAN fabric
python nexus_dashboard.py create-fabric \
  --nd-url https://nd-lan.rich.ciscolabs.com \
  --nd-username admin \
  --vault-file vault-ai-pod.yaml \
  --fabric-name prod-vxlan-01 \
  --fabric-type vxlanIbgp \
  --config-file prod_vxlan_fabric.yaml

# Add switches with high security
python nexus_dashboard.py add-devices \
  --nd-url https://nd-lan.rich.ciscolabs.com \
  --nd-username admin \
  --vault-file vault-ai-pod.yaml \
  --fabric-name prod-vxlan-01 \
  --config-file prod_vxlan_fabric.yaml \
  --platform-type nx-os \
  --snmp-auth sha-256-aes \
  --preserve-config true
```

## Schema Validation

The configuration is validated against the JSON schema at `schemas/source/nexus_dashboard.json`.

### Validation Features

- **Fabric Settings**: Validates fabric-specific settings based on type
- **Switch Configuration**: Validates required and optional switch fields
- **SNMP Protocols**: Validates SNMP authentication protocol selection
- **IP Addresses**: Validates IPv4 format for switch IPs
- **VNI Ranges**: Validates VXLAN VNI ranges format

### Validation Examples

**Valid configuration**:
```yaml
fabric_settings:
  bgpAsn: "65000"
  fabricMtu: 9216
  
switches:
  - ip: "10.1.1.10"
    hostname: "leaf1"
    model: "N9K-C93180YC-FX"
    serialNumber: "SAL1234ABCD"
    softwareVersion: "10.3(3)"
```

**Invalid configuration** (will fail validation):
```yaml
switches:
  - ip: "not.an.ip"           # ❌ Invalid IP format
    hostname: ""              # ❌ Empty hostname
    model: "N9K-C93180YC-FX"
    serialNumber: "SAL1234ABCD"
    softwareVersion: "10.3(3)"
```

## Credential Management

### Vault File Structure

```yaml
nexus_dashboard:
  nd_password: "nexus_dashboard_admin_password"
  switch_password: "switch_discovery_password"
```

### Loading Credentials

The tool uses vault path notation (dot notation) to load credentials:

```python
# Loads nexus_dashboard.nd_password from vault
vault.get_credential('nexus_dashboard.nd_password')

# Loads nexus_dashboard.switch_password from vault
vault.get_credential('nexus_dashboard.switch_password')
```

### Environment Variables

Credentials can also be passed directly via command line (useful for CI/CD):

```bash
python nexus_dashboard.py create-fabric \
  --nd-url https://nd-lan.rich.ciscolabs.com \
  --nd-username admin \
  --nd-password direct_password \
  --fabric-name my-fabric \
  --fabric-type classicLan
```

Priority order for credential loading:
1. Command-line arguments (highest priority)
2. Vault file (recommended for production)
3. Error if neither provided

## Python API Usage

You can also use the module as a Python library:

```python
from nexus_dashboard import NexusDashboardClient, VaultCredentials

# Load vault credentials
vault = VaultCredentials('vault-ai-pod.yaml')
nd_password = vault.get_credential('nexus_dashboard.nd_password')

# Initialize client
client = NexusDashboardClient(
    nd_url="https://nd-lan.rich.ciscolabs.com",
    username="admin",
    password=nd_password
)

# Create fabric
fabric = client.create_fabric(
    fabric_name="my-fabric",
    fabric_type="classicLan",
    fabric_settings={
        "monitoredMode": True,
        "snmpTrap": True
    }
)

# Add switches
switches = [
    {
        "ip": "10.1.1.10",
        "hostname": "leaf1",
        "model": "N9K-C93180YC-FX",
        "serialNumber": "SAL1234ABCD",
        "softwareVersion": "10.3(3)"
    }
]

response = client.add_switches_to_fabric(
    fabric_name="my-fabric",
    switches=switches,
    username="admin",
    password="switch_password"
)

# List fabrics
fabrics = client.list_fabrics()

# List switches
switches = client.list_fabric_switches("my-fabric")
```

## Troubleshooting

### Connection Issues
- Verify Nexus Dashboard URL is correct and accessible
- Check network connectivity from your machine to ND cluster
- Ensure credentials are correct

### Validation Errors
- Check YAML syntax with online YAML validators
- Verify all required fields are present
- Ensure IP addresses are in valid IPv4 format
- Check fabric_type is one of: classicLan, vxlanIbgp, vxlanEbgp

### Authentication Errors
- Verify vault file path is correct
- Check vault file contains nexus_dashboard credentials
- Ensure credentials have fabric-admin role
- Verify switch credentials work on at least one switch

### SNMP Protocol Errors
- Use one of the supported SNMP protocols from the table above
- Default md5-aes is recommended
- For higher security, use sha-256-aes or sha-512-aes

### Switch Discovery Issues
- Verify switch management IP is reachable from ND cluster
- Check switch credentials are correct (use a single switch first)
- Ensure switches support SNMPv3
- Verify firewall allows SNMP communication

## Best Practices

1. **Start with a single switch** to verify connectivity and credentials
2. **Use YAML files** for configuration (version control friendly)
3. **Store passwords in vault** and encrypt with ansible-vault
4. **Use appropriate auth protocols**: md5-aes minimum, sha-256-aes for production
5. **Enable performance monitoring** in production fabrics
6. **Document fabric settings** and maintain backup configurations
7. **Test in dev/test** before production deployment
8. **Monitor fabric health** after creation and switch addition

## Schema Files

Schema files are located in `schemas/source/`:

- `nexus_dashboard.json` - Nexus Dashboard-specific schemas
- `cisco-ai-pods.json` - Integration with main AI PODs schema

These files provide:
- Configuration validation
- IDE autocomplete (in supported tools)
- Documentation of valid options
- Type checking for YAML files

## Support

For issues or questions:

1. Review error messages carefully
2. Check configuration examples in `examples/nexus_dashboard/`
3. Validate YAML syntax
4. Verify vault credentials
5. Test with `list-fabrics` command to verify API connectivity

## Related Documentation

- [Nexus Dashboard API](https://nd-lan.rich.ciscolabs.com/swagger)
- [Cisco Nexus Dashboard User Guide](https://www.cisco.com/c/en/us/support/cloud-systems-management/nexus-dashboard/series.html)
- [JSON Schema Documentation](https://json-schema.org/)
- [Ansible Vault Documentation](https://docs.ansible.com/ansible/latest/user_guide/vault.html)

## Version

2.0.0 (Multi-fabric support, YAML configuration, schema validation)

## Authors

Cisco AI PODs

## License

See LICENSE file in repository
