"""Check template object differences against Intersight live API schemas.

This script extends the template difference checker to analyze template objects:
- BIOS Templates (compute/BiosProfileTemplates)
- Ethernet Adapter Templates (ether/AdapterProfileTemplates)
- Fibre Channel Adapter Templates (fc/AdapterProfileTemplates)
- Storage Templates (storage/StorageProfileTemplates)
- vNIC Templates (vnic/EthAdapterProfileTemplates)
- vHBA Templates (vhba/FibreChannelAdapterProfileTemplates)

Features:
- Queries live Intersight.com API for template object schemas
- Compares actual template definitions against API schema
- Identifies attributes in live API templates not in schema
- Identifies attributes in schema not used in live API templates
- Generates comprehensive reports
"""

import argparse
import json
import logging
import os
import sys
import subprocess
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Optional
from collections import defaultdict


# =============================================================================
# Configuration
# =============================================================================

TEMPLATE_OBJECT_TYPES = {
    'bios_templates': {
        'api': 'compute/BiosProfileTemplates',
        'name': 'BIOS Profile Templates',
        'schema_field': 'intersight.bios.templates',
        'examples': ['C240M5-BIOS', 'C220M5-BIOS']
    },
    'ethernet_adapter_templates': {
        'api': 'ether/AdapterProfileTemplates',
        'name': 'Ethernet Adapter Profile Templates',
        'schema_field': 'intersight.ethernet_adapter.templates',
        'examples': ['LAG-Adapter', 'Default-Adapter']
    },
    'fibre_channel_adapter_templates': {
        'api': 'fc/AdapterProfileTemplates',
        'name': 'Fibre Channel Adapter Profile Templates',
        'schema_field': 'intersight.fibre_channel_adapter.templates',
        'examples': ['FC-Adapter', 'Default-FC']
    },
    'storage_templates': {
        'api': 'storage/StorageProfileTemplates',
        'name': 'Storage Profile Templates',
        'schema_field': 'intersight.storage.templates',
        'examples': ['RAID5-Storage', 'Default-Storage']
    },
    'vnic_templates': {
        'api': 'vnic/EthAdapterProfileTemplates',
        'name': 'vNIC (Ethernet) Profile Templates',
        'schema_field': 'intersight.vnic.templates',
        'examples': ['vNIC-Default', 'vNIC-LAG']
    },
    'vhba_templates': {
        'api': 'vhba/FibreChannelAdapterProfileTemplates',
        'name': 'vHBA (Fibre Channel) Profile Templates',
        'schema_field': 'intersight.vhba.templates',
        'examples': ['vHBA-Default', 'vHBA-FC']
    }
}

