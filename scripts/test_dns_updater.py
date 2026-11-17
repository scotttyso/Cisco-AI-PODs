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
        mock_yaml.return_value = {'openshift': {'install': {'bare_metal': {
            'base_dns_domain': 'example.com',
            'cluster_name': 'ai-pods',
            'cluster_networking': {'api': {'v4': '10.0.0.9'}, 'ingress': {'v4': '10.0.0.10'}},
            'servers': [{'hostname': 'node1', 'role': 'master',
                         'interfaces': {'ethernet': [{'name': 'eno1', 'ipv4': '10.0.0.11/24'}]}}],
        }}}}

        records = {(r.hostname, r.ip_address) for r in self.parser.parse_openshift("install.ezai.yaml")}

        self.assertEqual(records, {
            ('api.ai-pods.example.com', '10.0.0.9'),
            ('api-int.ai-pods.example.com', '10.0.0.9'),
            ('*.apps.ai-pods.example.com', '10.0.0.10'),
            ('node1.example.com', '10.0.0.11'),
            ('node1-eno1.example.com', '10.0.0.11'),
        })

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
        
        # A record whose address differs is both missing (desired) and stale (current), so apply replaces it
        self.assertEqual({r.hostname for r in missing}, {"test2.example.com", "test3.example.com"})
        self.assertEqual({r.hostname for r in stale}, {"test2.example.com", "old.example.com"})
        self.assertEqual({r.hostname for r in matching}, {"test1.example.com"})


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


class FakeLdap:
    """Just enough of an ldap3 connection to exercise the AD record writer"""

    def __init__(self, nodes=None):
        self.nodes = nodes or {}  # node dn -> list of dnsRecord blobs
        self.entries = []
        self.result = {'description': 'success', 'message': ''}
        self.calls = []

    def search(self, base, query, scope, attributes=None):
        label = query.split('(name=')[1].rstrip(')')
        dn = f"DC={label},{base}"
        self.entries = []
        if dn in self.nodes:
            entry = Mock(entry_dn=dn)
            entry.dnsRecord.raw_values = self.nodes[dn]
            entry.__contains__ = lambda self_, key: True
            self.entries = [entry]
        return bool(self.entries)

    def add(self, dn, classes, attributes):
        self.calls.append(('add', dn, attributes))
        self.nodes[dn] = list(attributes['dnsRecord'])
        return True

    def modify(self, dn, changes):
        self.calls.append(('modify', dn, changes))
        self.nodes[dn] = list(changes['dnsRecord'][0][1])
        return True


class TestActiveDirectoryWrites(unittest.TestCase):
    ZONE_DN = 'DC=aipod.local,CN=MicrosoftDNS,DC=DomainDnsZones,DC=aipod,DC=local'

    def provider(self, nodes=None):
        provider = ActiveDirectoryProvider({'server': 'dc'})
        provider.connection = FakeLdap(nodes)
        provider.zones = {'aipod.local': self.ZONE_DN}
        provider.serials = {'aipod.local': 7}
        return provider

    def test_a_record_blob_layout(self):
        blob = ActiveDirectoryProvider._a_blob('10.1.2.3', 3600, 7)
        self.assertEqual(blob[:2], b'\x04\x00')          # data length
        self.assertEqual(blob[2:4], b'\x01\x00')         # type A
        self.assertEqual(blob[4:6], bytes([5, 240]))      # version, zone rank
        self.assertEqual(blob[8:12], b'\x07\x00\x00\x00')  # serial
        self.assertEqual(blob[12:16], (3600).to_bytes(4, 'big'))
        self.assertEqual(blob[16:24], bytes(8))           # static record: no timestamp
        self.assertEqual(blob[24:], bytes([10, 1, 2, 3]))

    def test_zone_is_the_longest_matching_ad_zone(self):
        provider = self.provider()
        provider.zones['aid.aipod.local'] = 'x'
        self.assertEqual(provider._zone_of('api.aid.aipod.local'), 'aid.aipod.local')
        self.assertEqual(provider._zone_of('*.apps.aid.aipod.local'), 'aid.aipod.local')
        self.assertEqual(provider._zone_of('host.aipod.local'), 'aipod.local')
        self.assertIsNone(provider._zone_of('host.other.com'))

    def test_create_adds_a_new_node(self):
        provider = self.provider()
        self.assertTrue(provider.create_record(DNSRecord('node1.aipod.local', '10.1.2.3', 'aipod.local')))
        action, dn, attributes = provider.connection.calls[0]
        self.assertEqual((action, dn), ('add', f'DC=node1,{self.ZONE_DN}'))
        self.assertEqual(attributes['dnsRecord'][0][24:], bytes([10, 1, 2, 3]))

    def test_wildcard_node_keeps_its_dotted_name(self):
        provider = self.provider()
        provider.create_record(DNSRecord('*.apps.aipod.local', '10.1.2.4', 'aipod.local'))
        self.assertEqual(provider.connection.calls[0][1], f'DC=*.apps,{self.ZONE_DN}')

    def test_existing_address_is_left_alone(self):
        dn = f'DC=node1,{self.ZONE_DN}'
        provider = self.provider({dn: [ActiveDirectoryProvider._a_blob('10.1.2.3', 3600, 1)]})
        self.assertTrue(provider.create_record(DNSRecord('node1.aipod.local', '10.1.2.3', 'aipod.local')))
        self.assertEqual(provider.connection.calls, [])

    def test_different_address_is_replaced_and_other_records_kept(self):
        dn = f'DC=node1,{self.ZONE_DN}'
        txt = bytes([3, 0, 16, 0, 5, 240, 0, 0, 1, 0, 0, 0, 0, 0, 14, 16, 0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3])
        provider = self.provider({dn: [ActiveDirectoryProvider._a_blob('10.9.9.9', 3600, 1), txt]})
        self.assertTrue(provider.create_record(DNSRecord('node1.aipod.local', '10.1.2.3', 'aipod.local')))
        others, addresses = ActiveDirectoryProvider._split_blobs(provider.connection.nodes[dn])
        self.assertEqual(addresses, ['10.1.2.3'])
        self.assertEqual(others, [txt])

    def test_record_outside_ad_zones_fails_without_writing(self):
        provider = self.provider()
        self.assertFalse(provider.create_record(DNSRecord('host.other.com', '10.1.2.3', 'other.com')))
        self.assertEqual(provider.connection.calls, [])

    def test_stale_records_are_never_deleted(self):
        provider = self.provider()
        self.assertFalse(provider.deletes_stale)
        self.assertFalse(provider.delete_record(DNSRecord('node1.aipod.local', '10.9.9.9', 'aipod.local')))
        self.assertEqual(provider.connection.calls, [])


def run_tests():
    """Run all tests with verbose output"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test cases
    suite.addTests(loader.loadTestsFromTestCase(TestDNSRecord))
    suite.addTests(loader.loadTestsFromTestCase(TestInventoryParser))
    suite.addTests(loader.loadTestsFromTestCase(TestDNSComparator))
    suite.addTests(loader.loadTestsFromTestCase(TestActiveDirectoryProvider))
    suite.addTests(loader.loadTestsFromTestCase(TestActiveDirectoryWrites))
    suite.addTests(loader.loadTestsFromTestCase(TestInfobloxProvider))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestErrorHandling))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(run_tests())
