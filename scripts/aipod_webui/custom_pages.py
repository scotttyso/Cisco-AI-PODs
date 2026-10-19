"""Page-specific forms that sit above the YAML workbench: settings that are not in the schema, guided editors that
write into the YAML, key and CSR generation, and summaries of data collected by the automation."""

from __future__ import annotations

import datetime
import os
import re
import shutil
from pathlib import Path

from nicegui import run, ui

from . import seeds
from .panels import CredentialsPanel, write_text
from .vault import VaultError

OPERATORS = {
    "aap": "Ansible Automation Platform",
    "cert-manager-operator": "cert-manager Operator",
    "cisco-intersight": "Cisco Intersight Operator",
    "external-secrets-operator": "External Secrets Operator",
    "openshift-cnv": "OpenShift Virtualization",
    "openshift-nfd": "Node Feature Discovery",
    "openshift-nmstate": "Kubernetes NMState",
    "openshift-sriov-network-operator": "SR-IOV Network Operator",
    "redhat-ods-operator": "Red Hat OpenShift AI",
}
NVIDIA_OPERATORS = {
    "nvidia-gpu-operator": "NVIDIA GPU Operator",
    "nvidia-network-operator": "NVIDIA Network Operator",
    "nvidia-nim-operator": "NVIDIA NIM Operator",
}
DEFAULT_CILIUM_VERSION = "1.19.7"
MAC_VLAN_COUNT = 8
# Route host for the gitea-with-admin instance in the gitea-operator namespace; the
# instance creates one user named lab-user (roles/openshift_gitea/templates/instance.yaml.j2).
GITEA_URL_PREFIX = "https://gitea-with-admin-gitea-operator.apps."
GITEA_USER = "lab-user"
GITEA_REPOSITORY = "openshift-gitops-repo"


def gitea_repo_url(cluster: str | None, domain: str | None) -> str:
    if not cluster or not domain:
        return ""
    return f"{GITEA_URL_PREFIX}{cluster}.{domain}/{GITEA_USER}/{GITEA_REPOSITORY}.git"


def card(title: str, subtitle: str = "", icon: str = "tune", value: bool = True):
    """Collapsible page section; returns its body column (usable as a context manager)."""
    with ui.expansion(title, icon=icon, value=value).classes("w-full env-card page-section"):
        body = ui.column().classes("w-full gap-3 p-4")
    if subtitle:
        with body:
            ui.label(subtitle).classes("muted text-sm")
    return body


def default_nd_url(cluster: dict) -> str:
    for node in cluster.get("nodes") or []:
        if isinstance(node, dict) and node.get("role") == "bootstrap" and (node.get("mgmt") or {}).get("ip"):
            return f"https://{node['mgmt']['ip']}"
    return ""


# ------------------------------------------------------------------------------------------------------- Network

def nd_access_form(handle) -> None:
    """URL, username, and admin password every Nexus Dashboard page uses, whether or not this page deploys the cluster."""
    from .pages import ND_ADMIN, nd_access

    url_value, user_value = nd_access(handle.context)
    with card("Nexus Dashboard access", "Required even when the cluster already exists and is not deployed from here: "
              "the backend, frontend, and management fabric pages and the post-checks connect with these settings.",
              icon="link"):
        with ui.row().classes("w-full gap-3 items-start"):
            url = ui.input("Nexus Dashboard URL", value=url_value, placeholder="https://nd.example.com",
                           validation={"Required": lambda value: bool((value or "").strip()),
                                       "Use https://": lambda value: not value or value.startswith(("https://", "http://"))}
                           ).props("outlined dense").classes("grow")
            user = ui.input("Username", value=user_value,
                            validation={"Required": lambda value: bool((value or "").strip())}
                            ).props("outlined dense").style("width:200px")

            def save() -> None:
                if not url.validate() or not user.validate():
                    ui.notify("Enter the Nexus Dashboard URL and username", type="warning")
                    return
                handle.save_state({"nd_url": url.value.strip().rstrip("/"), "nd_username": user.value.strip()})
                ui.notify("Nexus Dashboard access saved", type="positive")

            ui.button("Save", icon="save", on_click=save).props("outline")
        ui.label("Defaults to the bootstrap node management address in the cluster file.").classes("muted text-xs")
        CredentialsPanel(handle.context, lambda: [ND_ADMIN], embedded=True, on_change=handle.refresh_credentials)


# ------------------------------------------------------------------------------------------------------- Compute

TARGET_COLUMNS = [
    {"name": "hostname", "label": "Hostname", "field": "hostname", "align": "left", "sortable": True},
    {"name": "role", "label": "Role", "field": "role_label", "align": "left"},
    {"name": "address", "label": "DHCP address", "field": "address", "align": "left"},
    {"name": "static_ip", "label": "Static address", "field": "static_ip", "align": "left"},
    {"name": "netmask", "label": "Netmask", "field": "netmask", "align": "left"},
    {"name": "gateway", "label": "Gateway", "field": "gateway", "align": "left"},
    {"name": "organization", "label": "Organization", "field": "org_label", "align": "left"},
    {"name": "credentials", "label": "Credentials", "field": "credentials", "align": "left"},
    {"name": "actions", "label": "", "field": "id", "align": "right"},
]


