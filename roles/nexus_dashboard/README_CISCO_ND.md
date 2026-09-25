# Nexus Dashboard Ansible Role

Ansible role for managing Cisco Nexus Dashboard fabrics using the official `cisco.nd` collection.

## Overview

This role provides a unified interface for managing Nexus Dashboard fabrics through Ansible playbooks, supporting all fabric types (classic-LAN, VXLAN iBGP, VXLAN eBGP) with YAML-based configuration.

## Requirements

### Ansible

- Ansible >= 2.9
- `cisco.nd` collection >= 1.0.0

### Python

Python 3.6+ with standard libraries (requests, etc.)

### Installation

**1. Install Ansible**

```bash
pip install ansible
```

**2. Install cisco.nd Collection**

```bash
# From Galaxy (recommended)
ansible-galaxy collection install cisco.nd

# Or from GitHub
ansible-galaxy collection install git+https://github.com/CiscoDevNet/ansible-nd.git
```

**3. Verify Installation**

```bash
ansible-galaxy collection list | grep cisco.nd
```

## Configuration

### 1. Create Vault File

Create `vault-ai-pod.yaml` with Nexus Dashboard credentials:

```yaml
nexus_dashboard:
  nd_password: "your_nd_admin_password"
  switch_password: "your_switch_discovery_password"
```

Encrypt the vault:

```bash
ansible-vault encrypt vault-ai-pod.yaml
```

### 2. Prepare Configuration Files

Create YAML files in `examples/nexus_dashboard/` for your fabric deployments:

**Classic-LAN Example** (`examples/nexus_dashboard/classic_lan_fabric.yaml`):

```yaml
fabric_settings:
  monitoredMode: true
  performanceMonitoring: false
  snmpTrap: true
  coppPolicy: manual

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

**VXLAN eBGP Example** (`examples/nexus_dashboard/vxlan_fabric.yaml`):

```yaml
fabric_settings:
  bgpAsn: 65001
  fabricMtu: 9216
  firstHopRedundancyProtocol: hsrp
  networkVlanRange: "2300-2999"
  performanceMonitoring: true

switches:
  - ip: "10.2.1.10"
    hostname: "leaf1"
    model: "N9K-C93180YC-FX"
    serialNumber: "SAL2000ABCD"
    softwareVersion: "10.3(3)"
    switchRole: "leaf"
  - ip: "10.2.1.1"
    hostname: "spine1"
    model: "N9K-C93180YC-FX"
    serialNumber: "SAL2000SPINE1"
    softwareVersion: "10.3(3)"
    switchRole: "spine"
```

## Usage

### Create a Fabric

```bash
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=create_fabric \
  -e fabric_name=my-fabric \
  -e fabric_type=classicLan \
  --ask-vault-pass
```

With custom settings from file:

```bash
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=create_fabric \
  -e fabric_name=vxlan-fabric \
  -e fabric_type=vxlanEbgp \
  -e config_file=examples/nexus_dashboard/vxlan_fabric.yaml \
  --ask-vault-pass
```

### Add Switches to Fabric

```bash
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=add_devices \
  -e fabric_name=my-fabric \
  -e config_file=examples/nexus_dashboard/classic_lan_fabric.yaml \
  --ask-vault-pass
```

### List All Fabrics

```bash
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=list_fabrics \
  --ask-vault-pass
```

### List Switches in Fabric

```bash
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=list_switches \
  -e fabric_name=my-fabric \
  --ask-vault-pass
