"""Workflow sections, sub-pages, and the generic stage page builder for the Automation UI."""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml
from nicegui import run, ui

from . import custom_pages, intersight_policies, seeds, stage_inventory
from .dhcp_model import build_dhcp_model, default_gateway, host_interfaces, suggest_network
from .panels import (Action, CredentialsPanel, FileSpec, JobConsole, RunContext, UiContext, Workbench, Workbenches,
                     collapsible,
                     model_secret_fields, secret, show_problems, write_text)
from .vault import TOP, SecretField
from .yaml_editor import YamlEditor, validate_yaml

INTERSIGHT_KEY_ID = secret("vault_intersight_api_key_id", "Intersight API key ID",
                           (TOP, "vault_intersight_api_key_id"), ("intersight", "intersight_api_key_id"))
INTERSIGHT_SECRET_KEY = secret("vault_intersight_api_private_key", "Intersight API secret key (PEM)",
                               (TOP, "vault_intersight_api_private_key"), ("intersight", "intersight_secret_key"),
                               multiline=True, help="Paste or upload the PEM secret key downloaded with the API key.")
ND_ADMIN = secret("vault_nd_admin_password", "Nexus Dashboard admin password",
                  (TOP, "vault_nd_admin_password"), ("nexus_dashboard", "nexus_dashboard_password"))
ND_SWITCH = secret("switch_password", "Fabric switch admin password", ("nexus_dashboard", "switch_password"),
                   (TOP, "vault_switch_password"),
                   help="Password Nexus Dashboard uses to discover and add the switches.")
OCP_CONSOLE_TOKEN = secret("ocp_console_token", "console.redhat.com API token", ("openshift", "ocp_console_token"),
                           help="https://console.redhat.com/openshift/token - Load Token, then copy it here.")
OCP_PULL_SECRET = secret("ocp_pull_secret", "OpenShift pull secret (JSON)", ("openshift", "ocp_pull_secret"),
                         multiline=True, help="https://console.redhat.com/openshift/install/pull-secret")
LDAP_BIND = secret("ldap_bind_password", "LDAP bind password", ("openshift", "ldap_bind_password"),
                   help="Service account password for bind_dn. Also settable in Initial Inventory > Shared services > LDAP.")
ISOVALENT_TOKEN = secret("isovalent_registry_token", "Isovalent registry identity token",
                         ("openshift", "isovalent_registry_token"),
                         help="Identity token from https://docs.isovalent.com/iep/latest/platform/registry.html")
GITOPS_TOKEN = dataclasses.replace(
    secret("gitops_git_token", "GitOps repository access token", ("openshift", "gitops_git_token"),
           help="HTTPS token (for example a GitHub fine-grained token with Contents read/write) used by Push to "
                "GitOps repository. Not needed for SSH remotes that use this server's SSH key."), optional=True)
OCP_API = (secret("openshift_api_url", "OpenShift API URL (optional when a kubeconfig is set)",
                  ("openshift", "openshift_api_url")),
           secret("openshift_token_id", "OpenShift API token (optional when a kubeconfig is set)",
                  ("openshift", "openshift_token_id")))
KNOWN_SECRETS = {item.key: item for item in (INTERSIGHT_KEY_ID, INTERSIGHT_SECRET_KEY, ND_ADMIN)}
INTERSIGHT_KEYS = (INTERSIGHT_KEY_ID.key, INTERSIGHT_SECRET_KEY.key)


@dataclass(frozen=True)
class PageSpec:
    key: str
    title: str
    icon: str
    stage: str = ""
    summary: str = ""
    files: tuple[FileSpec, ...] = ()
    # Separate titled Variables sections; used instead of ``files``.
    file_groups: tuple[tuple[str, tuple[FileSpec, ...]], ...] = ()
    actions: tuple[Action, ...] = ()
    secrets: Callable[["PageHandle"], list[SecretField]] | None = None
    form: Callable[["PageHandle"], None] | None = None
    on_save: Callable[["PageHandle", str, str], None] | None = None
    notes: tuple[str, ...] = ()
    group: str = ""
    # The page form renders its own credential inputs; the page panel only tracks what actions need.
    inline_secrets: bool = False
    # Secret key -> where it is entered (another page or a form card); still checked before runs.
    hidden_secrets: dict[str, str] = field(default_factory=dict)
    # Rendered inside the Passwords and secrets section, above the inputs (for example the Intersight policy choices).
    secrets_header: Callable[["PageHandle"], None] | None = None
    # Folders below host_vars where the user can upload extra YAML files: one per Variables section (file_groups),
    # or one for ``files``. Empty entries disable uploads for that section.
    upload_dirs: tuple[str, ...] = ()

    @property
    def full_title(self) -> str:
        return f"{self.group} - {self.title}" if self.group else self.title


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    icon: str
    pages: tuple[PageSpec, ...] = field(default_factory=tuple)


@dataclass
class PageHandle:
    """What a page form can reach: the shared context, its saved state, and the page panels."""

    context: UiContext
    spec: PageSpec
    workbench: Workbench | Workbenches | None = None
    credentials: CredentialsPanel | None = None

    def state(self, key: str = "") -> dict:
        return self.context.store.page_state(key or self.spec.key)

    def save_state(self, values: dict, key: str = "") -> None:
        state = self.state(key)
        state.update(values)
        self.context.store.save_page_state(key or self.spec.key, state)

    def models(self) -> list[dict]:
        return self.workbench.models() if self.workbench else []

    def refresh_credentials(self) -> None:
        if self.credentials:
            self.credentials.render()


# --------------------------------------------------------------------------------------------------- command helpers

def script(rc: RunContext, path: str, *arguments: str) -> list[str]:
    return [rc.ui.python(), str(rc.ui.repository / path), *arguments]


def playbook(rc: RunContext, path: str, *arguments: str) -> list[str]:
    return ["ansible-playbook", str(rc.ui.repository / path), *arguments]


def deploy(role: str, *extra: str) -> Callable[[RunContext], list[list[str]]]:
    return lambda rc: [rc.ui.deploy_args() + ["--role", role, *extra]]


def phase2(tags: str) -> Callable[[RunContext], list[list[str]]]:
    return lambda rc: [playbook(rc, "playbooks/deploy_openshift_phase2.yaml", "-e", f"host_vars_dir={rc.ui.host_vars_dir}",
                                "--tags", tags)]


OCP_UPLOADS = {"ocp-cluster": "openshift/uploads/install", "ocp-certificates": "openshift/uploads/certificates",
               "ocp-ldap": "openshift/uploads/ldap"}


def apply_certificates(rc: RunContext) -> list[list[str]]:
    state = {**rc.ui.store.page_state("ocp-cluster"), **rc.ui.store.page_state("ocp-certificates")}
    try:
        custom_pages.write_certificates_vars(rc.ui, state.get("cluster_name", ""), state.get("base_dns_domain")
                                             or rc.ui.store.shared_services().get("domain_name", ""))
    except ValueError:
        # An uploaded certificates YAML may point at certificates created outside this page.
        if not any(key.startswith(OCP_UPLOADS["ocp-certificates"] + "/") for key in rc.files):
            raise
    return phase2("certificates")(rc)


def ocp_env(rc: RunContext) -> dict[str, str]:
    kubeconfig = rc.ui.store.page_state("ocp-cluster").get("kubeconfig", "")
    return {"KUBECONFIG": kubeconfig, "K8S_AUTH_KUBECONFIG": kubeconfig} if kubeconfig else {}


OPERATORS_TARGET = "openshift/operators.ezai.yaml"


def gitops_push(rc: RunContext) -> list[list[str]]:
    """Commit openshift.destination_directory and push it to openshift.operators.openshift_gitops.gitops_repo_url."""
    openshift = rc.model(OPERATORS_TARGET).get("openshift") or {}
    directory = str(openshift.get("destination_directory") or "").strip()
    url = str(((openshift.get("operators") or {}).get("openshift_gitops") or {}).get("gitops_repo_url") or "").strip()
    if not (directory and url):
        raise ValueError("Set destination_directory and openshift_gitops.gitops_repo_url, then Save")
    state = rc.state.get("gitops_repository") or {}
    command = script(rc, "scripts/gitops_push.py", "--directory", directory, "--url", url,
                     "--branch", str(state.get("branch") or "main"))
    for option, key in (("--author-name", "author_name"), ("--author-email", "author_email")):
        if state.get(key):
            command += [option, str(state[key])]
    return [command]


def gitops_env(rc: RunContext) -> dict[str, str]:
    username = str((rc.state.get("gitops_repository") or {}).get("username") or "")
    return {"AIPOD_GIT_USERNAME": username} if username else {}


