# Cisco AI PODs Troubleshooting Guide

## Overview
This guide provides comprehensive troubleshooting procedures for Cisco AI PODs deployments, covering common issues and their resolutions.

## Quick Reference

### Emergency Contacts
- **Cisco TAC:** 1-800-553-2447
- **Everpure Support:** 1-650-729-4088  
- **Internal IT Escalation:** [Your internal escalation process]

# Everpure
ansible all -i inventory -m ping
purearray list --array

# Network  
show interface brief
show vlan brief
show port-channel summary
```

## Intersight Issues

### Authentication Problems

#### Issue: API Key Authentication Failure
**Symptoms:**
- "Authentication failed" errors
- HTTP 401 responses
- Unable to connect to Intersight
- "Invalid API Key ID format" errors

**Diagnosis:**
```bash
# Check environment variables are set
echo $intersight_api_key_id
echo $intersight_secret_key

# Verify API key format (should be UUID format)
# Expected: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Verify secret key file exists and has correct permissions
ls -la $intersight_secret_key
# Should show: -rw------- (600 permissions)

# Check secret key file format
head -1 $intersight_secret_key
# Should start with: -----BEGIN RSA PRIVATE KEY-----

# Enable debug logging for detailed error information
python3 scripts/deploy_ai_pod.py --role intersight
```

**Resolution:**
1. **Regenerate API Key:**
   - Login to Intersight portal (SaaS or CVA/PVA)
   - Navigate to Settings > API Keys
   - Delete old key and generate new one
   - Download new SecretKey.pem file

2. **Fix File Permissions:**
   ```bash
   chmod 600 $TF_VAR_intersight_secret_key
   chown $(whoami) $TF_VAR_intersight_secret_key
   ```

3. **Verify API Key Permissions:**
   - Ensure API key has organizational access
   - Check resource group permissions
   - Verify domain policy permissions

4. **Test Authentication:**
   ```bash
   # For SaaS Intersight
   curl -X GET "https://intersight.com/api/v1/organizations/Organizations" \
     -H "Authorization: Bearer $intersight_api_key_id"
   
   # For CVA/PVA
   curl -k -X GET "https://<intersight_fqdn>/api/v1/organizations/Organizations"
   ```
```

**Resolution:**
1. Regenerate API key in Intersight
2. Verify secret key file format (PEM)
3. Check file permissions (600)
4. Confirm API key has required permissions

#### Issue: CVA/PVA Connection Problems
**Symptoms:**
- Cannot connect to on-premises Intersight
- Certificate errors
- Network timeouts

**Diagnosis:**
```bash
# Test connectivity
ping your-cva-fqdn
telnet your-cva-fqdn 443

# Check certificate
openssl s_client -connect your-cva-fqdn:443

```

**Resolution:**
1. Verify CVA/PVA is accessible
2. Update intersight_fqdn in global_settings.ezi.yaml
3. Check network connectivity and DNS resolution
4. Verify SSL certificate trust

### Deployment Order Issues

#### Issue: Executing Phases Out of Sequence
**Symptoms:**
- Ansible failures due to missing dependencies
- Network connectivity issues
- Resource creation failures
- Authentication problems due to missing infrastructure

**Diagnosis:**
```bash
# Check if you're following the proper deployment order
# Reference: Main runbook deployment execution order

# Phase verification checklist:
# 1. Network Foundation - Management connectivity verified?
# 2. Intersight/UCS - Compute infrastructure operational?
# 3. Everpure - Storage dependent on compute hosts
# 4. Network Completion - Data/storage networks configured?
# 5. Integration - All components validated?
```

