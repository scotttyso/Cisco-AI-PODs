#!/usr/bin/env python3
"""
DNS Validator - Pre-Installation DNS Verification
Validates DNS records for OpenShift installation
Tests hostname resolution, API endpoint, and wildcard DNS before cluster deployment
"""

import dns.resolver
import dns.rdatatype
import socket
import logging
from typing import Dict, List, Tuple, Set
from dataclasses import dataclass
from pathlib import Path
import yaml
import json
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class DNSTestResult:
    """Result of a single DNS test"""
    hostname: str
    test_type: str  # 'A_RECORD', 'CNAME', 'WILDCARD', 'REVERSE', 'CONNECTIVITY'
    expected_value: str
    actual_value: str
    status: str  # 'PASS', 'FAIL', 'WARNING', 'SKIP'
    message: str
    timestamp: str = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class DNSValidator:
    """Validates DNS configuration for OpenShift installation"""

    def __init__(self, nameserver: str = None, logger_instance=None):
        """
        Initialize DNS validator
        
        Args:
            nameserver: Optional specific nameserver to query (e.g., '8.8.8.8')
            logger_instance: Optional logger instance
        """
        self.nameserver = nameserver
        self.logger = logger_instance or logging.getLogger(__name__)
        self.test_results: List[DNSTestResult] = []
        
        # Setup DNS resolver
        if nameserver:
            self.resolver = dns.resolver.Resolver()
            self.resolver.nameservers = [nameserver]
        else:
            self.resolver = dns.resolver.Resolver()

    def test_a_record(self, hostname: str, expected_ip: str = None) -> DNSTestResult:
        """
        Test if hostname resolves to expected A record
        
        Args:
            hostname: Hostname to test (e.g., 'ocp-master-1.example.com')
            expected_ip: Expected IP address (optional)
        
        Returns:
            DNSTestResult with test outcome
        """
        try:
            answers = self.resolver.resolve(hostname, 'A')
            actual_ip = str(answers[0])
            
            if expected_ip:
                if actual_ip == expected_ip:
                    result = DNSTestResult(
                        hostname=hostname,
                        test_type='A_RECORD',
                        expected_value=expected_ip,
                        actual_value=actual_ip,
                        status='PASS',
                        message=f'✓ {hostname} resolves to {actual_ip}'
                    )
                else:
                    result = DNSTestResult(
                        hostname=hostname,
                        test_type='A_RECORD',
                        expected_value=expected_ip,
                        actual_value=actual_ip,
                        status='FAIL',
                        message=f'✗ {hostname} resolves to {actual_ip}, expected {expected_ip}'
                    )
            else:
                result = DNSTestResult(
                    hostname=hostname,
                    test_type='A_RECORD',
                    expected_value='any',
                    actual_value=actual_ip,
                    status='PASS',
                    message=f'✓ {hostname} resolves to {actual_ip}'
                )
            
            self.test_results.append(result)
            self.logger.info(result.message)
            return result
        
        except dns.resolver.NXDOMAIN:
            result = DNSTestResult(
                hostname=hostname,
                test_type='A_RECORD',
                expected_value=expected_ip or 'any',
                actual_value='NXDOMAIN',
                status='FAIL',
                message=f'✗ {hostname} not found in DNS (NXDOMAIN)'
            )
            self.test_results.append(result)
            self.logger.error(result.message)
            return result
        
        except dns.resolver.NoNameservers:
            result = DNSTestResult(
                hostname=hostname,
                test_type='A_RECORD',
                expected_value=expected_ip or 'any',
                actual_value='NO_NAMESERVERS',
                status='FAIL',
                message=f'✗ No nameservers available for {hostname}'
            )
            self.test_results.append(result)
            self.logger.error(result.message)
            return result
        
        except Exception as e:
            result = DNSTestResult(
                hostname=hostname,
                test_type='A_RECORD',
                expected_value=expected_ip or 'any',
                actual_value='ERROR',
                status='FAIL',
                message=f'✗ Error resolving {hostname}: {str(e)}'
            )
            self.test_results.append(result)
            self.logger.error(result.message)
            return result

    def test_wildcard_dns(self, wildcard_domain: str, test_hostname: str = None) -> DNSTestResult:
        """
        Test wildcard DNS record (e.g., *.apps.example.com)
        
        Args:
            wildcard_domain: Wildcard domain pattern (e.g., 'apps.example.com')
            test_hostname: Optional specific hostname to test (e.g., 'test.apps.example.com')
        
        Returns:
            DNSTestResult with test outcome
        """
        if not test_hostname:
            test_hostname = f"test-wildcard.{wildcard_domain}"
        
        try:
            answers = self.resolver.resolve(test_hostname, 'A')
            actual_ip = str(answers[0])
            
            result = DNSTestResult(
                hostname=wildcard_domain,
                test_type='WILDCARD',
                expected_value=f'*.{wildcard_domain}',
                actual_value=actual_ip,
                status='PASS',
                message=f'✓ Wildcard DNS *.{wildcard_domain} resolves to {actual_ip}'
            )
            self.test_results.append(result)
            self.logger.info(result.message)
            return result
        
        except dns.resolver.NXDOMAIN:
            result = DNSTestResult(
                hostname=wildcard_domain,
                test_type='WILDCARD',
                expected_value=f'*.{wildcard_domain}',
                actual_value='NXDOMAIN',
                status='FAIL',
                message=f'✗ Wildcard DNS *.{wildcard_domain} not configured'
            )
            self.test_results.append(result)
            self.logger.error(result.message)
            return result
        
        except Exception as e:
            result = DNSTestResult(
                hostname=wildcard_domain,
                test_type='WILDCARD',
                expected_value=f'*.{wildcard_domain}',
                actual_value='ERROR',
                status='FAIL',
                message=f'✗ Error testing wildcard {wildcard_domain}: {str(e)}'
            )
            self.test_results.append(result)
            self.logger.error(result.message)
            return result

    def test_api_endpoint(self, api_hostname: str, expected_ip: str = None) -> DNSTestResult:
        """
        Test API endpoint (e.g., api.prod.example.com or api-int.prod.example.com)
        
        Args:
            api_hostname: API hostname
            expected_ip: Expected IP address
        
        Returns:
            DNSTestResult with test outcome
        """
        try:
            answers = self.resolver.resolve(api_hostname, 'A')
            actual_ip = str(answers[0])
            
            if expected_ip:
                if actual_ip == expected_ip:
                    status = 'PASS'
                    message = f'✓ API endpoint {api_hostname} resolves to {actual_ip}'
                else:
                    status = 'FAIL'
                    message = f'✗ API endpoint {api_hostname} resolves to {actual_ip}, expected {expected_ip}'
            else:
                status = 'PASS'
                message = f'✓ API endpoint {api_hostname} resolves to {actual_ip}'
            
            result = DNSTestResult(
                hostname=api_hostname,
                test_type='API_ENDPOINT',
                expected_value=expected_ip or 'any',
                actual_value=actual_ip,
                status=status,
                message=message
            )
            self.test_results.append(result)
            self.logger.info(result.message)
            return result
        
        except Exception as e:
            result = DNSTestResult(
                hostname=api_hostname,
                test_type='API_ENDPOINT',
                expected_value=expected_ip or 'any',
                actual_value='ERROR',
                status='FAIL',
                message=f'✗ Error resolving API endpoint {api_hostname}: {str(e)}'
            )
            self.test_results.append(result)
            self.logger.error(result.message)
            return result

    def test_connectivity(self, hostname: str, port: int = 443) -> DNSTestResult:
        """
        Test network connectivity to hostname:port
        
        Args:
            hostname: Hostname to connect to
            port: Port to test (default 443 for HTTPS)
        
        Returns:
            DNSTestResult with test outcome
        """
        try:
            ip = socket.gethostbyname(hostname)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result_code = sock.connect_ex((ip, port))
            sock.close()
            
            if result_code == 0:
                result = DNSTestResult(
                    hostname=hostname,
                    test_type='CONNECTIVITY',
                    expected_value=f'{hostname}:{port}',
                    actual_value='OPEN',
                    status='PASS',
                    message=f'✓ Connectivity to {hostname}:{port} successful'
                )
            else:
                result = DNSTestResult(
                    hostname=hostname,
                    test_type='CONNECTIVITY',
                    expected_value=f'{hostname}:{port}',
                    actual_value='CLOSED',
                    status='WARNING',
                    message=f'⚠ Port {port} closed on {hostname} (may be expected pre-install)'
                )
            
            self.test_results.append(result)
            self.logger.info(result.message)
            return result
        
        except socket.gaierror as e:
            result = DNSTestResult(
                hostname=hostname,
                test_type='CONNECTIVITY',
                expected_value=f'{hostname}:{port}',
                actual_value='RESOLUTION_ERROR',
                status='FAIL',
                message=f'✗ Failed to resolve {hostname}: {str(e)}'
            )
            self.test_results.append(result)
            self.logger.error(result.message)
            return result
        
        except Exception as e:
            result = DNSTestResult(
                hostname=hostname,
                test_type='CONNECTIVITY',
                expected_value=f'{hostname}:{port}',
                actual_value='ERROR',
                status='FAIL',
                message=f'✗ Connectivity test failed: {str(e)}'
            )
            self.test_results.append(result)
            self.logger.error(result.message)
            return result

    def test_reverse_dns(self, ip_address: str, expected_hostname: str = None) -> DNSTestResult:
        """
        Test reverse DNS (PTR record)
        
        Args:
            ip_address: IP address to reverse lookup
            expected_hostname: Expected hostname (optional)
        
        Returns:
            DNSTestResult with test outcome
        """
        try:
            answers = self.resolver.resolve(dns.reversename.from_address(ip_address), 'PTR')
            actual_hostname = str(answers[0]).rstrip('.')
            
            if expected_hostname:
                if actual_hostname == expected_hostname:
                    result = DNSTestResult(
                        hostname=ip_address,
                        test_type='REVERSE',
                        expected_value=expected_hostname,
                        actual_value=actual_hostname,
                        status='PASS',
                        message=f'✓ Reverse DNS {ip_address} -> {actual_hostname}'
                    )
                else:
                    result = DNSTestResult(
                        hostname=ip_address,
                        test_type='REVERSE',
                        expected_value=expected_hostname,
                        actual_value=actual_hostname,
                        status='FAIL',
                        message=f'✗ Reverse DNS mismatch: {ip_address} -> {actual_hostname}, expected {expected_hostname}'
                    )
            else:
                result = DNSTestResult(
                    hostname=ip_address,
                    test_type='REVERSE',
                    expected_value='any',
                    actual_value=actual_hostname,
                    status='PASS',
                    message=f'✓ Reverse DNS {ip_address} -> {actual_hostname}'
                )
            
            self.test_results.append(result)
            self.logger.info(result.message)
            return result
        
        except dns.resolver.NXDOMAIN:
            result = DNSTestResult(
                hostname=ip_address,
                test_type='REVERSE',
                expected_value=expected_hostname or 'any',
                actual_value='NXDOMAIN',
                status='WARNING',
                message=f'⚠ No reverse DNS record for {ip_address}'
            )
            self.test_results.append(result)
            self.logger.warning(result.message)
            return result
        
        except Exception as e:
            result = DNSTestResult(
                hostname=ip_address,
                test_type='REVERSE',
                expected_value=expected_hostname or 'any',
                actual_value='ERROR',
                status='FAIL',
                message=f'✗ Reverse DNS lookup failed: {str(e)}'
            )
            self.test_results.append(result)
            self.logger.error(result.message)
            return result

    def validate_openshift_cluster(self, cluster_name: str, domain: str, 
                                   master_ips: Dict[str, str] = None,
                                   worker_ips: Dict[str, str] = None,
                                   api_ip: str = None,
                                   api_int_ip: str = None) -> Dict:
        """
        Comprehensive OpenShift cluster DNS validation
        
        Args:
            cluster_name: Cluster name (e.g., 'prod')
            domain: Domain (e.g., 'example.com')
            master_ips: Dict of master hostnames and IPs
            worker_ips: Dict of worker hostnames and IPs
            api_ip: API endpoint IP
            api_int_ip: Internal API endpoint IP
        
        Returns:
            Dict with validation results
        """
        self.logger.info("=" * 80)
        self.logger.info(f"OpenShift Cluster DNS Validation: {cluster_name}.{domain}")
        self.logger.info("=" * 80)
        
        # Test control plane nodes
        self.logger.info("\n📍 Testing Control Plane (Master) Nodes:")
        if master_ips:
            for hostname, ip in master_ips.items():
                self.test_a_record(hostname, ip)
                self.test_reverse_dns(ip, hostname)
        
        # Test worker nodes
        self.logger.info("\n📍 Testing Worker Nodes:")
        if worker_ips:
            for hostname, ip in worker_ips.items():
                self.test_a_record(hostname, ip)
                self.test_reverse_dns(ip, hostname)
        
        # Test API endpoints
        self.logger.info("\n📍 Testing API Endpoints:")
        api_hostname = f"api.{cluster_name}.{domain}"
        api_int_hostname = f"api-int.{cluster_name}.{domain}"
        
        self.test_api_endpoint(api_hostname, api_ip)
        self.test_api_endpoint(api_int_hostname, api_int_ip)
        
        # Test wildcard DNS for apps
        self.logger.info("\n📍 Testing Wildcard DNS for Applications:")
        apps_domain = f"apps.{cluster_name}.{domain}"
        self.test_wildcard_dns(apps_domain)
        
        # Test connectivity
        self.logger.info("\n📍 Testing Network Connectivity:")
        self.test_connectivity(api_hostname)
        
        # Compile results
        passed = sum(1 for r in self.test_results if r.status == 'PASS')
        failed = sum(1 for r in self.test_results if r.status == 'FAIL')
        warnings = sum(1 for r in self.test_results if r.status == 'WARNING')
        
        summary = {
            'cluster': f"{cluster_name}.{domain}",
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_tests': len(self.test_results),
                'passed': passed,
                'failed': failed,
                'warnings': warnings,
                'ready_for_install': failed == 0
            },
            'results': [
                {
                    'hostname': r.hostname,
                    'test_type': r.test_type,
                    'status': r.status,
                    'expected': r.expected_value,
                    'actual': r.actual_value,
                    'message': r.message,
                    'timestamp': r.timestamp
                }
                for r in self.test_results
            ]
        }
        
        return summary

    def get_report(self) -> str:
        """Generate formatted report of all tests"""
        report = "\n" + "="*80 + "\n"
        report += "DNS VALIDATION REPORT\n"
        report += "="*80 + "\n\n"
        
        # Summary
        passed = sum(1 for r in self.test_results if r.status == 'PASS')
        failed = sum(1 for r in self.test_results if r.status == 'FAIL')
        warnings = sum(1 for r in self.test_results if r.status == 'WARNING')
        
        report += f"Summary: {len(self.test_results)} tests\n"
        report += f"  ✓ Passed:  {passed}\n"
        report += f"  ✗ Failed:  {failed}\n"
        report += f"  ⚠ Warnings: {warnings}\n\n"
        
        # Grouped by status
        report += "PASSED TESTS:\n"
        for r in sorted(self.test_results, key=lambda x: x.hostname):
            if r.status == 'PASS':
                report += f"  ✓ {r.hostname:40} - {r.message}\n"
        
        if failed > 0:
            report += "\nFAILED TESTS (Must fix before install):\n"
            for r in sorted(self.test_results, key=lambda x: x.hostname):
                if r.status == 'FAIL':
                    report += f"  ✗ {r.hostname:40} - {r.message}\n"
        
        if warnings > 0:
            report += "\nWARNINGS (Recommended to fix):\n"
            for r in sorted(self.test_results, key=lambda x: x.hostname):
                if r.status == 'WARNING':
                    report += f"  ⚠ {r.hostname:40} - {r.message}\n"
        
        report += "\n" + "="*80 + "\n"
        
        if failed == 0:
            report += "✓ All DNS records validated successfully!\n"
            report += "✓ OpenShift cluster is ready for installation.\n"
        else:
            report += "✗ DNS validation FAILED - fix errors before proceeding\n"
        
        report += "="*80 + "\n"
        
        return report