# Attributes to skip (read-only, system-managed, or references)
SKIP_ATTRIBUTES = {
    'Moid', 'ObjectType', 'ClassId', 'CreateTime', 'ModTime', 'UpdateTime',
    'Ancestors', 'DomainGroupMoid', 'Owners', 'PermissionResources',
    'Parent', 'Organization', 'Shared', 'SharedScope', 'VersionContext',
    'Tags', 'SrcTemplate', 'TargetMoid'  # Template-specific references
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
            logging.FileHandler(f'template_objects_diff_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


# =============================================================================
# Vault and Credentials
# =============================================================================

def load_vault_credentials(vault_path: Optional[str] = None, 
                          vault_password_path: Optional[str] = None) -> Dict:
    """Load Intersight credentials from ansible-vault encrypted file.
    
    Args:
        vault_path: Path to vault file (default: ~/.config/cisco-ai-pods/vault.yaml)
        vault_password_path: Path to vault password file (default: ~/.config/cisco-ai-pods/vault-password)
        
    Returns:
        Dictionary with intersight credentials
    """
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


# =============================================================================
# Schema and Template Analysis
# =============================================================================

class TemplateObjectAnalyzer:
    """Analyze template objects from live Intersight API."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.template_objects = {}
    
    def fetch_template_objects(self, api_type: str, api_key_id: str, 
                              secret_key: str) -> List[Dict]:
        """Fetch template objects from Intersight API.
        
        Args:
            api_type: API endpoint (e.g., 'compute/BiosProfileTemplates')
            api_key_id: Intersight API key ID
            secret_key: Intersight secret key (or file path)
            
        Returns:
            List of template objects from API
        """
        try:
            # Import IntersightAuth for authenticated requests
            try:
                from intersight_auth import IntersightAuth, repair_pem
            except ImportError:
                self.logger.warning(f"IntersightAuth module not available; install with: pip install intersight-auth")
                return []
            
            # Initialize authentication
            self.logger.debug(f"Initializing authentication with key ID: {api_key_id[:20]}...")
            
            # Determine if secret_key is a file or string
            if Path(secret_key).exists():
                self.logger.debug(f"Using secret key from file: {secret_key}")
                auth = IntersightAuth(
                    api_key_id=api_key_id,
                    secret_key_filename=str(secret_key)
                )
            elif '\n' in secret_key or secret_key.startswith('-----'):
                self.logger.debug("Using secret key string (PEM format)")
                auth = IntersightAuth(
                    api_key_id=api_key_id,
                    secret_key_string=secret_key
                )
            else:
                self.logger.debug("Attempting to repair and use secret key string")
                auth = IntersightAuth(
                    api_key_id=api_key_id,
                    secret_key_string=repair_pem(secret_key)
                )
            
            # Query API
            url = f'https://intersight.com/api/v1/{api_type}?$top=1000'
            self.logger.debug(f"Querying: {url}")
            
            response = auth.request('GET', url)
            
            if response.status_code == 200:
                data = response.json()
                templates = data.get('Results', [])
                self.logger.info(f"✓ Retrieved {len(templates)} {api_type} template objects")
                return templates
            else:
                self.logger.warning(f"API query failed for {api_type}: {response.status_code}")
                try:
                    error_info = response.json()
                    self.logger.debug(f"Error response: {error_info}")
                except:
                    self.logger.debug(f"Response text: {response.text[:200]}")
                return []
                
        except Exception as e:
            self.logger.error(f"Error fetching {api_type}: {e}", exc_info=False)
            return []
    
    def extract_attributes(self, objects: List[Dict]) -> Set[str]:
        """Extract all attributes from template objects.
        
        Args:
            objects: List of template objects from API
            
        Returns:
            Set of attribute names (excluding skipped attributes)
        """
        attributes = set()
        for obj in objects:
            for key in obj.keys():
                if key not in SKIP_ATTRIBUTES:
                    attributes.add(key)
        return attributes
    
    def load_schema_attributes(self, schema_field: str) -> Set[str]:
        """Load template attributes from schema definition.
        
        Args:
            schema_field: Schema definition field (e.g., 'intersight.bios.templates')
            
        Returns:
            Set of attribute names defined in schema
        """
        # This would load from the schemas/source/intersight.json
        # For now, return empty set as placeholder
        return set()


class TemplateObjectComparison:
    """Compare template objects across API and schema."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.results = []
    
    def compare(self, template_type: str, api_attrs: Set[str], 
                schema_attrs: Set[str], live_templates: List[Dict]) -> Dict:
        """Compare template object attributes.
        
        Args:
            template_type: Type of template (e.g., 'bios_templates')
            api_attrs: Attributes found in live API templates
            schema_attrs: Attributes defined in schema
            live_templates: List of live template objects
            
        Returns:
            Comparison result dictionary
        """
        api_only = api_attrs - schema_attrs
        schema_only = schema_attrs - api_attrs
        both = api_attrs & schema_attrs
        
        return {
            'template_type': template_type,
            'template_count': len(live_templates),
            'api_attributes': len(api_attrs),
            'schema_attributes': len(schema_attrs),
            'in_both': len(both),
            'api_only': sorted(api_only),
            'schema_only': sorted(schema_only),
            'coverage': (len(both) / len(api_attrs) * 100) if api_attrs else 0,
            'live_templates': [
                {
                    'name': t.get('Name', 'Unknown'),
                    'moid': t.get('Moid', ''),
                    'attributes': sorted([k for k in t.keys() if k not in SKIP_ATTRIBUTES])
                }
                for t in live_templates[:5]  # First 5 as examples
            ]
        }


# =============================================================================
# Report Generation
# =============================================================================

class TemplateObjectReportGenerator:
    """Generate reports for template object compliance."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def generate_markdown_report(self, results: List[Dict], output_file: Path):
        """Generate markdown report.
        
        Args:
            results: List of comparison results
            output_file: Output file path
        """
        with open(output_file, 'w') as f:
            f.write("# Template Object Compliance Analysis Report\n\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n\n")
            
            f.write("## Summary\n\n")
            f.write(f"- **Template Object Types Analyzed**: {len(results)}\n\n")
            
            # Summary table
            f.write("| Template Type | Count | API Attrs | Coverage | Gaps |\n")
            f.write("|---|---|---|---|---|\n")
            
            total_gaps = 0
            for result in results:
                template_type = result['template_type'].replace('_', ' ').title()
                gaps = len(result['api_only'])
                total_gaps += gaps
                coverage = f"{result['coverage']:.1f}%"
                f.write(f"| {template_type} | {result['template_count']} | "
                       f"{result['api_attributes']} | {coverage} | {gaps} |\n")
            
            f.write(f"\n**Total Gaps**: {total_gaps}\n\n")
            
            # Detailed findings
            f.write("## Detailed Findings\n\n")
            
            for result in results:
                template_type = result['template_type'].replace('_', ' ').title()
                f.write(f"### {template_type}\n\n")
                
                f.write(f"**Metrics**:\n")
                f.write(f"- Live Templates: {result['template_count']}\n")
                f.write(f"- API Attributes: {result['api_attributes']}\n")
                f.write(f"- Schema Attributes: {result['schema_attributes']}\n")
                f.write(f"- Coverage: {result['coverage']:.1f}%\n\n")
                
                if result['api_only']:
                    f.write(f"**Missing from Schema** ({len(result['api_only'])} attributes):\n")
                    for attr in result['api_only'][:10]:  # Show first 10
                        f.write(f"- {attr}\n")
                    if len(result['api_only']) > 10:
                        f.write(f"- ... and {len(result['api_only']) - 10} more\n")
                    f.write("\n")
                
                if result['schema_only']:
                    f.write(f"**Unused in Schema** ({len(result['schema_only'])} attributes):\n")
                    for attr in result['schema_only'][:10]:  # Show first 10
                        f.write(f"- {attr}\n")
                    if len(result['schema_only']) > 10:
                        f.write(f"- ... and {len(result['schema_only']) - 10} more\n")
                    f.write("\n")
                
                if result['live_templates']:
                    f.write(f"**Example Live Templates**:\n")
                    for tmpl in result['live_templates']:
                        f.write(f"- **{tmpl['name']}** ({tmpl['moid'][:8]}...)\n")
                        f.write(f"  - Attributes: {len(tmpl['attributes'])}\n")
                    f.write("\n")
        
        self.logger.info(f"Markdown report written to {output_file}")
    
    def generate_json_report(self, results: List[Dict], output_file: Path):
        """Generate JSON report.
        
        Args:
            results: List of comparison results
            output_file: Output file path
        """
        report = {
            'generated': datetime.now().isoformat(),
            'template_object_types': len(results),
            'results': results
        }
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        self.logger.info(f"JSON report written to {output_file}")
    
    def generate_console_summary(self, results: List[Dict]):
        """Generate console summary.
        
        Args:
            results: List of comparison results
        """
        print("\n" + "="*80)
        print("TEMPLATE OBJECT COMPLIANCE ANALYSIS SUMMARY")
        print("="*80 + "\n")
        
        total_gaps = 0
        total_coverage = 0
        
        for result in results:
            template_type = result['template_type'].replace('_', ' ').title()
            gaps = len(result['api_only'])
            total_gaps += gaps
            total_coverage += result['coverage']
            
            status = "✅" if gaps == 0 else "⚠️"
            print(f"{status} {template_type:<50} {result['coverage']:>6.1f}% ({gaps} gaps)")
        
        print("\n" + "="*80)
        avg_coverage = total_coverage / len(results) if results else 0
        print(f"Average Coverage: {avg_coverage:.1f}%")
        print(f"Total Gaps: {total_gaps}")
        print("="*80 + "\n")


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main entry point for template object compliance checker."""
    parser = argparse.ArgumentParser(
        description='Analyze template object compliance against Intersight API'
    )
    parser.add_argument(
        '-t', '--template-type',
        choices=list(TEMPLATE_OBJECT_TYPES.keys()) + ['all'],
        default='all',
        help='Template type to analyze (default: all)'
    )
    parser.add_argument(
        '-o', '--output',
        type=str,
        default='template_objects_diff',
        help='Output filename prefix (without extension)'
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
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(args.verbose)
    logger.info("Starting Template Object Compliance Analysis")
    
    # Load credentials
    api_key_id = args.api_key_id
    api_secret_key = args.api_secret_key
    
    if not api_key_id or not api_secret_key:
        logger.info("Loading credentials from vault...")
        try:
            creds = load_vault_credentials(args.vault, args.vault_password)
            api_key_id = api_key_id or creds.get('intersight_api_key_id')
            
            secret_key_file = creds.get('intersight_secret_key_file')
            secret_key_content = creds.get('intersight_secret_key')
            
            if secret_key_file:
                api_secret_key = api_secret_key or secret_key_file
            elif secret_key_content:
                api_secret_key = api_secret_key or secret_key_content
            
            if not api_key_id or not api_secret_key:
                logger.error("Credentials incomplete")
                sys.exit(1)
            
            logger.info("✓ Credentials loaded from vault")
        except Exception as e:
            logger.error(f"Failed to load credentials: {e}")
            sys.exit(1)
    
    # Initialize analyzers
    analyzer = TemplateObjectAnalyzer(logger)
    comparator = TemplateObjectComparison(logger)
    reporter = TemplateObjectReportGenerator(logger)
    
    # Determine which template types to analyze
    types_to_analyze = (
        [args.template_type] if args.template_type != 'all' 
        else list(TEMPLATE_OBJECT_TYPES.keys())
    )
    
    # Analyze each template type
    all_results = []
    
    for template_type in types_to_analyze:
        logger.info(f"\nAnalyzing {template_type}...")
        config = TEMPLATE_OBJECT_TYPES[template_type]
        
        # Fetch live templates
        logger.debug(f"Querying API: {config['api']}")
        live_templates = analyzer.fetch_template_objects(
            config['api'],
            api_key_id,
            api_secret_key
        )
        
        if not live_templates:
            logger.warning(f"No templates found for {template_type}")
            continue
        
        # Extract attributes
        api_attrs = analyzer.extract_attributes(live_templates)
        logger.debug(f"Found {len(api_attrs)} attributes in {len(live_templates)} templates")
        
        # Load schema attributes (placeholder for now)
        schema_attrs = analyzer.load_schema_attributes(config['schema_field'])
        logger.debug(f"Found {len(schema_attrs)} attributes in schema")
        
        # Compare
        result = comparator.compare(template_type, api_attrs, schema_attrs, live_templates)
        all_results.append(result)
    
    # Generate reports
    output_base = Path(args.output)
    logger.info("\nGenerating reports...")
    
    reporter.generate_json_report(all_results, output_base.with_suffix('.json'))
    reporter.generate_markdown_report(all_results, output_base.with_suffix('.md'))
    reporter.generate_console_summary(all_results)
    
    logger.info("Analysis complete")


if __name__ == '__main__':
    main()
