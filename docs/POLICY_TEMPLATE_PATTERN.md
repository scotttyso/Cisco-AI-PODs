# Policy Template Enhancement Pattern Guide

**Last Updated:** 2026-11-14  
**Pattern Source:** switch_control.json.j2 implementation  
**Purpose:** Document the three-layer pattern for adding platform-specific attributes to policy templates

---

## Quick Summary

When adding new attributes to Intersight policy templates that support multiple platforms (UCS Domain, Unified Edge), you must update **three distinct files**:

| Layer | File | Purpose |
|-------|------|---------|
| 1 | `{policy}.json.j2` | Runtime template with platform conditionals |
| 2 | `intersight.json` | User-facing schema documentation |
| 3 | `intersight/policies.json` | Detailed attribute validation definitions |

---

## Layer 1: Jinja2 Template (Runtime)

**Location:** `roles/intersight_ucs_provision/templates/intersight/policies/{policy_name}.json.j2`

### Core Pattern

```jinja2
{% set _platform = item.target_platform | default('UCS Domain') %}

{# Platform-specific: Unified Edge only #}
{% if _platform == 'Unified Edge' %}
  "LldpSettings": {
    "Enabled": {{ item.enable_lldp | default(false) | tojson }},
    "ObjectType": "fabric.LldpGlobalSettings"
  },
{% endif %}

{# Platform-specific: UCS Domain only #}
{% if _platform == 'UCS Domain' %}
  "VlanPortOptimizationEnabled": {{ item.vlan_port_count_optimization | default(false) | tojson }},
{% endif %}

{# Conditional: Both platforms but with conditions #}
{% if _platform == 'UCS Domain' and item.switching_mode_ethernet | default('switch') == 'end-host' %}
  "MacLearningSettings": {
    "DisabledVlans": "{{ item.disabled_mac_address_learning_vlans | default('') }}",
    "ObjectType": "fabric.MacLearningSettings"
  },
{% endif %}
```

### Implementation Checklist

- [ ] Store platform in variable at template top
- [ ] Wrap platform-specific attributes in `{% if _platform == 'Platform' %}`
- [ ] Include `"ObjectType": "fabric.SettingType"` for nested objects
- [ ] Provide sensible defaults with `| default(value)`
- [ ] Handle conditional requirements (e.g., only if other attribute set)
- [ ] Test template output for both platforms

---

## Layer 2: Main Schema Description

**Location:** `schemas/source/intersight.json`

**Find:** Search for `"switch_control": {` (or your policy name)

### Pattern

Update the `description` field with clear platform separation:

```json
"switch_control": {
    "description": "The Switch Control policy configures fabric switching behavior.\n\nRequired Attributes:\n  * `name`\n  * `target_platform`\n\n########################################\n# Unified Edge\n########################################\n\nOptional Attributes:\n  * `description`\n  * `enable_jumbo_frames`\n  * `enable_lldp` - Enable LLDP Global Settings\n  * `enable_stp` - Enable Spanning Tree Protocol\n  * `mac_address_table_aging`\n  * `mac_aging_time`\n  * `tags`\n\n########################################\n# UCS Domain\n########################################\n\nOptional Attributes:\n  * `aes_primary_key`\n  * `description`\n  * `disabled_mac_address_learning_vlans` - Only valid for switching_mode_ethernet `End Host`\n  * `switching_mode_ethernet`\n  * `switching_mode_fc`\n  * `mac_address_table_aging`\n  * `mac_aging_time`\n  * `tags`\n  * `reserved_vlan_start_id`\n  * `udld_global_settings`\n  * `vlan_port_count_optimization`\n",
```

### Implementation Checklist

- [ ] Add "Required Attributes" section (attributes needed for all platforms)
- [ ] Create "# Unified Edge" delimiter section
- [ ] Create "# UCS Domain" delimiter section
- [ ] List platform-specific attributes under respective sections
- [ ] Add clarifying notes with asterisks for conditional attributes
- [ ] Use `\n` for line breaks in JSON strings
- [ ] Use backticks around attribute names

---

## Layer 3: Policy Schema Definitions

**Location:** `schemas/source/intersight/policies.json`

**Find:** Search for `"definitions": {` then find your policy

### Pattern

Add or update property definitions with type, description, and defaults:

```json
"switch_control": {
  "type": "object",
  "description": "Switch Control Policy configuration",
  "properties": {
    "name": {
      "type": "string",
      "description": "Policy name"
    },
    "target_platform": {
      "type": "string",
      "enum": ["UCS Domain", "Unified Edge"],
      "default": "UCS Domain",
      "description": "Target platform for this policy"
    },
    "enable_lldp": {
      "type": "boolean",
      "default": false,
      "description": "Enable LLDP for Unified Edge. (UCS Domain: always false)"
    },
    "enable_stp": {
      "type": "boolean",
      "default": false,
      "description": "Enable STP for Unified Edge. (UCS Domain: always disabled)"
    },
    "disabled_mac_address_learning_vlans": {
      "type": "string",
      "description": "VLANs where MAC learning is disabled (UCS Domain only, requires switching_mode_ethernet = 'End Host')"
    }
  },
  "required": ["name", "target_platform"],
  "additionalProperties": false
}
```

