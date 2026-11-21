import json
import unittest
from pathlib import Path

import jinja2

TEMPLATES = Path(__file__).resolve().parents[1] / 'roles/intersight_ucs_provision/templates/intersight'


# Already broken before this guard existed; remove an entry when its template is repaired
KNOWN_BROKEN = {'policies/local_user.users_roles.json.j2', 'policies/san_connectivity.vhbas_from_template.json.j2'}


class TestIntersightTemplates(unittest.TestCase):
    def environment(self, directory):
        return jinja2.Environment(loader=jinja2.FileSystemLoader(str(directory)), undefined=jinja2.StrictUndefined)

    def test_every_template_compiles(self):
        for path in sorted(TEMPLATES.rglob('*.j2')):
            name = str(path.relative_to(TEMPLATES))
            with self.subTest(template=name):
                if name in KNOWN_BROKEN:
                    with self.assertRaises(jinja2.TemplateSyntaxError):
                        self.environment(path.parent).get_template(path.name)
                    continue
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


if __name__ == '__main__':
    unittest.main()
