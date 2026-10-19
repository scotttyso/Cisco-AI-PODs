# Automation — Subsystem 07 (OpenShift cluster)

Skeleton. `playbooks/07_openshift_cluster.yml` wires this subsystem into the domain hierarchy; the automation itself is not implemented yet.

Tier 2 in the four-tier model:

| Tier | Path |
|---|---|
| 4 | `playbooks/deploy_aipod.yml` |
| 3 | `playbooks/domains/platform.yml` |
| 2 | `playbooks/07_openshift_cluster.yml` (this subsystem) |
| 1 | `roles/` — not yet scaffolded |

Scope and dependencies are described in [`../README.md`](../README.md). Inventory shape is governed by [`schemas/openshift-cluster.schema.json`](../../schemas/openshift-cluster.schema.json) (stub today).