def registration_form(handle) -> None:
    """Claim Targets: Intersight account, default device credentials, and the editable list of targets to claim."""
    from .pages import INTERSIGHT_KEY_ID, INTERSIGHT_SECRET_KEY
    from .panels import secret
    from . import stage_inventory as si

    context = handle.context
    state = handle.state()
    rows = context.store.inventory()
    model = {"organizations": si.organizations(state), "targets": si.registration_targets(rows, state)}

    def persist(message: str = "") -> None:
        handle.save_state({"api_uri": (url.value or "").strip().rstrip("/") or "https://intersight.com",
                           "fi_username": (fi_user.value or "").strip() or "admin",
                           "cimc_username": (cimc_user.value or "").strip() or "admin",
                           "organizations": [item for item in model["organizations"] if item["organization"]],
                           "targets": model["targets"]})
        for name in ("devices", "account_name", "organization", "resource_group"):
            handle.state().pop(name, None)
        handle.refresh_credentials()
        overrides.render()
        if message:
            ui.notify(message, type="positive")

    # ------------------------------------------------------------------ account
    with card("Intersight account", "Every target in the list below is claimed into this account. The account name is "
                                    "read from the API key.", icon="cloud"):
        url = ui.input("Intersight URL", value=state.get("api_uri", "https://intersight.com")).props(
            "outlined dense").classes("w-full")
        url.on("blur", lambda: persist())
        CredentialsPanel(context, lambda: [INTERSIGHT_KEY_ID, INTERSIGHT_SECRET_KEY], title="API key", embedded=True,
                         on_change=handle.refresh_credentials)
        ui.label("Organizations and resource groups").classes("font-medium mt-2")
        ui.label("The first entry is the default for every target; a target can be moved to another entry. Missing "
                 "organizations and resource groups are created during the claim.").classes("muted text-xs")

        @ui.refreshable
        def org_list() -> None:
            for index, item in enumerate(model["organizations"]):
                with ui.row().classes("w-full items-center gap-3 no-wrap"):
                    ui.badge("default" if index == 0 else str(index + 1)).props("outline")

                    def update(event, item=item, name="organization") -> None:
                        item[name] = (event.value or "").strip()

                    ui.input("Organization", value=item["organization"],
                             on_change=lambda e, item=item: update(e, item, "organization")).props(
                        "outlined dense").classes("grow").on("blur", lambda: persist())
                    ui.input("Resource group", value=item["resource_group"],
                             on_change=lambda e, item=item: update(e, item, "resource_group")).props(
                        "outlined dense").classes("grow").on("blur", lambda: persist())

                    def remove(index=index) -> None:
                        model["organizations"].pop(index)
                        if not model["organizations"]:
                            model["organizations"].append(dict(si.DEFAULT_ORGANIZATION))
                        persist()
                        org_list.refresh()
                        target_table.refresh()

                    ui.button(icon="delete", on_click=remove).props("flat round dense color=negative").tooltip(
                        "Remove").set_enabled(len(model["organizations"]) > 1)

        org_list()

        def add_org() -> None:
            model["organizations"].append({"organization": "", "resource_group": ""})
            org_list.refresh()

        ui.button("Add organization", icon="add", on_click=add_org).props("outline dense")

    # ------------------------------------------------------------------ credentials
    with card("Device credentials", "Defaults for every target. A target can override the username and password in its "
                                    "Edit dialog. Passwords need at least 12 characters so every device accepts them.", icon="key"):
        with ui.row().classes("w-full gap-3"):
            fi_user = ui.input("Fabric Interconnect username", value=state.get("fi_username", "admin")).props(
                "outlined dense").classes("grow")
            cimc_user = ui.input("CIMC / BMC username", value=state.get("cimc_username", "admin")).props(
                "outlined dense").classes("grow")
            fi_user.on("blur", lambda: persist())
            cimc_user.on("blur", lambda: persist())
        CredentialsPanel(context, lambda: [
            secret(si.vault_key(si.FI_PASSWORD_REF), "Fabric Interconnect password", min_length=si.FACTORY_PASSWORD_MIN),
            secret(si.vault_key(si.CIMC_PASSWORD_REF), "CIMC / BMC password", min_length=si.FACTORY_PASSWORD_MIN,
                   help="Targets marked factory default are logged into with password 'password' and changed to this.")],
            title="Default passwords", embedded=True, on_change=handle.refresh_credentials)

    # ------------------------------------------------------------------ targets
    roles = {role: seeds.ROLES.get(role, role) for role in si.TARGET_ROLES}

    def org_names() -> list[str]:
        return [item["organization"] for item in model["organizations"] if item["organization"]]

    def display(target: dict) -> dict:
        names = org_names()
        organization = target.get("organization") if target.get("organization") in names else ""
        redfish = target.get("role") in si.REDFISH_ROLES
        credentials = "override" if target.get("override") else "default"
        if target.get("factory_default") and redfish:
            credentials += ", factory default"
        if not si.target_claimable(target):
            credentials += " (not claimable; Redfish only)"
        return {**target, "role_label": roles.get(target.get("role"), target.get("role")),
                "org_label": organization or f"{names[0] if names else 'default'} (default)",
                "credentials": credentials}

    def edit(target: dict | None) -> None:
        current = dict(target or {"id": "", "hostname": "", "role": "ucs-server", "pid": "", "serial_number": "",
                                  "address": "", "static_ip": "", "netmask": "", "gateway": "", "organization": "",
                                  "factory_default": False, "override": False, "username": ""})
        with ui.dialog() as dialog, ui.card().style("min-width:640px"):
            ui.label("Edit target" if target else "Add target").classes("text-lg font-medium")
            with ui.element("div").classes("services-grid w-full"):
                hostname = ui.input("Hostname", value=current["hostname"]).props("outlined dense")
                role = ui.select(roles, value=current["role"], label="Role").props("outlined dense")
                pid = ui.input("Model (PID)", value=current.get("pid", "")).props("outlined dense")
                serial = ui.input("Serial number", value=current.get("serial_number", "")).props("outlined dense")
                address = ui.input("DHCP / current address", value=current.get("address", "")).props("outlined dense")
                static = ui.input("Static address", value=current.get("static_ip", ""),
                                  placeholder="same as current").props("outlined dense")
                netmask = ui.input("Netmask", value=current.get("netmask", ""),
                                   placeholder="read from the device").props("outlined dense")
                gateway = ui.input("Gateway", value=current.get("gateway", ""),
                                   placeholder="read from the device").props("outlined dense")
                options = {"": "Default"} | {name: name for name in org_names()}
                organization = ui.select(options, value=current.get("organization") if current.get("organization")
                                         in options else "", label="Organization").props("outlined dense")
            ui.label("Leave Netmask and Gateway empty to keep the values the device has from DHCP. Fabric "
                     "Interconnect and X-Direct addresses are set during their initial setup.").classes("muted text-xs")
            factory = ui.checkbox("Factory default password ('password'); change it to the CIMC / BMC password (HGX: the HGX BMC password)",
                                  value=bool(current.get("factory_default")))
            override = ui.checkbox("Override username and password for this target", value=bool(current.get("override")))
            username = ui.input("Username", value=current.get("username", ""), placeholder="admin").props(
                "outlined dense").classes("w-full")
            username.bind_visibility_from(override, "value")
            ui.label("The override password is entered under Target password overrides after saving.").classes(
                "muted text-xs").bind_visibility_from(override, "value")

            def sync_role() -> None:
                redfish = role.value in si.REDFISH_ROLES
                factory.set_enabled(redfish)
                if not redfish:
                    factory.value = False

            role.on_value_change(lambda: sync_role())
            sync_role()

            def apply() -> None:
                name = (hostname.value or "").strip()
                if not name:
                    ui.notify("Hostname is required", type="negative")
                    return
                key = seeds.host_key(name)
                if any(item["id"] == key and item is not target for item in model["targets"]):
                    ui.notify(f"{name} is already in the list", type="negative")
                    return
                values = {"id": key, "hostname": name, "role": role.value, "pid": (pid.value or "").strip(),
                          "serial_number": (serial.value or "").strip(), "address": (address.value or "").strip(),
                          "static_ip": (static.value or "").strip(), "netmask": (netmask.value or "").strip(),
                          "gateway": (gateway.value or "").strip(), "organization": organization.value or "",
                          "factory_default": bool(factory.value), "override": bool(override.value),
                          "username": (username.value or "").strip() if override.value else ""}
                if target is None:
                    model["targets"].append(values)
                else:
                    target.clear()
                    target.update(values)
                persist(f"Saved {name}")
                target_table.refresh()
                dialog.close()

            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button("Save", icon="save", on_click=apply)
        dialog.open()

    def find(key: str) -> dict | None:
        return next((item for item in model["targets"] if item["id"] == key), None)

    def remove(key: str) -> None:
        model["targets"][:] = [item for item in model["targets"] if item["id"] != key]
        persist("Target removed")
        target_table.refresh()

    def add_missing() -> None:
        missing = si.missing_targets(rows, model["targets"])
        model["targets"].extend(missing)
        persist(f"Added {len(missing)} targets from the initial inventory" if missing else "")
        if not missing:
            ui.notify("Every inventory target is already in the list", type="info")
        target_table.refresh()

    with card("Targets", "Everything in this list is registered: CIMC / BMC addresses move to the static address, "
                         "factory default passwords are changed, and the targets are claimed into Intersight. Rows start "
                         "from the initial inventory (Fabric Interconnects, X-Direct, standalone C-Series, HGX nodes).", icon="dns"):
        @ui.refreshable
        def target_table() -> None:
            table = ui.table(columns=TARGET_COLUMNS, rows=[display(item) for item in model["targets"]],
                             row_key="id").props("flat bordered dense").classes("w-full")
            table.add_slot("body-cell-actions", """
                <q-td :props="props" auto-width>
                  <q-btn flat round dense icon="edit" @click="$parent.$emit('edit', props.row.id)" />
                  <q-btn flat round dense icon="delete" color="negative" @click="$parent.$emit('remove', props.row.id)" />
                </q-td>""")
            table.on("edit", lambda event: edit(find(event.args)))
            table.on("remove", lambda event: remove(event.args))
            if not model["targets"]:
                ui.label("No targets. Add one, or add the inventory rows with a Fabric Interconnect, X-Direct, UCS "
                         "server, or HGX node role.").classes("text-warning")

        target_table()
        with ui.row().classes("w-full gap-2"):
            ui.button("Add target", icon="add", on_click=lambda: edit(None))
            ui.button("Add missing from inventory", icon="playlist_add", on_click=add_missing).props("outline")

        def override_fields() -> list:
            return [secret(si.vault_key(si.target_pass_ref(item)), f"{item['hostname']} password",
                           min_length=si.FACTORY_PASSWORD_MIN) for item in model["targets"] if item.get("override")]

        overrides = CredentialsPanel(context, override_fields, title="Target password overrides", embedded=True,
                                     on_change=handle.refresh_credentials)


