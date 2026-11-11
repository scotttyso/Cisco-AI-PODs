# Subsystem 04 - Storage (Everpure FlashBlade + XFM)

Stub. Will deploy and configure Everpure FlashBlade//S with XFM aggregation switches (pair of 1RU switches that aggregate multiple FlashBlade chassis to scale storage incrementally), exposed to OpenShift via the FB CSI driver.

Vendor-named per the locked subsystem table (D11/S1) — future storage variants land as peer subsystems (`storage-netapp/`, `storage-vast/`, etc.) so partner ownership stays clean.

Schema: [`schemas/storage-everpure.schema.json`](../schemas/storage-everpure.schema.json) (stub today).
