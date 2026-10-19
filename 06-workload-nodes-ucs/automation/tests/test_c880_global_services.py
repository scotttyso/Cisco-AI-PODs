"""Global-variable consequences, with every hardware/credential operation mocked."""
from datetime import datetime, timezone
import importlib
from pathlib import Path
import sys
from unittest.mock import patch

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
post = importlib.import_module('probe_c880_huu_postcheck')
configure = importlib.import_module('configure_c880_mgmt')
planner = importlib.import_module('plan_c880_deployment')


def globals_spec():
    return dict(domain_name='example.test', dns_servers=['192.0.2.53'],
                ntp_servers=['192.0.2.123'], timezone='Asia/Kolkata')


def inventory(tmp_path, data):
    (tmp_path / 'group_vars').mkdir(exist_ok=True)
    (tmp_path / 'group_vars/all.yml').write_text(yaml.safe_dump(data))
    return tmp_path


def test_reader_prefers_only_aipod_even_if_legacy_disagrees(tmp_path):
    expected = globals_spec()
    root = inventory(tmp_path, {'aipod': expected, 'aipod_spec': {'timezone': 'UTC'},
                              'ucs_management_services': {'domain_name': 'wrong.local'}})
    assert post._read_shared_spec(root) == expected


@pytest.mark.parametrize('data', [{}, {'aipod_spec': globals_spec()},
                                 {'ucs_management_services': globals_spec()}, {'aipod': []}])
def test_no_legacy_or_lab_fallback(tmp_path, data):
    with pytest.raises(ValueError):
        post._read_shared_spec(inventory(tmp_path, data))


@pytest.mark.parametrize('field,value', [('dns_servers', []), ('dns_servers', '192.0.2.53'),
    ('dns_servers', ['invalid']), ('ntp_servers', []), ('ntp_servers', '192.0.2.123'),
    ('domain_name', ''), ('timezone', 'invalid/zone')])
def test_invalid_globals_block_before_credentials_or_transport(tmp_path, field, value):
    spec = globals_spec(); spec[field] = value
    root = inventory(tmp_path, {'aipod': spec})
    with patch.object(configure, '_read_host_spec', return_value={'pass_ref':'FAKE'}), \
         patch.object(configure, '_read_vault_password', side_effect=AssertionError('no credential read')) as secret, \
         patch.object(configure, '_get_opener', side_effect=AssertionError('no transport')) as opener:
        with pytest.raises((ValueError, KeyError)):
            configure.configure_node(root, 'ucs-c880-3')
        secret.assert_not_called(); opener.assert_not_called()


@pytest.mark.parametrize('zone,instant,expected', [
    ('America/New_York', '2026-01-15T12:00:00+00:00', '-05:00'),
    ('America/New_York', '2026-07-15T12:00:00+00:00', '-04:00'),
    ('UTC', '2026-07-15T12:00:00+00:00', '+00:00'),
    ('Asia/Kolkata', '2026-07-15T12:00:00+00:00', '+05:30')])
def test_timezone_offset_follows_global_and_season(zone, instant, expected):
    assert post._timezone_offset(zone, datetime.fromisoformat(instant)) == expected


def test_configuration_payloads_use_globals_only(tmp_path):
    spec = globals_spec(); root = inventory(tmp_path, {'aipod': spec})
    (root / 'host_vars').mkdir()
    (root / 'host_vars/ucs-c880-3.yml').write_text('ucs:\n  hostname: HOST3\n')
    host = dict(ip='192.0.2.3', user='synthetic', pass_ref='FAKE')
    with patch.object(configure, '_read_host_spec', return_value=host), \
         patch.object(configure, '_read_vault_password', return_value='synthetic'), \
         patch.object(configure, '_get_opener', return_value=object()), \
         patch.object(configure, 'RedfishReader', return_value=lambda _: {}), \
         patch.object(configure, '_redfish_patch') as writer, \
         patch.object(configure, 'audit_settings_persistence', return_value={'all_passed':True}), \
         patch.object(configure.time, 'sleep'):
        configure.configure_node(root, 'ucs-c880-3', logger=lambda *a, **k: None)
    payloads = [c.args[3] for c in writer.call_args_list]
    assert payloads == [{'NTP': {'NTPServers':['192.0.2.123'], 'ProtocolEnabled':True}},
                        {'DateTimeLocalOffset':'+05:30'},
                        {'HostName':'HOST3','FQDN':'HOST3.example.test',
                         'StaticNameServers':['192.0.2.53','::']}]


def test_postcheck_rejects_wrong_season_offset_and_labels_scope():
    shared = globals_spec(); shared['timezone'] = 'America/New_York'
    host = dict(ip='192.0.2.3', netmask='255.255.255.0', gateway='192.0.2.1')
    resources = {
        '/redfish/v1/Managers/BMC/EthernetInterfaces/eth0': {'IPv4Addresses':[{'Address':host['ip'], 'SubnetMask':host['netmask'], 'Gateway':host['gateway']}]},
        '/redfish/v1/Managers/BMC/NetworkProtocol': {'NTP': {'NTPServers':shared['ntp_servers'], 'ProtocolEnabled':True}, 'SSH': {'ProtocolEnabled':True,'Port':22}},
        '/redfish/v1/Managers/BMC': {'DateTimeLocalOffset':'-04:00'}}
    instant = datetime(2026,1,15,tzinfo=timezone.utc)
    result = post.audit_settings_persistence(resources.__getitem__, host, shared, at=instant)
    assert not result['all_passed']
    assert result['details']['timezone_offset']['expected'] == '-05:00'
    assert result['details']['timezone_offset']['scope'] == 'current_offset_only'
    resources['/redfish/v1/Managers/BMC']['DateTimeLocalOffset'] = '-05:00'
    assert post.audit_settings_persistence(resources.__getitem__, host, shared, at=instant)['all_passed']


def test_planner_does_not_accept_legacy_only_globals(tmp_path):
    root = inventory(tmp_path, {'ucs_management_services': globals_spec()})
    (root/'host_vars').mkdir()
    (root/'host_vars/ucs-c880-3.yml').write_text('ucs: {}\n')
    checks = planner.build_plan(root)['hosts'][0]['inventory_checks']
    assert not checks['shared_dns_present'] and not checks['shared_ntp_present']