def macs_summary(handle) -> None:
    container = card("Collected MAC addresses", icon="settings_ethernet")

    def render() -> None:
        container.clear()
        with container:
            ui.label("Written by the Collect MACs actions; the OpenShift node inventory and the NVIDIA Network Operator "
                     "rules pre-fill from them.").classes("muted text-sm")
            macs = handle.context.collected_macs()
            if not macs:
                ui.label("Nothing collected yet.").classes("muted text-sm")
            else:
                rows = [{"host": host, "ports": len(ports),
                         "mellanox": sum(name.startswith(("mlx-", "ens", "enp")) for name in ports)}
                        for host, ports in sorted(macs.items())]
                ui.table(columns=[{"name": "host", "label": "Host", "field": "host", "align": "left"},
                                  {"name": "ports", "label": "Interfaces", "field": "ports"},
                                  {"name": "mellanox", "label": "High-speed NICs", "field": "mellanox"}],
                         rows=rows).props("dense flat").classes("w-full")
            ui.button("Refresh", icon="refresh", on_click=render).props("flat dense")

    render()


# ---------------------------------------------------------------------------------------------------- OpenShift

def console_form(handle) -> None:
    with card("Red Hat console access", "iserver uses the console.redhat.com API to create the cluster and download "
                                        "the discovery ISO.", icon="key"):
        ui.markdown("1. Copy the API token from [console.redhat.com/openshift/token]"
                    "(https://console.redhat.com/openshift/token) (Load Token).\n"
                    "2. Copy the pull secret from [console.redhat.com/openshift/install/pull-secret]"
                    "(https://console.redhat.com/openshift/install/pull-secret).\n"
                    "3. Store both in the Credentials panel, then run **Configure iserver console access**.")
        if not shutil.which("iserver"):
            ui.label("iserver is not installed on this server (https://github.com/datacenter/iserver).").classes(
                "text-warning text-sm")


