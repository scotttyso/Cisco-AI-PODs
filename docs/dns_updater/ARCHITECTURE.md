# DNS Manager Architecture & Deployment

This document describes the DNS Manager architecture and deployment options.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Cisco AI PODs Automation UI                 │
│                      (NiceGUI / automation_ui.py)               │
└──────────────────────┬──────────────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        │                             │
   ┌────▼─────────────┐    ┌────────▼────────────┐
   │  DNS Validator   │    │  DNS Manager Page   │
   │ (dns_validator)  │    │ (dns_manager_page)  │
   └────┬─────────────┘    └────────┬────────────┘
        │                           │
        │  Validates DNS before     │  Synchronizes DNS
        │  OpenShift install        │  records from inventory
        │                           │
   ┌────▴──────────────────────────┴──┐
   │      DNS Updater Framework       │
   │       (dns_updater.py)           │
   │                                  │
   │  ┌────────────────────────────┐  │
   │  │  Inventory Parser          │  │
   │  │ • OpenShift                │  │
   │  │ • Intersight               │  │
   │  │ • EveryPure                │  │
   │  └────────────────────────────┘  │
   │                                  │
   │  ┌────────────────────────────┐  │
   │  │  DNS Provider (Abstract)   │  │
   │  │ • Active Directory ✓       │  │
   │  │ • Infoblox                 │  │
   │  │ • BlueCat                  │  │
   │  │ • Efficient IP             │  │
   │  │ • BIND DNS                 │  │
   │  └────────────────────────────┘  │
   │                                  │
   │  ┌────────────────────────────┐  │
   │  │  DNS Comparator            │  │
   │  │ • Set-based comparison     │  │
   │  │ • Idempotent operations    │  │
   │  └────────────────────────────┘  │
   └────┬─────────────────────────────┘
        │
        │
   ┌────▴────────────────────────────────┐
   │      Credential Management          │
   │                                     │
   │  ┌────────────────────────────────┐ │
   │  │  HashiCorp Vault (optional)    │ │
   │  │ • Secure credential storage    │ │
   │  │ • Dynamic credentials          │ │
   │  └────────────────────────────────┘ │
   │                                     │
   │  ┌────────────────────────────────┐ │
   │  │  Environment Variables         │ │
   │  │ • CI/CD pipeline integration   │ │
   │  └────────────────────────────────┘ │
   └────┬────────────────────────────────┘
        │
   ┌────▴───────────────────────────────────┐
   │      External DNS Providers            │
   │                                        │
   │  ┌──────────┐    ┌──────────────────┐  │
   │  │    AD    │    │   Infoblox       │  │
   │  │   LDAP   │    │   REST API       │  │
   │  └──────────┘    └──────────────────┘  │
   │                                        │
   │  ┌──────────┐    ┌──────────────────┐  │
   │  │  BlueCat │    │  Efficient IP    │  │
   │  │   REST   │    │   REST API       │  │
   │  └──────────┘    └──────────────────┘  │
   │                                        │
   │  ┌──────────────────────────────────┐  │
   │  │        BIND DNS                  │  │
   │  │      Zone File Editing           │  │
   │  └──────────────────────────────────┘  │
   └────────────────────────────────────────┘
```

## Component Descriptions

### DNS Validator
- **Purpose**: Pre-installation DNS validation for OpenShift clusters
- **Functionality**:
  - A record resolution testing
  - API endpoint validation (api.cluster.domain)
  - Wildcard DNS testing (*.apps.cluster.domain)
  - Reverse DNS (PTR record) testing
  - Master/worker node hostname testing
  - Connectivity verification

### DNS Manager Page (NiceGUI Integration)
- **Purpose**: Web UI integration with Cisco AI PODs automation UI
- **Features**:
  - Three tabs: Validator, Updater, Status
  - Real-time status updates
  - Responsive design
  - Modal confirmations for destructive operations

### DNS Updater Framework
- **Purpose**: Core DNS synchronization engine
- **Components**:
  - **InventoryParser**: Parses YAML inventory files
  - **DNSProvider**: Abstract base class for DNS operations
  - **DNSComparator**: Set-based record comparison
  - **DNSUpdater**: Orchestration engine

### Credential Management
- **Vault Integration**: Primary method for production
- **Environment Variables**: Fallback for CI/CD
- **Configuration Files**: Not recommended for production

## Deployment Options

### Option 1: Local Development (No Vault)

**When to use**: Testing, development, proof-of-concept

**Setup**:
```yaml
vault:
  enabled: false

