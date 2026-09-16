# Comprehensive Sensitive Variables Validator

## Overview

The `validate_sensitive_variables.py` script provides centralized validation of all sensitive environment variables required across all Ansible playbooks and roles:

- **intersight_ucs_provision**
- **openshift_install**
- **everpure** (FlashArray & FlashBlade)
- **splunk_observability**

This consolidates validation logic that was previously split between `roles/intersight_ucs_provision/library/src/validate_sensitive_variables.py` and `roles/openshift_install/library/generate_server_and_nmstate_templates.py`.

Sensitive variable validation is now run automatically from deployment playbooks after merged model objects are built in `pre_tasks`.

## Supported Sensitive Variables

The script uses two sources of truth:

- Pattern/context detection in `validate_sensitive_variables.py` (`_SENSITIVE_VAR_PATTERNS` + path-aware rules)
- Schema constraints from `definitions.abstract.sensitive_variables.properties`

### Mapped Schema Keys

The validator currently maps detected variables to these schema keys:

- `cco_password`
- `cco_user`
- `drive_security_authentication_password`
- `drive_security_current_security_key_passphrase`
- `drive_security_new_security_key_passphrase`
- `everpure_api_token`
- `everpure_snmp_auth_passphrase`
- `everpure_snmp_community`
- `everpure_snmp_privacy_passphrase`
- `fabric_interconnect_password`
- `intersight_api_key_id`
- `ipmi_encryption_key`
- `iscsi_boot_password`
- `iso_web_server_password`
- `ldap_binding_password`
- `linux_password`
- `local_user_password`
- `mac_sec_fallback_key_chain_secret`
- `mac_sec_primary_key_chain_secret`
- `persistent_passphrase`
- `private_key_passphrase`
- `proxy_password`
- `pure_api_token`
- `redfish_password`
- `root_password`
- `snmp_community_string`
- `snmp_password`
- `splunk_observability_access_token`
- `splunk_observability_nexus_password`
- `splunk_platform_token`
- `ssh_public_key`
- `switch_control_aes_primary_key`
- `vmedia_password`
- `vmware_esxi_password`
- `windows_admin_password`

## Usage

### Default (Playbook-Integrated) Validation

Validation is invoked automatically by these playbooks after host_vars are merged:

- `playbooks/deploy_ai_pod_phase1.yaml`
- `playbooks/deploy_ai_pod_phase2.yaml`
- `playbooks/deploy_observability.yaml`
- `playbooks/deploy_openshift_phase1.yaml`
- `playbooks/deploy_openshift_phase2.yaml`
- `playbooks/deploy_storage.yaml`

It also runs at the start of `scripts/deploy_ai_pod.py`.

Each playbook creates a temporary merged JSON model, runs:

```bash
python3 scripts/validate_sensitive_variables.py --models <temp_merged_model>.json
```

and then removes the temporary file.

### Manual Validation (Optional)

```bash
# Validate a single model
python3 scripts/validate_sensitive_variables.py --models model.json

# Validate multiple models (from different roles)
python3 scripts/validate_sensitive_variables.py --models intersight_model.json openshift_model.json everpure_model.json

# Use custom schema path
python3 scripts/validate_sensitive_variables.py --models model.json --schema /path/to/schema.json

# Show descriptions for each variable type
python3 scripts/validate_sensitive_variables.py --models model.json --verbose
```

### Exit Codes

- `0` — All required sensitive variables and certificate/private-key file checks pass
- `1` — One or more sensitive variables or certificate/private-key file checks fail

## Features

### ✓ Comprehensive Coverage
- Detects all currently supported sensitive prefixes across all roles
- Handles path-aware detection (e.g., `binding_parameters.password` → `ldap_binding_password_*`)
- Recognizes contextual field name mappings (e.g., `auth_password` in SNMP context → `snmp_auth_passphrase_*`)

### ✓ Schema Validation
- Validates against `minLength` / `maxLength` constraints
- Validates against regex patterns from schema
- Provides helpful error messages with constraints when validation fails

### ✓ Certificate and Key File Validation
- Validates configured certificate and private-key file paths from merged model content
- Checks file existence and confirms each path is a regular file
- Validates PEM content type by expected kind:
  - Certificate files must contain `-----BEGIN CERTIFICATE-----`
  - Private key files must contain a `-----BEGIN ... PRIVATE KEY-----` header
- If `intersight` exists in the merged model, `intersight_secret_key` must be set and must point to a valid private key file

Validated model paths:

