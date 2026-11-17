# Feature 2 Implementation Guide: Dynamic Payload Adapter

## Overview

Feature 2 adds dynamic payload filtering for CVA (Cloud Virtual Appliance) and PVA (Private Virtual Appliance) environments, allowing the same templates to work across SaaS, CVA, and PVA with automatic attribute stripping.

## Modules Created

### 1. `feature2_environment.py`
Handles multi-environment vault loading and environment detection.

**Key Classes:**
- `MultiEnvironmentVault`: Load credentials for SaaS/CVA/PVA from encrypted vault
- `SchemaCache`: Cache API schemas locally to reduce queries
- `EnvironmentDetector`: Detect target environment with priority logic

**Usage:**
```python
from src.intersight.feature2_environment import MultiEnvironmentVault, EnvironmentDetector

# Load vault
vault = MultiEnvironmentVault()

# Detect target environment
detector = EnvironmentDetector(vault)
env = detector.get_target_environment(
    env_var=os.getenv('INTERSIGHT_ENVIRONMENT'),
    endpoint=kwargs.args.intersight_fqdn
)

# Get credentials for target environment
creds = vault.get_environment_credentials(env)
endpoint = creds['endpoint']
apikey = creds['apikey']
secretkey = creds['secretkey']
```

**Vault Structure Required:**
```yaml
intersight:
  saas:
    endpoint: "https://intersight.com"
    apikey: "5a1234567890abcd"
    secretkey_file: "~/.config/cisco-ai-pods/intersight-secretkey"
  
  cva:
    endpoint: "https://cva.example.com"
    apikey: "5a1234567890abcd"
    secretkey_file: "~/.config/cisco-ai-pods/intersight-cva-secretkey"
  
  pva:
    endpoint: "https://pva.example.com"
    apikey: "5a1234567890abcd"
    secretkey_file: "~/.config/cisco-ai-pods/intersight-pva-secretkey"
```

### 2. `feature2_schema_discovery.py`
Queries API schemas and discovers supported attributes.

**Key Classes:**
- `SchemaDiscovery`: Query environment's API for schema information
- `SchemaAnalyzer`: Compare and report on attribute differences

**Usage:**
```python
from src.intersight.feature2_schema_discovery import SchemaDiscovery

# Initialize discoverer
discoverer = SchemaDiscovery(endpoint, apikey, secretkey)

# Discover all supported attributes for policies
policies_attrs = discoverer.discover_all_attributes(category='policies')

# Or query specific endpoint
schema = discoverer.query_schema('bios/Policies')
attributes = discoverer.extract_attributes(schema)

# Compare with SaaS
comparison = discoverer.compare_environments(saas_attrs, cva_attrs)
report = SchemaAnalyzer.generate_report(comparison)
print(report)
```

### 3. `feature2_payload_filter.py`
Filters unsupported attributes from payloads before API calls.

**Key Classes:**
- `PayloadFilter`: Filter attributes from payloads
- `FilteredPayloadTracker`: Audit log of filtered operations

**Usage:**
```python
from src.intersight.feature2_payload_filter import PayloadFilter

# Initialize filter with supported attributes
filter = PayloadFilter(supported_attributes=cva_attributes)

# Filter a payload
filtered_body, removed = filter.filter_payload(
    api_body=original_payload,
    object_type='bios',
    strict=True  # Remove unsupported attrs vs warn
)

# Recursively filter nested objects
filtered_body, all_removed = filter.filter_nested_object(
    obj=original_payload,
    object_type='bios',
    strict=True
)

# Generate warning for user
warning = filter.generate_warning_message('cva')
print(warning)
```

## Integration Points

### 1. In `api.py` - ApiClient class

**Location:** After API response is received, before processing

```python
# In ApiClient.call_api() or similar method
if environment != 'saas':
    # Apply payload filtering
    from src.intersight.feature2_payload_filter import PayloadFilter
    
    payload_filter = PayloadFilter(schema_cache.get_schema(environment))
    api_body, removed = payload_filter.filter_payload(api_body)
    
    if removed:
        self.logger.warning(
            f"Filtered {len(removed)} unsupported attributes for {environment}"
        )
```

### 2. In `configure.py` - Before API calls

**Location:** Line 820+ where policies/pools are deployed

```python
# Before making PATCH/POST calls
if environment != 'saas':
    payload_filter = PayloadFilter(schema_cache.get_schema(environment))
    
    for policy_name, policy_data in kwargs.policies[k].items():
        # Filter the policy payload
        filtered_body, removed = payload_filter.filter_payload(
            policy_data.get('body', {}),
            object_type=get_object_type(policy_data)
        )
        
        # Update kwargs with filtered body
        kwargs.policies[k][policy_name]['body'] = filtered_body
        
        if removed:
            self.logger.info(
                f"Filtered {len(removed)} attributes from {policy_name}"
            )
```

### 3. In `deploy_intersight_ucs.py` - Command-line support

**Add argument:**
```python
parser.add_argument(
    '--intersight-environment',
    choices=['saas', 'cva', 'pva'],
    default=None,
    help='Target Intersight environment (default: auto-detect from endpoint)'
)
```

