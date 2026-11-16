# DNS Manager Implementation Checklist

Step-by-step implementation tracking for DNS Manager in production.

## Pre-Implementation

- [ ] Identify DNS provider (Active Directory, Infoblox, etc.)
- [ ] Identify inventory sources (OpenShift, Intersight, EveryPure)
- [ ] Get DNS provider admin access
- [ ] Get service account credentials or Vault access
- [ ] Identify staging/non-production test environment
- [ ] Plan rollout timeline
- [ ] Identify stakeholders and communicating changes

## Phase 1: Infrastructure Setup

### DNS Provider Access

- [ ] Verify Active Directory connectivity from automation server
- [ ] Test LDAP port accessibility (389 or 636)
- [ ] Create service account in Active Directory
  - [ ] Account name: `dns-automation-service` or similar
  - [ ] Password: Strong, 32+ characters
  - [ ] Permissions: Read/write DNS records in target zone
  - [ ] MFA: Disabled for service accounts
- [ ] Test service account credentials:
  ```bash
  ldapsearch -x -h dc1.example.com \
    -D "CN=dns-automation-service,DC=example,DC=com" -W
  ```
- [ ] Document service account details (securely stored)

### Vault Setup (if using Vault)

- [ ] Install HashiCorp Vault or get access to existing
- [ ] Create Vault path for DNS credentials:
  ```bash
  vault kv put secret/cisco-ai-pods/activedirectory \
    bind_dn="CN=dns-automation-service,DC=example,DC=com" \
    password="your_strong_password"
  ```
- [ ] Configure Vault authentication
- [ ] Enable audit logging in Vault
- [ ] Set up Vault agent for credential injection
- [ ] Document Vault configuration

### Network Configuration

- [ ] Whitelist automation server IP in firewall
- [ ] Configure routing to DNS provider network
- [ ] Test network connectivity:
  ```bash
  ping dc1.example.com
  telnet dc1.example.com 389
  ```
- [ ] Configure reverse DNS (if required)

## Phase 2: DNS Manager Setup

### Installation and Dependencies

- [ ] Clone/update Cisco AI PODs repository
- [ ] Install Python 3.10+
- [ ] Activate Python virtual environment
- [ ] Install DNS Manager dependencies:
  ```bash
  pip install -r requirements.txt
  ```
- [ ] Verify installation:
  ```bash
  python -c "import dns_updater; print('OK')"
  ```

### Configuration Files

- [ ] Create `dns_config.yaml`:
  ```bash
  cp examples/dns_config.ezai.yaml dns_config.yaml
  ```
- [ ] Configure DNS provider section:
  - [ ] Set server address
  - [ ] Set domain name
  - [ ] Set LDAP port (389 for plain, 636 for SSL)
  - [ ] Set SSL/TLS settings
  - [ ] Set Vault path or credentials (plain text for testing only)
- [ ] Configure inventory section:
  - [ ] Set OpenShift inventory path (examples/inventory.openshift.yaml)
  - [ ] Set Intersight inventory path (examples/inventory.intersight.yaml, if applicable)
  - [ ] Set EveryPure inventory path (examples/inventory.everpure.yaml, if applicable)
  - [ ] Enable/disable sources as needed
- [ ] Validate configuration:
  ```bash
  make dns-validate
  ```

### Inventory Files

- [ ] Create or obtain `scripts/inventories/openshift.yaml`:
  - [ ] Cluster name
  - [ ] Domain
  - [ ] API endpoint hostname
  - [ ] API endpoint IP
  - [ ] Wildcard apps domain
  - [ ] Master node records (hostname and IP)
  - [ ] Worker node records (hostname and IP)
- [ ] Create or obtain `scripts/inventories/intersight.yaml` (if applicable):
  - [ ] Server FQDNs
  - [ ] Server IPs
- [ ] Create or obtain `scripts/inventories/everpure.yaml` (if applicable):
  - [ ] Storage system FQDNs
  - [ ] Storage system IPs
- [ ] Validate YAML syntax in all inventory files
- [ ] Verify all hostnames match your DNS naming scheme

### Directory Structure

- [ ] Verify directory structure:
  ```
  scripts/
  ├── dns_updater.py
  ├── dns_validator.py
  ├── dns_manager_ui.py
  ├── aipod_webui/
  │   └── dns_manager_page.py
  ├── dns_config.yaml
  ├── inventories/
  │   ├── openshift.yaml
  │   ├── intersight.yaml
  │   └── everpure.yaml
  └── test_dns_updater.py
  ```
- [ ] All files have correct permissions (644 for configs, 755 for scripts)
- [ ] Configuration files are readable by DNS Manager process user