```

## Playbooks

### deploy_nexus_dashboard.yaml

Master playbook supporting all operations. Recommended for most use cases.

**Parameters:**

- `action`: Required. Operation to perform
  - `create_fabric` (requires: fabric_name, fabric_type)
  - `add_devices` (requires: fabric_name, config_file)
  - `list_fabrics`
  - `list_switches` (requires: fabric_name)

- `fabric_name`: Name of the fabric
- `fabric_type`: Type (classicLan, vxlanIbgp, vxlanEbgp)
- `config_file`: Path to YAML configuration file
- `nd_url`: Nexus Dashboard URL (default: https://nd-lan.rich.ciscolabs.com)
- `nd_username`: Nexus Dashboard username (default: admin)
- `vault_file`: Path to vault-ai-pod.yaml
- `platform_type`: Platform type (default: nx-os)
- `snmp_auth_protocol`: SNMPv3 protocol (default: md5-aes)
- `switch_username`: Switch discovery username (default: admin)

### Individual Playbooks

For specific operations:

- `nexus_dashboard_create_fabric.yaml` - Create only
- `nexus_dashboard_add_devices.yaml` - Add devices only
- `nexus_dashboard_list_fabrics.yaml` - List fabrics only
- `nexus_dashboard_list_switches.yaml` - List switches only

## Role Variables

Role defaults (override with -e flags):

```yaml
nd_url: "https://nd-lan.rich.ciscolabs.com"
nd_username: "admin"
vault_file: "vault-ai-pod.yaml"
platform_type: "nx-os"
snmp_auth_protocol: "md5-aes"
switch_username: "admin"
preserve_config: true
```

## Fabric Types

### classicLan

Traditional network management. Suitable for brownfield deployments.

Default settings:
- `monitoredMode: true`
- `coppPolicy: manual`
- `nxapi: false`

### vxlanIbgp

VXLAN with internal BGP. Single ASN, single domain.

Default settings:
- `bgpAsn: 65000`
- `coppPolicy: strict`
- `fabricMtu: 9216`
- `nxapi: true`

### vxlanEbgp

VXLAN with external BGP. Multi-hop, multi-site capable.

Default settings:
- `bgpAsn: 65000` (override per deployment)
- `coppPolicy: strict`
- `fabricMtu: 9216`
- `nxapi: true`

## SNMPv3 Authentication Protocols

Supported protocols (default: md5-aes):

- md5, sha
- md5-des, md5-aes
- sha-des, sha-aes
- sha-224, sha-224-aes
- sha-256, sha-256-aes
- sha-384, sha-384-aes
- sha-512, sha-512-aes

## Workflow Examples

### Complete Deployment

```bash
# 1. Create classic-lan fabric
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=create_fabric \
  -e fabric_name=prod-fabric \
  -e fabric_type=classicLan \
  --ask-vault-pass

# 2. Add switches
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=add_devices \
  -e fabric_name=prod-fabric \
  -e config_file=examples/nexus_dashboard/classic_lan_fabric.yaml \
  --ask-vault-pass

# 3. Verify
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=list_switches \
  -e fabric_name=prod-fabric \
  --ask-vault-pass
```

### Multi-Fabric Deployment

```bash
for fabric_type in classicLan vxlanIbgp vxlanEbgp; do
  ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
    -e action=create_fabric \
    -e fabric_name="fabric-$fabric_type" \
    -e fabric_type="$fabric_type" \
    --ask-vault-pass
done
```

## Environment Variables

Set these to avoid passing arguments repeatedly:

```bash
export ND_URL="https://nd-lan.rich.ciscolabs.com"
export ND_USERNAME="admin"

ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=list_fabrics \
  --ask-vault-pass
```

## Vault Integration

### Store Credentials Securely

```bash
# Create vault file
cat > vault-ai-pod.yaml << EOF
nexus_dashboard:
  nd_password: "my_nd_password"
  switch_password: "my_switch_password"
EOF

# Encrypt
ansible-vault encrypt vault-ai-pod.yaml

# Run playbooks (will prompt for vault password)
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=create_fabric \
  -e fabric_name=my-fabric \
  -e fabric_type=classicLan \
  --ask-vault-pass
```

### Use Vault Password File

```bash
# Create password file
echo "my_vault_password" > ~/.vault_pass

# Set permissions
chmod 600 ~/.vault_pass

# Run playbooks
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=create_fabric \
  -e fabric_name=my-fabric \
  -e fabric_type=classicLan \
  --vault-password-file ~/.vault_pass
```

## Troubleshooting

### Collection Not Found

```bash
# Ensure cisco.nd is installed
ansible-galaxy collection list | grep cisco.nd

# If not, install it
ansible-galaxy collection install cisco.nd
```

### Connection Issues

```bash
# Test connectivity
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=list_fabrics \
  -v
```

### Vault Issues

```bash
# View vault file
ansible-vault view vault-ai-pod.yaml --ask-vault-pass

# Re-encrypt if needed
ansible-vault encrypt vault-ai-pod.yaml
```

### Debug Output

Run with verbose output:

```bash
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=list_fabrics \
  -vvv
```

## Integration with Cisco AI PODs

This role follows Cisco AI PODs conventions:

- **YAML Configuration**: Consistent with other Cisco AI PODs examples
- **Vault-Based Credentials**: Secure credential management via ansible-vault
- **Playbook Structure**: Follows Cisco AI PODs playbook patterns
- **Schema Validation**: Integrates with cisco-ai-pods.json schema

## Related Documentation

- [Cisco ND Ansible Collection](https://github.com/CiscoDevNet/ansible-nd)
- [Cisco Nexus Dashboard API](https://developer.cisco.com/docs/nexus-dashboard/)
- [Ansible Galaxy](https://galaxy.ansible.com/ui/repo/published/cisco/nd/)

## Support

For issues:

1. Check the Cisco ND collection documentation
2. Review examples in `examples/nexus_dashboard/`
3. Verify credentials in vault file
4. Enable verbose output with `-v` or `-vv`
5. Check Cisco DevNet GitHub for known issues

## License

This role is part of the Cisco AI PODs project and follows the same licensing as the parent project.
