# OpenShift Deployment Guide

This guide provides comprehensive workflows for deploying and configuring OpenShift clusters as part of the Cisco AI PODs infrastructure. Follow the sections in order, or jump to a specific role's section if you only need that component.

## Quick Navigation

- **[Cluster Installation](#cluster-installation)** — Generate manifests and deploy bare-metal OpenShift
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