def write_devices(rc: RunContext, roles: tuple[str, ...], name: str) -> Path:
    rows = rc.ui.store.inventory()
    selected = seeds.by_role(rows, *roles) if roles else [row for row in rows if row.get("hostname")]
    devices = [{"hostname": row["hostname"], "ip": row.get("ip", ""), "role": seeds.row_role(row)}
               for row in selected if row.get("ip")]
    if not devices:
        raise ValueError("No inventory devices with an address match this check. Save the Initial Inventory first.")
    path = rc.ui.output_dir / "inventory" / f"devices-{name}.json"
    write_text(path, json.dumps(devices, indent=2))
    return path


def reachability(name: str, *roles: str) -> Callable[[RunContext], list[list[str]]]:
    return lambda rc: [script(rc, "00-environment-prep/automation/scripts/check_reachability.py",
                              "--devices", str(write_devices(rc, roles, name)))]


def check_action(name: str, label: str, *roles: str, group: str = "Pre-check") -> Action:
    return Action(f"reach-{name}", label, "network_ping", reachability(name, *roles), group=group, files=False,
                  tooltip="Ping and probe TCP 22/443 on each device's inventory address.")


def collect_intersight_macs(rc: RunContext) -> list[list[str]]:
    rows = seeds.by_role(rc.ui.store.inventory(), "ucs-blade", "ucs-server")
    if not rows:
        raise ValueError("No UCS servers in the initial inventory")
    arguments = []
    for row in rows:
        arguments += ["--profile", row["hostname"]]
        if row.get("serial_number"):
            arguments += ["--serial", f"{row['hostname']}={row['serial_number']}"]
    return [script(rc, "05-mgmt-nodes-ucs/automation/scripts/collect_intersight_macs.py", *arguments,
                   "--output", str(rc.ui.macs_dir / "intersight.json"))]


def collect_redfish_macs(rc: RunContext) -> list[list[str]]:
    return [script(rc, "06-workload-nodes-ucs/automation/scripts/collect_redfish_macs.py",
                   "--inventory-dir", str(rc.inventory.parent), "--output", str(rc.ui.macs_dir / "redfish.json"))]


INTERSIGHT_MACS = Action("macs-intersight", "Collect MACs from Intersight", "settings_ethernet", collect_intersight_macs,
                         group="Tools", secrets=INTERSIGHT_KEYS, files=False,
                         tooltip="Read vNIC / adapter MACs from the server profiles; OpenShift pages pre-fill from them.")
REDFISH_MACS = Action("macs-redfish", "Collect MACs from BMC Redfish", "developer_board", collect_redfish_macs,
                      group="Tools", secrets=("*",), inventory=True, files=False,
                      tooltip="Read NIC MACs from the CIMC / BMC Redfish API of standalone and HGX servers.")


def model_secrets(handle: PageHandle) -> list[SecretField]:
    return model_secret_fields(handle.models())


def stage_secrets(pairs: list[tuple[str, str]]) -> list[SecretField]:
    return [KNOWN_SECRETS.get(key) or secret(key, label) for key, label in pairs]


def saved_nd_cluster(context: UiContext) -> dict:
    path = context.host_vars_dir / "nexus_dashboard" / "cluster.ezai.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, yaml.YAMLError):
        return {}
    cluster = ((data or {}).get("nexus_dashboard") or {}).get("cluster")
    return cluster if isinstance(cluster, dict) else {}


# ------------------------------------------------------------------------------------------------------- Network

def nd_cluster_secrets(handle: PageHandle) -> list[SecretField]:
    pairs = stage_inventory.required_secrets(handle.context.store.inventory(), saved_nd_cluster(handle.context))
    return stage_secrets(pairs["nd-cluster"])


def nd_phase(phase: str) -> Callable[[RunContext], list[list[str]]]:
    return lambda rc: [script(rc, "01-nd-cluster/automation/scripts/main.py", phase, "--ansible-inventory", str(rc.inventory))]


def nd_full_deploy(rc: RunContext) -> list[list[str]]:
    vault = str(rc.ui.vault.vault_file)
    return [playbook(rc, "01-nd-cluster/automation/playbooks/01_nd_cluster.yml", "-i", str(rc.inventory),
                     "-e", f"aipod_vault_file={vault}", "-e", f"nd_vault_file={vault}")]


def nd_collections(rc: RunContext) -> list[list[str]]:
    return [["bash", str(rc.ui.repository / "scripts/build_collection.sh")],
            ["ansible-galaxy", "collection", "install", "-r",
             str(rc.ui.repository / "01-nd-cluster/automation/requirements-aipod-inf.yml"),
             "-p", str(rc.ui.repository / "build/galaxy/01-nd-cluster")]]


ND_CLUSTER_ACTIONS = (
    Action("precheck", "Precheck", "fact_check", nd_phase("precheck"), group="Pre-check", secrets=("*",), inventory=True,
           tooltip="CIMC reachability, credentials, ISO, DNS/NTP, and address plan checks."),
    Action("deploy", "Deploy cluster", "rocket_launch", nd_full_deploy, secrets=("*",), inventory=True,
           confirm="Installs Nexus Dashboard on all nodes through CIMC vMedia and forms the cluster. "
                   "Existing node content is overwritten."),
    Action("node1", "Install node 1", "looks_one", nd_phase("node1"), secrets=("*",), inventory=True,
           confirm="Boot the bootstrap node from the ND ISO and install it."),
    Action("bootstrap", "Bootstrap cluster", "hub", nd_phase("bootstrap"), secrets=("*",), inventory=True),
    Action("secondary", "Install secondaries", "filter_2", nd_phase("secondary"), secrets=("*",), inventory=True,
           confirm="Install the secondary nodes and join them to the cluster."),
    Action("validate", "Validate cluster", "verified", nd_phase("validate"), group="Post-check", secrets=("*",),
           inventory=True),
    Action("collections", "Install stage collections", "extension", nd_collections, group="Tools", files=False),
)


ND_ACCESS_PAGE = "Network > Nexus Dashboard > Cluster Deployment"


def nd_access(context: UiContext) -> tuple[str, str]:
    """Nexus Dashboard URL and username from the Cluster Deployment page (older fabric-page state as fallback)."""
    state = {**context.store.page_state("nd-fabrics"), **context.store.page_state("nd-cluster")}
    url = state.get("nd_url") or custom_pages.default_nd_url(saved_nd_cluster(context))
    return url, state.get("nd_username") or "admin"


def nd_env(rc: RunContext) -> dict[str, str]:
    url, username = nd_access(rc.ui)
    if not url:
        raise ValueError(f"Set the Nexus Dashboard URL under {ND_ACCESS_PAGE}")
    return {"ND_URL": url, "ND_USERNAME": username}


ND_FABRIC_SCRIPT = "scripts/nd_fabric.py"


def merge_models(left: dict, right: dict) -> dict:
    """Recursive merge like the deployment playbooks: mappings merge, anything else (lists too) is replaced."""
    result = dict(left)
    for key, value in right.items():
        result[key] = (merge_models(result[key], value) if isinstance(result.get(key), dict) and isinstance(value, dict)
                       else value)
    return result


def run_config(rc: RunContext, target: str, upload_dir: str) -> Path:
    """The page file, or for scripts that read a single file, a run copy with the page's uploaded YAML merged in."""
    main = rc.files[target]
    uploads = [path for key, path in sorted(rc.files.items())
               if key.startswith(f"{upload_dir}/") and key != target and path.is_file()]
    if not uploads:
        return main
    merged: dict = {}
    for path in (main, *uploads):
        model = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
        if not isinstance(model, dict):
            raise ValueError(f"{path} is not a YAML mapping")
        merged = merge_models(merged, model)
    folder = rc.ui.output_dir / "merged"
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    output = folder / Path(target).name
    output.write_text(yaml.safe_dump(merged, sort_keys=False), encoding="utf-8")
    output.chmod(0o600)
    return output


def fabric_uploads(kind: str) -> str:
    return f"nexus_dashboard/uploads/{kind}-fabric"


def fabric_report(context: UiContext, kind: str) -> Path:
    """Port discovery report written by ``nd_fabric.py ports`` and read by the fabric page port table."""
    return context.output_dir / "reports" / f"{kind}-fabric-ports.json"


def nd_fabric(target: str, command: str, kind: str = "") -> Callable[[RunContext], list[list[str]]]:
    def build(rc: RunContext) -> list[list[str]]:
        if command == "list":
            return [script(rc, ND_FABRIC_SCRIPT, "list")]
        extra = ["--report", str(fabric_report(rc.ui, kind))] if command == "ports" else []
        config = run_config(rc, target, fabric_uploads(target.rsplit("/", 1)[-1].removesuffix("-fabric.ezai.yaml")))
        return [script(rc, ND_FABRIC_SCRIPT, command, "--config", str(config), *extra)]
    return build