def _ssh_reference(handle) -> int:
    for model in handle.models():
        bare = (((model.get("openshift") or {}).get("install") or {}).get("bare_metal")) or {}
        if isinstance(bare.get("ssh_public_key"), int):
            return bare["ssh_public_key"]
    return 1


def ocp_cluster_form(handle) -> None:
    context = handle.context
    state = handle.state("ocp-cluster")
    with card("Cluster access", "Kubeconfig written by the installer; used by the post-checks and every later OpenShift, "
                                "GitOps, and Splunk page.", icon="admin_panel_settings"):
        with ui.row().classes("w-full items-center gap-3"):
            kubeconfig = ui.input("Kubeconfig path", value=state.get("kubeconfig", ""),
                                  placeholder=str(context.repository / "assisted-installer/<cluster>/auth/kubeconfig")
                                  ).props("outlined dense").classes("grow")

            def save() -> None:
                path = (kubeconfig.value or "").strip()
                if path and not Path(path).expanduser().is_file():
                    ui.notify(f"{path} does not exist yet; saved anyway", type="warning")
                handle.save_state({"kubeconfig": str(Path(path).expanduser()) if path else ""}, "ocp-cluster")
                ui.notify("Saved", type="positive")

            ui.button("Save", icon="save", on_click=save).props("outline")

    with card("Node SSH key", "The public key is added to every node for the core user. Generate a new ed25519 key "
                              "pair here, or paste or upload an existing public key in the Credentials panel.", icon="vpn_key"):
        with ui.row().classes("gap-2"):
            async def generate() -> None:
                from cryptography.hazmat.primitives import serialization
                from cryptography.hazmat.primitives.asymmetric import ed25519

                number = _ssh_reference(handle)
                key = ed25519.Ed25519PrivateKey.generate()
                private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                                            serialization.NoEncryption()).decode()
                public = key.public_key().public_bytes(serialization.Encoding.OpenSSH,
                                                       serialization.PublicFormat.OpenSSH).decode() + " aipod-openshift"
                try:
                    await run.io_bound(context.vault.update, {("openshift", f"ssh_public_key_{number}"): public,
                                                              ("openshift", f"ssh_private_key_{number}"): private})
                except VaultError as error:
                    ui.notify(f"Vault update failed: {error}", type="negative")
                    return
                ui.download.content(private, "aipod-openshift-id_ed25519")
                handle.refresh_credentials()
                ui.notify(f"Stored ssh_public_key_{number} and its private key in the vault; the private key is "
                          "downloading.", type="positive", multi_line=True)

            async def download() -> None:
                number = _ssh_reference(handle)
                try:
                    data = await run.io_bound(context.vault.load)
                except VaultError as error:
                    ui.notify(str(error), type="negative")
                    return
                private = (data.get("openshift") or {}).get(f"ssh_private_key_{number}")
                if not private:
                    ui.notify("No generated private key is stored for this cluster", type="warning")
                    return
                ui.download.content(private, "aipod-openshift-id_ed25519")

            ui.button("Generate key pair", icon="vpn_key", on_click=generate).props("outline")
            ui.button("Download private key", icon="download", on_click=download).props("flat")

    with card("Node MAC addresses", "Run Collect MACs from Intersight (domain and standalone servers) and Collect MACs "
                                    "from BMC Redfish (HGX C845A / C880A) in Tools, then Refresh from inventory.", icon="settings_ethernet"):
        macs = context.collected_macs()
        nodes = seeds.by_role(context.store.inventory(), *seeds.COMPUTE_ROLES)
        found = sum(1 for row in nodes if macs.get(seeds.host_key(row["hostname"])))
        ui.label(f"{found} of {len(nodes)} compute nodes in the inventory have collected MACs.").classes("text-sm")


# ---------------------------------------------------------------------------------------------------- Certificates

