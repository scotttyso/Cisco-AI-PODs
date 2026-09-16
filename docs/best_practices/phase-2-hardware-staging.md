# Phase 2: Hardware Staging and Day-0 Readiness

## Executive Summary

Phase 2 ensures every compute node, management interface, and physical link is installed consistently before fabric bring-up. The objective is to eliminate avoidable Day-1 failures caused by cabling mistakes, firmware drift, and incomplete out-of-band management setup.

For Cisco AI PODs aligned to the current guidance in this repository, use:
- Training-focused GPUs: B300 and H200
- Inference-focused GPUs: RTX6000 and RTX4500

## Table of Contents
- [1. Cable Labeling and Documentation](#1-cable-labeling-and-documentation-pre-power-on)
- [2. Out-of-Band Management Network Setup](#2-out-of-band-management-network-setup)
- [3. Baseline Firmware and BIOS Policy](#3-baseline-firmware-and-bios-policy-pre-os)
- [4. GPU and Node Staging Matrix](#4-gpu-and-node-staging-matrix)
- [5. Phase Completion Checklist](#5-phase-completion-checklist)
- [Summary](#summary)

## 1. Cable Labeling and Documentation (Pre-Power-On)

In AI Pods, high-density 400G and 800G links make traceability mandatory. A single crossed backend cable can degrade all-reduce performance across the cluster.

### Best Practices

1. Source-to-destination labels on both ends of every cable.
2. Use a strict label pattern:
   - NODE-RACK-UNIT:PORT -> SWITCH-RACK-UNIT:PORT
3. Maintain color standards:
   - Blue or green: frontend and management traffic
   - Yellow or orange: backend GPU fabric
   - Red: dual-feed power
4. Track cable inventory in a cable matrix:
   - Serial number
   - Length
   - Media type (DAC, AOC, transceiver + fiber)
   - Endpoint pair
5. Require two-person verification for backend ports before power-on.

### Troubleshooting: Cabling Faults

- Symptom: CRC or FCS errors increase on backend ports.
  - Action: Reseat optics and cable, inspect bend radius, swap to known-good cable, validate transceiver compatibility.
- Symptom: One node underperforms in NCCL tests.
  - Action: Verify backend port map for that node, check link speed/duplex, compare with baseline node.
- Symptom: Links stay down after boot.
  - Action: Confirm both ends are in matching breakout mode and speed profile.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 2. Out-of-Band Management Network Setup

Out-of-band (OOB) access enables zero-touch recovery, firmware operations, and remote lifecycle control through Cisco Intersight.

### Setup Steps

1. Connect all CIMC or BMC ports to a dedicated OOB switch stack.
2. Assign management addresses using static IP or DHCP reservations.
3. Reserve a dedicated management VLAN and subnet.
4. Confirm outbound HTTPS reachability to Cisco Intersight.
5. Harden baseline access:
   - Rotate default credentials immediately
   - Enable HTTPS and SSH only
   - Disable insecure services and unused accounts

### OOB Validation Checklist

- [ ] Every server responds to ping and SSH in management VLAN.
- [ ] Time sync configured (NTP) on switches and servers.
- [ ] DNS resolution works for management services.
- [ ] Intersight device claim completed for each node.

### Troubleshooting: OOB Access Issues

- Symptom: Node visible on switch but not reachable by IP.
  - Action: Validate VLAN tagging, native VLAN mismatch, and ACLs.
- Symptom: Intersight claim fails intermittently.
  - Action: Check outbound firewall policy, DNS resolution, and certificate trust path.
- Symptom: Slow management sessions.
  - Action: Verify no oversubscription or QoS policing on OOB path.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 3. Baseline Firmware and BIOS Policy (Pre-OS)

Uniform firmware is required for stable distributed training and consistent behavior for GPUDirect RDMA, PCIe topology, and accelerator telemetry.

### Firmware Staging Guidance

1. Define a standard firmware baseline in Cisco Intersight.
2. Apply baseline using Server Profile Templates.
3. Stage upgrades in rings:
   - Ring 0: One canary node
   - Ring 1: One rack
   - Ring 2: Remaining fleet
4. Verify post-upgrade parity across:
   - BIOS
   - BMC/CIMC
   - NIC/VIC
   - GPU firmware and drivers

### BIOS and Platform Settings

- Enable SR-IOV and IOMMU where required.
- Configure NUMA-aware policies and deterministic performance profile.
- Keep PCIe link settings consistent across all nodes.
- Document any vendor-required deviations per GPU type:
  - B300 and H200 training nodes
  - RTX6000 and RTX4500 inference nodes

### Troubleshooting: Firmware Drift and Stability

- Symptom: Performance variance across otherwise identical nodes.
  - Action: Compare full firmware inventory and BIOS exports; remediate drift before workload tests.
- Symptom: GPU not enumerated after upgrade.
  - Action: Check PCIe slot mapping, power state, BIOS compatibility, and driver version pinning.
- Symptom: RDMA not available on subset of nodes.
  - Action: Confirm NIC firmware consistency, RoCE settings, and driver module parity.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 4. GPU and Node Staging Matrix

Use a clear placement matrix so each node role is explicit before cluster provisioning.

| Node Role | GPU Profile | Primary Workload | Notes |
|---|---|---|---|
| Training Node | B300 | Large-scale training | Maximize backend fabric bandwidth and cooling headroom |
| Training Node | H200 | Fine-tuning and training | Strong memory capacity, balanced scale-out |
| Inference Node | RTX6000 | High-throughput inference | Optimize for serving density and latency |
| Inference Node | RTX4500 | Cost-efficient inference | Suitable for lower concurrency tiers |

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

## 5. Phase Completion Checklist

Do not proceed to Phase 3 until all criteria pass.

- [ ] Cable map approved and physically verified.
- [ ] OOB management reachable for every node.
- [ ] Intersight claim and policy attachment complete.
- [ ] Firmware baseline consistent across fleet.
- [ ] GPU inventory matches node role matrix.
- [ ] Initial node health checks pass with no critical hardware alerts.

## Summary

A successful Phase 2 focuses on repeatability: deterministic cabling, deterministic management reachability, and deterministic firmware state. That foundation reduces fabric issues in Phase 3 and shortens time to first stable distributed workload.

#### [<ins>Back to Table of Contents</ins>](#table-of-contents)

#### [<ins>Next Step - `Phase 3: Fabric Configuration and Validation`</ins>](phase-3-fabric-configuration.md)

#### [<ins>Back to `Best Practices` README</ins>](README.md)

#### [<ins>Back to `Repository` README</ins>](../../README.md)