OPENSHIFT_UPLOAD_NOTE = ("Use the upload button in Variables to add your own YAML files (listed as uploads/...). Every "
                         "OpenShift action merges all host_vars/openshift files, uploads last, so an uploaded key "
                         "overrides the page file.")
UPLOAD_NOTE = ("Use the upload button in Variables to add your own YAML files (listed as uploads/...). They are merged "
               "with this page's file when an action runs: mappings merge, and a list in an uploaded file replaces "
               "the list of the same key.")


def fabric_page(key: str, title: str, icon: str, stage: str, summary: str, kind: str, notes: tuple[str, ...] = (),
                extra_actions: tuple[Action, ...] = (),
                page_secrets: Callable[[PageHandle], list[SecretField]] | None = None) -> PageSpec:
    target = f"nexus_dashboard/{kind}-fabric.ezai.yaml"
    secrets = (ND_ADMIN.key,)
    switch = secrets + (ND_SWITCH.key,)
    return PageSpec(
        key, title, icon, stage, summary,
        files=(FileSpec("examples/nexus_dashboard/fabrics.ezai.yaml", target, f"fabric_{kind}", f"{kind}-fabric.ezai.yaml"),),
        actions=(
            check_action(f"{kind}-switches", "Switch reachability", f"switch-{kind}"),
            Action("create", "Create / update fabric", "add_circle", nd_fabric(target, "create"), secrets=secrets,
                   env=nd_env, confirm="Creates the fabric on Nexus Dashboard (or updates its settings and telemetry) "
                                       "and enables POAP when poap.enabled is true.",
                   tooltip="Telemetry defaults to out-of-band over mgmt0 in the management VRF."),
            Action("claim", "Claim POAP switches", "how_to_reg", nd_fabric(target, "claim"), secrets=switch, env=nd_env,
                   confirm="Waits for every switch in this file to appear in the fabric's POAP list (power them on "
                           "with no configuration), claims them by serial number with the hostname, management "
                           "address, and admin password, waits until they join the fabric, then sets their roles.",
                   tooltip="External DHCP: the DHCP Bootstrap scope needs option 66 = Nexus Dashboard and option 67 "
                           "= poap_dcnm.py."),
            Action("add", "Add configured switches", "dns", nd_fabric(target, "add"), secrets=switch, env=nd_env,
                   confirm="Discovers switches that already have a management address and admin account (no POAP) "
                           "and adds them to the fabric. Switch configuration may be overwritten when the fabric is "
                           "deployed."),
            Action("ports", "Discover ports", "settings_input_hdmi", nd_fabric(target, "ports", kind),
                   secrets=(ND_SWITCH.key,),
                   tooltip="SSH to each switch and list the interfaces with optics installed and their LLDP "
                           "neighbors. Assign fabric / host roles in the Ports section afterwards."),
            Action("apply-ports", "Apply port roles", "tune", nd_fabric(target, "apply-ports"), secrets=secrets,
                   env=nd_env, confirm="Sets the host interfaces in this file to the host trunk policy (jumbo MTU) "
                                       "on Nexus Dashboard. Run Deploy fabric afterwards."),
            Action("deploy", "Deploy fabric", "rocket_launch", nd_fabric(target, "deploy"), secrets=secrets, env=nd_env,
                   confirm="Recalculates the fabric and deploys the pending configuration to every switch."),
            Action("status", "Fabric status", "lan", nd_fabric(target, "status"), group="Post-check", secrets=secrets,
                   env=nd_env),
            *extra_actions,
        ),
        secrets=page_secrets or (lambda handle: [ND_ADMIN, ND_SWITCH]),
        hidden_secrets={ND_ADMIN.key: f"entered under {ND_ACCESS_PAGE}"},
        form=custom_pages.fabric_form, upload_dirs=(fabric_uploads(kind),),
        notes=notes + ("Nexus Dashboard URL, username, and admin password come from Cluster Deployment. The Switches "
                       "section starts from the initial inventory rows with this fabric's switch role; add or remove "
                       "switches there and the YAML switches list follows.",
                       "Day-0 flow: Create / update fabric (enables POAP), power on the switches, Claim POAP "
                       "switches, Discover ports, assign port roles, Apply port roles, Deploy fabric.",
                       UPLOAD_NOTE),
        group="Nexus Dashboard",
    )


BACKEND_PLAYBOOK = "02-backend-fabric-nxos/automation/playbooks/02_backend_fabric.yml"


def saved_backend_fabrics(context: UiContext) -> list[dict]:
    return stage_inventory.saved_backend_fabrics(context.host_vars_dir)


def backend_secrets(handle: PageHandle) -> list[SecretField]:
    pairs = stage_inventory.required_secrets(handle.context.store.inventory(), saved_nd_cluster(handle.context),
                                             saved_backend_fabrics(handle.context))
    return stage_secrets(pairs["backend-fabric"])


def backend_inventory(rc: RunContext) -> Path:
    if not saved_backend_fabrics(rc.ui):
        raise ValueError("Save the backend fabric file with at least one switch first.")
    if not saved_nd_cluster(rc.ui).get("nodes"):
        raise ValueError("The stage 02 workflow deploys through the Nexus Dashboard cluster; save the Cluster Deployment "
                         "page first.")
    return rc.inventory


def backend_workflow(rc: RunContext) -> list[list[str]]:
    return [playbook(rc, BACKEND_PLAYBOOK, "-i", str(backend_inventory(rc)),
                     "-e", f"aipod_vault_file={rc.ui.vault.vault_file}")]


def backend_cabling(rc: RunContext) -> list[list[str]]:
    inventory = backend_inventory(rc)
    return [script(rc, "02-backend-fabric-nxos/automation/scripts/check_be_core_connectivity.py", str(inventory.parent),
                   "--require-inventory-match", "--vault-file", str(rc.ui.vault.vault_file),
                   "--report-prefix", str(rc.ui.output_dir / "reports" / "backend-cabling"))]


def backend_collections(rc: RunContext) -> list[list[str]]:
    return [["bash", str(rc.ui.repository / "scripts/build_collection.sh")],
            ["ansible-galaxy", "collection", "install", "-r",
             str(rc.ui.repository / "02-backend-fabric-nxos/automation/requirements-backend-fabric.yml"),
             "-p", str(rc.ui.repository / "build/galaxy/02-backend-fabric-nxos")]]


BACKEND_ACTIONS = (
    Action("cabling", "Spine-leaf cabling gate", "cable", backend_cabling, group="Pre-check", secrets=("*",),
           inventory=True, files=False, tooltip="Read-only LLDP check of the spine-to-leaf links over SSH. Reports are "
                                               "written to the environment's reports/ folder."),
    Action("stage02", "Run backend fabric workflow", "account_tree", backend_workflow, secrets=("*",), inventory=True,
           confirm="Runs the stage 02 workflow: read-only cabling gate, switch discovery access (SSH, SHA/AES), then "
                   "creates the AI backend fabrics on Nexus Dashboard, adds the switches, and deploys. Switch "
                   "configuration is changed."),
    Action("stage02-collections", "Install stage collections", "extension", backend_collections, group="Tools",
           files=False),
)


NETWORK_CHECK_ACTIONS = (
    check_action("all", "All inventory devices", group="Pre-check"),
    check_action("switches", "Switches", "switch-backend", "switch-frontend", "switch-mgmt"),
    check_action("nd-nodes", "Nexus Dashboard CIMCs", "nd-node"),
    Action("nd-precheck", "Nexus Dashboard precheck", "fact_check", nd_phase("precheck"), group="Pre-check",
           secrets=("*",), inventory=True, files=False),
    Action("nd-validate", "Nexus Dashboard cluster health", "verified", nd_phase("validate"), group="Post-check",
           secrets=("*",), inventory=True, files=False),
    Action("nd-fabrics", "Nexus Dashboard fabrics", "list", nd_fabric("", "list"), group="Post-check",
           secrets=(ND_ADMIN.key,), env=nd_env, files=False),
    check_action("post-all", "Device reachability", group="Post-check"),
)


# ------------------------------------------------------------------------------------------------------- Compute

def registration_state(context: UiContext) -> dict:
    return context.store.page_state("intersight-registration")


def registration_secrets(handle: PageHandle) -> list[SecretField]:
    pairs = stage_inventory.required_secrets(handle.context.store.inventory(),
                                             registration=registration_state(handle.context))
    return stage_secrets(pairs["intersight-registration"])


def static_ip(apply: bool) -> Callable[[RunContext], list[list[str]]]:
    return lambda rc: [script(rc, "05-mgmt-nodes-ucs/automation/scripts/set_static_mgmt_ip.py",
                              "--inventory-dir", str(rc.inventory.parent), *(["--apply"] if apply else []))]


