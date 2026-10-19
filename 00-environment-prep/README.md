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
   In the WebUI, drag rows using the handle beside the hostname to arrange imported or
   manually added nodes (clear sorting and filters before dragging). Check the rows to
   update, enter a starting hostname and/or IP address, optionally choose a Role, and
   select **Apply to checked rows**. Hostnames increment the last number in the first DNS
   label, preserving zero padding (`node09` becomes `node10`); IP addresses increment by
   one. Assignment follows the checked rows' displayed order, top to bottom. Blank inputs
   leave fields unchanged; supplied values overwrite existing ones. Clear filters if any
   checked rows are hidden. Bulk edits reject invalid values without partially applying changes.
   Temporary duplicate hostnames/IPs are allowed while editing; **Validate** and **Save** report
   duplicates until you resolve them, and persist the edits and row order only when valid.
   **Pool IP** leaves the address blank and excludes the device from DHCP reservations
   (for example, UCS X-Series compute nodes using an Intersight IP pool). Imported
   X-Series compute nodes default to Pool IP. Toggle the per-row checkbox or use the
   bulk **IP assignment** selector to change it. Pool IP rows can receive bulk hostnames
   and roles but do not consume an IP sequence number. Selecting manual addressing
   again requires entering an IP before saving. This flag does not create the
   Intersight pool; configure the pool in the Intersight policies and profiles.
   C880A and C885A models are detected as **UCS HGX node (C880A / C885A)**; C845A
   models use **UCS C-Series standalone server**. Explicitly saved role choices are
   preserved; change any previously assigned C845A HGX roles to standalone and Save.
   Standalone Intersight profiles are grouped by server family: C845A uses
   `target_platform: Standalone` and `server_family: UCSC845A`, while ordinary C-Series
   uses `UCSC2XX/4XX`. Both C880A and C885A stay in the separate HGX Servers workflow
   and are excluded from Intersight claiming, registration inventory, and generated profiles.
   New model-specific groups default to `No-op` without attaching the generic C-Series
   template. Configure their policies or a matching template before deployment;
   existing group settings are preserved.
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

   For Nexus switch POAP with external DHCP (the fabric page default), set **POAP / TFTP
   server** (option 66) to the Nexus Dashboard address and **Boot file** (option 67) to
   `poap_dcnm.py`. Switches without a MAC address in the inventory are not served while
   **Only serve inventory devices** is on.
3. **ISO library.** Upload installation media served by the deployment server.
