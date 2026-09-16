# Phase 6: Orchestration and Workload Operations

## Executive Summary

Phase 6 operationalizes OpenShift on Cisco AI PODs for production AI workloads. This phase standardizes operator deployment, scheduling policy, and benchmark validation so B300/H200 training pools and RTX6000/RTX4500 inference pools run predictably under multi-tenant conditions.

## Table of Contents
- [1. Installation Strategy: IPI vs UPI](#1-installation-strategy-ipi-vs-upi)
- [2. Operator Stack and Validation Order](#2-operator-stack-and-validation-order)
- [3. Workload Segmentation by GPU Class](#3-workload-segmentation-by-gpu-class)
- [4. Resource Governance](#4-resource-governance)
- [5. NCCL and Data Path Validation](#5-nccl-and-data-path-validation)
- [6. Inference Workload Validation](#6-inference-workload-validation)
- [7. Troubleshooting Guide](#7-troubleshooting-guide)
- [8. Phase Completion Checklist](#8-phase-completion-checklist)
- [Summary](#summary)

## Platform Technologies

<p align="center">
  <a href="https://www.openshift.com/"><picture><source media="(prefers-color-scheme: dark)" srcset="../images/storage-partners/openshift.svg"><source media="(prefers-color-scheme: light)" srcset="../images/storage-partners/openshift-light.svg"><img src="../images/storage-partners/openshift-light.svg" alt="OpenShift logo" width="140"></picture></a>
</p>

## 1. Installation Strategy: IPI vs UPI

### IPI (Installer-Provisioned Infrastructure)

Best for standardized deployments where automation speed is prioritized.

### UPI (User-Provisioned Infrastructure)

Best for environments requiring strict control over VLANs, addressing, and backend fabric mapping.

### Guidance

- Use UPI when backend network and storage topology must be precisely aligned to training rails.
- Use IPI when fast repeatability and simplified lifecycle are primary goals.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 2. Operator Stack and Validation Order

Install and validate in this sequence:
1. Node Feature Discovery (NFD)
2. NVIDIA GPU Operator
3. NVIDIA Network Operator
4. NMState Operator

### Validation Checks

- GPU resources exposed on intended worker nodes.
- RDMA-capable network interfaces present and healthy.
- Driver/toolkit versions consistent across node roles.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 3. Workload Segmentation by GPU Class

Use dedicated node pools and labels for role isolation.

### Recommended Pools

- Training pool: B300 and H200
- Inference pool: RTX6000 and RTX4500

### Scheduling Guidance

- Enforce node selectors and taints per pool.
- Apply pod anti-affinity for heavy jobs.
- Use topology and NUMA-aware placement for communication-intensive workloads.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 4. Resource Governance

### Quotas and Limit Ranges

- Set namespace GPU quotas to prevent resource starvation.
- Require explicit requests and limits for GPU workloads.
- Define separate quota profiles for training and inference namespaces.

### Partitioning Guidance

- Use hardware partitioning features only where supported by the target GPU class and validated in your stack.
- For inference density objectives, combine namespace controls with replica-based autoscaling and pool-level capacity limits.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 5. NCCL and Data Path Validation

Before production rollout, baseline collective communication and data path behavior.

### Minimum Test Workflow

1. Verify operator health and GPU allocatable resources.
2. Run NCCL all-reduce tests on training pool nodes.
3. Validate RDMA path and network policy alignment.
4. Correlate benchmark output with switch and host telemetry.
5. Repeat tests after major firmware, driver, or topology changes.

### Performance Targets

- 400G backend fabrics: target sustained all-reduce bandwidth in expected platform range with stable latency.
- Results must be repeatable across multiple runs and time windows.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 6. Inference Workload Validation

For RTX6000/RTX4500 pools, measure service behavior under realistic traffic.

### Required Tests

- Cold-start and warm-start model load time.
- Steady-state throughput at target concurrency.
- p95/p99 latency under burst and sustained load.
- Rolling update behavior with no SLO breach.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 7. Troubleshooting Guide

### 7.1 GPU Resources Not Advertised

- Symptoms:
  - Pods pending with insufficient GPU errors.
- Actions:
  1. Validate GPU Operator daemonsets and device plugin state.
  2. Confirm node labels and taints are correctly applied.
  3. Verify driver and runtime compatibility per node pool.

### 7.2 NCCL Underperformance (Training Pool)

- Symptoms:
  - Low all-reduce bandwidth or high latency variability.
- Actions:
  1. Verify RDMA configuration and MTU consistency.
  2. Check topology-aware scheduling and NUMA locality.
  3. Compare benchmark outcomes to known-good baselines.

### 7.3 Inference SLO Violations (RTX6000/RTX4500)

- Symptoms:
  - p95 or p99 latency spikes during load.
- Actions:
  1. Inspect node-level contention and throttling metrics.
  2. Validate autoscaler behavior and replica warm-up.
  3. Ensure storage/model-cache path is not congested.

### 7.4 Pod Scheduling Instability

- Symptoms:
  - Frequent rescheduling or uneven placement.
- Actions:
  1. Review affinity and anti-affinity constraints.
  2. Verify taints/tolerations and pool quotas.
  3. Audit cluster autoscaler and disruption budgets.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 8. Phase Completion Checklist

- [ ] Node pools and labels documented and validated.
- [ ] Operator lifecycle runbook published.
- [ ] NCCL and inference benchmark baselines archived.
- [ ] Alert thresholds tuned for production traffic patterns.
- [ ] Upgrade and rollback procedures tested.

## Summary

Phase 6 is complete when orchestration policy, benchmark validation, and incident runbooks are production-ready. At this point, Cisco AI PODs can safely host mixed training and inference workloads with predictable performance and governance.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

#### [<ins>Back to `Best Practices` README</ins>](README.md)

#### [<ins>Back to `Repository` README</ins>](../../README.md)
