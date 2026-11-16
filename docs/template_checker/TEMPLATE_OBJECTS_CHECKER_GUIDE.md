# Template Objects Compliance Checker - Implementation Guide

## Overview

This guide provides comprehensive documentation for checking **Template Objects** (BIOS Templates, Ethernet Adapter Templates, Fibre Channel Adapter Templates, Storage Templates, vNIC Templates, vHBA Templates) against the Intersight SaaS API.

## Template Object Types

### 1. **BIOS Profile Templates** (`compute/BiosProfileTemplates`)
- **Purpose**: Reusable BIOS configuration templates
- **API Endpoint**: `https://intersight.com/api/v1/compute/BiosProfileTemplates`
- **Key Attributes**:
  - `Name`: Template name
  - `Description`: Template description
  - `BiosSettings`: Array of BIOS token configurations
  - `SourceTemplate`: Reference to source template (if cloned)
  - `Attributes`: Individual BIOS settings

### 2. **Ethernet Adapter Profile Templates** (`ether/AdapterProfileTemplates`)
- **Purpose**: Reusable Ethernet adapter settings
- **API Endpoint**: `https://intersight.com/api/v1/ether/AdapterProfileTemplates`
- **Key Attributes**:
  - `Name`: Template name
  - `EthSettings`: Ethernet settings configuration
  - `RssHashSettings`: RSS configuration

### 3. **Fibre Channel Adapter Profile Templates** (`fc/AdapterProfileTemplates`)
- **Purpose**: Reusable Fibre Channel adapter settings
- **API Endpoint**: `https://intersight.com/api/v1/fc/AdapterProfileTemplates`
- **Key Attributes**:
  - `Name`: Template name
  - `FcSettings`: Fibre Channel settings

### 4. **Storage Profile Templates** (`storage/StorageProfileTemplates`)
- **Purpose**: Reusable storage configuration templates
- **API Endpoint**: `https://intersight.com/api/v1/storage/StorageProfileTemplates`
- **Key Attributes**:
  - `Name`: Template name
  - `StoragePolicies`: Associated storage policies
  - `RaidLevel`: RAID configuration

### 5. **vNIC (Ethernet) Profile Templates** (`vnic/EthAdapterProfileTemplates`)
- **Purpose**: Reusable vNIC templates for Ethernet profiles
- **API Endpoint**: `https://intersight.com/api/v1/vnic/EthAdapterProfileTemplates`
- **Key Attributes**:
  - `Name`: Template name
  - `EthIf`: Ethernet interface settings

### 6. **vHBA (Fibre Channel) Profile Templates** (`vhba/FibreChannelAdapterProfileTemplates`)
- **Purpose**: Reusable vHBA templates for Fibre Channel profiles
- **API Endpoint**: `https://intersight.com/api/v1/vhba/FibreChannelAdapterProfileTemplates`
- **Key Attributes**:
  - `Name`: Template name
  - `FcIf`: Fibre Channel interface settings

---

## How to Query Live Template Objects

### Using Intersight API CLI (cURL)

```bash
# BIOS Templates
curl -s \
  -H "Authorization: Bearer <token>" \
  "https://intersight.com/api/v1/compute/BiosProfileTemplates?$top=100" | jq .

# Ethernet Adapter Templates
curl -s \
  -H "Authorization: Bearer <token>" \
  "https://intersight.com/api/v1/ether/AdapterProfileTemplates?$top=100" | jq .

# Fibre Channel Adapter Templates
curl -s \
  -H "Authorization: Bearer <token>" \
  "https://intersight.com/api/v1/fc/AdapterProfileTemplates?$top=100" | jq .

# Storage Templates
curl -s \
  -H "Authorization: Bearer <token>" \
  "https://intersight.com/api/v1/storage/StorageProfileTemplates?$top=100" | jq .

# vNIC Templates
curl -s \
  -H "Authorization: Bearer <token>" \
  "https://intersight.com/api/v1/vnic/EthAdapterProfileTemplates?$top=100" | jq .

# vHBA Templates
curl -s \
  -H "Authorization: Bearer <token>" \
  "https://intersight.com/api/v1/vhba/FibreChannelAdapterProfileTemplates?$top=100" | jq .
```

### Using Python with IntersightAuth

