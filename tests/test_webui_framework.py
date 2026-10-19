import asyncio
import datetime
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))
sys.path.insert(0, str(REPOSITORY / "07-openshift-cluster" / "automation" / "scripts"))
from aipod_webui import custom_pages, intersight_policies, pages, panels, seeds, stage_inventory  # noqa: E402
from aipod_webui.jobs import JobManager  # noqa: E402
from aipod_webui.vault import VAULT_HEADER, VaultStore, stage_env_name  # noqa: E402
import iserver_setup  # noqa: E402


@unittest.skipUnless(shutil.which("ansible-vault"), "ansible-vault is not installed")
class VaultStoreTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.vault = VaultStore(root / "vault.yaml", root / "cfg" / "vault-password")
        self.vault.create_password()

    def tearDown(self):
        self.directory.cleanup()

    def test_environment_prefers_the_page_section(self):
        self.vault.update({("everpure", "local_user_password_1"): "Pure-Pass-1",
                           ("intersight", "local_user_password_1"): "Ucs-Pass-1"})
        self.assertEqual(self.vault.environment()[0]["local_user_password_1"], "Ucs-Pass-1")
        self.assertEqual(self.vault.environment(prefer="everpure")[0]["local_user_password_1"], "Pure-Pass-1")

    def test_update_encrypts_and_round_trips(self):
        self.vault.update({("", "vault_nd_admin_password"): "Secret-Value-1",
                           ("openshift", "proxy_password_1"): "Proxy-Pass-2"})
        self.assertTrue(self.vault.vault_file.read_text().startswith(VAULT_HEADER))
        self.assertEqual(self.vault.vault_file.stat().st_mode & 0o777, 0o600)
        data = self.vault.load()
        self.assertEqual(data["vault_nd_admin_password"], "Secret-Value-1")
        self.assertTrue(self.vault.is_set(data, "openshift", "proxy_password_1"))

        env, redact = self.vault.environment()
        self.assertEqual(env["ND_ADMIN_PASSWORD"], "Secret-Value-1")
        self.assertEqual(env["proxy_password_1"], "Proxy-Pass-2")
        self.assertIn("Secret-Value-1", redact)

        self.vault.update({("openshift", "proxy_password_1"): None})
        self.assertNotIn("openshift", self.vault.load())

    def test_intersight_ldap_binding_reuses_shared_ldap_password(self):
        self.vault.update({("openshift", "ldap_bind_password"): "Ldap-Bind-123"})
        self.assertEqual(self.vault.environment()[0]["ldap_binding_password_1"], "Ldap-Bind-123")
        self.vault.update({("intersight", "ldap_binding_password_1"): "Own-Ldap-456"})
        self.assertEqual(self.vault.environment()[0]["ldap_binding_password_1"], "Own-Ldap-456")

    def test_rejects_unknown_section_and_open_password_file(self):
        with self.assertRaises(Exception):
            self.vault.update({("bogus", "key"): "value"})
        os.chmod(self.vault.password_file, 0o644)
        self.assertFalse(self.vault.status()["ready"])

    def test_stage_env_name(self):
        self.assertEqual(stage_env_name("vault_fi_a_cimc_password"), "FI_A_CIMC_PASSWORD")


