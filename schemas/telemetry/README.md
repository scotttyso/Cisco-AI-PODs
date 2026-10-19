# Telemetry schemas

This directory holds **telemetry** schemas, which are a different family from the inventory
schemas one level up. The two are easy to confuse because they share a parent directory, so
the distinction is written down here rather than left to be inferred.

| | Inventory — `schemas/*.schema.json` | Telemetry — `schemas/telemetry/*.telemetry.schema.json` |
|---|---|---|
| Describes | What the POD **is** — desired state, config, inventory | What a run **emitted** — results, component status, logs |
| Composed by | `aipod.schema.json`, which `$ref`s all nine subsystem schemas | nothing; each stands alone |
| Produced by | authors and inventory files | the orchestrator at the end of a run |
| Consumed by | `scripts/validate_inventory.py` | the operator-facing user interface |

**The telemetry schemas are deliberately not `$ref`d from `aipod.schema.json`.** That is not an
oversight to be tidied up. The two families version independently: an inventory change should
not force a telemetry version bump, and the reverse. Folding telemetry into the composed
inventory schema would couple them permanently.

## Convention

One telemetry schema per subsystem, named by **subsystem**, not by platform:

```
schemas/telemetry/<subsystem>.telemetry.schema.json
schemas/telemetry/_examples/<subsystem>.telemetry.example.json
```

`$id` follows the same shape: `https://cisco.com/aipod/schemas/telemetry/<subsystem>/v1`.

`run-status.schema.json` is the one exception: run lifecycle state has the same shape for every
subsystem, so there is a single shared schema rather than one per subsystem. Subsystems 01, 02,
and 06 use it unchanged. Lifecycle fields and exit mapping must not fork between producers.

Naming by subsystem rather than platform matters because a subsystem can hold more than one
platform. Subsystem 06's schema currently describes C880A M8 upgrades and would extend to
cover another UCS workload platform without needing a second file or a rename.

Every schema sets `additionalProperties: false`. A new optional field keeps older payloads
valid against the updated schema, but it can still break an older consumer that rejects unknown
fields. Coordinate schema and consumer updates, or publish a new `$id`/schema version when the
change cannot be safely deployed to all consumers together. Consumers must validate against the
schema version they explicitly support; do not assume strict v1 consumers accept later v1 fields.

Each schema ships with a sanitized example and a test validating one against the other, so the
two cannot drift. Examples must carry no real lab addressing and no machine-specific absolute
paths; the subsystem 06 example uses a neutral `/opt/aipod/...` prefix.

## Current producers

| Subsystem | Schema | Example | Producer |
|---|---|---|---|
| 01 — ND cluster | `nd-cluster.telemetry.schema.json` | `_examples/nd-cluster.telemetry.example.json` | `01-nd-cluster/automation/scripts/main.py` |
| 02 — backend fabric | `backend-fabric-nxos.telemetry.schema.json` | `_examples/backend-fabric-nxos.telemetry.example.json` | `02-backend-fabric-nxos/automation/scripts/sg2_nd_paired_upgrade.py` |
| 06 — UCS workload nodes | `workload-nodes-ucs.telemetry.schema.json` | `_examples/workload-nodes-ucs.telemetry.example.json` | `06-workload-nodes-ucs/automation/scripts/c880_upgrade_orchestrator.py` |

The shared lifecycle and FE consumer contract are documented in
`docs/orchestrator-telemetry-contract.md`. UI implementations should consume the committed
examples and their schemas, not parse Python output or infer status from log text. Each producer
also supports an offline telemetry-only path that makes no network calls and reads no credentials.
