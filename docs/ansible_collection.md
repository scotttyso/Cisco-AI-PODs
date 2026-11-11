# Cisco AI PODs Docs Index and Collection Setup

This document captures the minimum setup required to run Ansible collection sanity checks and complete the collection/module workflow for this repository.

## Why this matters

Ansible sanity tooling expects collection repositories to be located in collection layout directories.

Expected layout:

- ansible_collections/<namespace>/<collection>

For this project, from galaxy.yml:

- namespace: cisco
- name: aipod

So the repository path should be:

- ansible_collections/cisco/aipod

## Current repository mapping

If your repository is currently at:

- ~/src/Cisco-AI-PODs

ansible-test sanity will fail collection-layout checks because it is not under ansible_collections/cisco/aipod.

## Setup options

### Option 1: Move the repository (recommended)

    mkdir -p ~/scotttyso/ansible_collections/cisco
    mv ~/scotttyso/Cisco-AI-PODs ~/scotttyso/ansible_collections/cisco/aipod
    cd ~/scotttyso/ansible_collections/cisco/aipod

### Option 2: Keep the current checkout and create an isolated worktree

    mkdir -p ~/scotttyso/ansible_collections/cisco
    git -C ~/scotttyso/Cisco-AI-PODs worktree add --detach ~/scotttyso/ansible_collections/cisco/aipod HEAD
    cd ~/scotttyso/ansible_collections/cisco/aipod

The worktree contains committed changes only. Commit fixes before creating it, or use a physical source copy when
validating uncommitted changes. Do not use a directory symlink: delegated tests resolve its real path and can reject
the collection layout.

## Verify layout before running tests

    pwd -P

The output should end with:

- ansible_collections/cisco/aipod

## Run sanity checks

    ansible-test sanity --test ignores
    ansible-test sanity

## Notes on Helm template ignores

- Do not add yamllint skip rules to tests/sanity/ignore files.
- Sanity rejects those with cannot-ignore errors.
- Helm template exclusions should be configured in .yamllint ignore paths.
- Ansible sanity does not read `.yamllint`; its specific unrendered Helm syntax exceptions are documented in
  [tests/sanity/README.md](../tests/sanity/README.md).

Standalone Python entry points use `#!/usr/bin/env python`; activate the repository virtual environment before
executing them directly (or invoke them with that environment's Python). The privileged appliance helpers retain
their fixed `/usr/bin/python3` interpreter.

## Shared Python helpers

Collection filters import helpers from `ansible_collections.cisco.aipod.plugins.module_utils.shared.lib`.
The canonical sources live in `plugins/module_utils/shared/lib/`; the repository's `shared/__init__.py` preserves
existing `shared.lib` imports for standalone scripts. The collection builder copies the canonical helpers and
the Nexus Dashboard inventory schema into the assembled collection.

The unrelated retained `shared/lib/build_py.py` artifact is not an automation helper and is not copied by the builder.
The helper modules retain legacy future-import and metaclass boilerplate for Ansible 2.16 sanity compatibility,
alongside postponed annotations for the supported Python runtimes.

## Related docs

- docs/guide_prepare_the_environment.md
- docs/guide_cisco_ai_pods_runbook.md
- docs/guide_troubleshooting.md
- docs/intersight.md
- docs/openshift.md
- docs/everpure.md
- docs/splunk_observability.md
