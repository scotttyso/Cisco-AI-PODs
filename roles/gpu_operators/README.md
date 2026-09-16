# GPU Operators Role

Deploys and configures NVIDIA GPU-related operators for OpenShift-based Cisco AI PODs environments.

## Purpose

This role is the integration point for GPU operator deployment workflows. It is currently a migration placeholder while GitOps content is moved from the OpenShift playbook tree into role-native tasks.

## Inputs

- OpenShift API environment variables:
  - `openshift_api_url`
  - `openshift_token_id`
- Optional role variables from `defaults/main.yml`:
  - `gpu_driver_version`
  - `nfd_enabled`
  - `sriov_enabled`
  - `network_operator_enabled`
  - `dcgm_enabled`

## Run

Run the role through the main playbook:

```bash
ansible-playbook playbooks/deploy_ai_pod_phase2.yaml --tags gpu_operators
```

## Notes

The role currently emits a placeholder task while deployment logic is being migrated.