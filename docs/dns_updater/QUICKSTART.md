# DNS Manager Quick Start Guide

Get the DNS Manager up and running in 5 minutes.

## Prerequisites

- Python 3.10+
- Cisco AI PODs automation environment installed
- Access to DNS provider (Active Directory recommended for testing)

## Step 1: Install Dependencies

Dependencies are already included in `requirements.txt`. Ensure they're installed:

```bash
cd /path/to/Cisco-AI-PODs
pip install -r requirements.txt
```

Key DNS Manager packages installed:
- `dnspython` - DNS query and validation
- `hvac` - HashiCorp Vault integration
- `ldap3` - LDAP/Active Directory connectivity
- `pyad` - PyAD for AD operations

## Step 2: Create Configuration File

Create `dns_config.yaml` from the example:

```bash
cp examples/dns_config.ezai.yaml dns_config.yaml
# Edit with your DNS provider details
```

Minimal Active Directory configuration:

```yaml
vault:
  enabled: false          # Disable for testing

providers:
  ad:
    type: active_directory
    server: dc1.example.com
    domain: example.com
    ldap_port: 389
    secure_ldap_port: 636
    use_ssl: false        # Use false for plain LDAP during testing
    bind_dn: "CN=Service Account,DC=example,DC=com"
    password: "your_password"

inventory:
  openshift:
    file: examples/inventory.openshift.yaml
    enabled: true
  intersight:
    file: examples/inventory.intersight.yaml
    enabled: false
  everpure:
    file: examples/inventory.everpure.yaml
    enabled: false
```

## Step 3: Create Test Inventory

Create `examples/inventory.openshift.yaml` (or modify existing):

```yaml
cluster:
  name: "prod-ocp"
  domain: "example.com"
  api_vip: "192.168.1.10"
  api_vip_dnsname: "api.prod-ocp.example.com"
  api_vip_int_dnsname: "api-int.prod-ocp.example.com"
  ingress_vip_dnsname: "*.apps.prod-ocp.example.com"

masters:
  - name: "master-0"
    hostname: "master-0.prod-ocp.example.com"
    ip: "192.168.1.20"
  - name: "master-1"
    hostname: "master-1.prod-ocp.example.com"
    ip: "192.168.1.21"
  - name: "master-2"
    hostname: "master-2.prod-ocp.example.com"
    ip: "192.168.1.22"

workers:
  - name: "worker-0"
    hostname: "worker-0.prod-ocp.example.com"
    ip: "192.168.1.30"
  - name: "worker-1"
    hostname: "worker-1.prod-ocp.example.com"
    ip: "192.168.1.31"
```

## Step 4: Test DNS Validation

Validate DNS records before installation:

```bash
cd scripts
python -c "
from dns_validator import DNSValidator

validator = DNSValidator()
results = validator.validate_openshift_cluster(
    cluster_name='prod',
    domain='example.com',
    api_ip='192.168.1.5',
    master_ips={
        'ocp-master-1.prod.example.com': '192.168.1.10',
        'ocp-master-2.prod.example.com': '192.168.1.11'
    }
)

print(f\"Passed: {results['summary']['passed']}\")
print(f\"Failed: {results['summary']['failed']}\")
"
```

## Step 5: Test DNS Synchronization

Preview DNS record changes:

```bash
python scripts/dns_updater.py --config dns_config.yaml --dry-run --inventory examples/inventory.openshift.yaml
```

Expected output:
```
DNS Updater - Dry Run Mode
Provider: Active Directory DNS
Zone: example.com

Matching Records: 4
Missing Records (would create): 0
Stale Records (would delete): 0
```

## Step 6: Access Web UI

Start the main automation UI:

```bash
python scripts/automation_ui.py --port 8080
```

Access at: `http://localhost:8080`

Navigate to: **DNS Manager** tab

## Common Workflows

### Validate Before Installation

1. Go to **Validator** tab
2. Enter cluster details:
   - Cluster: `prod`
   - Domain: `example.com`
   - API hostname: `api.prod.example.com`
   - API IP: `192.168.1.5`
   - Nodes (JSON):
     ```json
     [
       {"name": "ocp-master-1.prod.example.com", "ip": "192.168.1.10", "type": "master"},
       {"name": "ocp-worker-1.prod.example.com", "ip": "192.168.1.20", "type": "worker"}
     ]
     ```
3. Click **Validate**
4. Check results - should show all tests passing
5. If any fail, resolve DNS issues and retry

### Synchronize DNS Records

1. Go to **Updater** tab
2. Select provider: **Active Directory DNS**
3. Configure inventory sources (default paths usually work)
4. Click **Test** - should show "Connected"
5. Click **Dry-Run** - preview changes
6. Review results:
   - Matching: ✓ Existing records
   - Missing: + Records to create
   - Stale: - Records to delete
7. If satisfied, click **Apply**

## Troubleshooting

### "Connection refused" error

**Problem**: Can't connect to Active Directory

**Solution**:
```bash
# Test connectivity to DC
ping dc1.example.com

# Test LDAP port
telnet dc1.example.com 389

# Verify credentials
ldapsearch -x -h dc1.example.com -D "CN=Service Account,DC=example,DC=com" -W
```

### "DNS name not found" during validation

**Problem**: Hostnames don't resolve

**Solution**:
```bash
# Check DNS server
nslookup api.prod.example.com 8.8.8.8

# Verify DNS records exist in AD
nslookup ocp-master-1.prod.example.com dc1.example.com
```

### Tests pass but records don't sync

**Problem**: Dry-run shows all matching, but expected missing records

**Solution**:
1. Verify inventory files are correctly formatted
2. Check that hostnames in inventory match your DNS naming scheme
3. Ensure zone configuration is correct in `dns_config.yaml`

### "Config file not found" error

**Solution**:
```bash
# Ensure dns_config.yaml exists in scripts directory
ls -la scripts/dns_config.yaml

# Or specify full path
python dns_updater.py --config /path/to/dns_config.yaml --dry-run
```

## Next Steps

1. **Review Architecture**: See [ARCHITECTURE.md](./ARCHITECTURE.md) for deployment options
2. **Implement Vault**: Follow [IMPLEMENTATION_CHECKLIST.md](./IMPLEMENTATION_CHECKLIST.md) for production setup
3. **Add More Providers**: Implement Infoblox or other DNS providers as needed
4. **Automate**: Schedule DNS syncs with Ansible playbook or cron

## Support

- Check logs: `tail -f dns_updater.log`
- Run tests: `make dns-test`
- Validate config: `make dns-validate`
- Review full docs: See [README.md](./README.md)