def _csr(common_name: str, subject: dict, directory: Path, stem: str) -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=subject.get("key_size", 4096))
    names = [x509.NameAttribute(NameOID.COMMON_NAME, common_name)]
    for oid, field in ((NameOID.ORGANIZATION_NAME, "organization"), (NameOID.ORGANIZATIONAL_UNIT_NAME, "unit"),
                       (NameOID.LOCALITY_NAME, "locality"), (NameOID.STATE_OR_PROVINCE_NAME, "state"),
                       (NameOID.COUNTRY_NAME, "country")):
        if subject.get(field):
            names.append(x509.NameAttribute(oid, subject[field]))
    request = (x509.CertificateSigningRequestBuilder().subject_name(x509.Name(names))
               .add_extension(x509.SubjectAlternativeName([x509.DNSName(common_name)]), critical=False)
               .sign(key, hashes.SHA256()))
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    key_path = directory / f"{stem}.key"
    descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                       serialization.NoEncryption()))
    write_text(directory / f"{stem}.csr", request.public_bytes(serialization.Encoding.PEM).decode())


def check_chain(chain: bytes, key_path: Path | None, name: str) -> list[str]:
    """Problems with an uploaded PEM chain: parse errors, key mismatch, expiry, and missing host name."""
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    try:
        certificates = x509.load_pem_x509_certificates(chain)
    except ValueError as error:
        return [f"Not a PEM certificate chain: {error}"]
    leaf, problems = certificates[0], []
    if key_path and key_path.is_file():
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        if key.public_key().public_numbers() != leaf.public_key().public_numbers():
            problems.append(f"The certificate does not match {key_path.name}")
    if leaf.not_valid_after_utc < datetime.datetime.now(datetime.timezone.utc):
        problems.append("The certificate has expired")
    if name:
        try:
            dns = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
        except x509.ExtensionNotFound:
            dns = []
        if name not in dns:
            problems.append(f"{name} is not in the certificate subject alternative names ({', '.join(dns) or 'none'})")
    return problems


CERTIFICATE_FILES = {"api_key_file": "api.key", "api_cert_chain_file": "api.chain.pem",
                     "ingress_key_file": "ingress.key", "ingress_cert_chain_file": "ingress.chain.pem",
                     "user_ca_bundle_file": "ca-bundle.pem"}
CERTIFICATES_VARS = "openshift/certificates.ezai.yaml"


def certificate_directory(context, cluster: str) -> Path:
    return context.output_dir / "certificates" / (cluster or "cluster").strip()


def write_certificates_vars(context, cluster: str, domain: str) -> Path:
    """Write host_vars openshift/certificates.ezai.yaml from the generated keys and uploaded chains."""
    cluster, domain = (cluster or "").strip(), (domain or "").strip()
    if not (cluster and domain):
        raise ValueError("Enter the cluster name and base DNS domain on this page first")
    directory = certificate_directory(context, cluster)
    missing = [name for name in CERTIFICATE_FILES.values() if not (directory / name).is_file()]
    if missing:
        raise ValueError(f"Missing in {directory}: {', '.join(missing)}. Generate the keys and CSRs, then upload the "
                         "signed chains and the CA bundle.")
    values = {"api_server_hostname": f"api.{cluster}.{domain}",
              **{key: str(directory / name) for key, name in sorted(CERTIFICATE_FILES.items())}}
    path = context.host_vars_dir / CERTIFICATES_VARS
    write_text(path, seeds.dump({"openshift": {"certificates": values}}))
    return path


