# 00 — Environment prep

Not a Deployment Guide chapter. This is the work that has to exist before
subsystem 01: operator workstation, MAC/DHCP, management-switch reachability,
and inventory validation helpers.

| Path | Purpose |
|---|---|
| `docs/` | Notes and checklists for env prep (not a CVD chapter) |
| `automation/playbooks/` | `00_environment_prep.yml` and `deploy_dhcp_server.yml` (Kea DHCPv4 bootstrap) |
| `automation/roles/dhcp_server/` | Kea DHCPv4 role for CIMC, management, and Nexus POAP addressing |
| `automation/scripts/` | `build_initial_inventory.py` — order spreadsheets + shared services to `initial_inventory` |
| `automation/examples/` | Example `dhcp` data model |
| `lab/` | Cisco-lab-only fixtures, only if they appear |

Canonical site inventory lives under `inventories/<environment>/`. It is
shared by every subsystem; subsystems do not maintain local inventories.

## Workflow

1. **Initial inventory.** In the Automation UI (*Environment Preparation → Initial
   Inventory*), or with `automation/scripts/build_initial_inventory.py`, import the order
   spreadsheets, assign hostnames and bootstrap addresses, and confirm the shared services
   (DNS, domain, search domains, NTP, timezone, proxy). Host defaults are detected from the
   deployment server; only overrides are saved. Shared services are validated against
   `schemas/source/cisco-ai-pods.json#/definitions/shared_services` and reused by later stages.
2. **DHCP bootstrap.** Generate the `dhcp` data model from the inventory
   (*Environment Preparation → DHCP Bootstrap*). **Render and validate** writes the Kea files
   only. **Install and start Kea** requires `dhcp.interfaces` to list interfaces
   that exist on this host (`*` is refused; with a DHCP relay, select the interface
   facing the relay). The UI asks for the local sudo password only when sudo needs
   one; it is used for that job only, never saved, and redacted from logs. From a
   shell:

   ```bash
   ansible-playbook 00-environment-prep/automation/playbooks/deploy_dhcp_server.yml \
     -i <inventory> -e dhcp_hosts=localhost -e dhcp_vars_file=/path/to/dhcp.yaml -K
   ```
3. **ISO library.** Upload installation media served by the deployment server.
