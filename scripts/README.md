# Scripts

Utility scripts for the Cisco AI POD collection. Unless noted otherwise, run them
from the repository root so relative default paths resolve correctly.

```bash
cd /path/to/Cisco-AI-PODs
python3 scripts/<script>.py --help
```

Dependencies come from [requirements.txt](../requirements.txt) (`PyYAML`, `tabulate`,
and related packages). Activate your virtual environment first.

---

## deploy_ai_pod.py

Runs the Cisco AI POD deployment stages with live, unbuffered child-process output.
Roles remain the implementation; this script owns role selection, ordering, and
sensitive-variable validation.

It loads and merges every `*.ezai.yaml` file found under the host vars directory,
validates sensitive variables, then runs the configured roles in this order:
`everpure`, `intersight`, `openshift`, `observability`. Roles that are not configured
in the merged model are skipped.

```bash
# Run every configured role
python3 scripts/deploy_ai_pod.py

# Run a single role
python3 scripts/deploy_ai_pod.py --role intersight

# Run several roles, in the standard order
python3 scripts/deploy_ai_pod.py --role everpure --role intersight

# Dry run where the underlying role supports check mode
python3 scripts/deploy_ai_pod.py --check

# Use a different host_vars location
python3 scripts/deploy_ai_pod.py --host-vars-dir ./lab/host_vars

# Load the default AI POD vault using a password file
python3 scripts/deploy_ai_pod.py --vault-password-file ~/.config/cisco-ai-pods/vault-password

# Use a different encrypted vault
python3 scripts/deploy_ai_pod.py \
  --vault-file ~/.config/cisco-ai-pods/vault.yaml \
  --vault-password-file ~/.config/cisco-ai-pods/vault-password
```

| Option | Description |
| --- | --- |
| `--role {everpure,intersight,openshift,observability}` | Run one role. Repeat the flag for multiple roles. Defaults to all. |
| `--host-vars-dir HOST_VARS_DIR` | Directory containing `*.ezai.yaml` files. Defaults to `host_vars/`. |
| `--vault-file VAULT_FILE` | Encrypted Ansible Vault file. Defaults to `vault-ai-pod.yaml`. |
| `--vault-password-file VAULT_PASSWORD_FILE` | File containing the Ansible Vault password. Defaults to `~/.config/cisco-ai-pods/vault-password`. If missing, the script tells you to create it there. |
| `--check` | Pass check mode where supported. |
| `--openshift-stage {phase1,iserver,phase2}` | Start the OpenShift role at this stage and continue through the rest. Defaults to `phase1`. |
| `--openshift-only-stage {phase1,iserver,phase2}` | Run a single OpenShift stage and stop. |

### OpenShift stages

The OpenShift role runs three stages in order:

| Stage | What runs |
| --- | --- |
| `phase1` | `playbooks/deploy_openshift_phase1.yaml`, the install prep |
| `iserver` | `iserver create ocp cluster bm --dir assisted-installer --mode install`, output streamed live |
| `phase2` | `playbooks/deploy_openshift_phase2.yaml`, certificates, auth, and operators |

Use the stage flags to resume after a failure instead of repeating completed work:

```bash
# Cluster is already installed, only run post-install configuration
python3 scripts/deploy_ai_pod.py --role openshift --openshift-stage phase2

# Re-run the iServer install, then continue into post-install
python3 scripts/deploy_ai_pod.py --role openshift --openshift-stage iserver

# Re-run install prep only, without touching the cluster
python3 scripts/deploy_ai_pod.py --role openshift --openshift-only-stage phase1
```

The `iserver` stage is skipped when `openshift.install.bare_metal` is not configured, and in `--check` mode.

The deployment decrypts the vault before validation and exports scalar values from
the `everpure`, `intersight`, `openshift`, and `splunk_observability` sections into
the child-process environment. Existing environment variables with the same names
are replaced by vault values. The decrypted content is never written to disk or
printed. Start from [examples/vault.example.yaml](../examples/vault.example.yaml),
fill in the values, encrypt the copy, and keep the password file outside the
repository. The default password-file location is `~/.config/cisco-ai-pods/vault-password`:

