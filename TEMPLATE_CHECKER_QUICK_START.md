# Template Difference Checker - Quick Start Guide

## What Is It?

A maintenance tool that compares your Jinja2 templates against Intersight API schemas to find missing or mismatched attributes.

## Quick Start

### Installation
No installation needed! The tool is part of the repository.

### Basic Usage
```bash
cd /path/to/Cisco-AI-PODs
python roles/intersight_ucs_provision/library/src/intersight/check_template_differences.py
```

### Common Tasks

#### 1. Check All Templates (All Reports)
```bash
python roles/intersight_ucs_provision/library/src/intersight/check_template_differences.py \
  -c all \
  -o my_report \
  -f all
```
**Output**: 
- `my_report.json` - Structured data
- `my_report.csv` - Spreadsheet format
- `my_report.md` - Human-readable report
- `template_diff_*.log` - Execution log

#### 2. Check Specific Category (Policies)
```bash
python roles/intersight_ucs_provision/library/src/intersight/check_template_differences.py \
  -c policies \
  -o policy_check \
  -f markdown
```

#### 3. Check Pools Only (CSV for Spreadsheet)
```bash
python roles/intersight_ucs_provision/library/src/intersight/check_template_differences.py \
  -c pools \
  -o pool_check \
  -f csv
```

#### 4. Check with Detailed Attribute Lists
```bash
python roles/intersight_ucs_provision/library/src/intersight/check_template_differences.py \
  -c profiles \
  -o profile_analysis \
  -f markdown \
  -d
```

#### 5. Verbose Mode for Troubleshooting
```bash
python roles/intersight_ucs_provision/library/src/intersight/check_template_differences.py \
  -c all \
  -o debug_report \
  -f json \
  -v
```

## Command Options

| Option | Values | Default | Purpose |
|--------|--------|---------|---------|
| `-c, --category` | policies, pools, profiles, templates, system, all | all | Which templates to analyze |
| `-o, --output` | filename (no extension) | template_differences | Report filename prefix |
| `-f, --formats` | json, csv, markdown, all | all | Report formats to generate |
| `-d, --details` | (flag) | off | Include detailed attributes in markdown |
| `-v, --verbose` | (flag) | off | Enable detailed logging |
| `-h, --help` | (flag) | - | Show help message |

## Understanding the Reports

### Example Output
```
================================================================================
TEMPLATE DIFFERENCE ANALYSIS SUMMARY
================================================================================

Total Templates Analyzed: 104
Templates with Attribute Gaps: 3

Top Issues (sorted by missing API attributes):

  policies/firmware
    - 2 attributes not in current API

...
```

### Report Columns (CSV/JSON)
- **Template**: Policy name (e.g., "policies/bios")
- **Template Attributes**: Count of attributes in your template
- **API Attributes**: Count of attributes in Intersight API
- **Missing in API**: Attributes you use that API doesn't support
- **Missing in Template**: API attributes you haven't templated yet
- **Match Ratio**: Percentage of attribute alignment (higher is better)

### Match Ratio Interpretation
- **100%**: Perfect alignment - no gaps
- **90-99%**: Minor gaps - likely OK
- **70-89%**: Moderate gaps - review recommended
- **<70%**: Significant gaps - investigate

## Troubleshooting

### No output generated
```bash
# Check if templates directory exists
ls -la roles/intersight_ucs_provision/templates/intersight/policies/
```

### "Failed to parse template" warnings
- Normal for some templates with non-standard Jinja2 syntax
- Tool continues analysis despite warnings
- Check specific template if concerned

### Empty results
- Ensure category name is correct
- Verify `.j2` files exist in category
- Use `-v` (verbose) flag to see what's being analyzed

### Reports not readable
- JSON: Open with text editor or JSON viewer
- CSV: Import into Excel or Google Sheets
- Markdown: View in text editor or markdown viewer

## Working with Results

### For Analysis
1. Open `report.csv` in Excel
2. Sort by "Missing in API (Count)" column (descending)
3. Review templates with highest missing counts

### For Documentation
1. Open `report.md` in text editor
2. Look for templates with match ratio <100%
3. Use detailed findings to plan updates

### For Integration
1. Parse `report.json` programmatically
2. Filter results by category or match ratio
3. Integrate into CI/CD pipeline

## Running Tests

Verify the tool is working correctly:
```bash
cd roles/intersight_ucs_provision
python -m pytest tests/test_check_template_differences.py -v
```

Expected output:
```
============================== 37 passed in 0.11s ==============================
```

## What Gets Analyzed

### Template Categories
| Category | Count | Examples |
|----------|-------|----------|
| policies | 78 | bios, ethernet_adapter, firmware, etc. |
| pools | 9 | ip, mac, uuid, iqn, etc. |
| profiles | 4 | server, domain, chassis, etc. |
| templates | 8 | vnic, vhba, domain, etc. |
| system | 5 | organizations, iam, resource groups |
| **Total** | **104** | - |

### What's Compared
- JSON attribute names in templates (e.g., "Name", "Description", "ObjectType")
- Attributes supported by Intersight APIs
- Identifies gaps in both directions

### What's NOT Compared
- Attribute data types
- Nested object structures
- Validation rules
- Template variable names (only attributes count)

## Next Steps

### After First Run
1. Review summary output
2. Check any templates with gaps
3. Decide if templates need updating or if API has new features

### For Feature 2 (Dynamic Payload Adapter)
- This tool identifies what attributes exist
- Feature 2 will use this info to automatically filter attributes
- Coming in next release when test environment is ready

### Regular Maintenance
- Run after major Intersight version upgrades
- Run before deploying new configurations
- Track reports to spot API changes over time

## More Information

For detailed documentation, see: `TEMPLATE_DIFFERENCE_CHECKER.md`

For release notes, see: `RELEASE_v0.1.14_NOTES.md`

For source code and tests, see:
- `roles/intersight_ucs_provision/library/src/intersight/check_template_differences.py`
- `roles/intersight_ucs_provision/tests/test_check_template_differences.py`

---

**Questions?** Review the full documentation or check the test files for usage examples.