providers:
  ad:
    type: active_directory
    server: dc1.example.com
    domain: example.com
    bind_dn: "CN=Service Account,DC=example,DC=com"
    password: "your_password"
```

**Pros**:
- Quick setup
- No external dependencies
- Good for testing

**Cons**:
- Credentials in config file
- Not secure for production
- Not suitable for CI/CD

### Option 2: Vault-Based (Production)

**When to use**: Production environments, CI/CD pipelines

**Setup**:
1. Install and configure HashiCorp Vault
2. Store credentials in Vault:
   ```bash
   vault kv put secret/cisco-ai-pods/activedirectory \
     bind_dn="CN=Service Account,DC=example,DC=com" \
     password="your_password"
   ```
3. Configure DNS Manager:
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
       vault_path: activedirectory
   ```

**Pros**:
- Secure credential management
- Dynamic credentials supported
- Audit trail
- Multi-environment support

**Cons**:
- Additional infrastructure
- More complex setup

### Option 3: Automated via Ansible

**When to use**: Infrastructure-as-code deployments

**Ansible Playbook** (`dns_updater.yml`):
```yaml
---
- hosts: dns_servers
  name: DNS Manager Synchronization
  tasks:
    - name: Run DNS validation
      block:
        - name: Validate DNS before installation
          command: |
            python scripts/dns_validator.py \
              --cluster prod \
              --domain example.com \
              --api-ip 192.168.1.5
      rescue:
        - name: Handle validation failure
          debug:
            msg: "DNS validation failed. Fix issues and retry."

    - name: Run DNS synchronization
      block:
        - name: Dry-run DNS synchronization
          command: |
            python scripts/dns_updater.py \
              --config dns_config.yaml \
              --dry-run
          register: dry_run_result

        - name: Apply DNS changes
          command: |
            python scripts/dns_updater.py \
              --config dns_config.yaml \
              --apply
          when: dry_run_result.rc == 0
```

**Usage**:
```bash
ansible-playbook dns_updater.yml -i inventory.ini
```

**Pros**:
- Infrastructure-as-code
- Idempotent
- Audit trail
- Integration with other Ansible tasks

**Cons**:
- Requires Ansible setup
- More configuration

### Option 4: Containerized (Kubernetes)

**When to use**: Running in containerized environments

**Dockerfile**:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/ ./scripts/
COPY dns_config.yaml .

ENTRYPOINT ["python", "scripts/dns_updater.py"]
CMD ["--config", "dns_config.yaml", "--dry-run"]
```

**Kubernetes CronJob**:
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: dns-manager-sync
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: dns-manager
            image: dns-manager:latest
            args:
            - "--config"
            - "/etc/dns-manager/dns_config.yaml"
            volumeMounts:
            - name: config
              mountPath: /etc/dns-manager
              readOnly: true
          volumes:
          - name: config
            configMap:
              name: dns-manager-config
          restartPolicy: OnFailure
```

**Pros**:
- Cloud-native
- Easy scaling
- Kubernetes integration
- Automated scheduling

**Cons**:
- Kubernetes knowledge required
- More infrastructure

### Option 5: Scheduled Cron Job

**When to use**: Simple periodic synchronization

**Cron job** (Linux):
```bash
# Add to crontab: crontab -e
0 2 * * * cd /home/automation-ui/Cisco-AI-PODs && python scripts/dns_updater.py --config scripts/dns_config.yaml --apply >> /var/log/dns_manager.log 2>&1
```

**Setup**:
1. Create log directory:
   ```bash
   mkdir -p /var/log
   touch /var/log/dns_manager.log
   chmod 666 /var/log/dns_manager.log
   ```

2. Add cron job:
   ```bash
   crontab -e
   ```

3. Monitor logs:
   ```bash
   tail -f /var/log/dns_manager.log
   ```

**Pros**:
- Simple setup
- No external dependencies
- Low overhead

