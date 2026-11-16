#!/usr/bin/env python3
"""Check BIOS and Adapter templates against Intersight API schemas.

This script compares BIOS, Ethernet Adapter, and Fibre Channel Adapter templates
in the special template organization with actual Intersight SaaS API schemas to
identify missing attributes.

Templates are identified as policies in the special organization:
  5ddfd9ff6972652d31ee6582

API Endpoints:
  - BIOS Templates:          api/v1/bios/Policies
  - Ethernet Adapter:        api/v1/ether/Policies  
  - Fibre Channel Adapter:   api/v1/fc/Policies

This approach follows the pattern provided by the user where templates are
recognized by their organization affiliation, not by separate "template" endpoints.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any, Optional
from collections import defaultdict
from copy import deepcopy

try:
    import requests
    import urllib3
    import yaml
except ImportError as e:
    print(f"ERROR: Missing required module. Install with: pip install {e.name}")
    sys.exit(1)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# =============================================================================
# Configuration
# =============================================================================

# Template organization (special Cisco-provided templates)
TEMPLATE_ORG_MOID = '5ddfd9ff6972652d31ee6582'

# Template types with their API endpoints
TEMPLATE_TYPES = {
    'bios': 'bios/Policies',
    'ethernet_adapter': 'vnic/EthAdapterPolicies',
    'fibre_channel_adapter': 'vnic/FcAdapterPolicies',
}

# Attributes to skip in comparison
# These are read-only or system-managed attributes
SKIP_ATTRIBUTES = {
    'Moid', 'ObjectType', 'ClassId', 'AccountMoid',
    'CreateTime', 'ModTime', 'UpdateTime',
    'Ancestors', 'DomainGroupMoid', 'Owners',
    'PermissionResources', 'Shared', 'SharedScope',
    'Tags', 'Organization', 'Profiles', 'Description',
}


# =============================================================================
# Logging Setup
# =============================================================================

def setup_logging(verbose: bool = False) -> logging.Logger:
    """Set up logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    log_file = f"template_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    logger.info(f"Logging to {log_file}")
    return logger


# =============================================================================
# Intersight Authentication & API
# =============================================================================

