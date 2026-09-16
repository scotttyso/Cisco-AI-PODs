# Cisco AI PODs Best Practices Phases

This guide is the high-level entry point for the six-phase Cisco AI PODs best-practices runbook. It provides a structured progression from planning and hardware readiness to orchestration and workload operations.

Use these phases in order. Each phase builds on controls and validation steps from the previous phase.

#### [<ins>Back to `Repository` README</ins>](../../README.md)

## Table of Contents

- [Overview](#overview)
- [Phase 1: Planning and Design](#phase-1-planning-and-design)
- [Phase 2: Hardware Staging](#phase-2-hardware-staging)
- [Phase 3: Fabric Configuration](#phase-3-fabric-configuration)
- [Phase 4: Compute and GPU Configuration](#phase-4-compute-and-gpu-configuration)
- [Phase 5: Storage Provisioning](#phase-5-storage-provisioning)
- [Phase 6: Orchestration and Workload Operations](#phase-6-orchestration-and-workload-operations)
- [Suggested Execution Order](#suggested-execution-order)

## Overview

The six phases are designed to reduce deployment risk, standardize operations, and improve production readiness for mixed AI workloads.

- Training focus: B300 and H200 pools
- Inference focus: RTX6000 and RTX4500 pools
- Platform focus: Cisco Intersight, validated network fabrics, and OpenShift orchestration

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## Phase 1: Planning and Design

Defines workload sizing, architecture decisions, risk controls, and Day-2 planning.

- Document: [Phase 1: Planning and Design](phase-1-planning-and-design.md)
- Key outcomes:
	- UCS AI Sizer-based capacity planning
	- Scale-unit mapping and topology targets
	- Baseline success criteria and risk mitigation

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## Phase 2: Hardware Staging

Standardizes physical installation, management-plane readiness, and pre-OS firmware parity.

- Document: [Phase 2: Hardware Staging](phase-2-hardware-staging.md)
- Key outcomes:
	- Deterministic cabling and labeling
	- OOB management validation
	- Firmware and BIOS baseline consistency

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## Phase 3: Fabric Configuration

Activates frontend/backend fabrics and validates stability for distributed GPU workloads.

- Document: [Phase 3: Fabric Configuration](phase-3-fabric-configuration.md)
- Key outcomes:
	- RoCE/QoS baseline implementation
	- Link and policy conformance checks
	- NCCL and fabric health validation

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## Phase 4: Compute and GPU Configuration

Phase 4 is split into compute lifecycle baseline and GPU runtime tuning.

- Compute document: [Phase 4A: Compute Provisioning](phase-4-compute-provisioning.md)
- GPU document: [Phase 4B: GPU Configuration](phase-4-gpu-configuration.md)
- Key outcomes:
	- Role-based provisioning templates
	- Runtime and fabric service validation
	- Thermal, RDMA, and performance baselines

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## Phase 5: Storage Provisioning

Aligns data-path architecture, checkpoint protection, and lifecycle tiering to workload demands.

- Document: [Phase 5: Storage Provisioning](phase-5-storage-provisioning.md)
- Key outcomes:
	- Throughput and capacity planning
	- Snapshot/recovery validation
	- Data pipeline reliability controls

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## Phase 6: Orchestration and Workload Operations

Operationalizes cluster policy, operator lifecycle, scheduling controls, and production validation.

- Document: [Phase 6: Orchestration and Workload Operations](phase-6-orchestration-and-workload.md)
- Key outcomes:
	- Operator stack health and governance
	- Training/inference pool isolation
	- NCCL and inference SLO validation

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## Suggested Execution Order

1. Start with [Phase 1: Planning and Design](phase-1-planning-and-design.md).
2. Continue through phases 2 and 3 before onboarding compute runtimes.
3. Complete both phase 4 documents before phase 5 and phase 6 production rollout.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

#### [<ins>Back to `Repository` README</ins>](../README.md)
