# Cisco Intersight and UCS Configuration

## Overview

This document describes how to configure Cisco Intersight policies, pools, and profiles for Cisco UCS environment automation. The Intersight provisioning roles orchestrate policy creation, resource pool management, and server profile deployment.

## Quick Start

1. Edit your Intersight configuration in `host_vars/intersight/`:

```bash
vi host_vars/intersight/intersight.ezai.yaml
```

2. Provide the deployment vault password file. The vault supplies the environment
	 variables to the Python library while it runs:

```bash
python3 scripts/deploy_ai_pod.py --role intersight
```

3. Run Intersight provisioning (optional):

```bash
python3 scripts/deploy_ai_pod.py --role intersight
```

Or run the full Cisco AI PODs workflow (all domains):

```bash
python3 scripts/deploy_ai_pod.py
```

## Variable Layout

The examples (and the WebUI, which saves to the same paths under `host_vars/intersight/`) are split by page, because
pools and many policies differ between UCS domains and servers:

| Folder | WebUI page | Contents |
|--------|------------|----------|
| `system/system.ezai.yaml` | System (Orgs) | Organizations and resource groups (saved as `host_vars/intersight/system.ezai.yaml`), deployed from this page only |
| `domains/` | UCS Domains | `policies.ezai.yaml` (every domain and chassis policy in one file; remove the ones you do not need), `pools.ezai.yaml` (the Inband / OoBand IP pools the Chassis IMC Access policy uses), templates, and profiles |
| `servers/x-series/` | UCS Servers | X-Series pools and policies, optional Fibre Channel pools / policies / SAN connectivity, server templates, and blade server profiles |
| `servers/standalone/` | UCS Servers | Standalone C-Series policies, templates, and profiles |
| `C885A/` | (none) | C885A policies and profiles; not part of a WebUI page |

Claim Targets claims every target into the `default` organization and resource group. The built-in `default` resource
group always holds every target and is not changed; to separate servers, list them under another resource group in
`system.ezai.yaml` and point an organization at it.

System (Orgs) accepts a standalone `intersight.system` configuration; it does not require
`intersight.configure` or any domain/server pools, policies, templates, or profiles.
Resource groups are processed before organizations so organization references can resolve.

Profiles with `action: Deploy` and an attached template synchronize after successful deployment.
Server and domain profiles use the Intersight template Sync action; domain synchronization includes
the parent and both A/B switch profiles. Chassis profiles use the existing template-policy inheritance
mechanism: verification checks that template policies are present, preserving additional profile policies.
Profiles copied from templates with `attach_template: false` are not synchronized.
If synchronization changes a profile, automation redeploys it once and verifies template synchronization
again. Failed deployments, failed syncs, and timeouts stop the run; persistent drift after redeployment
is reported instead of starting an unbounded sync/deploy loop. Check mode submits neither sync nor deployment.
Redeployment applies template changes to hardware and can require server activation or reboot;
run it during a suitable maintenance window.

An associated server profile with `ConfigStateSummary: Inconsistent` whose only
`InconsistencyReason` is `Not-activated` has changes awaiting activation, not a failed
deployment. Automation activates those changes and waits for the activation workflow
before synchronizing templates. A rerun resumes activation without redeploying if
there are no further configuration changes. Other inconsistencies and failure states
still stop the run. Activation can reboot the server.

### API debug logging

On **System (Orgs)**, **UCS Domains**, and **UCS Servers**, use
**Intersight troubleshooting > API debug level** before **Validate** or **Deploy**.
The selection is saved per page and environment; the default is **0 - Off**.
Select **7 - Full API debug** for the equivalent of `-dl 7`. Output appears in
the normal run log and its downloads:

| Level | Output |
|-------|--------|
| 0 | Normal progress only |
| 1 | API response status |
| 5 | Status and request URLs |
| 6 | Above, plus response headers and request payloads |
| 7 | Above, plus JSON response bodies |

Known vault secrets are redacted from GUI job logs, but API payloads and responses
can contain other sensitive configuration. Review logs before sharing and return
the level to **0** after troubleshooting. Debug logging does not change deployment
actions or enable check mode.

The deployment wrapper accepts the same setting, including with scoped/selected files:

```bash
python3 scripts/deploy_ai_pod.py --role intersight --intersight-scope servers -dl 7
```

