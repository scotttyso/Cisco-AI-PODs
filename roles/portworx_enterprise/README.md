# Portworx CSI Role

Installs and configures Portworx on OpenShift using Everpure-generated credentials.

Main guide: [docs/everpure.md](../../docs/everpure.md)

## Critical Ordering

Portworx deployment must run only after OpenShift installation is complete.

Required dependency:
- [docs/openshift.md - Cluster Installation](../../docs/openshift.md#cluster-installation)

## Inputs

- Variables file: `host_vars/everpure/everpure.ezai.yaml`
- Generated credential file: `pure.json`
- Environment variables:
  - `openshift_api_url`
  - `openshift_token_id`

## Role Structure

- `tasks/main.yaml`: Role entry point and deployment flow

## What It Deploys

- Namespace from `everpure.portworx.namespace`
- Secret `px-pure-secret` from local `pure.json`
- Portworx Subscription `portworx-certified` in `openshift-operators`
- Portworx StorageCluster
- StorageClass resources from `everpure.portworx.storage_classes[]`

## Run

Run only Portworx after OpenShift install:

```bash
ansible-playbook playbooks/deploy_ai_pod_phase2.yaml --tags portworx
```

Run with Everpure credential generation:

```bash
ansible-playbook playbooks/deploy_ai_pod_phase2.yaml --tags everpure,portworx
```

## Validation

```bash
oc get subscription -n openshift-operators | grep portworx
oc get csv -n openshift-operators | grep -i portworx
oc get storagecluster -n <portworx-namespace>
oc get storageclass
```

## Troubleshooting

- `pure.json` missing:
  - Run Everpure first with required API tokens exported.
- Operator not ready:
  - Check Subscription and CSV status in `openshift-operators`.
- StorageCluster not progressing:
  - Review events and describe StorageCluster.

Useful commands:

```bash
oc describe storagecluster -n <portworx-namespace>
oc get events -n <portworx-namespace> --sort-by=.metadata.creationTimestamp
```
