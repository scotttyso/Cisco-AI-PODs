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
from aipod_webui import custom_pages, pages, panels, seeds, stage_inventory  # noqa: E402
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

    def test_registration_hosts_and_secrets(self):
        legacy = {"organization": "Prod", "devices": {"c240-1": {"ip": "10.0.0.42", "netmask": "255.255.255.0"}}}
        hosts = stage_inventory.registration_hosts(self.ROWS, legacy)
        self.assertEqual(set(hosts), {"fi-a", "c845-1", "c240-1"})
        cimc = hosts["c240-1"]["ucs"]["cimc"]
        self.assertEqual((cimc["ip"], cimc["dhcp_ip"], cimc["netmask"]), ("10.0.0.42", "198.18.0.42", "255.255.255.0"))
        self.assertEqual(cimc["pass_ref"], "UCS_CIMC_PASSWORD")
        self.assertEqual(hosts["fi-a"]["ucs"]["platform"], "domain")
        self.assertEqual(hosts["fi-a"]["ucs"]["cimc"]["pass_ref"], "UCS_FI_PASSWORD")
        self.assertEqual((hosts["fi-a"]["ucs"]["organization"], hosts["fi-a"]["ucs"]["resource_group"]), ("Prod", "Prod"))
        secrets = dict(stage_inventory.required_secrets(self.ROWS)["intersight-registration"])
        self.assertEqual(set(secrets), {"vault_intersight_api_key_id", "vault_intersight_api_private_key",
                                        "vault_ucs_fi_password", "vault_ucs_cimc_password",
                                        "vault_hgx_bmc_password"})
        self.assertEqual(hosts["c845-1"]["ucs"]["cimc"]["pass_ref"], "HGX_BMC_PASSWORD")

    def test_registration_targets_override_and_orgs(self):
        state = {"organizations": [{"organization": "default", "resource_group": "default"},
                                   {"organization": "AI", "resource_group": "AI-RG"}],
                 "cimc_username": "ops",
                 "targets": [{"id": "c240-1", "hostname": "c240-1", "role": "ucs-server", "address": "198.18.0.42",
                              "static_ip": "", "organization": "AI", "factory_default": True, "override": True,
                              "username": "root"},
                             {"id": "c240-2", "hostname": "c240-2", "role": "ucs-server", "address": "198.18.0.43",
                              "organization": "gone"}]}
        hosts = stage_inventory.registration_hosts(self.ROWS, state)
        self.assertEqual(set(hosts), {"c240-1", "c240-2"})
        first, second = hosts["c240-1"]["ucs"], hosts["c240-2"]["ucs"]
        self.assertEqual((first["cimc"]["user"], first["cimc"]["pass_ref"], first["cimc"]["ip"]),
                         ("root", "C240_1_CIMC_PASSWORD", "198.18.0.42"))
        self.assertEqual((first["organization"], first["resource_group"], first["factory_default"]), ("AI", "AI-RG", True))
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
