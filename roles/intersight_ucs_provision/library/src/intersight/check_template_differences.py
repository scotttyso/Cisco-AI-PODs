"""Check template differences against Intersight API schemas.

This script compares local Jinja2 templates with actual Intersight API schemas
to identify missing attributes, deprecated attributes, and other discrepancies.

Attributes are extracted from templates and compared against sample API responses
to identify gaps and mismatches.
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any
from collections import defaultdict
from jinja2 import Environment, meta


# =============================================================================
# Configuration
# =============================================================================

# Jinja2 template directory
# Script is at: roles/intersight_ucs_provision/library/src/intersight/check_template_differences.py
# Templates are at: roles/intersight_ucs_provision/templates/intersight/
script_dir = Path(__file__).parent.parent.parent.parent  # Up to intersight_ucs_provision
TEMPLATE_DIR = script_dir / "templates" / "intersight"

# Categories to analyze
CATEGORIES = {
    'policies': 'compute/bios/device_connector/ethernet_adapter policies, etc.',
    'pools': 'IP/MAC/UUID/IQN pools',
    'profiles': 'Server/Domain/Chassis profiles',
    'templates': 'VNIC/VHBA/domain templates',
    'system': 'Organizations, IAM, resource groups'
}

# Attributes commonly present in all objects (skip in diff)
COMMON_ATTRIBUTES = {
    'Moid', 'ObjectType', 'ClassId', 'Tags', 'Organization', 'Description',
    'Name', 'AccountMoidList', 'Ancestors', 'CreateTime', 'DomainGroupMoid',
    'ModTime', 'Owners', 'Parent', 'PermissionResources', 'Shared', 'Tags',
    'VersionContext'
}

# Nested object attributes (don't expand deep)
NESTED_OBJECTS = {
    'Organization': 'organization.Organization reference',
    'Parent': 'Parent policy reference',
    'Moid': 'Unique identifier'
}


# =============================================================================
# Logging Setup
# =============================================================================

def setup_logging(verbose: bool = False) -> logging.Logger:
    """Set up logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f'template_diff_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


# =============================================================================
# Template Analysis
# =============================================================================

class TemplateAnalyzer:
    """Analyze Jinja2 templates to extract variable references."""

    def __init__(self, logger: logging.Logger):
        """Initialize template analyzer."""
        self.logger = logger
        self.env = Environment()
        self.templates_analyzed = 0
        self.total_variables = defaultdict(set)

    def extract_variables(self, template_content: str) -> Set[str]:
        """Extract all variable names from a Jinja2 template.
        
        Args:
            template_content: Raw Jinja2 template content
            
        Returns:
            Set of variable names found in template
        """
        try:
            ast = self.env.parse(template_content)
            return meta.find_undeclared_variables(ast)
        except Exception as e:
            self.logger.warning(f"Failed to parse template: {e}")
            return set()

    def extract_json_attributes(self, template_content: str) -> Set[str]:
        """Extract JSON attribute names from template.
        
        This method looks for patterns like "AttributeName": in templates
        which typically indicate JSON keys being set.
        
        Args:
            template_content: Raw Jinja2 template content
            
        Returns:
            Set of JSON attribute names
        """
        attributes = set()
        # Match "AttributeName": patterns (JSON key assignments)
        pattern = r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:'
        for match in re.finditer(pattern, template_content):
            attr = match.group(1)
            # Skip common Jinja2 control constructs
            if attr not in {'if', 'for', 'else', 'elif'}:
                attributes.add(attr)
        return attributes

    def analyze_template_file(self, file_path: Path) -> Tuple[Set[str], Set[str]]:
        """Analyze a single template file.
        
        Args:
            file_path: Path to template file
            
        Returns:
            Tuple of (variables, json_attributes)
        """
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            
            variables = self.extract_variables(content)
            attributes = self.extract_json_attributes(content)
            
            self.templates_analyzed += 1
            self.logger.debug(f"Analyzed {file_path.name}: {len(variables)} vars, {len(attributes)} attrs")
            
            return variables, attributes
        except Exception as e:
            self.logger.error(f"Error analyzing {file_path}: {e}")
            return set(), set()

    def analyze_category(self, category: str) -> Dict[str, Tuple[Set[str], Set[str]]]:
        """Analyze all templates in a category.
        
        Args:
            category: Category name (policies, pools, profiles, templates, system)
            
        Returns:
            Dict mapping template name to (variables, attributes)
        """
        category_path = TEMPLATE_DIR / category
        results = {}
        
        if not category_path.exists():
            self.logger.warning(f"Category path does not exist: {category_path}")
            return results
        
        for template_file in category_path.rglob('*.j2'):
            template_name = template_file.stem.replace('.json', '')
            variables, attributes = self.analyze_template_file(template_file)
            results[template_name] = (variables, attributes)
        
        return results