Automatic tags identify the managing automation with `managed-by: cisco-ai-pods` and
`release: <VERSION>`, for example `v0.1.5`. The release is read from the repository's VERSION
file at runtime and describes the last-applied software release, not the resource's creation version.
These replace the legacy script-name/version tags when resources are reconciled.
Explicit YAML and global tags remain supported; `intersight.global_settings.include_script_tags: false`
disables automatic tags. The bundled schema's `x-schema-version` is also generated from VERSION.

Claim Targets requires at least 8 characters for Fabric Interconnect and CIMC passwords, including target overrides.
The GUI shows the [Cisco UCS password guidelines](https://www.cisco.com/c/en/us/td/docs/unified_computing/ucs/ucs-manager/GUI-User-Guides/Admin-Management/4-1/b_Cisco_UCS_Admin_Mgmt_Guide_4-1/m_password_management.html):
8-80 characters, at least three character classes (lowercase, uppercase, digits, special characters), no character
repeated more than three times consecutively, no `$`, `?`, or `=`, and no username, reversed username, or
dictionary-based passwords. The GUI checks the minimum length; the device enforces its configured strength and
dictionary checks. HGX BMC credentials retain their separate 12-character GUI minimum.

Delete the files you do not deploy (for example the Fibre Channel files or templates); in the WebUI use the delete
button on the Variables toolbar. `scripts/deploy_ai_pod.py --intersight-scope system` deploys only
the top-level Intersight files and System-tab uploads; `--intersight-scope domains|servers`
deploys only the selected folder, including its uploads. Deploy organizations from System (Orgs)
first. Domain and server deployments use existing organizations without reconciling their system files.
The CLI's default `--intersight-scope all` still deploys the complete configuration.

On the UCS Domains and UCS Servers pages, the upload button on each Variables toolbar adds your own YAML files. They are
schema-checked, saved as `<name>.ezai.yaml` under an `uploads/` folder in that page's folder (for example
`host_vars/intersight/servers/x-series/uploads/`), listed as `uploads/<name>` in the file menu, and merged with the
page's other files when it deploys. The delete button removes an uploaded file.

On UCS Domains and UCS Servers, **Deploy to Intersight** and **Validate (check mode)**
open a file picker with all saved page files selected by default, including uploads.
Choose only templates or profiles to resume after pools and policies have succeeded.
The action uses saved disk contents; save editor changes before opening the picker.
At least one file is required. Only selected files are validated and loaded, including
their referenced secrets. Unselected resources are not created or updated, so any
dependencies they supply must already exist in Intersight. Resource dependency order
is preserved regardless of the file selection order.

The CLI supports the same selection using repeatable paths relative to `host_vars/intersight`:

```bash
python3 scripts/deploy_ai_pod.py --role intersight --intersight-scope domains \
  --intersight-file domains/templates.ezai.yaml \
  --intersight-file domains/profiles.ezai.yaml
```

Omit `--intersight-file` to deploy all files in the selected scope. The selection is
per run and does not delete or change any variable files. System (Orgs) keeps its
existing whole-page deployment behavior.

### PCIe connectivity

For FI-attached UCS X-Series servers, add `pcie_connectivity` to an organization's
`policies` configuration. Policies use `compute/PcieConnectivityPolicies`.

```yaml
pcie_connectivity:
  - name: PCIe-GPU
    gpu_model: UCSC-GPU-L40S
    mappings:
      - cpu_id: 1
      - cpu_id: 2
  - name: PCIe-GPU-SmartNIC
    gpu_model: UCSC-GPU-L40S
    mappings:
      - cpu_id: 1
        gpu_quantity: 1
        smart_nic: UCSC-P-N7S400GF
      - cpu_id: 2
        gpu_quantity: 1
        smart_nic: UCSC-P-N7D200GF
  - name: PCIe-Any
    mappings:
      - cpu_id: any
```

`name` and one or two `mappings` are required. Each mapping requires `cpu_id`:
lowercase `any`, or the YAML integer `1` or `2`. These render as API CPU IDs
`Any`, `"1"`, and `"2"`. `gpu_model` defaults to `Any`; each mapping's
`gpu_quantity` defaults to `1` and accepts only `1` or `2`.
Replace the previous `cpus` mapping key with `cpu_id` in existing variable files;
the schema no longer accepts `cpus`.