def validate_from_yaml(inventory_file: str, dns_server: str = None) -> Dict:
    """
    Validate DNS from inventory YAML file
    
    Args:
        inventory_file: Path to inventory YAML
        dns_server: Optional specific DNS server to query
    
    Returns:
        Validation results dict
    """
    try:
        with open(inventory_file) as f:
            inventory = yaml.safe_load(f)
        
        validator = DNSValidator(nameserver=dns_server)
        
        # Extract cluster details
        cluster_name = inventory.get('cluster', {}).get('name', 'prod')
        domain = inventory.get('cluster', {}).get('domain', 'example.com')
        
        # Extract node IPs
        master_ips = {}
        for node in inventory.get('control_plane_nodes', []):
            hostname = node.get('name')
            ip = node.get('ip')
            if hostname and ip:
                master_ips[hostname] = ip
        
        worker_ips = {}
        for node in inventory.get('worker_nodes', []):
            hostname = node.get('name')
            ip = node.get('ip')
            if hostname and ip:
                worker_ips[hostname] = ip
        
        # API endpoints
        api_config = inventory.get('api', {})
        api_ip = api_config.get('ip')
        api_int_ip = api_config.get('internal_ip')
        
        # Run validation
        results = validator.validate_openshift_cluster(
            cluster_name=cluster_name,
            domain=domain,
            master_ips=master_ips or None,
            worker_ips=worker_ips or None,
            api_ip=api_ip,
            api_int_ip=api_int_ip
        )
        
        # Print report
        print(validator.get_report())
        
        return results
    
    except Exception as e:
        logger.error(f"Error validating from YAML: {e}")
        return {
            'status': 'error',
            'message': str(e)
        }


if __name__ == '__main__':
    import sys
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if len(sys.argv) > 1:
        # Validate from inventory file
        inventory_file = sys.argv[1]
        dns_server = sys.argv[2] if len(sys.argv) > 2 else None
        validate_from_yaml(inventory_file, dns_server)
    else:
        print("Usage: python3 dns_validator.py <inventory_file> [dns_server]")
        print("Example: python3 dns_validator.py openshift_inventory.yaml 8.8.8.8")
