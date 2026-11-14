"""Unit tests for template difference checker script.

Tests cover:
- Template analysis and variable extraction
- JSON attribute extraction from templates
- API schema analysis
- Comparison logic
- Report generation in multiple formats
"""

import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

# Add library path for imports
lib_path = Path(__file__).parent.parent / 'library' / 'src'
sys.path.insert(0, str(lib_path))

# Import the module directly from file to avoid package initialization
import importlib.util
spec = importlib.util.spec_from_file_location(
    "check_template_differences",
    lib_path / 'intersight' / 'check_template_differences.py'
)
check_template_differences = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_template_differences)

TemplateAnalyzer = check_template_differences.TemplateAnalyzer
APISchemaAnalyzer = check_template_differences.APISchemaAnalyzer
TemplateDifferenceAnalyzer = check_template_differences.TemplateDifferenceAnalyzer
DifferenceReportGenerator = check_template_differences.DifferenceReportGenerator
COMMON_ATTRIBUTES = check_template_differences.COMMON_ATTRIBUTES


class TestTemplateAnalyzer(unittest.TestCase):
    """Tests for TemplateAnalyzer class."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = logging.getLogger('test')
        self.analyzer = TemplateAnalyzer(self.logger)

    def test_extract_variables_simple(self):
        """Test extraction of simple variables."""
        template = "Hello {{ name }}!"
        variables = self.analyzer.extract_variables(template)
        self.assertIn('name', variables)

    def test_extract_variables_multiple(self):
        """Test extraction of multiple variables."""
        template = """
        {
            "Name": "{{ item.name }}",
            "Description": "{{ item.description }}",
            "Organization": "{{ organization }}"
        }
        """
        variables = self.analyzer.extract_variables(template)
        self.assertIn('item', variables)
        self.assertIn('organization', variables)

    def test_extract_variables_with_filters(self):
        """Test extraction of variables with Jinja2 filters."""
        template = "{{ item.name | default('Unknown') }}"
        variables = self.analyzer.extract_variables(template)
        self.assertIn('item', variables)

    def test_extract_variables_with_loops(self):
        """Test extraction of variables in loop contexts."""
        template = """
        {% for tag in item.tags %}
            "Key": "{{ tag.key }}"
        {% endfor %}
        """
        variables = self.analyzer.extract_variables(template)
        self.assertIn('item', variables)

    def test_extract_variables_empty_template(self):
        """Test extraction from empty/static template."""
        template = "Hello world!"
        variables = self.analyzer.extract_variables(template)
        self.assertEqual(len(variables), 0)

    def test_extract_json_attributes_simple(self):
        """Test extraction of JSON attributes."""
        template = '{"Name": "test", "Description": "desc"}'
        attributes = self.analyzer.extract_json_attributes(template)
        self.assertIn('Name', attributes)
        self.assertIn('Description', attributes)

    def test_extract_json_attributes_with_variables(self):
        """Test extraction of JSON attributes mixed with variables."""
        template = """
        {
            "Name": {{ item.name | tojson }},
            "Description": {{ item.description | tojson }},
            "ObjectType": "compute.BiosPolicy"
        }
        """
        attributes = self.analyzer.extract_json_attributes(template)
        self.assertIn('Name', attributes)
        self.assertIn('Description', attributes)
        self.assertIn('ObjectType', attributes)

    def test_extract_json_attributes_nested(self):
        """Test extraction of nested JSON attributes."""
        template = """
        {
            "Organization": {
                "Moid": "{{ org_moid }}",
                "ObjectType": "organization.Organization"
            },
            "Tags": []
        }
        """
        attributes = self.analyzer.extract_json_attributes(template)
        self.assertIn('Organization', attributes)
        self.assertIn('Moid', attributes)
        self.assertIn('ObjectType', attributes)
        self.assertIn('Tags', attributes)

    def test_extract_json_attributes_controls_ignored(self):
        """Test that Jinja2 control keywords are not extracted as attributes."""
        template = """
        {% if condition %}
            "AttributeA": "value"
        {% else %}
            "AttributeB": "value"
        {% endif %}
        """
        attributes = self.analyzer.extract_json_attributes(template)
        self.assertNotIn('if', attributes)
        self.assertNotIn('else', attributes)
        self.assertNotIn('elif', attributes)
        self.assertIn('AttributeA', attributes)
        self.assertIn('AttributeB', attributes)

    def test_analyze_template_file_valid(self):
        """Test analysis of a valid template file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.j2', delete=False) as f:
            f.write('{"Name": "{{ item.name }}", "ObjectType": "compute.BiosPolicy"}')
            f.flush()
            
            variables, attributes = self.analyzer.analyze_template_file(Path(f.name))
            
            self.assertIn('item', variables)
            self.assertIn('Name', attributes)
            self.assertIn('ObjectType', attributes)
            
            Path(f.name).unlink()

    def test_analyze_template_file_not_found(self):
        """Test analysis of non-existent file."""
        variables, attributes = self.analyzer.analyze_template_file(
            Path('/nonexistent/template.j2')
        )
        self.assertEqual(len(variables), 0)
        self.assertEqual(len(attributes), 0)


