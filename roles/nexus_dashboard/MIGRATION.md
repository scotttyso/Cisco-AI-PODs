# Nexus Dashboard Role Refactoring Summary

## Overview
The `nexus_dashboard_classic_lan` role has been refactored and expanded into the `nexus_dashboard` role with support for multiple fabric types, YAML configuration, vault integration, and schema validation.

## What Changed

### Role Name
- **Old**: `Cisco-AI-PODs/roles/nexus_dashboard_classic_lan/`
- **New**: `Cisco-AI-PODs/roles/nexus_dashboard/`

### Configuration Format
- **Old**: JSON files (switches.json, fabric_settings.json)
- **New**: YAML files (like other Cisco AI PODs examples)

### Credential Management
- **Old**: Command-line passwords
- **New**: Vault-based credentials loaded from `vault-ai-pod.yaml`

### Fabric Types Supported
- **Old**: Classic-LAN only
- **New**: 
  - Classic-LAN
  - VXLAN iBGP
  - VXLAN eBGP

### Schema Integration
- **Old**: No schema validation
- **New**: 
  - `schemas/source/nexus_dashboard.json` - Nexus Dashboard-specific schema
  - `schemas/source/cisco-ai-pods.json` - Updated to include nexus_dashboard

## Directory Structure

```
Cisco-AI-PODs/
├── roles/
│   └── nexus_dashboard/
│       ├── library/
│       │   └── nexus_dashboard.py          # Main module (v2.0.0)
│       └── README.md                       # Complete documentation
├── examples/
│   └── nexus_dashboard/
│       ├── classic_lan_fabric.yaml         # Classic-LAN example
│       ├── vxlan_fabric.yaml               # VXLAN eBGP example
│       └── vxlan_ibgp_fabric.yaml          # VXLAN iBGP example
├── schemas/
│   └── source/
│       ├── nexus_dashboard.json            # Nexus Dashboard schema
│       └── cisco-ai-pods.json              # Updated main schema
└── examples/
    └── vault.example.yaml                  # Updated with nexus_dashboard
```

## New Features

### 1. YAML Configuration
Configuration files now follow the Cisco AI PODs pattern:

```yaml
# examples/nexus_dashboard/classic_lan_fabric.yaml
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
```

### 2. Vault Integration
Credentials are stored in vault file and loaded via path notation:

```yaml
# examples/vault.example.yaml
nexus_dashboard:
  nd_password: "your_password"
  switch_password: "your_password"
```

Usage:
```bash
python nexus_dashboard.py create-fabric \
  --nd-url https://nd-lan.rich.ciscolabs.com \
  --nd-username admin \
  --vault-file vault-ai-pod.yaml \
  --fabric-name my-fabric \
  --fabric-type classicLan
```

### 3. Multiple Fabric Types
- **classicLan**: Traditional network, ideal for brownfield deployments
- **vxlanIbgp**: VXLAN with internal BGP
- **vxlanEbgp**: VXLAN with external BGP

Each has default settings optimized for the fabric type.

### 4. Schema Validation
Configuration validated against `schemas/source/nexus_dashboard.json`:
- Fabric settings validated by type
- Switch configuration fields validated
- SNMP protocols restricted to valid options
- IP addresses validated for correct format

### 5. Python 3.6+ Compatible
- Uses PyYAML for YAML parsing
- Uses jsonschema for validation
- Uses requests for API calls
- Full type hints for better IDE support

## Migration Steps

If you're upgrading from the old role:

### Step 1: Backup Old Role (Optional)
```bash
# Keep a backup if needed
cp -r roles/nexus_dashboard_classic_lan roles/nexus_dashboard_classic_lan.backup
```

### Step 2: Use New YAML Format
Convert your old JSON files to YAML format in `examples/nexus_dashboard/`:

**Old (JSON)**:
```json
{
  "ip": "10.1.1.10",
  "hostname": "leaf1",
  "model": "N9K-C93180YC-FX",
  "serialNumber": "SAL1234ABCD",
  "softwareVersion": "10.3(3)"
}
```

**New (YAML)**:
```yaml
switches:
  - ip: "10.1.1.10"
    hostname: "leaf1"
    model: "N9K-C93180YC-FX"
    serialNumber: "SAL1234ABCD"
    softwareVersion: "10.3(3)"
```

