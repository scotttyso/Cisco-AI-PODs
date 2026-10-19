"""Offline shared-site mapping, compatibility and deployment wiring checks."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from shared.lib.inventory import (InventoryError, _composed_from_ansible,
                                  inventory_from_merged_vars, resolve_nd_site_services)
from shared.lib.nd_setup import build_nd_setup_args
from shared.lib.nd_parity import compare_nd_baselines
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_inventory import CLUSTER, NODES


def services():
    return yaml.safe_load((ROOT / 'inventories/example/group_vars/all.yml').read_text())['aipod']


def spec():
    result = deepcopy(CLUSTER)
    for key in ('dns', 'ntp', 'timezone'):
        del result[key]
    return result


def test_resolution_is_pure_and_keeps_nonservice_fields():
    source, site = spec(), services()
    before = deepcopy((source, site))
    resolved = resolve_nd_site_services(source, site)
    assert (source, site) == before
    assert resolved['dns']['search_domains'] == ['example.com']
    assert resolved['ntp']['servers'] == [
        {'host': '198.51.100.124', 'preferred': True},
        {'host': '198.51.100.125', 'preferred': False},
    ]
    assert resolved['timezone'] == 'America/New_York'
    assert resolved['network'] == source['network']
    resolved['dns']['servers'].append('192.0.2.1')
    assert site == before[1]


def test_legacy_spec_remains_unchanged_without_global_vars():
    assert resolve_nd_site_services(CLUSTER) == CLUSTER


def test_legacy_optional_timezone_keeps_utc_default():
    cluster = deepcopy(CLUSTER)
    del cluster['timezone']
    inv = inventory_from_merged_vars(cluster, {}, 'admin', 'FAKE', NODES)
    assert inv.cluster.timezone == 'UTC'


def test_direct_merged_vars_adapter_resolves_shared_services():
    inv = inventory_from_merged_vars(spec(), {}, 'admin', 'FAKE', NODES, aipod=services())
    assert inv.cluster.dns.search_domains == ['example.com']
    with pytest.raises(InventoryError, match='missing aipod'):
        inventory_from_merged_vars(spec(), {}, 'admin', 'FAKE', NODES)


def test_global_values_are_not_restricted_to_nd_service_fields():
    site = services()
    site['other_subsystem_setting'] = 'unchanged'
    assert resolve_nd_site_services(spec(), site)['dns']['search_domains'] == ['example.com']


def test_example_cluster_contains_only_nd_specific_settings():
    cluster = yaml.safe_load((ROOT / 'inventories/example/group_vars/nd_cluster.yml').read_text())['nd_cluster_spec']
    assert set(cluster) == {'start_mode', 'name', 'implementation_type', 'iso', 'network',
                            'internal_networks', 'proxy', 'external_services'}


@pytest.mark.parametrize('field', ['dns', 'ntp', 'timezone'])
def test_local_override_fails_even_if_equal(field):
    cluster = spec()
    cluster[field] = resolve_nd_site_services(cluster, services())[field]
    with pytest.raises(InventoryError, match='local'):
        resolve_nd_site_services(cluster, services())


@pytest.mark.parametrize('site', [None, {}, {'unexpected': True}])
def test_missing_or_unknown_services_fail(site):
    with pytest.raises(InventoryError):
        resolve_nd_site_services(spec(), site)


@pytest.mark.parametrize('field,value', [
    ('dns_servers', []), ('dns_servers', ['bad-ip']),
    ('dns_servers', ['192.0.2.1', '192.0.2.1']),
    ('dns_search_domains', 'example.com'), ('dns_search_domains', ['bad domain']),
    ('dns_search_domains', ['example.com', 'example.com']),
    ('ntp_servers', ['192.0.2.1']),
    ('ntp_servers', ['192.0.2.1', '192.0.2.1']),
    ('ntp_preferred_server', '192.0.2.99'),
    ('timezone', 'not/a/timezone'), ('timezone', None),
    ('domain_name', '-bad.local'),
])
def test_invalid_service_values_fail(field, value):
    site = services()
    site[field] = value
    with pytest.raises(InventoryError):
        resolve_nd_site_services(spec(), site)


def test_search_domain_is_not_inferred_from_host_domain():
    site = services()
    site['domain_name'] = 'host.example.com'
    site['dns_search_domains'] = []
    resolved = resolve_nd_site_services(spec(), site)
    assert resolved['dns']['search_domains'] == []
    inv = inventory_from_merged_vars(resolved, {}, 'admin', 'FAKE_REF', NODES)
    artifact = {'nodes': {n['hostname']: {'cimc_ip': n['cimc']['ip'], 'serial_number': 'FAKE-' + n['hostname']} for n in NODES}}
    args = build_nd_setup_args(inv, artifact, admin_password='FAKE', resolve_cimc_password=lambda _: 'FAKE')
    assert 'dns_search_domain' not in args
    assert 'timezone' not in args
    assert 'domain_name' not in args


def test_plain_yaml_globals_have_one_service_source():
    data = yaml.safe_load((ROOT / 'inventories/example/group_vars/all.yml').read_text())
    assert 'ucs_management_services' not in data
    assert data['aipod'] == {
        'domain_name': 'example.com',
        'dns_servers': ['192.0.2.53', '192.0.2.54'],
        'dns_search_domains': ['example.com'],
        'ntp_servers': ['198.51.100.124', '198.51.100.125'],
        'ntp_preferred_server': '198.51.100.124',
        'timezone': 'America/New_York',
    }
    assert data['ucs_c880'] == {'sol_enabled': True}


def test_python_adapter_rejects_host_service_disagreement():
    variables = {'nd_cluster_spec': spec(), 'aipod': services(),
                 'nd_admin_username': 'admin', 'nd_admin_pass_ref': 'FAKE', 'nd_runtime': {}}
    hostvars = {node['hostname']: dict(deepcopy(variables), nd_node=node) for node in NODES}
    payload = {'nd_cluster': {'hosts': list(hostvars)}, '_meta': {'hostvars': hostvars}}
    assert _composed_from_ansible(payload)['cluster'] == resolve_nd_site_services(spec(), services())
    hostvars['ND-2']['aipod']['dns_search_domains'] = ['different.example.com']
    with pytest.raises(InventoryError, match='differs between hosts'):
        _composed_from_ansible(payload)


def test_role_filter_and_cli_share_the_mapper():
    filename = ROOT / '01-nd-cluster/automation/roles/nd_cluster/filter_plugins/nd_setup.py'
    module_spec = importlib.util.spec_from_file_location('nd_role_filters', filename)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    assert module.FilterModule().filters()['aipod_nd_cluster_spec'] is resolve_nd_site_services


def test_every_deployment_and_capture_cluster_input_is_resolved():
    for filename in ['01_nd_cluster.yml', 'capture_nd_baseline.yml']:
        plays = yaml.safe_load((ROOT / '01-nd-cluster/automation/playbooks' / filename).read_text())
        clusters = [task['vars']['cluster'] for play in plays for task in play['tasks'] if 'cluster' in task.get('vars', {})]
        assert clusters
        assert all('cisco.aipod.aipod_nd_cluster_spec(aipod | default(none))' in value for value in clusters)


def test_old_empty_search_domain_does_not_pass_new_intent():
    expected = {'cluster': {'search_domains': ['example.com']}, 'nodes': []}
    baseline = {'expected_from_inventory': expected,
                'observed_from_nd': {'cluster': {'search_domains': []}, 'nodes': []}}
    errors = compare_nd_baselines(dict(baseline, baseline_kind='manual'), dict(baseline, baseline_kind='automated'))
    assert 'manual cluster configuration differs from inventory' in errors
    assert 'automated cluster configuration differs from inventory' in errors
