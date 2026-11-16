#!/usr/bin/env python3
"""
DNS Updater - Integration and Unit Tests
Tests the DNS updater functionality with various providers and inventory sources
"""

import unittest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import sys
import os

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from dns_updater import (
    DNSRecord,
    InventoryParser,
    DNSComparator,
    ActiveDirectoryProvider,
    InfobloxProvider,
)


class TestDNSRecord(unittest.TestCase):
    """Test DNSRecord dataclass"""

    def test_dns_record_creation(self):
        record = DNSRecord(
            hostname="test.example.com",
            ip_address="192.168.1.1",
            zone="example.com"
        )
        self.assertEqual(record.hostname, "test.example.com")
        self.assertEqual(record.ip_address, "192.168.1.1")
        self.assertEqual(record.zone, "example.com")
        self.assertEqual(record.record_type, "A")

    def test_dns_record_equality(self):
        record1 = DNSRecord("test.example.com", "192.168.1.1", "example.com")
        record2 = DNSRecord("test.example.com", "192.168.1.1", "example.com")
        self.assertEqual(record1, record2)

    def test_dns_record_hash(self):
        record1 = DNSRecord("test.example.com", "192.168.1.1", "example.com")
        record2 = DNSRecord("test.example.com", "192.168.1.1", "example.com")
        # Should be able to add to set without duplicates
        record_set = {record1, record2}
        self.assertEqual(len(record_set), 1)


class TestInventoryParser(unittest.TestCase):
    """Test inventory parsing from various sources"""

    def setUp(self):
        self.parser = InventoryParser()

    def test_extract_zone_from_fqdn(self):
        self.assertEqual(
            InventoryParser._extract_zone("host.example.com"),
            "example.com"
        )
        self.assertEqual(
            InventoryParser._extract_zone("host.prod.example.com"),
            "prod.example.com"
        )
        self.assertEqual(
            InventoryParser._extract_zone("localhost"),
            "local"
        )

    @patch('builtins.open')
    @patch('yaml.safe_load')
    def test_parse_openshift_inventory(self, mock_yaml, mock_open):
        mock_yaml.return_value = {
            'nodes': [
                {'name': 'ocp-master-1.example.com', 'ip': '192.168.1.10'},
                {'name': 'ocp-worker-1.example.com', 'ip': '192.168.1.20'},
            ]
        }
        
        records = self.parser.parse_openshift("openshift.yaml")
        self.assertEqual(len(records), 2)

    @patch('builtins.open')
    @patch('yaml.safe_load')
    def test_parse_intersight_inventory(self, mock_yaml, mock_open):
        mock_yaml.return_value = {
            'servers': [
                {'hostname': 'pod-1.example.com', 'management_ip': '192.168.100.1'},
                {'hostname': 'pod-2.example.com', 'management_ip': '192.168.100.2'},
            ]
        }
        
        records = self.parser.parse_intersight("intersight.yaml")
        self.assertEqual(len(records), 2)

    @patch('builtins.open')
    @patch('yaml.safe_load')
    def test_parse_everpure_inventory(self, mock_yaml, mock_open):
        mock_yaml.return_value = {
            'devices': [
                {'hostname': 'switch-1.example.com', 'ip_address': '192.168.200.1'},
                {'hostname': 'switch-2.example.com', 'ip_address': '192.168.200.2'},
            ]
        }
        
        records = self.parser.parse_everpure("everpure.yaml")
        self.assertEqual(len(records), 2)


class TestDNSComparator(unittest.TestCase):
    """Test DNS record comparison logic"""

    def setUp(self):
        self.comparator = DNSComparator()

    def test_compare_identical_records(self):
        desired = {
            DNSRecord("test1.example.com", "192.168.1.1", "example.com"),
            DNSRecord("test2.example.com", "192.168.1.2", "example.com"),
        }
        actual = desired.copy()
        
        missing, stale, matching = self.comparator.compare(desired, actual)
        
        self.assertEqual(len(missing), 0)
        self.assertEqual(len(stale), 0)
        self.assertEqual(len(matching), 2)

    def test_compare_missing_records(self):
        desired = {
            DNSRecord("test1.example.com", "192.168.1.1", "example.com"),
            DNSRecord("test2.example.com", "192.168.1.2", "example.com"),
        }
        actual = {
            DNSRecord("test1.example.com", "192.168.1.1", "example.com"),
        }
        
        missing, stale, matching = self.comparator.compare(desired, actual)
        
        self.assertEqual(len(missing), 1)
        self.assertEqual(len(stale), 0)
        self.assertEqual(len(matching), 1)

    def test_compare_stale_records(self):
        desired = {
            DNSRecord("test1.example.com", "192.168.1.1", "example.com"),
        }
        actual = {
            DNSRecord("test1.example.com", "192.168.1.1", "example.com"),
            DNSRecord("old.example.com", "192.168.1.99", "example.com"),
        }
        
        missing, stale, matching = self.comparator.compare(desired, actual)
        
        self.assertEqual(len(missing), 0)
        self.assertEqual(len(stale), 1)
        self.assertEqual(len(matching), 1)

    def test_compare_mixed_scenario(self):
        desired = {
            DNSRecord("test1.example.com", "192.168.1.1", "example.com"),
            DNSRecord("test2.example.com", "192.168.1.2", "example.com"),
            DNSRecord("test3.example.com", "192.168.1.3", "example.com"),
        }
        actual = {
            DNSRecord("test1.example.com", "192.168.1.1", "example.com"),
            DNSRecord("test2.example.com", "192.168.1.99", "example.com"),  # Different IP
            DNSRecord("old.example.com", "192.168.1.50", "example.com"),
        }
        
        missing, stale, matching = self.comparator.compare(desired, actual)
        
        # test3 is missing, test2 differs in IP (not in missing because hostname matches)
        self.assertEqual(len(missing), 1)  # test3
        self.assertEqual(len(stale), 1)    # old.example.com
        self.assertEqual(len(matching), 1) # test1