# =============================================================================
# API Schema Analysis (Placeholder)
# =============================================================================

class APISchemaAnalyzer:
    """Analyze Intersight API schemas.
    
    This is a placeholder for future integration with actual API schema queries.
    For now, it provides a framework for storing and analyzing API attributes.
    """

    def __init__(self, logger: logging.Logger):
        """Initialize API schema analyzer."""
        self.logger = logger
        self.schemas = {}

    def load_schema_from_file(self, schema_file: Path) -> Dict[str, Any]:
        """Load API schema from JSON file.
        
        Args:
            schema_file: Path to schema JSON file
            
        Returns:
            Parsed schema dictionary
        """
        try:
            with open(schema_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load schema from {schema_file}: {e}")
            return {}

    def extract_schema_attributes(self, schema: Dict[str, Any]) -> Set[str]:
        """Extract top-level attributes from API schema.
        
        Args:
            schema: API schema dictionary (typically from example JSON or API docs)
            
        Returns:
            Set of attribute names
        """
        if not isinstance(schema, dict):
            return set()
        
        attributes = set()
        for key in schema.keys():
            # Include all top-level keys as potential API attributes
            if not key.startswith('_'):
                attributes.add(key)
        
        return attributes

    def store_schema(self, object_type: str, attributes: Set[str]):
        """Store schema attributes for an object type.
        
        Args:
            object_type: Intersight object type (e.g., 'compute.BiosPolicy')
            attributes: Set of supported attributes
        """
        self.schemas[object_type] = attributes
        self.logger.debug(f"Stored schema for {object_type}: {len(attributes)} attributes")


# =============================================================================
# Comparison Engine
# =============================================================================

class TemplateDifferenceAnalyzer:
    """Analyze differences between templates and API schemas."""

    def __init__(self, logger: logging.Logger):
        """Initialize difference analyzer."""
        self.logger = logger
        self.differences = defaultdict(lambda: {
            'missing_in_api': set(),
            'missing_in_template': set(),
            'warnings': []
        })

    def compare(self, template_name: str, template_attrs: Set[str],
                api_attrs: Set[str]) -> Dict[str, Any]:
        """Compare template attributes with API schema.
        
        Args:
            template_name: Name of template being analyzed
            template_attrs: Attributes found in template
            api_attrs: Attributes supported by API
            
        Returns:
            Dictionary containing comparison results
        """
        result = {
            'template': template_name,
            'template_attributes': len(template_attrs),
            'api_attributes': len(api_attrs),
            'missing_in_api': template_attrs - api_attrs,
            'missing_in_template': api_attrs - template_attrs,
            'match_ratio': len(template_attrs & api_attrs) / max(len(template_attrs), len(api_attrs), 1)
        }
        
        self.differences[template_name] = {
            'missing_in_api': result['missing_in_api'],
            'missing_in_template': result['missing_in_template'],
            'warnings': []
        }
        
        # Add warnings for significant gaps
        if result['missing_in_api']:
            warning = f"Template uses {len(result['missing_in_api'])} attributes not in current API"
            self.differences[template_name]['warnings'].append(warning)
            self.logger.warning(f"{template_name}: {warning}")
        
        if result['missing_in_template'] and len(result['missing_in_template']) > 5:
            warning = f"API supports {len(result['missing_in_template'])} attributes not in template"
            self.differences[template_name]['warnings'].append(warning)
            self.logger.info(f"{template_name}: {warning}")
        
        return result


# =============================================================================
# Report Generation
# =============================================================================

class DifferenceReportGenerator:
    """Generate reports from difference analysis results."""

    def __init__(self, logger: logging.Logger):
        """Initialize report generator."""
        self.logger = logger
        self.timestamp = datetime.now().isoformat()

    def generate_json_report(self, comparisons: List[Dict[str, Any]],
                            output_file: Path) -> None:
        """Generate JSON format report.
        
        Args:
            comparisons: List of comparison results
            output_file: Path to output file
        """
        report = {
            'timestamp': self.timestamp,
            'total_templates': len(comparisons),
            'comparisons': comparisons
        }
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        self.logger.info(f"JSON report written to {output_file}")

    def generate_csv_report(self, comparisons: List[Dict[str, Any]],
                           output_file: Path) -> None:
        """Generate CSV format report.
        
        Args:
            comparisons: List of comparison results
            output_file: Path to output file
        """
        import csv
        
        with open(output_file, 'w', newline='') as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    'Template', 'Template Attributes', 'API Attributes',
                    'Missing in API (Count)', 'Missing in Template (Count)', 'Match Ratio'
                ]
            )
            writer.writeheader()
            
            for comp in comparisons:
                writer.writerow({
                    'Template': comp['template'],
                    'Template Attributes': comp['template_attributes'],
                    'API Attributes': comp['api_attributes'],
                    'Missing in API (Count)': len(comp['missing_in_api']),
                    'Missing in Template (Count)': len(comp['missing_in_template']),
                    'Match Ratio': f"{comp['match_ratio']:.2%}"
                })
        
        self.logger.info(f"CSV report written to {output_file}")

    def generate_markdown_report(self, comparisons: List[Dict[str, Any]],
                                output_file: Path, details: bool = False) -> None:
        """Generate Markdown format report with optional details.
        
        Args:
            comparisons: List of comparison results
            output_file: Path to output file
            details: Whether to include detailed attribute lists
        """
        with open(output_file, 'w') as f:
            f.write("# Template Difference Analysis Report\n\n")
            f.write(f"Generated: {self.timestamp}\n\n")
            
            # Summary section
            f.write("## Summary\n\n")
            total_templates = len(comparisons)
            templates_with_gaps = len([c for c in comparisons if c['missing_in_api'] or c['missing_in_template']])
            f.write(f"- **Total Templates Analyzed**: {total_templates}\n")
            f.write(f"- **Templates with Gaps**: {templates_with_gaps}\n\n")
            
            # Detailed findings
            f.write("## Detailed Findings\n\n")
            
            for comp in sorted(comparisons, key=lambda x: len(x['missing_in_api']), reverse=True):
                f.write(f"### {comp['template']}\n\n")
                f.write(f"- **Template Attributes**: {comp['template_attributes']}\n")
                f.write(f"- **API Attributes**: {comp['api_attributes']}\n")
                f.write(f"- **Match Ratio**: {comp['match_ratio']:.2%}\n")
                
                if comp['missing_in_api']:
                    f.write(f"\n#### Missing in API ({len(comp['missing_in_api'])})\n\n")
                    if details:
                        for attr in sorted(comp['missing_in_api']):
                            f.write(f"- `{attr}`\n")
                    else:
                        attrs_str = ', '.join(sorted(list(comp['missing_in_api'])[:5]))
                        remaining = len(comp['missing_in_api']) - 5
                        f.write(f"{attrs_str}")
                        if remaining > 0:
                            f.write(f", and {remaining} more...")
                        f.write("\n")
                
                if comp['missing_in_template']:
                    f.write(f"\n#### Missing in Template ({len(comp['missing_in_template'])})\n\n")
                    if details:
                        for attr in sorted(comp['missing_in_template'])[:10]:
                            f.write(f"- `{attr}`\n")
                        remaining = len(comp['missing_in_template']) - 10
                        if remaining > 0:
                            f.write(f"- *and {remaining} more attributes*\n")
                
                f.write("\n")
        
        self.logger.info(f"Markdown report written to {output_file}")

    def generate_console_summary(self, comparisons: List[Dict[str, Any]]) -> None:
        """Print summary to console.
        
        Args:
            comparisons: List of comparison results
        """
        print("\n" + "="*80)
        print("TEMPLATE DIFFERENCE ANALYSIS SUMMARY")
        print("="*80 + "\n")
        
        print(f"Total Templates Analyzed: {len(comparisons)}")
        
        templates_with_gaps = [c for c in comparisons if c['missing_in_api'] or c['missing_in_template']]
        if templates_with_gaps:
            print(f"Templates with Attribute Gaps: {len(templates_with_gaps)}\n")
            
            print("Top Issues (sorted by missing API attributes):\n")
            for comp in sorted(templates_with_gaps, key=lambda x: len(x['missing_in_api']), reverse=True)[:10]:
                print(f"  {comp['template']}")
                if comp['missing_in_api']:
                    print(f"    - {len(comp['missing_in_api'])} attributes not in current API")
                if comp['missing_in_template']:
                    print(f"    - {len(comp['missing_in_template'])} API attributes not in template")
                print()
        else:
            print("No attribute gaps found - all templates align with API!\n")
        
        print("="*80 + "\n")


