# Release v0.1.15: Feature 1 Enhancements & Template Completeness

**Release Date:** 2026-11-14  
**Status:** Ready for Production  
**Previous Versions:** Includes changes from v0.1.13 and v0.1.14 plus new enhancements

---

## Overview

Feature 1 (Live Intersight Template Difference Checker) now reaches **98.1% template compliance** with new platform-specific attributes, enhanced schemas, and comprehensive validation patterns.

---

## ✨ What's New

### 1. **Enhanced VLAN Templates & Schema**

Added two critical VLAN attributes for switch control:
- `AutoAllowOnInterSwitchPorts` - Enable automatic ISL port configuration
- `AutoAllowOnSecureRouterRoles` - Support for secure router role discovery

**Files Updated:**
- `roles/intersight_ucs_provision/templates/intersight/policies/vlan.vlans.json.j2`
- `schemas/source/intersight/policies.json` (new property definitions)
- `schemas/source/intersight.json` (updated descriptions)

### 2. **Switch Control Policy Platform-Specific Attributes**

Implemented three-layer pattern for platform-specific attributes (UCS Domain vs Unified Edge):

#### New Settings Added:
- **LldpSettings** (Unified Edge + UCS Domain)
  - Enable LLDP global settings and configuration
  
- **MacLearningSettings** (UCS Domain, End Host mode only)
  - Disabled VLAN specification for MAC address learning
  
- **StpSettings** (Unified Edge + UCS Domain)
  - Spanning Tree Protocol configuration

**Files Updated:**
- `roles/intersight_ucs_provision/templates/intersight/policies/switch_control.json.j2`
- `schemas/source/intersight/policies.json` (complete property definitions with platform notes)
- `schemas/source/intersight.json` (platform-specific sections in descriptions)

**Example:** Only MacLearningSettings applies when:
```
target_platform == 'UCS Domain' AND switching_mode_ethernet == 'end-host'
```

### 3. **Template Difference Checker Bug Fixes**

**Critical Fix:** API Endpoint Mappings
- **Before:** Querying child objects (fabric/Vlans, fabric/Vsans)
- **After:** Querying parent policies (fabric/EthNetworkPolicies, fabric/FcNetworkPolicies)
- **Impact:** Eliminated false positives; accurate attribute comparison

**Enhancement:** JSON Attribute Extraction
- Improved depth-aware parsing to extract only top-level keys
- Excludes reference objects (Profiles, Groups, Providers) from compliance gaps
- More accurate exclusion system in `attribute_exclusions.yaml`

### 4. **New Documentation: Policy Template Enhancement Pattern**

Comprehensive guide in `docs/POLICY_TEMPLATE_PATTERN.md`:
- Three-layer implementation pattern
- Platform-specific conditional handling
- Testing checklist
- Common mistakes and solutions
- Future policy enhancement guidance

---

## 📊 Template Compliance Report

### Overall Status
- **Templates Analyzed:** 104
- **Fully Compliant:** 102 (98.1%)
- **Partial/Under Review:** 2

### Key Findings

#### ✅ BIOS Policy - 100% Complete
- **473 BIOS settings** ✓ All present
- GPU controls, PCIe slots, CPU frequency, security features
- All AMD CBS and Intel technology settings included
- Production ready with zero missing attributes

#### ✅ VLAN Policy - Now Complete
- **AutoAllowOnInterSwitchPorts** ✓ Added
- **AutoAllowOnSecureRouterRoles** ✓ Added
- Complete ISL and secure router support

#### ✅ Switch Control Policy - Enhanced
- **LldpSettings** ✓ Added (platform-conditional)
- **MacLearningSettings** ✓ Added (UCS Domain + End Host mode)
- **StpSettings** ✓ Added (platform-conditional)
- Full support for UCS Domain and Unified Edge platforms

### Attribute Exclusions Updated
System/reference attributes now properly excluded from gap analysis:
- Global: Profiles, Groups, Providers, ClassId, Moid, ObjectType, Tags
- Policy-specific: IsAesPrimaryKeySet (switch_control), VsanSettings, VlanSettings
- Improves accuracy of compliance reporting

---

## 🔧 Technical Details

### Three-Layer Pattern (Established)

When adding platform-specific attributes, update:

1. **Jinja2 Template** - Runtime with platform conditionals
   ```jinja2
   {% set _platform = item.target_platform | default('UCS Domain') %}
   {% if _platform == 'Unified Edge' %}
     "LldpSettings": { ... }
   {% endif %}
   ```

2. **intersight.json** - User-facing documentation
   ```json
   "description": "...\n# Unified Edge\n...\n# UCS Domain\n..."
   ```

3. **intersight/policies.json** - Schema definitions with platform notes
   ```json
   "properties": {
     "enable_lldp": {
       "description": "LLDP settings (Unified Edge specific)"
     }
   }
   ```

See `docs/POLICY_TEMPLATE_PATTERN.md` for complete implementation guide.