**Resolution:**
1. **Stop Current Deployment:** Do not proceed with failed phase
2. **Review Dependencies:** Check [Deployment Execution Order](Cisco-AI-PODs-Runbook.md#deployment-execution-order)
3. **Complete Prerequisites:** Ensure all prior phases are fully validated
4. **Restart from Failed Phase:** Only proceed after prerequisites are met

#### Issue: Skipping Network Foundation (Phase 1)
**Symptoms:**
- Cannot reach Intersight for authentication
- Terraform timeouts
- DNS resolution failures

**Resolution:**
```bash
# Always establish network foundation first
# 1. Configure management switches
# 2. Establish uplink connectivity  
# 3. Configure management VLANs
# 4. Test connectivity before proceeding
ping intersight.com  # or your CVA/PVA FQDN
```

#### Issue: Running Storage Before Compute
**Symptoms:**
- Storage cannot discover hosts
- Host mapping failures
- Multipath configuration issues

**Resolution:**
```bash
# Storage (Phase 3) depends on Compute (Phase 2)
# 1. Verify UCS hosts are discovered in Intersight
# 2. Confirm server profiles are created
# 3. Validate host connectivity before storage configuration
```

## Everpure Issues

### Connectivity Problems

#### Issue: Ansible Cannot Connect to Array
**Symptoms:**
- "Connection refused" errors
- Authentication failures
- Module import errors

**Diagnosis:**
```bash
# Test basic connectivity
ansible all -i inventory -m ping

# Check API connectivity
curl -k https://flasharray-ip/api/api_version

# Verify collection installation
ansible-galaxy collection list purestorage.flasharray
```

**Resolution:**
```bash
# Reinstall Everpure collection
ansible-galaxy collection install purestorage.flasharray --force

# Install Python dependencies
pip install purestorage py-pure-client

# Update inventory with correct credentials
# Verify API token validity
```

#### Issue: API Token Authentication Failure
**Symptoms:**
- "Invalid API token" errors
- HTTP 403 responses
- Authentication timeouts

**Diagnosis:**
```bash
# Test API token manually
curl -k -H "api-token: your-token" https://flasharray-ip/api/2.0/arrays

# Check token expiration
# Verify token permissions
```

**Resolution:**
1. Generate new API token in Everpure GUI
2. Update inventory file with new token
3. Verify token has required permissions
4. Check token format (no extra characters)

### Configuration Issues

#### Issue: Volume Creation Failures
**Symptoms:**
- Volumes not created
- Size allocation errors
- Host mapping failures

**Diagnosis:**
```bash
# Check array capacity
ansible flasharray -i inventory -m purefa_info -a "gather_subset=capacity"

# Verify volume configuration in playbook
# Check for naming conflicts
```

**Resolution:**
1. Verify available capacity
2. Check volume naming conventions
3. Ensure host exists before volume mapping
4. Validate size formatting (TB, GB, etc.)

#### Issue: Host Connectivity Problems
**Symptoms:**
- Hosts not discovered
- Multipath failures
- Performance issues

**Diagnosis:**
```bash
# On compute host
multipath -ll
iscsiadm -m session
lsscsi

# Check Everpure host configuration
# Verify IQN/WWPN configuration
```

**Resolution:**
1. Configure multipath properly
2. Verify iSCSI initiator configuration
3. Check FC HBA configuration
4. Confirm network connectivity

## Network Issues

### Switch Connectivity Problems

#### Issue: Cannot Connect to Switch
**Symptoms:**
- SSH/Telnet connection refused
- Network unreachable
- Authentication failures

**Diagnosis:**
```bash
# Test basic connectivity
ping switch-ip

# Check port connectivity
telnet switch-ip 22
telnet switch-ip 23

# Verify credentials
# Check console connection if available
```

**Resolution:**
1. Verify network connectivity
2. Check IP address configuration
3. Confirm SSH/Telnet is enabled
4. Use console connection for recovery
5. Reset credentials if necessary

#### Issue: VLAN Configuration Problems
**Symptoms:**
- VLANs not working
- Inter-VLAN communication failures
- Trunk port issues

**Diagnosis:**
```bash
# Check VLAN configuration
show vlan brief
show interface trunk
show spanning-tree brief

# Verify port assignments
show interface status
```

**Resolution:**
```bash
# Recreate VLANs if necessary
vlan 100
  name compute-vlan
  
# Fix trunk configuration
interface Ethernet1/1
  switchport mode trunk
  switchport trunk allowed vlan 100,200,300
```

### Performance Issues

#### Issue: Network Performance Problems
**Symptoms:**
- Slow network performance
- High latency
- Packet loss

**Diagnosis:**
```bash
# Check interface counters
show interface counters
show interface counters errors

# Monitor interface utilization
show interface counters rates

# Check for spanning tree issues
show spanning-tree blockedports
```

**Resolution:**
1. Identify bottlenecks
2. Configure port channels for more bandwidth
3. Optimize spanning tree topology
4. Check for cable/hardware issues
5. Implement QoS if needed

## Integration Issues

### UCS-Storage Integration

#### Issue: Storage Not Visible to Hosts
**Symptoms:**
- Storage volumes not detected
- Multipath not working
- Boot failures

**Diagnosis:**
```bash
# On UCS hosts
lsscsi
multipath -ll
dmesg | grep -i scsi

# Check Everpure host registration
# Verify network connectivity
```

**Resolution:**
1. Verify storage network configuration
2. Check iSCSI/FC configuration
3. Confirm host registration on storage
4. Validate multipath configuration
5. Check boot policy configuration

### Intersight-UCS Integration

#### Issue: UCS Domain Not Discovered
**Symptoms:**
- UCS domain not visible in Intersight
- Connection timeouts
- Registration failures

**Diagnosis:**
```bash
# Check UCS Manager connectivity
# Verify Intersight device connector status
# Check network connectivity to Intersight
```

**Resolution:**
1. Verify UCS Manager version compatibility
2. Check Intersight device connector configuration
3. Ensure network connectivity to Intersight
4. Re-register UCS domain if necessary

## Performance Troubleshooting

### Storage Performance Issues

#### Issue: Poor Storage Performance
**Symptoms:**
- High I/O latency
- Low throughput
- Application performance issues

**Diagnosis:**
```bash
# Check storage array performance
# Monitor host I/O patterns
iostat -x 1
iotop

# Check network utilization
# Verify multipath configuration
```

**Resolution:**
1. Optimize multipath configuration
2. Tune I/O scheduler settings
3. Check network performance
4. Review Everpure performance policies
5. Analyze application I/O patterns

### Network Performance Issues

#### Issue: Network Bottlenecks
**Symptoms:**
- High network utilization
- Dropped packets
- Application timeouts

**Diagnosis:**
```bash
# Monitor interface utilization
show interface counters rates

# Check for errors
show interface counters errors

# Monitor CPU utilization
show system resources
```

**Resolution:**
1. Implement port channels
2. Upgrade network interfaces
3. Optimize traffic distribution
4. Implement QoS policies
5. Check for hardware issues

## Monitoring and Alerting

### Health Monitoring Setup

#### Intersight Monitoring
```bash
# Check system health via API
curl -X GET "https://intersight.com/api/v1/compute/PhysicalSummaries"

#### Everpure Monitoring
```bash
# Check array health
ansible flasharray -i inventory -m purefa_info -a "gather_subset=health"

# Monitor performance
# Set up Pure1 monitoring
```

#### Network Monitoring
```bash
# SNMP monitoring setup
snmp-server community public ro
snmp-server host 10.1.1.100 version 2c public

# Check system health
show environment
show hardware
```

### Log Analysis

#### Collecting Logs
```bash
# Intersight Logs
python3 deploy_intersight_ucs.py -dl 7
in your Home Folder look under the Logs Directory

# Ansible logs  
ansible-playbook -vvv playbook.yaml 2>&1 | tee ansible.log

# Switch logs
show logging
show tech-support
```

#### Log Analysis Tools
```bash
# Search for errors
grep -i error logfile
grep -i fail logfile

# Analyze patterns
awk '/ERROR/ {print $0}' logfile
```

## Recovery Procedures

### Disaster Recovery

#### Terraform State Recovery
```bash
# Backup current state
cp terraform.tfstate terraform.tfstate.backup

# Restore from backup
cp terraform.tfstate.backup terraform.tfstate

# Rebuild from infrastructure
terraform import [resources]
```

#### Configuration Recovery
```bash
# Network configuration backup
copy running-config bootflash:backup.cfg

# Restore configuration
copy bootflash:backup.cfg running-config
```

### Emergency Procedures

#### Complete Infrastructure Failure
1. **Assessment Phase:**
   - Identify scope of failure
   - Check power and connectivity
   - Verify management access

2. **Recovery Phase:**
   - Restore network connectivity
   - Recover management systems
   - Restore storage access
   - Validate compute resources

3. **Verification Phase:**
   - Test all integrations
   - Verify data integrity
   - Confirm application functionality
   - Update documentation

## Testing and Validation

Beyond ad-hoc diagnosis, use the standalone validation tests in
[tests/](../tests/) to confirm a specific piece of cluster functionality
(e.g. GPU metrics collection, backend networking) works as expected after a
deployment or configuration change. See [docs/tests.md](tests.md) for the
full index of available tests.

## Preventive Measures

### Regular Maintenance
- Weekly health checks
- Monthly configuration backups
- Quarterly performance reviews
- Annual disaster recovery testing

### Monitoring Setup
- Configure alerts for critical thresholds
- Set up automated health checks
- Implement centralized logging
- Create performance dashboards

### Documentation Updates
- Keep runbooks current
- Document all changes
- Maintain network diagrams
- Update contact information

## Escalation Procedures

### Internal Escalation
1. Level 1: Infrastructure team
2. Level 2: Senior engineers
3. Level 3: Vendor support
4. Level 4: Management notification

### Vendor Support
- **Cisco TAC:** For Intersight and UCS issues
- **Everpure:** For storage-related problems
- **Network team:** For switch configuration issues

### Documentation Requirements
- Problem description
- Steps taken to resolve
- Current status
- Next steps planned
- Contact information