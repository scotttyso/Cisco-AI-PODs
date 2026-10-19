# OpenShift Certificates Role

Manages custom CA bundle, ingress wildcard certificate, and API server certificate with validation and rollout monitoring.

**Main Documentation:** [docs/openshift.md — Certificates](../../docs/openshift.md#certificates)

## Role Tasks

- `main.yaml` — Validates certificates, applies ConfigMaps/Secrets, patches cluster resources, monitors rollout

## What It Does

1. Validates `oc` CLI and required environment variables
2. Validates certificate file existence and format
3. Creates/updates `user-ca-bundle` ConfigMap in `openshift-config`
4. Patches proxy/cluster to trust user CA bundle
5. Waits for master MachineConfigPool update
6. Prompts before ingress update
7. Creates/updates ingress TLS secret, patches ingress controller
8. Waits for OAuth and router pod readiness
9. Prompts before API update
10. Creates/updates API TLS secret, patches apiserver/cluster
11. Waits for kube-apiserver rollout stabilization

## Files

| File | Description |
|------|-------------|
| `tasks/main.yaml` | Role entry point with full certificate workflow |
| `defaults/main.yaml` | Role defaults |
| `templates/user-ca-bundle.yaml.j2` | ConfigMap template for user CA |
| `templates/ingress-tls-secret.yaml.j2` | Secret template for ingress cert/key |
| `templates/api-tls-secret.yaml.j2` | Secret template for API cert/key |

## Key Variables

Set in `host_vars/openshift/certificates.ezai.yaml`:

- `openshift.certificates.user_ca_bundle_file` — Path to user CA bundle (PEM)
- `openshift.certificates.ingress_certificate_file` — Path to ingress cert (PEM)
- `openshift.certificates.ingress_key_file` — Path to ingress private key (PEM)
- `openshift.certificates.api_certificate_file` — Path to API cert (PEM)
- `openshift.certificates.api_key_file` — Path to API private key (PEM)

Set via environment variables:

- `openshift_api_url` — OpenShift API URL
- `openshift_token_id` — OpenShift API token

## Certificate Requirements

- **Private keys:** Unencrypted PEM format
- **Ingress cert:** Must cover `*.apps.<cluster-name>.<base-domain>`
- **API cert:** Must include `api.<cluster-name>.<base-domain>` in SAN
- **Chain order:** Leaf cert first, then intermediates, then root
- **User CA bundle:** Root CA(s) trusted by organization

### Generate CSRs

**API:**
```bash
openssl req -newkey rsa:2048 -keyout api.key -out api.csr \
  -subj "/CN=api.<cluster>.<domain>/O=Org/C=US" \
  -addext "subjectAltName=DNS:api.<cluster>.<domain>"
```

**Ingress:**
```bash
openssl req -newkey rsa:2048 -keyout ingress.key -out ingress.csr \
  -subj "/CN=apps.<cluster>.<domain>/O=Org/C=US" \
  -addext "subjectAltName=DNS:apps.<cluster>.<domain>,DNS:*.apps.<cluster>.<domain>"
```

The subject alternative names include the common name. With an openssl config file, the equivalent is:

```ini
# API
[alt_names]
DNS.1 = api.<cluster>.<domain>

# Ingress
[alt_names]
DNS.1 = apps.<cluster>.<domain>
DNS.2 = *.apps.<cluster>.<domain>
```

The WebUI Certificates page generates both CSRs with these names.

## Idempotency

Safe to re-run. Existing resources are reconciled to desired state. Patch operations are idempotent.

## Validation

```bash
# Check user CA
oc get configmap user-ca-bundle -n openshift-config -o yaml

# Check ingress cert
oc get secret ingress-tls-secret -n openshift-ingress
oc get ingresscontroller.operator/default -n openshift-ingress-operator -o yaml

# Check API cert
oc get secret api-tls-secret -n openshift-config
oc get apiserver cluster -o yaml

# Monitor rollouts
oc get clusteroperators kube-apiserver
oc get mcp
```

## Troubleshooting

- **Certificate parse error:** Verify PEM format with `openssl x509 -in <cert> -noout -text`
- **Ingress still serving old cert:** Re-run playbook and wait for router pod recreation
- **API not stabilizing:** Check `oc get clusteroperators kube-apiserver` conditions
- **File not found:** Verify paths in variables file are correct relative to playbook directory

Check logs:
```bash
oc logs -n openshift-config operator deployment
oc logs -n openshift-ingress-operator deployment
oc logs -n openshift-kube-apiserver pod/<api-server>
```

See [docs/openshift.md — Certificates](../../docs/openshift.md#certificates) for full setup guide.