class TestAPISchemaAnalyzer(unittest.TestCase):
    """Tests for APISchemaAnalyzer class."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = logging.getLogger('test')
        self.analyzer = APISchemaAnalyzer(self.logger)

    def test_extract_schema_attributes_simple(self):
        """Test extraction of attributes from simple schema."""
        schema = {
            'Name': 'test',
            'Description': 'Test description',
            'Enabled': True
        }
        attributes = self.analyzer.extract_schema_attributes(schema)
        self.assertEqual(attributes, {'Name', 'Description', 'Enabled'})

    def test_extract_schema_attributes_nested(self):
        """Test extraction from nested schema (only top-level)."""
        schema = {
            'Name': 'test',
            'Organization': {
                'Moid': '123',
                'Name': 'org'
            },
            'Tags': [{'Key': 'env', 'Value': 'prod'}]
        }
        attributes = self.analyzer.extract_schema_attributes(schema)
        self.assertIn('Name', attributes)
        self.assertIn('Organization', attributes)
        self.assertIn('Tags', attributes)
        # Should not include nested keys
        self.assertNotIn('Moid', attributes)

    def test_extract_schema_attributes_ignores_private(self):
        """Test that private attributes (starting with _) are ignored."""
        schema = {
            'Name': 'test',
            '_internal': 'value',
            '__private': 'value'
        }
        attributes = self.analyzer.extract_schema_attributes(schema)
        self.assertIn('Name', attributes)
        self.assertNotIn('_internal', attributes)
        self.assertNotIn('__private', attributes)

    def test_extract_schema_attributes_empty(self):
        """Test extraction from empty schema."""
        attributes = self.analyzer.extract_schema_attributes({})
        self.assertEqual(attributes, set())

    def test_extract_schema_attributes_non_dict(self):
        """Test extraction from non-dict input."""
        attributes = self.analyzer.extract_schema_attributes("not a dict")
        self.assertEqual(attributes, set())

    def test_store_schema(self):
        """Test storing schema for object type."""
        attributes = {'Name', 'Description', 'Enabled'}
        self.analyzer.store_schema('compute.BiosPolicy', attributes)
        
        self.assertIn('compute.BiosPolicy', self.analyzer.schemas)
        self.assertEqual(self.analyzer.schemas['compute.BiosPolicy'], attributes)

    def test_load_schema_from_file_valid(self):
        """Test loading schema from valid JSON file."""
        schema_data = {'Name': 'test', 'Enabled': True}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(schema_data, f)
            f.flush()
            
            loaded = self.analyzer.load_schema_from_file(Path(f.name))
            
            self.assertEqual(loaded, schema_data)
            Path(f.name).unlink()

    def test_load_schema_from_file_not_found(self):
        """Test loading from non-existent file."""
        loaded = self.analyzer.load_schema_from_file(Path('/nonexistent.json'))
        self.assertEqual(loaded, {})

    def test_load_schema_from_file_invalid_json(self):
        """Test loading from file with invalid JSON."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{ invalid json")
            f.flush()
            
            loaded = self.analyzer.load_schema_from_file(Path(f.name))
            
            self.assertEqual(loaded, {})
            Path(f.name).unlink()


