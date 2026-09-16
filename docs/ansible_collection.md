# Cisco AI PODs Docs Index and Collection Setup

This document captures the minimum setup required to run Ansible collection sanity checks and complete the collection/module workflow for this repository.

## Why this matters

Ansible sanity tooling expects collection repositories to be located in collection layout directories.

Expected layout:

- ansible_collections/<namespace>/<collection>

For this project, from galaxy.yml:

- namespace: cisco
- name: ai_pods

So the repository path should be:

- ansible_collections/cisco/ai_pods

## Current repository mapping

If your repository is currently at:

- /home/tyscott/scotttyso/Cisco-AI-PODs

ansible-test sanity will fail collection-layout checks because it is not under ansible_collections/cisco/ai_pods.

## Setup options

### Option 1: Move the repository (recommended)

    mkdir -p ~/scotttyso/ansible_collections/cisco
    mv ~/scotttyso/Cisco-AI-PODs ~/scotttyso/ansible_collections/cisco/ai_pods
    cd ~/scotttyso/ansible_collections/cisco/ai_pods

### Option 2: Keep current path and use a symlink

    mkdir -p ~/scotttyso/ansible_collections/cisco
    ln -s ~/scotttyso/Cisco-AI-PODs ~/scotttyso/ansible_collections/cisco/ai_pods
    cd ~/scotttyso/ansible_collections/cisco/ai_pods

## Verify layout before running tests

    pwd

The output should end with:

- ansible_collections/cisco/ai_pods

## Run sanity checks

    ansible-test sanity --test ignores
    ansible-test sanity

## Notes on Helm template ignores

- Do not add yamllint skip rules to tests/sanity/ignore files.
- Sanity rejects those with cannot-ignore errors.
- Helm template exclusions should be configured in .yamllint ignore paths.

## Related docs

- docs/guide_prepare_the_environment.md
- docs/guide_cisco_ai_pods_runbook.md
- docs/guide_troubleshooting.md
- docs/intersight.md
- docs/openshift.md
- docs/everpure.md
- docs/splunk_observability.md