def certificates_form(handle) -> None:
    context = handle.context
    state = handle.state()
    cluster_state = {**handle.state("ocp-cluster"), **{key: state[key] for key in ("cluster_name", "base_dns_domain")
                                                       if state.get(key)}}
    with card("Certificate requests", "Private keys stay on this server (mode 0600). Send the CSRs to your certificate "
                                      "authority, then upload the signed chains below.", icon="description"):
        with ui.element("div").classes("services-grid"):
            cluster = ui.input("Cluster name", value=cluster_state.get("cluster_name", ""))
            domain = ui.input("Base DNS domain", value=cluster_state.get("base_dns_domain")
                              or context.store.shared_services().get("domain_name", ""))
            subject = {name: ui.input(label, value=state.get(name, "")) for name, label in (
                ("organization", "Organization (O)"), ("unit", "Organizational unit (OU)"), ("locality", "City (L)"),
                ("state", "State (ST)"), ("country", "Country (C, 2 letters)"))}
            for item in (cluster, domain, *subject.values()):
                item.props("outlined dense").classes("w-full")
        status = ui.column().classes("w-full gap-1")

    def directory() -> Path:
        return certificate_directory(context, cluster.value)

    def names() -> dict[str, str]:
        base = f"{(cluster.value or '').strip()}.{(domain.value or '').strip()}"
        return {"api": f"api.{base}", "ingress": f"*.apps.{base}"}

    def render_status() -> None:
        status.clear()
        with status:
            if not ((cluster.value or "").strip() and (domain.value or "").strip()):
                ui.label("Enter the cluster name and base DNS domain (saved from OpenShift - Cluster Deployment when "
                         "available) to generate requests.").classes("muted text-sm")
                return
            for stem, name in names().items():
                files = [f"{stem}.{suffix}" for suffix in ("key", "csr", "chain.pem") if (directory() / f"{stem}.{suffix}").is_file()]
                ui.label(f"{name}: {', '.join(files) or 'nothing generated yet'}").classes("text-sm")
            ui.label("ca-bundle.pem " + ("uploaded" if (directory() / "ca-bundle.pem").is_file() else "not uploaded yet")
                     ).classes("text-sm")
            try:
                path = write_certificates_vars(context, cluster.value, domain.value)
            except ValueError:
                ui.label("Apply certificates is available once every file above exists.").classes("muted text-xs")
            else:
                ui.label(f"Ready: {path} written for Apply certificates.").classes("text-sm text-positive")

    async def generate() -> None:
        if not (cluster.value and domain.value):
            ui.notify("Enter the cluster name and base DNS domain", type="warning")
            return
        country = (subject["country"].value or "").strip()
        if country and len(country) != 2:
            ui.notify("Country must be a 2-letter code", type="warning")
            return
        if any((directory() / f"{stem}.key").is_file() for stem in names()):
            with ui.dialog() as dialog, ui.card().classes("dialog-surface"):
                ui.label("Replace the existing private keys and CSRs? Certificates signed for the old keys stop "
                         "matching.").classes("text-sm")
                with ui.row().classes("w-full justify-end"):
                    ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("flat")
                    ui.button("Replace", color="negative", on_click=lambda: dialog.submit(True))
            if not await dialog:
                return
        values = {name: (item.value or "").strip() for name, item in subject.items()}
        handle.save_state({**values, "cluster_name": cluster.value.strip(), "base_dns_domain": domain.value.strip()})
        for stem, name in names().items():
            await run.io_bound(_csr, name, values, directory(), stem)
        render_status()
        ui.notify(f"Generated keys and CSRs in {directory()}", type="positive")

    def download(stem: str) -> None:
        path = directory() / f"{stem}.csr"
        if path.is_file():
            ui.download.file(str(path), f"{cluster.value}-{stem}.csr")
        else:
            ui.notify("Generate the CSRs first", type="warning")

    async def upload(event, stem: str) -> None:
        content = await event.file.read() if hasattr(event, "file") else event.content.read()
        target_name = names().get(stem, "")
        problems = await run.io_bound(check_chain, content, directory() / f"{stem}.key" if stem != "ca-bundle" else None,
                                      target_name if stem != "ca-bundle" else "")
        if problems and any("PEM" in problem or "match" in problem for problem in problems):
            ui.notify("; ".join(problems), type="negative", multi_line=True)
            return
        if not ((cluster.value or "").strip() and (domain.value or "").strip()):
            ui.notify("Enter the cluster name and base DNS domain first", type="warning")
            return
        path = directory() / ("ca-bundle.pem" if stem == "ca-bundle" else f"{stem}.chain.pem")
        await run.io_bound(write_text, path, content.decode("utf-8"))
        render_status()
        ui.notify(f"Saved {path.name}" + (f" ({'; '.join(problems)})" if problems else ""),
                  type="warning" if problems else "positive", multi_line=True)

    with card("Signed certificates", "Upload the full chain (server certificate first, then intermediates) for each "
                                     "request, and the enterprise CA bundle when the issuing CA is private.", icon="verified_user"):
        with ui.row().classes("gap-2 items-center"):
            ui.button("Generate keys and CSRs", icon="key", on_click=generate)
            ui.button("API CSR", icon="download", on_click=lambda: download("api")).props("outline")
            ui.button("Ingress CSR", icon="download", on_click=lambda: download("ingress")).props("outline")
        with ui.row().classes("w-full gap-3"):
            for stem, label in (("api", "API certificate chain"), ("ingress", "Ingress (*.apps) certificate chain"),
                                ("ca-bundle", "CA bundle")):
                ui.upload(label=label, auto_upload=True, max_files=1, max_file_size=1024 * 1024,
                          on_upload=lambda event, stem=stem: upload(event, stem)).props("flat bordered").classes("grow")
    def changed() -> None:
        handle.save_state({"cluster_name": (cluster.value or "").strip(), "base_dns_domain": (domain.value or "").strip()})
        render_status()

    cluster.on_value_change(lambda _: changed())
    domain.on_value_change(lambda _: changed())
    render_status()


# ------------------------------------------------------------------------------------------------------- GitOps

