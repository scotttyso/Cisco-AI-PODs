# Subsystem 06 - UCS workload nodes

Provisions UCS systems assigned to the OpenShift worker role. Workload nodes can use either the `domain` or `standalone` UCS platform and can serve `general` or `gpu` workloads. GPU workloads include AI Defense, GPU-equipped UCS X-Series and general-purpose C-Series systems, and dedicated rack AI servers.

Scope is hardware-level only: UCS domain Device Console, CIMC, or Cisco BMC 4.0 access; Intersight claim on supported platforms; server profiles; firmware policies; BIOS and boot configuration; GPU-specific tuning when applicable; and fabric attachment. UCS C880 does not support Intersight claim. Its deployment follows Procedures 1–6 in MOP-06 using Cisco BMC, Redfish, and HUU. The OpenShift install and role assignment live in Subsystem 07.

Schema: [`schemas/workload-nodes-ucs.schema.json`](../schemas/workload-nodes-ucs.schema.json).

## HGX server BMC settings

C845A and C880A BMCs are configured over Redfish by
[`automation/scripts/configure_hgx_bmc.py`](automation/scripts/configure_hgx_bmc.py)
from an `hgx_servers` variables file (schema: `hgx` namespace in
[`schema/cisco-ai-pods.json`](../schema/cisco-ai-pods.json); example:
[`examples/hgx/hgx.ezai.yaml`](../examples/hgx/hgx.ezai.yaml)). It sets the BMC
host name / FQDN, static DNS servers, NTP servers (with NTP enabled), and the
time-zone offset, each switchable under `bmc_settings.configure`.

```bash
python3 automation/scripts/configure_hgx_bmc.py --vars hgx.ezai.yaml            # report differences only
python3 automation/scripts/configure_hgx_bmc.py --vars hgx.ezai.yaml --apply    # patch, then verify
```

Passwords are read from the environment variable named by `password_ref`
(default `HGX_BMC_PASSWORD`). In the web UI (**Compute > HGX Servers**) the
file is pre-filled from Initial Inventory shared services and the HGX rows on
Claim Targets, and the HGX BMC password is entered on the HGX Servers page
(the C880A cannot be claimed, so it does not depend on Claim Targets). The same
password is used to claim C845A nodes and to collect MACs over Redfish.

## Intersight-claim prerequisites

- Both CIMC/Device Console endpoints of a `domain` target must be reachable.
- Device Connector must be enabled. The role reconciles the UCS-X Direct
  connector DNS and NTP lists to the canonical site values, waits through the
  connector restart, and requires `Connected` before claim. Proxy settings
  (when required) and outbound access remain site prerequisites.
- Canonical UCS DNS/NTP values live once in
  `inventories/<environment>/group_vars/all.yml` under
  `aipod`. For UCS-X Direct, every canonical server must be
  present and the connector must report `Connected`; additional
  platform-provided entries can remain because the Device Connector API does
  not consistently remove them. The claim role only validates those values
  read-only on supported standalone Redfish controllers. It does not change
  CIMC, Cisco BMC 4.0, or Device Console IP addressing, subnet masks, gateways,
  VLANs, or proxy settings.
- The Intersight account/resource group must already exist; the API key pair
  and every endpoint password belong only in the gitignored vault.
- Device ID and Claim Code are discovered at run time and are never inventory
  inputs.
- UCS-X Direct and C845 use their embedded Device Connector claim paths.
  UCS C880 does not support Intersight claim or reclaim. Every C880 host must
  set `ucs.intersight_claim_supported: false` and omit `ucs.claim_target` in
  host_vars. C880 nodes remain in the workload ownership group. The normal
  and explicit reclaim paths exclude these hosts before credential validation
  or connector access and report
  `outcome: not_supported` in `ucs_intersight_skipped_targets` and the operator
  console. These results can be displayed by the frontend; they do not imply
  a successful claim. C880 BMC and firmware operations remain available.

For an excluded node, `ucs_intersight_target_filter` uses the inventory host
handle; supported nodes continue to use `ucs.claim_target`. For example,
selecting a C880 host reports `Not supported on UCS C880.` without needing an
Intersight API key or a BMC password. The shared `intersight_*` site settings
remain required for supported claim targets.

Normal claim/verify: `automation/playbooks/06_workload_nodes_ucs.yml`.
Explicit test/recovery reclaim requires the separate
`automation/playbooks/reclaim_workload_nodes_intersight.yml` entrypoint and
`-e ucs_intersight_allow_reclaim=true`.
