# Feature 2: Dynamic Payload Adapter

## Overview

Feature 2 implements dynamic attribute filtering to support deployment across Intersight environments:
- **SaaS** (intersight.com) - Full feature support, all attributes always available
- **CVA** (Cloud Virtual Appliance) - Limited attribute support

The adapter queries CVA's API schema to determine which attributes are supported, automatically strips unsupported attributes before deployment, and warns users about missing features.

**Note**: PVA (Private Virtual Appliance/On-Premises) will use the same implementation pattern as CVA.

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────┐
│  User Configuration (YAML templates)                     │
│  - Policies with full attribute sets                     │
│  - Profiles/Templates with references                    │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│  Dynamic Payload Adapter (Feature 2)                     │
│  1. Load target environment (SaaS/CVA/PVA)              │
│  2. Query environment API schema                        │
│  3. Extract supported attributes for each policy type   │
│  4. Compare user config against supported attributes    │
│  5. Strip unsupported attributes from payload           │
│  6. Log warnings about removed attributes               │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│  Intersight API Client                                   │
│  - POST/PATCH with filtered payload                     │
│  - Only includes attributes supported by target env     │
└─────────────────────────────────────────────────────────┘
```

### Environment Detection

The adapter determines the target environment from:
1. **Environment Variable** (priority 1): `INTERSIGHT_ENVIRONMENT` (saas/cva/pva)
2. **Command-line Argument** (priority 2): `--intersight-environment`
3. **API Endpoint URL** (priority 3): Pattern matching on endpoint domain
4. **Default** (priority 4): SaaS

### Credential Management

Credentials are stored in encrypted vault file at `~/.config/cisco-ai-pods/vault.yaml`:

```yaml
intersight:
  saas:
    endpoint: "https://intersight.com"
    apikey: "API_KEY_ID"
    secretkey: "SECRET_KEY"
  cva:
    endpoint: "https://cva-instance.example.com"
    apikey: "API_KEY_ID"
    secretkey: "SECRET_KEY"
```

Alternatively, environment variables override vault values:
- `intersight_api_key_id` - API Key ID
- `intersight_api_private_key` - API Secret Key
- `intersight_endpoint` - API Endpoint URL

## Implementation Phases

### Phase 1: Vault Configuration & Schema Caching (v0.1.16)

**Components:**
- Update vault loading to support SaaS/CVA configuration
- Create schema cache module to store supported attributes
- Implement environment detection logic

**Key Files:**
- `roles/intersight_ucs_provision/library/src/shared_functions.py` - Add vault parsing for multi-env
- `roles/intersight_ucs_provision/library/src/intersight/schema_cache.py` - NEW: Cache manager

**Deliverables:**
- [ ] Parse multi-environment vault configuration (SaaS + CVA)
- [ ] Detect target environment from credentials/arguments
- [ ] Load environment-specific credentials
- [ ] Store schema queries in persistent cache (`~/.cache/cisco-ai-pods/`)
- [ ] Unit tests for environment detection and vault parsing

### Phase 2: Schema Querying & Attribute Discovery (v0.1.16)

**Components:**
- Query CVA's API schema
- Extract supported attributes for each policy/profile type
- Compare with SaaS attribute set

**Key Files:**
- `roles/intersight_ucs_provision/library/src/intersight/schema_discovery.py` - NEW: Schema query logic

**Deliverables:**
- [ ] Query CVA's API for supported attributes
- [ ] Cache schema results for CVA
- [ ] Extract attribute names and types from schema responses
- [ ] Compare CVA attributes to SaaS (identify missing features)
- [ ] Unit tests for schema queries

### Phase 3: Payload Filtering & Warning System (v0.1.16)

**Components:**
- Compare user payload against CVA schema
- Strip unsupported attributes before API calls
- Generate warnings for removed attributes

**Key Files:**
- `roles/intersight_ucs_provision/library/src/intersight/payload_filter.py` - NEW: Filter logic
- `roles/intersight_ucs_provision/library/src/intersight/configure.py` - Integrate filtering into deployment

**Deliverables:**
- [ ] Implement attribute filtering before API calls (CVA only)
- [ ] Log removed attributes with reasons
- [ ] Generate per-object filtered payload report
- [ ] Summary of unsupported features by policy type
- [ ] Unit tests for filtering logic

## Detailed Design

### Schema Cache Structure

Schema results are cached locally to avoid repeated API queries:

```
~/.cache/cisco-ai-pods/
├── schemas/
│   ├── saas_v1_attributes.json      # SaaS full schema
│   ├── cva_v1_attributes.json       # CVA limited schema
│   └── pva_v1_attributes.json       # PVA limited schema
└── cache_metadata.json              # Cache version/timestamp
```

Cache format (per environment):
```json
{
  "environment": "cva",
  "timestamp": "2026-11-16T13:20:00Z",
  "api_version": "v1",
  "policies": {
    "bios": ["Name", "Description", "Tags", ...],
    "boot_order": ["Name", "Description", ...],
    "ethernet_adapter": ["Name", "Description", ...],
    ...
  },
  "profiles": {
    "server": ["Name", "Description", ...],
    "domain": ["Name", "Description", ...],
    ...
  }
}
```

### Attribute Filtering Logic

```python
def filter_payload(api_body, object_type, environment_schema):
    """
    Remove attributes not supported by target environment.
    
    Args:
        api_body: Dict of attributes to send to API
        object_type: Type of object (e.g., 'bios.Policy')
        environment_schema: Supported attributes for this object in target env
    
    Returns:
        (filtered_payload, removed_attributes)
    """
    supported = environment_schema.get(object_type, [])
    removed = {}
    
    for key, value in list(api_body.items()):
        if key not in supported:
            removed[key] = value
            del api_body[key]
    
    return api_body, removed
