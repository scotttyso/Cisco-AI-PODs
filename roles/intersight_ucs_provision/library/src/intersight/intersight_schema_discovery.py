"""
Schema discovery and querying for Feature 2.

Queries target environment's API to discover supported attributes for each policy/profile type.
"""

import requests
from typing import Dict, List, Any, Optional


class SchemaDiscovery:
    """Query Intersight API schema for supported attributes."""

    # API endpoints to query for each object type
    SCHEMA_ENDPOINTS = {
        'policies': [
            'bios/Policies',
            'boot/PrecisionPolicies',
            'vnic/EthAdapterPolicies',
            'vnic/EthQosPolicies',
            'vnic/FcAdapterPolicies',
            'fabric/EthNetworkControlPolicies',
            'fabric/EthNetworkGroupPolicies',
            'ippool/IpPools',
            'macpool/Pools',
            'uuidpool/Pools',
            'iqnpool/Pools',
            'fcpool/Pools',
            'storage/StoragePolicies',
            'ipmioverlan/Policies',
            'imcaccess/Policies',
            'cifs/Server',
            'ntp/Policy',
            'kmip/CipherSuites',
            'comm/LocalUserPasswords',
            'deviceconnector/DeviceConnectorManagers',
            'firmware/Policies',
            'memory/Policies',
            'power/Policies',
            'recovery/Policies',
            'serial/Policies',
            'thermal/Policies',
            'access/Policies',
            'adapter/ConfigPolicy',
        ],
        'profiles': [
            'server/Profiles',
            'domain/Profiles',
            'chassis/Profiles',
        ],
        'templates': [
            'bios/ProfileTemplates',
            'boot/ProfileTemplates',
            'compute/BladeProfileTemplates',
        ]
    }

    def __init__(self, endpoint: str, apikey: str, secretkey: str):
        """Initialize schema discoverer.

        Args:
            endpoint: API endpoint URL (e.g., 'https://cva.example.com')
            apikey: API key ID
            secretkey: API secret key
        """
        self.endpoint = endpoint.rstrip('/')
        self.apikey = apikey
        self.secretkey = secretkey
        self.session = None

    def _setup_session(self):
        """Setup requests session with API authentication."""
        # Import here to avoid dependency issues
        try:
            pass
        except ImportError:
            raise ImportError(
                "Intersight SDK required: pip install intersight"
            )

        # Create authenticated session
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        })

    def query_schema(self, uri_path: str) -> Optional[Dict[str, Any]]:
        """Query API schema for a specific endpoint.

        Args:
            uri_path: API path (e.g., 'bios/Policies')

        Returns:
            Schema dict or None if query fails
        """
        if not self.session:
            self._setup_session()

        schema_url = f"{self.endpoint}/api/v1/json-schemas/v1/{uri_path}"

        try:
            # Try to get schema via JSON schema endpoint
            response = self.session.get(schema_url, timeout=10)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass

        return None

    def extract_attributes(self, schema: Dict[str, Any]) -> List[str]:
        """Extract attribute names from schema.

        Args:
            schema: Schema dict from API

        Returns:
            List of attribute names
        """
        attributes = []

        # Schema structure varies, try common patterns
        if 'properties' in schema:
            attributes.extend(schema['properties'].keys())
        elif 'x-intersight-properties' in schema:
            attributes.extend(schema['x-intersight-properties'].keys())
        elif 'allOf' in schema:
            # Handle allOf composition
            for sub_schema in schema['allOf']:
                if 'properties' in sub_schema:
                    attributes.extend(sub_schema['properties'].keys())

        return sorted(list(set(attributes)))  # Remove duplicates and sort

    def discover_all_attributes(self, category: str = 'policies',
                                max_retries: int = 3) -> Dict[str, List[str]]:
        """Discover all supported attributes for a category.

        Args:
            category: Category to query ('policies', 'profiles', 'templates')
            max_retries: Maximum retry attempts per endpoint

        Returns:
            Dict mapping object_type -> list of supported attributes
        """
        attributes_map = {}
        endpoints = self.SCHEMA_ENDPOINTS.get(category, [])

        for endpoint in endpoints:
            # Extract object type from endpoint
            object_type = endpoint.rsplit('/', 1)[0]  # e.g., 'bios' from 'bios/Policies'

            schema = self.query_schema(endpoint)
            if schema:
                attrs = self.extract_attributes(schema)
                attributes_map[object_type] = attrs
            else:
                # Retry or use empty list
                attributes_map[object_type] = []

        return attributes_map

    def compare_environments(self, saas_attrs: Dict[str, List[str]],
                             target_attrs: Dict[str, List[str]]
                             ) -> Dict[str, Dict[str, Any]]:
        """Compare attributes between SaaS and target environment.

        Args:
            saas_attrs: Attributes supported in SaaS
            target_attrs: Attributes supported in target environment (CVA/PVA)

        Returns:
            Dict of object_type -> {'supported': [...], 'missing': [...], 'match_ratio': 0.0}
        """
        comparison = {}

        for obj_type, target_list in target_attrs.items():
            saas_list = saas_attrs.get(obj_type, [])

            supported = target_list
            missing = [attr for attr in saas_list if attr not in target_list]

            # Calculate match ratio
            if saas_list:
                match_ratio = len(supported) / len(saas_list) * 100
            else:
                match_ratio = 100.0

            comparison[obj_type] = {
                'supported_count': len(supported),
                'saas_count': len(saas_list),
                'missing_count': len(missing),
                'match_ratio': round(match_ratio, 2),
                'missing_attributes': sorted(missing),
                'supported_attributes': sorted(supported)
            }

        return comparison


class SchemaAnalyzer:
    """Analyze and report on schema differences."""

    @staticmethod
    def generate_report(comparison: Dict[str, Dict[str, Any]]) -> str:
        """Generate human-readable comparison report.

        Args:
            comparison: Comparison dict from SchemaDiscovery.compare_environments

        Returns:
            Formatted report string
        """
        lines = [
            "=" * 80,
            "SCHEMA ATTRIBUTE COMPARISON REPORT",
            "=" * 80,
            ""
        ]

        # Sort by match ratio (lowest first)
        sorted_types = sorted(
            comparison.items(),
            key=lambda x: x[1]['match_ratio']
        )

        total_types = len(sorted_types)
        perfect_match = sum(1 for item in sorted_types if item[1]['match_ratio'] == 100)

        lines.append(f"Total Object Types: {total_types}")
        lines.append(f"Perfect Match (100%): {perfect_match}")
        lines.append("")

        for obj_type, stats in sorted_types:
            if stats['match_ratio'] < 100:
                lines.append(f"{obj_type}:")
                lines.append(f"  Match Ratio: {stats['match_ratio']}% "
                             f"({stats['supported_count']}/{stats['saas_count']} attributes)")
                lines.append(f"  Missing {stats['missing_count']} attributes:")

                # Show missing attributes in chunks
                missing = stats['missing_attributes']
                for i in range(0, len(missing), 5):
                    chunk = ', '.join(missing[i:i + 5])
                    lines.append(f"    - {chunk}")
                lines.append("")

        lines.append("=" * 80)
        return "\n".join(lines)