```python
from intersight_auth import IntersightAuth

# Initialize auth
auth = IntersightAuth(
    secret_key='your_secret_key',
    api_key_id='your_api_key_id',
    api_url='https://intersight.com'
)

# Query BIOS Templates
response = auth.request('get', 'https://intersight.com/api/v1/compute/BiosProfileTemplates?$top=100')
templates = response.json().get('Results', [])

# Extract attributes from templates
attributes = set()
for template in templates:
    for key in template.keys():
        if key not in ['Moid', 'ObjectType', 'ClassId', 'CreateTime', 'ModTime', 'Organization', 'Tags']:
            attributes.add(key)

print(f"Found {len(templates)} BIOS templates")
print(f"Attributes: {sorted(attributes)}")
```

---

## Schema Structure for Template Objects

Templates are defined in the schemas:

### Location
```
schemas/source/intersight/templates.json
schemas/source/intersight.json  (consolidated schema)
```

### Key Sections
```json
{
  "definitions": {
    "bios_templates": {
      "properties": {
        "name": { ... },
        "description": { ... },
        "bios_tokens": { ... }
      }
    },
    "ethernet_adapter_templates": { ... },
    "fibre_channel_adapter_templates": { ... },
    "storage_templates": { ... },
    "vnic_templates": { ... },
    "vhba_templates": { ... }
  }
}
```

---

## Comparison Process

### Step 1: Extract Template Attributes from Schema
```python
from pathlib import Path
import json

schema_path = Path('schemas/source/intersight/templates.json')
with open(schema_path) as f:
    schema = json.load(f)

# Get BIOS template attributes
bios_template_def = schema['definitions']['bios_templates']
schema_attrs = set(bios_template_def['properties'].keys())
```

### Step 2: Fetch Live Templates from API
```python
# Query Intersight API for actual templates
response = auth.request('get', 'https://intersight.com/api/v1/compute/BiosProfileTemplates?$top=100')
live_templates = response.json().get('Results', [])

# Extract attributes from live templates
api_attrs = set()
for template in live_templates:
    for key in template.keys():
        if not key.startswith('_') and key not in SKIP_ATTRS:
            api_attrs.add(key)
```

### Step 3: Compare Attributes
```python
# Find gaps
missing_in_schema = api_attrs - schema_attrs  # API has but schema doesn't
unused_in_api = schema_attrs - api_attrs      # Schema has but API doesn't
both = api_attrs & schema_attrs               # Covered

coverage = (len(both) / len(api_attrs) * 100) if api_attrs else 0
```

### Step 4: Report Results
```python
print(f"Coverage: {coverage:.1f}%")
print(f"\nMissing from schema:")
for attr in sorted(missing_in_schema):
    print(f"  - {attr}")

print(f"\nNot used in API:")
for attr in sorted(unused_in_api):
    print(f"  - {attr}")
```

---

## Expected Output

### Console Output
```
================================================================================
TEMPLATE OBJECT COMPLIANCE ANALYSIS SUMMARY
================================================================================

✅ BIOS Profile Templates              98.5% (1 gaps)
⚠️ Ethernet Adapter Templates          95.2% (3 gaps)
✅ Fibre Channel Adapter Templates     99.0% (1 gaps)
✅ Storage Profile Templates           97.8% (2 gaps)
✅ vNIC Profile Templates              96.5% (2 gaps)
✅ vHBA Profile Templates              98.0% (1 gaps)

================================================================================
Average Coverage: 97.5%
Total Gaps: 10
================================================================================
```

### Report Files Generated

1. **template_objects_diff.md** - Human-readable markdown report
2. **template_objects_diff.json** - Structured JSON report
3. **template_objects_diff_*.log** - Detailed execution log

---

## Running the Checker

### Basic Usage
```bash
python3 check_template_objects.py
```

### Analyze Specific Template Type
```bash
python3 check_template_objects.py --template-type bios_templates
python3 check_template_objects.py --template-type ethernet_adapter_templates
```

### Analyze All Template Types
```bash
python3 check_template_objects.py --template-type all
```

### With Custom Vault Location
```bash
python3 check_template_objects.py \
  --vault /path/to/vault.yaml \
  --vault-password /path/to/vault-password
```

### With API Credentials as Arguments
```bash
python3 check_template_objects.py \
  --api-key-id YOUR_KEY_ID \
  --api-secret-key /path/to/secret.txt
```

### Verbose Output
```bash
python3 check_template_objects.py --verbose
```