### Step 3: Update Vault File
Add nexus_dashboard credentials to `vault-ai-pod.yaml`:

```yaml
nexus_dashboard:
  nd_password: "your_nd_password"
  switch_password: "your_switch_password"
```

Then encrypt:
```bash
ansible-vault encrypt vault-ai-pod.yaml
```

### Step 4: Update Commands
Use new command syntax with `--config-file` and `--vault-file`:

**Old**:
```bash
python library/nexus_dashboard_classic_lan.py create-fabric \
  --nd-url https://nd-lan.rich.ciscolabs.com \
  --nd-username admin \
  --nd-password password \
  --fabric-name my-fabric
```

**New**:
```bash
python roles/nexus_dashboard/library/nexus_dashboard.py create-fabric \
  --nd-url https://nd-lan.rich.ciscolabs.com \
  --nd-username admin \
  --vault-file vault-ai-pod.yaml \
  --fabric-name my-fabric \
  --fabric-type classicLan
```

## API Changes

### Fabric Type Selection
New required parameter for fabric type:

```bash
# Specify fabric type when creating
--fabric-type classicLan      # Classic-LAN
--fabric-type vxlanIbgp       # VXLAN iBGP
--fabric-type vxlanEbgp       # VXLAN eBGP
```

### Configuration File
Replaced JSON with YAML:

```bash
# Config file path for fabric settings and switches
--config-file examples/nexus_dashboard/classic_lan_fabric.yaml
```

### Vault File Support
Added for secure credential management:

```bash
# Optional - loads credentials from vault file
--vault-file vault-ai-pod.yaml
```

## Backward Compatibility

The old `nexus_dashboard_classic_lan` role is still available in `roles/nexus_dashboard_classic_lan/` if needed for compatibility. However, new deployments should use the `nexus_dashboard` role.

## Performance Improvements

- Single Python module supporting multiple fabric types
- Centralized schema validation
- Efficient credential loading from vault
- Better error messages with logging support

## Testing

To test the new role:

```bash
# List fabrics (basic connectivity test)
python roles/nexus_dashboard/library/nexus_dashboard.py list-fabrics \
  --nd-url https://nd-lan.rich.ciscolabs.com \
  --nd-username admin \
  --vault-file vault-ai-pod.yaml

# Create a test classic-lan fabric
python roles/nexus_dashboard/library/nexus_dashboard.py create-fabric \
  --nd-url https://nd-lan.rich.ciscolabs.com \
  --nd-username admin \
  --vault-file vault-ai-pod.yaml \
  --fabric-name test-classic-lan \
  --fabric-type classicLan

# Add switches
python roles/nexus_dashboard/library/nexus_dashboard.py add-devices \
  --nd-url https://nd-lan.rich.ciscolabs.com \
  --nd-username admin \
  --vault-file vault-ai-pod.yaml \
  --fabric-name test-classic-lan \
  --config-file examples/nexus_dashboard/classic_lan_fabric.yaml
```

## Documentation

Comprehensive documentation available at:
- `roles/nexus_dashboard/README.md` - Main documentation
- `examples/nexus_dashboard/*.yaml` - Configuration examples
- `schemas/source/nexus_dashboard.json` - Schema documentation

## Support

For questions or issues:
1. Review the README.md in the role directory
2. Check examples in `examples/nexus_dashboard/`
3. Verify YAML syntax and schema compliance
4. Check vault file contains correct credentials

## Version

- **Old**: nexus_dashboard_classic_lan v1.0.0
- **New**: nexus_dashboard v2.0.0

Major improvements:
- ✓ Support for multiple fabric types
- ✓ YAML configuration (consistent with Cisco AI PODs)
- ✓ Vault integration for credentials
- ✓ JSON schema validation
- ✓ Better error handling and logging
- ✓ Python 3.6+ support with type hints
- ✓ Modular architecture for future extensibility

## Next Steps

1. Update your configuration files to YAML format
2. Add nexus_dashboard credentials to vault-ai-pod.yaml
3. Review examples in examples/nexus_dashboard/
4. Test with list-fabrics command
5. Create your first fabric using new syntax
