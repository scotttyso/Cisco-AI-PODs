# Storage Policy Templates Reference

Each template lists the storage settings it configures.
Settings not listed are left at policy defaults.

## Table of Contents

- [edge_compact](#edge_compact)
- [inference_optimized](#inference_optimized)
- [model_cache](#model_cache)
- [training_data](#training_data)

---

## edge_compact

_Recommended storage settings for Unified Edge nodes._

| Setting | Value | Description |
|---|---|---|
| `default_drive_state` | `UnconfiguredGood` | Initial state for unconfigured/newly inserted drives. |
| `hybrid_slot_configuration.direct_attached_nvme_slots` | `1-4` | NVMe slots configured in direct-attach (passthrough) mode. |
| `m2_raid_configuration.name` | `MStorBootVd` | Name of the M.2 RAID virtual drive. |
| `m2_raid_configuration.slot` | `MSTOR-RAID-1` | M.2 RAID controller slot for the boot virtual drive. |
| `single_drive_raid0_configuration.virtual_drive_policy.access_policy` | `ReadWrite` | Host access mode for the virtual drive (ReadWrite, ReadOnly, Blocked). |
| `single_drive_raid0_configuration.virtual_drive_policy.drive_cache` | `Default` | Disk cache mode (Enable, Disable, NoChange, Default). |
| `single_drive_raid0_configuration.virtual_drive_policy.read_policy` | `ReadAhead` | Read-ahead mode (ReadAhead, NoReadAhead, Default). |
| `single_drive_raid0_configuration.virtual_drive_policy.strip_size` | `64` | RAID strip size in KiB (64, 128, 256, 512, 1024). |
| `single_drive_raid0_configuration.virtual_drive_policy.write_policy` | `WriteThrough` | Write cache mode (WriteThrough, WriteBackGoodBbu, AlwaysWriteBack, Default). |
| `unused_disks_state` | `NoChange` | State to set for drives not used by this policy. |
| `use_jbod_for_vd_creation` | `False` | Allow JBOD-state drives to be used for virtual drive creation. |

[⬆ Back to Top](#table-of-contents)
---

## inference_optimized

_Recommended storage settings for inference optimized workloads._

| Setting | Value | Description |
|---|---|---|
| `default_drive_state` | `UnconfiguredGood` | Initial state for unconfigured/newly inserted drives. |
| `hybrid_slot_configuration.direct_attached_nvme_slots` | `1-4` | NVMe slots configured in direct-attach (passthrough) mode. |
| `single_drive_raid0_configuration.virtual_drive_policy.access_policy` | `ReadWrite` | Host access mode for the virtual drive (ReadWrite, ReadOnly, Blocked). |
| `single_drive_raid0_configuration.virtual_drive_policy.drive_cache` | `Enable` | Disk cache mode (Enable, Disable, NoChange, Default). |
| `single_drive_raid0_configuration.virtual_drive_policy.read_policy` | `ReadAhead` | Read-ahead mode (ReadAhead, NoReadAhead, Default). |
| `single_drive_raid0_configuration.virtual_drive_policy.strip_size` | `256` | RAID strip size in KiB (64, 128, 256, 512, 1024). |
| `single_drive_raid0_configuration.virtual_drive_policy.write_policy` | `WriteThrough` | Write cache mode (WriteThrough, WriteBackGoodBbu, AlwaysWriteBack, Default). |
| `unused_disks_state` | `NoChange` | State to set for drives not used by this policy. |
| `use_jbod_for_vd_creation` | `False` | Allow JBOD-state drives to be used for virtual drive creation. |

[⬆ Back to Top](#table-of-contents)
---

## model_cache

_Recommended storage settings for fast NVMe cache tier for model artifacts._

| Setting | Value | Description |
|---|---|---|
| `default_drive_state` | `UnconfiguredGood` | Initial state for unconfigured/newly inserted drives. |
| `hybrid_slot_configuration.direct_attached_nvme_slots` | `1-4` | NVMe slots configured in direct-attach (passthrough) mode. |
| `m2_raid_configuration.name` | `MStorBootVd` | Name of the M.2 RAID virtual drive. |
| `m2_raid_configuration.slot` | `MSTOR-RAID-1` | M.2 RAID controller slot for the boot virtual drive. |
| `unused_disks_state` | `NoChange` | State to set for drives not used by this policy. |
| `use_jbod_for_vd_creation` | `False` | Allow JBOD-state drives to be used for virtual drive creation. |

[⬆ Back to Top](#table-of-contents)
---

## training_data

_Recommended storage settings for large dataset access during training._

| Setting | Value | Description |
|---|---|---|
| `default_drive_state` | `UnconfiguredGood` | Initial state for unconfigured/newly inserted drives. |
| `hybrid_slot_configuration.direct_attached_nvme_slots` | `1-4` | NVMe slots configured in direct-attach (passthrough) mode. |
| `m2_raid_configuration.name` | `MStorBootVd` | Name of the M.2 RAID virtual drive. |
| `m2_raid_configuration.slot` | `MSTOR-RAID-1` | M.2 RAID controller slot for the boot virtual drive. |
| `single_drive_raid0_configuration.virtual_drive_policy.access_policy` | `ReadWrite` | Host access mode for the virtual drive (ReadWrite, ReadOnly, Blocked). |
| `single_drive_raid0_configuration.virtual_drive_policy.drive_cache` | `Enable` | Disk cache mode (Enable, Disable, NoChange, Default). |
| `single_drive_raid0_configuration.virtual_drive_policy.read_policy` | `ReadAhead` | Read-ahead mode (ReadAhead, NoReadAhead, Default). |
| `single_drive_raid0_configuration.virtual_drive_policy.strip_size` | `512` | RAID strip size in KiB (64, 128, 256, 512, 1024). |
| `single_drive_raid0_configuration.virtual_drive_policy.write_policy` | `AlwaysWriteBack` | Write cache mode (WriteThrough, WriteBackGoodBbu, AlwaysWriteBack, Default). |
| `unused_disks_state` | `UnconfiguredGood` | State to set for drives not used by this policy. |
| `use_jbod_for_vd_creation` | `False` | Allow JBOD-state drives to be used for virtual drive creation. |

[⬆ Back to Top](#table-of-contents)