class JobManagerTest(unittest.TestCase):
    def test_runs_commands_streams_log_and_redacts(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = JobManager(Path(directory))

            async def scenario():
                job = manager.start("page", "Echo", [["sh", "-c", "echo hello $TOKEN"], ["sh", "-c", "exit 3"]],
                                    {"TOKEN": "TopSecret99"}, Path(directory), redact=["TopSecret99"])
                self.assertIs(manager.running("page"), job)
                self.assertIn(job, JobManager.all_running())
                with self.assertRaises(RuntimeError):
                    manager.start("page", "Again", [["true"]], {}, Path(directory))
                for _ in range(100):
                    if not manager.running("page"):
                        break
                    await asyncio.sleep(0.05)
                return job

            job = asyncio.run(scenario())
            finished = manager.history("page")[0]
            self.assertEqual(finished.id, job.id)
            self.assertEqual(finished.status, "failed")
            self.assertEqual(finished.returncode, 3)
            text, _ = JobManager.read(finished)
            self.assertIn("hello", text)
            self.assertNotIn("TopSecret99", text)


class SudoAndDhcpGuardTest(unittest.TestCase):
    def test_sudo_askpass_answers_from_job_environment_only(self):
        env = panels.sudo_environment("Sudo-Pass-123")
        self.assertEqual(env["BECOME_PASSWORD"], "Sudo-Pass-123")
        answer = subprocess.run([env["SUDO_ASKPASS"], "[sudo] password:"], capture_output=True, text=True,
                                env={"AIPOD_SUDO_PASSWORD": env["AIPOD_SUDO_PASSWORD"]}).stdout
        self.assertEqual(answer, "Sudo-Pass-123\n")
        self.assertFalse(any(field.key == "vault_become_password" for field in vars(pages).values()
                             if hasattr(field, "key")))

    def test_kea_install_requires_listen_interfaces_on_this_host(self):
        install = next(action for action in pages.dhcp_actions(Path("x.yaml"), Path("x.conf")) if action.key == "install")
        self.assertTrue(install.sudo)
        with tempfile.TemporaryDirectory() as folder:
            vars_file = Path(folder, "dhcp.yaml")
            for interfaces in (None, [], ["*"], ["eth0", "*"]):
                vars_file.write_text(yaml.safe_dump({"dhcp": {"interfaces": interfaces, "subnets": []}}))
                with self.subTest(interfaces=interfaces), self.assertRaisesRegex(ValueError, "listen interface"):
                    pages.check_listen_interfaces(vars_file, {"eth0"})
            vars_file.write_text(yaml.safe_dump({"dhcp": {"interfaces": ["eth9"]}}))
            with self.assertRaisesRegex(ValueError, "not on this server: eth9"):
                pages.check_listen_interfaces(vars_file, {"eth0"})
            vars_file.write_text(yaml.safe_dump({"dhcp": {"interfaces": ["eth0"]}}))
            self.assertEqual(pages.check_listen_interfaces(vars_file, {"eth0", "eth1"}), ["eth0"])


class SeedTest(unittest.TestCase):
    ROWS = [
        {"hostname": "nd-1", "ip": "198.18.0.11", "pid": "ND-NODE-L4", "serial_number": "A"},
        {"hostname": "be-leaf-1", "ip": "198.18.0.21", "pid": "N9K-C9364D-GX2A", "serial_number": "B"},
        {"hostname": "oob-1", "ip": "198.18.0.22", "pid": "N9K-C93108TC-FX3", "serial_number": "C"},
        {"hostname": "fi-a", "ip": "198.18.0.31", "pid": "UCS-FI-6536", "serial_number": "D"},
        {"hostname": "c845-1", "ip": "198.18.0.41", "pid": "UCSC-845A-M8", "serial_number": "E"},
        {"hostname": "c240-1", "ip": "198.18.0.42", "pid": "UCSC-C240-M8", "serial_number": "F",
         "role": "ucs-server"},
    ]

    def test_guess_role(self):
        self.assertEqual([seeds.row_role(row) for row in self.ROWS],
                         ["nd-node", "switch-backend", "switch-mgmt", "fabric-interconnect", "hgx-node", "ucs-server"])

    def test_hgx_seed_from_inventory(self):
        context = seeds.SeedContext(self.ROWS, {"dns_servers": ["192.0.2.53"], "ntp_servers": ["192.0.2.123"],
                                                "domain_name": "example.com", "timezone": "UTC"},
                                    {"intersight-registration": {"devices": {"c845-1": {"ip": "10.0.0.41"}}}})
        example = (REPOSITORY / "examples/hgx/hgx.ezai.yaml").read_text(encoding="utf-8")
        data = yaml.safe_load(seeds.apply_seed("hgx", example, context))["hgx_servers"]
        self.assertEqual(data["bmc_settings"]["dns_servers"], ["192.0.2.53"])
        self.assertEqual(data["servers"], [{"hostname": "c845-1", "model": "C845A", "serial_number": "E",
                                            "bmc": {"ip": "10.0.0.41"}}])

    def test_domain_and_xseries_seeds_are_split(self):
        rows = [{"hostname": "ucsai-1-a", "pid": "UCSX-S9108-100G", "serial_number": "FDO29100001", "role": "x-direct"},
                {"hostname": "ucsai-1-1", "pid": "UCSX-215C-M8", "serial_number": "FCH29100001", "role": "ucs-blade"}]
        context = seeds.SeedContext(rows, {})
        domains = yaml.safe_load(seeds.apply_seed("domain_profiles", (REPOSITORY / "examples/intersight/domains/"
                                                  "profiles.ezai.yaml").read_text(encoding="utf-8"), context))
        domain_profiles = domains["intersight"]["configure"]["default"]["profiles"]
        self.assertNotIn("server", domain_profiles)
        self.assertIn("ucsai-1", [item["name"] for item in domain_profiles["domain"]])
        servers = yaml.safe_load(seeds.apply_seed("xseries_profiles", (REPOSITORY / "examples/intersight/servers/"
                                                  "x-series/profiles.ezai.yaml").read_text(encoding="utf-8"), context))
        server_profiles = servers["intersight"]["configure"]["default"]["profiles"]
        self.assertEqual(set(server_profiles), {"server"})
        self.assertEqual([(item["domain_name"], [target["name"] for target in item["targets"]])
                          for item in server_profiles["server"]], [("ucsai-1", ["ucsai-1-1"])])

    def test_system_seed_puts_claimed_targets_in_default_resource_group(self):
        example = (REPOSITORY / "examples/intersight/system/system.ezai.yaml").read_text(encoding="utf-8")
        system = yaml.safe_load(seeds.apply_seed("system", example, seeds.SeedContext(self.ROWS, {})))["intersight"]["system"]
        default = next(item for item in system["resource_groups"] if item["name"] == "default")
        self.assertEqual(default["resources"]["targets"], ["fi-a", "c845-1", "c240-1"])
        self.assertIn("default", next(item for item in system["organizations"] if item["name"] == "default")["resource_groups"])
        system["resource_groups"].append({"name": "AI", "resources": {"targets": ["c240-1"]}})
        again = yaml.safe_load(seeds.apply_seed("system", yaml.safe_dump({"intersight": {"system": system}}),
                                                seeds.SeedContext(self.ROWS, {})))["intersight"]["system"]
        default = next(item for item in again["resource_groups"] if item["name"] == "default")
        self.assertEqual(default["resources"]["targets"], ["fi-a", "c845-1"])

    def test_intersight_policy_secret_fields(self):
        state = {intersight_policies.STATE_KEY: {"snmp": 2, "ldap": 1, "mac_sec": 1, "firmware_authenticate": 1}}
        domains = {item.key: item for item in intersight_policies.fields(state, "intersight-domains")}
        self.assertEqual(set(domains), {"snmp_community_string_1", "snmp_access_community_string_1",
                                        "snmp_trap_community_1", "snmp_password_1", "snmp_user_auth_password_1",
                                        "snmp_user_privacy_password_1", "snmp_community_string_2",
                                        "snmp_access_community_string_2", "snmp_trap_community_2", "snmp_password_2",
                                        "snmp_user_auth_password_2", "snmp_user_privacy_password_2",
                                        "mac_sec_primary_key_chain_secret_1", "mac_sec_fallback_key_chain_secret_1"})
        self.assertTrue(domains["snmp_password_2"].optional)
        self.assertFalse(domains["mac_sec_primary_key_chain_secret_1"].optional)
        self.assertEqual(domains["mac_sec_primary_key_chain_secret_1"].targets,
                         (("intersight", "mac_sec_primary_key_chain_secret_1"),))
        servers = {item.key for item in intersight_policies.fields(state, "intersight-servers")}
        self.assertIn("cco_password_1", servers)
        self.assertNotIn("mac_sec_primary_key_chain_secret_1", servers)

    def test_snmp_fields_have_their_own_counts(self):
        state = {intersight_policies.STATE_KEY: {"snmp": 1, "snmp.snmp_user_auth_password": 3,
                                                 "snmp.snmp_user_privacy_password": 2, "snmp.snmp_password": 0,
                                                 "local_user": 2, "certificate_management": 1}}
        keys = {item.key: item for item in intersight_policies.fields(state, "intersight-domains")}
        self.assertTrue({"snmp_user_auth_password_3", "snmp_user_privacy_password_2", "local_user_password_2",
                         "snmp_community_string_1", "private_key_passphrase_1"} <= set(keys))
        self.assertFalse({"snmp_user_auth_password_4", "snmp_user_privacy_password_3", "snmp_password_1",
                          "snmp_community_string_2"} & set(keys))
        self.assertIn("snmp_users[].auth_password: 3", keys["snmp_user_auth_password_3"].help)
        self.assertIn("users[].password: 2", keys["local_user_password_2"].help)

    def test_certificate_uploads(self):
        self.assertEqual(intersight_policies.certificate_file_name("IMC Certificate.crt"), "IMC_Certificate.crt")
        self.assertEqual(intersight_policies.certificate_file_name("../root ca"), "root_ca.pem")
        self.assertEqual(intersight_policies.certificate_file_name("server.KEY"), "server.key")
        text, kind = intersight_policies.check_certificate(b"-----BEGIN CERTIFICATE-----\nAA\n-----END CERTIFICATE-----")
        self.assertEqual((kind, text.endswith("\n")), ("certificate", True))
        self.assertEqual(intersight_policies.check_certificate(
            b"-----BEGIN RSA PRIVATE KEY-----\nAA\n-----END RSA PRIVATE KEY-----\n")[1], "private_key")
        with self.assertRaises(ValueError):
            intersight_policies.check_certificate(b"not pem")
        self.assertEqual(intersight_policies.certificate_dir(Path("/env")), Path("/env/certificates/intersight"))

    def test_everpure_policy_secret_fields(self):
        state = {intersight_policies.STATE_KEY: {
            "everpure_certificates": 2, "everpure_local_user": 1, "everpure_ldap": 1, "everpure_snmp": 1,
            "everpure_snmp.everpure_snmp_community": 2, "everpure_snmp.everpure_snmp_auth_passphrase": 1,
            "everpure_snmp.everpure_snmp_privacy_passphrase": 0, "snmp": 3}}
        keys = {item.key: item for item in intersight_policies.fields(state, "everpure")}
        self.assertEqual(set(keys), {"private_key_passphrase_1", "private_key_passphrase_2", "local_user_password_1",
                                     "everpure_snmp_community_1", "everpure_snmp_community_2",
                                     "everpure_snmp_auth_passphrase_1"})
        self.assertEqual(keys["local_user_password_1"].targets, (("everpure", "local_user_password_1"),))
        self.assertIn("array_certificates[].private_key_passphrase: 2", keys["private_key_passphrase_2"].help)
        self.assertIn("v2c[].community", keys["everpure_snmp_community_2"].help)
        self.assertEqual(intersight_policies.certificate_dir(Path("/env"), "everpure"),
                         Path("/env/certificates/everpure"))
        self.assertIn("array_certificates", custom_pages.certificate_example(Path("/env/certificates/everpure"), True))

    def test_yaml_secret_section_prefers_the_model_section(self):
        from aipod_webui import vault
        everpure = {item.key: item.targets for item in vault.sensitive_fields(
            {"everpure": {"settings": {"security": {"users": [{"name": "px", "password": 1}]}}}})}
        self.assertEqual(everpure["local_user_password_1"], (("everpure", "local_user_password_1"),))
        intersight = {item.key: item.targets for item in vault.sensitive_fields(
            {"intersight": {"policies": [{"local_user": [{"users": [{"name": "a", "password": 1}]}]}]}})}
        self.assertEqual(intersight["local_user_password_1"], (("intersight", "local_user_password_1"),))
        self.assertEqual(panels.vault_section_for("everpure"), "everpure")
        self.assertEqual(panels.vault_section_for("intersight-servers"), "intersight")
        self.assertIsNone(panels.vault_section_for("splunk"))

    def test_openshift_csr_alt_names_include_the_common_name(self):
        self.assertEqual(custom_pages.certificate_alt_names("api", "ocp", "example.com"), ["api.ocp.example.com"])
        self.assertEqual(custom_pages.certificate_alt_names("ingress", "ocp", "example.com"),
                         ["apps.ocp.example.com", "*.apps.ocp.example.com"])
        from cryptography import x509
        with tempfile.TemporaryDirectory() as folder:
            custom_pages._csr("apps.ocp.example.com", {"key_size": 2048}, Path(folder), "ingress",
                              custom_pages.certificate_alt_names("ingress", "ocp", "example.com"))
            request = x509.load_pem_x509_csr((Path(folder) / "ingress.csr").read_bytes())
            names = request.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            self.assertEqual(names.get_values_for_type(x509.DNSName), ["apps.ocp.example.com", "*.apps.ocp.example.com"])

    def test_single_file_scripts_merge_uploaded_yaml(self):
        import types
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            main = root / "host_vars/hgx/hgx.ezai.yaml"
            upload = root / "host_vars/hgx/uploads/extra.ezai.yaml"
            upload.parent.mkdir(parents=True)
            main.write_text("hgx_servers:\n  dns: [1.1.1.1]\n  ntp: [pool]\n")
            context = types.SimpleNamespace(output_dir=root)
            only = panels.RunContext(context, "hgx-nodes", {}, {pages.HGX_VARS: main})
            self.assertEqual(pages.run_config(only, pages.HGX_VARS, pages.HGX_UPLOADS), main)
            upload.write_text("hgx_servers:\n  dns: [8.8.8.8]\n  timezone: UTC\n")
            run = panels.RunContext(context, "hgx-nodes", {}, {pages.HGX_VARS: main,
                                                              "hgx/uploads/extra.ezai.yaml": upload})
            merged = pages.run_config(run, pages.HGX_VARS, pages.HGX_UPLOADS)
            self.assertEqual(merged, root / "merged/hgx.ezai.yaml")
            self.assertEqual(yaml.safe_load(merged.read_text()),
                             {"hgx_servers": {"dns": ["8.8.8.8"], "ntp": ["pool"], "timezone": "UTC"}})
            self.assertEqual(merged.stat().st_mode & 0o777, 0o600)

    def test_upload_buttons_on_requested_pages(self):
        specs = {spec.key: spec for section in pages.SECTIONS for spec in section.pages}
        for key in ("backend-fabric", "frontend-fabric", "mgmt-fabric", "everpure", "intersight-system",
                    "hgx-nodes", "ocp-cluster", "ocp-certificates", "ocp-ldap", "splunk"):
            self.assertTrue(specs[key].upload_dirs and specs[key].upload_dirs[0], key)

    def test_registration_hosts_and_secrets(self):
        legacy = {"devices": {"c240-1": {"ip": "10.0.0.42", "netmask": "255.255.255.0"}}}
        hosts = stage_inventory.registration_hosts(self.ROWS, legacy)
        self.assertEqual(set(hosts), {"fi-a", "c845-1", "c240-1"})
        cimc = hosts["c240-1"]["ucs"]["cimc"]
        self.assertEqual((cimc["ip"], cimc["dhcp_ip"], cimc["netmask"]), ("10.0.0.42", "198.18.0.42", "255.255.255.0"))
        self.assertEqual(cimc["pass_ref"], "UCS_CIMC_PASSWORD")
        self.assertEqual(hosts["fi-a"]["ucs"]["platform"], "domain")
        self.assertEqual(hosts["fi-a"]["ucs"]["cimc"]["pass_ref"], "UCS_FI_PASSWORD")
        self.assertEqual((hosts["fi-a"]["ucs"]["organization"], hosts["fi-a"]["ucs"]["resource_group"]),
                         ("default", "default"))
        secrets = dict(stage_inventory.required_secrets(self.ROWS)["intersight-registration"])
        self.assertEqual(set(secrets), {"vault_intersight_api_key_id", "vault_intersight_api_private_key",
                                        "vault_ucs_fi_password", "vault_ucs_cimc_password",
                                        "vault_hgx_bmc_password"})
        self.assertEqual(hosts["c845-1"]["ucs"]["cimc"]["pass_ref"], "HGX_BMC_PASSWORD")

    def test_registration_targets_override_default_org(self):
        state = {"cimc_username": "ops",
                 "targets": [{"id": "c240-1", "hostname": "c240-1", "role": "ucs-server", "address": "198.18.0.42",
                              "static_ip": "", "factory_default": True, "override": True, "username": "root"},
                             {"id": "c240-2", "hostname": "c240-2", "role": "ucs-server", "address": "198.18.0.43"}]}
        hosts = stage_inventory.registration_hosts(self.ROWS, state)
        self.assertEqual(set(hosts), {"c240-1", "c240-2"})
        first, second = hosts["c240-1"]["ucs"], hosts["c240-2"]["ucs"]
        self.assertEqual((first["cimc"]["user"], first["cimc"]["pass_ref"], first["cimc"]["ip"]),
                         ("root", "C240_1_CIMC_PASSWORD", "198.18.0.42"))
        self.assertEqual((first["organization"], first["resource_group"], first["factory_default"]),
                         ("default", "default", True))
        self.assertEqual((second["cimc"]["user"], second["organization"]), ("ops", "default"))
        missing = stage_inventory.missing_targets(self.ROWS, stage_inventory.registration_targets(self.ROWS, state))
        self.assertEqual({item["hostname"] for item in missing}, {"fi-a", "c845-1"})

    def test_backend_fabric_inventory(self):
        fabric = {"nexus_dashboard": {"fabrics": [{
            "name": "AIPOD-Backend", "type": "aiVxlanEvpn", "licenseTier": "premier",
            "fabric_settings": {"bgpAsn": 65100},
            "backend_settings": {"key": "backend", "replicationMode": "Ingress", "ptp": False,
                                 "location": {"name": "Example City, US", "latitude": 0, "longitude": 0}},
            "switches": [
                {"hostname": "be-sp-1", "ip": "198.18.0.21", "switchRole": "spine", "model": "M", "serialNumber": "S1",
                 "softwareVersion": "10.6", "fabricLinkInterfaces": ["Ethernet1/1"]},
                {"hostname": "be-lf-1", "ip": "198.18.0.22", "switchRole": "leaf", "model": "M", "serialNumber": "S2",
                 "softwareVersion": "10.6", "passwordRef": "BE_LF_1_PASSWORD"}]}]}}
        import yaml
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "host_vars" / "nexus_dashboard").mkdir(parents=True)
            (root / "host_vars" / "nexus_dashboard" / "backend-fabric.ezai.yaml").write_text(yaml.safe_dump(fabric))
            inventory = stage_inventory.build(root, root / "host_vars", [], {}, {})
            tree = yaml.safe_load(inventory.read_text())
            group = tree["all"]["children"]["backend_fabric_switches"]["children"]["backend_fabric_backend"]
            self.assertEqual(set(group["hosts"]), {"be-sp-1", "be-lf-1"})
            be_vars = yaml.safe_load((root / "inventory/group_vars/backend_fabric_switches.yml").read_text())
            self.assertEqual(be_vars["be_fabrics"][0], {
                "key": "backend", "name": "AIPOD-Backend", "bgp_as": 65100, "underlay_first_octet": 20,
                "qos_policy": "AI_Fabric_QOS_400G", "license_tier": "Premier", "replication_mode": "Ingress",
                "ptp": False, "location": {"name": "Example City, US", "latitude": 0, "longitude": 0}})
            self.assertEqual(be_vars["be_fabric_features"]["switch_password_ref"], "SWITCH_PASSWORD")
            spine = yaml.safe_load((root / "inventory/host_vars/be-sp-1.yml").read_text())["be_switch"]
            self.assertEqual(spine, {"fabric_key": "backend", "hostname": "BE-SP-1", "role": "spine",
                                     "mgmt_ip": "198.18.0.21", "username": "admin", "pass_ref": "SWITCH_PASSWORD",
                                     "fabric_link_interfaces": ["Ethernet1/1"]})
            secrets = dict(stage_inventory.required_secrets(
                [], None, stage_inventory.saved_backend_fabrics(root / "host_vars"))["backend-fabric"])
            self.assertEqual(set(secrets), {"vault_nd_admin_password", "vault_switch_password",
                                            "vault_be_lf_1_password"})
            (root / "host_vars" / "nexus_dashboard" / "backend-fabric.ezai.yaml").unlink()
            stage_inventory.build(root, root / "host_vars", [], {}, {})
            self.assertFalse((root / "inventory/group_vars/backend_fabric_switches.yml").exists())

    def test_backend_seed_prefers_ai_vxlan_evpn(self):
        example = (REPOSITORY / "examples/nexus_dashboard/fabrics.ezai.yaml").read_text()
        text = seeds.apply_seed("fabric_backend", example, seeds.SeedContext(self.ROWS, {}))
        self.assertIn("aiVxlanEvpn", text)
        self.assertIn("backend_settings:", text)
        self.assertNotIn("aiRouted", text)

    def test_splunk_seed_uses_shared_proxy(self):
        context = seeds.SeedContext(self.ROWS, {"proxy_servers": {"https_proxy": "http://proxy:80",
                                                                  "no_proxy": ["localhost"]}})
        text = seeds.apply_seed("splunk", "---\nsplunk_observability: {}\n", context)
        self.assertIn("http://proxy:80", text)

    def fabric(self, kind: str, state: dict | None = None) -> dict:
        example = (REPOSITORY / "examples/nexus_dashboard/fabrics.ezai.yaml").read_text()
        text = seeds.apply_seed(f"fabric_{kind}", example, seeds.SeedContext(self.ROWS, {}, state or {}))
        return yaml.safe_load(text)["nexus_dashboard"]["fabrics"][0]

    def test_fabric_seed_types_telemetry_and_inventory_switches(self):
        backend, frontend, mgmt = self.fabric("backend"), self.fabric("frontend"), self.fabric("mgmt")
        self.assertEqual((backend["name"], backend["type"]), ("aipod-backend", "aiVxlanEvpn"))
        self.assertEqual((frontend["name"], frontend["type"]), ("aipod-frontend", "aiVxlanEvpn"))
        self.assertNotIn("backend_settings", frontend)
        self.assertEqual(mgmt["type"], "classicLan")
        for fabric in (backend, frontend, mgmt):
            telemetry = fabric["telemetry"]
            self.assertEqual((telemetry["telemetryMode"], telemetry["telemetryVrf"],
                              telemetry["telemetrySourceInterface"]), ("outofband", "management", "mgmt0"))
            self.assertNotIn("performanceMonitoring", telemetry)
            self.assertNotIn("performanceMonitoring", fabric.get("fabric_settings") or {})
            self.assertTrue(fabric["poap"]["enabled"])
        self.assertEqual([switch["hostname"] for switch in backend["switches"]], ["be-leaf-1"])
        self.assertEqual(backend["switches"][0]["switchRole"], "leaf")
        self.assertEqual([switch["hostname"] for switch in mgmt["switches"]], ["oob-1"])

    def test_fabric_seed_page_switches_ports_and_poap_gateway(self):
        switches = [{"hostname": "be-spine-1", "ip": "198.18.0.25", "model": "N9K-C9364D-GX2A", "serialNumber": "S1",
                     "switchRole": "spine"},
                    {"hostname": "be-leaf-1", "ip": "198.18.0.21", "serialNumber": "B", "switchRole": "leaf"}]
        state = {"backend-fabric": {"switches": switches,
                                    "ports": {seeds.host_key("be-leaf-1"): {"Ethernet1/10": "host", "Ethernet1/2": "fabric",
                                                                            "Ethernet1/1": "fabric", "Ethernet1/3": "unused"}}},
                 "dhcp": {"network": "198.18.0.0/24", "routers": ["198.18.0.1"]}}
        fabric = self.fabric("backend", state)
        self.assertEqual([switch["hostname"] for switch in fabric["switches"]], ["be-spine-1", "be-leaf-1"])
        leaf = fabric["switches"][1]
        self.assertEqual(leaf["fabricLinkInterfaces"], ["Ethernet1/1", "Ethernet1/2"])
        self.assertEqual(leaf["hostInterfaces"], ["Ethernet1/10"])
        self.assertEqual(fabric["poap"]["gateway"], "198.18.0.1/24")
        self.assertEqual(self.fabric("backend", {"backend-fabric": {"switches": []}}).get("switches"), [])

    def test_port_rows_guess_roles_from_lldp(self):
        report = {"switches": {"be-leaf-1": {"ports": [
            {"name": "Ethernet1/10", "neighbor": "gpu-node-1", "neighbor_port": "ens1"},
            {"name": "Ethernet1/2", "neighbor": "be-spine-1.example.com", "neighbor_port": "Ethernet1/1"},
            {"name": "Ethernet1/3"}, {"name": "Ethernet1/4", "neighbor": "be-spine-1"}]}}}
        switches = [{"hostname": "be-leaf-1"}, {"hostname": "be-spine-1"}]
        rows = seeds.port_rows(report, switches, {seeds.host_key("be-leaf-1"): {"Ethernet1/4": "unused"}})
        self.assertEqual([(row["name"], row["role"]) for row in rows],
                         [("Ethernet1/2", "fabric"), ("Ethernet1/3", "unused"), ("Ethernet1/4", "unused"),
                          ("Ethernet1/10", "host")])
        self.assertEqual(seeds.port_assignments(rows)[seeds.host_key("be-leaf-1")]["Ethernet1/10"], "host")
        current = {"be-leaf-1": {"hostInterfaces": ["Ethernet1/2"]}}
        self.assertEqual(seeds.port_rows(report, switches, {}, current)[0]["role"], "host")