class IntersightAPIClient:
    """Client for querying Intersight SaaS API."""

    def __init__(self, api_key_id: str, api_secret_key: str, 
                 base_url: str = "https://intersight.com", logger=None):
        """Initialize API client."""
        self.api_key_id = api_key_id
        self.api_secret_key = api_secret_key
        self.base_url = base_url
        self.logger = logger or logging.getLogger(__name__)
        self.session = requests.Session()
        self.auth = self._init_auth()

    def _init_auth(self):
        """Initialize IntersightAuth."""
        try:
            from intersight_auth import IntersightAuth, repair_pem
            
            # Determine if secret_key is a file or string
            if os.path.isfile(self.api_secret_key):
                auth = IntersightAuth(
                    api_key_id=self.api_key_id,
                    secret_key_filename=self.api_secret_key
                )
                self.logger.debug(f"Loaded secret key from file: {self.api_secret_key}")
            elif '\n' in self.api_secret_key or self.api_secret_key.startswith('-----'):
                auth = IntersightAuth(
                    api_key_id=self.api_key_id,
                    secret_key_string=self.api_secret_key
                )
                self.logger.debug("Using secret key string")
            else:
                auth = IntersightAuth(
                    api_key_id=self.api_key_id,
                    secret_key_string=repair_pem(self.api_secret_key)
                )
                self.logger.debug("Using repaired secret key string")
            return auth
        except Exception as e:
            self.logger.error(f"Failed to initialize auth: {e}")
            return None

    def query_api(self, endpoint: str) -> List[Dict]:
        """Query Intersight API endpoint."""
        if not self.auth:
            self.logger.error("API authentication not initialized")
            return []

        url = f"{self.base_url}/api/v1/{endpoint}"
        
        try:
            self.logger.debug(f"Querying: {url}")
            
            response = self.session.get(
                url,
                auth=self.auth,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('Results', [])
            else:
                self.logger.warning(f"API query failed: {response.status_code}")
                return []
                
        except Exception as e:
            self.logger.error(f"Error querying {endpoint}: {e}")
            return []


# =============================================================================
# Template Checker
# =============================================================================

class BiosAdapterTemplateChecker:
    """Check BIOS and Adapter templates against live API."""

    def __init__(self, api_client: IntersightAPIClient, logger=None):
        """Initialize checker."""
        self.api_client = api_client
        self.logger = logger or logging.getLogger(__name__)
        self.results = {}

    def get_templates(self, endpoint: str) -> Dict[str, Dict]:
        """Get all templates (policies in special org) for given endpoint."""
        policies = self.api_client.query_api(endpoint)
        templates = {}

        for policy in policies:
            # Only include policies from template organization
            if policy.get('Organization', {}).get('Moid') == TEMPLATE_ORG_MOID:
                name = policy.get('Name', 'unknown')
                templates[name] = policy

        return templates

    def extract_attributes(self, obj: Dict) -> Set[str]:
        """Extract all top-level attribute names from object."""
        attributes = set()
        for key, value in obj.items():
            if key not in SKIP_ATTRIBUTES and not key.startswith('_'):
                attributes.add(key)
        return attributes

    def compare_templates(self, template_type: str, templates: Dict[str, Dict]) -> Dict[str, Any]:
        """Compare templates of same type."""
        self.logger.info(f"\nAnalyzing {template_type.upper()} templates:")
        self.logger.info("=" * 80)

        result = {
            'type': template_type,
            'templates_found': len(templates),
            'details': {},
            'summary': {}
        }

        if not templates:
            self.logger.warning(f"No templates found for {template_type}")
            return result

        # Analyze each template
        for name, policy in sorted(templates.items()):
            attrs = self.extract_attributes(policy)
            result['details'][name] = {
                'attributes': sorted(attrs),
                'count': len(attrs)
            }
            self.logger.info(f"  {name:40} {len(attrs):3} attributes")

        # Calculate summary
        all_attributes = set()
        for detail in result['details'].values():
            all_attributes.update(detail['attributes'])

        result['summary'] = {
            'unique_attributes': sorted(all_attributes),
            'unique_count': len(all_attributes),
            'templates_count': len(templates),
        }

        self.logger.info(f"\nTotal unique attributes: {len(all_attributes)}")

        return result

    def run_all_checks(self) -> Dict[str, Any]:
        """Run all template checks."""
        print("\n" + "=" * 80)
        print("BIOS AND ADAPTER TEMPLATE CHECKER")
        print("=" * 80)
        print(f"Intersight SaaS API: https://intersight.com")
        print(f"Template Organization: {TEMPLATE_ORG_MOID}")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print("=" * 80)

        self.results = {
            'timestamp': datetime.now().isoformat(),
            'template_org_moid': TEMPLATE_ORG_MOID,
            'api_base_url': self.api_client.base_url,
            'checks': {}
        }

        # Check BIOS templates
        endpoint = TEMPLATE_TYPES['bios']
        templates = self.get_templates(endpoint)
        self.results['checks']['bios'] = self.compare_templates('bios', templates)

        # Check Ethernet Adapter templates
        endpoint = TEMPLATE_TYPES['ethernet_adapter']
        templates = self.get_templates(endpoint)
        self.results['checks']['ethernet_adapter'] = self.compare_templates(
            'ethernet_adapter', templates
        )

        # Check Fibre Channel Adapter templates
        endpoint = TEMPLATE_TYPES['fibre_channel_adapter']
        templates = self.get_templates(endpoint)
        self.results['checks']['fibre_channel_adapter'] = self.compare_templates(
            'fibre_channel_adapter', templates
        )

        return self.results

    def print_summary(self):
        """Print summary of findings."""
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)

        for check_type, check_result in self.results.get('checks', {}).items():
            print(f"\n{check_type.upper().replace('_', ' ')}:")
            print(f"  Templates Found: {check_result['templates_found']}")
            if check_result.get('summary'):
                print(f"  Unique Attributes: {check_result['summary']['unique_count']}")

    def save_results(self, output_dir: str = None):
        """Save results to files in output directory."""
        if output_dir is None:
            # Default to build/reports/template-checker
            output_dir = Path('build/reports/template-checker')
        else:
            output_dir = Path(output_dir)
        
        # Create directory if it doesn't exist
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # JSON output
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        json_file = output_dir / f"template_check_{timestamp}.json"
        with open(json_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        self.logger.info(f"✅ Results saved to {json_file}")

        # Markdown output
        md_file = output_dir / f"template_check_{timestamp}.md"
        with open(md_file, 'w') as f:
            self._write_markdown(f)
        self.logger.info(f"✅ Markdown report saved to {md_file}")

        return str(json_file), str(md_file)

    def _write_markdown(self, f):
        """Write markdown report."""
        f.write("# BIOS and Adapter Templates Report\n\n")
        f.write(f"**Generated:** {datetime.now().isoformat()}\n\n")
        f.write(f"**Organization:** {TEMPLATE_ORG_MOID}\n\n")

        for check_type, check_result in self.results.get('checks', {}).items():
            f.write(f"## {check_type.upper().replace('_', ' ')}\n\n")
            f.write(f"**Templates Found:** {check_result['templates_found']}\n\n")

            if check_result['details']:
                f.write("### Templates\n\n")
                for name, detail in sorted(check_result['details'].items()):
                    f.write(f"#### {name}\n\n")
                    f.write(f"- **Attributes:** {detail['count']}\n")
                    if detail['attributes']:
                        f.write("- **Attribute List:**\n")
                        for attr in detail['attributes']:
                            f.write(f"  - `{attr}`\n")
                    f.write("\n")

                if check_result.get('summary', {}).get('unique_attributes'):
                    f.write("### All Unique Attributes\n\n")
                    for attr in check_result['summary']['unique_attributes']:
                        f.write(f"- `{attr}`\n")
                    f.write("\n")


# =============================================================================
# Main Entry Point
# =============================================================================

def load_credentials_from_vault() -> Tuple[str, str]:
    """Load API credentials from ansible-vault."""
    vault_path = Path.home() / '.config' / 'cisco-ai-pods' / 'vault.yaml'
    pwd_path = Path.home() / '.config' / 'cisco-ai-pods' / 'vault-password'

    if not vault_path.exists() or not pwd_path.exists():
        raise FileNotFoundError("Vault files not found at ~/.config/cisco-ai-pods/")

    # Read password
    with open(pwd_path, 'r') as f:
        password = f.read().strip()

    # Decrypt vault
    import subprocess
    try:
        result = subprocess.run(
            ['ansible-vault', 'view', str(vault_path), '--vault-password-file', str(pwd_path)],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            raise Exception(f"ansible-vault failed: {result.stderr}")

        vault_data = yaml.safe_load(result.stdout)
    except Exception as e:
        raise Exception(f"Failed to decrypt vault: {e}")

    # Extract credentials
    # Look for intersight section in vault
    if 'intersight' in vault_data:
        intersight = vault_data['intersight']
        api_key_id = intersight.get('intersight_api_key_id')
        api_secret_key = intersight.get('intersight_secret_key_file')
    else:
        raise KeyError("No 'intersight' section found in vault")

    if not api_key_id or not api_secret_key:
        raise ValueError("Missing intersight_api_key_id or intersight_secret_key_file in vault")

    return api_key_id, api_secret_key


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Check BIOS and Adapter templates from Intersight SaaS API'
    )
    parser.add_argument('--api-key-id', help='Intersight API Key ID')
    parser.add_argument('--api-secret-key', help='Intersight API Secret Key')
    parser.add_argument('--vault', action='store_true', 
                        help='Load credentials from ~/.config/cisco-ai-pods/vault.yaml')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose logging')
    parser.add_argument('-o', '--output-dir', default='build/reports/template-checker',
                        help='Output directory (default: build/reports/template-checker)')

    args = parser.parse_args()

    logger = setup_logging(args.verbose)

    # Get credentials
    if args.vault:
        try:
            api_key_id, api_secret_key = load_credentials_from_vault()
            logger.info("✅ Loaded credentials from vault")
        except Exception as e:
            logger.error(f"❌ {e}")
            return 1
    elif args.api_key_id and args.api_secret_key:
        api_key_id = args.api_key_id
        api_secret_key = args.api_secret_key
    else:
        logger.error("❌ Please provide either --vault or --api-key-id/--api-secret-key")
        return 1

    # Initialize API client
    try:
        api_client = IntersightAPIClient(api_key_id, api_secret_key, logger=logger)
        logger.info("✅ Initialized Intersight API client")
    except Exception as e:
        logger.error(f"❌ Failed to initialize API client: {e}")
        return 1

    # Run checks
    try:
        checker = BiosAdapterTemplateChecker(api_client, logger=logger)
        results = checker.run_all_checks()
        checker.print_summary()
        json_file, md_file = checker.save_results(args.output_dir)
        logger.info(f"✅ Check completed successfully")
        return 0
    except Exception as e:
        logger.error(f"❌ Error during check: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
