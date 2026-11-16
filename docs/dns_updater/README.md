# DNS Manager for Cisco AI PODs

A comprehensive DNS synchronization and validation tool for the Cisco AI PODs project. The DNS Manager provides:

- **Pre-installation DNS validation** for OpenShift clusters
- **Multi-provider DNS synchronization** (Active Directory, Infoblox, BlueCat, Efficient IP, BIND)
- **Multi-source inventory support** (OpenShift, Cisco Intersight, Cisco EveryPure)
- **Web UI integration** with NiceGUI for easy testing and management
- **Idempotent operations** with dry-run mode for safety
- **Vault-based credential management** for secure operations

## Quick Start

### 1. Install Dependencies

The DNS Manager dependencies are included in the main `requirements.txt`:

```bash
pip install -r requirements.txt
```

### 2. Configure DNS Provider

Create a `dns_config.yaml` file in the scripts directory:

```yaml
vault:
  enabled: true
  url: https://vault.example.com:8200
  path_prefix: secret/data/cisco-ai-pods

providers:
  ad:
    type: active_directory
    server: dc1.example.com
    domain: example.com
    ldap_port: 389
    secure_ldap_port: 636
    use_ssl: true
    vault_path: activedirectory/credentials

inventory:
  openshift:
    file: inventories/openshift.yaml
  intersight:
    file: inventories/intersight.yaml
    enabled: true
  everpure:
    file: inventories/everpure.yaml
    enabled: false
```

### 3. Access the DNS Manager UI

The DNS Manager is integrated into the main Cisco AI PODs automation UI. Access it at:

```
http://localhost:8080/dns-manager
```

Three tabs are available:

- **Validator**: Pre-installation DNS validation
- **Updater**: DNS record synchronization
- **Status**: System health and configuration overview

## Features

### DNS Validation

Validates DNS records before OpenShift installation:

- ✓ Forward DNS (A record) resolution
- ✓ API endpoint validation (api.cluster.domain)
- ✓ Wildcard DNS validation (*.apps.cluster.domain)
- ✓ Reverse DNS (PTR records)
- ✓ Master/Worker node records
- ✓ Connectivity testing

### DNS Synchronization

Synchronizes DNS records from multiple inventory sources:

- Parses OpenShift, Intersight, and EveryPure inventory files
- Compares desired vs. actual DNS records
- Identifies missing, stale, and matching records
- Supports dry-run mode for safe preview
- Idempotent operations (safe to run multiple times)

### Multi-Provider Support

Extensible provider architecture with implementations for:

- **Active Directory DNS** (primary, fully implemented)
- **Infoblox** (framework ready)
- **BlueCat** (framework ready)
- **Efficient IP** (framework ready)
- **BIND DNS** (framework ready)

## Usage Workflows

### Pre-Installation DNS Validation

1. Click on the **Validator** tab
2. Enter cluster configuration:
   - Cluster name
   - Domain
   - API hostname and IP
   - Wildcard apps domain
   - Master/worker node records (JSON format)
3. Click **Validate**
4. Review results and fix any failed tests
5. Proceed with OpenShift installation once all tests pass

### DNS Synchronization

1. Click on the **Updater** tab
2. Select DNS provider (Active Directory)
3. Configure inventory sources
4. Click **Test** to verify provider connection
5. Click **Dry-Run** to preview changes
6. Review missing, stale, and matching records
7. Click **Apply** to synchronize DNS records

## Configuration

### dns_config.yaml Structure

```yaml
vault:
  enabled: bool           # Enable Vault integration
  url: string            # Vault server URL
  path_prefix: string    # Base path for secrets

providers:
  <provider_name>:
    type: string         # Provider type (active_directory, infoblox, etc.)
    server: string       # DNS server address
    domain: string       # Base domain
    # Provider-specific options...
    vault_path: string   # Path to credentials in Vault

inventory:
  openshift:
    file: string         # Path to OpenShift inventory YAML
    enabled: bool        # Enable this source
  intersight:
    file: string         # Path to Intersight inventory YAML
    enabled: bool
  everpure:
    file: string         # Path to EveryPure inventory YAML
    enabled: bool
```

### Inventory Format

#### OpenShift Inventory (openshift.yaml)

