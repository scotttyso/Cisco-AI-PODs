# DNS Manager Web UI Guide

Complete guide for using the DNS Manager web interface integrated into Cisco AI PODs.

## Accessing the DNS Manager

1. Start the automation UI:
   ```bash
   cd scripts
   python automation_ui.py --port 8080
   ```

2. Open your browser:
   ```
   http://localhost:8080
   ```

3. Navigate to **DNS Manager** tab (or look for 🔧 icon)

## User Interface Overview

The DNS Manager consists of three main tabs:

- **Validator**: Pre-installation DNS validation
- **Updater**: DNS record synchronization
- **Status**: System health and configuration

### Validator Tab

Validates DNS records before OpenShift installation.

#### Input Section (Left)

**Cluster Configuration**:
- **Cluster Name**: Name of your cluster (e.g., `prod`)
- **Domain**: Base domain name (e.g., `example.com`)
- **API Hostname**: API endpoint hostname (optional, e.g., `api.prod.example.com`)
- **API IP**: IP address of API endpoint (optional)
- **Wildcard Apps Domain**: Wildcard DNS for applications (optional)

**Node Records**:
- Enter node information in JSON format
- Each node requires `name`, `ip`, and `type` fields
- Types: `master` or `worker`

Example:
```json
[
  {"name": "ocp-master-1.prod.example.com", "ip": "192.168.1.10", "type": "master"},
  {"name": "ocp-master-2.prod.example.com", "ip": "192.168.1.11", "type": "master"},
  {"name": "ocp-worker-1.prod.example.com", "ip": "192.168.1.20", "type": "worker"},
  {"name": "ocp-worker-2.prod.example.com", "ip": "192.168.1.21", "type": "worker"}
]
```

#### Actions

- **🔍 Validate**: Run validation tests
- **Clear**: Reset node records to empty array

#### Results Section (Right)

Shows validation status and test results.

**Status Indicator**:
- 🔵 Blue: Validation in progress
- 🟢 Green: Validation passed
- 🔴 Red: Validation failed

**Result Cards** (after validation):
- **Total**: Number of tests run
- **Passed**: Successfully resolved tests
- **Failed**: Tests that need attention
- **Warnings**: Tests with non-critical issues

**Test Results Table**:
Shows each individual test with:
- Hostname being tested
- Test type (A record, wildcard, reverse, etc.)
- Status (passed/failed/warning)
- Message describing result

**Recommendation Box**:
- ✓ Green: Ready for OpenShift installation
- ✗ Red: Fix failed tests before installation

### Updater Tab

Synchronizes DNS records from infrastructure inventory to Active Directory.

#### Configuration Section (Left)

**Provider Selection**:
- Currently supports: **Active Directory DNS**
- Future: Infoblox, BlueCat, etc.

**Inventory Sources**:
- **OpenShift Inventory**: Path to openshift.yaml
- **Intersight Inventory**: Path to intersight.yaml (optional)
- **EveryPure Inventory**: Path to everpure.yaml (optional)

Default paths work if inventories are in `scripts/inventories/` directory.

#### Actions

- **🔗 Test**: Verify connection to DNS provider
- **🔍 Dry-Run**: Preview changes without applying

#### Results Section (Right)

Shows DNS synchronization summary.

**Status Indicator**:
- 🔵 Blue: Operation in progress
- 🟢 Green: Operation succeeded
- 🔴 Red: Operation failed

**Summary Cards**:
- **Matching**: Records that already exist correctly
- **Missing**: Records that need to be created
- **Stale**: Records that should be deleted

**Records Tables** (if changes found):

**Matching Records** (✓ Green):
- Displays existing records in correct state
- No action needed
- Shown for verification

**Missing Records** (+ Red):
- Records to be created
- Shows hostname, IP, and zone
- These will be created on **Apply**

**Stale Records** (- Yellow):
- Records to be deleted
- Shows hostname, IP, and zone
- These will be deleted on **Apply**

### Status Tab

System information and operation history.

**Configuration Status**:

**DNS Providers**:
- Shows configured DNS providers
- Number of providers ready

**Inventory Sources**:
- Shows configured inventory sources
- Enabled/disabled status

**Vault Integration**:
- ✓ Green: Vault enabled and configured
- ✗ Red: Vault disabled (using plain-text config)

**Last Operations**:

Shows results from most recent operations:
- Last Validation: passed/failed counts
- Last Sync Check: matching/missing/stale records

## Common Workflows

### Workflow 1: Pre-Installation DNS Validation

**Goal**: Verify DNS is configured correctly before OpenShift installation

**Steps**:

1. Click **Validator** tab
2. Enter your cluster details:
   ```
   Cluster Name: prod
   Domain: example.com
   API Hostname: api.prod.example.com
   API IP: 192.168.1.5
   Wildcard Apps Domain: apps.prod.example.com
   ```
3. Enter nodes as JSON (see example above)
4. Click **🔍 Validate**
5. Wait for tests to complete (usually 10-30 seconds)
6. Review results:
   - If all tests pass ✓: Ready to proceed with installation
   - If any fail ✗: Fix DNS issues and retry
     - Check DNS server configuration
     - Verify all records exist
     - Ensure correct IP addresses

**Example**: Testing API endpoint resolution

```
Test: Test API endpoint - api.prod.example.com
Status: Failed
Message: Unable to resolve api.prod.example.com to 192.168.1.5
```

**Solution**: Add A record in Active Directory:
```
Name: api.prod.example.com (or just "api" in example.com zone)
Type: A
IP Address: 192.168.1.5
```

Then retry validation.

### Workflow 2: DNS Record Synchronization

