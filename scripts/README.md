# Scripts

Utility scripts for the Cisco AI POD collection. Unless noted otherwise, run them
from the repository root so relative default paths resolve correctly.

```bash
cd /path/to/Cisco-AI-PODs
python3 scripts/<script>.py --help
```

Dependencies come from [requirements.txt](../requirements.txt) (`PyYAML`, `tabulate`,
and related packages). Activate your virtual environment first.

| Section | Purpose |
| --- | --- |
| [build_initial_inventory.py](#build_initial_inventorypy) | Build the initial inventory from order `.xlsx` files. |
| [deploy_ai_pod.py](#deploy_ai_podpy) | Run the AI POD deployment roles in order. |
| [validate_sensitive_variables.py](#validate_sensitive_variablespy) | Validate required sensitive environment variables. |
| [update_nexus_switch_inventory.py](#update_nexus_switch_inventorypy) | Read MAC, model, and serial from Nexus switches and update the YAML. |
| [nxos_bootflash_stage.py](#nxos_bootflash_stagepy) | Prepare switch bootflash and copy NX-OS images from SCP. |
| [nd_switch_fabric_lookup.py](#nd_switch_fabric_lookuppy) | Look up the ND fabric name for a list of switch IPs. |
| [nd_stage_nexus_updates.py](#nd_stage_nexus_updatespy) | Configure per-device ND update groups, report checks, and image staging. |
| [ucs_imc_firmware.py](#ucs_imc_firmwarepy) | Report running firmware on standalone UCS C-Series servers. |
| [merge_schemas.py](#merge_schemaspy) | Bundle the split JSON schemas. |
| [check_schema_refs.py](#check_schema_refspy) | Check JSON schemas for broken `$ref` targets. |
| [nvidia_support_matrix.py](#nvidia_support_matrixpy) | Report NVIDIA AI Enterprise compatibility. |
| [regenerate_kubeconfig.py](#regenerate_kubeconfigpy) | Rebuild a kubeconfig with a new CA, server, or token. |
| [Shell helpers](#shell-helpers) | Environment setup, lint, and sanity helpers. |
| [Typical schema workflow](#typical-schema-workflow) | Edit, bundle, and check the schemas. |

## build_initial_inventory.py

The builder lives in `00-environment-prep/automation/scripts/`; this path is a
compatibility wrapper. Read all `.xlsx` files in a folder and write rows with a MAC address to
`host_vars/initial_inventory.ezai.yaml`. The script prompts for the folder;
press Enter to use `~/orders`. Each entry has a placeholder hostname, a
sequential `198.18.0.X` address, MAC, PID, and serial number.

```bash
python3 scripts/build_initial_inventory.py
# Optional output location:
python3 scripts/build_initial_inventory.py --output /path/to/initial_inventory.ezai.yaml
```

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
| `--intersight-scope {all,domains,servers}` | Deploy every file under `host_vars/intersight` (default), or only the shared top-level `intersight/*.ezai.yaml` files plus the `domains/` or `servers/` subfolder. The UI's Intersight Domains and Servers pages use this so each page deploys only its own files. |
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

## update_nexus_switch_inventory.py

Connects to the Nexus switches listed in the fabric YAML, reads the mgmt0 MAC,
module model, and VDH serial number, then updates the matching DHCP reservations
and fabric switch entries. It writes nothing unless every switch responds with
all three values. New SSH host keys are shown for verification in the terminal.

Export the switch password in the same shell used to run the script. Do not echo
the password:

```bash
export NEXUS_PASSWORD
python3 scripts/update_nexus_switch_inventory.py --dry-run
python3 scripts/update_nexus_switch_inventory.py
```

The script uses SSH with `RSAMinSize=1024` for these switches. The password is
read from the environment, placed briefly in a mode-0600 temporary file for
OpenSSH password prompting, and removed when the script exits. It is not put in
the SSH command line or sent as an SSH environment variable.

| Option | Description |
| --- | --- |
| `--user USER` | SSH username. Defaults to `admin`. |
| `--dhcp-file PATH` | DHCP variables file. Defaults to `host_vars/dhcp/dhcp.yaml`. |
| `--fabric-file PATH` | Fabric variables file. Defaults to `host_vars/nexus_dashboard/fabrics.ezai.yaml`. |
| `--connect-timeout SECONDS` | Per-connection timeout. Defaults to 10 seconds. |
| `--dry-run` | Query all switches and display values without writing YAML. |

---

## nxos_bootflash_stage.py

Prepares switch bootflash and copies images from an SCP server using the model-specific
upgrade paths in the input sheet. Connects through Nexus Dashboard or directly over SSH
with `--direct`. Start from
[nxos_bootflash_stage.example.yaml](../examples/nexus_dashboard/nxos_bootflash_stage.example.yaml)
and set the ND login, switches, SCP server, image catalog, and upgrade paths for your environment.

Passwords come from `NEXUS_DASHBOARD_PASSWORD` (when using ND), `NEXUS_PASSWORD`
(switches), and `SCP_SERVER_PASSWORD`. Set them securely in the shell running the script;
do not put passwords in the YAML or command-line arguments.

```bash
# Inspect the plan without deleting or copying files
python3 scripts/nxos_bootflash_stage.py \
  --config examples/nexus_dashboard/nxos_bootflash_stage.example.yaml --dry-run

# Prepare bootflash and copy the required images
python3 scripts/nxos_bootflash_stage.py \
  --config examples/nexus_dashboard/nxos_bootflash_stage.example.yaml
```

**File deletion:** Without `--dry-run`, images not protected by the configured catalog,
upgrade paths, running release, or boot variable can be deleted from bootflash. Review the
input sheet and dry-run output first. This script prepares images; it does not install them.

| Option | Description |
| --- | --- |
| `--config PATH` | Required YAML input sheet. |
| `--dry-run` | Report the plan without deleting or copying files. |
| `--direct` | Connect directly to switches instead of through ND. |
| `--only IP` | Limit execution to a configured switch IP; repeatable. |
| `--workers N` | Limit parallel sessions. |
| `--stagger SECONDS` | Delay between session starts; defaults to 2 seconds. |
| `--log-dir PATH` | Override the default timestamped directory under `LOGS/nxos_stage_logs/`. |

---

## nd_switch_fabric_lookup.py

Logs in to the Nexus Dashboard API and prints the hostname and fabric name for each IP in
`switches.hosts`. Start from
[nd_switch_fabric_lookup.example.yaml](../examples/nexus_dashboard/nd_switch_fabric_lookup.example.yaml);
an `nxos_bootflash_stage.yaml` sheet also works if its ND username can log in to the API.
The password comes from `NEXUS_DASHBOARD_PASSWORD` (prompted when unset). Exits with 2 if any IP
is not found.

```bash
python3 scripts/nd_switch_fabric_lookup.py \
  --config examples/nexus_dashboard/nd_switch_fabric_lookup.example.yaml
```

| Option | Description |
| --- | --- |
| `--config PATH` | Required YAML input sheet. |
| `--domain NAME` | ND login domain; overrides `nexus_dashboard.domain` (default `local`). |
| `--yaml` | Print results as YAML instead of a table. |

---

## nd_stage_nexus_updates.py

Uses the Nexus Dashboard Manage API to select switches, create or reuse update groups,
configure report checks, and stage an image already uploaded to ND.
Start from
[nxos_update_groups.example.yaml](../examples/nexus_dashboard/nxos_update_groups.example.yaml).
The sheet configures ND host, username, authentication domain, TLS verification, timeout,
credential source, and either named `update_groups` (each with a `hosts` list) or
`switches.hosts` for one group per switch. Hosts are switch names, management IPs, or
serials. Switches in a named group must share a fabric, target image, and check set, so
keep vPC pairs and standalone switches in separate groups. With neither section set, the
script prompts for device selection. CLI settings override YAML values; `--device`
overrides `update_groups`.

Target selection is restricted to N9K devices. Without `upgrade_rules`, the defaults are:

| Running Release / Model | Target |
| --- | --- |
| Any N9K running 9.3 | 9.3.16 |
| 93180YC-EX or 93108TC-EX running 10.3 | 10.3.10 |
| Other N9K running 10.3 | 10.6.4 |

Add a top-level `upgrade_rules` list to the input sheet to **replace all defaults**.
Rules are evaluated in order; the first match wins. Each rule requires `models`
(a nonempty list of case-insensitive shell-style patterns, such as `N9K*` or an
exact model), `source_version` (a quoted dotted version prefix), and `target_version`
(a quoted dotted release). Source `"10.6"` matches `10.6(3)` or `10.6.3`, but not `10.60`.
For example, to allow only the following rule:

```yaml
upgrade_rules:
  - models: ["N9K-C93240YC-FX2"]
    source_version: "10.6"
    target_version: "10.6.4"
```

Verify the supported upgrade path and desired target before using this example.
To retain the original rules as well, include them explicitly as shown in the
example sheet. Empty or malformed rule lists are rejected.

The exact filename is resolved from ND's uploaded-image catalog. Missing or ambiguous
matches stop execution. Switches not matching any rule are skipped.

```bash
# Read-only plan
python3 scripts/nd_stage_nexus_updates.py \
  --config examples/nexus_dashboard/nxos_update_groups.example.yaml

# Configure groups, request pre-reports, and stage images; no software upgrade
python3 scripts/nd_stage_nexus_updates.py \
  --config examples/nexus_dashboard/nxos_update_groups.example.yaml \
  --apply --run-pre-report
```

Passwords come from the configured `password_env` variable (default `NEXUS_PASSWORD`
when no sheet is supplied), an interactive prompt, or an encrypted Ansible Vault.
Vaults must contain `nexus_dashboard.nexus_dashboard_password`. The vault-password file
must have mode `0600`; keep it outside the repository. Relative vault paths in YAML resolve
from the sheet's directory; `~` paths are supported.

```bash
python3 scripts/nd_stage_nexus_updates.py \
  --config examples/nexus_dashboard/nxos_update_groups.example.yaml \
  --vault-file ~/.config/cisco-ai-pods/nd-vault.yaml \
  --vault-password-file ~/.config/cisco-ai-pods/vault-password
```

On apply, the script creates or reuses 18 `nxos_` custom replacements from ND's
existing report definitions, plus three new custom checks (`nxos_Running_config`:
`show running-config`, `nxos_Default_route`: `show ip route 0.0.0.0 vrf all`, and
`nxos_mac_address`: `show mac address dynamic | sort`), and sets
their post-update delays to 360 seconds. Original
catalog entries remain unchanged; an existing `mac_address` check is not required.
Checks created with the previous prefix are not renamed or deleted.
Each group selects only applicable replacements, excluding
overlapping default checks. Standalone switches omit vPC checks; dual-supervisor redundancy
is selected only for 9508s. Custom checks copy visible commands and filters, but equivalence
to ND's built-in validators is not guaranteed.

Existing groups containing only the planned switches can be reused after a partial run. The script
reads back the saved report selection before submitting report or staging requests.
Acceptance of a request does not establish completion or a passing report; inspect results
in ND. **The script never starts the NX-OS upgrade.**

| Option | Description |
| --- | --- |
| `--config PATH` | YAML environment input sheet. |
| `--nd-url URL`, `--username USER`, `--domain DOMAIN` | Override the ND endpoint and login settings. |
| `--device NAME_OR_IP_OR_SERIAL` | Per-device group selection; overrides YAML `update_groups`/`switches`; repeatable. |
| `--password-env NAME` | Override the password environment variable. |
| `--vault-file PATH`, `--vault-password-file PATH` | Load encrypted ND credentials locally. |
| `--apply` | Configure checks and groups and request image staging; default is plan-only. |
| `--run-pre-report` | With `--apply`, request pre-report execution before staging. |
| `--request-timeout SECONDS` | Per-request read timeout; defaults to 600 seconds. |
| `--insecure` | Disable TLS verification and suppress its warning; use only for trusted lab endpoints. |
| `--verify-tls` | Require TLS verification even when disabled in YAML. |

---

## ucs_imc_firmware.py

Logs in to standalone UCS C-Series servers through the Cisco IMC XML API
(`https://<host>/nuova`) and reports the model, serial number, and running
firmware versions. Hosts are queried in parallel, and each session is logged out
when done.

Export the IMC password in the same shell used to run the script. Do not echo
the password:

```bash
export local_user_password_1
```

Hosts can be passed on the command line, comma or space separated, or in a file.
Files ending in `.yaml` or `.yml` must contain a `hosts` list. Any other file is
read as plain text with one host per line and `#` comments allowed. Start from
[examples/ucs_imc/hosts.example.yaml](../examples/ucs_imc/hosts.example.yaml):

```yaml
hosts:
  - 192.168.65.103
  - 192.168.65.105
  - 192.168.65.106
```

```bash
# All running firmware components per server
python3 scripts/ucs_imc_firmware.py 192.168.65.106,192.168.65.105

# Only the CIMC system firmware (sys/rack-unit-N/mgmt/fw-system), one row per server
python3 scripts/ucs_imc_firmware.py -f examples/ucs_imc/hosts.example.yaml --system-only

# JSON output
python3 scripts/ucs_imc_firmware.py -f examples/ucs_imc/hosts.example.yaml --system-only --json
```

| Option | Description |
| --- | --- |
| `hosts ...` | IMC IPs or hostnames, comma and/or space separated. |
| `-f`, `--hosts-file PATH` | YAML file with a `hosts` list, or a text file with one host per line. |
| `-u`, `--username USER` | IMC username. Defaults to `admin`. |
| `-p`, `--password-env NAME` | Environment variable holding the password. Defaults to `local_user_password_1`. |
| `--system-only` | Only report the `sys/rack-unit-N/mgmt/fw-system` version per server. |
| `--json` | Print JSON instead of a table. |
| `--verify` | Verify TLS certificates. Off by default because IMC usually uses self-signed certificates. |
| `--timeout SECONDS` | HTTP timeout per request. Defaults to 30 seconds. |
| `--workers N` | Number of hosts to query in parallel. Defaults to 10. |

Exit codes:

- `0` — every host returned data
- `1` — one or more hosts failed. The error is shown in that host's output.

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
