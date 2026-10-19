# Everpure Role

Configures Pure Storage FlashArray and FlashBlade settings for Cisco AI PODs.

Main guide: [docs/everpure.md](../../../../docs/everpure.md)

## Purpose

This role applies Day 0/Day 1 storage configuration across one or more arrays and blades based on values in `host_vars/everpure/everpure.ezai.yaml`.

## Inputs

- Variables files: `host_vars/everpure/**/*.ezai.yaml` (`everpure.ezai.yaml` plus any files uploaded on the
  WebUI Everpure page into `uploads/`)
- Environment variables (stored in the `everpure` vault section; the YAML holds only the number):
  - `everpure_api_token_<id>` for each `api_token_id`
  - `private_key_passphrase_<id>` for an encrypted `array_certificates[].private_key_passphrase`
  - `ldap_binding_password_<id>` for `directory_service.configuration[].bind_password` (the WebUI exports the
    Shared services LDAP bind password as `ldap_binding_password_1`)
  - `local_user_password_<id>` for `settings.security.users[].password`
  - `everpure_snmp_community_<id>`, `everpure_snmp_auth_passphrase_<id>`, `everpure_snmp_privacy_passphrase_<id>`
    for the SNMP managers and agent
- Certificate files: `array_certificates[].certificate_file`, `intermediate_certificate_file`, and
  `private_key_file` are absolute paths on the automation host. The WebUI saves uploads in
  `<environment>/certificates/everpure/`.

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
  - Confirm `everpure_api_token_<id>` names match configured `api_token_id` values.
- Unexpected task skips:
  - Verify keys under `everpure.settings.*` and array/blade objects are present.
- Input validation issues:
  - Open `host_vars/everpure/everpure.ezai.yaml` in VS Code and resolve Red Hat YAML extension errors.

Environment prep and schema setup:
- [docs/guide_prepare_the_environment.md](../../../../docs/guide_prepare_the_environment.md)
- [YAML schema validation section](../../../../docs/guide_prepare_the_environment.md#yaml-schema-for-auto-completion-help-and-error-validation)
