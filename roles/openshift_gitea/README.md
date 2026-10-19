# OpenShift Gitea Role

Deploys an internal Git repository (Gitea) on OpenShift for onboarding repositories.

**Main Documentation:** [docs/openshift.md — Gitea](../../docs/openshift.md#gitea)

## Role Tasks

- `main.yaml` — Validates prerequisites, installs Gitea Operator, deploys Gitea instance

## What It Does

1. Validates `oc` CLI and required environment variables
2. Creates `gitea-operator` namespace
3. Creates OperatorGroup in namespace
4. Creates namespace-scoped CatalogSource (`redhat-rhpds-gitea`)
5. Creates Subscription for Gitea Operator (channel: stable)
6. Waits for operator deployment (`gitea-operator-controller-manager`) to be ready
7. Creates Gitea custom resource (`gitea-with-admin`) with defaults

## Files

| File | Description |
|------|-------------|
| `tasks/main.yaml` | Role entry point with full deployment workflow |
| `defaults/main.yaml` | Role defaults |
| `templates/operator-group.yaml.j2` | OperatorGroup manifest |
| `templates/catalog-source.yaml.j2` | CatalogSource for Red Hat Gitea catalog |
| `templates/subscription.yaml.j2` | Operator subscription manifest |
| `templates/instance.yaml.j2` | Gitea custom resource instance |

## Key Variables

Set via environment variables:

- `openshift_api_url` — OpenShift API URL
- `openshift_token_id` — OpenShift API token

No variables file needed — this role works with environment variables only.

## Default Gitea Configuration

The instance is created with these defaults (adjust templates if needed):

- **Namespace:** `gitea-operator`
- **Instance name:** `gitea-with-admin`
- **Admin user:** `opentlc-mgr`
- **Admin password:** Auto-generated (32 characters)
- **Admin email:** `opentlc-mgr@redhat.com`
- **SSL:** Enabled
- **User creation:** Enabled
- **User:** `lab-user` (the format has no `%d`, so the single user is not numbered)
- **Initial users:** 1

The route host is `gitea-with-admin-gitea-operator.apps.<cluster_name>.<base_dns_domain>`. When
`openshift.operators.gitea.enable` is true and `gitops_repo_url` is empty, the `openshift_gitops` role uses
`https://gitea-with-admin-gitea-operator.apps.<cluster_name>.<base_dns_domain>/lab-user/openshift-gitops-repo.git`.
Create the `openshift-gitops-repo` repository for `lab-user` and push the generated GitOps directory to it.

## Access Gitea

Get the route:
```bash
oc get route -n gitea-operator
```

Retrieve admin password:
```bash
# Option 1: From the Gitea resource status
oc get gitea gitea-with-admin -n gitea-operator -o jsonpath='{.status.adminPassword}{"\n"}{.status.userPassword}{"\n"}'

# Option 2: From operator logs
oc logs deploy/gitea-operator-controller-manager -n gitea-operator | grep -i password

# Option 3: From Gitea pod env (after deployment)
oc exec -n gitea-operator deploy/gitea-<name> -- env | grep ADMIN
```

## Idempotency

Fully idempotent. Safe to re-run. Resources are reconciled to desired state.

## Verification

Check operator status:
```bash
oc get ns gitea-operator
oc get operatorgroup -n gitea-operator
oc get catalogsource -n gitea-operator
oc get subscription -n gitea-operator
oc get csv -n gitea-operator
```

Check Gitea deployment:
```bash
oc get gitea -n gitea-operator
oc get pods -n gitea-operator
oc get svc -n gitea-operator
oc get route -n gitea-operator
```

## Troubleshooting

- **Operator subscription failing:** Verify catalog source is available and image is reachable from cluster
- **Gitea pod not starting:** Check pod logs: `oc logs -n gitea-operator pod/<gitea-pod>`
- **Admin credentials not working:** Wait for pod to be ready (CSI may take a minute); try retrieving from pod env
- **Routes not created:** Ensure ingress is configured on cluster
- **Token expired:** Get fresh token from OpenShift web console
- **Image pull errors:** Verify cluster can pull from `quay.io/rhpds/gitea-catalog:latest`

Check all resources:
```bash
oc get all -n gitea-operator
oc describe gitea gitea-with-admin -n gitea-operator
oc logs deploy/gitea-operator-controller-manager -n gitea-operator
oc get events -n gitea-operator --sort-by=.metadata.creationTimestamp
```

## Dependencies

This role depends on:
- `kubernetes.core` Ansible collection

Install prerequisites:
```bash
ansible-galaxy collection install kubernetes.core
```

## When to Use Gitea

Use Gitea when:
- No existing Git service (GitHub, GitLab, Gitea, etc.) is available
- You need to host internal repositories securely

**Do not** use public Git repositories for this workflow — they're not suitable for customer-specific infrastructure configuration.

See [docs/openshift.md — Gitea](../../docs/openshift.md#gitea) for full setup guide.