GPU models are `Any`, `UCSC-GPU-H100-NVL`, `UCSC-GPU-H200-NVL`, `UCSC-GPU-L40S`,
`UCSC-GPU-RTXP6000`, and `UCSC-GPU-RTXP4500`. Optional `smart_nic` choices are
`Any`, `UCSC-P-N7S400GF`, `UCSC-P-N7D200GF`, `UCSC-P-N7S400GFO`, and `UCSC-P-N7D200GFO`.
Omitting `smart_nic` emits no adapter endpoint; setting it selects one adapter.
`description` and standard `tags` are optional. Reference the policy from an
FI-attached server profile or template with `pcie_connectivity_policy: PCIe-GPU`.
Normal policy name prefixes/suffixes and shared-organization references apply.

See Cisco's [PCIe connectivity policy documentation](https://intersight.com/help/saas/resources/server_policies#pcie_connectivity_policy).

### Domain uplink connectivity

The UCS Domains post-check **Validate domain uplink connectivity** replaces server MAC collection
(which remains on UCS Servers). It uses the saved domain profiles' `serial_numbers` to find each
Fabric Interconnect, then reads its assigned switch profile and port policy from Intersight.
It checks every Ethernet, FCoE, and FC uplink, including port-channel members and breakout ports.
Missing ports, down/unknown link states, missing assignments, and API errors fail the check.
This is a read-only post-deployment check of the assigned policy, not a comparison against
unapplied local port-policy edits.

For Ethernet/FCoE ports, the console includes CDP/LLDP neighbor device, remote port, and management
address when Intersight reports them. No neighbor data is explicitly reported as unavailable:
an up link alone does not prove connection to the intended physical switch. FC ports have no
CDP/LLDP check. Intersight inventory may lag physical changes.

For profiles attached to a domain template, provisioning creates/updates the cluster and both
A/B switch profiles, then merges the corresponding templates using `bulk/MoMergers`.
Before `action: Deploy` runs, it reads back the template relationships and inherited policy
references (including System QoS when configured on the switch template). Missing inheritance
stops deployment with an explicit error. A profiles-only retry also repairs profiles that have
a template reference but no inherited policies; it does not require recreating pools or policies.
`attach_template: false` retains its copy-without-binding behavior, and check mode does not
submit template merges.

```bash
python3 05-mgmt-nodes-ucs/automation/scripts/check_intersight_domain_ports.py \
  --domains-dir host_vars/intersight/domains
```

The command uses the same `intersight_api_key_id`, `intersight_secret_key`, and optional
`intersight_fqdn` environment variables as the existing Intersight MAC collector.

### Automation logs

The Automation panel retains the latest 25 completed runs per page, not 90 days.
When another run completes, logs beyond that count are deleted. Download logs before
they roll out of history; expired logs cannot be recovered through the UI.

Use the single-log download icon for the displayed run, **Page logs** for a ZIP of
all retained logs on that page, or **Environment logs** for a ZIP across all pages
of the current environment. ZIPs contain the already-redacted log files, grouped
by page; they do not include vault files or job metadata. Active runs are included
as snapshots and may not yet contain their final output. Download errors are shown
in the UI. Retention is unchanged by downloading.

Policy passwords and secrets are under Passwords and secrets on both pages: check each policy the YAML uses and set how
many values it references (SNMP has a count per value, for example three `snmp_user_auth_password` entries referenced
as `auth_password: 1`, `2`, `3`). Checking Certificate Management adds an upload for PEM certificate and key files; they
are saved (mode 0600) under `<environment>/certificates/intersight/`, and a dialog shows the absolute path to use as
each certificate's `certificate_file` / `private_key_file`.

## Folder Contents

- `playbooks/deploy_ai_pod_phase1.yaml`: Full-stack entry point playbook (Intersight runs through `scripts/deploy_ai_pod.py`)
- `host_vars/intersight/`: Active Intersight configuration variables
- `roles/intersight_pools/tasks/`: Policies for MAC, UUID, and IP pools
- `roles/intersight_policies/tasks/`: BIOS, boot, network, and storage policy configurations
- `roles/intersight_profiles/tasks/`: Server profile templates and deployment profiles
- `docs/intersight_policy_templates/`: Reference documentation for BIOS, Ethernet, Fibre Channel, and Storage policy templates
- `docs/intersight_prefix_suffix.md`: Name prefix and suffix decoration guidance

## Configuration Structure

Intersight configuration is organized by organization, and resources are deployed with optional name prefix/suffix decoration. See [intersight_prefix_suffix.md](intersight_prefix_suffix.md) for details on applying name decoration to pools, policies, profiles, and templates.

## Related Documentation

- [Policy Templates Reference](intersight_policy_templates/): BIOS, Ethernet adapter, Fibre Channel adapter, and storage policy templates
- [Name Prefix and Suffix Support](intersight_prefix_suffix.md)
