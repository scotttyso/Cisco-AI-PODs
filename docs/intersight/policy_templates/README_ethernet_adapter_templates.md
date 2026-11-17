# Ethernet Adapter Policy Templates Reference

Each template below lists all adapter settings it configures.
Settings not listed are left at policy defaults.

## Table of Contents

- [16RxQs-4G](#16rxqs-4g)
- [16RxQs-5G](#16rxqs-5g)
- [Linux](#linux)
- [Linux-NVMe-RoCE](#linux-nvme-roce)
- [Linux-v2](#linux-v2)
- [MQ](#mq)
- [MQ-SMBd](#mq-smbd)
- [MQ-SMBd-v2](#mq-smbd-v2)
- [MQ-v2](#mq-v2)
- [SMBClient](#smbclient)
- [SMBServer](#smbserver)
- [SRIOV-HPN](#sriov-hpn)
- [Solaris](#solaris)
- [VMWareNVMeRoCEv2](#vmwarenvmerocEv2)
- [VMware](#vmware)
- [VMware-High-Trf](#vmware-high-trf)
- [VMware-v2](#vmware-v2)
- [VMwarePassThru](#vmwarepassthru)
- [Win-AzureStack](#win-azurestack)
- [Win-HPN](#win-hpn)
- [Win-HPN-SMBd](#win-hpn-smbd)
- [Win-HPN-SMBd-v2](#win-hpn-smbd-v2)
- [Win-HPN-v2](#win-hpn-v2)
- [Windows](#windows)
- [usNIC](#usnic)
- [usNICOracleRAC](#usnicoraclerac)

---

## 16RxQs-4G

_Recommended adapter settings for 16RxQs 4th Gen VIC._

| Setting | Value | Description |
|---|---|---|
| `completion.queue_count` | `9` | Number of completion queue resources to allocate. |
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `19` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |
| `receive.queue_count` | `8` | Number of receive queue resources to allocate. |
| `receive.ring_size` | `4096` | Number of descriptors in each receive queue. |
| `receive_side_scaling_enable` | `True` | Spread incoming traffic across multiple CPU cores. |
| `transmit.queue_count` | `1` | Number of transmit queue resources to allocate. |
| `transmit.ring_size` | `4096` | Number of descriptors in each transmit queue. |

[⬆ Back to Top](#table-of-contents)
---

## 16RxQs-5G

_Recommended adapter settings for 16RxQs 5th Gen VIC._

| Setting | Value | Description |
|---|---|---|
| `completion.queue_count` | `9` | Number of completion queue resources to allocate. |
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `19` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |
| `receive.queue_count` | `16` | Number of receive queue resources to allocate. |
| `receive.ring_size` | `16384` | Number of descriptors in each receive queue. |
| `receive_side_scaling_enable` | `True` | Spread incoming traffic across multiple CPU cores. |
| `transmit.queue_count` | `1` | Number of transmit queue resources to allocate. |
| `transmit.ring_size` | `16384` | Number of descriptors in each transmit queue. |

[⬆ Back to Top](#table-of-contents)
---

## Linux

_Recommended adapter settings for Linux._

| Setting | Value | Description |
|---|---|---|
| `completion.queue_count` | `2` | Number of completion queue resources to allocate. |
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `4` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |
| `receive.queue_count` | `1` | Number of receive queue resources to allocate. |
| `receive.ring_size` | `512` | Number of descriptors in each receive queue. |
| `receive_side_scaling_enable` | `False` | Spread incoming traffic across multiple CPU cores. |

[⬆ Back to Top](#table-of-contents)
---

## Linux-NVMe-RoCE

_Recommended adapter settings for Linux NVMe with RoCEv2._

| Setting | Value | Description |
|---|---|---|
| `completion.queue_count` | `2` | Number of completion queue resources to allocate. |
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `256` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |
| `receive.queue_count` | `1` | Number of receive queue resources to allocate. |
| `receive.ring_size` | `512` | Number of descriptors in each receive queue. |
| `receive_side_scaling_enable` | `True` | Spread incoming traffic across multiple CPU cores. |
| `roce_settings.class_of_service` | `5` | RoCE class of service (CoS) level. |
| `roce_settings.enable_rdma_over_converged_ethernet` | `True` | Enable RoCE (RDMA over Converged Ethernet). |
| `roce_settings.memory_regions` | `131072` | Number of memory regions per adapter. |
| `roce_settings.queue_pairs` | `1024` | Number of RoCE queue pairs per adapter. |
| `roce_settings.resource_groups` | `8` | Number of RoCE resource groups per adapter. |
| `roce_settings.version` | `2` | RoCE protocol version (1 or 2). |

[⬆ Back to Top](#table-of-contents)
---

## Linux-v2

_Recommended adapter settings for Linux Version 2._

| Setting | Value | Description |
|---|---|---|
| `completion.queue_count` | `9` | Number of completion queue resources to allocate. |
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `11` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |
| `receive.queue_count` | `8` | Number of receive queue resources to allocate. |
| `receive.ring_size` | `4096` | Number of descriptors in each receive queue. |
| `receive_side_scaling_enable` | `True` | Spread incoming traffic across multiple CPU cores. |
| `roce_settings.class_of_service` | `5` | RoCE class of service (CoS) level. |
| `roce_settings.enable_rdma_over_converged_ethernet` | `True` | Enable RoCE (RDMA over Converged Ethernet). |
| `roce_settings.memory_regions` | `131072` | Number of memory regions per adapter. |
| `roce_settings.queue_pairs` | `1024` | Number of RoCE queue pairs per adapter. |
| `roce_settings.resource_groups` | `8` | Number of RoCE resource groups per adapter. |
| `roce_settings.version` | `2` | RoCE protocol version (1 or 2). |
| `transmit.queue_count` | `1` | Number of transmit queue resources to allocate. |
| `transmit.ring_size` | `4096` | Number of descriptors in each transmit queue. |

[⬆ Back to Top](#table-of-contents)
---

## MQ

_Recommended adapter settings for MQ._

| Setting | Value | Description |
|---|---|---|
| `completion.queue_count` | `576` | Number of completion queue resources to allocate. |
| `completion.ring_size` | `4` | Number of descriptors in each completion queue. |
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `256` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |
| `receive.queue_count` | `512` | Number of receive queue resources to allocate. |
| `receive.ring_size` | `512` | Number of descriptors in each receive queue. |
| `receive_side_scaling_enable` | `True` | Spread incoming traffic across multiple CPU cores. |
| `transmit.queue_count` | `64` | Number of transmit queue resources to allocate. |
| `transmit.ring_size` | `256` | Number of descriptors in each transmit queue. |

[⬆ Back to Top](#table-of-contents)
---

## MQ-SMBd

_Recommended adapter settings for MQ-SMBd._

| Setting | Value | Description |
|---|---|---|
| `completion.queue_count` | `576` | Number of completion queue resources to allocate. |
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `512` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |
| `receive.queue_count` | `512` | Number of receive queue resources to allocate. |
| `receive.ring_size` | `512` | Number of descriptors in each receive queue. |
| `receive_side_scaling_enable` | `True` | Spread incoming traffic across multiple CPU cores. |
| `roce_settings.class_of_service` | `5` | RoCE class of service (CoS) level. |
| `roce_settings.enable_rdma_over_converged_ethernet` | `True` | Enable RoCE (RDMA over Converged Ethernet). |
| `roce_settings.memory_regions` | `65536` | Number of memory regions per adapter. |
| `roce_settings.queue_pairs` | `256` | Number of RoCE queue pairs per adapter. |
| `roce_settings.resource_groups` | `2` | Number of RoCE resource groups per adapter. |
| `roce_settings.version` | `2` | RoCE protocol version (1 or 2). |
| `transmit.queue_count` | `64` | Number of transmit queue resources to allocate. |
| `transmit.ring_size` | `256` | Number of descriptors in each transmit queue. |

[⬆ Back to Top](#table-of-contents)
---

## MQ-SMBd-v2

_Recommended adapter settings for VIC 1400/14000/15000 series and later optimized for Multi Queue SMBd high performance networking._

| Setting | Value | Description |
|---|---|---|
| `completion.queue_count` | `576` | Number of completion queue resources to allocate. |
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `512` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |
| `receive.queue_count` | `512` | Number of receive queue resources to allocate. |
| `receive.ring_size` | `4096` | Number of descriptors in each receive queue. |
| `receive_side_scaling_enable` | `True` | Spread incoming traffic across multiple CPU cores. |
| `roce_settings.class_of_service` | `5` | RoCE class of service (CoS) level. |
| `roce_settings.enable_rdma_over_converged_ethernet` | `True` | Enable RoCE (RDMA over Converged Ethernet). |
| `roce_settings.memory_regions` | `131072` | Number of memory regions per adapter. |
| `roce_settings.queue_pairs` | `2048` | Number of RoCE queue pairs per adapter. |
| `roce_settings.resource_groups` | `32` | Number of RoCE resource groups per adapter. |
| `roce_settings.version` | `2` | RoCE protocol version (1 or 2). |
| `transmit.queue_count` | `64` | Number of transmit queue resources to allocate. |
| `transmit.ring_size` | `4096` | Number of descriptors in each transmit queue. |

[⬆ Back to Top](#table-of-contents)
---

## MQ-v2

_Recommended adapter settings for VIC 1400/14000/15000 series and later optimized for Multi Queue high performance networking._

| Setting | Value | Description |
|---|---|---|
| `completion.queue_count` | `576` | Number of completion queue resources to allocate. |
| `completion.ring_size` | `4` | Number of descriptors in each completion queue. |
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `256` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |
| `receive.queue_count` | `512` | Number of receive queue resources to allocate. |
| `receive.ring_size` | `4096` | Number of descriptors in each receive queue. |
| `receive_side_scaling_enable` | `True` | Spread incoming traffic across multiple CPU cores. |
| `transmit.queue_count` | `64` | Number of transmit queue resources to allocate. |
| `transmit.ring_size` | `4096` | Number of descriptors in each transmit queue. |

[⬆ Back to Top](#table-of-contents)
---

## SMBClient

_Recommended adapter settings for SMBClient._

| Setting | Value | Description |
|---|---|---|
| `receive_side_scaling_enable` | `True` | Spread incoming traffic across multiple CPU cores. |
| `roce_settings.class_of_service` | `0` | RoCE class of service (CoS) level. |
| `roce_settings.enable_rdma_over_converged_ethernet` | `True` | Enable RoCE (RDMA over Converged Ethernet). |
| `roce_settings.memory_regions` | `131072` | Number of memory regions per adapter. |
| `roce_settings.queue_pairs` | `2048` | Number of RoCE queue pairs per adapter. |
| `roce_settings.resource_groups` | `32` | Number of RoCE resource groups per adapter. |
| `roce_settings.version` | `1` | RoCE protocol version (1 or 2). |

[⬆ Back to Top](#table-of-contents)
---

## SMBServer

_Recommended adapter settings for SMBServer._

| Setting | Value | Description |
|---|---|---|
| `receive_side_scaling_enable` | `True` | Spread incoming traffic across multiple CPU cores. |
| `roce_settings.class_of_service` | `0` | RoCE class of service (CoS) level. |
| `roce_settings.enable_rdma_over_converged_ethernet` | `True` | Enable RoCE (RDMA over Converged Ethernet). |
| `roce_settings.memory_regions` | `131072` | Number of memory regions per adapter. |
| `roce_settings.queue_pairs` | `2048` | Number of RoCE queue pairs per adapter. |
| `roce_settings.resource_groups` | `32` | Number of RoCE resource groups per adapter. |
| `roce_settings.version` | `1` | RoCE protocol version (1 or 2). |

[⬆ Back to Top](#table-of-contents)
---

## SRIOV-HPN

_Recommended adapter settings for SRIOV high performance and networking._

| Setting | Value | Description |
|---|---|---|
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `32` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |

[⬆ Back to Top](#table-of-contents)
---

## Solaris

_Recommended adapter settings for Solaris._

| Setting | Value | Description |
|---|---|---|
| `completion.queue_count` | `2` | Number of completion queue resources to allocate. |
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `4` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |
| `receive_side_scaling_enable` | `False` | Spread incoming traffic across multiple CPU cores. |

[⬆ Back to Top](#table-of-contents)
---

## VMWareNVMeRoCEv2

_Recommended adapter settings for VMware NVMe ROCEv2._

| Setting | Value | Description |
|---|---|---|
| `completion.queue_count` | `2` | Number of completion queue resources to allocate. |
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `256` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |
| `receive.queue_count` | `1` | Number of receive queue resources to allocate. |
| `receive.ring_size` | `512` | Number of descriptors in each receive queue. |
| `receive_side_scaling_enable` | `True` | Spread incoming traffic across multiple CPU cores. |
| `roce_settings.class_of_service` | `5` | RoCE class of service (CoS) level. |
| `roce_settings.enable_rdma_over_converged_ethernet` | `True` | Enable RoCE (RDMA over Converged Ethernet). |
| `roce_settings.memory_regions` | `131072` | Number of memory regions per adapter. |
| `roce_settings.queue_pairs` | `1024` | Number of RoCE queue pairs per adapter. |
| `roce_settings.resource_groups` | `8` | Number of RoCE resource groups per adapter. |
| `roce_settings.version` | `2` | RoCE protocol version (1 or 2). |
| `transmit.queue_count` | `1` | Number of transmit queue resources to allocate. |
| `transmit.ring_size` | `256` | Number of descriptors in each transmit queue. |

[⬆ Back to Top](#table-of-contents)
---

## VMware

_Recommended adapter settings for VMware._

| Setting | Value | Description |
|---|---|---|
| `completion.queue_count` | `2` | Number of completion queue resources to allocate. |
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `4` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |
| `receive.queue_count` | `4` | Number of receive queue resources to allocate. |
| `receive.ring_size` | `512` | Number of descriptors in each receive queue. |
| `receive_side_scaling_enable` | `False` | Spread incoming traffic across multiple CPU cores. |

[⬆ Back to Top](#table-of-contents)
---

## VMware-High-Trf

_Recommended adapter settings for VMware High Traffic._

| Setting | Value | Description |
|---|---|---|
| `completion.queue_count` | `9` | Number of completion queue resources to allocate. |
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `11` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |
| `receive.queue_count` | `8` | Number of receive queue resources to allocate. |
| `receive.ring_size` | `4096` | Number of descriptors in each receive queue. |
| `receive_side_scaling_enable` | `True` | Spread incoming traffic across multiple CPU cores. |
| `transmit.queue_count` | `1` | Number of transmit queue resources to allocate. |
| `transmit.ring_size` | `4096` | Number of descriptors in each transmit queue. |

[⬆ Back to Top](#table-of-contents)
---

## VMware-v2

_Recommended adapter settings for VMware Version 2._

| Setting | Value | Description |
|---|---|---|
| `completion.queue_count` | `9` | Number of completion queue resources to allocate. |
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `11` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |
| `receive.queue_count` | `8` | Number of receive queue resources to allocate. |
| `receive.ring_size` | `4096` | Number of descriptors in each receive queue. |
| `receive_side_scaling_enable` | `True` | Spread incoming traffic across multiple CPU cores. |
| `roce_settings.class_of_service` | `5` | RoCE class of service (CoS) level. |
| `roce_settings.enable_rdma_over_converged_ethernet` | `True` | Enable RoCE (RDMA over Converged Ethernet). |
| `roce_settings.memory_regions` | `131072` | Number of memory regions per adapter. |
| `roce_settings.queue_pairs` | `1024` | Number of RoCE queue pairs per adapter. |
| `roce_settings.resource_groups` | `8` | Number of RoCE resource groups per adapter. |
| `roce_settings.version` | `2` | RoCE protocol version (1 or 2). |
| `transmit.queue_count` | `1` | Number of transmit queue resources to allocate. |
| `transmit.ring_size` | `4096` | Number of descriptors in each transmit queue. |

[⬆ Back to Top](#table-of-contents)
---

## VMwarePassThru

_Recommended adapter settings for VMwarePassThru._

| Setting | Value | Description |
|---|---|---|
| `completion.queue_count` | `8` | Number of completion queue resources to allocate. |
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `12` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |
| `receive_side_scaling_enable` | `True` | Spread incoming traffic across multiple CPU cores. |
| `transmit.queue_count` | `4` | Number of transmit queue resources to allocate. |
| `transmit.ring_size` | `256` | Number of descriptors in each transmit queue. |

[⬆ Back to Top](#table-of-contents)
---

## Win-AzureStack

_Recommended adapter settings for Win-AzureStack._

| Setting | Value | Description |
|---|---|---|
| `completion.queue_count` | `11` | Number of completion queue resources to allocate. |
| `completion.ring_size` | `256` | Number of descriptors in each completion queue. |
| `enable_vxlan_offload` | `True` | Enable VXLAN protocol offload on the virtual interface. |
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `256` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |
| `receive.queue_count` | `8` | Number of receive queue resources to allocate. |
| `receive.ring_size` | `4096` | Number of descriptors in each receive queue. |
| `receive_side_scaling_enable` | `True` | Spread incoming traffic across multiple CPU cores. |
| `roce_settings.class_of_service` | `5` | RoCE class of service (CoS) level. |
| `roce_settings.enable_rdma_over_converged_ethernet` | `True` | Enable RoCE (RDMA over Converged Ethernet). |
| `roce_settings.memory_regions` | `131072` | Number of memory regions per adapter. |
| `roce_settings.queue_pairs` | `256` | Number of RoCE queue pairs per adapter. |
| `roce_settings.resource_groups` | `2` | Number of RoCE resource groups per adapter. |
| `roce_settings.version` | `2` | RoCE protocol version (1 or 2). |
| `transmit.queue_count` | `3` | Number of transmit queue resources to allocate. |
| `transmit.ring_size` | `1024` | Number of descriptors in each transmit queue. |

[⬆ Back to Top](#table-of-contents)
---

## Win-HPN

_Recommended adapter settings for Windows High Performance Networking._

| Setting | Value | Description |
|---|---|---|
| `enable_vxlan_offload` | `True` | Enable VXLAN protocol offload on the virtual interface. |
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `512` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |
| `receive_side_scaling_enable` | `True` | Spread incoming traffic across multiple CPU cores. |

[⬆ Back to Top](#table-of-contents)
---

## Win-HPN-SMBd

_Recommended adapter settings for Windows High Performance Networking SMBd._

| Setting | Value | Description |
|---|---|---|
| `enable_vxlan_offload` | `True` | Enable VXLAN protocol offload on the virtual interface. |
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `512` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |
| `receive_side_scaling_enable` | `True` | Spread incoming traffic across multiple CPU cores. |
| `roce_settings.class_of_service` | `5` | RoCE class of service (CoS) level. |
| `roce_settings.enable_rdma_over_converged_ethernet` | `True` | Enable RoCE (RDMA over Converged Ethernet). |
| `roce_settings.memory_regions` | `131072` | Number of memory regions per adapter. |
| `roce_settings.queue_pairs` | `256` | Number of RoCE queue pairs per adapter. |
| `roce_settings.resource_groups` | `2` | Number of RoCE resource groups per adapter. |
| `roce_settings.version` | `2` | RoCE protocol version (1 or 2). |

[⬆ Back to Top](#table-of-contents)
---

## Win-HPN-SMBd-v2

_Recommended adapter settings for VIC 1400/14000/15000 series and later optimized for Windows SMBd high performance networking._

| Setting | Value | Description |
|---|---|---|
| `completion.queue_count` | `9` | Number of completion queue resources to allocate. |
| `enable_vxlan_offload` | `True` | Enable VXLAN protocol offload on the virtual interface. |
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `512` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |
| `receive.queue_count` | `8` | Number of receive queue resources to allocate. |
| `receive.ring_size` | `4096` | Number of descriptors in each receive queue. |
| `receive_side_scaling_enable` | `True` | Spread incoming traffic across multiple CPU cores. |
| `roce_settings.class_of_service` | `5` | RoCE class of service (CoS) level. |
| `roce_settings.enable_rdma_over_converged_ethernet` | `True` | Enable RoCE (RDMA over Converged Ethernet). |
| `roce_settings.memory_regions` | `131072` | Number of memory regions per adapter. |
| `roce_settings.queue_pairs` | `256` | Number of RoCE queue pairs per adapter. |
| `roce_settings.resource_groups` | `2` | Number of RoCE resource groups per adapter. |
| `roce_settings.version` | `2` | RoCE protocol version (1 or 2). |
| `transmit.queue_count` | `1` | Number of transmit queue resources to allocate. |
| `transmit.ring_size` | `4096` | Number of descriptors in each transmit queue. |

[⬆ Back to Top](#table-of-contents)
---

## Win-HPN-v2

_Recommended adapter settings for VIC 1400/14000/15000 series and later optimized for Windows high performance networking._

| Setting | Value | Description |
|---|---|---|
| `completion.queue_count` | `9` | Number of completion queue resources to allocate. |
| `enable_vxlan_offload` | `True` | Enable VXLAN protocol offload on the virtual interface. |
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `512` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |
| `receive.queue_count` | `8` | Number of receive queue resources to allocate. |
| `receive.ring_size` | `4096` | Number of descriptors in each receive queue. |
| `receive_side_scaling_enable` | `True` | Spread incoming traffic across multiple CPU cores. |
| `transmit.queue_count` | `1` | Number of transmit queue resources to allocate. |
| `transmit.ring_size` | `4096` | Number of descriptors in each transmit queue. |

[⬆ Back to Top](#table-of-contents)
---

## Windows

_Recommended adapter settings for Windows._

_No additional settings (all defaults apply)._

---

## usNIC

_Recommended adapter settings for usNIC._

| Setting | Value | Description |
|---|---|---|
| `UplinkFailbackTimeout` | `0` | Seconds before switching back to primary uplink after recovery. |
| `completion.queue_count` | `12` | Number of completion queue resources to allocate. |
| `receive.queue_count` | `6` | Number of receive queue resources to allocate. |
| `receive.ring_size` | `512` | Number of descriptors in each receive queue. |
| `receive_side_scaling_enable` | `True` | Spread incoming traffic across multiple CPU cores. |
| `transmit.queue_count` | `6` | Number of transmit queue resources to allocate. |
| `transmit.ring_size` | `256` | Number of descriptors in each transmit queue. |

[⬆ Back to Top](#table-of-contents)
---

## usNICOracleRAC

_Recommended adapter settings for usNICOracleRAC._

| Setting | Value | Description |
|---|---|---|
| `InterruptScaling` | `True` | Enable interrupt scaling on the interface. |
| `UplinkFailbackTimeout` | `0` | Seconds before switching back to primary uplink after recovery. |
| `completion.queue_count` | `2000` | Number of completion queue resources to allocate. |
| `completion.ring_size` | `4` | Number of descriptors in each completion queue. |
| `interrupt_settings.coalescing_type` | `MIN` | Interrupt coalescing type (MIN or IDLE). |
| `interrupt_settings.mode` | `MSIx` | Interrupt mode (MSIx, MSI, or INTx). |
| `interrupt_settings.queue_count` | `1024` | Number of interrupt resources to allocate. |
| `interrupt_settings.timer` | `125` | Time (µs) between interrupts; 0 disables coalescing. |
| `receive.queue_count` | `1000` | Number of receive queue resources to allocate. |
| `receive.ring_size` | `512` | Number of descriptors in each receive queue. |
| `receive_side_scaling_enable` | `True` | Spread incoming traffic across multiple CPU cores. |
| `transmit.queue_count` | `1000` | Number of transmit queue resources to allocate. |
| `transmit.ring_size` | `256` | Number of descriptors in each transmit queue. |

[⬆ Back to Top](#table-of-contents)