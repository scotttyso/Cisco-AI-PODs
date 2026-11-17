# Fibre Channel Adapter Policy Templates Reference

Each template lists the FC adapter settings it configures.
Settings not listed are left at policy defaults.

## Table of Contents

- [FCNVMeInitiator](#fcnvmeinitiator)
- [FCNVMeTarget](#fcnvmetarget)
- [Initiator](#initiator)
- [Linux](#linux)
- [Solaris](#solaris)
- [Target](#target)
- [VMware](#vmware)
- [Windows](#windows)
- [WindowsBoot](#windowsboot)

---

## FCNVMeInitiator

_Recommended adapter settings for FC NVMe Initiator._

| Setting | Value | Description |
|---|---|---|
| `IoThrottleCount` | `256` | Maximum pending I/O operations on the virtual interface at one time. |
| `error_recovery.port_down_io_retry` | `30` | Number of I/O retries before marking a port unavailable. |
| `error_recovery.port_down_timeout` | `30000` | Milliseconds a remote FC port must be offline before marking unavailable. |

[⬆ Back to Top](#table-of-contents)
---

## FCNVMeTarget

_Recommended adapter settings for FC NVMe Target._

| Setting | Value | Description |
|---|---|---|
| `IoThrottleCount` | `256` | Maximum pending I/O operations on the virtual interface at one time. |
| `error_recovery.port_down_io_retry` | `30` | Number of I/O retries before marking a port unavailable. |
| `error_recovery.port_down_timeout` | `30000` | Milliseconds a remote FC port must be offline before marking unavailable. |

[⬆ Back to Top](#table-of-contents)
---

## Initiator

_Recommended adapter settings for SCSI Initiator._

| Setting | Value | Description |
|---|---|---|
| `IoThrottleCount` | `256` | Maximum pending I/O operations on the virtual interface at one time. |
| `error_recovery.port_down_io_retry` | `30` | Number of I/O retries before marking a port unavailable. |
| `error_recovery.port_down_timeout` | `10000` | Milliseconds a remote FC port must be offline before marking unavailable. |

[⬆ Back to Top](#table-of-contents)
---

## Linux

_Recommended adapter settings for Linux._

| Setting | Value | Description |
|---|---|---|
| `IoThrottleCount` | `256` | Maximum pending I/O operations on the virtual interface at one time. |
| `error_recovery.port_down_io_retry` | `30` | Number of I/O retries before marking a port unavailable. |
| `error_recovery.port_down_timeout` | `30000` | Milliseconds a remote FC port must be offline before marking unavailable. |

[⬆ Back to Top](#table-of-contents)
---

## Solaris

_Recommended adapter settings for Solaris._

| Setting | Value | Description |
|---|---|---|
| `IoThrottleCount` | `256` | Maximum pending I/O operations on the virtual interface at one time. |
| `error_recovery.port_down_io_retry` | `30` | Number of I/O retries before marking a port unavailable. |
| `error_recovery.port_down_timeout` | `30000` | Milliseconds a remote FC port must be offline before marking unavailable. |
| `flogi.retries` | `8` | Number of fabric login retry attempts after first failure. |
| `flogi.timeout` | `20000` | Milliseconds to wait before retrying fabric login. |

[⬆ Back to Top](#table-of-contents)
---

## Target

_Recommended adapter settings for Target._

| Setting | Value | Description |
|---|---|---|
| `IoThrottleCount` | `256` | Maximum pending I/O operations on the virtual interface at one time. |
| `error_recovery.port_down_io_retry` | `30` | Number of I/O retries before marking a port unavailable. |
| `error_recovery.port_down_timeout` | `30000` | Milliseconds a remote FC port must be offline before marking unavailable. |

[⬆ Back to Top](#table-of-contents)
---

## VMware

_Recommended adapter settings for VMware._

| Setting | Value | Description |
|---|---|---|
| `IoThrottleCount` | `256` | Maximum pending I/O operations on the virtual interface at one time. |
| `error_recovery.port_down_io_retry` | `30` | Number of I/O retries before marking a port unavailable. |
| `error_recovery.port_down_timeout` | `10000` | Milliseconds a remote FC port must be offline before marking unavailable. |

[⬆ Back to Top](#table-of-contents)
---

## Windows

_Recommended adapter settings for Windows._

| Setting | Value | Description |
|---|---|---|
| `IoThrottleCount` | `256` | Maximum pending I/O operations on the virtual interface at one time. |
| `error_recovery.port_down_io_retry` | `30` | Number of I/O retries before marking a port unavailable. |
| `error_recovery.port_down_timeout` | `30000` | Milliseconds a remote FC port must be offline before marking unavailable. |

[⬆ Back to Top](#table-of-contents)
---

## WindowsBoot

_Recommended adapter settings for Windows Boot._

| Setting | Value | Description |
|---|---|---|
| `IoThrottleCount` | `256` | Maximum pending I/O operations on the virtual interface at one time. |
| `error_recovery.port_down_io_retry` | `30` | Number of I/O retries before marking a port unavailable. |
| `error_recovery.port_down_timeout` | `5000` | Milliseconds a remote FC port must be offline before marking unavailable. |
| `plogi.retries` | `8` | Number of port login retry attempts after first failure. |
| `plogi.timeout` | `4000` | Milliseconds to wait before retrying port login. |

[⬆ Back to Top](#table-of-contents)