# Automation - Subsystem 01 (Nexus Dashboard 4.3.x cluster install)

Drives the same procedure documented in [`../docs/MOP-ND4-install.md`](../docs/MOP-ND4-install.md) end-to-end:

- **Imaging**: `iso_reimage` installs the selected ISO on all three nodes; ND-1 also runs first-boot bootstrap. `factory_preinstalled` skips imaging only after pre-flight positively verifies the selected release on every node, then runs the same ND-1 first-boot bootstrap without mounting an ISO.
- **Cluster**: `cisco.nd.nd_setup` consumes the canonical Ansible inventory and runtime-discovered serials after all three nodes already have the target release.
- **Validate**: poll cluster status and write a Markdown report.

## Setup
The UI generates a site inventory for each environment. Do not edit the checked-in example as site data; use the generated inventory explicitly with `-i inventories/<environment>/inventory.yml` (and `--ansible-inventory` for the Python precheck CLI). `inventories/example/` documents the expected structure only.

```bash
cd 01-nd-cluster/automation
source .venv-aipod-inf/bin/activate
pip install -r requirements-aipod-inf.txt
ansible-galaxy collection install -r requirements-aipod-inf.yml \
  -p ../../build/galaxy/01-nd-cluster

# Edit the UI-generated inventory for this environment:
#   ../../inventories/<environment>/group_vars/nd_cluster.yml
#   ../../inventories/<environment>/host_vars/nd-*.yml
# Create a gitignored vault in the generated inventory:
cp ../../inventories/example/group_vars/vault.yml.example \
  ../../inventories/<environment>/group_vars/vault.yml
${EDITOR:-vi} ../../inventories/<environment>/group_vars/vault.yml
chmod 600 ../../inventories/<environment>/group_vars/vault.yml
```

The environment vault may remain plaintext. Ansible Vault encryption is recommended for
customer environments but optional; if selected, run `ansible-vault encrypt`
on the file and supply its password when running the playbook. Secrets must
never appear inline in shell history, git, or chat. The required key names are
documented in `inventories/example/group_vars/vault.yml.example`.

See [`RESUME.md`](RESUME.md) for the full secrets-from-keychain workflow,
including how to safely resume a paused install.

## Credentials (must be treated as distinct)

This automation deals with two **independent credentials** with different blast radii. Keep them logically separate even if your example environment happens to set them to the same string:

| Credential | Scope | Env var (default `pass_ref`) | Set on | Used by |
|---|---|---|---|---|
| **CIMC `admin` password** | Out-of-band hardware mgmt of one ND appliance (Redfish, vKVM, SOL) | Per-node `ND1_CIMC_PASSWORD` / `ND2_` / `ND3_` reference backed by Vault | Each server CIMC | `cimc_redfish.py`, `sol_bootstrap.py`, runtime serial discovery |
| **ND cluster `admin` password** | Nexus Dashboard cluster login (UI, API, CLI) | `ND_ADMIN_PASSWORD` | The cluster itself, set at first-boot of node 1 | `sol_bootstrap.py` (bootstrap phase), `nd_api.py` |

**Rules:**

1. They are **separate variables in code, separate refs in inventory, separate rotation schedules in operations.** Never re-use one ref for both.
2. The inventory always keeps one reference per CIMC, even when this example inventory currently models the same value to all three.
3. Production deployments **must** set `CIMC_PASSWORD*` and `ND_ADMIN_PASSWORD` to **different** values. The schema and code do not enforce this — it is a documentation and operational convention. An example environment that sets them to the same string for convenience is acceptable; a customer copying that example inventory into production is not.
4. The playbook loads the four values from the gitignored site secret file and exposes them to Python only for the duration of the task that needs them.

## Run

```bash
cd <repo-root>
scripts/build_collection.sh

# Read-only prerequisite checks against the selected inventory.
python 01-nd-cluster/automation/scripts/main.py precheck --ansible-inventory inventories/<environment>/inventory.yml

# Complete workflow: precheck (including start-mode release verification) →
# image all three nodes when start_mode is iso_reimage → runtime serial
# discovery → cisco.nd.nd_setup → post-install validation.
ansible-playbook -i inventories/<environment>/inventory.yml \
  01-nd-cluster/automation/playbooks/01_nd_cluster.yml
```

Before teardown, capture the completed manual deployment with the read-only
baseline playbook. After automation, run the same playbook with
`nd_baseline_kind=automated`:

```bash
ansible-playbook -i inventories/<environment>/inventory.yml \
  01-nd-cluster/automation/playbooks/capture_nd_baseline.yml

ansible-playbook -i inventories/<environment>/inventory.yml \
  01-nd-cluster/automation/playbooks/capture_nd_baseline.yml \
  -e nd_baseline_kind=automated
```

The playbook writes only an allowlisted, secret-free JSON artifact under the
gitignored `01-nd-cluster/automation/state/baselines/` directory. It never
writes the raw API response.

Compare the two explicit artifacts after the automated capture. The command
fails non-zero for inventory drift, manual/automated configuration drift, or
node identity drift:

