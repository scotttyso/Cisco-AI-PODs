"""Real local Ansible evaluates source assertions/payloads; no URI tasks execute."""
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize('subsystem,role', [('05-mgmt-nodes-ucs','mgmt_nodes_ucs'),
                                         ('06-workload-nodes-ucs','workload_nodes_ucs')])
@pytest.mark.parametrize('case', ['global','legacy_only','string_dns','empty_ntp'])
def test_actual_role_service_expressions_are_global_and_fail_closed(tmp_path, subsystem, role, case):
    executable = Path(sys.executable).with_name('ansible-playbook')
    if not executable.is_file():
        pytest.skip('Ansible unavailable beside Python')
    source = ROOT/subsystem/'automation/roles'/role/'tasks'
    domain = yaml.safe_load((source/'reconcile_domain_connector_prerequisites.yml').read_text())
    standalone = yaml.safe_load((source/'validate_standalone_connector_prerequisites.yml').read_text())
    globals = {'domain_name':'example.test','dns_servers':['192.0.2.53'], 'ntp_servers':['192.0.2.123']}
    variables = {'aipod':globals, 'ucs_management_services':{'dns_servers':['192.0.2.99'],'ntp_servers':['192.0.2.199']},
        'ucs_claim_endpoint':{'inventory_host':'fixture'},
        'ucs_domain_comm_configs':{'NameServers':['192.0.2.54'],'NtpServers':['192.0.2.124'], 'DomainName':'old.test'},
        'ucs_redfish_network_protocol':{'json':{'NTP':{'ProtocolEnabled':True,'NTPServers':globals['ntp_servers']}}},
        'ucs_redfish_ethernet':{'json':{'StaticNameServers':globals['dns_servers']}}}
    if case == 'legacy_only': del variables['aipod']
    if case == 'string_dns': globals['dns_servers'] = '192.0.2.53'
    if case == 'empty_ntp': globals['ntp_servers'] = []
    drift = next(t for t in domain if 'ucs_domain_dns_drift' in t.get('ansible.builtin.set_fact',{}))
    dns = next(t['ansible.builtin.uri']['body'] for t in domain if t.get('register')=='ucs_domain_dns_update')
    ntp = next(t['ansible.builtin.uri']['body'] for t in domain if t.get('register')=='ucs_domain_ntp_update')
    verify = next(t for t in standalone if t['name'].endswith('validate standalone DNS and NTP prerequisites'))
    tasks = [domain[0], standalone[0], drift,
        {'ansible.builtin.set_fact':{'rendered_dns':dns,'rendered_ntp':ntp}},
        {'ansible.builtin.assert':{'that':[
            'ucs_domain_dns_drift | bool', 'ucs_domain_ntp_drift | bool',
            "rendered_dns.DomainName == 'example.test'",
            "rendered_dns.NameServers | sort == ['192.0.2.53','192.0.2.54']",
            "rendered_ntp.NtpServers | sort == ['192.0.2.123','192.0.2.124']"]}}, verify]
    assert all(set(t).intersection({'ansible.builtin.uri','ansible.builtin.include_tasks'}) == set() for t in tasks)
    fixture = tmp_path/'fixture.yml'
    fixture.write_text(yaml.safe_dump([{'hosts':'localhost','connection':'local','gather_facts':False,
                                       'vars':variables, 'tasks':tasks}]))
    env = dict(os.environ, ANSIBLE_LOCAL_TEMP=str(tmp_path/'local'), ANSIBLE_REMOTE_TEMP=str(tmp_path/'remote'),
               ANSIBLE_NOCOLOR='1', ANSIBLE_CONFIG=str(tmp_path/'ansible.cfg'))
    (tmp_path/'ansible.cfg').write_text('[defaults]\nretry_files_enabled = False\n')
    result = subprocess.run([str(executable),'-i','localhost,',str(fixture)], env=env,
                            capture_output=True,text=True,timeout=45)
    assert result.returncode == (0 if case == 'global' else 2), result.stdout + result.stderr
    if case != 'global':
        assert 'TASK [UCS/Intersight: require canonical' in result.stdout
