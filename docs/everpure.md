# Everpure and Portworx Deployment Guide

This guide covers the storage workflows for Cisco AI PODs:

- Everpure array configuration (FlashArray and FlashBlade)
- Portworx deployment and StorageCluster setup on OpenShift

## Table of Contents

- [Everpure and Portworx Deployment Guide](#everpure-and-portworx-deployment-guide)
  - [Table of Contents](#table-of-contents)
  - [Prerequisites](#prerequisites)
  - [Deployment Order](#deployment-order)
  - [Configuration Files](#configuration-files)
  - [Environment Variables](#environment-variables)
  - [Quick Start](#quick-start)
  - [Everpure Array Workflow](#everpure-array-workflow)
  - [Portworx Workflow](#portworx-workflow)
  - [Validation](#validation)
  - [Troubleshooting](#troubleshooting)

## Prerequisites

- Install Ansible collections from `requirements.yaml`
- Install Python dependencies from `requirements.txt`
- Ensure network connectivity to Everpure arrays and OpenShift API

Prepare the environment first:

- [Prepare the Environment](guide_prepare_the_environment.md)
- [Install Visual Studio Code Extensions](guide_prepare_the_environment.md#install-visual-studio-code-extensions)
- [YAML Schema for auto-completion, Help, and Error Validation](guide_prepare_the_environment.md#yaml-schema-for-auto-completion-help-and-error-validation)

Important: Use Visual Studio Code (not terminal editors) to edit `.ezai.yaml` files so the Red Hat YAML extension can validate schema and catch input issues before running automation.

## Deployment Order

Use this order to avoid dependency issues:

1. Configure Everpure arrays (FlashArray/FlashBlade).
2. Complete OpenShift installation first.
3. Generate `pure.json` and deploy Portworx on OpenShift.

Critical dependency: Portworx installation must occur only after OpenShift installation is complete. Follow [OpenShift Deployment Guide](openshift.md#cluster-installation) before any Portworx deployment.

## Configuration Files

- `host_vars/everpure/everpure.ezai.yaml`: Everpure and Portworx input variables
- `04-storage-everpure/automation/roles/everpure/tasks/main.yml`: Everpure role entry point
- `roles/portworx_enterprise/tasks/main.yaml`: Portworx role entry point

Edit variables in Visual Studio Code:

1. Open the repository folder in Visual Studio Code
2. Open `host_vars/everpure/everpure.ezai.yaml`
3. Validate warnings/errors from the Red Hat YAML extension

## Environment Variables

The encrypted deployment vault supplies one API token per `api_token_id` used in
variables. The script uses `~/.config/cisco-ai-pods/vault-password` by default.

Other values are referenced by number in the YAML and stored in the `everpure` vault section:

| YAML key | Vault / environment name |
|---|---|
| `array_certificates[].private_key_passphrase` | `private_key_passphrase_<n>` |
| `directory_service.configuration[].bind_password` | `ldap_binding_password_<n>` (Shared services LDAP bind password is `1`) |
| `settings.security.users[].password` | `local_user_password_<n>` |
| SNMP `community` | `everpure_snmp_community_<n>` |
| SNMP `auth_passphrase` / `privacy_passphrase` | `everpure_snmp_auth_passphrase_<n>` / `everpure_snmp_privacy_passphrase_<n>` |

On the WebUI Everpure page, check each policy under **Passwords and secrets > Policy passwords and secrets**
and set how many values it uses. For Array Certificates, upload the PEM certificate and key files; they are
saved in `<environment>/certificates/everpure/` and referenced by absolute path as `certificate_file`,
`intermediate_certificate_file`, and `private_key_file`. The upload button in **Variables** adds your own
YAML files under `host_vars/everpure/uploads/`; they are merged after `everpure.ezai.yaml`.

```bash
python3 scripts/deploy_ai_pod.py --role everpure
```

OpenShift credentials can be stored in the `openshift` section of
`vault-ai-pod.yaml` before Portworx deployment.

## Quick Start

Run Everpure array configuration only:

```bash
python3 scripts/deploy_ai_pod.py --role everpure
```

Run Portworx only (after OpenShift install is complete):

```bash
ansible-playbook playbooks/deploy_ai_pod_phase2.yaml --tags portworx
```

Run both together:

```bash
python3 scripts/deploy_ai_pod.py --role everpure
ansible-playbook playbooks/deploy_storage.yaml --tags portworx
```

Run full stack instead:

```bash
python3 scripts/deploy_ai_pod.py
```

## Everpure Array Workflow

The Everpure role configures FlashArray and FlashBlade settings from input variables:

- Network settings
- Access/security settings
- System settings
- FlashBlade notifications (if configured)

Role details: [04-storage-everpure/automation/roles/everpure/README.md](../04-storage-everpure/automation/roles/everpure/README.md)

### Appliance certificates (Web UI)

The **Appliance certificates** card on the Everpure page creates one private key and CSR per FlashArray or FlashBlade. The appliances come from `array_fqdn` in the YAML, and you can add extra FQDNs. The common name is the appliance FQDN and is also included in the subject alternative names, along with any extra DNS names.

1. Click **Generate keys and CSRs**, then **Download CSRs** and have them signed.
2. Upload each signed chain: the server certificate first, followed by any intermediate certificates. The UI checks the chain against the key and saves the files under `certificates/everpure/` in the environment.
3. Click **Add to YAML** to add or update the `everpure.settings.security.certificates.array_certificates` entries.

When the environment is saved to Git with **Store secrets in the repository** enabled, private keys are committed only inside the encrypted `certificate-keys.vault.yaml`. PEM key files are never committed.

## Portworx Workflow

The combined Everpure + Portworx flow does the following:

1. Creates or rotates the Portworx API user on each array/blade
2. Renders `pure.json` from template values
3. Deploys Portworx operator on OpenShift
4. Creates StorageCluster
5. Creates StorageClass resources from configured entries

Role details: [roles/portworx_enterprise/README.md](../roles/portworx_enterprise/README.md)

## Validation

Validate Portworx deployment:

```bash
oc get subscription -n openshift-operators | grep portworx
oc get csv -n openshift-operators | grep -i portworx
oc get storagecluster -n <portworx-namespace>
oc get storageclass
```

Validate PVC provisioning using examples:

```bash
oc apply -f examples/everpure/pvc/
oc get pvc -A
```

## Troubleshooting

- `pure.json` missing: Verify each `api_token_id` has matching `everpure_api_token_<id>`
- Portworx operator not ready: Check Subscription and CSV in `openshift-operators`
- StorageCluster pending: Inspect events and describe the StorageCluster
- YAML input issues: Open files in Visual Studio Code and fix Red Hat YAML validation errors

Helpful commands:

```bash
oc describe storagecluster -n <portworx-namespace>
oc get events -n <portworx-namespace> --sort-by=.metadata.creationTimestamp
```