### Nested Object Attributes

Always include `"ObjectType"` for complex settings:
```json
"LldpSettings": {
  "Enabled": true,
  "ObjectType": "fabric.LldpGlobalSettings"
}
```

---

## 🐛 Bug Fixes

### 1. API Endpoint Mapping (Critical)
- **Issue:** VLAN/VSAN queries hitting child endpoints instead of parent policies
- **Fix:** Updated mappings in `check_template_differences.py`
  - vlan → fabric/EthNetworkPolicies
  - vsan → fabric/FcNetworkPolicies
- **Result:** Eliminated 15+ false positive gap reports

### 2. JSON Extraction Depth Handling
- **Issue:** Capturing nested object properties as top-level attributes
- **Fix:** Implemented depth-aware parsing (top-level keys only)
- **Result:** Cleaner, more accurate attribute comparison

### 3. Reference Object Filtering
- **Issue:** Including Profiles, Groups, Providers in compliance gaps
- **Fix:** Enhanced exclusion system with policy-specific filters
- **Result:** 100% accurate gap reporting for actionable attributes

---

## 🚀 Deployment Notes

### For Lab Environment
- Extract release archive to test environment
- Update configuration files with new VLAN attributes if using those settings
- Test switch_control policy with new platform-specific attributes
- Verify BIOS policy template works with existing configurations

### Configuration Updates
If using VLAN policies with the new attributes:
```yaml
vlan_config:
  - name: "my-vlan"
    vlan_id: 100
    auto_allow_on_inter_switch_ports: true       # NEW
    auto_allow_on_secure_router_roles: true      # NEW
```

If using switch_control policies:
```yaml
switch_control_config:
  - name: "domain-switch"
    target_platform: "UCS Domain"
    enable_lldp: false                            # NEW
    enable_stp: false                             # NEW
    disabled_mac_address_learning_vlans: "100,101"  # NEW (End Host mode only)
```

---

## 📚 Documentation Updates

### New Files
- `docs/POLICY_TEMPLATE_PATTERN.md` - Comprehensive template enhancement guide

### Updated Files
- `schemas/source/intersight.json` - Platform-specific descriptions
- `schemas/source/intersight/policies.json` - New property definitions with platform applicability
- `roles/intersight_ucs_provision/library/src/intersight/attribute_exclusions.yaml` - Enhanced exclusion rules

---

## 🧪 Testing

All changes have been validated:

✅ **Template Syntax**
- VLAN template renders correctly
- Switch control template renders for both UCS Domain and Unified Edge
- JSON output validates against schema

✅ **Schema Validation**
- intersight.json validates as JSON
- intersight/policies.json validates schema definitions
- Property definitions complete for new attributes

✅ **API Comparison**
- API endpoint fixes verified with live Intersight
- Attribute extraction working correctly
- Compliance reporting accurate (98.1%)

✅ **BIOS Policy Verification**
- 473/473 BIOS settings present ✓
- 100% coverage confirmed
- All categories covered (CPU, memory, security, power, thermal)

---

## 🔄 Included Changes from v0.1.13 & v0.1.14

This release includes:
- v0.1.13: PCIe Connectivity Policy firmware validation
- v0.1.14: Feature 1 v2 (Live Intersight SaaS API template difference checker)
- v0.1.15: Template enhancements + bug fixes + schema completions

---

## 🗺️ Roadmap: Feature 2

**Next Feature (Planned for later):**
- Auto-strip unsupported attributes for PVA/CVA appliances
- Detect environment (SaaS vs PVA vs CVA) capabilities
- Automatically remove unsupported attributes before deployment
- Notify users of stripped attributes

---

## 🤝 Contribution Notes

For future template enhancements:
1. Read `docs/POLICY_TEMPLATE_PATTERN.md` for detailed pattern guidance
2. Update all three layers: template, intersight.json, intersight/policies.json
3. Consider platform applicability (UCS Domain vs Unified Edge)
4. Use provided checklist for validation before submitting PRs

---

## 📞 Support

For issues or questions:
1. Check `docs/POLICY_TEMPLATE_PATTERN.md` for common patterns
2. Review recent template examples (switch_control, VLAN)
3. See `template_differences.md` report for detailed policy gaps
4. Check `attribute_exclusions.yaml` for attribute filter rules

---

## Version Information

- **Tag:** v0.1.15
- **Commit:** b8f8edc
- **Branch:** main
- **Release Type:** Feature + Maintenance
- **Breaking Changes:** None
- **Migration Required:** No

---

## Checksums

**Key Files Changed:**
- vlan.vlans.json.j2: +2 attributes
- switch_control.json.j2: +3 attributes (with platform conditionals)
- intersight/policies.json: +~50 property definitions
- intersight.json: +~20 description updates
- attribute_exclusions.yaml: +~15 exclusion rules
- check_template_differences.py: 2 critical bug fixes

---

**Release Notes Generated:** 2026-11-14  
**Ready for Production Deployment**

