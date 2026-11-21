import json
import unittest
from pathlib import Path

import jinja2

TEMPLATES = Path(__file__).resolve().parents[1] / 'roles/intersight_ucs_provision/templates/intersight'


class TestIntersightTemplates(unittest.TestCase):
    def environment(self, directory):
        return jinja2.Environment(loader=jinja2.FileSystemLoader(str(directory)), undefined=jinja2.StrictUndefined)

    def test_every_template_compiles(self):
        for path in sorted(TEMPLATES.rglob('*.j2')):
            with self.subTest(template=str(path.relative_to(TEMPLATES))):
                self.environment(path.parent).get_template(path.name)

    def render_switch_control(self, **item):
        item = {'name': 'sc', 'tags': [], **item}
        text = self.environment(TEMPLATES / 'policies').get_template('switch_control.json.j2').render(
            item=item, name_prefix='', name_suffix='', organization='o', org_moids={'o': {'moid': 'm'}},
            sensitive_vars={})
        return json.loads(text)

    def test_switch_control_renders_for_each_platform(self):
        domain = self.render_switch_control(target_platform='UCS Domain', switching_mode_ethernet='end-host',
                                            disabled_mac_address_learning_vlans='10,20')
        self.assertEqual(domain['MacLearningSettings']['DisabledVlans'], '10,20')
        self.assertEqual(domain['Name'], 'sc')
        self.assertNotIn('StpSettings', domain)
        plain = self.render_switch_control(target_platform='UCS Domain', switching_mode_ethernet='switch')
        self.assertNotIn('MacLearningSettings', plain)
        self.assertEqual(plain['Organization']['Moid'], 'm')

    def test_switch_control_stp_follows_the_setting(self):
        off = self.render_switch_control(target_platform='Unified Edge')
        on = self.render_switch_control(target_platform='Unified Edge', enable_stp=True)
        self.assertEqual(off['StpSettings']['StpMode'], 'Disabled')
        self.assertEqual(on['StpSettings']['StpMode'], 'RPVST+')

    def render(self, name, **context):
        template = self.environment(TEMPLATES / 'policies').get_template(name)
        return json.loads(template.render(**context))

    def test_vhba_from_template_renders_with_and_without_override(self):
        isight = {'org': {'policies': {'fibre_channel_adapter': {'fca': {'moid': 'a1'}}},
                          'pools': {'wwpn': {'pool': {'moid': 'p1'}}}}}
        base = {'name': 'vhba-a', 'parent': 'san1', 'tags': [], 'target_platform': 'FIAttached'}
        plain = self.render('san_connectivity.vhbas_from_template.json.j2', item=base, isight=isight,
                            organization='org')
        self.assertEqual((plain['Name'], plain['WwpnAddressType']), ('vhba-a', 'POOL'))
        self.assertNotIn('FcAdapterPolicy', plain)
        override = self.render('san_connectivity.vhbas_from_template.json.j2', isight=isight, organization='org',
                               item={**base, 'allow_override': True, 'fibre_channel_adapter_policy': 'fca',
                                     'wwpn_pool': 'pool', 'placement': {'pci_link': 1, 'slot_id': 'MLOM'}})
        self.assertEqual(override['FcAdapterPolicy']['Moid'], 'a1')
        self.assertEqual(override['WwpnPool']['Moid'], 'p1')
        self.assertEqual(override['Placement']['Id'], 'MLOM')

    def test_local_user_role_renders_with_the_cached_user_and_role(self):
        isight = {'system': {'iam_end_point_role': {'admin': {'moid': 'r1'}}},
                  'org': {'policies': {'local_user': {'pol1': 'lu', 'lu': {'users': {'bob': {'moid': 'u1'}}}}}}}
        body = self.render('local_user.users_roles.json.j2', isight=isight, organization='org',
                           sensitive_vars={'local_user_password_2': 'secret'},
                           item={'name': 'bob', 'role': 'admin', 'password': 2, 'parent': 'pol1'})
        self.assertEqual(body['EndPointRole'][0]['Moid'], 'r1')
        self.assertEqual(body['EndPointUser']['Moid'], 'u1')
        self.assertEqual((body['Password'], body['EndPointUserPolicy']['Moid']), ('secret', 'pol1'))


if __name__ == '__main__':
    unittest.main()
