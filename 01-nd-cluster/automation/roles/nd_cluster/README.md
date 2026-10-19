# cisco.aipod.nd_cluster - Ansible role (Phase 2 SKELETON / DRAFT)

> **Status:** Draft for team discussion. The role files in this directory are
> a **wedge** that demonstrates how Phase 2 Ansible would wrap the existing
> Phase 1 Python automation under `01-nd-cluster/automation/scripts/`.
> Nothing in this directory is wired into a working pipeline yet.

## What this role would do (when activated)

Drive the same Nexus Dashboard 4.x install procedure documented in
[`../../../docs/MOP-ND4-install.md`](../../../docs/MOP-ND4-install.md) and
implemented today by the Python scripts under `../scripts/`.

The role is **product-level** with **capability-named task files**, per
the granularity guidance in the `aipod-architecture` skill:

| Task file | Capability | Trigger |
|---|---|---|
| `tasks/preflight.yml` | Validate inventory + reachability + credentials | Always first |
| `tasks/image_node.yml` | Image one ND node via CIMC vMedia; bootstrap first-boot only on ND-1 | Every node when `start_mode: iso_reimage`; skipped for `factory_preinstalled` |
| `tasks/bootstrap_node.yml` | Bootstrap ND-1 over SOL without reinstalling | Once for `factory_preinstalled`, after release verification |
| `tasks/form_cluster.yml` | Bootstrap the 3-node cluster from ND-1 | Once per cluster |
| `tasks/intersight_claim.yml` | Claim or verify ND in Intersight; preserve and reconcile its resource-group selector | After the cluster is Running |
| `tasks/intersight_reclaim.yml` | Explicitly unclaim then reclaim ND | Only with one-run confirmation |
| `tasks/capture_baseline.yml` | Query and normalize a secret-free parity snapshot | Before teardown and after automation |
| `tasks/persistent_ips.yml` | Manage the persistent IP pool (day-2 capable) | Set or update |
| `tasks/remote_auth.yml` | Configure TACACS+ / LDAP (day-2) | Optional |
| `tasks/main.yml` | Dispatcher: selects by `nd_action` var | Always entrypoint |

Each task file maps 1:1 to a Phase 1 Python entrypoint
(`scripts/main.py precheck|node1|cluster|validate`) and 1:1 to a future
MCP tool (`bootstrap_nd_cluster`, `set_persistent_ips`, ...).

## How the wedge works (Phase 2 strategy)

The first iteration of this role does NOT reimplement the install in pure
Ansible. It **shells out** to the proven Python automation:

```yaml
# tasks/form_cluster.yml (sketch)
- name: Bootstrap ND cluster from ND-1
  ansible.builtin.command:
    cmd: "python3 scripts/main.py cluster"
    chdir: "{{ playbook_dir }}/.."
  environment:
    ND_ADMIN_PASSWORD: "{{ lookup('env', nd_admin_pass_ref) }}"
    ND1_CIMC_PASSWORD: "{{ lookup('env', nd1_cimc_pass_ref) }}"
    # ...
  register: cluster_bootstrap
  changed_when: "'changed=true' in cluster_bootstrap.stdout"
```

This gives us:
- An **Ansible surface** customers can call from a section playbook today.
- **Zero rewrite** of the validated install logic.
- A **migration path**: each capability can be replaced with native Ansible
  modules incrementally, one task file at a time, without changing the role
  contract or the section playbook above it.

Long-term (Phase 3) the Python helpers in `cisco-aipod/shared/lib/` get
wrapped as proper Ansible modules under `plugins/modules/` of the
`cisco.aipod` collection, and the `command:` shell-outs go away.

## Files in this skeleton

```
nd_cluster/
├── README.md                       # this file
├── meta/
│   ├── main.yml                    # role metadata + collection deps
│   └── argument_specs.yml          # input contract per task entrypoint
├── defaults/main.yml               # tunables; override via inventory
├── vars/main.yml                   # role-internal constants
├── handlers/main.yml               # restart/notify hooks (none yet)
└── tasks/
    ├── main.yml                    # dispatcher
    ├── preflight.yml
    ├── image_node.yml
    ├── form_cluster.yml
    ├── persistent_ips.yml
    └── remote_auth.yml
```

## Open questions for the team

These are highlighted in the discussion doc but worth restating here:

1. **Where does this role actually live?** Two options:
   - Per-section (this directory) — keeps everything for ND in one place,
     but breaks the standard Ansible Collection layout.
   - Top-level `roles/nd_cluster/` — Collection-idiomatic, but splits
     ND artifacts across two trees.
2. **Phase 2 timing.** Is this work scheduled for the next CVD revision,
   or deferred until the Python automation has matured for all sections?
3. **MCP timeline.** Does the team want an MCP server in v2 of the
   collection, or v3? The argument_specs.yml shape already supports it.
4. **Vault backend.** Phase 1 uses env vars + macOS Keychain in the lab.
   Phase 2 should pick one of: Ansible Vault, HashiCorp Vault, sops,
   AWS Secrets Manager. Customer/partner choice or one default?

## Cross-references

- Inventory schema: `../../../../schemas/nd-cluster.schema.json`
- MOP (procedures this role drives): `../../../docs/MOP-ND4-install.md`
- Phase 1 Python: `../scripts/`