class NdFabricScriptTest(unittest.TestCase):
    FABRIC = {"name": "aipod-backend", "type": "aiVxlanEvpn",
              "telemetry": {"telemetryCollection": True, "telemetryMode": "outofband", "telemetryVrf": "management",
                            "telemetrySourceInterface": "mgmt0"},
              "poap": {"enabled": True, "dhcp": "external", "gateway": "198.18.0.1/24"},
              "switches": [{"hostname": "be-leaf-1", "ip": "198.18.0.21", "serialNumber": "B", "model": "N9K",
                            "softwareVersion": "10.4(5)", "switchRole": "leaf", "hostInterfaces": ["Ethernet1/10"]},
                           {"hostname": "be-spine-1", "ip": "198.18.0.25", "serialNumber": "S1"}]}

    @classmethod
    def setUpClass(cls):
        import importlib
        cls.nd = importlib.import_module("nd_fabric")

    def test_telemetry_is_out_of_band_without_performance_monitoring(self):
        fields = self.nd.telemetry_fields(self.FABRIC)
        self.assertEqual(fields["telemetryCollectionType"], "outOfBand")
        self.assertEqual(fields["telemetrySourceInterface"], "mgmt0")
        self.assertNotIn("performanceMonitoring", str(self.nd.fabric_body(self.FABRIC, None)))

    def test_bootstrap_and_read_only(self):
        pairs = self.nd.bootstrap_nvpairs(self.FABRIC, {"FABRIC_NAME": "aipod-backend"})
        self.assertEqual(pairs["BOOTSTRAP_ENABLE"], "true")
        with self.assertRaises(Exception):
            self.nd.bootstrap_nvpairs(self.FABRIC, {"FABRIC_NAME": "aipod-backend", "IS_READ_ONLY": "true"})

    def test_claim_payload_matches_serials(self):
        poap = [{"serialNumber": "B", "model": "N9K", "version": "10.4(5)", "publicKey": "k", "fingerprint": "f",
                 "data": '{"modulesModel": ["N9K"]}'}]
        entries, missing = self.nd.claim_payload(self.FABRIC, poap, "pw")
        self.assertEqual([(entry["serialNumber"], entry["ipAddress"], entry["hostname"]) for entry in entries],
                         [("B", "198.18.0.21", "be-leaf-1")])
        self.assertEqual(missing, ["be-spine-1 (S1)"])

    def test_parse_ports_and_host_payload(self):
        transceivers = {"TABLE_interface": {"ROW_interface": [
            {"interface": "Ethernet1/1", "sfp": "present", "type": "QSFP-400G-DR4"},
            {"interface": "Ethernet1/2", "sfp": "not present"}]}}
        lldp = {"TABLE_nbor": {"ROW_nbor": {"l_port_id": "Ethernet1/1", "chassis_id": "be-spine-1", "port_id": "Eth1/1"}}}
        ports = self.nd.parse_ports(transceivers, lldp, {})
        self.assertEqual([(port["name"], port["neighbor"]) for port in ports], [("Ethernet1/1", "be-spine-1")])
        payload = self.nd.host_port_payload(self.FABRIC, "B", ["Ethernet1/10"])
        self.assertEqual(payload["interfaces"][0]["ifName"], "Ethernet1/10")
        self.assertEqual(payload["interfaces"][0]["fabricName"], "aipod-backend")


