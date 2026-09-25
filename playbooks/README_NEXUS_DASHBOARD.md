# Nexus Dashboard Ansible Playbooks

This directory contains Ansible playbooks for managing Nexus Dashboard fabrics. Both standalone playbooks and a master playbook are provided for flexibility.

## Prerequisites

1. **Ansible**: >= 2.9
2. **Python 3.6+** with required packages:
   - requests
   - pyyaml
   - jsonschema
   - urllib3

3. **Vault credentials**: `vault-ai-pod.yaml` with Nexus Dashboard credentials

## Setup

### 1. Install Dependencies

```bash
pip install requests pyyaml jsonschema urllib3
```

### 2. Configure Vault File

Create `vault-ai-pod.yaml` with Nexus Dashboard credentials:

```yaml
nexus_dashboard:
  nd_password: "your_nd_admin_password"
  switch_password: "your_switch_discovery_password"
```

Encrypt the vault file:

```bash
ansible-vault encrypt vault-ai-pod.yaml
```

### 3. Prepare Configuration Files

Create YAML configuration files in `examples/nexus_dashboard/` with fabric settings and switches.

## Playbooks

### 1. deploy_nexus_dashboard.yaml (Master Playbook)

Universal playbook supporting all operations. Recommended for most use cases.

**Usage:**

```bash
# Create a classic-lan fabric
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=create_fabric \
  -e fabric_name=my-fabric \
  -e fabric_type=classicLan

# Create fabric with custom settings from YAML
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=create_fabric \
  -e fabric_name=vxlan-fabric \
  -e fabric_type=vxlanEbgp \
  -e config_file=examples/nexus_dashboard/vxlan_fabric.yaml

# Add switches to fabric
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=add_devices \
  -e fabric_name=my-fabric \
  -e config_file=examples/nexus_dashboard/classic_lan_fabric.yaml

# List all fabrics
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=list_fabrics

# List switches in specific fabric
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=list_switches \
  -e fabric_name=my-fabric
```

**Parameters:**

- `action`: Required. Operation to perform:
  - `create_fabric` (requires: fabric_name, fabric_type)
  - `add_devices` (requires: fabric_name, config_file)
  - `list_fabrics`
  - `list_switches` (requires: fabric_name)