def factory_password(apply: bool) -> Callable[[RunContext], list[list[str]]]:
    return lambda rc: [script(rc, "05-mgmt-nodes-ucs/automation/scripts/set_initial_password.py",
                              "--inventory-dir", str(rc.inventory.parent), *(["--apply"] if apply else []))]


def register_all(rc: RunContext) -> list[list[str]]:
    return factory_password(True)(rc) + static_ip(True)(rc) + claim(rc)


def claim(rc: RunContext) -> list[list[str]]:
    return [playbook(rc, "05-mgmt-nodes-ucs/automation/playbooks/05_mgmt_nodes_ucs.yml", "-i", str(rc.inventory),
                     "-e", f"aipod_vault_file={rc.ui.vault.vault_file}", "-e", "ucs_claim_inventory_group=ucs_registration")]


REGISTRATION_ACTIONS = (
    check_action("registration", "Device reachability", *seeds.REGISTRATION_ROLES),
    Action("static-preview", "Static address plan", "preview", static_ip(False), group="Pre-check", secrets=("*",),
           inventory=True, files=False, tooltip="Show the DHCP-to-static changes without applying them."),
    Action("register", "Register all targets", "rocket_launch", register_all, secrets=("*",), inventory=True,
           files=False, confirm="For every target: changes factory default passwords, moves CIMC / BMC addresses to "
                                "their static address, then claims the targets into Intersight."),
    Action("password-preview", "Factory default password plan", "preview", factory_password(False), group="Pre-check",
           secrets=("*",), inventory=True, files=False),
    Action("password-apply", "Change factory default passwords", "password", factory_password(True), secrets=("*",),
           inventory=True, files=False,
           confirm="Logs into targets marked factory default with 'password' and sets the CIMC / BMC password."),
    Action("static-apply", "Convert to static addresses", "pin", static_ip(True), secrets=("*",), inventory=True,
           files=False, confirm="Sets each CIMC / BMC management interface to the static address in the Targets list. "
                                "Connections to the old DHCP address drop."),
    Action("claim", "Claim into Intersight", "app_registration", claim, secrets=("*",), inventory=True, files=False,
           confirm="Claims every target into the Intersight account, in the default organization and resource "
                   "group. Use Intersight - System (Orgs) to move them."),
    check_action("registration-post", "Device reachability", *seeds.REGISTRATION_ROLES, group="Post-check"),
)


def intersight_secrets(handle: PageHandle) -> list[SecretField]:
    """API key, then values the saved YAML references (required), then the enabled policy secrets (form)."""
    page = handle.spec.key
    enabled = intersight_policies.counts(handle.state(), page)
    referenced = [item for item in model_secrets(handle) if item.key != intersight_policies.LDAP_ALIAS]
    uses_ldap = "ldap" in enabled or len(referenced) != len(model_secrets(handle))
    return ([INTERSIGHT_KEY_ID, INTERSIGHT_SECRET_KEY] + referenced + intersight_policies.fields(handle.state(), page)
            + ([LDAP_BIND] if uses_ldap else []))


INTERSIGHT_HIDDEN = {LDAP_BIND.key: "Initial Inventory - Shared services - LDAP"}


def everpure_secrets(handle: PageHandle) -> list[SecretField]:
    """Values the saved YAML references (API tokens and any others), then the enabled policy secrets (form)."""
    enabled = intersight_policies.counts(handle.state(), "everpure")
    models = model_secrets(handle)
    referenced = [item for item in models if item.key != intersight_policies.LDAP_ALIAS]
    uses_ldap = "everpure_ldap" in enabled or len(referenced) != len(models)
    return referenced + intersight_policies.fields(handle.state(), "everpure") + ([LDAP_BIND] if uses_ldap else [])


def intersight_actions(scope: str, label: str) -> tuple[Action, ...]:
    check = Action("check", "Validate (check mode)", "fact_check",
                   deploy("intersight", "--intersight-scope", scope, "--check"), group="Pre-check", secrets=("*",))
    if scope == "system":
        return (check, Action("deploy", "Deploy to Intersight", "cloud_upload",
                              deploy("intersight", "--intersight-scope", scope), secrets=("*",),
                              confirm="Creates or updates the organizations and resource groups in "
                                      "host_vars/intersight/system.ezai.yaml."))
    return (
        check,
        Action("deploy", "Deploy to Intersight", "cloud_upload", deploy("intersight", "--intersight-scope", scope),
               secrets=("*",),
               confirm=f"Creates or updates pools, policies, templates, and profiles from this page's {label} files "
                       f"(host_vars/intersight/{scope}/) plus the organizations in host_vars/intersight/system.ezai.yaml, "
                       "then deploys the profiles."),
        INTERSIGHT_MACS,
    )


def hgx_secrets(handle: PageHandle) -> list[SecretField]:
    hosts = stage_inventory.registration_hosts(handle.context.store.inventory(), registration_state(handle.context))
    references = {stage_inventory.HGX_PASSWORD_REF: "HGX BMC password"}
    for item in hosts.values():
        if item["ucs"]["device_role"] == "hgx-node":
            references.setdefault(item["ucs"]["cimc"]["pass_ref"], f"{item['ucs']['hostname']} BMC password")
    for model in handle.models():
        root = model.get("hgx_servers") if isinstance(model.get("hgx_servers"), dict) else {}
        settings = root.get("bmc_settings") if isinstance(root.get("bmc_settings"), dict) else {}
        if settings.get("password_ref"):
            references.setdefault(str(settings["password_ref"]), "HGX BMC password")
        for server in root.get("servers") or []:
            bmc = server.get("bmc") if isinstance(server, dict) and isinstance(server.get("bmc"), dict) else {}
            if bmc.get("password_ref"):
                references.setdefault(str(bmc["password_ref"]), f"{server.get('hostname', 'server')} BMC password")
    return [secret(stage_inventory.vault_key(reference), label, min_length=stage_inventory.FACTORY_PASSWORD_MIN,
                   help=f"Exported to the automation as {reference}. Used to configure the BMC and collect MACs. "
                        "C880A and C885A nodes use the separate HGX workflow, not Intersight claiming.")
            for reference, label in references.items()]


HGX_VARS = "hgx/hgx.ezai.yaml"
HGX_UPLOADS = "hgx/uploads"
HGX_FILE = FileSpec("examples/hgx/hgx.ezai.yaml", HGX_VARS, "hgx", "hgx.ezai.yaml (BMC settings)")


def hgx_bmc(apply: bool) -> Callable[[RunContext], list[list[str]]]:
    def build(rc: RunContext) -> list[list[str]]:
        return [script(rc, "06-workload-nodes-ucs/automation/scripts/configure_hgx_bmc.py",
                       "--vars", str(run_config(rc, HGX_VARS, HGX_UPLOADS)), *(["--apply"] if apply else []))]
    return build


def intersight_file(path: str, seed: str = "", optional: bool = True, note: str = "") -> FileSpec:
    """``examples/intersight/<path>`` saved as ``host_vars/intersight/<path>``; the label is the path below the page folder."""
    label = path.split("/", 1)[1] + (f" ({note})" if note else "")
    return FileSpec(f"examples/intersight/{path}", f"intersight/{path}", seed, label, optional)


# ---------------------------------------------------------------------------------------------------- OpenShift

def save_cluster_state(handle: PageHandle, target: str, content: str) -> None:
    try:
        data = yaml.safe_load(content) or {}
    except yaml.YAMLError:
        return
    bare = (((data.get("openshift") or {}).get("install") or {}).get("bare_metal")) or {}
    if not isinstance(bare, dict):
        return
    networking = bare.get("cluster_networking") or {}
    values = {"cluster_name": bare.get("cluster_name"), "base_dns_domain": bare.get("base_dns_domain"),
              "cluster_network": (networking.get("cluster_network") or {}).get("v4_cidr"),
              "service_network": (networking.get("service_network") or {}).get("v4_cidr")}
    gateway = (networking.get("machine_network_gateway") or {}).get("v4")
    try:
        values["machine_network"] = str(ipaddress.ip_interface(gateway).network) if gateway and "/" in str(gateway) else None
    except ValueError:
        values["machine_network"] = None
    handle.save_state({key: value for key, value in values.items() if value}, "ocp-cluster")


def iserver_setup(*arguments: str) -> Callable[[RunContext], list[list[str]]]:
    return lambda rc: [script(rc, "07-openshift-cluster/automation/scripts/iserver_setup.py", *arguments)]


def cluster_status(rc: RunContext) -> list[list[str]]:
    if not ocp_env(rc):
        raise ValueError("Set the kubeconfig path in the cluster settings on the Cluster Deployment page")
    return [["bash", "-c", "oc get clusterversion && oc get nodes -o wide && oc get co"]]