class UploadTest(unittest.TestCase):
    def test_upload_file_name_is_safe_ezai_yaml(self):
        self.assertEqual(panels.upload_file_name("My Policies.yaml"), "My_Policies.ezai.yaml")
        self.assertEqual(panels.upload_file_name("../../etc/x.ezai.yml"), "x.ezai.yaml")
        self.assertEqual(panels.upload_file_name("pools.ezai.yaml"), "pools.ezai.yaml")
        self.assertEqual(panels.upload_file_name(".yaml"), "uploaded.ezai.yaml")

    def test_check_upload_requires_yaml_mapping(self):
        self.assertEqual(panels.check_upload(b"intersight: {}"), "intersight: {}\n")
        for content in (b"- a\n- b\n", b"key: [unclosed", b"\xff\xfe", b"x" * (panels.UPLOAD_MAX_BYTES + 1)):
            with self.assertRaises(ValueError):
                panels.check_upload(content)

    def test_intersight_pages_upload_into_their_deploy_folders(self):
        self.assertEqual(pages.PAGES["intersight-domains"].upload_dirs, ("intersight/domains/uploads",))
        servers = pages.PAGES["intersight-servers"]
        self.assertEqual(len(servers.upload_dirs), len(servers.file_groups))
        self.assertTrue(all(folder.startswith("intersight/servers/") for folder in servers.upload_dirs))
        self.assertIs(servers.secrets_header, custom_pages.policy_secrets_selector)
        self.assertIsNone(servers.form)