## Phase 3: Testing

### Unit Testing

- [ ] Run test suite:
  ```bash
  make dns-test
  ```
- [ ] All tests pass ✓
- [ ] Code coverage acceptable (>80% for critical paths)
- [ ] Review test results for any warnings

### Integration Testing - Validation

- [ ] Test DNS validation in development environment:
  ```bash
  python -c "
  from dns_validator import DNSValidator
  validator = DNSValidator()
  results = validator.validate_openshift_cluster(
    cluster_name='prod',
    domain='example.com',
    api_ip='192.168.1.5'
  )
  print('Validation passed!' if not results['summary']['failed'] else 'Failed!')
  "
  ```
- [ ] All DNS validation tests pass ✓
- [ ] Document any failures and resolutions

### Integration Testing - Synchronization

- [ ] Test provider connection:
  ```bash
  python -c "
  from dns_updater import ActiveDirectoryProvider
  config = {'server': 'dc1.example.com', 'domain': 'example.com'}
  provider = ActiveDirectoryProvider(config)
  provider.authenticate()
  print('Connected!')
  "
  ```
- [ ] Test inventory parsing:
  ```bash
  python dns_updater.py --config dns_config.yaml --parse-inventory
  ```
- [ ] Test dry-run mode:
  ```bash
  python dns_updater.py --config dns_config.yaml --dry-run
  ```
- [ ] Review dry-run output for accuracy
- [ ] No actual changes should occur

### Web UI Testing

- [ ] Start automation UI:
  ```bash
  python automation_ui.py --port 8080
  ```
- [ ] Access DNS Manager tab
- [ ] Test Validator tab:
  - [ ] Enter valid cluster details
  - [ ] Run validation
  - [ ] Verify results display correctly
  - [ ] All tests pass or expected failures
- [ ] Test Updater tab:
  - [ ] Select provider
  - [ ] Test connection
  - [ ] Run dry-run
  - [ ] Review results
- [ ] Test Status tab:
  - [ ] Configuration displays
  - [ ] Last operations shown
- [ ] Stop UI without errors

### Performance Testing

- [ ] Test with small dataset (5 records) ✓
- [ ] Test with medium dataset (50 records) ✓
- [ ] Test with large dataset (1000+ records) ✓
- [ ] Record operation times
- [ ] Identify any performance bottlenecks

## Phase 4: Staging/Non-Production Testing

### Staging Environment Setup

- [ ] Deploy to staging environment
- [ ] Configure staging DNS provider (separate zone if possible)
- [ ] Create staging inventory files
- [ ] Configure staging dns_config.yaml
- [ ] Run all tests in staging

### Staging Validation

- [ ] Validate DNS records in staging zone
- [ ] Synchronize DNS records (dry-run)
- [ ] Review changes without applying
- [ ] Apply changes to staging zone
- [ ] Verify all records created correctly
- [ ] Verify idempotency (run twice, same result)

### Staging Monitoring

- [ ] Monitor DNS operations in staging
- [ ] Check logs for errors or warnings
- [ ] Verify audit trail (if using Vault)
- [ ] Test rollback procedures (restore from backup)
- [ ] Document any issues found

## Phase 5: Production Deployment

### Pre-Production

- [ ] Get production sign-off from DNS admin
- [ ] Get change management approval
- [ ] Backup production DNS records:
  ```bash
  python -c "
  from dns_updater import ActiveDirectoryProvider
  import json
  provider = ActiveDirectoryProvider(config)
  provider.authenticate()
  records = provider.get_records('example.com')
  with open('dns_backup_prod.json', 'w') as f:
    json.dump([r.__dict__ for r in records], f, indent=2)
  "
  ```
- [ ] Verify backup created successfully
- [ ] Store backup in secure location
- [ ] Communicate deployment to stakeholders

### Production Deployment

- [ ] Deploy DNS Manager to production:
  ```bash
  # Option 1: Directly
  cp -r dns_manager_ui.py /path/to/production/scripts/
  
  # Option 2: Via Kubernetes
  kubectl apply -f dns-manager-deployment.yaml
  
  # Option 3: Via Ansible
  ansible-playbook dns_updater.yml -i production_inventory
  ```
- [ ] Verify deployment completed
- [ ] Check process is running:
  ```bash
  ps aux | grep dns_updater
  ```
- [ ] Check logs for errors:
  ```bash
  tail -f /var/log/dns_updater.log
  ```

### Production Testing

- [ ] Run dry-run on production data:
  ```bash
  python dns_updater.py --config dns_config.yaml --dry-run
  ```
- [ ] Review changes in dry-run output
- [ ] No unexpected changes should appear
- [ ] Apply changes (if approved):
  ```bash
  python dns_updater.py --config dns_config.yaml --apply
  ```