**Goal**: Keep DNS records synchronized with infrastructure inventory

**Setup** (first time only):
1. Create `scripts/dns_config.yaml` with your Active Directory details
2. Create inventory files in `scripts/inventories/`

**Synchronization** (recurring):

1. Click **Updater** tab
2. Verify provider is **Active Directory DNS**
3. Click **🔗 Test**
   - Expected: "✓ Connected to Active Directory"
   - If fails: Check config and AD connectivity
4. Click **🔍 Dry-Run**
   - Shows preview of changes
   - No actual changes made
5. Review results:
   - **Matching**: Current records ✓
   - **Missing**: Records that will be created +
   - **Stale**: Records that will be deleted -
6. If satisfied with preview:
   - Click **Apply** button (if available)
   - System creates/updates/deletes records as shown
   - View confirmation message

**Example**: Adding new worker node

**Before**:
- Matching: 10 records
- Missing: 1 record (ocp-worker-3.prod.example.com)
- Stale: 0 records

**Dry-Run Shows**:
- Will create: ocp-worker-3.prod.example.com → 192.168.1.23

**After Apply**:
- Matching: 11 records
- Missing: 0 records
- Stale: 0 records

### Workflow 3: Troubleshooting DNS Issues

**Problem**: "Validation failed - cannot resolve hostnames"

**Investigation**:
1. Go to **Validator** tab
2. Enter test hostname that's failing
3. Run validation - note specific error
4. Common causes:
   - DNS server not configured
   - Record doesn't exist
   - Incorrect IP address
   - DNS cache issue

**Solutions**:

**Solution A**: Verify DNS record exists
```bash
# From your workstation
nslookup ocp-master-1.prod.example.com
# Should return: 192.168.1.10
```

**Solution B**: Check DNS server directly
```bash
# Query specific DNS server (Active Directory)
nslookup ocp-master-1.prod.example.com dc1.example.com
```

**Solution C**: Clear DNS cache (if recently added)
```bash
# Windows
ipconfig /flushdns

# Linux
sudo systemctl restart systemd-resolved

# macOS
dscacheutil -flushcache
```

**Problem**: "Synchronization failed - cannot connect to Active Directory"

**Investigation**:
1. Go to **Updater** tab
2. Click **Test** to verify connection
3. Check error message

**Solutions**:

**Solution A**: Verify AD connectivity
```bash
# Check if AD server is reachable
ping dc1.example.com

# Check LDAP port (389 for plain, 636 for SSL)
telnet dc1.example.com 389
```

**Solution B**: Verify credentials
```bash
# Test LDAP bind with ldapsearch
ldapsearch -x -h dc1.example.com -D "CN=Service Account,DC=example,DC=com" -W
# Enter password when prompted
```

**Solution C**: Check configuration
```bash
# Verify dns_config.yaml
cat scripts/dns_config.yaml
# Check:
# - server: matches your AD server
# - domain: matches your domain
# - bind_dn: correct service account
# - password: correct (not empty)
```

## Tips and Best Practices

### Pre-Validation Best Practices

1. **Run validation early**: Don't wait until installation starts
2. **Validate regularly**: DNS changes over time
3. **Test from multiple locations**: Ensures DNS propagation
4. **Check all node types**: Masters, workers, management nodes
5. **Verify reverse DNS**: Important for some applications

### DNS Synchronization Best Practices

1. **Always dry-run first**: Review changes before applying
2. **Schedule during maintenance windows**: Avoid business hours
3. **Monitor after sync**: Verify no unexpected changes
4. **Keep inventory updated**: Stale inventory = stale DNS
5. **Document changes**: Log who/when/what was changed

### DNS Configuration Best Practices

1. **Use service accounts**: Don't use personal credentials
2. **Enable Vault**: For production deployments
3. **Backup DNS records**: Before major operations
4. **Test in non-production**: Validate in test zone first
5. **Monitor DNS queries**: Track usage patterns

## Troubleshooting Guide

| Problem | Symptoms | Solution |
|---------|----------|----------|
| Validation times out | Stuck on "Validating..." | Check network/DNS server connectivity |
| Connection refused | Updater Test fails | Verify AD server is online and reachable |
| Permission denied | Sync operation fails | Check service account permissions |
| Records not updating | Dry-run shows changes but not applied | Verify inventory files are updated |
| Duplicate records | Multiple A records for same hostname | Run comparator to identify and clean up |
| DNS cache issues | Old records resolved after deletion | Clear client DNS cache or wait for TTL |

## UI Tips

- **JSON validation**: Use online JSON validator to verify node records
- **Copy/Paste**: Can copy results from Status tab for documentation
- **Browser console**: Press F12 to see detailed error messages
- **Keyboard shortcuts**: Tab to navigate between fields
- **Mobile support**: UI is responsive, works on tablets/phones

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Tab | Move to next field |
| Shift+Tab | Move to previous field |
| Enter | Submit form in input field |
| Escape | Close modal/dialog |
| F12 | Open browser developer console |

## Screenshots

See image references in `docs/dns_updater/images/` for:
- Pre-validation workflow
- DNS synchronization workflow
- Error handling examples
- Status dashboard overview

## Support and Help

**For more help**:
- Check [README.md](./README.md) for overview
- See [QUICKSTART.md](./QUICKSTART.md) for setup
- Review [ARCHITECTURE.md](./ARCHITECTURE.md) for technical details
- Check logs in `dns_updater.log`

**Common Help Commands**:
```bash
# Validate configuration
make dns-validate

# Run tests
make dns-test

# Check DNS connectivity
make dns-lint
```