class CertificateTest(unittest.TestCase):
    def test_csr_and_chain_check(self):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.x509.oid import NameOID

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "certs"
            custom_pages._csr("api.ocp.example.com", {"organization": "Cisco", "country": "US", "key_size": 2048},
                              folder, "api")
            key_path = folder / "api.key"
            self.assertEqual(key_path.stat().st_mode & 0o777, 0o600)
            request = x509.load_pem_x509_csr((folder / "api.csr").read_bytes())
            self.assertEqual(request.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value, "api.ocp.example.com")

            key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
            now = datetime.datetime.now(datetime.timezone.utc)
            certificate = (x509.CertificateBuilder().subject_name(request.subject).issuer_name(request.subject)
                           .public_key(key.public_key()).serial_number(1)
                           .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
                           .add_extension(x509.SubjectAlternativeName([x509.DNSName("api.ocp.example.com")]), False)
                           .sign(key, hashes.SHA256()))
            chain = certificate.public_bytes(serialization.Encoding.PEM)
            self.assertEqual(custom_pages.check_chain(chain, key_path, "api.ocp.example.com"), [])
            problems = custom_pages.check_chain(chain, key_path, "*.apps.ocp.example.com")
            self.assertTrue(any("subject alternative names" in problem for problem in problems))
            self.assertTrue(custom_pages.check_chain(b"junk", None, "")[0].startswith("Not a PEM"))