def linked(fields: list[SecretField], source: str) -> list[SecretField]:
    return [dataclasses.replace(item, source=source) for item in fields]


def ocp_cluster_secrets(handle: PageHandle) -> list[SecretField]:
    """The install YAML's own secrets, plus the Intersight and BMC credentials entered on the Compute pages."""
    return (model_secrets(handle) + linked(hgx_secrets(handle), "Compute - HGX Servers")
            + linked(registration_secrets(handle), "Compute - Intersight - Claim Targets"))


PHASE2_SECRETS = lambda handle: model_secrets(handle) + list(OCP_API)  # noqa: E731

SECTIONS = (
    Section("environment", "Environment Preparation", "construction", (
        PageSpec("inventory", "Initial Inventory", "dns", "00-environment-prep",
                 "Order spreadsheets, bootstrap addresses, and shared services (DNS, NTP, timezone, proxy). Saved "
                 "values pre-fill the DHCP reservations, Nexus Dashboard, and Compute pages."),
        PageSpec("dhcp", "DHCP Bootstrap", "lan", "00-environment-prep",
                 "Build and run the Kea DHCPv4 server that brings CIMC, UCS, and Nexus management interfaces online."),
        PageSpec("iso", "File Server", "folder_shared", "00-environment-prep",
                 "Installation media and other files served over HTTP by this deployment server."),
    )),
    Section("network", "Network", "hub", (
        PageSpec("nd-prechecks", "Pre-Checks", "fact_check", "01-nd-cluster",
                 "Validate that the physical network, CIMCs, and services are ready before deployment.",
                 actions=tuple(action for action in NETWORK_CHECK_ACTIONS if action.group == "Pre-check"),
                 secrets=nd_cluster_secrets, group="Nexus Dashboard"),
        PageSpec("nd-cluster", "Cluster Deployment", "dashboard", "01-nd-cluster",
                 "Install and form the Nexus Dashboard 4.x cluster through CIMC vMedia. Nodes come from the inventory "
                 "devices with the Nexus Dashboard node role.",
                 files=(FileSpec("examples/nexus_dashboard/cluster.ezai.yaml", "nexus_dashboard/cluster.ezai.yaml",
                                 "nd_cluster"),),
                 actions=ND_CLUSTER_ACTIONS, secrets=nd_cluster_secrets, form=custom_pages.nd_access_form,
                 hidden_secrets={ND_ADMIN.key: "Nexus Dashboard access section"}, group="Nexus Dashboard"),
        fabric_page("backend-fabric", "Backend Fabric", "settings_ethernet", "02-backend-fabric-nxos",
                    "GPU backend (east-west) NX-OS fabric managed by Nexus Dashboard.", "backend",
                    ("Run backend fabric workflow uses the stage 02 playbook with the inventory generated from this "
                     "environment: backend_settings and the switch username / passwordRef / fabricLinkInterfaces / "
                     "breakoutCommands fields feed it. The other actions run scripts/nd_fabric.py.",),
                    extra_actions=BACKEND_ACTIONS, page_secrets=backend_secrets),
        fabric_page("frontend-fabric", "Frontend Fabric", "router", "03-frontend-fabric-nxos",
                    "Frontend (north-south) NX-OS fabric.", "frontend"),
        fabric_page("mgmt-fabric", "Management Fabric", "device_hub", "03-mgmt-fabric-nxos",
                    "Out-of-band management network added to Nexus Dashboard.", "mgmt"),
        PageSpec("nd-postchecks", "Post Checks", "verified", "01-nd-cluster",
                 "Confirm the Nexus Dashboard cluster, fabrics, and devices are healthy after deployment.",
                 actions=tuple(action for action in NETWORK_CHECK_ACTIONS if action.group == "Post-check"),
                 secrets=nd_cluster_secrets, group="Nexus Dashboard"),
    )),
    Section("storage", "Storage", "sd_storage", (
        PageSpec("everpure", "Everpure", "storage", "04-storage-everpure",
                 "Everpure FlashArray / FlashBlade configuration and OpenShift storage integration.",
                 files=(FileSpec("examples/everpure/everpure.ezai.yaml", "everpure/everpure.ezai.yaml"),),
                 actions=(Action("check", "Validate (check mode)", "fact_check", deploy("everpure", "--check"),
                                 group="Pre-check", secrets=("*",)),
                          Action("deploy", "Deploy storage", "cloud_upload", deploy("everpure"), secrets=("*",),
                                 confirm="Configures the FlashArrays / FlashBlades in the saved file.")),
                 secrets=everpure_secrets, secrets_header=custom_pages.policy_secrets_selector,
                 hidden_secrets=INTERSIGHT_HIDDEN, upload_dirs=("everpure/uploads",),
                 form=custom_pages.everpure_certificates_form,
                 notes=("Use the upload button in Variables to add your own YAML files (listed as uploads/...); they "
                        "are merged with everpure.ezai.yaml when Validate or Deploy runs.",)),
    )),
    Section("compute", "Compute", "memory", (
        PageSpec("intersight-registration", "Claim Targets", "app_registration", "05-mgmt-nodes-ucs",
                 "Claim Fabric Interconnects, X-Direct domains, and standalone servers into Intersight and move "
                 "CIMC / BMC addresses from DHCP to static. Targets start from the initial inventory.",
                 actions=REGISTRATION_ACTIONS, secrets=registration_secrets, form=custom_pages.registration_form,
                 group="Intersight", inline_secrets=True),
        PageSpec("intersight-system", "System (Orgs)", "account_tree", "06-workload-nodes-ucs",
                 "Intersight organizations and resource groups. Claimed targets start in the default organization / "
                 "resource group; move them to another resource group here and add organizations that share it.",
                 files=(FileSpec("examples/intersight/system/system.ezai.yaml", "intersight/system.ezai.yaml", "system",
                                 "system.ezai.yaml (organizations and resource groups)"),),
                 actions=intersight_actions("system", "system"), secrets=lambda handle: [INTERSIGHT_KEY_ID,
                                                                                        INTERSIGHT_SECRET_KEY],
                 upload_dirs=("intersight/system/uploads",),
                 notes=("The default resource group is built in and always holds every target; it is not changed. A "
                        "target listed under another resource group is left out of the regenerated default list.",
                        "UCS Domains and UCS Servers deploy with these organizations, so deploy this page first.",
                        "Use the upload button in Variables to add your own YAML files (listed as uploads/...); they are "
                        "deployed with system.ezai.yaml from this page, UCS Domains, and UCS Servers."),
                 group="Intersight"),
        PageSpec("intersight-domains", "UCS Domains", "view_module", "06-workload-nodes-ucs",
                 "UCS domain and chassis policies, templates, and profiles for X-Direct and Fabric Interconnect "
                 "domains. Profile names come from the inventory hostnames. X-Series blade server profiles are on the "
                 "UCS Servers page.",
                 files=(intersight_file("domains/policies.ezai.yaml"),
                        intersight_file("domains/pools.ezai.yaml", note="IP pools for the Chassis IMC Access policy"),
                        intersight_file("domains/templates.ezai.yaml"),
                        intersight_file("domains/profiles.ezai.yaml", "domain_profiles", False)),
                 actions=intersight_actions("domains", "domain"), secrets=intersight_secrets,
                 secrets_header=custom_pages.policy_secrets_selector, hidden_secrets=INTERSIGHT_HIDDEN,
                 upload_dirs=("intersight/domains/uploads",),
                 notes=("Deploy and Validate use only this page's files plus the organizations from Intersight - System "
                        "(Orgs). policies.ezai.yaml holds every domain and chassis policy; remove the ones you do not "
                        "need. Files marked \"optional, not deployed\" are left out until saved; use the delete button "
                        "to remove a saved optional file.",
                        "Use the upload button in Variables to add your own YAML files (listed as uploads/...); they "
                        "are deployed with this page's files.",), group="Intersight"),
        PageSpec("intersight-servers", "UCS Servers", "dns", "06-workload-nodes-ucs",
                 "Server pools, policies, templates, and profiles for X-Series blades and standalone C-Series 2XX / "
                 "8XX servers. Profile names come from inventory hostnames.",
                 file_groups=(
                     ("X-Series variables", (
                         intersight_file("servers/x-series/pools/pools.ezai.yaml"),
                         intersight_file("servers/x-series/policies/compute.ezai.yaml"),
                         intersight_file("servers/x-series/policies/ethernet.ezai.yaml"),
                         intersight_file("servers/x-series/policies/lan_connectivity.ezai.yaml"),
                         intersight_file("servers/x-series/policies/management.ezai.yaml"),
                         intersight_file("servers/x-series/policies/environment.ezai.yaml"),
                         intersight_file("servers/x-series/policies/storage.ezai.yaml"),
                         intersight_file("servers/x-series/pools/fibre_channel_pools.ezai.yaml", note="Fibre Channel only"),
                         intersight_file("servers/x-series/policies/fibre_channel.ezai.yaml", note="Fibre Channel only"),
                         intersight_file("servers/x-series/policies/san_connectivity.ezai.yaml", note="Fibre Channel only"),
                         intersight_file("servers/x-series/templates.ezai.yaml"),
                         intersight_file("servers/x-series/profiles.ezai.yaml", "xseries_profiles"))),
                     ("Standalone variables", (
                         intersight_file("servers/standalone/policies/compute.ezai.yaml"),
                         intersight_file("servers/standalone/policies/management.ezai.yaml"),
                         intersight_file("servers/standalone/policies/environment.ezai.yaml"),
                         intersight_file("servers/standalone/templates.ezai.yaml"),
                         intersight_file("servers/standalone/profiles.ezai.yaml", "server_profiles")))),
                 actions=intersight_actions("servers", "server"), secrets=intersight_secrets,
                 secrets_header=custom_pages.policy_secrets_selector, hidden_secrets=INTERSIGHT_HIDDEN,
                 upload_dirs=("intersight/servers/x-series/uploads", "intersight/servers/standalone/uploads"),
                 notes=("Deploy and Validate use only this page's files plus the organizations from Intersight - System "
                        "(Orgs). Pools are X-Series only. Save only the server types you deploy; files marked "
                        "\"optional, not deployed\" are left out, and the delete button removes a saved optional "
                        "file.",
                        "Use the upload button in each Variables section to add your own YAML files (listed as "
                        "uploads/...); they are deployed with this page's files.",), group="Intersight"),
        PageSpec("hgx-nodes", "HGX Servers", "developer_board", "06-workload-nodes-ucs",
                 "C880A / C885A HGX nodes managed through the BMC Redfish API (not Intersight). Collected MACs pre-fill "
                 "the OpenShift node inventory and the NVIDIA Network Operator rules. The variables set the BMC "
                 "host name, DNS, NTP, and time-zone offset.",
                 files=(HGX_FILE,),
                 actions=(check_action("hgx", "BMC reachability", "hgx-node"),
                          Action("bmc-check", "Check BMC settings", "fact_check", hgx_bmc(False), group="Pre-check",
                                 secrets=("*",),
                                 tooltip="Read each BMC over Redfish and list the settings that differ (no changes)."),
                          Action("bmc-apply", "Configure BMC", "settings", hgx_bmc(True), secrets=("*",),
                                 confirm="Patches the host name / FQDN, DNS servers, NTP servers, and time-zone offset on "
                                         "each BMC in hgx.ezai.yaml. Changing the BMC interface settings briefly "
                                         "restarts BMC networking; the script waits and verifies."),
                          Action("macs", "Collect MACs from BMC Redfish", "developer_board",
                                 lambda rc: [script(rc, "06-workload-nodes-ucs/automation/scripts/collect_redfish_macs.py",
                                                    "--inventory-dir", str(rc.inventory.parent), "--role", "hgx-node",
                                                    "--output", str(rc.ui.macs_dir / "redfish-hgx.json"))],
                                 secrets=("*",), inventory=True, files=False),
                          Action("static-preview", "Static address plan", "preview", static_ip(False), group="Post-check",
                                 secrets=("*",), inventory=True, files=False)),
                 secrets=hgx_secrets, form=custom_pages.macs_summary, upload_dirs=(HGX_UPLOADS,),
                 notes=("The HGX BMC password is entered here. C880A and C885A nodes are excluded from Intersight claiming. Hosts "
                        "and their addresses come from the HGX rows on Claim Targets; a target with overridden "
                        "credentials there gets its own password field below.", UPLOAD_NOTE)),
    )),
    Section("kubernetes", "Kubernetes", "cloud", (
        PageSpec("ocp-console", "Console Registration", "key", "07-openshift-cluster",
                 "console.redhat.com API token and pull secret for iserver.",
                 actions=(Action("console", "Configure iserver console access", "key", iserver_setup("console"),
                                 secrets=(OCP_CONSOLE_TOKEN.key, OCP_PULL_SECRET.key), files=False),
                          Action("console-check", "Check console login", "verified", iserver_setup("console-check"),
                                 group="Post-check", files=False)),
                 secrets=lambda handle: [OCP_CONSOLE_TOKEN, OCP_PULL_SECRET], form=custom_pages.console_form,
                 group="OpenShift"),
        PageSpec("ocp-cluster", "Cluster Deployment", "rocket_launch", "07-openshift-cluster",
                 "Agent-based bare-metal install settings and node inventory. DNS, NTP, and nodes come from the "
                 "initial inventory; node MACs come from Intersight or the BMC Redfish API.",
                 files=(FileSpec("examples/openshift/install.ezai.yaml", "openshift/install.ezai.yaml", "ocp_install"),),
                 actions=(Action("check", "Validate (check mode)", "fact_check",
                                 deploy("openshift", "--openshift-only-stage", "phase1", "--check"), group="Pre-check",
                                 secrets=("*",)),
                          Action("phase1", "Prepare install (phase 1)", "build", deploy("openshift", "--openshift-only-stage",
                                                                                         "phase1"), secrets=("*",)),
                          Action("iserver", "Install cluster (iserver)", "rocket_launch",
                                 deploy("openshift", "--openshift-only-stage", "iserver"), secrets=("*",),
                                 confirm="Boots the nodes from the discovery ISO and installs OpenShift. Node disks are "
                                         "erased."),
                          Action("status", "Cluster status", "monitor_heart", cluster_status, group="Post-check",
                                 env=ocp_env, files=False),
                          INTERSIGHT_MACS, REDFISH_MACS),
                 secrets=ocp_cluster_secrets, form=custom_pages.ocp_cluster_form, on_save=save_cluster_state,
                 upload_dirs=(OCP_UPLOADS["ocp-cluster"],), notes=(OPENSHIFT_UPLOAD_NOTE,), group="OpenShift"),
        PageSpec("ocp-certificates", "Certificates", "verified_user", "07-openshift-cluster",
                 "API and *.apps ingress certificates: generate keys and CSRs, upload the signed chains, then apply.",
                 actions=(Action("apply", "Apply certificates", "verified_user", apply_certificates,
                                 secrets=("*",), env=ocp_env, files=False,
                                 confirm="Replaces the API and ingress certificates. The API server restarts."),),
                 files=(FileSpec("examples/openshift/certificates.ezai.yaml", custom_pages.CERTIFICATES_VARS,
                                 label="certificates.ezai.yaml (written from the generated keys and signed chains)",
                                 optional=True),),
                 upload_dirs=(OCP_UPLOADS["ocp-certificates"],),
                 secrets=lambda handle: list(OCP_API), form=custom_pages.certificates_form,
                 notes=("certificates.ezai.yaml is rewritten from the files above once the keys, signed chains, and CA "
                        "bundle all exist. To use certificates created elsewhere, upload a YAML file with "
                        "openshift.certificates (absolute paths on this server) instead.", OPENSHIFT_UPLOAD_NOTE),
                 group="OpenShift"),
        PageSpec("ocp-ldap", "LDAP", "groups", "07-openshift-cluster",
                 "LDAP identity provider and group sync.",
                 files=(FileSpec("examples/openshift/ldap.ezai.yaml", "openshift/ldap.ezai.yaml", "ocp_ldap"),),
                 actions=(Action("apply", "Configure LDAP", "groups", phase2("auth"), secrets=("*",), env=ocp_env),),
                 secrets=lambda handle: [LDAP_BIND] + PHASE2_SECRETS(handle),
                 upload_dirs=(OCP_UPLOADS["ocp-ldap"],),
                 notes=("The URL, base DNs, and bind DN pre-fill from Initial Inventory > Shared services > LDAP. Set the "
                        "cluster admin groups and group mappings here.", OPENSHIFT_UPLOAD_NOTE), group="OpenShift"),
        PageSpec("ocp-gitops", "OpenShift GitOps", "account_tree", "08-mlops",
                 "OpenShift GitOps (Argo CD) operators: Cilium, NVIDIA AI Enterprise, and more.",
                 files=(FileSpec("examples/openshift/operators.ezai.yaml", OPERATORS_TARGET,
                                 "ocp_operators"),),
                 actions=(Action("isovalent-check", "Check Isovalent registry", "verified",
                                 iserver_setup("isovalent-check"), group="Pre-check", files=False),
                          Action("isovalent", "Register Isovalent registry", "key", iserver_setup("isovalent"),
                                 group="Tools", secrets=(ISOVALENT_TOKEN.key,), files=False),
                          Action("gitops", "Deploy GitOps", "account_tree", phase2("gitea,argocd,gitops"),
                                 secrets=("*",), env=ocp_env,
                                 confirm="Installs Gitea (when enabled) and OpenShift GitOps, and renders the "
                                         "operator applications into destination_directory. Then use Push to GitOps "
                                         "repository."),
                          Action("gitops-push", "Push to GitOps repository", "cloud_upload", gitops_push,
                                 env=gitops_env,
                                 confirm="Commits the rendered operator applications in destination_directory and "
                                         "pushes them to the GitOps repository URL."),
                          INTERSIGHT_MACS, REDFISH_MACS),
                 secrets=lambda handle: PHASE2_SECRETS(handle) + [ISOVALENT_TOKEN, GITOPS_TOKEN],
                 form=custom_pages.gitops_form, group="OpenShift"),
    )),
    Section("observability", "Splunk Observability", "query_stats", (
        PageSpec("splunk", "Deployment", "insights", "09-ai-workloads",
                 "Splunk OpenTelemetry Collector for the cluster. otel_collector.proxy is filled from the Initial Inventory "
                 "shared services (with the recommended no_proxy entries) and left out when no proxy is configured.",
                 files=(FileSpec("examples/splunk_observability/splunk.ezai.yaml",
                                 "splunk_observability/splunk.ezai.yaml", "splunk"),),
                 actions=(Action("check", "Validate (check mode)", "fact_check", deploy("observability", "--check"),
                                 group="Pre-check", secrets=("*",), env=ocp_env),
                          Action("deploy", "Deploy collector", "cloud_upload", deploy("observability"), secrets=("*",),
                                 env=ocp_env)),
                 secrets=model_secrets, upload_dirs=("splunk_observability/uploads",),
                 notes=("Use the upload button in Variables to add your own YAML files (listed as uploads/...); they "
                        "are merged after splunk.ezai.yaml, so an uploaded key overrides it.",)),
    )),
)