**Usage in kwargs:**
```python
from src.intersight.feature2_environment import EnvironmentDetector, MultiEnvironmentVault

vault = MultiEnvironmentVault()
detector = EnvironmentDetector(vault)

kwargs.intersight_environment = detector.get_target_environment(
    env_var=os.getenv('INTERSIGHT_ENVIRONMENT'),
    endpoint=kwargs.args.intersight_fqdn
)

if kwargs.args.intersight_environment:
    kwargs.intersight_environment = kwargs.args.intersight_environment
```

### 4. In notifications.py - Logging filtered attributes

**Add to operation completion messages:**
```python
if hasattr(kwargs, 'filtered_attributes') and kwargs.filtered_attributes:
    for obj_type, removed in kwargs.filtered_attributes.items():
        logger.warning(
            f"Note: {len(removed)} attributes were filtered for {obj_type} "
            f"({kwargs.intersight_environment})"
        )
```

## Implementation Workflow

### Phase 1: Environment Detection (Already done)
- ✅ Load vault credentials for multiple environments
- ✅ Detect target environment (env var → endpoint pattern → default)
- ✅ Validate credentials exist

### Phase 2: Schema Discovery (Already done)
- ✅ Query API schemas from target environment
- ✅ Extract supported attributes per object type
- ✅ Cache schemas locally for reuse
- ✅ Compare SaaS vs CVA/PVA attributes

### Phase 3: Payload Filtering (Already done)
- ✅ Filter unsupported attributes from payloads
- ✅ Support nested object filtering
- ✅ Generate user warnings about filtered attributes
- ✅ Audit log of filtered operations

### Phase 4: Integration (Next - To Do)
- [ ] Integrate environment detection into deploy script
- [ ] Add command-line argument for environment selection
- [ ] Load schema cache on startup
- [ ] Apply filtering before API calls
- [ ] Handle CVA API failures gracefully (fall back to no filtering)

### Phase 5: Testing (Next - To Do)
- [ ] Unit tests for environment detection
- [ ] Unit tests for multi-env vault loading
- [ ] Unit tests for payload filtering
- [ ] Integration tests with CVA (when available)
- [ ] Edge case tests (missing attributes, nested objects, etc.)

## Environment Detection Priority

1. **Command-line argument:** `--intersight-environment cva`
2. **Environment variable:** `INTERSIGHT_ENVIRONMENT=cva`
3. **API endpoint pattern:**
   - `intersight.com` → SaaS
   - `cva.example.com` → CVA
   - `pva.example.com` → PVA
4. **Default:** SaaS

## Schema Caching

Schemas are cached at: `~/.cache/cisco-ai-pods/schemas/`

**Cache files:**
- `saas_v1_schema.json` - SaaS API schema
- `cva_v1_schema.json` - CVA API schema
- `pva_v1_schema.json` - PVA API schema

**Cache invalidation:**
- Manual: `cache.clear_cache('cva')` or `cache.clear_cache()`
- Automatic: (Optional) Can add TTL-based expiry (e.g., 7 days)

## Error Handling

### Missing Schema
If schema query fails:
1. Check if cached version exists, use it
2. If no cache, warn user and proceed without filtering
3. Log warning: "Schema query failed, proceeding without filtering"

### Missing Credentials
If environment credentials not in vault:
1. Raise ValueError with clear message
2. Direct user to VAULT_STRUCTURE_GUIDE.md
3. Exit gracefully

### API Failures
If CVA API returns error during deployment:
1. Log the error
2. Optionally retry (with backoff)
3. Continue with original payload (may fail on CVA but clear error)
4. Warn user about unsupported attributes in final message

## Testing the Implementation

### Manual Testing
```bash
# Test environment detection
export INTERSIGHT_ENVIRONMENT=cva
python deploy_intersight_ucs.py --dir roles/intersight_ucs_provision

# Test with explicit environment
python deploy_intersight_ucs.py --dir roles/intersight_ucs_provision \
    --intersight-environment cva

# Check vault loading
python -c "
from src.intersight.feature2_environment import MultiEnvironmentVault
vault = MultiEnvironmentVault()
print(vault.get_environment_credentials('cva'))
"
```

### Unit Test Coverage
```python
# Test environment detection
def test_detect_environment_from_env_var()
def test_detect_environment_from_endpoint()
def test_detect_environment_default_saas()

# Test vault loading
def test_load_vault_credentials_saas()
def test_load_vault_credentials_cva()
def test_load_vault_credentials_secretkey_file()

# Test payload filtering
def test_filter_unsupported_attributes()
def test_filter_nested_objects()
def test_filter_respects_supported_attrs()

# Test schema cache
def test_schema_cache_save_and_load()
def test_schema_cache_clear()
```

## Next Steps

1. Create integration tests to verify modules work together
2. Update `deploy_intersight_ucs.py` to use environment detection
3. Add `--intersight-environment` command-line argument
4. Integrate filtering into API calls in `configure.py`
5. Test with CVA instance (when available)
6. Update user documentation

## References

- Previous checkpoint: `009-feature-1-complete-feature-2-d.md`
- Design document: `docs/FEATURE_2_DYNAMIC_PAYLOAD_ADAPTER.md`
- Vault structure: `VAULT_STRUCTURE_GUIDE.md`
