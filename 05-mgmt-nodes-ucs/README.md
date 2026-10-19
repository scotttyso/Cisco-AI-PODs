# Subsystem 05 - UCS management nodes

Provisions UCS systems assigned to the OpenShift management tier. Management nodes can use either the `domain` or `standalone` UCS platform. Subsystem 07 assigns the OpenShift `control` or `compact` role.

Scope is hardware-level only: UCS domain Device Console or CIMC access, Intersight claim, server profiles, firmware policies, BIOS and boot configuration, and fabric attachment. The OpenShift install itself lives in Subsystem 07.

Provisioning interface (IMM / Redfish / Intersight-claimed) lives inside the schema as a discriminated field, not as a separate subsystem (D13/N2).

Schema: [`schemas/mgmt-nodes-ucs.schema.json`](../schemas/mgmt-nodes-ucs.schema.json).

## Intersight-claim prerequisites

- Both CIMC/Device Console endpoints of a `domain` target must be reachable.
- Device Connector must be enabled on every endpoint. The role reconciles the
  UCS-X Direct connector DNS and NTP lists to the canonical site values, waits
  through the connector restart, and requires `Connected` before claim. Proxy
  settings (when required) and outbound access to Intersight remain site
  prerequisites.
- Canonical UCS DNS/NTP values live once in
  `inventories/<environment>/group_vars/all.yml` under
  `aipod`. For UCS-X Direct, every canonical server must be
  present and the connector must report `Connected`; additional
  platform-provided entries can remain because the Device Connector API does
  not consistently remove them. The claim role only validates those values
  read-only on supported standalone Redfish controllers. It does not change
  CIMC or Device Console IP addressing, subnet masks, gateways, VLANs, or proxy
  settings.
- The Intersight account and resource group named in canonical site inventory
  must already exist. The API key pair belongs only in the gitignored vault.
- Per-endpoint credentials belong in the vault keys referenced by `cimc.pass_ref`.
- Device ID, Claim Code, serials, model, and registration identity are
  discovered at run time and must not be copied into inventory.
- A target already claimed by another account is rejected. Moving it requires
  explicit ownership resolution; the normal play never transfers ownership.

Normal claim/verify: `automation/playbooks/05_mgmt_nodes_ucs.yml`.
Explicit test/recovery reclaim requires the separate
`automation/playbooks/reclaim_mgmt_nodes_intersight.yml` entrypoint and
`-e ucs_intersight_allow_reclaim=true`.
