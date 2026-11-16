# Release v0.1.16 - DNS Manager with Production-Ready Schema

**Release Date:** November 16, 2026

## Overview
This release delivers a fully functional DNS Manager for the Cisco AI PODs automation platform with comprehensive schema documentation and multi-provider support. The DNS Manager enables automatic DNS record synchronization across multiple DNS providers including Active Directory, Infoblox, BlueCat, Efficient IP, and BIND DNS.

## 🎯 Key Features

### DNS Manager Framework
- **Multi-Provider Support**: Configure Active Directory, Infoblox, BlueCat, Efficient IP, and BIND DNS
- **Automatic Record Extraction**: Parse OpenShift, Initial Inventory, and Everpure files to extract DNS A records
- **LDAP Integration**: Auto-load Active Directory LDAP settings from Initial Inventory's shared services
- **Credential Management**: Vault integration for secure credential storage in production environments
- **Pre-Installation DNS Validation**: Verify DNS records before OpenShift cluster deployment

### Web UI - DNS Manager Page
- **Provider Selection**: Easy dropdown or chip selection of DNS provider
- **Inventory Source Management**: Checkboxes to select which inventory files to include
- **LDAP Auto-Configuration**: Automatic LDAP settings loading with override capability
- **DNS Configuration Generation**: Auto-generates dns_config.ezai.yaml with extracted A records
- **YAML Editor**: Full-featured editor for manual configuration review and editing
- **Actions**: Validate (dry-run) and Sync buttons for DNS management operations

### Record Extraction Logic
- **OpenShift Parsing**: Extracts node hostnames/IPs, API VIP, ingress VIP with FQDN construction
- **Initial Inventory Parsing**: Extracts device hostnames and IP addresses from JSON format
- **Everpure Parsing**: Extracts storage system hostnames and IPs
- **Fallback Path Resolution**: Robust file detection with multiple path fallbacks
- **Domain-Qualified FQDNs**: Automatically constructs fully-qualified domain names from cluster configuration

### Production-Ready Schema
- **Comprehensive Descriptions**: All providers documented with Required vs Optional attributes
- **intersight.json Style Format**: Clear documentation of:
  - Required attributes (must be provided)
  - Optional attributes (with default values)
  - Special notes and constraints
  - Workflow documentation
- **Validation Support**: Full JSON Schema validation for dns_config.ezai.yaml
- **Multi-Provider Configuration**: Support for multiple provider instances in single configuration

## 📋 Schema Components

### Supported DNS Providers

#### Active Directory
```yaml
providers:
  ad_primary:
    type: active_directory
    use_shared_ldap: true  # Auto-import LDAP from Initial Inventory
    server: ad1.example.com
    domain: example.com
    bind_dn: CN=Service Account,CN=Users,DC=example,DC=com
    ldap_port: 389
    secure_ldap_port: 636
    use_ssl: false
    password: ${AD_PASSWORD}
    timeout: 10
```

#### Infoblox
```yaml
providers:
  infoblox_primary:
    type: infoblox
    server: infoblox.example.com
    api_version: "2.11"
    username: api_user
    password: ${INFOBLOX_PASSWORD}
    use_ssl: true
    verify_ssl: true
    wapi_port: 443
    timeout: 30
```

#### BIND DNS
```yaml
providers:
  bind_primary:
    type: bind
    server: ns1.example.com
    zone_file_path: /var/lib/named/zones
    nsupdate: true
    tsig_keyfile: /etc/named.keys/update.key
    timeout: 10
```

#### BlueCat
```yaml
providers:
  bluecat_primary:
    type: bluecat
    server: bluecat.example.com
    username: api_user
    password: ${BLUECAT_PASSWORD}
    timeout: 30
```

#### EfficientIP
```yaml
providers:
  efficientip_primary:
    type: efficientip
    server: efficientip.example.com
    username: api_user
    password: ${EFFICIENTIP_PASSWORD}
    timeout: 30
```

### DNS Records Configuration
```yaml
records:
  - hostname: node1.example.com
    ipv4: 198.18.0.1
  - hostname: api.cluster.example.com
    ipv4: 198.18.0.9
  - hostname: "*.apps.cluster.example.com"
    ipv4: 198.18.0.10
```

## 🚀 Usage Workflow

1. **Navigate to DNS Manager** in Environment Preparation section
2. **Select your DNS Provider** from: Active Directory, BIND DNS, BlueCat, Efficient IP, or Infoblox
3. **Configure LDAP** (auto-loaded from Initial Inventory if available)
4. **Select Inventory Sources**:
   - ☑ OpenShift Cluster Deployment (openshift/install.ezai.yaml)
   - ☑ Initial Inventory with Shared Services
   - ☑ Everpure Storage Inventory (everpure/everpure.ezai.yaml)