- `fabric_name`: Name of the fabric
- `fabric_type`: Type of fabric (classicLan, vxlanIbgp, vxlanEbgp)
- `config_file`: Path to YAML configuration file
- `nd_url`: Nexus Dashboard URL (default: https://nd-lan.rich.ciscolabs.com)
- `nd_username`: Nexus Dashboard username (default: admin)
- `vault_file`: Path to vault-ai-pod.yaml

### 2. nexus_dashboard_create_fabric.yaml

Create a new fabric (standalone).

```bash
ansible-playbook playbooks/nexus_dashboard_create_fabric.yaml \
  -e fabric_name=my-fabric \
  -e fabric_type=classicLan \
  -e config_file=examples/nexus_dashboard/classic_lan_fabric.yaml
```

### 3. nexus_dashboard_add_devices.yaml

Add switches to an existing fabric (standalone).

```bash
ansible-playbook playbooks/nexus_dashboard_add_devices.yaml \
  -e fabric_name=my-fabric \
  -e config_file=examples/nexus_dashboard/classic_lan_fabric.yaml
```

### 4. nexus_dashboard_list_fabrics.yaml

List all fabrics (standalone).

```bash
ansible-playbook playbooks/nexus_dashboard_list_fabrics.yaml
```

### 5. nexus_dashboard_list_switches.yaml

List switches in a specific fabric (standalone).

```bash
ansible-playbook playbooks/nexus_dashboard_list_switches.yaml \
  -e fabric_name=my-fabric
```

## Environment Variables

You can set these environment variables instead of passing them as arguments:

```bash
export ND_URL="https://nd-lan.rich.ciscolabs.com"
export ND_USERNAME="admin"

ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=list_fabrics
```

## Using with Vault

Run playbooks with vault password:

```bash
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=create_fabric \
  -e fabric_name=my-fabric \
  -e fabric_type=classicLan \
  --ask-vault-pass
```

Or use vault password file:

```bash
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=create_fabric \
  -e fabric_name=my-fabric \
  -e fabric_type=classicLan \
  --vault-password-file=/path/to/vault/password
```

## Configuration Examples

### Classic-LAN Fabric

**File: `examples/nexus_dashboard/classic_lan_fabric.yaml`**

```yaml
fabric_settings:
  monitoredMode: true
  performanceMonitoring: false
  snmpTrap: true

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

### VXLAN eBGP Fabric

**File: `examples/nexus_dashboard/vxlan_fabric.yaml`**

```yaml
fabric_settings:
  bgpAsn: 65001
  fabricMtu: 9216
  firstHopRedundancyProtocol: hsrp
  networkVlanRange: "2300-2999"
  performanceMonitoring: true
  snmpTrap: true

switches:
  - ip: "10.2.1.10"
    hostname: "leaf1"
    model: "N9K-C93180YC-FX"
    serialNumber: "SAL2000ABCD"
    softwareVersion: "10.3(3)"
    switchRole: "leaf"
  - ip: "10.2.1.11"
    hostname: "leaf2"
    model: "N9K-C93180YC-FX"
    serialNumber: "SAL2000ABCE"
    softwareVersion: "10.3(3)"
    switchRole: "leaf"
  - ip: "10.2.1.1"
    hostname: "spine1"
    model: "N9K-C93180YC-FX"
    serialNumber: "SAL2000SPINE1"
    softwareVersion: "10.3(3)"
    switchRole: "spine"
  - ip: "10.2.1.2"
    hostname: "spine2"
    model: "N9K-C93180YC-FX"
    serialNumber: "SAL2000SPINE2"
    softwareVersion: "10.3(3)"
    switchRole: "spine"
```

### VXLAN iBGP Fabric

**File: `examples/nexus_dashboard/vxlan_ibgp_fabric.yaml`**

```yaml
fabric_settings:
  bgpAsn: 65000
  fabricMtu: 9216
  firstHopRedundancyProtocol: vrrp
  intraFabricSubnetRange: "10.4.0.0/16"
  l2VniRange: "20000-20999"
  l3VniRange: "30000-30999"
  performanceMonitoring: true

switches:
  - ip: "10.3.1.10"
    hostname: "leaf1"
    model: "N9K-C93180YC-FX"
    serialNumber: "SAL3000ABCD"
    softwareVersion: "10.3(3)"
    switchRole: "leaf"
  - ip: "10.3.1.11"
    hostname: "leaf2"
    model: "N9K-C93180YC-FX"
    serialNumber: "SAL3000ABCE"
    softwareVersion: "10.3(3)"
    switchRole: "leaf"
```

## Workflow Examples

### Complete Deployment Flow

```bash
# 1. Create classic-lan fabric
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=create_fabric \
  -e fabric_name=production-fabric \
  -e fabric_type=classicLan

# 2. Add switches to fabric
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=add_devices \
  -e fabric_name=production-fabric \
  -e config_file=examples/nexus_dashboard/classic_lan_fabric.yaml \
  -e snmp_auth_protocol=sha-aes

# 3. Verify fabric creation
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=list_fabrics

# 4. Verify switches added
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=list_switches \
  -e fabric_name=production-fabric
```

### Multi-Fabric Deployment

```bash
# Create multiple fabrics in sequence
for fabric_type in classicLan vxlanIbgp vxlanEbgp; do
  ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
    -e action=create_fabric \
    -e fabric_name="fabric-$fabric_type" \
    -e fabric_type="$fabric_type"
done
```

## Troubleshooting

### Connection Issues

```bash
# Test connectivity to Nexus Dashboard
ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=list_fabrics \
  -v
```

### Vault Password Issues

```bash
# Ensure vault file is encrypted
ansible-vault view vault-ai-pod.yaml --ask-vault-pass

# Re-encrypt vault file if needed
ansible-vault encrypt vault-ai-pod.yaml
```

### Module Not Found

Ensure `roles/nexus_dashboard/library/` is in the Ansible module path:

```bash
# Set ANSIBLE_LIBRARY environment variable
export ANSIBLE_LIBRARY=./roles/nexus_dashboard/library:$ANSIBLE_LIBRARY

ansible-playbook playbooks/deploy_nexus_dashboard.yaml \
  -e action=list_fabrics
```

## Comparison: Python CLI vs Ansible Playbooks

| Operation | Python CLI | Ansible |
|-----------|-----------|---------|
| Create Fabric | `python nexus_dashboard.py create-fabric` | `ansible-playbook deploy_nexus_dashboard.yaml -e action=create_fabric` |
| Add Switches | `python nexus_dashboard.py add-devices` | `ansible-playbook deploy_nexus_dashboard.yaml -e action=add_devices` |
| List Fabrics | `python nexus_dashboard.py list-fabrics` | `ansible-playbook deploy_nexus_dashboard.yaml -e action=list_fabrics` |
| List Switches | `python nexus_dashboard.py list-switches` | `ansible-playbook deploy_nexus_dashboard.yaml -e action=list_switches` |

**Choose Python CLI for:**
- Quick one-off operations
- Shell scripting automation
- CI/CD pipelines without Ansible

**Choose Ansible for:**
- Infrastructure-as-Code workflows
- Integration with existing Ansible playbooks
- Complex orchestration scenarios
- Multi-host deployments
- Idempotent operations

## Best Practices

1. **Use Vault for Credentials**: Never hardcode passwords in playbooks or config files
2. **Version Control**: Keep configuration files in git
3. **Test First**: Test with `list_fabrics` before creating
4. **Use Variables**: Define reusable variables in group_vars or host_vars
5. **Document Fabrics**: Add comments in config files explaining fabric purpose
6. **Monitor Results**: Check debug output for API responses

## Support

For issues or questions:

1. Check the README.md in roles/nexus_dashboard/
2. Review examples in examples/nexus_dashboard/
3. Verify vault file credentials
4. Enable verbose output with `-v` or `-vv`