def schema_property(context, name: str) -> dict:
    """First property definition called ``name`` in the source schema (walks allOf lists too)."""
    import json

    def walk(node):
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict) and isinstance(properties.get(name), dict):
                return properties[name]
            children = node.values()
        elif isinstance(node, list):
            children = node
        else:
            return None
        for child in children:
            found = walk(child)
            if found is not None:
                return found
        return None

    try:
        schema = json.loads((context.repository / "schemas/source/cisco-ai-pods.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return walk(schema) or {}


def network_operator_default(context, nvaie: str) -> str:
    """Network Operator release certified for an NVIDIA AI Enterprise version (scripts/nvidia_support_matrix.py)."""
    import sys

    scripts = str(context.repository / "scripts")
    if scripts not in sys.path:
        sys.path.append(scripts)
    try:
        from nvidia_support_matrix import NVIDIA_SUPPORT_MATRIX
    except Exception:  # optional helper (tabulate missing, ...): keep whatever the user entered
        return ""
    version = ((NVIDIA_SUPPORT_MATRIX.get(nvaie) or {}).get("infrastructure_software") or {}).get("NVIDIA Network Operator")
    return f"v{version}" if version else ""


def gitops_form(handle) -> None:
    target = "openshift/operators.ezai.yaml"
    workbench = handle.workbench
    if not workbench or target not in workbench.specs:
        return
    context = handle.context
    data = seeds.load(workbench.load(target)[0]) or {}
    openshift = data.get("openshift") or {}
    operators = openshift.get("operators") or {}
    selected = set(operators.get("operators_to_install") or [])
    cilium = operators.get("cilium") or {}
    gitops = operators.get("openshift_gitops") or {}
    network = operators.get("nvidia_network_operator") or {}
    cluster_state = handle.state("ocp-cluster")
    nvaie_schema = schema_property(context, "nvidia_ai_enterprise_version")
    gpu_schema = schema_property(context, "gpu_models")
    controls: dict = {}
    pending = {"loading": True, "dirty": False}

    def changed(*_) -> None:
        if not pending["loading"]:
            pending["dirty"] = True

    with card("Operators", "Select the operators that Argo CD installs. The YAML in Variables updates as you change "
                           "these settings; review and Save it before running.", icon="extension"):
        with ui.element("div").classes("services-grid"):
            for key, label in OPERATORS.items():
                controls[key] = ui.checkbox(label, value=key in selected, on_change=changed)
        with ui.row().classes("w-full items-center gap-3"):
            controls["cilium"] = ui.checkbox("Isovalent Enterprise for Cilium (CNI)", value=bool(cilium), on_change=changed)
            controls["cilium_version"] = ui.input("Cilium version", value=str(cilium.get("version") or DEFAULT_CILIUM_VERSION),
                                                  on_change=changed).props("outlined dense").style("width:160px")
            ui.label("Requires Isovalent registry access: store the identity token in Passwords and secrets, then run "
                     "Register Isovalent registry (Tools).").classes("muted text-xs grow")

    with card("NVIDIA AI Enterprise", icon="memory"):
        versions = list(nvaie_schema.get("enum") or [])
        current_nvaie = str(openshift.get("nvidia_ai_enterprise_version") or nvaie_schema.get("default") or "")
        if current_nvaie and current_nvaie not in versions:
            versions.append(current_nvaie)
        controls["nvaie"] = ui.select(versions, value=current_nvaie or None, label="NVIDIA AI Enterprise version"
                                      ).props("outlined dense").style("width:260px")
        with ui.column().classes("w-full gap-1 pl-4"):
            controls["nvidia-gpu-operator"] = ui.checkbox(NVIDIA_OPERATORS["nvidia-gpu-operator"],
                                                          value="nvidia-gpu-operator" in selected, on_change=changed)
            with ui.column().classes("w-full gap-2 pl-8") as gpu_options:
                controls["rdma"] = ui.switch("Enable GPUDirect RDMA", on_change=changed,
                                             value=bool((operators.get("nvidia_gpu_operator") or {}).get("enable_rdma", True)))
                models = list((gpu_schema.get("items") or {}).get("enum") or [])
                chosen_models = [str(item) for item in openshift.get("gpu_models") or []]
                controls["gpu_models"] = ui.select(sorted(set(models) | set(chosen_models)), value=chosen_models,
                                                   multiple=True, label="Supported GPU models in the cluster",
                                                   on_change=changed).props("outlined dense use-chips").classes("w-full")
            controls["nvidia-nim-operator"] = ui.checkbox(NVIDIA_OPERATORS["nvidia-nim-operator"] + " (adds the GPU Operator)",
                                                          value="nvidia-nim-operator" in selected, on_change=changed)
            controls["nvidia-network-operator"] = ui.checkbox(NVIDIA_OPERATORS["nvidia-network-operator"],
                                                              value="nvidia-network-operator" in selected, on_change=changed)
            with ui.column().classes("w-full gap-2 pl-8") as network_options:
                controls["network_version"] = ui.input(
                    "Network Operator version", on_change=changed,
                    value=str(network.get("network_operator_version") or network_operator_default(context, current_nvaie)),
                    validation={"Use vNN.N.N": lambda value: not value or bool(re.fullmatch(r"v\d{2,3}\.\d{1,2}\.\d{1,2}", value))},
                ).props("outlined dense").style("width:260px")
                ui.label("Defaults to the release certified for the selected NVIDIA AI Enterprise version; edit to "
                         "override.").classes("muted text-xs")
                ui.label("MAC VLAN networks (8 required)").classes("font-medium mt-2")
                entries = list(network.get("mac_vlan") or [])
                vlan_rows = []
                for index in range(MAC_VLAN_COUNT):
                    entry = entries[index] if index < len(entries) else {}
                    vlan_rows.append({"id": str(index), "master_interface": entry.get("master_interface", ""),
                                      "ip_range": entry.get("ip_range", ""),
                                      "exclude_ips": ", ".join(str(value) for value in entry.get("exclude_ips") or [])})
                vlan_grid = ui.aggrid({
                    "defaultColDef": {"editable": True, "resizable": True},
                    "columnDefs": [dict(headerName="Master interface", field="master_interface", width=200),
                                   dict(headerName="IP range (CIDR)", field="ip_range", width=200),
                                   dict(headerName="Excluded IPs (comma separated)", field="exclude_ips", flex=1)],
                    "rowData": vlan_rows, "rowHeight": 32, "headerHeight": 34, "stopEditingWhenCellsLoseFocus": True,
                    "singleClickEdit": True, ":getRowId": "params => params.data.id",
                }, theme="balham").classes("w-full").style("height:330px")

                def vlan_changed(event) -> None:
                    row = event.args.get("data") or {}
                    for item in vlan_rows:
                        if item["id"] == row.get("id"):
                            item.update({key: row.get(key, "") for key in ("master_interface", "ip_range", "exclude_ips")})
                    changed()

                vlan_grid.on("cellValueChanged", vlan_changed, args=["data"])
                rules = network.get("persistent_net_rules") or []
                ui.label(f"Persistent NIC naming rules: {len(rules)} hosts in the YAML. Collect MACs (Tools), then use "
                         "Refresh from inventory to rebuild them from the collected Mellanox MACs.").classes("muted text-xs")

    def nvaie_changed(event) -> None:
        default = network_operator_default(context, event.value or "")
        if default:
            controls["network_version"].set_value(default)
        changed()

    controls["nvaie"].on_value_change(nvaie_changed)

    with card("OpenShift GitOps (Argo CD)", icon="account_tree"):
        with ui.row().classes("w-full items-center gap-4"):
            controls["gitea"] = ui.switch("Deploy Gitea in the cluster", on_change=changed,
                                          value=bool((operators.get("gitea") or {}).get("enable")))
            controls["prune"] = ui.switch("Prune", value=bool(gitops.get("prune")), on_change=changed)
            controls["self_heal"] = ui.switch("Self heal", value=bool(gitops.get("self_heal")), on_change=changed)
        controls["repo"] = ui.input("GitOps repository URL", value=str(gitops.get("gitops_repo_url") or ""),
                                    on_change=changed).props("outlined dense").classes("w-full")
        hint = ui.label().classes("muted text-xs")

        def gitea_hint() -> None:
            cluster, domain = cluster_state.get("cluster_name"), cluster_state.get("base_dns_domain")
            if controls["gitea"].value:
                suggestion = gitea_repo_url(cluster, domain)
                hint.set_text("Gitea hosts the repository. " + (f"Suggested URL: {suggestion} - create the repository "
                                                                 "for the lab-user account after Gitea is deployed."
                                                                 if suggestion else
                                                                 "Save the Cluster Deployment page to suggest its URL."))
                current_url = controls["repo"].value or ""
                if suggestion and (not current_url or current_url.startswith(GITEA_URL_PREFIX)):
                    controls["repo"].set_value(suggestion)
            else:
                hint.set_text("Use an external Git repository that Argo CD can reach (HTTPS URL).")

        controls["gitea"].on_value_change(lambda _: gitea_hint())
        gitea_hint()
    warnings = ui.label().classes("text-sm text-warning")

    def visibility() -> None:
        gpu_options.set_visibility(bool(controls["nvidia-gpu-operator"].value or controls["nvidia-nim-operator"].value))
        network_options.set_visibility(bool(controls["nvidia-network-operator"].value))

    for key in ("nvidia-gpu-operator", "nvidia-nim-operator", "nvidia-network-operator"):
        controls[key].on_value_change(lambda _: visibility())
    visibility()

    async def render() -> None:
        problems = []
        filled = [row for row in vlan_rows if str(row.get("master_interface") or "").strip()]
        if controls["nvidia-network-operator"].value and len(filled) != MAC_VLAN_COUNT:
            problems.append(f"The NVIDIA Network Operator needs all {MAC_VLAN_COUNT} MAC VLAN networks.")
        if not (controls["repo"].value or "").strip():
            problems.append("Enter the GitOps repository URL.")
        gpu_wanted = controls["nvidia-gpu-operator"].value or controls["nvidia-nim-operator"].value
        if gpu_wanted and not controls["gpu_models"].value:
            problems.append("Select the GPU models in the cluster.")
        warnings.set_text(" ".join(problems))
        current = seeds.load(await workbench.content(target))
        root = seeds.ensure(current, "openshift")
        for key in ("cluster_name", "base_dns_domain"):
            if cluster_state.get(key):
                root[key] = cluster_state[key]
        if controls["nvaie"].value:
            root["nvidia_ai_enterprise_version"] = str(controls["nvaie"].value)
        if controls["gpu_models"].value:
            root["gpu_models"] = seeds.seq(controls["gpu_models"].value)
        node = seeds.ensure(root, "operators")
        chosen = [key for key in (*OPERATORS, *NVIDIA_OPERATORS) if controls[key].value]
        node["operators_to_install"] = seeds.seq(chosen)
        if controls["cilium"].value:
            settings = seeds.ensure(node, "cilium")
            settings["version"] = (controls["cilium_version"].value or DEFAULT_CILIUM_VERSION).strip()
            settings.pop("download_url", None)
            if "cluster_network" not in settings:
                settings["cluster_network"] = seeds.cmap(v4_cidr=cluster_state.get("cluster_network") or "10.128.0.0/14",
                                                         v4_host_prefix=23)
        else:
            node.pop("cilium", None)
        seeds.ensure(node, "gitea")["enable"] = bool(controls["gitea"].value)
        argo = seeds.ensure(node, "openshift_gitops")
        argo["enable"] = True
        argo["gitops_repo_url"] = (controls["repo"].value or "").strip()
        argo["prune"] = bool(controls["prune"].value)
        argo["self_heal"] = bool(controls["self_heal"].value)
        if gpu_wanted:
            seeds.ensure(node, "nvidia_gpu_operator")["enable_rdma"] = bool(controls["rdma"].value)
        else:
            node.pop("nvidia_gpu_operator", None)
        if controls["nvidia-network-operator"].value:
            net = seeds.ensure(node, "nvidia_network_operator")
            if (controls["network_version"].value or "").strip():
                net["network_operator_version"] = controls["network_version"].value.strip()
            net["mac_vlan"] = seeds.seq(seeds.cmap(
                exclude_ips=seeds.seq(value.strip() for value in str(row.get("exclude_ips") or "").split(",") if value.strip()),
                ip_range=str(row.get("ip_range") or "").strip(),
                master_interface=str(row.get("master_interface") or "").strip()) for row in filled)
        workbench.set_content(target, seeds.dump(current), "Rendered from the selections above (not saved yet)")

    async def tick() -> None:
        # Debounce: render once the user pauses instead of on every keystroke.
        if pending["dirty"]:
            pending["dirty"] = False
            await render()

    ui.timer(0.5, tick)
    pending["loading"] = False
