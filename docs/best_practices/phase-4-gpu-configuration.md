# Phase 4B: GPU Runtime Configuration and Performance Validation

## Executive Summary

Phase 4B applies runtime-level GPU controls and validation for Cisco AI PODs. Training profiles target B300 and H200 nodes for sustained throughput. Inference profiles target RTX6000 and RTX4500 nodes for low-latency, stable serving.

## Table of Contents
- [1. Hardware Roles and Runtime Targets](#1-hardware-roles-and-runtime-targets)
- [2. Persistence and Fabric Services](#2-persistence-and-fabric-services)
- [3. Clock and Power Policy Guidance](#3-clock-and-power-policy-guidance)
- [4. Topology and Fabric Validation](#4-topology-and-fabric-validation)
- [5. GPUDirect RDMA Validation](#5-gpudirect-rdma-validation)
- [6. Performance Testing Runbook (OpenShift Manifests and Commands)](#6-performance-testing-runbook-openshift-manifests-and-commands)
- [7. Thermal and Power Monitoring](#7-thermal-and-power-monitoring)
- [8. Troubleshooting Guide](#8-troubleshooting-guide)
- [9. Phase Completion Checklist](#9-phase-completion-checklist)
- [Summary](#summary)

## 1. Hardware Roles and Runtime Targets

| Node Class | GPU Type | Primary Objective | Runtime Priority |
|---|---|---|---|
| Training | B300 | Maximum distributed training throughput | Stable clocks, fabric health, RDMA path |
| Training | H200 | High-memory training and fine-tuning | NVLink integrity, RDMA consistency |
| Inference | RTX6000 | High-throughput model serving | Latency stability, thermal consistency |
| Inference | RTX4500 | Cost-efficient serving tiers | Predictable p95 latency |

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 2. Persistence and Fabric Services

On training-capable systems, keep GPU runtime services persistent and verify fabric bring-up before benchmarks.

### Enable Services

```bash
systemctl enable --now nvidia-persistenced
systemctl enable --now nvidia-fabricmanager
```

### Verify

```bash
nvidia-smi -q | grep -i "Persistence Mode"
systemctl status nvidia-fabricmanager --no-pager
```

Expected outcome:
- Persistence mode enabled.
- Fabric Manager active on systems requiring NVSwitch/NVLink fabric control.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 3. Clock and Power Policy Guidance

### Training (B300/H200)

- Lock clocks only after thermal baseline is established.
- Use validated clock ranges from platform qualification.
- Favor consistency over absolute peak values.

Example flow:

```bash
nvidia-smi -q -d SUPPORTED_CLOCKS | head -n 20
# Apply validated values from your qualification sheet
nvidia-smi --lock-gpu-clocks=<min>,<max>
```

### Inference (RTX6000/RTX4500)

- Tune for latency stability, not max sustained power.
- Keep power policy and fan behavior consistent across inference pools.
- Validate p95/p99 latency under realistic concurrency.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 4. Topology and Fabric Validation

Validate that intended high-speed paths are active and no traffic falls back to slower paths.

### Commands

```bash
nvidia-smi topo -m
nvidia-smi nvlink -s
```

### Acceptance Guidance

- Training nodes (B300/H200): expected NVLink connectivity visible and consistent.
- Any unexpected SYS/PXB path in critical pairs should be investigated before production.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 5. GPUDirect RDMA Validation

For multi-node training, verify direct GPU-memory data movement with RDMA enabled.

### Module Check

```bash
modprobe nvidia_peermem
lsmod | grep nvidia_peermem
```

### NCCL Baseline Example

```bash
./all_reduce_perf -b 8 -e 8G -f 2 -g 8
```

Validation goals:
- Throughput aligns with known-good baseline for cluster size.
- Transport logs indicate direct path usage (GDR where applicable).

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 6. Performance Testing Runbook (OpenShift Manifests and Commands)

Use this workflow to validate end-to-end GPU communication and baseline all-reduce performance on training pools (B300/H200).

### 6.1 Pre-Flight Checks

Run these checks before launching test workloads:

```bash
# Confirm worker GPU labels
oc get nodes -L nvidia.com/gpu.product

# Confirm allocatable GPUs are visible
oc describe nodes | grep -A8 "Allocatable" | grep nvidia.com/gpu

# Confirm GPU and network operators are healthy
oc -n nvidia-gpu-operator get pods
oc -n nvidia-network-operator get pods

# Optional: quick RDMA visibility check on a worker
oc debug node/<worker-node-name> -- chroot /host rdma link show
```

### 6.2 Apply Test Manifest

Create a file named `nccl-allreduce-job.yaml` and apply it as-is, then adjust node selectors and image tag for your environment.

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: gpu-perf-tests
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: nccl-hostfile
  namespace: gpu-perf-tests
data:
  hostfile: |
    worker-01 slots=8
    worker-02 slots=8
    worker-03 slots=8
    worker-04 slots=8
---
apiVersion: batch/v1
kind: Job
metadata:
  name: nccl-allreduce
  namespace: gpu-perf-tests
spec:
  parallelism: 4
  completions: 4
  backoffLimit: 1
  template:
    metadata:
      labels:
        app: nccl-allreduce
    spec:
      restartPolicy: Never
      nodeSelector:
        node-role.kubernetes.io/worker: ""
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchLabels:
                app: nccl-allreduce
            topologyKey: kubernetes.io/hostname
      containers:
      - name: nccl
        image: nvcr.io/nvidia/pytorch:24.03-py3
        imagePullPolicy: IfNotPresent
        securityContext:
          privileged: true
        resources:
          requests:
            nvidia.com/gpu: 8
            cpu: "24"
            memory: 64Gi
          limits:
            nvidia.com/gpu: 8
            cpu: "24"
            memory: 64Gi
        env:
        - name: NCCL_DEBUG
          value: INFO
        - name: NCCL_IB_DISABLE
          value: "0"
        - name: NCCL_IB_GID_INDEX
          value: "3"
        - name: NCCL_ALGO
          value: Ring
        - name: NCCL_PROTO
          value: Simple
        - name: NCCL_SOCKET_IFNAME
          value: eth0
        command:
        - /bin/bash
        - -lc
        - |
          set -euo pipefail
          echo "=== GPU Inventory ==="
          nvidia-smi
          echo "=== NCCL Test ==="
          /opt/pytorch/nccl-tests/build/all_reduce_perf \
            -b 8M -e 2G -f 2 -g 1 -c 10 -w 50
```

Deploy:

```bash
oc apply -f nccl-allreduce-job.yaml
oc -n gpu-perf-tests get pods -w
```

### 6.3 Monitor and Collect Results

```bash
# View job status
oc -n gpu-perf-tests get job nccl-allreduce

# Confirm pod placement
oc -n gpu-perf-tests get pods -o wide

# Stream one pod log
oc -n gpu-perf-tests logs -f <pod-name>

# Collect all logs for comparison
for p in $(oc -n gpu-perf-tests get pods -o name); do
  oc -n gpu-perf-tests logs "$p" > "${p##*/}.log"
done
```

### 6.4 Parse Bus Bandwidth Quickly

```bash
# Print rows with bus bandwidth from each log
grep -h "float" ./*.log | awk '{print $1, $NF}' | head -30

# Show top bandwidth values seen
grep -h "float" ./*.log | awk '{print $NF}' | sort -nr | head -10
```

### 6.5 Acceptance Criteria

- All pods schedule on distinct worker nodes.
- No NCCL timeout or CUDA errors in logs.
- Bandwidth is stable across repeated runs.
- Throughput is within expected range for your backend fabric and cluster size.
- Results are captured as baseline artifacts for future regression checks.

### 6.6 Cleanup

```bash
oc -n gpu-perf-tests delete job nccl-allreduce
oc delete namespace gpu-perf-tests
```

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 7. Thermal and Power Monitoring

Continuous monitoring is mandatory to avoid hidden throttling.

### Telemetry Command

```bash
nvidia-smi --query-gpu=temperature.gpu,power.draw,clocks.current.graphics,clocks_throttle_reasons.active --format=csv -l 1
```

### Best Practices

- Track sustained temperature and throttle flags during representative workloads.
- Keep role-specific thermal thresholds documented:
  - Training pools (B300/H200)
  - Inference pools (RTX6000/RTX4500)
- Align Intersight thermal policies with rack power and cooling design.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 8. Troubleshooting Guide

### 8.1 Fabric Manager Not Active

- Symptoms:
  - Incomplete topology visibility.
  - Unexpected low inter-GPU bandwidth.
- Actions:
  1. Verify service state and startup logs.
  2. Validate driver and fabric-manager package compatibility.
  3. Re-test topology and NCCL baseline.

### 8.2 RDMA Underperforming

- Symptoms:
  - All-reduce throughput lower than baseline.
  - High host CPU usage during collectives.
- Actions:
  1. Confirm nvidia_peermem is loaded.
  2. Validate NIC and GPU firmware/driver parity.
  3. Check RoCE policy, MTU consistency, and queue settings.

### 8.3 Thermal Throttling Under Load

- Symptoms:
  - Clock drops during sustained runs.
  - Throughput degrades over time.
- Actions:
  1. Inspect throttle reasons and fan policy.
  2. Validate chassis airflow and blanking panel placement.
  3. Reduce clock lock targets until stability is restored.

### 8.4 Inference Tail Latency Spikes (RTX6000/RTX4500)

- Symptoms:
  - p95/p99 latency outliers at steady RPS.
- Actions:
  1. Correlate GPU clocks and power draw with latency timeline.
  2. Validate CPU pinning and NIC IRQ placement for serving process.
  3. Check model cache and storage burst contention.

## 9. Phase Completion Checklist

- [ ] GPU services active and persistent across reboot.
- [ ] Topology and fabric checks pass for each node class.
- [ ] RDMA baseline validated on training pools.
- [ ] Thermal and power baselines captured.
- [ ] Inference latency SLOs validated for RTX6000 and RTX4500 pools.
- [ ] Runbooks published for top failure modes.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## Summary

Phase 4B is complete when GPU runtime behavior is stable, measurable, and role-appropriate. B300/H200 training nodes and RTX6000/RTX4500 inference nodes should each have dedicated baselines and incident playbooks before production workload onboarding.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

#### [<ins>Next Step - `Phase 5: Storage Provisioning and Data Pipeline Readiness`</ins>](phase-5-storage-provisioning.md)

#### [<ins>Back to `Best Practices` README</ins>](README.md)

#### [<ins>Back to `Repository` README</ins>](../../README.md)