```bash
cp examples/vault.example.yaml vault-ai-pod.yaml
${EDITOR:-vi} vault-ai-pod.yaml
ansible-vault encrypt vault-ai-pod.yaml
chmod 600 ~/.config/cisco-ai-pods/vault-password
python3 scripts/deploy_ai_pod.py --vault-password-file ~/.config/cisco-ai-pods/vault-password
```

See [VALIDATE_SENSITIVE_VARIABLES.md](VALIDATE_SENSITIVE_VARIABLES.md) for the
validation rules.

---

## validate_sensitive_variables.py

Validates every sensitive environment variable required across the playbooks
(`intersight_ucs_provision`, `openshift_install`, `everpure`, `splunk_observability`)
against one or more merged data models. `deploy_ai_pod.py` calls this automatically,
but it is useful on its own before a deployment.

```bash
# Validate a single merged model
python3 scripts/validate_sensitive_variables.py --models model.json

# Validate several models at once
python3 scripts/validate_sensitive_variables.py --models model1.json model2.json

# Show a description for each sensitive variable type
python3 scripts/validate_sensitive_variables.py --models model.json --verbose
```

| Option | Description |
| --- | --- |
| `--models MODELS [MODELS ...]` | Required. Paths to one or more merged model JSON files. |
| `--schema SCHEMA` | Path to the sensitive-variable schema. Defaults to `schemas/sensitive/variables.json`. |
| `--verbose` | Print descriptions for each sensitive variable type. |

Exit codes:

- `0` — all required sensitive variables found and valid
- `1` — one or more sensitive variables missing or invalid

Full background, including the naming convention for each variable, is in
[VALIDATE_SENSITIVE_VARIABLES.md](VALIDATE_SENSITIVE_VARIABLES.md).

---

## merge_schemas.py

Bundles the split JSON schemas under `schemas/source/` into the single
VS Code-friendly schema at `schema/cisco-ai-pods.json`.

Each source file maps to a namespace, and nested Intersight files are merged into the
`intersight` namespace prefixed by their filename. A definition named
`adapter_configuration` in `schemas/source/intersight/policies.json` becomes
`intersight.policies.adapter_configuration` in the bundle, and all cross-file `$ref`
values are rewritten into internal `#/definitions/...` pointers.

Run this after editing anything under `schemas/source/`.

```bash
# Regenerate the canonical bundle
python3 scripts/merge_schemas.py

# Build to a scratch file first to review the result
python3 scripts/merge_schemas.py --output /tmp/cisco-ai-pods.json

# Bundle a different source tree
python3 scripts/merge_schemas.py --source-dir schemas/source --output schema/test.json
```

| Option | Description |
| --- | --- |
| `--source-dir SOURCE_DIR` | Directory containing the split JSON schemas. Defaults to `schemas/source`. |
| `--output OUTPUT` | Path for the generated bundled schema. Defaults to `schema/cisco-ai-pods.json`. |

The script fails loudly if a `$ref` cannot be resolved, so a successful run means the
bundle is internally consistent.

---

## check_schema_refs.py

Checks JSON schemas for broken `$ref` targets. Use it periodically, or in CI, to catch
references that were renamed or removed.

It recursively scans the given directories, so new subfolders are picked up
automatically. Directories holding a split composition root are validated using the same
resolution rules as `merge_schemas.py`, which prevents false failures on intentional
patterns such as `./intersight.json#/definitions/intersight.system`. Every other JSON
file, including generated bundles, is validated on its own.

```bash
# Scan schemas/ and schema/ recursively
python3 scripts/check_schema_refs.py

# Scan specific directories
python3 scripts/check_schema_refs.py schemas/source

# Print only problems, useful for cron or CI
python3 scripts/check_schema_refs.py --quiet

# Do not fail on http, https, or urn references
python3 scripts/check_schema_refs.py --allow-remote
```

| Option | Description |
| --- | --- |
| `directories ...` | Directories to scan recursively. Defaults to `schemas` and `schema`. |
| `--allow-remote` | Treat `http`, `https`, and `urn` references as acceptable. |
| `--quiet` | Only print problems. |

Reported problems include malformed JSON, missing target files, unresolved JSON
Pointers, and pointers missing a leading `/`.

Exit codes:

- `0` — no problems found
- `1` — at least one problem found

Example of a clean run:

```text
OK files=16 refs=1520 problems=0
```

