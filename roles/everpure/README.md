# Everpure Role

Configures Pure Storage FlashArray and FlashBlade settings for Cisco AI PODs.

Main guide: [docs/everpure.md](../../docs/everpure.md)

## Purpose

This role applies Day 0/Day 1 storage configuration across one or more arrays and blades based on values in `host_vars/everpure/everpure.ezai.yaml`.

## Inputs

- Variables file: `host_vars/everpure/everpure.ezai.yaml`
- Environment variables:
  - `pure_api_token_<id>` for each `api_token_id` in the variables file

## Role Structure

- `tasks/main.yaml`: Role entry point and flow control
- `tasks/flash_array/`: FlashArray workflows (network, security, system)
- `tasks/flash_blade/`: FlashBlade workflows (network, security, system, notifications)
- `templates/pure.json.j2`: Portworx credential file template generated from Everpure data

## What It Configures

Based on provided inputs:

- FlashArray network settings
- FlashArray access/security settings
- FlashArray system settings
- FlashBlade network settings
- FlashBlade security settings
- FlashBlade system settings
- FlashBlade notifications (if configured)

## Run

Run only Everpure:

```bash
python3 scripts/deploy_ai_pod.py --role everpure \
  --vault-password-file ~/.config/cisco-ai-pods/vault-password
```

Run with Portworx (OpenShift installation must be complete first):

```bash
python3 scripts/deploy_ai_pod.py --role everpure \
  --vault-password-file ~/.config/cisco-ai-pods/vault-password
ansible-playbook playbooks/deploy_storage.yaml --tags portworx
```

## Idempotency

Safe to re-run. The role reconciles desired state from current inputs.

## Troubleshooting

- Authentication failures:
  - Confirm `pure_api_token_<id>` names match configured `api_token_id` values.
- Unexpected task skips:
  - Verify keys under `everpure.settings.*` and array/blade objects are present.
- Input validation issues:
  - Open `host_vars/everpure/everpure.ezai.yaml` in VS Code and resolve Red Hat YAML extension errors.

Environment prep and schema setup:
- [docs/guide_prepare_the_environment.md](../../docs/guide_prepare_the_environment.md)
- [YAML schema validation section](../../docs/guide_prepare_the_environment.md#yaml-schema-for-auto-completion-help-and-error-validation)