---

## Understanding the Results

### Template Count
- Shows number of template objects found in live API
- Useful for understanding adoption

### API Attributes
- Number of distinct attributes across all template objects
- Indicates feature richness

### Schema Attributes
- Number of attributes defined in schema
- Should match API attributes

### Coverage Percentage
- `(Attributes in both / API attributes) * 100`
- Target: **98%+** for production

### Missing from Schema (api_only)
- Attributes found in live API templates but NOT in schema
- These need to be added to schema
- Priority: HIGH - blocks template creation

### Unused in Schema (schema_only)
- Attributes defined in schema but NOT found in live API templates
- May be:
  - Deprecated attributes
  - Feature not yet adopted
  - Conditional attributes
- Priority: LOW - review and document

---

## Common Gaps & Solutions

### Gap: `EnableTrunking` in Fibre Channel Adapter Templates
**Issue**: Attribute exists in API but not in schema  
**Solution**: Add to schema definition and document platform support

### Gap: `TargetPlatform` in BIOS Templates
**Issue**: New attribute for multi-platform support  
**Solution**: Add with platform conditionals (UCS Domain vs Unified Edge)

### Gap: `IsAesPrimaryKeySet` in Ethernet Adapter Templates
**Issue**: Read-only attribute (indicates if key is set)  
**Solution**: Add to skip list (don't require in templates)

---

## Integration with CI/CD

### GitHub Actions Example
```yaml
name: Template Compliance Check

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM
  workflow_dispatch:

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      
      - name: Run compliance checker
        env:
          VAULT_PASSWORD: ${{ secrets.VAULT_PASSWORD }}
          API_KEY_ID: ${{ secrets.INTERSIGHT_API_KEY_ID }}
          API_SECRET_KEY: ${{ secrets.INTERSIGHT_SECRET_KEY }}
        run: |
          python3 check_template_objects.py --verbose
      
      - name: Upload reports
        uses: actions/upload-artifact@v3
        with:
          name: compliance-reports
          path: template_objects_diff.*
      
      - name: Notify on gaps
        if: failure()
        run: |
          # Send email/Slack notification with report
```

---

## Scheduled Execution

### Cron Job Example
```bash
# Run daily at 2 AM, email results
0 2 * * * cd /path/to/Cisco-AI-PODs && \
  python3 roles/intersight_ucs_provision/library/src/intersight/check_template_objects.py && \
  mail -s "Template Object Compliance Report" user@example.com < template_objects_diff.md
```

---

## Troubleshooting

### "IntersightAuth not available"
**Problem**: Python module not installed  
**Solution**:
```bash
pip install intersight_auth
# or
pip install intersight-iac-python
```

### "No templates found"
**Problem**: API query returned empty  
**Solutions**:
1. Verify API credentials
2. Check organization access
3. Confirm templates exist in Intersight
4. Check network connectivity

### "Credentials incomplete"
**Problem**: Missing API key or secret key  
**Solutions**:
1. Check vault file location: `~/.config/cisco-ai-pods/vault.yaml`
2. Check vault password file: `~/.config/cisco-ai-pods/vault-password`
3. Use `--api-key-id` and `--api-secret-key` arguments directly

---

## Implementation Roadmap

### Phase 1: Foundation (Current)
- ✅ Create template object analyzer framework
- ✅ Identify template types and API endpoints
- ✅ Build schema-to-API comparison logic
- ✅ Generate reports (Markdown, JSON)

### Phase 2: Integration (Next)
- [ ] Integrate with existing `check_template_differences.py`
- [ ] Add to CI/CD pipeline
- [ ] Email notifications on gaps
- [ ] Dashboard/metrics tracking

### Phase 3: Automation (Future)
- [ ] Auto-update schema from live API
- [ ] Scheduled daily/weekly checks
- [ ] Trend analysis (gaps over time)
- [ ] Attribute deprecation tracking

---

## References

- **Intersight API Documentation**: https://intersight.com/help
- **easy-imm Schema**: https://github.com/scotttyso/intersight-tools/blob/master/schemas/easy-imm.json
- **Cisco AI PODs**: https://github.com/scotttyso/Cisco-AI-PODs

---

## Support

For issues or questions:
1. Check the logs: `template_objects_diff_*.log`
2. Review this guide
3. Check GitHub issues
4. Contact: Scott Tyso (@tyscott_cisco)