```

### Warning/Report Format

When attributes are stripped, users see:

```
⚠️  Attribute Filtering for CVA Environment
   Policy: 'AIPOD-AID-BIOS-Policy' (bios.Policy)
   Removed 3 attributes not supported in CVA:
   - CiscoOpromLaunchOptimization (SaaS-only feature)
   - CiscoXgmiMaxSpeed (requires CVA v3.1+)
   - EnableTdxSeamldr (processor feature not available)
   
   Recommendation: Upgrade CVA to v3.1 to support all features
```

## Configuration Guide

### Step 1: Update Vault File

Decrypt and edit your vault:
```bash
ansible-vault edit ~/.config/cisco-ai-pods/vault.yaml
```

Add CVA and PVA endpoints:
```yaml
intersight:
  saas:
    endpoint: "https://intersight.com"
    apikey: "your_saas_api_key"
    secretkey: "your_saas_secret"
  cva:
    endpoint: "https://cva.example.com"
    apikey: "your_cva_api_key"
    secretkey: "your_cva_secret"
  pva:
    endpoint: "https://pva.example.com"
    apikey: "your_pva_api_key"
    secretkey: "your_pva_secret"
```

### Step 2: Set Target Environment

Option A - Environment Variable:
```bash
export INTERSIGHT_ENVIRONMENT=cva
./deploy_intersight_ucs.py ...
```

Option B - Command-line Argument:
```bash
./deploy_intersight_ucs.py --intersight-environment pva ...
```

Option C - Automatic Detection:
```bash
# Script auto-detects based on endpoint URL
./deploy_intersight_ucs.py --intersight-endpoint https://cva.example.com ...
```

### Step 3: First Run (Schema Discovery)

First deployment to a new environment:
```bash
./deploy_intersight_ucs.py --intersight-environment cva --check
```

This will:
1. Query CVA's API schema
2. Cache supported attributes locally
3. Show what will be filtered
4. Display any warnings before actual deployment

## Testing Strategy

### Unit Tests

- **Environment Detection**: Verify correct environment identified from endpoint/env-var/arg
- **Vault Parsing**: Ensure multi-environment credentials parsed correctly
- **Schema Queries**: Mock API responses and verify schema extraction
- **Payload Filtering**: Test attribute removal logic with various payloads
- **Cache Management**: Verify cache read/write and expiration

### Integration Tests

- **End-to-end Filtering**: Deploy same config to SaaS/CVA/PVA, verify attribute differences
- **Cache Reuse**: Verify second deployment uses cached schema
- **Error Handling**: Test behavior when CVA/PVA unreachable or schema query fails
- **Warning Accuracy**: Verify warnings match actual filtered attributes

### Test Data

- Sample payloads with 50+ attributes
- Mock schema responses for each environment
- Known attribute differences (examples):
  - `CiscoOpromLaunchOptimization` - SaaS only
  - `CiscoXgmiMaxSpeed` - requires CVA v3.1+
  - Full BIOS attributes in SaaS, subset in CVA/PVA

## Security Considerations

1. **Vault Access**: Credentials remain encrypted at rest
2. **API Keys**: Each environment has separate API key; compromise isolated
3. **Cache Files**: Schema cache stored in user-readable location (`~/.cache/`), doesn't contain credentials
4. **Attribute Logging**: Filtered attributes logged with values stripped if sensitive (e.g., passwords)

## Rollback Plan

If Feature 2 causes issues:

1. **Revert to SaaS-Only**: 
   ```bash
   export INTERSIGHT_ENVIRONMENT=saas
   ./deploy_intersight_ucs.py ...  # No filtering applied
   ```

2. **Clear Schema Cache**:
   ```bash
   rm -rf ~/.cache/cisco-ai-pods/schemas/
   ```

3. **Disable Feature 2**:
   - Set environment variable `FEATURE_2_DISABLED=true` to skip filtering

## Success Criteria

✅ Users can deploy identical configuration to SaaS/CVA/PVA without manual modification  
✅ Unsupported attributes automatically stripped before API calls  
✅ Clear warnings explain what was removed and why  
✅ Schema cached to avoid repeated API queries  
✅ <5% performance impact on deployment operations  
✅ All existing tests continue to pass  
✅ 95%+ test coverage for new code  

## Related Issues/References

- **Feature 1**: Template compliance checking (v0.1.14-0.1.15)
- **GitHub Issue**: User request for CVA/PVA attribute filtering support
- **API Documentation**: Intersight API schema endpoints

## Timeline

- **v0.1.16**: All 3 Phases (Vault + Schema Discovery + Payload Filtering)

---

**Last Updated**: November 16, 2026  
**Status**: Design Phase  
**Assigned**: @tyscott_cisco  
