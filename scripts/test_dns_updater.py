"""
DNS Updater - Integration and Unit Tests
Tests the DNS updater functionality with various providers and inventory sources
"""

import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from dns_updater import (
    DNSRecord,
    extract_zone,
    DNSComparator,
    ActiveDirectoryProvider,
    InfobloxProvider,
    PtrPlan,
    PtrRecord,
    ZonePlan,
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


class TestExtractZone(unittest.TestCase):

    def test_extract_zone_from_fqdn(self):
        self.assertEqual(extract_zone("host.example.com"), "example.com")
        self.assertEqual(extract_zone("host.prod.example.com"), "prod.example.com")
        self.assertEqual(extract_zone("localhost"), "local")


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


class TestErrorHandling(unittest.TestCase):
    """Test error handling and edge cases"""

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


class FakeWinrmSession:
    def __init__(self, outputs=None, fail=None):
        self.scripts = []
        self.outputs = list(outputs or [])
        self.fail = fail

    def run_ps(self, script):
        self.scripts.append(script)
        if self.fail:
            return Mock(status_code=1, std_out=b'', std_err=self.fail)
        return Mock(status_code=0, std_out=self.outputs.pop(0) if self.outputs else b'CREATED', std_err=b'')


class TestActiveDirectoryWinrmFallback(unittest.TestCase):

    def provider(self, session=None, **config):
        provider = ActiveDirectoryProvider({'server': 'dc', 'domain': 'aipod.local', **config})
        provider.server = 'dc'
        provider.username = 'CN=Administrator,CN=Users,DC=aipod,DC=local'
        provider.password = 'secret'
        provider.writable = True
        provider.session = session
        provider.backend = 'winrm' if session else None
        provider.zones = {'aipod.local': 'aipod.local'}
        return provider

    def test_account_is_converted_from_the_bind_dn(self):
        self.assertEqual(self.provider()._winrm_account(), 'Administrator@aipod.local')
        provider = self.provider()
        provider.username = 'svc@aipod.local'
        self.assertEqual(provider._winrm_account(), 'svc@aipod.local')

    def test_falls_back_to_winrm_when_ldap_fails(self):
        provider = self.provider()
        session = FakeWinrmSession([b'"aipod.local"'])
        fake_winrm = Mock()
        fake_winrm.Session.return_value = session
        with patch.object(provider, '_load_zones_ldap', side_effect=RuntimeError('strongerAuthRequired')), \
                patch.dict(sys.modules, {'winrm': fake_winrm}):
            provider._load_zones()
        self.assertEqual(provider.backend, 'winrm')
        self.assertEqual(provider.zones, {'aipod.local': 'aipod.local'})
        self.assertEqual(fake_winrm.Session.call_args.kwargs['transport'], 'ntlm')
        self.assertEqual(fake_winrm.Session.call_args.args[0], 'http://dc:5985/wsman')
        self.assertEqual(fake_winrm.Session.call_args.kwargs['auth'], ('Administrator@aipod.local', 'secret'))

    def test_validate_does_not_use_winrm(self):
        provider = self.provider()
        provider.writable = False
        with patch.object(provider, '_load_zones_ldap', side_effect=RuntimeError('down')), \
                patch.object(provider, '_load_zones_winrm') as winrm:
            provider._load_zones()
        winrm.assert_not_called()

    def test_both_failures_are_reported(self):
        provider = self.provider()
        with patch.object(provider, '_load_zones_ldap', side_effect=RuntimeError('ldap down')), \
                patch.object(provider, '_load_zones_winrm', side_effect=RuntimeError('winrm down')):
            with self.assertRaises(RuntimeError) as raised:
                provider._load_zones()
        self.assertIn('ldap down', str(raised.exception))
        self.assertIn('winrm down', str(raised.exception))

    def test_create_runs_a_script_for_the_right_zone_and_name(self):
        session = FakeWinrmSession([b'CREATED'])
        provider = self.provider(session)
        self.assertTrue(provider.create_record(DNSRecord('*.apps.aipod.local', '10.1.2.3', 'aipod.local')))
        script = session.scripts[0]
        self.assertIn("$zone = 'aipod.local'", script)
        self.assertIn("$name = '*.apps'", script)
        self.assertIn("$ip = '10.1.2.3'", script)
        self.assertNotIn('secret', script)

    def test_unchanged_and_replaced_are_success(self):
        for output in (b'UNCHANGED', b'REPLACED 10.9.9.9'):
            provider = self.provider(FakeWinrmSession([output]))
            self.assertTrue(provider.create_record(DNSRecord('a.aipod.local', '10.1.2.3', 'aipod.local')))

    def test_powershell_failure_is_a_failed_record(self):
        provider = self.provider(FakeWinrmSession(fail=b'Access is denied'))
        self.assertFalse(provider.create_record(DNSRecord('a.aipod.local', '10.1.2.3', 'aipod.local')))

    def test_unexpected_names_are_refused_before_any_command(self):
        session = FakeWinrmSession()
        provider = self.provider(session)
        self.assertFalse(provider.create_record(DNSRecord("a';calc;'.aipod.local", '10.1.2.3', 'aipod.local')))
        self.assertEqual(session.scripts, [])

    def test_names_are_quoted_for_powershell(self):
        self.assertEqual(ActiveDirectoryProvider._ps_quote("it's"), "'it''s'")


class TestVerifyAfterWrite(unittest.TestCase):
    """Synchronize waits for the DNS server to load what it wrote"""

    def apply(self, visible_after, needs_settle=True):
        from dns_updater import DNSUpdater

        record = DNSRecord('api.example.com', '10.0.0.1', 'example.com')
        calls = {'count': 0}

        class Provider:
            deletes_stale = False

            def create_record(self, item):
                return True

            def get_records(self, zone):
                calls['count'] += 1
                return {record} if calls['count'] >= visible_after else set()

        provider = Provider()
        provider.needs_settle = needs_settle
        updater = DNSUpdater('unused.yaml')
        updater.VERIFY_INTERVAL = 0
        with patch('dns_updater.time.sleep'):
            updater._apply_changes(provider, {record}, set())
        return calls['count']

    def test_stops_waiting_as_soon_as_records_resolve(self):
        self.assertEqual(self.apply(visible_after=2), 2)

    def test_fails_when_records_never_resolve(self):
        with self.assertRaises(SystemExit) as raised:
            self.apply(visible_after=99)
        self.assertEqual(raised.exception.code, 1)

    def test_providers_that_apply_immediately_are_not_polled(self):
        self.assertEqual(self.apply(visible_after=1, needs_settle=False), 0)

    def test_only_ldap_writes_need_to_settle(self):
        provider = ActiveDirectoryProvider({'server': 'dc'})
        provider.backend = 'ldap'
        self.assertTrue(provider.needs_settle)
        provider.backend = 'winrm'
        self.assertFalse(provider.needs_settle)


class TestPointerRecordsAndZones(unittest.TestCase):
    """PTR records, and the forward and reverse zones that are created for them"""

    ZONE_DN = 'DC=aipod.local,CN=MicrosoftDNS,DC=DomainDnsZones,DC=aipod,DC=local'
    REVERSE_DN = 'DC=2.18.198.in-addr.arpa,CN=MicrosoftDNS,DC=DomainDnsZones,DC=aipod,DC=local'

    def provider(self, nodes=None, session=None, **config):
        provider = ActiveDirectoryProvider({'server': 'dc', 'domain': 'aipod.local', **config})
        provider.server = 'dc'
        provider.backend = 'ldap'
        provider.connection = FakeLdap(nodes)
        provider.zones = {'aipod.local': self.ZONE_DN}
        provider.reverse_zones = {'2.18.198.in-addr.arpa': self.REVERSE_DN}
        provider.serials = {'2.18.198.in-addr.arpa': 5}
        provider.session = session
        return provider

    @staticmethod
    def records(*pairs):
        return {DNSRecord(host, address, 'aipod.local') for host, address in pairs}

    def test_ptr_blob_is_a_valid_record_with_the_target_name(self):
        import struct
        import dns.name

        blob = ActiveDirectoryProvider._ptr_blob('node1.aipod.local.', 3600, 5)
        length, record_type, version, rank, _flags, serial = struct.unpack_from('<HHBBHI', blob)
        self.assertEqual((record_type, version, rank, serial), (12, 5, 240, 5))
        self.assertEqual(length, len(blob) - 24)
        self.assertEqual(struct.unpack_from('>I', blob, 12)[0], 3600)
        size, labels = blob[24], blob[25]
        self.assertEqual((size, labels), (len(blob) - 26, 3))
        self.assertEqual(dns.name.from_wire(blob[26:], 0)[0].to_text(), 'node1.aipod.local.')
        others, targets = ActiveDirectoryProvider._split_ptr_blobs([blob, b'x' * 28])
        self.assertEqual((targets, len(others)), (['node1.aipod.local'], 1))

    def test_reverse_zone_uses_the_most_specific_existing_zone_else_the_configured_size(self):
        provider = self.provider()
        provider.reverse_zones['18.198.in-addr.arpa'] = 'x'
        self.assertEqual(provider._reverse_zone_for('198.18.2.7'), '2.18.198.in-addr.arpa')
        self.assertEqual(provider._reverse_zone_for('198.18.9.7'), '18.198.in-addr.arpa')
        self.assertEqual(provider._reverse_zone_for('10.1.2.3'), '2.1.10.in-addr.arpa')
        self.assertEqual(self.provider(reverse_zone_prefix=16)._reverse_zone_for('10.1.2.3'), '1.10.in-addr.arpa')
        self.assertEqual(self.provider()._network_id('10.1.2.3'), '10.1.2.0/24')
        with self.assertRaises(ValueError):
            self.provider(reverse_zone_prefix=20)._reverse_zone_for('10.1.2.3')

    def test_ptr_plan_picks_one_name_per_address_and_skips_wildcards(self):
        provider = self.provider()
        answers = {'198.18.2.1': ['node1.aipod.local'], '198.18.2.2': ['old.aipod.local'], '198.18.2.3': []}
        records = self.records(('node1.aipod.local', '198.18.2.1'), ('node2.aipod.local', '198.18.2.2'),
                               ('api.aipod.local', '198.18.2.3'), ('api-int.aipod.local', '198.18.2.3'),
                               ('*.apps.aipod.local', '198.18.2.3'))
        with patch.object(provider, 'existing_ptr_targets', side_effect=lambda ip: answers[ip]):
            plan = provider.plan_ptr(records)
        self.assertEqual([p.ip_address for p in plan.matching], ['198.18.2.1'])
        self.assertEqual([(p.ip_address, v) for p, v in plan.changed.items()], [('198.18.2.2', ['old.aipod.local'])])
        self.assertEqual([(p.ip_address, p.target, p.label) for p in plan.missing],
                         [('198.18.2.3', 'api.aipod.local.', '3')])
        self.assertTrue(any('api-int.aipod.local' in note for note in plan.notes))
        self.assertTrue(any('wildcard' in note for note in plan.notes))

    def test_zones_are_planned_for_hosts_and_addresses_without_one(self):
        provider = self.provider()
        records = self.records(('node1.aipod.local', '198.18.2.1'), ('a.rich.example.com', '10.1.2.3'),
                               ('b.rich.example.com', '10.1.2.4'), ('*.apps.rich.example.com', '10.1.2.5'))
        ptr = PtrPlan(missing=[PtrRecord('198.18.2.1', 'n.', '2.18.198.in-addr.arpa', '1'),
                               PtrRecord('10.1.2.3', 'a.', '2.1.10.in-addr.arpa', '3'),
                               PtrRecord('10.1.2.4', 'b.', '2.1.10.in-addr.arpa', '4')])
        plans = provider.plan_zones(records, ptr)
        self.assertEqual([(p.name, p.reverse, p.network_id) for p in plans],
                         [('rich.example.com', False, ''), ('2.1.10.in-addr.arpa', True, '10.1.2.0/24')])
        self.assertEqual(self.provider(create_zones=False).plan_zones(records, ptr), [])

    def test_forward_zone_candidate_prefers_the_domain(self):
        provider = self.provider()
        self.assertEqual(provider._forward_zone_candidate('x.y.aipod.local'), 'aipod.local')
        self.assertEqual(provider._forward_zone_candidate('host.other.net'), 'other.net')
        self.assertEqual(provider._forward_zone_candidate('*.apps.other.net'), 'apps.other.net')

    def test_zones_are_created_through_winrm_and_reloaded(self):
        session = FakeWinrmSession([b'CREATED', b'EXISTS'])
        provider = self.provider(session=session)
        plans = [ZonePlan('rich.example.com'), ZonePlan('2.1.10.in-addr.arpa', True, '10.1.2.0/24')]
        with patch.object(provider, '_load_zones_ldap') as reload:
            created, failed = provider.create_zones(plans)
        self.assertEqual((len(created), failed), (2, []))
        self.assertIn("Add-DnsServerPrimaryZone -Name 'rich.example.com' -ReplicationScope 'Domain'",
                      session.scripts[0])
        self.assertIn("-NetworkId '10.1.2.0/24'", session.scripts[1])
        self.assertIn('-DynamicUpdate Secure', session.scripts[0])
        reload.assert_called_once()

    def test_zone_creation_without_winrm_explains_how_to_do_it_by_hand(self):
        provider = self.provider()
        with patch.object(provider, '_open_winrm', side_effect=RuntimeError('connection refused')):
            created, failed = provider.create_zones([ZonePlan('rich.example.com')])
        self.assertEqual(created, [])
        self.assertIn("Add-DnsServerPrimaryZone -Name 'rich.example.com'", failed[0][1])
        self.assertIn('connection refused', failed[0][1])

    def test_a_bad_replication_scope_is_rejected(self):
        created, failed = self.provider(zone_replication_scope='Everything').create_zones([ZonePlan('a.b')])
        self.assertEqual((created, len(failed)), ([], 1))

    def test_ptr_is_added_over_ldap(self):
        provider = self.provider()
        ptr = PtrRecord('198.18.2.1', 'node1.aipod.local.', '2.18.198.in-addr.arpa', '1')
        self.assertTrue(provider.create_ptr(ptr))
        action, dn, attributes = provider.connection.calls[0]
        self.assertEqual((action, dn), ('add', f'DC=1,{self.REVERSE_DN}'))
        self.assertEqual(provider._split_ptr_blobs(attributes['dnsRecord'])[1], ['node1.aipod.local'])

    def test_ptr_replaces_only_the_ptr_and_keeps_other_records(self):
        node = f'DC=1,{self.REVERSE_DN}'
        keep = ActiveDirectoryProvider._a_blob('10.0.0.1', 60, 1)
        old = ActiveDirectoryProvider._ptr_blob('old.aipod.local.', 3600, 1)
        provider = self.provider(nodes={node: [keep, old]})
        ptr = PtrRecord('198.18.2.1', 'node1.aipod.local.', '2.18.198.in-addr.arpa', '1')
        self.assertTrue(provider.create_ptr(ptr))
        others, targets = provider._split_ptr_blobs(provider.connection.nodes[node])
        self.assertEqual((others, targets), ([keep], ['node1.aipod.local']))
        calls = len(provider.connection.calls)
        self.assertTrue(provider.create_ptr(ptr))  # already correct: nothing is written
        self.assertEqual(len(provider.connection.calls), calls)

    def test_ptr_fails_when_the_reverse_zone_is_missing(self):
        provider = self.provider()
        provider.reverse_zones = {}
        ptr = PtrRecord('198.18.2.1', 'node1.aipod.local.', '2.18.198.in-addr.arpa', '1')
        self.assertFalse(provider.create_ptr(ptr))

    def test_ptr_over_winrm_is_quoted_and_validated(self):
        session = FakeWinrmSession([b'CREATED'])
        provider = self.provider(session=session)
        provider.backend = 'winrm'
        self.assertTrue(provider.create_ptr(PtrRecord('198.18.2.1', 'node1.aipod.local.', '2.18.198.in-addr.arpa', '1')))
        self.assertIn("-RRType PTR", session.scripts[0])
        self.assertIn("$target = 'node1.aipod.local.'", session.scripts[0])
        self.assertFalse(provider.create_ptr(PtrRecord('198.18.2.1', "x';calc;'.", '2.18.198.in-addr.arpa', '1')))
        self.assertEqual(len(session.scripts), 1)

    def test_sync_creates_zones_then_records_then_pointers_and_verifies(self):
        from dns_updater import DNSUpdater

        order = []
        record = DNSRecord('a.rich.example.com', '10.1.2.3', 'rich.example.com')
        ptr = PtrRecord('10.1.2.3', 'a.rich.example.com.', '2.1.10.in-addr.arpa', '3')

        class Provider:
            needs_settle = True
            deletes_stale = False

            def normalize(self, records):
                return records

            def create_zones(self, plans):
                order.append('zones')
                return list(plans), []

            def create_record(self, rec):
                order.append('a')
                return True

            def create_ptr(self, item):
                order.append('ptr')
                return True

            def get_records(self, zone):
                return {record}

            def ptr_resolves(self, item):
                return True

        updater = DNSUpdater('unused.yaml')
        updater.VERIFY_INTERVAL = 0
        with patch('dns_updater.time.sleep'):
            updater._apply_changes(Provider(), {record}, set(), PtrPlan(missing=[ptr]),
                                   [ZonePlan('rich.example.com')])
        self.assertEqual(order, ['zones', 'a', 'ptr'])

    def test_sync_fails_when_a_zone_cannot_be_created(self):
        from dns_updater import DNSUpdater

        class Provider:
            needs_settle = False
            deletes_stale = False

            def normalize(self, records):
                return records

            def create_zones(self, plans):
                return [], [(plans[0], 'no WinRM')]

        with self.assertRaises(SystemExit):
            DNSUpdater('unused.yaml')._apply_changes(Provider(), set(), set(), None, [ZonePlan('x.example.com')])


class TestCheckMode(unittest.TestCase):
    """--check turns a dry run into a pass/fail gate"""

    def run_check(self, found):
        import tempfile
        import yaml
        from dns_updater import DNSUpdater

        config = {'dns': {'providers': {'ad': {'type': 'active_directory', 'server': 'dc'}},
                          'records': [{'hostname': 'api.example.com', 'ipv4': '10.0.0.1'}]}}
        with tempfile.NamedTemporaryFile('w', suffix='.yaml') as handle:
            yaml.safe_dump(config, handle)
            handle.flush()
            with patch('dns_updater.ActiveDirectoryProvider.get_records', return_value=found):
                updater = DNSUpdater(handle.name, dry_run=True, check=True)
                updater.run('ad')

    def test_passes_when_every_record_resolves(self):
        self.run_check({DNSRecord('api.example.com', '10.0.0.1', 'example.com')})

    def test_fails_when_a_record_is_missing(self):
        with self.assertRaises(SystemExit) as raised:
            self.run_check(set())
        self.assertEqual(raised.exception.code, 1)

    def test_fails_when_a_record_has_another_address(self):
        with self.assertRaises(SystemExit):
            self.run_check({DNSRecord('api.example.com', '10.9.9.9', 'example.com')})


def run_tests():
    """Run all tests with verbose output"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test cases
    suite.addTests(loader.loadTestsFromTestCase(TestDNSRecord))
    suite.addTests(loader.loadTestsFromTestCase(TestExtractZone))
    suite.addTests(loader.loadTestsFromTestCase(TestDNSComparator))
    suite.addTests(loader.loadTestsFromTestCase(TestActiveDirectoryProvider))
    suite.addTests(loader.loadTestsFromTestCase(TestActiveDirectoryWrites))
    suite.addTests(loader.loadTestsFromTestCase(TestActiveDirectoryWinrmFallback))
    suite.addTests(loader.loadTestsFromTestCase(TestVerifyAfterWrite))
    suite.addTests(loader.loadTestsFromTestCase(TestCheckMode))
    suite.addTests(loader.loadTestsFromTestCase(TestInfobloxProvider))
    suite.addTests(loader.loadTestsFromTestCase(TestErrorHandling))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(run_tests())