5. **Click "Generate Configuration"** - Automatically extracts A records from selected inventory
6. **Review Generated YAML** - Edit records as needed in the YAML editor
7. **Click "Validate"** - Dry-run to check DNS before applying
8. **Click "Sync"** - Apply DNS records to your provider

## 📄 Files Changed

### New Files
- `scripts/aipod_webui/dns_manager_page.py` - Original DNS Manager page (kept for reference)

### Modified Files
- `scripts/aipod_webui/custom_pages.py` - Complete DNS Manager implementation
  - `extract_dns_records_from_files()` - Parse inventory files and extract A records
  - `load_ldap_from_inventory()` - Auto-load LDAP settings
  - `generate_dns_config()` - Generate dns_config.ezai.yaml
  - `dns_manager_form()` - Web UI form for DNS Manager

- `schemas/source/dns_manager.json` - DNS Manager schema definition
  - Added Required/Optional attributes documentation
  - Comprehensive provider descriptions
  - Workflow documentation
  - Record extraction behavior explanation

- `schema/cisco-ai-pods.json` - Regenerated merged schema with new descriptions

- `scripts/aipod_webui/pages.py` - DNS Manager page registration
  - `dns_manager_form` - Form component
  - `dns_manager_actions` - Validate action
  - `dns_manager_sync` - Sync action
  - `dns_manager_secrets` - Credential management

## 🔧 Technical Improvements

### File Detection Robustness
- Multiple path fallback mechanism for OpenShift and Everpure files
- Handles both workspace/ and host_vars/ directory structures
- Graceful handling of missing files with helpful user messages

### YAML Generation
- Proper indentation using PyYAML dump with:
  - `default_flow_style=False` - Block style (no flow sequences)
  - `sort_keys=False` - Preserve order
  - `allow_unicode=True` - Support Unicode characters

### Schema Validation
- Generated yaml_config.ezai.yaml passes schema validation
- Supports both required and optional fields
- Proper handling of default values

### Credential Management
- Vault path support for production environments
- Fallback to environment variables
- Secure password handling

## 🧪 Validation

### Schema Compliance
✅ dns_config.ezai.yaml validates against dns_manager.json schema
✅ All provider definitions properly reference schema
✅ Records section properly formatted as array of objects
✅ Merged schema includes all definitions

### File Detection
✅ OpenShift file detection from host_vars/openshift/install.ezai.yaml
✅ Initial Inventory detection from workspace/initial_inventory.json
✅ Everpure file detection from host_vars/everpure/everpure.ezai.yaml
✅ Fallback paths handle different working directory contexts

### Record Extraction
✅ OpenShift: Nodes, API VIP, ingress VIP with FQDN construction
✅ Initial Inventory: Device hostnames and IPs
✅ Everpure: Storage system hostnames and IPs
✅ FQDN construction using base_dns_domain from cluster config

## 🛡️ Security Considerations

### Credential Storage
- Passwords can be stored in Vault for production use
- Support for `vault_path` field in provider configuration
- Fallback to environment variables or plaintext (for testing only)

### LDAP Security
- Support for LDAPS (SSL/TLS) connections
- Secure port configuration (636 for LDAPS)
- Bind DN authentication

### API Security
- SSL/TLS support for all HTTPS-based providers (Infoblox, BlueCat, EfficientIP)
- SSL certificate verification options
- Timeout configuration for all API operations

## 📚 Documentation

### Schema Documentation
All providers include:
- Purpose and use case
- Required attributes with descriptions
- Optional attributes with default values
- Special notes and constraints
- Vault integration guidance

### Workflow Documentation
Main DNS Manager description includes:
- Supported providers list
- Configuration steps
- Validation and synchronization process
- Best practices

## 🐛 Bug Fixes

- Fixed Python bytecode caching issues in development
- Removed duplicate error message rendering
- Fixed file detection for host_vars directory structure
- Fixed LDAP field extraction from Initial Inventory
- Proper YAML indentation for records section

## ⚠️ Known Limitations

- Initial Inventory LDAP loading requires shared_services.ldap configuration
- OpenShift file must be in host_vars/openshift/ or workspace/openshift/ directory
- Everpure file must be in host_vars/everpure/ or workspace/everpure/ directory
- Record extraction currently supports basic hostname/IP pairs (future: CNAME, MX record support)

## 📦 Installation & Deployment

### For Development
```bash
# Update your local repository
git pull origin main

# Check out release tag
git checkout v0.1.16

# Start the web UI
python scripts/automation_ui.py --port 8090

# Access DNS Manager at: http://localhost:8090/#/dns-manager
```