class TestTemplateDifferenceAnalyzer(unittest.TestCase):
    """Tests for TemplateDifferenceAnalyzer class."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = logging.getLogger('test')
        self.analyzer = TemplateDifferenceAnalyzer(self.logger)

    def test_compare_perfect_match(self):
        """Test comparison with perfect attribute match."""
        template_attrs = {'Name', 'Description', 'Enabled', 'ObjectType'}
        api_attrs = {'Name', 'Description', 'Enabled', 'ObjectType'}
        
        result = self.analyzer.compare('test_template', template_attrs, api_attrs)
        
        self.assertEqual(len(result['missing_in_api']), 0)
        self.assertEqual(len(result['missing_in_template']), 0)
        self.assertEqual(result['match_ratio'], 1.0)

    def test_compare_missing_in_api(self):
        """Test comparison with attributes missing in API."""
        template_attrs = {'Name', 'Description', 'NewAttribute', 'ObjectType'}
        api_attrs = {'Name', 'Description', 'ObjectType'}
        
        result = self.analyzer.compare('test_template', template_attrs, api_attrs)
        
        self.assertIn('NewAttribute', result['missing_in_api'])
        self.assertEqual(len(result['missing_in_api']), 1)
        self.assertEqual(len(result['missing_in_template']), 0)

    def test_compare_missing_in_template(self):
        """Test comparison with attributes missing in template."""
        template_attrs = {'Name', 'Description'}
        api_attrs = {'Name', 'Description', 'Enabled', 'ObjectType', 'Organization'}
        
        result = self.analyzer.compare('test_template', template_attrs, api_attrs)
        
        self.assertEqual(len(result['missing_in_api']), 0)
        self.assertIn('Enabled', result['missing_in_template'])
        self.assertIn('ObjectType', result['missing_in_template'])

    def test_compare_bidirectional_gaps(self):
        """Test comparison with gaps in both directions."""
        template_attrs = {'Name', 'OldAttribute', 'CustomField'}
        api_attrs = {'Name', 'Enabled', 'Organization'}
        
        result = self.analyzer.compare('test_template', template_attrs, api_attrs)
        
        self.assertIn('OldAttribute', result['missing_in_api'])
        self.assertIn('CustomField', result['missing_in_api'])
        self.assertIn('Enabled', result['missing_in_template'])
        self.assertIn('Organization', result['missing_in_template'])

    def test_compare_empty_template_attributes(self):
        """Test comparison with empty template attributes."""
        template_attrs = set()
        api_attrs = {'Name', 'Description'}
        
        result = self.analyzer.compare('test_template', template_attrs, api_attrs)
        
        # match_ratio uses max() to avoid division by zero
        self.assertEqual(len(result['missing_in_api']), 0)
        self.assertEqual(len(result['missing_in_template']), 2)

    def test_compare_empty_api_attributes(self):
        """Test comparison with empty API attributes."""
        template_attrs = {'Name', 'Description'}
        api_attrs = set()
        
        result = self.analyzer.compare('test_template', template_attrs, api_attrs)
        
        self.assertEqual(len(result['missing_in_api']), 2)
        self.assertEqual(len(result['missing_in_template']), 0)

    def test_compare_stores_differences(self):
        """Test that comparisons are stored internally."""
        template_attrs = {'Name', 'OldAttr'}
        api_attrs = {'Name', 'NewAttr'}
        
        self.analyzer.compare('test_template', template_attrs, api_attrs)
        
        self.assertIn('test_template', self.analyzer.differences)
        self.assertIn('OldAttr', self.analyzer.differences['test_template']['missing_in_api'])


class TestDifferenceReportGenerator(unittest.TestCase):
    """Tests for DifferenceReportGenerator class."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = logging.getLogger('test')
        self.generator = DifferenceReportGenerator(self.logger)
        
        # Sample comparison data
        self.comparisons = [
            {
                'template': 'compute/bios',
                'template_attributes': 10,
                'api_attributes': 12,
                'missing_in_api': {'OldAttr1', 'OldAttr2'},
                'missing_in_template': {'NewAttr1'},
                'match_ratio': 0.85
            },
            {
                'template': 'networking/vlan',
                'template_attributes': 8,
                'api_attributes': 8,
                'missing_in_api': set(),
                'missing_in_template': set(),
                'match_ratio': 1.0
            }
        ]

    def test_generate_json_report(self):
        """Test JSON report generation."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = Path(f.name)
        
        try:
            self.generator.generate_json_report(self.comparisons, temp_path)
            
            with open(temp_path) as f:
                report = json.load(f)
            
            self.assertIn('timestamp', report)
            self.assertIn('total_templates', report)
            self.assertIn('comparisons', report)
            self.assertEqual(report['total_templates'], 2)
            self.assertEqual(len(report['comparisons']), 2)
        finally:
            temp_path.unlink()

    def test_generate_csv_report(self):
        """Test CSV report generation."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            temp_path = Path(f.name)
        
        try:
            self.generator.generate_csv_report(self.comparisons, temp_path)
            
            with open(temp_path) as f:
                content = f.read()
            
            self.assertIn('Template', content)
            self.assertIn('compute/bios', content)
            self.assertIn('networking/vlan', content)
            self.assertIn('Match Ratio', content)
        finally:
            temp_path.unlink()

    def test_generate_markdown_report_summary(self):
        """Test Markdown report generation (summary mode)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            temp_path = Path(f.name)
        
        try:
            self.generator.generate_markdown_report(self.comparisons, temp_path, details=False)
            
            with open(temp_path) as f:
                content = f.read()
            
            self.assertIn('# Template Difference Analysis Report', content)
            self.assertIn('## Summary', content)
            self.assertIn('## Detailed Findings', content)
            self.assertIn('compute/bios', content)
            self.assertIn('networking/vlan', content)
        finally:
            temp_path.unlink()

    def test_generate_markdown_report_detailed(self):
        """Test Markdown report generation (detailed mode)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            temp_path = Path(f.name)
        
        try:
            self.generator.generate_markdown_report(self.comparisons, temp_path, details=True)
            
            with open(temp_path) as f:
                content = f.read()
            
            self.assertIn('# Template Difference Analysis Report', content)
            self.assertIn('Missing in API', content)
            # Detailed mode should list attributes
            self.assertIn('OldAttr', content)
        finally:
            temp_path.unlink()

    def test_generate_console_summary_with_gaps(self):
        """Test console summary with attribute gaps."""
        # Should not raise an exception
        with patch('builtins.print'):
            self.generator.generate_console_summary(self.comparisons)

    def test_generate_console_summary_no_gaps(self):
        """Test console summary with no gaps."""
        comparisons = [
            {
                'template': 'test',
                'template_attributes': 5,
                'api_attributes': 5,
                'missing_in_api': set(),
                'missing_in_template': set(),
                'match_ratio': 1.0
            }
        ]
        
        # Should not raise an exception
        with patch('builtins.print'):
            self.generator.generate_console_summary(comparisons)

    def test_report_formats_created(self):
        """Test that all report formats are created."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir) / 'report'
            
            self.generator.generate_json_report(self.comparisons, base_path.with_suffix('.json'))
            self.generator.generate_csv_report(self.comparisons, base_path.with_suffix('.csv'))
            self.generator.generate_markdown_report(self.comparisons, base_path.with_suffix('.md'))
            
            self.assertTrue((base_path.with_suffix('.json')).exists())
            self.assertTrue((base_path.with_suffix('.csv')).exists())
            self.assertTrue((base_path.with_suffix('.md')).exists())


class TestIntegration(unittest.TestCase):
    """Integration tests for the complete workflow."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = logging.getLogger('test')

    def test_template_analysis_workflow(self):
        """Test complete template analysis workflow."""
        analyzer = TemplateAnalyzer(self.logger)
        
        # Create a sample template file
        template_content = '''
        {
            "Name": {{ item.name | tojson }},
            "Description": {{ item.description | tojson }},
            "ObjectType": "compute.BiosPolicy",
            "Organization": {
                "Moid": {{ org_moid | tojson }},
                "ObjectType": "organization.Organization"
            }
        }
        '''
        
        variables, attributes = analyzer.analyze_template_file(
            self._create_temp_template(template_content)
        )
        
        self.assertIn('item', variables)
        self.assertIn('org_moid', variables)
        self.assertIn('Name', attributes)
        self.assertIn('Description', attributes)
        self.assertIn('ObjectType', attributes)

    def test_comparison_workflow(self):
        """Test complete comparison workflow."""
        template_analyzer = TemplateAnalyzer(self.logger)
        difference_analyzer = TemplateDifferenceAnalyzer(self.logger)
        
        template_attrs = template_analyzer.extract_json_attributes(
            '{"Name": "test", "OldAttr": "value"}'
        )
        api_attrs = {'Name', 'Description', 'Enabled'}
        
        result = difference_analyzer.compare('test', template_attrs, api_attrs)
        
        self.assertIn('OldAttr', result['missing_in_api'])
        self.assertIn('Description', result['missing_in_template'])

    def test_full_report_generation_workflow(self):
        """Test full workflow from comparison to report generation."""
        comparisons = [
            {
                'template': 'test/policy',
                'template_attributes': 5,
                'api_attributes': 6,
                'missing_in_api': {'OldAttr'},
                'missing_in_template': {'NewAttr'},
                'match_ratio': 0.83
            }
        ]
        
        generator = DifferenceReportGenerator(self.logger)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir) / 'report'
            
            generator.generate_json_report(comparisons, base_path.with_suffix('.json'))
            generator.generate_csv_report(comparisons, base_path.with_suffix('.csv'))
            generator.generate_markdown_report(comparisons, base_path.with_suffix('.md'))
            
            # Verify all files exist
            self.assertTrue((base_path.with_suffix('.json')).exists())
            self.assertTrue((base_path.with_suffix('.csv')).exists())
            self.assertTrue((base_path.with_suffix('.md')).exists())
            
            # Verify JSON content
            with open(base_path.with_suffix('.json')) as f:
                report = json.load(f)
                self.assertEqual(report['total_templates'], 1)

    @staticmethod
    def _create_temp_template(content: str) -> Path:
        """Create a temporary template file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.j2', delete=False) as f:
            f.write(content)
            f.flush()
            return Path(f.name)


if __name__ == '__main__':
    unittest.main()
