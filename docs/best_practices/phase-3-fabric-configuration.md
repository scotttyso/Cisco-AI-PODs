# Phase 3: Fabric Configuration and Validation

## Executive Summary

Phase 3 activates and validates frontend and backend network fabrics for Cisco AI PODs. The target state is a low-latency, low-loss backend fabric for distributed training with B300 and H200 nodes, plus a stable frontend fabric for storage, orchestration, and inference traffic serving RTX6000 and RTX4500 nodes.

## Table of Contents
- [1. Fabric Design Objectives](#1-fabric-design-objectives)
- [2. Core Configuration Standards](#2-core-configuration-standards)
- [3. Bring-Up Sequence](#3-bring-up-sequence)
- [4. Validation and Acceptance Tests](#4-validation-and-acceptance-tests)
- [5. Troubleshooting Guide](#5-troubleshooting-guide)
- [6. Phase Completion Checklist](#6-phase-completion-checklist)
- [Summary](#summary)

## 1. Fabric Design Objectives

### Backend Fabric (East-West)

- Purpose: GPU-to-GPU collectives for distributed training.
- Design target:
  - 400G or 800G links
  - Near non-blocking topology
  - RoCEv2 with deterministic QoS
- Typical workloads:
  - Multi-node B300 or H200 training jobs

### Frontend Fabric (North-South)

- Purpose: storage I/O, cluster control plane, and inference ingress.
- Design target:
  - 100G or higher uplinks
  - Segmented VLANs
  - Predictable latency for service traffic
- Typical workloads:
  - Model serving on RTX6000 and RTX4500

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 2. Core Configuration Standards

### 2.1 VLAN and Addressing Model

Use separate segments for management, storage, cluster pod/service traffic, and backend transport.

| Segment | Example Use | Notes |
|---|---|---|
| Management VLAN | BMC, switch management, tooling | Isolate admin access and enforce ACLs |
| Storage VLAN | NFS, object, block access | Keep data path separate from control path |
| Cluster VLAN(s) | Kubernetes/OpenShift nodes and services | Avoid overlap with management network |
| Backend Routed Links | Training collective traffic | Prefer routed point-to-point for scale |

### 2.2 RoCE and QoS Baseline

1. Enable PFC only on designated RDMA class.
2. Enable ECN for early congestion signaling.
3. Define dedicated QoS class maps for backend AI traffic.
4. Validate MTU consistency end-to-end.
5. Keep frontend and backend queues isolated.

### 2.3 Link and Port Policy

- Lock speed and FEC policy per port profile.
- Standardize breakout mode by rack design.
- Use consistent LLDP and interface descriptions.
- Enforce template-based switch configuration to avoid drift.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 3. Bring-Up Sequence

1. Build and validate management plane first.
2. Bring up frontend leaf-spine under baseline templates.
3. Bring up backend leaf-spine links and verify routing adjacency.
4. Apply QoS and RoCE policy.
5. Validate host-facing links from training and inference nodes.
6. Run synthetic traffic and NCCL baseline tests.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 4. Validation and Acceptance Tests

### 4.1 Network Health Validation

- [ ] All intended links up at expected speed.
- [ ] No unexpected port flaps during 24-hour soak.
- [ ] CRC/FCS counters remain stable.
- [ ] Buffer and queue utilization within thresholds.
- [ ] ECN marks visible under controlled congestion tests.

### 4.2 AI Workload Validation

- [ ] NCCL all-reduce baseline meets expected throughput for cluster size.
- [ ] Job-to-job variance remains within accepted envelope.
- [ ] Storage-to-GPU data path sustains required throughput.
- [ ] Inference nodes (RTX6000 or RTX4500) meet latency SLOs.

### 4.3 Operational Validation

- [ ] Configuration backups exported and versioned.
- [ ] Telemetry and alerting integrated with NOC workflows.
- [ ] Runbooks validated for link, leaf, and rack failure scenarios.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 5. Troubleshooting Guide

### 5.1 High All-Reduce Latency

- Probable causes:
  - PFC/ECN misconfiguration
  - Backend oversubscription or hot-spots
  - MTU mismatch on one segment
- Actions:
  1. Compare QoS and RoCE policy against known-good template.
  2. Check per-link utilization and imbalance across spine paths.
  3. Verify MTU from host NIC to leaf to spine to peer NIC.
  4. Re-run NCCL test with fixed topology and controlled job placement.

### 5.2 Packet Loss or Retransmissions

- Probable causes:
  - Bad optics or cable integrity issues
  - Incorrect FEC settings
  - Congestion collapse from improper queueing
- Actions:
  1. Isolate links with rising CRC/FCS counters.
  2. Swap optics and patch cables with known-good components.
  3. Validate FEC mode and speed profile at both ends.
  4. Confirm queue allocations and PFC class mapping.

### 5.3 Inference Latency Spikes (RTX6000/RTX4500)

- Probable causes:
  - Shared frontend congestion with storage bursts
  - Asymmetric routing or ECMP imbalance
  - Host NIC queue tuning not aligned to workload profile
- Actions:
  1. Separate inference and storage traffic classes.
  2. Audit ECMP hash and path distribution.
  3. Tune host NIC RSS/IRQ affinity and retest p95 latency.

### 5.4 Intermittent Node Reachability

- Probable causes:
  - VLAN trunk mismatch
  - Duplicate IP or ARP instability
  - ACL/policy drift between switches
- Actions:
  1. Validate trunk allowed VLAN lists and native VLAN.
  2. Check ARP tables and duplicate address detection logs.
  3. Compare active configuration against intended template.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 6. Phase Completion Checklist

- [ ] Fabric diagrams and port maps updated.
- [ ] Golden configuration templates committed.
- [ ] Baseline performance report archived.
- [ ] Incident runbooks published for top failure modes.
- [ ] Sign-off completed by compute, network, and platform owners.

## Summary

Phase 3 is complete when the fabric is not only operational but predictable under load. Enforce strict template control, validate with both synthetic and workload-driven tests, and keep troubleshooting playbooks aligned to real observed failure patterns.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

#### [<ins>Next Step - `Phase 4A: Compute Provisioning and Lifecycle Baseline`</ins>](phase-4-compute-provisioning.md)

#### [<ins>Back to `Best Practices` README</ins>](README.md)

#### [<ins>Back to `Repository` README</ins>](../../README.md)
