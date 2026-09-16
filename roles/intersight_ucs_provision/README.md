# Intersight UCS Provision

Provisions Cisco UCS infrastructure through Cisco Intersight for Cisco AI PODs deployments.

## Purpose

This directory holds the Python implementation that validates deployment inputs and drives UCS provisioning operations. It is no longer an Ansible role; [scripts/deploy_ai_pod.py](../../scripts/deploy_ai_pod.py) invokes the library directly so provisioning output streams live.

## Inputs

- Variables from host vars for Intersight deployment
- Environment variables and credentials required by Cisco Intersight APIs

## Structure

- `library/`: entry point (`deploy_intersight_ucs.py`), custom modules, and helpers
- `templates/`: generated data and policy templates

## Run

```bash
python3 scripts/deploy_ai_pod.py --role intersight \
  --vault-password-file ~/.config/cisco-ai-pods/vault-password
```

To call the library directly:

```bash
python3 roles/intersight_ucs_provision/library/deploy_intersight_ucs.py \
  --dir host_vars/intersight --non-interactive
```

## Troubleshooting

- Verify API key and endpoint credentials.
- Confirm required variables are present in the selected host vars.
- Review output for validation errors before retrying.