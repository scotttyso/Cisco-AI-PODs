# AI POD orchestration playbooks (Tier 3–4)

Cross-subsystem Ansible entrypoints. **Subsystem playbooks (Tier 2)** and
**roles (Tier 1)** stay under each `<NN>-<subsystem>/automation/` directory.

## Four-tier model

| Tier | What | Where | Customer entry? |
|---|---|---|---|
| **4** | Solution — entire AI POD | `deploy_aipod.yml` | Yes |
| **3** | Domain — one of five program domains | `domains/*.yml` | Yes |
| **2** | Subsystem — one deployable unit (01–09) | `<NN>-*/automation/playbooks/` | Yes |
| **1** | Role — product implementation | `<NN>-*/automation/roles/` | No (implementation detail) |

**Five domains** (locked with slide 1 / subsystem table):

| Domain | Tier 3 playbook | Subsystems (Tier 2, deployment order) |
|---|---|---|
| Network | `domains/network.yml` | 01 `nd-cluster` → 02 `backend-fabric-nxos` → 03 `frontend-fabric-nxos` |
| Storage | `domains/storage.yml` | 04 `storage-everpure` |
| Compute | `domains/compute.yml` | 05 `mgmt-nodes-ucs` → 06 `workload-nodes-ucs` |
| Platform | `domains/platform.yml` | 07 `openshift-cluster` → 08 `mlops` |
| AI Workload | `domains/ai_workload.yml` | 09 `ai-workloads` |

`deploy_aipod.yml` imports the five domain playbooks in the order above.

> **Note (2026-07-13):** Earlier drafts used a three-tier model (solution =
> Tier 3, subsystem = Tier 2). Domains are now an explicit orchestration
> layer; solution promoted to **Tier 4**.

## Status

| Playbook | Status |
|---|---|
| `deploy_aipod.yml` | Wired — imports all five domain playbooks in order |
| `domains/network.yml` | Wired — imports Tier 2 playbooks 01 → 02 → 03 |
| `domains/storage.yml` | Wired — imports Tier 2 playbook 04 (skeleton) |
| `domains/compute.yml` | Wired — imports Tier 2 playbooks 05 → 06 (skeleton) |
| `domains/platform.yml` | Wired — imports Tier 2 playbooks 07 → 08 (skeleton) |
| `domains/ai_workload.yml` | Wired — imports Tier 2 playbook 09 (skeleton) |
| `01_nd_cluster.yml` | Skeleton — Phases A–C via Python wedge; D/E placeholders |
| `02_backend_fabric.yml` … `09_ai_workloads.yml` | Skeleton — hierarchy wired; automation TBD |

## Run examples

```bash
# Whole program (when all domains are implemented)
ansible-playbook playbooks/deploy_aipod.yml

# One domain
ansible-playbook playbooks/domains/network.yml

# One subsystem (typical today)
ansible-playbook 01-nd-cluster/automation/playbooks/01_nd_cluster.yml
```
