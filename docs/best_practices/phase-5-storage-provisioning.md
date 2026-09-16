# Phase 5: Storage Provisioning and Data Pipeline Readiness

## Executive Summary

Phase 5 establishes the storage architecture required to keep Cisco AI PODs compute resources fully utilized. The design must sustain high parallel throughput for B300 and H200 training clusters while also delivering low-latency model access for RTX6000 and RTX4500 inference pools.

## Table of Contents
- [1. Scale-Out Namespace and Access Model](#1-scale-out-namespace-and-access-model)
- [2. Pipeline-Aware Tiering Strategy](#2-pipeline-aware-tiering-strategy)
- [3. High-Throughput Data Path Design](#3-high-throughput-data-path-design)
- [4. Data Protection and Checkpoint Resilience](#4-data-protection-and-checkpoint-resilience)
- [5. Provisioning Workflow and Validation](#5-provisioning-workflow-and-validation)
- [6. Troubleshooting Guide](#6-troubleshooting-guide)
- [7. Phase Completion Checklist](#7-phase-completion-checklist)
- [Summary](#summary)

## Storage Partners

<p align="center">
  <a href="https://www.purestorage.com/"><picture><source media="(prefers-color-scheme: dark)" srcset="../images/storage-partners/everpure.svg"><source media="(prefers-color-scheme: light)" srcset="../images/storage-partners/everpure-light.svg"><img src="../images/storage-partners/everpure-light.svg" alt="EverPure logo" width="140"></picture></a>&emsp;&emsp;
  <a href="https://www.hitachivantara.com/"><picture><source media="(prefers-color-scheme: dark)" srcset="../images/storage-partners/hitachivantara.svg"><source media="(prefers-color-scheme: light)" srcset="../images/storage-partners/hitachivantara-light.svg"><img src="../images/storage-partners/hitachivantara-light.svg" alt="Hitachi Vantara logo" width="140"></picture></a>&emsp;&emsp;
  <a href="https://www.netapp.com/"><picture><source media="(prefers-color-scheme: dark)" srcset="../images/storage-partners/netapp.svg"><source media="(prefers-color-scheme: light)" srcset="../images/storage-partners/netapp-light.svg"><img src="../images/storage-partners/netapp-light.svg" alt="NetApp logo" width="180"></picture></a>&emsp;&emsp;
  <a href="https://www.qumulo.com/"><picture><source media="(prefers-color-scheme: dark)" srcset="../images/storage-partners/qumulo.svg"><source media="(prefers-color-scheme: light)" srcset="../images/storage-partners/qumulo-light.svg"><img src="../images/storage-partners/qumulo-light.svg" alt="Qumulo logo" width="170"></picture></a>&emsp;&emsp;
  <a href="https://www.vastdata.com/"><picture><source media="(prefers-color-scheme: dark)" srcset="../images/storage-partners/vastdata.svg"><source media="(prefers-color-scheme: light)" srcset="../images/storage-partners/vastdata-light.svg"><img src="../images/storage-partners/vastdata-light.svg" alt="VAST Data logo" width="140"></picture></a>
</p>

## 1. Scale-Out Namespace and Access Model

Use a single global namespace for training and shared artifact access.

### Best Practices

1. Present one logical namespace across storage nodes to eliminate data silos.
2. Distribute data and metadata paths to avoid hot spots.
3. Keep metadata-intensive workloads on all-flash tiers.
4. Separate admin/control operations from bulk data paths.

### Operational Guidance

- For B300/H200 training pools, prioritize wide parallel reads and checkpoint write throughput.
- For RTX6000/RTX4500 inference pools, prioritize model load latency and predictable cache behavior.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 2. Pipeline-Aware Tiering Strategy

Map storage tiers to AI lifecycle stages to minimize cost while preserving performance where needed.

### Recommended Tier Mapping

- Ingest and raw repositories: object storage tier.
- Active training datasets: high-performance file tier.
- Checkpoints and intermediate artifacts: high-throughput file tier with snapshot policy.
- Long-term retention: object archive with lifecycle transitions.

### Policy Guidance

- Automate transitions between tiers by age, access frequency, and project labels.
- Keep model registry artifacts replicated across at least two fault domains.
- Treat training checkpoints and inference model artifacts as separate policy classes.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 3. High-Throughput Data Path Design

### Throughput Planning Formula

```text
Minimum storage bandwidth = GPU count x 12.5 Gbps
```

Example targets:
- 32 GPUs: 400 Gbps minimum
- 64 GPUs: 800 Gbps minimum

### Best Practices

1. Enable multipath and multi-stream client access where supported.
2. Use nconnect and parallel mounts for read-heavy training stages.
3. Validate RDMA/RoCE path consistency for data-intensive jobs.
4. Reserve bandwidth classes for checkpoint windows.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 4. Data Protection and Checkpoint Resilience

Long-running training jobs require rapid checkpoint protection and restore.

### Recommended Controls

- Frequent pointer-based snapshots for checkpoint paths.
- Immutable retention windows for critical model milestones.
- Replication policies tuned by workload criticality.
- Routine restore drills to validate recovery objectives.

### Capacity Formula

```text
Total checkpoint capacity = model size x checkpoint frequency x retention window
Total storage plan = checkpoint capacity + dataset footprint + 20-30% growth buffer
```

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 5. Provisioning Workflow and Validation

1. Create role-based storage classes and performance tiers.
2. Provision file and object endpoints for each workload domain.
3. Attach quotas and lifecycle policies per namespace.
4. Validate mount options from worker nodes.
5. Run synthetic throughput and latency tests.
6. Baseline real workload data ingest and checkpoint operations.

### Validation Checklist

- [ ] Namespace and access policy model approved.
- [ ] Storage classes mapped to training and inference requirements.
- [ ] Throughput baseline meets target by cluster size.
- [ ] Snapshot and restore procedures tested.
- [ ] Monitoring dashboards and alerts active.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 6. Troubleshooting Guide

### 6.1 Low Training Throughput (B300/H200)

- Symptoms:
  - GPU utilization drops while data loaders wait.
- Actions:
  1. Check aggregate read throughput per mount and per node.
  2. Validate nconnect/session trunking configuration.
  3. Verify NIC queue settings and RDMA path health.
  4. Isolate noisy neighbors with namespace-level QoS controls.

### 6.2 Slow Checkpoint Writes

- Symptoms:
  - Training step time spikes at checkpoint interval.
- Actions:
  1. Move checkpoint path to high-performance tier.
  2. Stagger checkpoint schedules across concurrent jobs.
  3. Validate snapshot backend and metadata latency.

### 6.3 Inference Model Load Latency (RTX6000/RTX4500)

- Symptoms:
  - Elevated cold-start or model swap times.
- Actions:
  1. Place model artifacts on low-latency tier.
  2. Increase cache allocation for frequently used models.
  3. Pre-warm models during deployment rollouts.

### 6.4 Capacity Forecast Drift

- Symptoms:
  - Storage expansion required earlier than planned.
- Actions:
  1. Recalculate growth from recent checkpoint retention behavior.
  2. Audit stale artifacts and orphaned run outputs.
  3. Adjust lifecycle transitions and retention periods.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 7. Phase Completion Checklist

- [ ] Storage architecture and policy documentation finalized.
- [ ] Baseline performance report archived.
- [ ] Recovery runbooks validated and published.
- [ ] Ownership and escalation model agreed with operations team.

## Summary

Phase 5 is complete when storage throughput, latency, protection, and growth controls are validated against actual workload behavior. Strong storage readiness is a prerequisite for stable orchestration and workload scaling in Phase 6.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

#### [<ins>Next Step - `Phase 6: Orchestration and Workload Operations`</ins>](phase-6-orchestration-and-workload.md)

#### [<ins>Back to `Best Practices` README</ins>](README.md)

#### [<ins>Back to `Repository` README</ins>](../../README.md)