class EverpureCertificateTest(unittest.TestCase):
    def test_appliances_and_yaml_entries(self):
        models = [{"everpure": {"flash_arrays": [{"array_fqdn": "FA01.example.com"}, {"array_fqdn": " "}],
                                "flash_blades": [{"array_fqdn": "fb01.example.com"}, {"array_fqdn": "fa01.example.com"}]}}]
        self.assertEqual(custom_pages.everpure_appliances(models), ["fa01.example.com", "fb01.example.com"])
        self.assertEqual(custom_pages.everpure_certificate_name("fa01.example.com"), "fa01-cert")
        server, intermediate = custom_pages.split_chain(
            b"-----BEGIN CERTIFICATE-----\nA\n-----END CERTIFICATE-----\n-----BEGIN CERTIFICATE-----\nB\n-----END CERTIFICATE-----")
        self.assertIn("\nA\n", server)
        self.assertIn("\nB\n", intermediate)
        self.assertEqual(custom_pages.split_chain(b"-----BEGIN CERTIFICATE-----\nA\n-----END CERTIFICATE-----")[1], "")
        with self.assertRaises(ValueError):
            custom_pages.split_chain(b"junk")
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name in ("fa01.example.com.key", "fa01.example.com.crt", "fb01.example.com.key", "fb01.example.com.crt",
                         "fb01.example.com.intermediate.crt", "fx01.example.com.key"):
                (folder / name).write_text("x")
            text = ("everpure:\n  settings:\n    security:\n      certificates:\n        array_certificates:\n"
                    "          - name: fa01-cert\n            array_fqdns: [fa01.example.com]\n"
                    "            certificate_file: /old.crt\n          - name: other\n            array_fqdns: [x]\n")
            result, applied = custom_pages.apply_everpure_certificates(
                text, folder, ["fa01.example.com", "fb01.example.com", "fx01.example.com"])
            self.assertEqual(applied, ["fa01.example.com", "fb01.example.com"])
            entries = yaml.safe_load(result)["everpure"]["settings"]["security"]["certificates"]["array_certificates"]
            self.assertEqual([entry["name"] for entry in entries], ["fa01-cert", "other", "fb01-cert"])
            self.assertEqual(entries[0]["certificate_file"], str(folder / "fa01.example.com.crt"))
            self.assertNotIn("intermediate_certificate_file", entries[0])
            self.assertEqual(entries[2]["intermediate_certificate_file"], str(folder / "fb01.example.com.intermediate.crt"))
            self.assertEqual(entries[2]["private_key_file"], str(folder / "fb01.example.com.key"))

    def test_gitops_push_command(self):
        import types
        operators = {"openshift": {"destination_directory": "/srv/gitops",
                                   "operators": {"openshift_gitops": {"gitops_repo_url": "https://git.example.com/g.git"}}}}
        rc = types.SimpleNamespace(model=lambda target: operators, ui=types.SimpleNamespace(
            python=lambda: "python3", repository=REPOSITORY),
            state={"gitops_repository": {"branch": "lab", "author_name": "Ops", "username": "svc"}})
        command = pages.gitops_push(rc)[0]
        self.assertEqual(command[1:], [str(REPOSITORY / "scripts/gitops_push.py"), "--directory", "/srv/gitops", "--url",
                                       "https://git.example.com/g.git", "--branch", "lab", "--author-name", "Ops"])
        self.assertEqual(pages.gitops_env(rc), {"AIPOD_GIT_USERNAME": "svc"})
        operators["openshift"]["operators"] = {}
        with self.assertRaises(ValueError):
            pages.gitops_push(rc)


class ReadmeImageTest(unittest.TestCase):
    def test_inlines_only_local_images(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "stage"
            (folder / "docs").mkdir(parents=True)
            (folder / "docs" / "flow.png").write_bytes(b"\x89PNG")
            (Path(directory) / "outside.png").write_bytes(b"\x89PNG")
            text = pages.inline_images("![a](docs/flow.png) ![b](../outside.png) ![c](https://x/y.png)", folder)
            self.assertIn("![a](data:image/png;base64,", text)
            self.assertIn("![b](../outside.png)", text)
            self.assertIn("![c](https://x/y.png)", text)


class IserverSetupTest(unittest.TestCase):
    def test_masks_tokens(self):
        self.assertEqual(iserver_setup.mask("Identity token: abc"), "Identity token: ********")
        self.assertEqual(iserver_setup.mask('  "access_token": "abc",'), '  "access_token": "********",')
        self.assertEqual(iserver_setup.mask("Registry: registry.isovalent.com"), "Registry: registry.isovalent.com")

    def test_missing_secret_exits(self):
        os.environ.pop("ocp_console_token", None)
        with self.assertRaises(SystemExit):
            iserver_setup.secret("ocp_console_token")


if __name__ == "__main__":
    unittest.main()
