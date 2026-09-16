# Phase 1: Planning and Design - Cisco AI PODs

## Executive Summary

Day-2 planning at Day-0 is the single biggest gap we see in pilots. Successful Cisco AI PODs deployments require comprehensive planning across workload characterization, infrastructure design, networking architecture, storage strategy, and operational readiness. This phase establishes the foundation for predictable, scalable, and maintainable AI infrastructure.

## Table of Contents
- [1. Workload Characterization and Sizing](#1-workload-characterization-and-sizing)
- [2. GPU Interconnect Topology Design](#2-gpu-interconnect-topology-design)
- [3. Network Architecture Planning](#3-network-architecture-planning)
- [4. Storage Strategy and Validation](#4-storage-strategy-and-validation)
- [5. Day-2 Operations Planning](#5-day-2-operations-planning)
- [6. Risk Assessment and Mitigation](#6-risk-assessment-and-mitigation)
- [Summary and Next Steps](#summary-and-next-steps)

---

## 1. Workload Characterization and Sizing

### 1.1 Using the UCS AI Sizer Tool

The **UCS AI Sizer Tool** is a critical resource for accurate capacity planning and should be your starting point for any Cisco AI PODs project.

**Tool Access:**
- Web Tool: [https://ucsszr.cloudapps.cisco.com/ucsappsizer/](https://ucsszr.cloudapps.cisco.com/ucsappsizer/project/all)
- Used by Cisco sales engineers to validate designs and generate bill-of-materials (BOMs)
- Provides project customization and exports for procurement and planning

**Using the UCS AI Sizer:**

1. **Create a New Project:**
   - Navigate to the sizer tool and create a new project
  - Input project name, workload type (Training / Inference / Mixed), and target performance metrics
   - Specify geographic region and timeline for procurement

2. **Define Your Workload:**
   - Model type and framework (PyTorch, TensorFlow, JAX, etc.)
   - Model size (parameters) and precision (FP32, BF16, FP8)
   - Batch size per GPU and number of concurrent users/jobs
   - Training duration or inference throughput SLA
   - Data volume and preprocessing requirements

3. **Select Scale Unit:**
   - **SU1:** 32 GPUs (4 × UCS C885A-M8 servers with 8 GPUs each)
   - **SU2:** 64 GPUs (8 × UCS C885A-M8 servers)
   - **SU3:** 128 GPUs (16 × UCS C885A-M8 servers)
    - Can mix GPU types (B300, H200, RTX6000, RTX4500, etc.)

4. **Review Recommendations:**
   - Compute capacity (GPU count, server configuration)
   - Network fabric specifications (leaf/spine switches, port speeds)
   - Storage capacity and throughput requirements
   - Power and cooling estimates
   - Software components (drivers, CUDA, frameworks)

5. **Export Results:**
   - Generate detailed bill-of-materials (BOM)
   - Technical specifications document
   - Network topology diagram
   - Share with procurement and infrastructure teams

### 1.2 Model Size and Memory Calculations

**Memory Requirement Formula:**
```
Total VRAM per GPU = (Model Size) + (Activation Memory) + (Optimizer State) + (Batch Data)

Model Size = Parameters × Precision Bytes
  - FP32 (full precision): 4 bytes per parameter
  - BF16 (mixed precision): 2 bytes per parameter
  - FP8 (quantized): 1 byte per parameter

Activation Memory ≈ Model Size × Activation Factor (typically 2-4× model size for transformer models)

Optimizer State (Adam) ≈ 2-3× Model Size (maintains momentum and variance)
```

**Example: 70B Parameter Model Deployment**

| Precision | Model Size | Activation Mem | Optimizer | Per-GPU Total | Suitable GPU |
|-----------|-----------|----------------|-----------|--------------|-------------|
| FP32 | 280 GB | 560 GB | 840 GB | 1.68 TB | Not feasible on single B300 (288GB) or H200 (141GB) |
| BF16 | 140 GB | 280 GB | 420 GB | 840 GB | Not feasible on single B300 (288GB) or H200 (141GB) |
| BF16 + LoRA | 140 GB | 140 GB | 50 GB | 330 GB | Distributed across 2×B300 or 3×H200 |
| FP8 Quant | 70 GB | 140 GB | 0 GB (inference) | 210 GB | Feasible on 1×B300 or 2×H200 |

**Recommendations:**
- For training: plan 1.5-2× model size in GPU memory headroom
- For inference: use quantization (FP8/INT8) to reduce memory footprint by 75%
- Use vLLM or TensorRT-LLM for inference optimization
- Consider batch sizes: start conservative (batch_size=1 per GPU), increase after validation

### 1.3 Data Pipeline Characterization

**Throughput Requirements:**
```
Required Storage Throughput = (GPU Count) × (Tokens/sec/GPU) × (Bytes per Token)

Example: 32 GPUs processing 4000 tokens/sec/GPU with 2 bytes/token overhead
  = 32 × 4000 × 2 = 256 Gbps storage throughput needed
```

**Data Collection Worksheet:**
- Model parameters (billions)
- Training dataset size (TB/GB)
- Inference requests per second
- Concurrent users/sessions
- Data preprocessing pipeline latency (target: <10ms)
- Cache strategy (hot data, working set size)
- Data format (NFS, S3, parquet, pickle, etc.)

### 1.4 Scale Unit Matching

| Use Case | Recommended SU | GPU Config | Training Duration | Notes |
|----------|---|---|---|---|
| Development/Testing | SU1 | 32× H200 or 16× B300 | < 1 week | Quick iteration, fast prototyping |
| Fine-tuning | SU1-SU2 | 32-64× H200 or 16-32× B300 | 1-4 weeks | Moderate scale, cost-effective |
| Large-scale Training | SU2-SU3 | 64-128× H200 or 32-64× B300 | 2-12 weeks | Production workloads |
| Inference | SU1 | 32× RTX6000 or 32× RTX4500 | Continuous | Cost-efficient, lower latency needs |
| Mixed (Train + Infer) | SU2 | 32× H200 or 16× B300 + 32× RTX6000/RTX4500 | Varies | Separate fabrics recommended |

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)


---

## 2. GPU Interconnect Topology Design

### 2.1 Training vs. Inference Topology

**Training Topology (Backend Fabric Critical):**
- High-speed, low-latency GPU-to-GPU communication via backend fabric
- Distributed data parallelism, gradient synchronization every iteration
- All-reduce operation bandwidth: critical bottleneck (target >45 GB/s per rail for 400Gbps fabric)
- Typical all-reduce latency target: <100 microseconds
- Recommendation: Dedicated 400G backend leaf-spine with low-latency switches

**Inference Topology (Frontend Only):**
- Front-end network carries inference requests and responses
- Inter-GPU communication minimal (token batching may require it)
- Higher oversubscription acceptable (8:1 or 10:1)
- Recommendation: Standard 100G leaf-spine sufficient; add 400G for batch serving

### 2.2 Cisco Recommended Fabric Architecture

**Backend Fabric (GPU-to-GPU Communication):**
- **Leaf Switches:** Cisco Nexus 9332D-GX2B (32× 400G ports)
- **Spine Switches:** Cisco Nexus 9364D-GX2A (64× 400G ports)
- **Topology:** Full-mesh leaf-spine (every leaf connected to every spine)
- **Oversubscription:** 1:1 or 1.2:1 (fully non-blocking or near non-blocking)
- **Cabling:** 400G QSFP-DD optics, multimode fiber or direct-attach copper (DAC)
- **Buffer Strategy:** Deep buffers (28 MB+ per switch) for bursty communication patterns

**Frontend Fabric (Data and Management):**
- **Leaf Switches:** Cisco Nexus 9364C-GX (36× 100G ports)
- **Spine Switches:** Cisco Nexus 9508 (up to 128× 100G ports)
- **Topology:** Leaf-spine with 3:1 to 8:1 oversubscription (acceptable for serial data pipeline)
- **VLANs:** Separate for management, storage, inference, and shared services

### 2.3 Server-to-Network Connectivity

**For 8-GPU servers (B300 or H200 configurations):**
- **Port Layout:** 4× OSFP (Open Standard Form Factor) ports for backend
- **Typical Config:** All 4 ports bonded (400G each) for 1.6 Tbps aggregate backend bandwidth
- **Frontend:** 2× 100G ports for management and storage access
- **Recommended:** Dedicated NIC per fabric (backend NIC separate from frontend)

**Bond Configuration Example:**
```
Backend Interface (LACP bond):
  - 4× 400G ports → 1.6 Tbps total bandwidth
  - Reduce overhead to 400G per link for redundancy
  
Frontend Interface (Active-Backup):
  - 2× 100G ports → 100 Gbps active, 100 Gbps standby
  - Supports storage replication and management traffic
```

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)


---

## 3. Network Architecture Planning

### 3.1 VLAN and Routing Design

**Recommended VLAN Layout:**

| VLAN | Purpose | Subnet | Switch | Notes |
|------|---------|--------|--------|-------|
| 10 | Management | 10.0.0.0/24 | Frontend | BMC, Intersight, monitoring |
| 20 | Storage | 10.0.20.0/24 | Frontend | NFS, iSCSI, S3 (isolated for throughput) |
| 30 | Kubernetes Pod Network | 172.16.0.0/12 | Frontend | OpenShift pods, services (overlay or L3) |
| 100-110 | Backend Fabric | Point-to-point (no VLAN) | Backend | Direct GPU-to-GPU communication (routed) |

### 3.2 RoCE (RDMA over Converged Ethernet) Configuration

**For 400G Backend Fabric:**
```
Priority Flow Control (PFC):
  - Enable on CoS 3 (dedicated to RDMA)
  - Prevent packet drops on RDMA flows
  
Explicit Congestion Notification (ECN):
  - Enable on all buffer drops
  - Allows switches to signal congestion
  
Per-Flow Fairness:
  - Distribute bandwidth equally across flows
  - Prevent any single GPU pair from monopolizing fabric
  
Link-Level Flow Control:
  - Disable (use PFC instead)
```

### 3.3 Bandwidth Allocation Strategy

**GPU-to-GPU Allocation (Training):**
- 80% of 400G per link ≈ 320 Gbps dedicated to all-reduce
- 20% reserved for other collective operations (broadcast, scatter-gather)

**Data Pipeline (Shared Storage + Management):**
- Separate frontend VLAN to isolate storage I/O
- 100 Gbps per server for storage (12.5 Gbps per GPU)
- Allows parallel data loading while GPUs compute

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)


---

## 4. Storage Strategy and Validation

### 4.1 Storage Throughput Requirements

**Formula:**
```
Minimum Storage Bandwidth = GPU Count × 12.5 Gbps per GPU

Examples:
- 8-GPU server: 100 Gbps minimum dedicated storage bandwidth
- 32-GPU cluster (SU1): 400 Gbps minimum
- 64-GPU cluster (SU2): 800 Gbps minimum
```

### 4.2 Recommended Storage Solutions

**Cisco AI PODs Validated Storage Partners:**

| Partner | Solution | Best For | Throughput | Notes |
|---------|----------|----------|-----------|-------|
| EverPure (Pure Storage) | FlashArray//X | Training data archive | 10+ GB/s | All-flash, low latency, snapshot-friendly |
| NetApp | AFF A900 + FlexGroup | Scale-out NAS | 20+ GB/s | Dynamic filesystem expansion, cloud-ready |
| VAST Data | VAST Platform | Big data, unstructured | 30+ GB/s | Object + POSIX interface, cost-effective |
| Qumulo | Qumulo File System | Real-time analytics | 15+ GB/s | Kubernetes-native, multi-cloud capable |

### 4.3 Storage Technologies to Enable

**NFS over RDMA:**
- Reduce latency by offloading NFS protocol to NICs
- Direct RDMA reads/writes from GPU to storage
- Supported by NetApp, VAST, Qumulo
- Typical latency improvement: 50-70% reduction

**NVIDIA GPUDirect Storage:**
- Direct GPU-to-NVMe path (bypass CPU/RAM)
- Kernel bypass for maximum performance
- Requires CUDA 11.2+ and compatible storage driver
- Measurable improvement for sequential I/O workloads

**S3 Object Storage Integration:**
- Distributed training datasets in S3-compatible buckets
- Scale beyond single filesystem limits
- Use huggingface datasets, DVC, or S3 fuse mounts
- Throughput depends on object size and parallel requests

### 4.4 Capacity Planning

```
Minimum Capacity = (Dataset Size) × (Replication Factor) + (Snapshots/Backups)

Example: 10 TB dataset with 3× replication and 30% snapshot overhead
  = (10 TB × 3) + (10 TB × 3 × 0.30) = 39 TB minimum

Growth Buffer: Add 20-30% for future workloads and intermediate results
```

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)


---

## 5. Day-2 Operations Planning

### 5.1 Monitoring and Observability Strategy

**Key Metrics to Track:**

**Compute Metrics:**
- GPU utilization (target: >95% during training)
- GPU memory pressure (avoid >90% sustained usage)
- NUMA memory bandwidth saturation
- CPU-GPU PCIe bandwidth efficiency

**Network Metrics:**
- All-reduce latency and bandwidth (benchmark: 45+ GB/s for 400Gbps)
- RDMA packet loss (target: <1 per million packets)
- Fabric congestion events (PFC pause frames)
- Link-level errors (CRC, FCS)

**Storage Metrics:**
- Data pipeline throughput (target: >12.5 Gbps per GPU)
- I/O latency percentiles (p50, p95, p99)
- Cache hit rates (for frequently accessed datasets)
- Replication and snapshot backup success

**Framework-Level Metrics:**
- Training loss convergence
- Gradient synchronization time (all-reduce barrier)
- Data loading batch preparation time
- Model checkpoint save/restore duration

**Tools:**
- Cisco Intersight for hardware monitoring and lifecycle management
- Cisco Nexus Dashboard for network fabric observability
- Prometheus + Grafana for Kubernetes/application metrics
- NVIDIA DCGM for GPU-specific telemetry

### 5.2 Firmware Update Strategy

**Update Sequence (Maintenance Window Required):**

1. **Network (Minimal Impact):**
   - Update Nexus switch software in rolling fashion
   - 1 leaf at a time to maintain connectivity
   - Typical downtime: <5 minutes per leaf

2. **Storage (Graceful):**
   - For redundant storage: update one node/controller at a time
   - Rebalance data before and after each update
   - Typical downtime: 0 minutes (transparent during replication)

3. **Compute (Higher Impact):**
   - Gracefully shutdown running training jobs (save checkpoints)
   - Update server BIOS, BMC, and GPU drivers
   - Validate with burn-in test before returning to service
   - Typical downtime: 30-45 minutes per server

4. **GPU Drivers (Critical):**
   - Update CUDA and NVIDIA drivers atomically
   - Recompile NCCL tests to verify all-reduce performance
   - Typical downtime: 20-30 minutes

### 5.3 Scaling Plan

**Incremental Scaling Process:**

```
Phase 1: Deploy SU1 (32 GPUs)
  - Validate design and network baseline (all-reduce, storage throughput)
  - Identify bottlenecks and optimization opportunities
  - Establish operational playbooks and runbooks

Phase 2: Add SU2 (64 GPUs total)
  - Mirror network topology, increase fabric capacity
  - Test distributed training across both SUs
  - Validate load balancing and fair-share policies

Phase 3: Add SU3 (128 GPUs total)
  - Full 3-level fabric topology
  - Multi-cluster orchestration via Kubernetes federation
  - Implement cross-SU job scheduling policies
```

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)


---

## 6. Risk Assessment and Mitigation

### 6.1 Common Planning Pitfalls

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Underestimating storage bandwidth | Training blocked on I/O waits | Use UCS Sizer to validate data pipeline; run data load tests during POC |
| Undersizing backend fabric | All-reduce bottleneck, poor scaling efficiency | Target 400G full mesh with <1.2:1 oversubscription |
| Mixed GPU models in cluster | Uneven training speed, load balancing challenges | Standardize on single GPU type per cluster; use UCS Sizer for final config |
| Insufficient monitoring infrastructure | Difficult troubleshooting during production | Deploy monitoring tools before production workloads |
| Deferred Day-2 planning | Operational surprises, uncontrolled scaling | Plan firmware, scaling, and failover strategies before pilot completes |
| Inadequate power/cooling capacity | Hardware failures, unplanned downtime | Include power budget (+20% headroom) and cooling assessment from Day 1 |

### 6.2 Validation Checklist

Before moving to production, complete these validation steps:

**Infrastructure Validation:**
- [ ] All-reduce benchmark shows 45+ GB/s on backend fabric
- [ ] Storage throughput meets minimum 12.5 Gbps per GPU requirement
- [ ] GPU-to-storage latency <10ms (p95)
- [ ] Firmware versions consistent across all servers and switches
- [ ] RDMA configuration validated (ibv_devinfo, perftest)

**Operational Readiness:**
- [ ] Monitoring and alerting configured and tested
- [ ] Backup and recovery procedures documented and tested
- [ ] Firmware update runbooks created and tested on non-production systems
- [ ] Scaling procedures planned and validated
- [ ] On-call support structure defined

**Workload Validation:**
- [ ] Model training runs successfully across all GPUs
- [ ] All-reduce completion time <100 microseconds per iteration
- [ ] Data pipeline achieves target throughput with realistic batch sizes
- [ ] Model checkpointing and recovery procedures tested

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)


---

## Summary and Next Steps

Phase 1 planning establishes the foundation for a successful Cisco AI PODs deployment. Use the UCS AI Sizer tool early and often to validate infrastructure decisions. Engage Cisco sales engineers and your storage partner during design reviews to identify potential bottlenecks. Plan for Day-2 operations simultaneously with infrastructure design to ensure operational maturity from day one.

**Key Takeaways:**
1. **Use UCS AI Sizer** as your primary planning tool
2. **Validate all-reduce performance** before production workloads
3. **Match storage throughput** to GPU count and data pipeline requirements
4. **Plan Day-2 operations** during design phase
5. **Build in 20-30% headroom** for unexpected growth and optimization

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

#### [<ins>Next Step - `Phase 2: Hardware Staging and Day-0 Readiness`</ins>](phase-2-hardware-staging.md)

#### [<ins>Back to `Best Practices` README</ins>](README.md)

#### [<ins>Back to `Repository` README</ins>](../../README.md)