class TestActiveDirectoryProvider(unittest.TestCase):
    """Test Active Directory provider"""

    def setUp(self):
        self.config = {
            'server': 'dc01.example.com',
            'username': 'admin',
            'password': 'password'
        }
        self.provider = ActiveDirectoryProvider(self.config)

    def test_provider_initialization(self):
        self.assertEqual(self.provider.config['server'], 'dc01.example.com')

    def test_authenticate(self):
        # Mock authentication
        try:
            self.provider.authenticate()
            # Should not raise an exception
        except Exception as e:
            self.fail(f"authenticate() raised {e}")

    def test_get_records_returns_set(self):
        records = self.provider.get_records("example.com")
        self.assertIsInstance(records, set)

    def test_create_record_returns_bool(self):
        record = DNSRecord("test.example.com", "192.168.1.1", "example.com")
        result = self.provider.create_record(record)
        self.assertIsInstance(result, bool)


class TestInfobloxProvider(unittest.TestCase):
    """Test Infoblox provider"""

    def setUp(self):
        self.config = {
            'host': 'infoblox.example.com',
            'username': 'admin',
            'password': 'infoblox_password'
        }
        self.provider = InfobloxProvider(self.config)

    def test_provider_initialization(self):
        self.assertEqual(self.provider.config['host'], 'infoblox.example.com')

    def test_authenticate(self):
        try:
            self.provider.authenticate()
        except Exception as e:
            self.fail(f"authenticate() raised {e}")


class TestIntegration(unittest.TestCase):
    """Integration tests for complete workflows"""

    @patch('dns_updater.InventoryParser.parse_all_sources')
    @patch('dns_updater.ActiveDirectoryProvider.get_records')
    def test_end_to_end_workflow(self, mock_get_records, mock_parse):
        # Setup mocks
        mock_parse.return_value = {
            DNSRecord("test1.example.com", "192.168.1.1", "example.com"),
            DNSRecord("test2.example.com", "192.168.1.2", "example.com"),
        }
        mock_get_records.return_value = {
            DNSRecord("test1.example.com", "192.168.1.1", "example.com"),
        }
        
        # Execute
        parser = InventoryParser()
        desired = parser.parse_all_sources({})
        
        provider = ActiveDirectoryProvider({'server': 'dc01.example.com'})
        actual = provider.get_records("example.com")
        
        comparator = DNSComparator()
        missing, stale, matching = comparator.compare(desired, actual)
        
        # Verify
        self.assertEqual(len(desired), 2)
        self.assertEqual(len(actual), 1)
        self.assertEqual(len(missing), 1)
        self.assertEqual(len(stale), 0)
        self.assertEqual(len(matching), 1)


class TestErrorHandling(unittest.TestCase):
    """Test error handling and edge cases"""

    def test_parse_empty_inventory(self):
        parser = InventoryParser()
        with patch('builtins.open'):
            with patch('yaml.safe_load', return_value=None):
                records = parser.parse_openshift("empty.yaml")
                self.assertEqual(len(records), 0)

    def test_dns_record_with_special_characters(self):
        record = DNSRecord(
            hostname="test-host_01.prod-example.com",
            ip_address="192.168.1.1",
            zone="prod-example.com"
        )
        self.assertEqual(record.hostname, "test-host_01.prod-example.com")

    def test_provider_without_vault_client(self):
        config = {'server': 'dc01.example.com'}
        provider = ActiveDirectoryProvider(config, vault_client=None)
        self.assertIsNone(provider.vault_client)


def run_tests():
    """Run all tests with verbose output"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test cases
    suite.addTests(loader.loadTestsFromTestCase(TestDNSRecord))
    suite.addTests(loader.loadTestsFromTestCase(TestInventoryParser))
    suite.addTests(loader.loadTestsFromTestCase(TestDNSComparator))
    suite.addTests(loader.loadTestsFromTestCase(TestActiveDirectoryProvider))
    suite.addTests(loader.loadTestsFromTestCase(TestInfobloxProvider))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestErrorHandling))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(run_tests())