PAGES = {page.key: page for section in SECTIONS for page in section.pages}


# --------------------------------------------------------------------------------------------------- page builders

def stage_overview(context: UiContext, spec: PageSpec) -> None:
    with ui.row().classes("w-full items-start justify-between no-wrap gap-4"):
        with ui.column().classes("gap-1").style("min-width:0"):
            ui.label(spec.full_title).classes("section-title")
            ui.label(spec.summary).classes("muted")
        if spec.stage:
            ui.badge(spec.stage, color="primary").props("outline")
    for note in spec.notes:
        with ui.row().classes("w-full items-center gap-2 mt-2 no-wrap"):
            ui.icon("info").style("color:var(--muted)")
            ui.label(note).classes("muted text-sm")
    readme = context.repository / spec.stage / "README.md" if spec.stage else None
    if readme and readme.is_file():
        with collapsible("Stage README", "menu_book", value=False, classes="mt-3"):
            ui.markdown(inline_images(readme.read_text(encoding="utf-8")[:20000], readme.parent)).classes("w-full stage-readme")


IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".svg": "image/svg+xml"}


def inline_images(markdown: str, folder: Path) -> str:
    """Embed relative README images as data URIs; the stage folder is not served over HTTP."""
    root = folder.resolve()

    def replace(match: re.Match) -> str:
        target = match.group(2).strip()
        path = (folder / target).resolve()
        mime = IMAGE_TYPES.get(path.suffix.lower())
        if "://" in target or not mime or not path.is_relative_to(root) or not path.is_file():
            return match.group(0)
        data = base64.b64encode(path.read_bytes()).decode()
        return f"![{match.group(1)}](data:{mime};base64,{data})"

    return re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", replace, markdown)