```bash
python3 01-nd-cluster/automation/scripts/compare_baselines.py \
  --manual 01-nd-cluster/automation/state/baselines/manual-<timestamp>.json \
  --automated 01-nd-cluster/automation/state/baselines/automated-<timestamp>.json
```

If `vault.yml` was encrypted, add `--ask-vault-pass`.

Run only the read-only readiness gate with `--tags preflight`. A check may be
skipped for diagnosis with `-e '{"nd_precheck_skip":["<check-id>"]}'`, but the
deployment run itself must not skip a failed critical check.

## Intersight claim prerequisites

The ND claim is a post-install capability owned by this subsystem. Before
running it, the ND cluster must be Running, the Cisco Intersight account must
already exist, and ND-MGMT must resolve and reach `svc.intersight.com` over
HTTPS. If Cisco Cloud Control integration is used, configure the Intersight
tenant in Cisco Cloud Control and ensure the claiming user has the required
permissions. The shared non-secret site inputs are the `intersight_*` values
in `inventories/<environment>/group_vars/all.yml`; claim consumes the Intersight
endpoint, credentials, and selected resource group. Do not inventory a Cisco Cloud Control
tenant group as `intersight_*`. The API key ID and private key are the gitignored
`vault_intersight_api_key_id` and `vault_intersight_api_private_key` values.

Device ID and Claim Code are discovered only at runtime. They are never added
to inventory, the vault, test reports, or logs. The normal action verifies an
existing expected claim or claims an unclaimed ND cluster. A reclaim is a
separate, explicitly confirmed operation; it must never be selected by a
persisted inventory value.

Run the normal claim-or-verify capability on a Running ND cluster:

```bash
ansible-playbook -i inventories/<environment>/inventory.yml \
  01-nd-cluster/automation/playbooks/01_nd_cluster.yml \
  --tags intersight_claim
```

The selected resource group must already exist. The task preserves its current
selectors and appends the ND registration only when it is absent. For a
deliberate unclaim/reclaim maintenance test, use the separate entrypoint and
explicit one-run confirmation; it is never a normal deployment action:

```bash
ansible-playbook -i inventories/<environment>/inventory.yml \
  01-nd-cluster/automation/playbooks/reclaim_nd_intersight.yml \
  --tags intersight_reclaim \
  -e nd_intersight_allow_reclaim=true
```

## Troubleshooting

The deep guide is **[`docs/troubleshooting.md`](docs/troubleshooting.md)** —
empirical findings from the 4.2.1.10 example environment build. Read it before opening a TAC
case; it covers the recovery primitives you'll need.

Common quick hits:

- **`POST /v2/bootstrap/cluster` → 500 `Pending cluster bootstrap exists`** —
  there is **no API path** to clear this state (we tested every plausible
  endpoint; matrix in the troubleshooting doc). The fix is
  `acs reboot factory-reset` on ND-1, then re-drive the SOL first-boot
  dialog. See [`docs/troubleshooting.md` §1](docs/troubleshooting.md#1-pending-cluster-bootstrap-exists)
  and [§10](docs/troubleshooting.md#10-recovery-without-os-reinstall-acs-reboot-factory-reset).
- **`POST /bootstrap/verifyremoteservices` → 500 `Could not resolve host`** —
  your DNS can't resolve the NTP hostnames. Fix by switching NTP entries to
  site IP literals in `inventories/<environment>/group_vars/nd_cluster.yml`. See
  [`docs/troubleshooting.md` §2](docs/troubleshooting.md#2-verifyremoteservices-fails-on-ntp-dns-resolution).
- **Data plane silently broken (ND-1 can't reach ND-2/ND-3 over data)** —
  check STP Bridge Assurance on the access ports; ND VICs are end-stations
  and need `spanning-tree port type edge`, **not** `network`. See
  [`docs/troubleshooting.md` §3](docs/troubleshooting.md#3-stp-bridge-assurance-blocks-the-data-vlan).
- **`acs reboot ...` over SSH returns immediately and ND stays online** —
  use the foreground + stdin-pipe form, drop `-tt` and `nohup`. See
  [`docs/troubleshooting.md` §4](docs/troubleshooting.md#4-acs-reboot-from-ssh-doesnt-take-effect).
- `RedfishError login failed` — confirm CIMC IP, user, password (env var);
  confirm CIMC firmware supports Redfish.
- `SolError ... waiting for ...` — the installer/first-boot prompt wording
  changed slightly in your ND release. Edit the `PROMPT_*` regexes near the
  top of `scripts/sol_bootstrap.py`.
- `NdApiError POST ... → 4xx` — the cluster bringup REST contract differs
  from our default. Open the ND UI → click "API Inspector" while running
  the wizard manually once; copy the body shape into
  `nd_api.build_cluster_payload()`.

## Notes

- TLS verification is on by default. In labs with self-signed CIMC/ND certs, set `runtime.ca_bundle` to your internal CA bundle path. As a last resort for non-prod, set `runtime.verify_tls: false` and accept the warning.
- Secrets are held in the gitignored site secret file and injected only into tasks that need them. Encryption is supported and recommended for customers, but optional.
- All operations are idempotent. To force a fresh run, delete the directory pointed to by `runtime.state_dir` (default `state/`).
