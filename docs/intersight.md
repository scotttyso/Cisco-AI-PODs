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
| `system/system.ezai.yaml` | System (Orgs) | Organizations and resource groups (saved as `host_vars/intersight/system.ezai.yaml`), used by every deployment |
| `domains/` | UCS Domains | `policies.ezai.yaml` (every domain and chassis policy in one file; remove the ones you do not need), `pools.ezai.yaml` (the Inband / OoBand IP pools the Chassis IMC Access policy uses), templates, and profiles |
| `servers/x-series/` | UCS Servers | X-Series pools and policies, optional Fibre Channel pools / policies / SAN connectivity, server templates, and blade server profiles |
| `servers/standalone/` | UCS Servers | Standalone C-Series policies, templates, and profiles |
| `C885A/` | (none) | C885A policies and profiles; not part of a WebUI page |

Claim Targets claims every target into the `default` organization and resource group. The built-in `default` resource
group always holds every target and is not changed; to separate servers, list them under another resource group in
`system.ezai.yaml` and point an organization at it.

Delete the files you do not deploy (for example the Fibre Channel files or templates); in the WebUI use the delete
button on the Variables toolbar. `scripts/deploy_ai_pod.py --intersight-scope system` deploys only
`system.ezai.yaml`; `--intersight-scope domains|servers` deploys `system.ezai.yaml` plus one folder. Files from different folders are merged, and identical policy entries that
appear in both folders are kept once.

On the UCS Domains and UCS Servers pages, the upload button on each Variables toolbar adds your own YAML files. They are
schema-checked, saved as `<name>.ezai.yaml` under an `uploads/` folder in that page's folder (for example
`host_vars/intersight/servers/x-series/uploads/`), listed as `uploads/<name>` in the file menu, and merged with the
page's other files when it deploys. The delete button removes an uploaded file.

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