def stage_page(context: UiContext, spec: PageSpec) -> PageHandle:
    """Overview, page form, YAML workbench, vault credentials, and the automation console."""
    handle = PageHandle(context, spec)
    stage_overview(context, spec)
    form_area = ui.column().classes("w-full gap-3")
    if spec.secrets:
        with ui.column().classes("w-full mt-5"):
            handle.credentials = CredentialsPanel(context, lambda: spec.secrets(handle), visible=not spec.inline_secrets,
                                                  hide=spec.hidden_secrets,
                                                  header=(lambda: spec.secrets_header(handle)) if spec.secrets_header
                                                  else None)
    if spec.files or spec.file_groups:
        def saved(target: str, content: str) -> None:
            if spec.on_save:
                spec.on_save(handle, target, content)
            handle.refresh_credentials()
        handle.workbench = (Workbenches(context, spec.file_groups, saved, spec.upload_dirs) if spec.file_groups
                            else Workbench(context, spec.files, saved,
                                           upload_dir=spec.upload_dirs[0] if spec.upload_dirs else ""))
        # Secrets found in the saved YAML are only known once the workbench exists.
        handle.refresh_credentials()
    if spec.form:
        with form_area:
            spec.form(handle)
    workbench = handle.workbench
    JobConsole(context, spec.key, spec.actions, lambda: handle.state(), workbench.ready if workbench else None,
               handle.credentials,
               (lambda: {key: path for key, path in workbench.saved_paths().items() if path.is_file()})
               if workbench else None)
    return handle


def check_listen_interfaces(vars_file: Path, host: set[str]) -> list[str]:
    """Kea is only installed with explicit listen interfaces that exist on this server."""
    try:
        dhcp = (yaml.safe_load(vars_file.read_text(encoding="utf-8")) or {}).get("dhcp") or {}
    except (OSError, yaml.YAMLError, AttributeError) as error:
        raise ValueError(f"Cannot read {vars_file.name}: {error}") from error
    interfaces = [str(name) for name in dhcp.get("interfaces") or [] if str(name).strip()]
    if not interfaces or "*" in interfaces:
        raise ValueError("Select the listen interface(s) facing the bootstrap network or the DHCP relay, then "
                         "Generate (or set dhcp.interfaces in dhcp.yaml). Kea is not installed to listen on every "
                         "interface.")
    unknown = sorted(set(interfaces) - host)
    if unknown:
        raise ValueError(f"These listen interfaces are not on this server: {', '.join(unknown)} "
                         f"(available: {', '.join(sorted(host)) or 'none'})")
    return interfaces


def dhcp_actions(vars_file: Path, render_file: Path) -> tuple[Action, ...]:
    def base(rc: RunContext) -> list[str]:
        if not vars_file.is_file():
            raise ValueError("Generate the DHCP configuration first")
        return playbook(rc, "00-environment-prep/automation/playbooks/deploy_dhcp_server.yml", "-i", "localhost,",
                        "-c", "local", "-e", "dhcp_hosts=localhost", "-e", f"dhcp_vars_file={vars_file}")

    def install(rc: RunContext) -> list[list[str]]:
        check_listen_interfaces(vars_file, {item["name"] for item in host_interfaces()})
        return [base(rc) + ["-e", "ansible_become_password={{ lookup('ansible.builtin.env', 'BECOME_PASSWORD') }}"]]

    return (
        Action("render", "Render and validate", "fact_check",
               lambda rc: [base(rc) + ["-e", "dhcp_render_only=true", "-e", f"dhcp_render_dest={render_file}"]],
               group="Pre-check", files=False, tooltip=f"Writes {render_file} and checks it with kea-dhcp4 -t."),
        Action("install", "Install and start Kea", "play_arrow", install, files=False, sudo=True,
               confirm="Installs Kea DHCPv4 on this server, writes /etc/kea/kea-dhcp4.conf, and (re)starts the service. "
                       "Devices on the listen interfaces start receiving leases."),
        Action("status", "Service status", "monitor_heart",
               lambda rc: [["bash", "-c", "systemctl status --no-pager kea-dhcp4 2>/dev/null || "
                                          "systemctl status --no-pager kea-dhcp4-server"]],
               group="Post-check", files=False),
    )


def dhcp_inputs_fingerprint(context: UiContext) -> str:
    """Hash of the Initial Inventory values that dhcp.yaml is generated from, to spot a stale file."""
    services = context.store.shared_services()
    data = {"rows": sorted((str(row.get("hostname", "")), str(row.get("ip", "")), str(row.get("mac", "")).lower())
                           for row in context.store.inventory()),
            "services": {key: services.get(key) for key in ("domain_name", "dns_servers", "ntp_servers",
                                                            "dns_search_domains")}}
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def dhcp_defaults(context: UiContext, interfaces: list[dict]) -> dict:
    """Bootstrap settings suggested from the Initial Inventory addresses and this host's interfaces and route."""
    addresses = [row.get("ip", "") for row in context.store.inventory()]
    network, source = suggest_network(interfaces, addresses)
    gateway = default_gateway()
    return {"network": network, "source": source,
            "interfaces": [item["name"] for item in interfaces if item["network"] == network],
            "routers": [gateway] if gateway and _contains(network, gateway) else []}