- `everpure.settings.security.certificates.array_certificates[*].certificate_file` (Cert)
- `everpure.settings.security.certificates.array_certificates[*].intermediate_certificate_file` (Cert)
- `everpure.settings.security.certificates.array_certificates[*].private_key_file` (Private Key)
- `intersight.policies[*].certificate_management.certificates[*].certificate_file` (Cert)
- `intersight.policies[*].certificate_management.certificates[*].private_key_file` (Private Key)
- `openshift.certificates.api_cert_chain_file` (Cert)
- `openshift.certificates.ingress_cert_chain_file` (Cert)
- `openshift.certificates.api_key_file` (Private Key)
- `openshift.certificates.ingress_key_file` (Private Key)

### ✓ Helpful Error Output
- Colored console output (ANSI) for easy reading
- Suggests export commands with variable names
- Displays schema descriptions for each missing variable
- Groups variables by type for clarity

### ✓ Multiple Model Support
- Can validate across multiple merged models
- Merges models intelligently to consolidate requirements
- Reports ALL required variables from all inputs

## Integration Examples

### Integration with CI/CD Pipeline

```bash
#!/bin/bash
set -e

# Validation runs inside the deployment playbook pre_tasks
ansible-playbook playbooks/deploy_ai_pod_phase1.yaml
```

### Integration with Ansible Playbook

```yaml
- name: Create Temporary Model File for Sensitive Variable Validation
  ansible.builtin.tempfile:
    state: file
    suffix: .json
  register: sensitive_model_file

- name: Write Merged Variables for Sensitive Variable Validation
  ansible.builtin.copy:
    dest: "{{ sensitive_model_file.path }}"
    content: "{{ merged_vars | to_nice_json }}"
    mode: "0600"

- name: Validate Sensitive Environment Variables
  ansible.builtin.command:
    cmd: "{{ ansible_python_interpreter }} {{ playbook_dir }}/../scripts/validate_sensitive_variables.py --models {{ sensitive_model_file.path }}"
  changed_when: false

- name: Remove Temporary Model File
  ansible.builtin.file:
    path: "{{ sensitive_model_file.path }}"
    state: absent
```

## Differences from Individual Validators

| Feature | Individual Scripts | Consolidated Script |
|---------|-------------------|-------------------|
| **Coverage** | Limited to each role | All currently mapped variables across all roles |
| **Integration Point** | Inside role tasks | Top-level, before any roles execute |
| **Multi-role Support** | Separate validation per role | Single validation for all roles |
| **Centralized Configuration** | Duplicated patterns | Single source of truth |
| **Maintenance** | Pattern duplication across scripts | Single maintained file |

## Schema-Defined Variables

The script dynamically loads constraints from `schemas/sensitive/variables.json`, using its top-level `definitions` entries.

Important: discovery is not fully schema-driven. Variable detection depends on code-side mappings and path-aware logic in `validate_sensitive_variables.py`.

To add new sensitive variables:
1. Define them in the schema under `abstract.sensitive_variables.properties`
2. Add/update mapping or path-aware detection in `validate_sensitive_variables.py`
3. Re-run validation against merged test models to confirm detection and schema enforcement

## Known Limitations

- The script requires actual merged model files with concrete values
- Variable patterns are extracted from YAML keys in models (numeric suffixes 1-64)
- Path-aware detection relies on specific key names and nesting patterns
- Certificate and key validation currently checks PEM header format only (it does not perform full chain, key match, expiration, or trust validation)
- Suffix-style scans can include non-sensitive numeric keys (for example address fields like `address_1`), which must be filtered as non-sensitive

## Future Enhancements

Potential improvements for broader coverage:
- Auto-discovery of models from role directories
- Support for variables defined outside `abstract.sensitive_variables` schema
- YAML template introspection for indirect variable references
- Direct Ansible inventory parsing
- Pre-flight checks for schema pattern conflicts

## Troubleshooting

### Script Not Detecting Expected Variables

**Issue:** Variables defined in YAML but not detected by script.

**Solution:** Check that:
1. The YAML key matches a pattern in `_SENSITIVE_VAR_PATTERNS`
2. The value is a numeric identifier (1-64)
3. The nesting path matches expected patterns for path-aware detection
4. The model is valid JSON

### Schema Validation Failures

**Issue:** Variable present but validation fails against schema constraints.

**Solution:**
1. Check the variable's description in schema for requirements
2. Use `--verbose` flag to see full constraint descriptions
3. Verify value meets pattern, minLength, and maxLength requirements

## Related Files

- **Script:** `scripts/validate_sensitive_variables.py`
- **Schema:** `schemas/sensitive/variables.json` (top-level definitions)
- **Playbooks with Integrated Validation:**
  - `playbooks/deploy_ai_pod_phase1.yaml`
  - `playbooks/deploy_ai_pod_phase2.yaml`
  - `playbooks/deploy_observability.yaml`
  - `playbooks/deploy_openshift_phase1.yaml`
  - `playbooks/deploy_openshift_phase2.yaml`
  - `playbooks/deploy_storage.yaml`