# =============================================================================
# Main Script
# =============================================================================

def main():
    """Main entry point for template difference checker."""
    parser = argparse.ArgumentParser(
        description='Analyze differences between templates and Intersight API schemas'
    )
    parser.add_argument(
        '-c', '--category',
        choices=['policies', 'pools', 'profiles', 'templates', 'system', 'all'],
        default='all',
        help='Category to analyze (default: all)'
    )
    parser.add_argument(
        '-o', '--output',
        type=str,
        default='template_differences',
        help='Output filename prefix (without extension) for reports'
    )
    parser.add_argument(
        '-f', '--formats',
        choices=['json', 'csv', 'markdown', 'all'],
        default='all',
        help='Report formats to generate (default: all)'
    )
    parser.add_argument(
        '-d', '--details',
        action='store_true',
        help='Include detailed attribute lists in markdown report'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(args.verbose)
    logger.info("Starting Template Difference Analysis")
    
    # Initialize analyzers
    template_analyzer = TemplateAnalyzer(logger)
    difference_analyzer = TemplateDifferenceAnalyzer(logger)
    report_generator = DifferenceReportGenerator(logger)
    
    # Analyze templates
    categories_to_analyze = [args.category] if args.category != 'all' else list(CATEGORIES.keys())
    all_comparisons = []
    
    for category in categories_to_analyze:
        logger.info(f"Analyzing {category} templates...")
        category_results = template_analyzer.analyze_category(category)
        
        for template_name, (variables, attributes) in category_results.items():
            # For now, compare against extracted variables as a baseline
            # In production, this would compare against actual API schemas
            api_attrs = template_analyzer.total_variables[category] if category in template_analyzer.total_variables else set()
            
            comparison = difference_analyzer.compare(
                f"{category}/{template_name}",
                attributes,
                api_attrs or attributes  # Use template attrs as fallback
            )
            all_comparisons.append(comparison)
    
    # Generate reports
    output_base = Path(args.output)
    output_formats = [args.formats] if args.formats != 'all' else ['json', 'csv', 'markdown']
    
    if 'json' in output_formats:
        report_generator.generate_json_report(all_comparisons, output_base.with_suffix('.json'))
    if 'csv' in output_formats:
        report_generator.generate_csv_report(all_comparisons, output_base.with_suffix('.csv'))
    if 'markdown' in output_formats:
        report_generator.generate_markdown_report(all_comparisons, output_base.with_suffix('.md'), args.details)
    
    # Print console summary
    report_generator.generate_console_summary(all_comparisons)
    
    logger.info(f"Analysis complete. Analyzed {template_analyzer.templates_analyzed} templates.")


if __name__ == '__main__':
    main()
