# Cisco AI Pods Repository Guide

This repository contains automation and runbooks for Cisco AI Pods infrastructure across Intersight, storage, OpenShift, and observability workflows.

## Table of Contents

- [Cisco AI Pods Repository Guide](#cisco-ai-pods-repository-guide)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
  - [Primary Workstreams](#primary-workstreams)
  - [Repository Layout](#repository-layout)
  - [Runbook Documents](#runbook-documents)
  - [Environment Preparation](#environment-preparation)
  - [Quick Start Workflow](#quick-start-workflow)
    - [1. Prepare Environment](#1-prepare-environment)
    - [2. Deploy Full Stack (All Domains)](#2-deploy-full-stack-all-domains)
    - [3. Deploy Specific Domains (Optional)](#3-deploy-specific-domains-optional)
  - [Common Commands](#common-commands)
  - [Troubleshooting and Operations](#troubleshooting-and-operations)
  - [Architecture](#architecture)
  - [Support and Contribution](#support-and-contribution)

## Overview

The repository provides centralized Ansible-based automation for complete Cisco AI Pods infrastructure deployment across:

- **Intersight and UCS** - Policy provisioning, resource pool management, and server profile deployment
- **Everpure Storage** - FlashArray and FlashBlade configuration with Portworx Enterprise integration
- **Red Hat OpenShift** - Cluster installation, authentication, certificates, GitOps, and ArgoCD
- **Splunk Observability** - Full-stack visibility and monitoring integration

All workflows use centralized playbooks in `playbooks/` with tag-based conditional execution and variable auto-loading from `host_vars/`.

## Primary Workstreams

All workflows execute through centralized Ansible playbooks from the repository root:

1. **Full Stack Deployment** (`playbooks/deploy_ai_pod.yaml`)
   - Orchestrates all domains in deployment order
   - Automatically loads variables from `host_vars/` subdirectories
   - Supports `--tags` for selective execution

2. **Intersight and UCS** (`playbooks/deploy_ai_pod.yaml --tags intersight`)
   - Guide: [docs/intersight.md](docs/intersight.md)
   - Includes policy, pool, and profile provisioning

3. **Everpure Storage and Portworx** (`playbooks/deploy_ai_pod.yaml --tags everpure,portworx`)
   - Guide: [docs/everpure.md](docs/everpure.md)
  - Role details: [roles/everpure/README.md](roles/everpure/README.md)
  - Role details: [roles/portworx_enterprise/README.md](roles/portworx_enterprise/README.md)

4. **OpenShift Platform** (`playbooks/deploy_openshift.yaml` or `playbooks/deploy_ai_pod.yaml --tags openshift`)
   - Guide: [docs/openshift.md](docs/openshift.md)
   - Includes authentication, certificates, GitOps, and ArgoCD

5. **Splunk Observability** (`playbooks/deploy_ai_pod.yaml --tags observability`)
   - Guide: [docs/splunk_observability.md](docs/splunk_observability.md)
  - Role details: [roles/splunk_observability/README.md](roles/splunk_observability/README.md)
   - Full-stack monitoring and observability integration

6. **Testing** (standalone, outside the Ansible playbooks)
   - Guide: [docs/tests.md](docs/tests.md)
   - Standalone validation tests for the OpenShift cluster (e.g. GPU metrics, backend networking) under [tests/](tests/), each with its own README and setup script

## Repository Layout

Top-level structure:

```text
Cisco-AI-Pods/
  docs/                          # All documentation
    intersight.md
    openshift.md
    everpure.md
    splunk_observability.md
    tests.md
    guide_cisco_ai_pods_runbook.md
    guide_prepare_the_environment.md
    guide_troubleshooting.md
  tests/                         # Standalone OpenShift cluster validation tests
    nvidia-metrics-non-admin/
  playbooks/                     # Centralized Ansible playbooks
    deploy_ai_pod.yaml           # Full stack orchestration
    deploy_openshift.yaml        # OpenShift only
    deploy_storage.yaml          # Storage/Portworx only
    deploy_intersight_ucs.yaml   # Intersight only
    deploy_observability.yaml    # Splunk Observability only
  roles/                         # Ansible roles
    intersight_*/
    openshift_*/
    everpure/
    portworx_enterprise/
    splunk_observability/
  host_vars/                     # Environment variables (auto-loaded)
    everpure/
    intersight/
    openshift/
    splunk_observability/
  examples/                      # Example variable templates
  schema/                        # YAML schema for validation
  requirements.txt               # Python dependencies
  requirements.yaml              # Ansible collection dependencies
```

## Runbook Documents

All documentation is in the `docs/` folder:

- **Start here:** [docs/guide_prepare_the_environment.md](docs/guide_prepare_the_environment.md) — Install dependencies and prepare your environment
- **Main runbook:** [docs/guide_cisco_ai_pods_runbook.md](docs/guide_cisco_ai_pods_runbook.md) — Complete deployment workflow and playbook usage
- **Troubleshooting:** [docs/guide_troubleshooting.md](docs/guide_troubleshooting.md) — Cross-component triage and solutions
- **Domain-specific guides:**
  - [docs/intersight.md](docs/intersight.md) — Intersight/UCS provisioning
  - [docs/openshift.md](docs/openshift.md) — OpenShift deployment
  - [docs/everpure.md](docs/everpure.md) — Storage configuration
  - [docs/splunk_observability.md](docs/splunk_observability.md) — Observability integration
  - [docs/tests.md](docs/tests.md) — Standalone OpenShift cluster validation tests

## Environment Preparation

Run the automated setup script from the repository root:

```bash
./scripts/setup.sh
```

This script will:
- Install Git and Python prerequisites (auto-detects apt/dnf/yum)
- Create a Python virtual environment
- Install Ansible, Python dependencies, and Ansible collections
- Download and extract the latest iServer release for OpenShift

For detailed setup instructions and optional flags, see [docs/guide_prepare_the_environment.md](docs/guide_prepare_the_environment.md).

## Quick Start Workflow

### 1. Prepare Environment and Download iServer

From the repository root:

```bash
./scripts/setup.sh --git-name "Your Name" --git-email "your@email.com"
```

Activate the virtual environment:

```bash
source .venv/bin/activate
```

Then follow the iServer setup instructions: [https://github.com/datacenter/iserver/blob/main/doc/ocp/Console.md](https://github.com/datacenter/iserver/blob/main/doc/ocp/Console.md)

### 2. Prepare Deployment Variables

Copy example variables to `host_vars/` and customize for your environment:

```bash
mkdir -p host_vars
cp -r examples/intersight host_vars/
cp -r examples/openshift host_vars/
cp -r examples/everpure host_vars/
cp -r examples/splunk_observability host_vars/
```

### 3. Deploy Full Stack (All Domains)

```bash
ansible-playbook playbooks/deploy_ai_pod.yaml
```

Custom `host_vars` location:

```bash
ansible-playbook playbooks/deploy_ai_pod.yaml -e host_vars_dir=/some/custom/path
```

### 4. Deploy Specific Domains (Optional)

**Intersight and UCS only:**
```bash
ansible-playbook playbooks/deploy_ai_pod.yaml --tags intersight
```

**Storage and Portworx only:**
```bash
ansible-playbook playbooks/deploy_ai_pod.yaml --tags everpure,portworx
```

**OpenShift only:**
```bash
ansible-playbook playbooks/deploy_openshift.yaml
```

**Splunk Observability only:**
```bash
ansible-playbook playbooks/deploy_ai_pod.yaml --tags observability
```

For detailed procedures, see [docs/guide_cisco_ai_pods_runbook.md](docs/guide_cisco_ai_pods_runbook.md).

## Common Commands

Run playbook in dry-run mode (check mode):

```bash
ansible-playbook playbooks/deploy_ai_pod.yaml --check
```

Run with verbose output for debugging:

```bash
ansible-playbook playbooks/deploy_ai_pod.yaml -vvv
```

List all available tags:

```bash
ansible-playbook playbooks/deploy_ai_pod.yaml --list-tags
```

Run a specific role or tag:

```bash
ansible-playbook playbooks/deploy_ai_pod.yaml --tags certificates
```

## Troubleshooting and Operations

- **Cross-component triage:** [docs/guide_troubleshooting.md](docs/guide_troubleshooting.md)
- **Domain-specific issues:**
  - Intersight: [docs/intersight.md](docs/intersight.md)
  - OpenShift: [docs/openshift.md](docs/openshift.md)
  - Storage: [docs/everpure.md](docs/everpure.md)
  - Observability: [docs/splunk_observability.md](docs/splunk_observability.md)
- **Cluster validation tests:** [docs/tests.md](docs/tests.md)
- Keep `host_vars/` configurations and documentation synchronized as environments evolve
- Variables are auto-loaded from `host_vars/` subdirectories at runtime — no manual file copying needed

## Architecture

The repository uses a centralized Ansible architecture:

- **Playbooks** (`playbooks/deploy_*.yaml`) — Orchestrate roles in dependency order
- **Roles** (`roles/*/`) — Task implementations for each domain
- **Variables** (`host_vars/<domain>/`) — Environment-specific configuration auto-loaded at runtime
- **Tags** — Control which roles execute via `--tags` flag
- **Examples** (`examples/`) — Template variable files for reference
- **Schema** (`schema/`) — YAML validation for configuration files

For detailed architecture information, see [docs/guide_cisco_ai_pods_runbook.md](docs/guide_cisco_ai_pods_runbook.md).

## Support and Contribution

For issues, feature requests, or contributions, please use the GitHub repository issue tracker.

For detailed deployment procedures, consult the documentation in `docs/`.