### Implementation Checklist

- [ ] Define type for each property (string, boolean, object, array, integer, etc.)
- [ ] Add description with platform applicability
- [ ] Include sensible defaults
- [ ] Specify enum values if constrained
- [ ] Mark conditional requirements in description
- [ ] Update `required` array if needed
- [ ] Set `additionalProperties: false` to prevent typos

---

## Complete Example: Adding MacLearningSettings

### Scenario
Add MacLearningSettings to switch_control, available only on UCS Domain when in End Host mode.

### Step 1: Update Jinja2 Template

In `switch_control.json.j2`, after MacAgingSettings block:

```jinja2
{% if _platform == 'UCS Domain' and item.switching_mode_ethernet | default('switch') == 'end-host' and item.disabled_mac_address_learning_vlans is defined %}
  "MacLearningSettings": {
    "DisabledVlans": "{{ item.disabled_mac_address_learning_vlans | default('') }}",
    "ObjectType": "fabric.MacLearningSettings"
  },
{% endif %}
```

### Step 2: Update intersight.json

Find `"switch_control"` and update description under `# UCS Domain` section:

```
  * `disabled_mac_address_learning_vlans` - Comma-separated VLANs where MAC learning disabled (End Host mode only)
```

### Step 3: Update intersight/policies.json

In the switch_control definitions, add property:

```json
"disabled_mac_address_learning_vlans": {
  "type": "string",
  "description": "Comma-separated list of VLAN IDs where MAC address learning is disabled. Only valid when target_platform is 'UCS Domain' and switching_mode_ethernet is set to 'End Host'."
}
```

### Step 4: Validate

```bash
# Validate schema syntax
python3 -m json.tool schemas/source/intersight.json > /dev/null

# Test template rendering
cd roles/intersight_ucs_provision/templates/intersight/policies
jinja2 switch_control.json.j2 \
  -D item.name=test \
  -D item.target_platform='UCS Domain' \
  -D item.switching_mode_ethernet='end-host' \
  -D item.disabled_mac_address_learning_vlans='100,101,102'
```

---

## Key Principles

### 1. Platform Awareness
- Always check `target_platform` before adding platform-specific attributes
- Store platform in variable for reuse: `{% set _platform = item.target_platform | default('UCS Domain') %}`

### 2. Documentation Layering
- Layer 1 (Template): HOW it works
- Layer 2 (intersight.json): WHAT users can configure
- Layer 3 (policies.json): WHERE validation happens

### 3. Sensible Defaults
- Every attribute should have a `| default()` in Jinja2
- Consider security: sensitive fields default to disabled
- Consider compatibility: defaults for each platform

### 4. Nested Objects
- Always include `"ObjectType": "fabric.SettingType"` for complex attributes
- Match ObjectType to Intersight API schema
- Document nested properties in policies.json

### 5. Conditional Requirements
- Note in description if attribute only applies when another is set
- Example: "Only valid when switching_mode_ethernet = 'End Host'"
- Use this in template conditions: `and item.switching_mode_ethernet == 'end-host'`

---

## Testing Checklist

Before committing changes:

- [ ] Schema JSON validates: `python3 -m json.tool`
- [ ] Template renders for UCS Domain
- [ ] Template renders for Unified Edge
- [ ] Playbook accepts new attributes
- [ ] Documentation is clear and complete
- [ ] Attribute values in examples match schema enums
- [ ] All required fields are populated

---

## Common Mistakes to Avoid

❌ **Don't:** Add attributes without platform checks  
✅ **Do:** Always wrap with `{% if _platform == '...' %}`

❌ **Don't:** Forget ObjectType for nested objects  
✅ **Do:** Include `"ObjectType": "fabric.SettingType"`

❌ **Don't:** Document in only one layer  
✅ **Do:** Update all three: template, intersight.json, policies.json

❌ **Don't:** Use inconsistent attribute naming  
✅ **Do:** Use snake_case in templates, match Intersight API names in JSON

❌ **Don't:** Leave attributes without defaults  
✅ **Do:** Provide `| default(value)` in all templates

---

## Files to Update Summary

When adding new policy attributes:

```
1. Jinja2 Template
   File: roles/intersight_ucs_provision/templates/intersight/policies/{policy}.json.j2
   Action: Add platform-conditional attribute blocks

2. Schema Description
   File: schemas/source/intersight.json
   Search: "{policy_name}"
   Action: Update description with platform sections

3. Schema Definitions
   File: schemas/source/intersight/policies.json
   Search: "definitions"
   Action: Add property definitions for new attributes
```

---

## Related Policies Using This Pattern

✅ Implemented:
- switch_control.json.j2 (LldpSettings, MacLearningSettings, StpSettings)
- system_qos.json.j2 (some platform-specific attributes)

🔄 Consider for:
- fibre_channel_network.json.j2 (EnableTrunking)
- storage.json.j2 (DriveGroup handling)
- Other policies as needed

---

## Future Enhancements

- [ ] Create validator script to check consistency across all three layers
- [ ] Auto-generate documentation from schema definitions
- [ ] Template generator based on API schema
- [ ] Integration tests for template-schema validation