### For Customer Environment
```bash
# Clone the repository at the release tag
git clone -b v0.1.16 <repository-url>

# Install dependencies
pip install -r requirements.txt

# Configure your environment
# 1. Create Initial Inventory with LDAP settings in shared_services
# 2. Place OpenShift install.ezai.yaml in host_vars/openshift/
# 3. Place Everpure config in host_vars/everpure/ (optional)

# Start the UI
python scripts/automation_ui.py --port 8090

# Navigate to DNS Manager page
# Select your DNS provider
# Generate configuration from inventory sources
# Validate and sync DNS records
```

## 🔄 Upgrade Path

If upgrading from v0.1.15:
1. All existing configurations remain compatible
2. No data migration required
3. New DNS Manager features are additive
4. Schema changes are backward compatible

## 📞 Support & Troubleshooting

### Common Issues

**Q: "Not found - save OpenShift Cluster Deployment first"**
A: Ensure openshift/install.ezai.yaml is saved in host_vars/openshift/ directory

**Q: "No LDAP configuration found in Initial Inventory"**
A: Configure shared_services.ldap in your Initial Inventory's shared_services section

**Q: Records not appearing in generated config**
A: Check that inventory checkboxes are selected and files exist at expected paths

**Q: YAML indentation looks wrong**
A: PyYAML correctly indents records as a list (- hostname, - hostname...). This is valid YAML.

## 🎓 Examples

### Complete Active Directory Configuration
```yaml
dns:
  vault:
    enabled: true
    url: https://vault.example.com:8200
    path_prefix: secret/data/cisco-ai-pods
    auth_method: token
    auth_token_env: VAULT_TOKEN
  
  providers:
    ad_primary:
      type: active_directory
      use_shared_ldap: true
      server: ad1.example.com
      domain: example.com
      bind_dn: CN=dns-automation,CN=Users,DC=example,DC=com
      ldap_port: 389
      secure_ldap_port: 636
      use_ssl: false
      vault_path: dns/ad_credentials
      timeout: 10
  
  records:
    - hostname: dcmaihgx5001.example.com
      ipv4: 198.18.2.47
    - hostname: dcmaihgx5002.example.com
      ipv4: 198.18.2.48
    - hostname: api.ai-pods.example.com
      ipv4: 198.18.0.9
    - hostname: "*.apps.ai-pods.example.com"
      ipv4: 198.18.0.10
```

### Multi-Provider Configuration
```yaml
dns:
  providers:
    ad_primary:
      type: active_directory
      use_shared_ldap: true
      server: ad1.example.com
      domain: example.com
      bind_dn: CN=dns-automation,CN=Users,DC=example,DC=com
      password: ${AD_PASSWORD}
      timeout: 10
    
    infoblox_backup:
      type: infoblox
      server: infoblox.example.com
      api_version: "2.11"
      username: api_user
      password: ${INFOBLOX_PASSWORD}
      timeout: 30
  
  records:
    - hostname: node1.example.com
      ipv4: 198.18.0.1
    - hostname: node2.example.com
      ipv4: 198.18.0.2
```

## ✅ Verification Checklist for Deployment

- [ ] Git repository checked out at v0.1.16
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Initial Inventory configured with LDAP in shared_services
- [ ] OpenShift install.ezai.yaml placed in host_vars/openshift/
- [ ] Web UI started successfully on port 8090
- [ ] DNS Manager page loads without errors
- [ ] Inventory checkboxes can be selected
- [ ] "Generate Configuration" button works
- [ ] YAML is properly formatted with correct indentation
- [ ] Schema validation passes for generated config
- [ ] Validate (dry-run) action executes successfully
- [ ] Sync action prepares for DNS provider synchronization

## 📋 Release Notes by Component

### DNS Manager UI
- Complete provider selection interface
- Automatic LDAP configuration loading
- Inventory source checkboxes
- YAML editor integration
- Validate and Sync action buttons

### Record Extraction Engine
- Robust file detection with fallbacks
- OpenShift: Nodes, API VIP, ingress VIP
- Initial Inventory: Device records
- Everpure: Storage system records
- FQDN construction from cluster domain

### Schema & Validation
- Comprehensive provider definitions
- Required/Optional attribute documentation
- Workflow explanation
- Record structure definition
- Full JSON Schema validation support

---

**Release Tag:** `v0.1.16`
**Commit Hash:** 3bbf20e (Add comprehensive descriptions to DNS Manager schema...)
**Repository:** scotttyso/Cisco-AI-PODs

For the latest updates and support, visit the GitHub repository.