```yaml
openshift:
  domain: prod.example.com
  clusters:
    - name: ocp-prod
      api_hostname: api.prod.example.com
      api_ip: 192.168.1.5
      wildcard_domain: apps.prod.example.com
      nodes:
        - hostname: ocp-master-1.prod.example.com
          ip: 192.168.1.10
          type: master
        - hostname: ocp-worker-1.prod.example.com
          ip: 192.168.1.20
          type: worker
```

#### Intersight Inventory (intersight.yaml)

```yaml
intersight:
  domain: example.com
  servers:
    - hostname: ucs-mgmt-1.example.com
      ip: 192.168.1.100
    - hostname: ucs-mgmt-2.example.com
      ip: 192.168.1.101
```

#### EveryPure Inventory (everpure.yaml)

```yaml
everpure:
  domain: example.com
  systems:
    - hostname: pure-storage-1.example.com
      ip: 192.168.1.50
    - hostname: pure-storage-2.example.com
      ip: 192.168.1.51
```

## API Reference

The DNS Manager provides REST API endpoints for programmatic access:

### Validation Endpoints

```
POST /api/dns/validate
  - Validates DNS records before installation
  - Input: cluster_name, domain, api_hostname, nodes
  - Output: validation results with pass/fail/warning status

GET /api/dns/validation/status
  - Returns status of last validation
```

### Synchronization Endpoints

```
POST /api/dns/dry-run
  - Preview DNS record changes without applying
  - Input: provider, inventory_sources
  - Output: missing, stale, matching records

POST /api/dns/apply
  - Apply DNS record synchronization
  - Input: provider, inventory_sources
  - Output: operation summary (created, updated, deleted)

POST /api/dns/provider/test
  - Test provider connection
  - Input: provider name
  - Output: connection status
```

## Security Considerations

- **Never store credentials in config files** - Use Vault
- **Environment variable fallback** for CI/CD pipelines
- **HTTPS enforcement** for DNS provider APIs
- **Idempotent operations** for safe re-runs
- **Dry-run mode** to preview changes before applying

## Troubleshooting

### DNS Validation Failures

**Issue**: A record tests failing for master nodes

**Solution**: Verify that all master node hostnames are correctly registered in DNS:
```bash
# Test DNS resolution
nslookup ocp-master-1.prod.example.com
# Should return the correct IP address
```

**Issue**: Wildcard DNS validation fails

**Solution**: Verify wildcard DNS record is configured:
```bash
# Test wildcard resolution
nslookup test.apps.prod.example.com
# Should resolve to wildcard IP
```

### Provider Connection Issues

**Issue**: Active Directory connection fails

**Solution**: Verify credentials and connectivity:
```bash
# Test LDAP connectivity
ldapsearch -x -h dc1.example.com -D "CN=Service Account,DC=example,DC=com" -W
```

**Issue**: Vault connection fails

**Solution**: Verify Vault URL and authentication:
```bash
# Test Vault connectivity
curl https://vault.example.com:8200/v1/sys/health
```

## Running Tests

Run the DNS Manager test suite:

```bash
# Run all DNS tests
make dns-test

# Run specific test file
python -m pytest scripts/test_dns_updater.py -v

# Run with coverage
pytest scripts/test_dns_updater.py --cov=scripts/dns_updater --cov=scripts/dns_validator
```

## Linting

Check code quality:

```bash
make dns-lint
```

## Configuration Validation

Validate dns_config.yaml:

```bash
make dns-validate
```

## Architecture

For detailed architecture information, see [ARCHITECTURE.md](./ARCHITECTURE.md).

## Implementation Checklist

For step-by-step implementation guidance, see [IMPLEMENTATION_CHECKLIST.md](./IMPLEMENTATION_CHECKLIST.md).

## Web UI Guide

For complete web interface usage guide, see [WEB_UI_GUIDE.md](./WEB_UI_GUIDE.md).

## Support

For issues and questions:

1. Check [WEB_UI_GUIDE.md](./WEB_UI_GUIDE.md) troubleshooting section
2. Review logs in `dns_updater.log`
3. Run configuration validation: `make dns-validate`
4. Check provider connectivity from Status tab

## See Also

- [Quick Start Guide](./QUICKSTART.md)
- [Architecture & Deployment](./ARCHITECTURE.md)
- [Web UI Guide](./WEB_UI_GUIDE.md)
- [Implementation Checklist](./IMPLEMENTATION_CHECKLIST.md)