def dhcp_page(context: UiContext) -> None:
    spec = PAGES["dhcp"]
    saved = context.store.page_state("dhcp")
    interfaces = host_interfaces()
    suggested = dhcp_defaults(context, interfaces)
    known = {item["name"] for item in interfaces}
    vars_file = context.output_dir / spec.stage / "dhcp.yaml"
    render_file = context.output_dir / spec.stage / "kea-dhcp4.conf"

    stage_overview(context, spec)
    with collapsible("DHCP Bootstrap", "lan"):
        with ui.element("div").classes("w-full p-3 rounded").style(
                "border:1px solid var(--border);background:rgba(2,123,193,.06)"):
            summary = ui.label().classes("text-sm")
            source = ui.label().classes("muted text-xs")
        with ui.row().classes("w-full items-center gap-2 no-wrap p-3 rounded").style(
                "border:1px solid #f2a93b;background:rgba(242,169,59,.12)") as stale:
            ui.icon("warning", size="sm").style("color:#f2a93b")
            ui.label("The Initial Inventory or shared services changed since dhcp.yaml was generated. Generate from "
                     "inventory to update the reservations, DNS, and NTP (this replaces manual edits).").classes("text-sm grow")
            ui.button("Generate now", icon="description", on_click=lambda: generate()).props("outline dense")
        with ui.element("div").classes("services-grid"):
            interface_select = ui.select({item["name"]: f"{item['name']} ({item['address']}, {item['network']})" for item in interfaces},
                                         value=[name for name in (saved.get("interfaces") or suggested["interfaces"]) if name in known],
                                         multiple=True, label="Listen interfaces (required to install Kea)").props("outlined dense use-chips hint=\"Ports facing the bootstrap network or the DHCP relay\"").classes("w-full")
            network = ui.input("Bootstrap network (CIDR)", value=saved.get("network") or suggested["network"]).props(
                "outlined dense").classes("w-full")
            routers = ui.input("Default gateway (optional)",
                               value=", ".join(saved.get("routers") if "routers" in saved else suggested["routers"])).props(
                "outlined dense").classes("w-full")
            pool_start = ui.input("Dynamic pool start (optional)", value=saved.get("pool_start", "")).props("outlined dense").classes("w-full")
            pool_end = ui.input("Dynamic pool end (optional)", value=saved.get("pool_end", "")).props("outlined dense").classes("w-full")
            lease = ui.number("Lease time (seconds)", value=saved.get("lease_time", 3600), min=300, precision=0).props("outlined dense").classes("w-full")
            tftp = ui.input("POAP / TFTP server (optional)", value=saved.get("tftp_server", ""),
                            placeholder="Nexus Dashboard address (switch POAP)").props("outlined dense").classes("w-full")
            bootfile = ui.input("Boot file (optional)", value=saved.get("bootfile", ""),
                                placeholder="poap_dcnm.py").props("outlined dense").classes("w-full")
            ui.label("Switch POAP with Nexus Dashboard: option 66 is the Nexus Dashboard data / management address "
                     "and option 67 is poap_dcnm.py. Enable POAP on the fabric (Create / update fabric) first.").classes(
                "muted text-xs")
            deny_unknown = ui.switch("Only serve inventory devices", value=saved.get("deny_unknown_clients", True))
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Fill from inventory", icon="auto_fix_high", on_click=lambda: fill()).props("outline").tooltip(
                "Reset the network, interfaces, and gateway to the values suggested from the Initial Inventory addresses")
            ui.button("Generate from inventory", icon="description", on_click=lambda: generate())
        problems = ui.column().classes("w-full")
        with ui.column().classes("w-full gap-2"):
            with ui.row().classes("w-full items-center gap-2"):
                ui.label("dhcp.yaml").classes("font-medium")
                file_label = ui.label().classes("muted text-xs grow")
                ui.button("Validate", icon="fact_check", on_click=lambda: validate()).props("outline dense")
                ui.button("Save", icon="save", on_click=lambda: save()).props("dense")
                ui.button(icon="download", on_click=lambda: download()).props("flat round dense").tooltip("Download dhcp.yaml")
            ui.label("Reservations come from the hostnames, MAC addresses, and IPs on the Initial Inventory page. Edit the "
                     "YAML here for anything else (extra subnets, per-host options); hover a key for help. Generate from "
                     "inventory rebuilds the file and replaces manual edits.").classes("muted text-xs")
            editor = YamlEditor(vars_file.read_text(encoding="utf-8") if vars_file.is_file() else "", context.schema_uri,
                                height="420px")
            editor_problems = ui.column().classes("w-full")
    JobConsole(context, "dhcp", dhcp_actions(vars_file, render_file), lambda: context.store.page_state("dhcp"))

    def refresh_summary() -> None:
        settings = context.store.shared_services()
        rows = context.store.inventory()
        with_mac = sum(1 for row in rows if row.get("mac") and row.get("ip"))
        summary.set_text(f"From the Initial Inventory: {len(rows)} devices ({with_mac} with a MAC and IP become "
                         f"reservations); DNS {', '.join(settings.get('dns_servers', [])) or 'not set'}; NTP "
                         f"{', '.join(settings.get('ntp_servers', [])) or 'not set'}; domain "
                         f"{settings.get('domain_name') or 'not set'}.")
        source.set_text(f"Suggested bootstrap network {suggested['network']} from {suggested['source']}"
                        + (f"; gateway {suggested['routers'][0]} from this host's default route" if suggested["routers"] else "")
                        + ".")
        if vars_file.is_file():
            file_label.set_text(str(vars_file))
        else:
            file_label.set_text("not generated yet")
        stale.set_visibility(vars_file.is_file() and bool(rows)
                             and context.store.page_state("dhcp-source").get("fingerprint") != dhcp_inputs_fingerprint(context))

    refresh_summary()

    def fill() -> None:
        current = dhcp_defaults(context, interfaces)
        suggested.update(current)
        network.value = current["network"]
        interface_select.value = [name for name in current["interfaces"] if name in known]
        routers.value = ", ".join(current["routers"])
        refresh_summary()
        ui.notify("Filled from the Initial Inventory. Generate to rebuild dhcp.yaml.", type="info")

    def options() -> dict:
        return dict(interfaces=interface_select.value or [], network=network.value,
                    routers=[value.strip() for value in (routers.value or "").split(",") if value.strip()],
                    pool_start=pool_start.value, pool_end=pool_end.value, lease_time=int(lease.value or 3600),
                    tftp_server=tftp.value, bootfile=bootfile.value, deny_unknown_clients=deny_unknown.value)

    async def generate(quiet: bool = False) -> None:
        problems.clear()
        try:
            settings = options()
            document, warnings = build_dhcp_model(context.store.inventory(), context.store.shared_services(), settings)
            context.store.save_page_state("dhcp", settings)
            context.store.save_page_state("dhcp-source", {"fingerprint": dhcp_inputs_fingerprint(context)})
            content = "---\n# Generated by the Automation UI from the initial inventory.\n" + yaml.safe_dump(
                document, sort_keys=False, default_flow_style=False)
            await run.io_bound(write_text, vars_file, content)
        except (ValueError, OSError) as error:
            if not quiet:
                show_problems(problems, str(error).splitlines(), "Cannot build the DHCP configuration")
            return
        show_problems(problems, warnings, "Warnings")
        editor.set_value(content)
        editor_problems.clear()
        refresh_summary()
        await asyncio.sleep(0)
        ui.notify(f"dhcp.yaml generated with {len(document['dhcp']['reservations'])} reservations. Use Render and "
                  "validate, then Install and start Kea.", type="positive")

    async def check() -> tuple[str, list[str]]:
        content = await editor.get_value()
        _, issues = await run.io_bound(validate_yaml, content, context.schema_path)
        return content, issues

    async def validate() -> None:
        _, issues = await check()
        show_problems(editor_problems, issues, "Schema validation failed")
        ui.notify("Valid" if not issues else f"{len(issues)} schema problems", type="positive" if not issues else "negative")

    async def save() -> None:
        content, issues = await check()
        show_problems(editor_problems, issues, "Saved with schema problems; fix them before installing Kea")
        await run.io_bound(write_text, vars_file, content)
        refresh_summary()
        ui.notify(f"Saved {vars_file.name}" + (f" with {len(issues)} schema problems" if issues else ""),
                  type="warning" if issues else "positive")

    async def download() -> None:
        ui.download.content(await editor.get_value(), "dhcp.yaml")

    # First visit: build the file from the inventory so the page opens with the generated reservations.
    if not vars_file.is_file() and context.store.inventory():
        ui.timer(0.5, lambda: generate(quiet=True), once=True)


def _contains(network: str, address: str) -> bool:
    try:
        return ipaddress.ip_address(address) in ipaddress.ip_network(network, strict=False)
    except ValueError:
        return False
