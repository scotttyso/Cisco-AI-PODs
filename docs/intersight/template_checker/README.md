# Template Checker Documentation

This folder contains documentation and guides for the Intersight template compliance checking tools.

## Quick Navigation

### For Users (Getting Started)
- **[Template Checker Quick Start](./TEMPLATE_CHECKER_QUICK_START.md)** - Start here if you want to run the template difference checker
  - Basic usage examples
  - Command options and common tasks
  - Understanding the reports
  - Troubleshooting guide

### For Developers (Deep Dives)
- **[Template Difference Checker](./TEMPLATE_DIFFERENCE_CHECKER.md)** - Complete technical documentation
  - Architecture and design
  - Implementation details
  - Extension points for future features
  - 37 comprehensive unit tests

- **[Template Objects Checker Guide](./TEMPLATE_OBJECTS_CHECKER_GUIDE.md)** - Comprehensive guide to analyzing template objects
  - Policy and profile analysis methodology
  - Attribute extraction and comparison
  - Report generation and interpretation

### For Implementation Planning
- **[BIOS/Adapter Templates Compliance](./BIOS_ADAPTER_TEMPLATES_COMPLIANCE.md)** - Current state of BIOS and Adapter policy templates
  - Supported attributes by template type
  - Known gaps and compliance status
  - Attribute reference by policy

- **[Template Objects Implementation Plan](./TEMPLATE_OBJECTS_IMPLEMENTATION_PLAN.md)** - Roadmap for template enhancements
  - Missing attributes by category
  - Prioritized implementation tasks
  - Integration with Feature 2 (Dynamic Payload Adapter)

### Quick Reference
- **[BIOS/Adapter Compliance Quick Reference](./BIOS_ADAPTER_COMPLIANCE_QUICK_REFERENCE.txt)** - Quick lookup of template statistics
  - Attribute counts by template type
  - Coverage percentages
  - At-a-glance status

## Tools Available

### Template Difference Checker
Compares your Jinja2 templates against Intersight API schemas to identify missing or mismatched attributes.

**Location**: `roles/intersight_ucs_provision/library/src/intersight/check_template_differences.py`

**Quick start**:
```bash
cd /path/to/Cisco-AI-PODs
python roles/intersight_ucs_provision/library/src/intersight/check_template_differences.py -c all -f all
```

**Tests**:
```bash
cd roles/intersight_ucs_provision
python -m pytest tests/test_check_template_differences.py -v
```

### BIOS/Adapter Compliance Checker
Checks deployed BIOS and Ethernet/FC Adapter policy templates in Intersight against the schema.

**Location**: `roles/intersight_ucs_provision/library/src/intersight/check_bios_adapter_templates.py`

**Setup**: Requires Intersight API credentials in `~/.config/cisco-ai-pods/vault.yaml`

## Related Features

- **Feature 1**: Template compliance checking (implemented in v0.1.14-0.1.15)
- **Feature 2**: Dynamic Payload Adapter - Automatically filters unsupported attributes by platform (PVA/CVA/SaaS)

## Generated Reports

The checker tools generate reports in multiple formats. These reports are generated locally and **not tracked in git**:
- `.json` - Machine-parseable structured data
- `.csv` - Spreadsheet format (Excel/Sheets compatible)
- `.md` - Human-readable markdown
- `.log` - Detailed execution logs

See the Quick Start guide for instructions on interpreting these reports.

## Support

For issues or questions:
1. Review the [Quick Start Guide](./TEMPLATE_CHECKER_QUICK_START.md#troubleshooting)
2. Check the test cases in `roles/intersight_ucs_provision/tests/test_check_template_differences.py`
3. Enable verbose mode (`-v` flag) for detailed debugging output

---

**Last Updated**: November 16, 2024

**Version**: 0.1.15