**Cons**:
- Limited logging
- No easy retry mechanism
- Maintenance overhead

## Data Flow

### DNS Validation Flow
```
User Input (Cluster Details)
    ↓
DNSValidator
    ↓
  ├─ Test A Records
  ├─ Test API Endpoints
  ├─ Test Wildcard DNS
  ├─ Test Reverse DNS
  └─ Test Connectivity
    ↓
Validation Results
    ↓
UI Display (Pass/Fail/Warning)
```

### DNS Synchronization Flow
```
Inventory Files
    ↓
InventoryParser
    ↓
Desired DNS Records (Set)
    ↓
DNSProvider.authenticate()
    ↓
Actual DNS Records (Set)
    ↓
DNSComparator
    ├─ Missing Records (desired - actual)
    ├─ Stale Records (actual - desired)
    └─ Matching Records (intersection)
    ↓
Dry-Run Mode?
    ├─ Yes → Display Preview (no changes)
    └─ No → Apply Changes
        ├─ Create missing
        ├─ Delete stale
        └─ Update matching
    ↓
Operation Summary
```

## Security Considerations

### Credential Storage
- **Never** store passwords in config files for production
- **Use Vault** for all production deployments
- **Environment variables** for CI/CD pipelines
- **Never commit** credentials to version control

### HTTPS Enforcement
- DNS provider APIs must use HTTPS
- Validate SSL certificates
- Use certificate pinning for critical connections

### Idempotent Operations
- Safe to run multiple times
- No duplicate records created
- Stale records cleaned up automatically

### Audit Trail
- Log all DNS operations
- Track who/when/what changes were made
- Vault provides audit logging

### Network Security
- Restrict DNS provider API access to authorized IPs
- Use VPN for remote access
- Implement network segmentation

## Performance Considerations

### Large Deployments (1000+ records)
- **Batch Operations**: Group records by zone
- **Parallel Processing**: Use thread pools for multiple zones
- **Caching**: Cache DNS provider responses
- **Pagination**: Handle paginated API responses

### DNS Query Optimization
- Use zone transfers instead of individual lookups
- Cache DNS responses locally
- Implement connection pooling for LDAP

### Monitoring and Logging
- Log operation duration
- Monitor API rate limits
- Alert on failures
- Track resource usage

## Disaster Recovery

### Backup DNS Records
```bash
# Backup current DNS records before sync
python -c "
from dns_updater import ActiveDirectoryProvider
import json

provider = ActiveDirectoryProvider(config)
provider.authenticate()
records = provider.get_records('example.com')

with open('dns_backup.json', 'w') as f:
    json.dump([r.__dict__ for r in records], f, indent=2)
"
```

### Restore DNS Records
```bash
# Restore from backup
python -c "
from dns_updater import ActiveDirectoryProvider
import json

with open('dns_backup.json') as f:
    records_data = json.load(f)

provider = ActiveDirectoryProvider(config)
provider.authenticate()

for record_data in records_data:
    # Recreate record from backup
    provider.create_record(record_data['zone'], record_data)
"
```

## Recommended Architecture

For production environments, we recommend:

1. **Vault** for credential management
2. **Kubernetes** or **Docker** for deployment
3. **Ansible** for orchestration
4. **Prometheus/Grafana** for monitoring
5. **ELK** for log aggregation

```
┌──────────────────────┐
│   Git Repository     │
│  (Infrastructure)    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│   CI/CD Pipeline     │
│  (GitHub Actions)    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Kubernetes Cluster  │
│  ├─ DNS Manager      │
│  ├─ Vault Agent      │
│  └─ Monitoring       │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│   HashiCorp Vault    │
│  (Credentials)       │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│   DNS Providers      │
│  ├─ Active Directory │
│  ├─ Infoblox         │
│  └─ Other            │
└──────────────────────┘
```

## Migration Path

For existing deployments:

1. **Phase 1**: Deploy in read-only mode (dry-run only)
2. **Phase 2**: Validate in test environment
3. **Phase 3**: Gradual rollout to production zones
4. **Phase 4**: Monitor and optimize
5. **Phase 5**: Full automation with scheduling

See [IMPLEMENTATION_CHECKLIST.md](./IMPLEMENTATION_CHECKLIST.md) for detailed steps.