---

## nvidia_support_matrix.py

Reports NVIDIA AI Enterprise GPU and component compatibility, and cross-references it
with the local configuration files. Most data is maintained in a static matrix inside
the script; some container image tags can be fetched live from NVIDIA documentation.

```bash
# Human-readable table
python3 scripts/nvidia_support_matrix.py

# Machine-readable output
python3 scripts/nvidia_support_matrix.py --format json
python3 scripts/nvidia_support_matrix.py --format csv

# Target a specific AI Enterprise version
python3 scripts/nvidia_support_matrix.py --version 8.1 --versions-only

# Populate DOCA image tags from the NVIDIA component matrix
python3 scripts/nvidia_support_matrix.py --fetch-live --version 8.1

# Detect AI Enterprise releases missing from the local matrix
python3 scripts/nvidia_support_matrix.py --check-updates

# Write JSON to a file, for Ansible integration
python3 scripts/nvidia_support_matrix.py --format json --output-file /tmp/matrix.json
```

| Option | Description |
| --- | --- |
| `--format {table,json,csv}` | Output format. Defaults to `table`. |
| `--version VERSION` | NVIDIA AI Enterprise version. Defaults to the version found in the examples. |
| `--variables VARIABLES` | Path to a variables file to cross-reference. |
| `--versions-only` | Show only software versions for the selected version. |
| `--fetch-live` | Fetch DOCA OFED Driver Container and DOCA Telemetry Service tags live. Use when static data shows `run --fetch-live`. |
| `--check-updates` | Check NVIDIA release notes for versions not yet in the local matrix. |
| `--output-file PATH` | Write JSON output to a file instead of stdout. |

`--fetch-live` and `--check-updates` require outbound network access to
`docs.nvidia.com`.

To add a new AI Enterprise release, run `--check-updates`, add the version block to
`NVIDIA_SUPPORT_MATRIX` in the script, then run `--fetch-live --version X.Y` to
populate the DOCA tags.

---

## regenerate_kubeconfig.py

Creates a new kubeconfig from an existing one by replacing the cluster CA bundle, and
optionally the API server URL or user token. The selected context and user
authentication are preserved.

```bash
# Replace the CA for the current context
python3 scripts/regenerate_kubeconfig.py \
  --kubeconfig-path ~/.kube/config \
  --ca-file ~/new-ca.crt \
  --output ~/new-kubeconfig

# Target a specific context and override the API server
python3 scripts/regenerate_kubeconfig.py \
  --kubeconfig-path ~/.kube/config \
  --context my-cluster-admin \
  --ca-file ~/new-ca.crt \
  --server https://api.example.com:6443 \
  --output ~/new-kubeconfig

# Produce a minimal, single-cluster kubeconfig
python3 scripts/regenerate_kubeconfig.py --ca-file ~/new-ca.crt --flatten --output ~/minimal-kubeconfig
```

| Option | Description |
| --- | --- |
| `--kubeconfig-path`, `--source` | Existing kubeconfig. Defaults to the first `KUBECONFIG` entry, otherwise `~/.kube/config`. |
| `--ca-file CA_FILE` | Required. PEM-encoded certificate authority file. |
| `--output OUTPUT` | Output path. Defaults to overwriting the source in place. |
| `--context CONTEXT` | Context to update. Defaults to `current-context`. |
| `--server SERVER` | Override the cluster API server URL. |
| `--token TOKEN` | Override the selected user's bearer token. |
| `--flatten` | Write only the selected cluster, user, and context. |

Omitting `--output` rewrites the source kubeconfig in place, so keep a backup when
experimenting.

---

## Shell helpers

These are not Python, but live in the same folder:

| Script | Purpose |
| --- | --- |
| `setup.sh` | Prepare the local development environment. |
| `check_ansible_env.sh` | Verify the Ansible environment prerequisites. |
| `run_ansible_lint.sh` | Run `ansible-lint` against the collection. |
| `sync-sanity-ignore.sh` | Sync the sanity test ignore entries. |

---

## Typical schema workflow

```bash
# 1. Edit the split sources under schemas/source/
# 2. Rebuild the bundle
python3 scripts/merge_schemas.py

# 3. Confirm nothing references a missing definition
python3 scripts/check_schema_refs.py
```
