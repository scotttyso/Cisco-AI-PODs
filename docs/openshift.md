# OpenShift Deployment Guide

This guide provides comprehensive workflows for deploying and configuring OpenShift clusters as part of the Cisco AI PODs infrastructure. Follow the sections in order, or jump to a specific role's section if you only need that component.

## Quick Navigation

- **[Cluster Installation](#cluster-installation)** — Generate manifests and deploy bare-metal OpenShift
- **[Cilium Registry Access](#cilium-registry-access)** — Register the Isovalent Enterprise (Cilium) registry with iServer
- **[Authentication](#authentication)** — Configure LDAP/Active Directory
- **[Certificates](#certificates)** — Manage custom CA, ingress, and API certificates
- **[GitOps](#gitops)** — Generate content for GitOps repositories
- **[Argo CD](#argo-cd)** — Install OpenShift GitOps Operator
- **[Gitea](#gitea)** — Deploy internal Git repository

---

## How to Run

### Run the full Cisco AI PODs stack:
```bash
python3 scripts/deploy_ai_pod.py
```

### Run only OpenShift roles:
```bash
python3 scripts/deploy_ai_pod.py --role openshift
```

### Run a specific OpenShift role (examples):
```bash
ansible-playbook playbooks/deploy_openshift_phase1.yaml --tags install
ansible-playbook playbooks/deploy_openshift_phase2.yaml --tags auth
ansible-playbook playbooks/deploy_openshift_phase2.yaml --tags certificates
```

---

## Cluster Installation

Generate and deploy bare-metal OpenShift cluster manifests via Cisco iServer and the OpenShift Assisted Installer.

**Role:** `roles/openshift_install`  
**Variables:** `host_vars/openshift/*.ezai.yaml*`
**Tag:** `install`

### Prerequisites

- Ansible with collections: `ansible.builtin`, `community.general`
- iServer executable from [datacenter/iserver releases](https://github.com/datacenter/iserver/releases)
- ISO web server reachable from target nodes
- SSH key pair for cluster node access

### Quick Start - Example

1. **Edit install variables:**
   ```bash
   mkdir host_vars
   cp -r examples/openshift host_vars/
   ```

2. **Modify each *.ezai.yaml file with the Configuration Relavent to the Environment**

3. **At a minimum configure (For OpenShift Install):**
   - `openshift.install.bare_metal.cluster_name`
   - `openshift.install.bare_metal.base_dns_domain`
   - `openshift.install.bare_metal.cluster_version`
   - `openshift.install.bare_metal.cluster_networking` (API VIP, Ingress VIP, machine network, DNS)
   - `openshift.install.bare_metal.fabric_interconnects` (if using servers with `fabric_interconnect`)
   - `openshift.install.bare_metal.iso_web_server` (IP, image URL, upload directory)
   - `openshift.install.bare_metal.servers` (hostnames, roles, interfaces, MACs)

4. **Provide sensitive credentials:**

   Put the credentials in the `openshift` section of `vault-ai-pod.yaml`. The
   deployment script uses the default password file under your home directory.
   ```bash
   export redfish_password_1='replace-with-secret-1'
   export redfish_password_2='replace-with-secret-2'
   export fi_password_1='replace-with-fi-secret-1'
   export fi_password_2='replace-with-fi-secret-2'
   export ssh_public_key_1='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... your-user@example.com'
   export GITHUB_TOKEN='replace-with-github-token'  # optional
   ```

4. **Run the playbook:**
   ```bash
   python3 scripts/deploy_ai_pod.py --role openshift
   ```

5. **Run iServer:**
   ```bash
   cd assisted-installer
   ./iserver create ocp cluster bm --dir ./ --mode check
   ./iserver create ocp cluster bm --dir ./ --mode install
   ```

For detailed instructions, see [roles/openshift_install/README.md](../roles/openshift_install/README.md).

---

## Cilium Registry Access

Isovalent Enterprise Platform (Cilium) images and manifests are served from a registry that requires authentication. iServer stores the registry host name and an identity token, verifies them, and the OpenShift installer adds the registry to the cluster pull secret. This is a one-time step per token; register again when the token expires (the access tokens iServer creates last 90 days).

In the UI use **OpenShift > Cilium Registry**:

1. Choose the registry. **Isovalent registry (customers)** uses `registry.isovalent.com`. **Other registry** takes any registry host name, for example an internal or mirrored registry (host name only, no `https://` and no path).
2. Create an identity token for that registry. For the Isovalent registry, sign in to the Isovalent Enterprise documentation and follow *Isovalent Registry Access* ([docs.isovalent.com](https://docs.isovalent.com/iep/latest/platform/registry.html)); other registries have their own procedure.
3. Store the identity token in the Credentials panel (it is kept in the encrypted vault and masked in job logs).
4. Click **Save registry**, then **Register Cilium registry**. This runs `iserver set ocp cilium registry --registry <host> --token <identity token>` and verifies access.

**Check Cilium registry** runs `iserver get ocp cilium registry`. When the install file selects the Cilium CNI, **Install cluster** on the Cluster Deployment page runs this check first, so an expired token stops the job before any node is touched.

### OpenShift and Cilium versions

`cluster_version` is optional and defaults to `the-latest-production-version`, which lets iServer install the latest production release the Red Hat Assisted Installer offers. Pick the latest stable release of a channel, such as `4.20.46`, to pin it. Only supported releases are accepted: the supported minor releases and the recommended patch are kept in `VERSION_SUPPORT` in `scripts/version_support_matrix.py`, and Prepare install stops with the reason when a pinned OpenShift or Cilium version is outside them. For the default, it looks up what the latest production release currently is (needs the Console Registration login) and stops if that release is not supported yet, so pin a supported one.

On the Cluster Deployment page, **Versions and container network** shows the latest stable release of each active OpenShift channel, like [console.redhat.com/openshift/releases](https://console.redhat.com/openshift/releases): the channel, its latest stable release, Red Hat's support phase and when it ends, and whether Cisco AI PODs supports it. Releases come from iServer (the versions the Assisted Installer accepts; uses the Console Registration login) or, without it, Red Hat's public update graph; support phases come from Red Hat's public [product life cycle API](https://access.redhat.com/product-life-cycles/api/v2/products?name=Red+Hat+OpenShift+Container+Platform). Neither public source needs a login or token. All five active channels (4.19, 4.20, 4.21, 4.22 and 5.0) are supported. The list offers the default, **Latest production release** (`the-latest-production-version`, chosen by iServer), followed by the latest stable release of each supported channel, newest first; only those releases can be chosen, so a saved `cluster_version` that is not in the list (for example an older patch) shows as the latest production release until you apply a listed release. With the Console Registration login, the **Assisted Installer** column shows whether the installer offers each release, and Apply warns if you pick one it does not. For Cilium, **Refresh** reads the registry's Helm index when you enter its URL as **Version catalog URL** on the Cilium Registry page, otherwise the tested versions in the matrix are offered. Without network access the tested versions in the matrix are used.

Keep the matrix current with the drift check, which exits 1 when a supported OpenShift channel reaches end of life, or (with your registry's index) a Cilium release newer than the recommended one exists or the recommended one disappears. It also notes newer OpenShift channels that are generally available but not in the matrix. A weekly GitHub Actions job runs it against the public sources. To include your registry's Cilium index, run it from cron where the token is available:

```bash
0 13 * * 1  CILIUM_VERSION_INDEX_URL=https://registry.example.com/.../index.yaml isovalent_registry_token=... \
            python3 /path/to/Cisco-AI-PODs/scripts/version_support_matrix.py check
```

`python3 scripts/version_support_matrix.py channels` prints the same channel table.

### Selecting Cilium

Choose the CNI and its version in the install file (`host_vars/openshift/install.ezai.yaml`), on the Cluster Deployment page (**Container network (CNI)**, then **Apply to YAML** and Save):

```yaml
openshift:
  install:
    bare_metal:
      cluster_networking:
        cilium:
          enable_hubble_metrics: false
          enable_kube_proxy_replacement: false
          version: 1.19.7
        container_network_interface: Cilium
```

Prepare install (phase 1) writes `"network_type": "Cilium"` and `"cilium": {"version": "1.19.7"}` into `cluster.json`; iServer then downloads the Isovalent manifests for that version and applies its automated fixups: the cluster pool CIDR and mask come from `cluster_network`, and the operator runs one replica on a single-node cluster ([Cilium fixups](https://github.com/datacenter/iserver/blob/main/doc/ocp/bm/cilium_fixup.md)). The CiliumConfig is not generated for now (the current iServer version fails with it): `roles/openshift_install/templates/cilium-config.yaml.j2` is kept and its task is commented out in the role, so `enable_hubble_metrics` and `enable_kube_proxy_replacement` have no effect until it is re-enabled. Prepare install stops with a clear message if Cilium is selected without `cilium.version`.

`cilium.version` replaces the earlier `container_network_version`; Apply to YAML on the Cluster Deployment page removes the old key. Cilium is no longer an operator setting: an `openshift.operators.cilium` block in an older `operators.ezai.yaml` must be deleted (or run Build from inputs on the OpenShift GitOps page, which removes it).

---

## Authentication

Configure OpenShift OAuth to authenticate against Active Directory via LDAP/LDAPS, with automatic group synchronization.

**Role:** `roles/openshift_auth`  
**Variables:** `host_vars/openshift/ldap.ezai.yaml`  
**Tag:** `auth`

### Prerequisites

- Ansible with `kubernetes.core` collection
- `oc` CLI installed on Ansible controller
- OpenShift cluster token with `cluster-admin` privileges
- Active Directory service account with read access
- For LDAPS: CA certificate chain of LDAP server(s)

### Quick Start

1. **Get LDAP server certificate (LDAPS only):**
   ```bash
   openssl s_client -showcerts -connect ldap-server.example.com:636 </dev/null 2>/dev/null \
     | awk '/BEGIN CERTIFICATE/,/END CERTIFICATE/' > ca.crt
   ```

2. **Copy and edit LDAP variables in Visual Studio Code:**
   ```bash
   cp -r examples/openshift host_vars/
   code host_vars/openshift/ldap.ezai.yaml
   ```

   Before editing, follow [Prepare the Environment](guide_prepare_the_environment.md) and ensure the Red Hat YAML extension is installed and schema validation is enabled:
   - [Install Visual Studio Code Extensions](guide_prepare_the_environment.md#install-visual-studio-code-extensions)
   - [YAML Schema for auto-completion, Help, and Error Validation](guide_prepare_the_environment.md#yaml-schema-for-auto-completion-help-and-error-validation)

3. **Export credentials:**
   ```bash
   export ldap_bind_password="<bind_password>"
   export openshift_api_url="https://api.<cluster>.<domain>:6443"
   export openshift_token_id="<token>"
   ```

   Get token from OpenShift web console:
   - Click username (top-right) → **Copy login command** → **Display Token**

4. **Run the playbook:**
   ```bash
   ansible-playbook playbooks/deploy_openshift_phase2.yaml --tags auth
   ```

For detailed instructions, see [roles/openshift_auth/README.md](../roles/openshift_auth/README.md).

---

## Certificates

Manage custom CA bundle, ingress wildcard certificate, and API server certificate.

**Role:** `roles/openshift_certificates`  
**Tag:** `certificates`

### Prerequisites

- `oc` CLI installed on Ansible controller
- Ansible collections: `kubernetes.core`, `community.crypto`
- Cluster credentials with permission to patch cluster resources
- Certificate and key files available locally (PEM format, unencrypted)

### Quick Start

1. **Export credentials:**
   ```bash
   export openshift_api_url="https://api.<cluster>.<domain>:6443"
   export openshift_token_id="<token>"
   ```

2. **Run the playbook:**
   ```bash
   ansible-playbook playbooks/deploy_openshift_phase2.yaml --tags certificates
   ```

3. **Validate:**
   ```bash
   oc get configmap user-ca-bundle -n openshift-config -o yaml
   oc get secret ingress-tls-secret -n openshift-ingress
   oc get secret api-tls-secret -n openshift-config
   ```

For detailed instructions, see [roles/openshift_certificates/README.md](../roles/openshift_certificates/README.md).

---

## GitOps

Generate content for GitOps repositories (Helm charts and OLM catalogs for cluster operators).

**Role:** `roles/openshift_gitops`  
**Variables:** `host_vars/openshift/operators.ezai.yaml`  
**Tag:** `gitops`

### Quick Start

1. **Edit operators variables in Visual Studio Code:**
   ```bash
   code host_vars/openshift/operators.ezai.yaml
   ```

   Before editing, follow [Prepare the Environment](guide_prepare_the_environment.md) and ensure the Red Hat YAML extension is installed and schema validation is enabled:
   - [Install Visual Studio Code Extensions](guide_prepare_the_environment.md#install-visual-studio-code-extensions)
   - [YAML Schema for auto-completion, Help, and Error Validation](guide_prepare_the_environment.md#yaml-schema-for-auto-completion-help-and-error-validation)

2. **Define at minimum:**
   - `openshift.destination_directory`
   - `openshift.operators.openshift_gitops.gitops_repo_url`

3. **Run the playbook:**
   ```bash
   ansible-playbook playbooks/deploy_openshift_phase2.yaml --tags gitops
   ```

4. **Commit to GitOps repository:**
   ```bash
   cd <destination>
   git add . && git commit -m "Generated OpenShift operators" && git push
   ```

**Web UI:** on the **OpenShift GitOps** page, **Build from inputs** turns the Operators, NVIDIA AI Enterprise and OpenShift GitOps answers into the YAML. It also adds node MAC addresses from the inventory. When Gitea is not used, the **GitOps repository** section sets the working copy (`destination_directory`, default `<output>/gitops-repo`), branch and Git user. **Push to GitOps repository** commits the generated files and pushes them to `gitops_repo_url`. Files that exist only in the remote are kept, so operators you remove are not deleted from the repository. For HTTPS repositories, store the access token as `openshift.gitops_git_token` in the vault. Keep the repository private.

For detailed instructions, see [roles/openshift_gitops/README.md](../roles/openshift_gitops/README.md).

---

## Argo CD

Install the OpenShift GitOps Operator (Argo CD) on the cluster.

**Role:** `roles/openshift_argo_cd`  
**Tag:** `argocd`

### Quick Start

1. **Export credentials:**
   ```bash
   export openshift_api_url="https://api.<cluster>.<domain>:6443"
   export openshift_token_id="<token>"
   ```

2. **Run the playbook:**
   ```bash
   ansible-playbook playbooks/deploy_openshift_phase2.yaml --tags argocd
   ```

3. **Verify:**
   ```bash
   oc get csv -n openshift-gitops-operator
   ```

For detailed instructions, see [roles/openshift_argo_cd/README.md](../roles/openshift_argo_cd/README.md).

---

## Gitea

Deploy an internal Git repository (Gitea) for onboarding repositories.

**Role:** `roles/openshift_gitea`  
**Tag:** `gitea`

### Quick Start

1. **Export credentials:**
   ```bash
   export openshift_api_url="https://api.<cluster>.<domain>:6443"
   export openshift_token_id="<token>"
   ```

2. **Run the playbook:**
   ```bash
   ansible-playbook playbooks/deploy_openshift_phase2.yaml --tags gitea
   ```

3. **Verify:**
   ```bash
   oc get gitea -n gitea-operator
   oc get route -n gitea-operator
   ```

For detailed instructions, see [roles/openshift_gitea/README.md](../roles/openshift_gitea/README.md).

---

## Common Troubleshooting

- **"oc not found":** Download from https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/
- **"Unauthorized":** Verify environment variables and get fresh token (they expire after 24 hours)
- **"Could not reach API":** Check cluster endpoint is reachable: `curl -k https://api.<cluster>.<domain>:6443`
- **All roles are idempotent — safe to re-run:** Fix the issue and run again
- **"Redfish vmedia mapping failed" / "Mount failed" on Install cluster:** run `scripts/vmedia_diagnose.py` (below) to see what the blade's CIMC reports.

### Virtual media diagnostics

`scripts/vmedia_diagnose.py` talks Redfish to the Fabric Interconnect directly (not through iServer), so every CIMC answer is visible. It uses the FI attached servers in `assisted-installer/server.json` (or `--fi IP --vault-file ...`), and `web.json` for the web server settings. On the appliance run it as root so it can read the Nginx log:

```bash
cd /home/automation-ui/Cisco-AI-PODs
sudo .venv/bin/python3 scripts/vmedia_diagnose.py inspect --url https://<appliance>/os-images/<file>.iso
sudo .venv/bin/python3 scripts/vmedia_diagnose.py mount --blade <inventory-id> --image <file>.iso
```

- `inspect` (read-only) shows per blade the CIMC firmware and clock (compared with this host), CIMC IP, gateway, VLAN and DNS, every virtual media slot with the CIMC's message, the CIMC log, the web server certificate, and whether the image URL answers from this host.
- `mount --capture` (as root, needs `tcpdump`; add `--cimc-ip` once per CIMC address if the FI does not report them) also records the CIMC's TCP traffic to the web server during the attempt and says where the connection fails: no packet arrives (path), a SYN is never answered (firewall or listener), a connection is reset before data (refused), or it fails after data (TLS handshake).
- `mount` ejects slot 3, inserts the image (a generated 1 MB test image unless `--url` or `--image` is given), prints a timestamped timeline of the slot, shows which requests the CIMC made to Nginx, then ejects and removes the test image. Use `--image` with the real OpenShift ISO to test it exactly as the install does.

What the CIMC's answer means (verified on a lab X-Series blade): a CIMC that can reach the server mounts within seconds and requests the file (`HEAD`, a 64-byte `GET`, `HEAD`); `Image file not found on server` means it reached Nginx but the file is missing or unreadable; an immediate `Mount failed` with no request in the Nginx log means the connection itself was refused or reset; a slot that stays `Updating` means traffic from the CIMC is being dropped. The CIMC does not validate the web server's certificate.

---

## Variable Files

The [examples](examples) folder contains example variable files. Copy to [host_vars](host_vars) and edit for your environment in Visual Studio Code:

```bash
mkdir -p host_vars
cp -r examples/openshift host_vars/
code host_vars/openshift/<file>.ezai.yaml
```

Important: use the Red Hat YAML extension and schema mapping from [Prepare the Environment](guide_prepare_the_environment.md#yaml-schema-for-auto-completion-help-and-error-validation) so invalid inputs are caught before playbook execution.

---

**Related:** [Cisco-AI-PODs README](../README.md)
