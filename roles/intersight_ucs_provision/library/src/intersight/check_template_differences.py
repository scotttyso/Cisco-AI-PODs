"""Check template differences against Intersight API schemas.

This script compares local Jinja2 templates with actual Intersight SaaS API schemas
to identify missing attributes, deprecated attributes, and other discrepancies.

Features:
- Queries live Intersight.com API for real attribute schemas
- Caches responses (24 hours) to minimize API calls
- Extracts attributes from local Jinja2 templates
- Performs bidirectional comparison
- Generates reports in JSON, CSV, and Markdown formats
"""

import argparse
import json
import logging
import os
import re
import sys
import time
import requests
import yaml
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any, Optional
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
# These are read-only or system-managed attributes that typically don't need
# to be added to templates
COMMON_ATTRIBUTES = {
    # Identifiers and system metadata
    'Moid', 'ObjectType', 'ClassId', 'AccountMoid', 'AccountMoidList',
    
    # Timestamps
    'CreateTime', 'ModTime', 'UpdateTime', 'LastModifiedTime',
    
    # Hierarchy and relationships
    'Ancestors', 'DomainGroupMoid', 'Owners', 'PermissionResources',
    'Parent', 'Organization',
    
    # Sharing and versioning
    'Shared', 'SharedScope', 'VersionContext', 'Tags',
    
    # Other read-only fields
    'Description', 'Name'
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
# API Schema Analysis - Live Intersight SaaS API Queries
# =============================================================================

class IntersightAPIClient:
    """Client for querying Intersight SaaS API for schema information."""

    def __init__(self, api_key_id: str, secret_key: str, api_url: str, logger: logging.Logger):
        """Initialize Intersight API client.
        
        Args:
            api_key_id: Intersight API key ID
            secret_key: Intersight secret key (content or file path)
            api_url: Intersight API URL (e.g., https://intersight.com)
            logger: Logger instance
        """
        self.logger = logger
        self.api_key_id = api_key_id
        self.secret_key = secret_key
        self.api_url = api_url
        self.auth = None
        self._initialize_auth()

    def _initialize_auth(self):
        """Initialize IntersightAuth for API authentication."""
        try:
            from intersight_auth import IntersightAuth, repair_pem
            
            # Determine if secret_key is a file or string
            if os.path.isfile(self.secret_key):
                self.auth = IntersightAuth(
                    api_key_id=self.api_key_id,
                    secret_key_filename=self.secret_key
                )
                self.logger.debug(f"Loaded secret key from file: {self.secret_key}")
            elif '\n' in self.secret_key or self.secret_key.startswith('-----'):
                self.auth = IntersightAuth(
                    api_key_id=self.api_key_id,
                    secret_key_string=self.secret_key
                )
                self.logger.debug("Using secret key string from vault")
            else:
                self.auth = IntersightAuth(
                    api_key_id=self.api_key_id,
                    secret_key_string=repair_pem(self.secret_key)
                )
                self.logger.debug("Using repaired secret key string")
        except ImportError as e:
            self.logger.error(f"Failed to import IntersightAuth: {e}")
            self.auth = None
        except Exception as e:
            self.logger.error(f"Failed to initialize authentication: {e}")
            self.auth = None

    def query_policy_schema(self, policy_type: str) -> Dict[str, Any]:
        """Query Intersight API to get policy schema attributes.
        
        Args:
            policy_type: Policy type (e.g., 'compute.BiosPolicy', 'fabric.Vlan')
            
        Returns:
            Dictionary with policy attributes or empty dict if query fails
        """
        if not self.auth:
            self.logger.warning(f"Cannot query policy {policy_type}: authentication not initialized")
            return {}
        
        try:
            # Construct API endpoint URL
            # For schema queries, we request example data which includes all attributes
            endpoint = f"/api/v1/{policy_type}?$top=1"
            url = f"{self.api_url}{endpoint}"
            
            self.logger.debug(f"Querying: {url}")
            
            # Make authenticated request
            response = requests.get(
                url,
                auth=self.auth,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if 'Results' in data and len(data['Results']) > 0:
                    return data['Results'][0]
                else:
                    self.logger.debug(f"No results returned for {policy_type}")
                    return {}
            else:
                self.logger.warning(f"API query failed for {policy_type}: {response.status_code}")
                return {}
        except Exception as e:
            self.logger.error(f"Error querying {policy_type}: {e}")
            return {}


class APISchemaAnalyzer:
    """Analyze Intersight API schemas using live API or cached data."""

    def __init__(self, logger: logging.Logger, api_client: Optional[IntersightAPIClient] = None):
        """Initialize API schema analyzer.
        
        Args:
            logger: Logger instance
            api_client: Optional IntersightAPIClient for live queries
        """
        self.logger = logger
        self.api_client = api_client
        self.schemas = {}
        self.cache_dir = Path.home() / '.cache' / 'intersight_schemas'
        self.cache_ttl = 86400  # 24 hours in seconds
        self._create_cache_dir()

    def _create_cache_dir(self):
        """Create cache directory if it doesn't exist."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Using cache directory: {self.cache_dir}")
        except Exception as e:
            self.logger.warning(f"Failed to create cache directory: {e}")
            self.cache_dir = None

    def _get_cache_file(self, policy_type: str) -> Optional[Path]:
        """Get cache file path for a policy type."""
        if not self.cache_dir:
            return None
        
        # Sanitize policy type for filename
        safe_name = policy_type.replace('/', '_').replace('.', '_')
        return self.cache_dir / f"{safe_name}.json"

    def _is_cache_valid(self, cache_file: Path) -> bool:
        """Check if cache file is still valid (within TTL)."""
        try:
            if not cache_file.exists():
                return False
            
            age = time.time() - cache_file.stat().st_mtime
            is_valid = age < self.cache_ttl
            
            if not is_valid:
                self.logger.debug(f"Cache expired for {cache_file.name}")
            
            return is_valid
        except Exception as e:
            self.logger.warning(f"Error checking cache validity: {e}")
            return False

    def _load_from_cache(self, cache_file: Path) -> Optional[Dict[str, Any]]:
        """Load schema from cache file."""
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
                self.logger.debug(f"Loaded from cache: {cache_file.name}")
                return data
        except Exception as e:
            self.logger.warning(f"Failed to load from cache: {e}")
            return None

    def _save_to_cache(self, cache_file: Path, schema: Dict[str, Any]) -> bool:
        """Save schema to cache file."""
        try:
            with open(cache_file, 'w') as f:
                json.dump(schema, f, indent=2, default=str)
            self.logger.debug(f"Saved to cache: {cache_file.name}")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to save to cache: {e}")
            return False

    def fetch_schema(self, policy_type: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch schema for a policy type (with caching).
        
        Args:
            policy_type: Policy type to fetch schema for
            force_refresh: Force fresh API query (bypass cache)
            
        Returns:
            Dictionary containing policy schema
        """
        cache_file = self._get_cache_file(policy_type)
        
        # Check cache first (unless force_refresh)
        if cache_file and not force_refresh:
            if self._is_cache_valid(cache_file):
                schema = self._load_from_cache(cache_file)
                if schema:
                    return schema
        
        # Query API if cache miss or force_refresh
        if self.api_client:
            schema = self.api_client.query_policy_schema(policy_type)
            
            # Cache the result
            if schema and cache_file:
                self._save_to_cache(cache_file, schema)
            
            return schema
        else:
            self.logger.warning(f"No API client available to query {policy_type}")
            return {}

    def extract_schema_attributes(self, schema: Dict[str, Any]) -> Set[str]:
        """Extract top-level attributes from API schema.
        
        Args:
            schema: API schema dictionary (from live Intersight API)
            
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

    def __init__(self, logger: logging.Logger, exclusion_config: Optional[Dict[str, Set[str]]] = None):
        """Initialize difference analyzer.
        
        Args:
            logger: Logger instance
            exclusion_config: Optional config with 'global' and policy-type exclusion sets
        """
        self.logger = logger
        self.exclusion_config = exclusion_config or {'global': set(COMMON_ATTRIBUTES), 'policies': {}}
        self.differences = defaultdict(lambda: {
            'missing_in_api': set(),
            'missing_in_template': set(),
            'warnings': []
        })

    def _get_exclusions_for_template(self, template_name: str) -> Set[str]:
        """Get all exclusions (global + policy-specific) for a template.
        
        Args:
            template_name: Template name (e.g., 'policies/vlan')
            
        Returns:
            Set of attribute names to exclude
        """
        # Start with global exclusions
        exclusions = set(self.exclusion_config.get('global', set(COMMON_ATTRIBUTES)))
        
        # Add policy-specific exclusions
        # Extract policy type from template name (e.g., 'policies/vlan' -> 'vlan')
        parts = template_name.split('/')
        if len(parts) >= 2:
            policy_type = parts[1].split('.')[0]  # Handle names like 'vlan.vlans'
            policy_exclusions = self.exclusion_config.get('policies', {}).get(policy_type, set())
            exclusions.update(policy_exclusions)
        
        return exclusions

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
        # Get exclusions for this template
        exclusions = self._get_exclusions_for_template(template_name)
        
        # Remove excluded attributes from comparison
        template_attrs_filtered = template_attrs - exclusions
        api_attrs_filtered = api_attrs - exclusions
        
        missing_in_api = template_attrs_filtered - api_attrs_filtered
        missing_in_template = api_attrs_filtered - template_attrs_filtered
        
        result = {
            'template': template_name,
            'template_attributes': len(template_attrs_filtered),
            'api_attributes': len(api_attrs_filtered),
            'missing_in_api': sorted(missing_in_api),
            'missing_in_template': sorted(missing_in_template),
            'match_ratio': len(template_attrs_filtered & api_attrs_filtered) / max(len(template_attrs_filtered), len(api_attrs_filtered), 1)
        }
        
        self.differences[template_name] = {
            'missing_in_api': set(result['missing_in_api']),
            'missing_in_template': set(result['missing_in_template']),
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
# Configuration Management
# =============================================================================

def load_exclusion_config(config_file: Optional[Path] = None) -> Dict[str, Set[str]]:
    """Load attribute exclusion configuration from YAML file.
    
    Config file format:
    ```yaml
    # Global exclusions apply to all policies
    global_exclusions:
      - Moid
      - CreateTime
      - ModTime
    
    # Per-policy-type exclusions
    policy_exclusions:
      vlan:
        - Description
        - TargetPlatform
      storage:
        - SomeReadOnlyField
    ```
    
    Args:
        config_file: Path to YAML config file
        
    Returns:
        Dictionary with 'global' and policy-type keys
    """
    exclusions = {
        'global': set(COMMON_ATTRIBUTES),  # Start with defaults
        'policies': {}
    }
    
    if not config_file:
        return exclusions
    
    config_file = Path(config_file)
    if not config_file.exists():
        return exclusions
    
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        if not config:
            return exclusions
        
        # Load global exclusions
        if 'global_exclusions' in config:
            exclusions['global'].update(config['global_exclusions'])
        
        # Load per-policy exclusions
        if 'policy_exclusions' in config:
            for policy_type, excluded_attrs in config['policy_exclusions'].items():
                exclusions['policies'][policy_type] = set(excluded_attrs or [])
        
        return exclusions
    except Exception as e:
        print(f"Warning: Failed to load exclusion config: {e}", file=sys.stderr)
        return exclusions


# =============================================================================
# Main Script
# =============================================================================

def load_vault_credentials(vault_path: Optional[str] = None, 
                         vault_password_path: Optional[str] = None) -> Dict[str, Any]:
    """Load credentials from ansible-vault encrypted file.
    
    Args:
        vault_path: Path to vault file (default: ~/.config/cisco-ai-pods/vault.yaml)
        vault_password_path: Path to vault password file (default: ~/.config/cisco-ai-pods/vault-password)
        
    Returns:
        Dictionary with intersight credentials
    """
    import subprocess
    
    if not vault_path:
        vault_path = Path.home() / '.config' / 'cisco-ai-pods' / 'vault.yaml'
    if not vault_password_path:
        vault_password_path = Path.home() / '.config' / 'cisco-ai-pods' / 'vault-password'
    
    vault_path = Path(vault_path)
    vault_password_path = Path(vault_password_path)
    
    if not vault_path.exists():
        raise FileNotFoundError(f"Vault file not found: {vault_path}")
    if not vault_password_path.exists():
        raise FileNotFoundError(f"Vault password file not found: {vault_password_path}")
    
    try:
        # Use ansible-vault to decrypt
        result = subprocess.run(
            ['ansible-vault', 'view', str(vault_path), '--vault-password-file', str(vault_password_path)],
            capture_output=True,
            text=True,
            check=True
        )
        
        vault_data = yaml.safe_load(result.stdout)
        return vault_data.get('intersight', {})
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to decrypt vault: {e.stderr}")
    except Exception as e:
        raise RuntimeError(f"Error loading vault credentials: {e}")


def main():
    """Main entry point for template difference checker."""
    parser = argparse.ArgumentParser(
        description='Analyze differences between Intersight SaaS API and local templates'
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
        '--config',
        type=str,
        default=None,
        help='Path to attribute exclusion config file (YAML)'
    )
    parser.add_argument(
        '--vault',
        type=str,
        default=None,
        help='Path to ansible-vault encrypted credentials file'
    )
    parser.add_argument(
        '--vault-password',
        type=str,
        default=None,
        help='Path to vault password file'
    )
    parser.add_argument(
        '--api-key-id',
        type=str,
        default=None,
        help='Intersight API key ID (or use vault)'
    )
    parser.add_argument(
        '--api-secret-key',
        type=str,
        default=None,
        help='Intersight secret key (or use vault)'
    )
    parser.add_argument(
        '--no-cache',
        action='store_true',
        help='Force fresh API queries (bypass cache)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(args.verbose)
    logger.info("Starting Template Difference Analysis (Live Intersight SaaS API)")
    
    # Load exclusion config
    exclusion_config = load_exclusion_config(args.config)
    logger.debug(f"Loaded {len(exclusion_config.get('global', set()))} global exclusions")
    
    # Load credentials
    api_key_id = args.api_key_id
    api_secret_key = args.api_secret_key
    
    if not api_key_id or not api_secret_key:
        logger.info("Loading credentials from vault...")
        try:
            creds = load_vault_credentials(args.vault, args.vault_password)
            api_key_id = api_key_id or creds.get('intersight_api_key_id')
            
            # Secret key can be a file path or content
            secret_key_file = creds.get('intersight_secret_key_file')
            secret_key_content = creds.get('intersight_secret_key')
            
            if secret_key_file:
                api_secret_key = api_secret_key or secret_key_file
            elif secret_key_content:
                api_secret_key = api_secret_key or secret_key_content
            
            if not api_key_id:
                logger.error("API key ID not found in vault or arguments")
                sys.exit(1)
            if not api_secret_key:
                logger.error("Secret key not found in vault or arguments")
                sys.exit(1)
            
            logger.info("✓ Credentials loaded from vault")
        except Exception as e:
            logger.error(f"Failed to load credentials: {e}")
            logger.info("Use --api-key-id and --api-secret-key arguments, or set up vault at ~/.config/cisco-ai-pods/vault.yaml")
            sys.exit(1)
    
    # Initialize API client and schema analyzer
    logger.info("Initializing Intersight API client...")
    try:
        api_client = IntersightAPIClient(
            api_key_id=api_key_id,
            secret_key=api_secret_key,
            api_url='https://intersight.com',
            logger=logger
        )
        
        schema_analyzer = APISchemaAnalyzer(logger, api_client=api_client)
        logger.info("✓ API client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize API client: {e}")
        sys.exit(1)
    
    # Initialize other analyzers
    template_analyzer = TemplateAnalyzer(logger)
    difference_analyzer = TemplateDifferenceAnalyzer(logger, exclusion_config)
    report_generator = DifferenceReportGenerator(logger)
    
    # Policy type mappings (template name -> Intersight API type)
    policy_type_map = {
        # Mapping template names to Intersight API endpoints
        # Format: api/v1/namespace/ResourcePlural
        # Note: Endpoints use plurals and path separators instead of dots
        'adapter_configuration': 'compute/AdapterConfigPolicies',
        'auditd': 'compute/AuditdPolicies',
        'bios': 'compute/BiosPolicies',
        'boot_order': 'compute/BootOrderPolicies',
        'certificate_management': 'fabric/CertificateManagementPolicies',
        'device_connector': 'compute/DeviceConnectorPolicies',
        'drive_security': 'compute/DriveSecurityPolicies',
        'ethernet_adapter': 'ether/AdapterPolicies',
        'ethernet_network': 'fabric/EthNetworkPolicies',
        'ethernet_network_control': 'fabric/EthNetworkControlPolicies',
        'ethernet_network_group': 'fabric/EthNetworkGroupPolicies',
        'ethernet_qos': 'fabric/EthQosPolicies',
        'fc_zone': 'fabric/FcZonePolicies',
        'fibre_channel_adapter': 'fc/AdapterPolicies',
        'fibre_channel_network': 'fabric/FcNetworkPolicies',
        'fibre_channel_qos': 'fabric/FcQosPolicies',
        'firmware': 'firmware/BaselinePolicies',
        'flow_control': 'fabric/FlowControlPolicies',
        'id_mapping': 'compute/IdMappings',
        'imc_access': 'compute/ImcAccessPolicies',
        'ipmi_over_lan': 'compute/IpmiOverLanPolicies',
        'iscsi_adapter': 'ether/IscsiAdapterPolicies',
        'iscsi_boot': 'compute/IscsiBootPolicies',
        'iscsi_static_target': 'compute/IscsiStaticTargetPolicies',
        'lan_connectivity': 'compute/LanConnectivityPolicies',
        'ldap': 'iam/LdapPolicies',
        'link_aggregation': 'fabric/LinkAggregationPolicies',
        'link_control': 'fabric/LinkControlPolicies',
        'local_user': 'iam/LocalUserPolicies',
        'mac_sec': 'fabric/MacSecPolicies',
        'memory': 'compute/MemoryPolicies',
        'multicast': 'fabric/MulticastPolicies',
        'netflow_configuration': 'fabric/NetflowPolicies',
        'network_connectivity': 'compute/NetworkConnectivityPolicies',
        'ntp': 'compute/NtpPolicies',
        'pcie_connectivity': 'compute/PcieConnectivityPolicies',
        'persistent_memory': 'compute/PersistentMemoryPolicies',
        'port': 'fabric/PortPolicies',
        'power': 'compute/PowerPolicies',
        'san_connectivity': 'compute/SanConnectivityPolicies',
        'scrub': 'compute/ScrubPolicies',
        'sd_card': 'compute/SdCardPolicies',
        'serial_over_lan': 'compute/SerialOverLanPolicies',
        'server_pool_qualification': 'compute/ServerPoolQualificationPolicies',
        'smtp': 'smtp/SmtpPolicies',
        'snmp': 'snmp/SnmpPolicies',
        'ssh': 'ssh/SshPolicies',
        'storage': 'storage/StoragePolicies',
        'switch_control': 'fabric/SwitchControlPolicies',
        'syslog': 'syslog/SyslogPolicies',
        'system_qos': 'fabric/SystemQosPolicies',
        'thermal': 'compute/ThermalPolicies',
        'virtual_kvm': 'compute/VirtualKvmPolicies',
        'virtual_media': 'compute/VirtualMediaPolicies',
        'vlan': 'fabric/Vlans',
        'vsan': 'fabric/Vsans',
        # Pools - endpoints may vary
        'ip': 'ippool/IpPools',
        'mac': 'macpool/MacPools',
        'iqn': 'iqnpool/IqnPools',
        'uuid': 'uuidpool/UuidPools',
    }
    
    # Analyze templates
    categories_to_analyze = [args.category] if args.category != 'all' else list(CATEGORIES.keys())
    all_comparisons = []
    
    for category in categories_to_analyze:
        logger.info(f"\nAnalyzing {category} templates...")
        category_results = template_analyzer.analyze_category(category)
        
        for template_name, (variables, attributes) in category_results.items():
            # Get API policy type
            api_policy_type = policy_type_map.get(template_name)
            
            if api_policy_type:
                logger.debug(f"Querying API for {api_policy_type}...")
                api_schema = schema_analyzer.fetch_schema(api_policy_type, force_refresh=args.no_cache)
                api_attrs = schema_analyzer.extract_schema_attributes(api_schema)
                
                if not api_attrs:
                    logger.warning(f"No attributes retrieved for {api_policy_type}, using template as baseline")
                    api_attrs = attributes
            else:
                logger.debug(f"No API mapping for {template_name}, comparing against template")
                api_attrs = attributes
            
            comparison = difference_analyzer.compare(
                f"{category}/{template_name}",
                attributes,
                api_attrs
            )
            all_comparisons.append(comparison)
    
    # Generate reports
    output_base = Path(args.output)
    output_formats = [args.formats] if args.formats != 'all' else ['json', 'csv', 'markdown']
    
    logger.info("\nGenerating reports...")
    if 'json' in output_formats:
        report_generator.generate_json_report(all_comparisons, output_base.with_suffix('.json'))
    if 'csv' in output_formats:
        report_generator.generate_csv_report(all_comparisons, output_base.with_suffix('.csv'))
    if 'markdown' in output_formats:
        report_generator.generate_markdown_report(all_comparisons, output_base.with_suffix('.md'), args.details)
    
    # Print console summary
    report_generator.generate_console_summary(all_comparisons)
    
    logger.info(f"Analysis complete. Analyzed {template_analyzer.templates_analyzed} templates.")
    logger.info(f"Reports written to: {output_base}.*")


if __name__ == '__main__':
    main()