- [ ] Verify changes applied successfully
- [ ] Check audit logs (if using Vault)

### Production Validation

- [ ] Validate DNS records with nslookup:
  ```bash
  nslookup ocp-master-1.example.com
  ```
- [ ] Verify all records resolve correctly
- [ ] Test from multiple locations
- [ ] Monitor DNS query responses
- [ ] No client complaints or issues

## Phase 6: Integration and Automation

### CI/CD Integration

- [ ] Create GitHub Actions workflow (if using GitHub):
  ```yaml
  name: DNS Manager Validation
  on: pull_request
  jobs:
    validate:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v3
        - name: Run DNS validation
          run: make dns-validate
  ```
- [ ] Configure webhook for GitHub events
- [ ] Test CI/CD pipeline
- [ ] All checks pass ✓

### Scheduled Synchronization

- [ ] Choose scheduling method:
  - [ ] Kubernetes CronJob
  - [ ] Ansible scheduled playbook
  - [ ] Linux cron job
  - [ ] Other
- [ ] Configure schedule:
  - [ ] Time of day
  - [ ] Frequency
  - [ ] Maintenance windows
- [ ] Test scheduled execution
- [ ] Verify logs show successful runs

### Monitoring and Alerts

- [ ] Configure logging:
  - [ ] Log file location
  - [ ] Log rotation policy
  - [ ] Log retention period
- [ ] Configure alerting (if applicable):
  - [ ] Alert on failures
  - [ ] Alert on unauthorized changes
  - [ ] Send to monitoring system
- [ ] Test alert workflow
- [ ] Verify on-call team receives alerts

## Phase 7: Documentation and Knowledge Transfer

### Documentation

- [ ] Document environment details:
  - [ ] DNS provider info
  - [ ] Service account details (securely)
  - [ ] Vault configuration
  - [ ] Scheduling details
- [ ] Create runbook for DNS Manager operations:
  - [ ] How to validate DNS
  - [ ] How to synchronize DNS
  - [ ] How to handle failures
  - [ ] How to restore from backup
- [ ] Document any customizations made
- [ ] Update main project README

### Knowledge Transfer

- [ ] Train ops team on DNS Manager
- [ ] Demonstrate common workflows
- [ ] Walk through troubleshooting
- [ ] Review security best practices
- [ ] Answer questions and concerns

### Support Plan

- [ ] Define support hours
- [ ] Identify primary/backup support person
- [ ] Document escalation path
- [ ] Set up communication channel
- [ ] Plan for handling issues

## Post-Implementation

### 30-Day Review

- [ ] Check operation for 30 days
- [ ] Review logs for issues
- [ ] Check performance metrics
- [ ] Gather feedback from team
- [ ] Document lessons learned

### Optimization

- [ ] Identify performance improvements
- [ ] Implement code optimizations if needed
- [ ] Adjust scheduling if needed
- [ ] Update documentation with improvements

### Maintenance Plan

- [ ] Schedule regular validation
- [ ] Plan for backup refresh
- [ ] Schedule dependency updates
- [ ] Plan for new DNS providers
- [ ] Review security quarterly

## Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| DNS Administrator | _____________ | ____/____/____ | _____________ |
| Infrastructure Lead | _____________ | ____/____/____ | _____________ |
| Operations Manager | _____________ | ____/____/____ | _____________ |
| Project Manager | _____________ | ____/____/____ | _____________ |

## Troubleshooting During Implementation

### "Configuration validation fails"
- Run: `make dns-validate`
- Check dns_config.yaml syntax
- Verify provider details are correct
- Ensure inventory files exist

### "Provider connection fails"
- Verify network connectivity to DNS provider
- Test LDAP port: `telnet dc1.example.com 389`
- Check service account credentials
- Verify credentials in Vault (if using)

### "Inventory parsing fails"
- Validate YAML syntax: Use online YAML validator
- Check file paths are correct
- Verify YAML structure matches schema
- Check file permissions

### "Tests fail"
- Review test output: `make dns-test -v`
- Check environment variables
- Verify Python version (3.10+)
- Review dependencies: `pip list | grep -E "dnspython|ldap3|hvac"`

## Completion Criteria

✓ All checkboxes completed
✓ All tests passing
✓ All documentation completed
✓ Sign-off received from all stakeholders
✓ No outstanding issues or concerns
✓ Team trained and ready
✓ Support plan in place
✓ Ready for production use

**Estimated Time**: 2-4 weeks
**Effort Level**: Medium (20-30 hours)
**Risk Level**: Low (dry-run mode makes changes safe)
