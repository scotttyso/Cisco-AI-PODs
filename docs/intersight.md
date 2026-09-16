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
