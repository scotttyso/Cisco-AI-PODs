# Splunk Observability Role

Deploys and configures Splunk Observability components for Cisco AI PODs, including OpenTelemetry collector resources and optional integrations (Intersight, Nexus, GPU metrics, and related templates).

Main guide: [docs/splunk_observability.md](../../docs/splunk_observability.md)

## Purpose

This role renders observability configuration from `host_vars/splunk_observability/` and environment variables, then applies the required Kubernetes resources and Helm values for telemetry collection.

## Inputs

- Variables file: `host_vars/splunk_observability/splunk_observability.ezai.yaml`
- Environment variables (as required by enabled integrations):
  - `openshift_api_url`
  - `openshift_token_id`
  - `splunk_observability_token`
  - `splunk_platform_token`
  - `intersight_api_key_id` (if Intersight integration enabled)
  - `intersight_secret_key` (if Intersight integration enabled)
  - `nexus_device_password` (if Nexus integration enabled)

## Role Structure

- `tasks/main.yaml`: Role entry point and orchestration
- `templates/otel-values.yaml.j2`: OpenTelemetry collector Helm values template
- `templates/intersight-config-map.yaml.j2`: Intersight exporter config
- `templates/intersight-deployment.yaml.j2`: Intersight exporter deployment
- `templates/nexus-config-map.yaml.j2`: Nexus exporter config
- `templates/nexus-deployment.yaml.j2`: Nexus exporter deployment
- `templates/nexus-service.yaml.j2`: Nexus exporter service
- `library/`: Helper modules used by role workflows
- `files/`: Static assets consumed by tasks/templates

## Run

Run only observability:

```bash
python3 scripts/deploy_ai_pod.py --role observability \
  --vault-password-file ~/.config/cisco-ai-pods/vault-password
```

Run observability from full stack playbook:

```bash
python3 scripts/deploy_ai_pod.py --role observability \
  --vault-password-file ~/.config/cisco-ai-pods/vault-password
```

## Validation

```bash
oc get pods -n otel
oc logs -n otel -l app=splunk-otel-collector
oc get configmap -n cisco-exporter
oc get deployment -n cisco-exporter
```

Check that telemetry reaches Splunk Observability Cloud using your configured realm and token.

## Idempotency

Safe to re-run. The role reconciles generated resources from current variable and environment inputs.

## Troubleshooting

- Missing telemetry:
  - Verify required environment variables are exported in the same shell as Ansible execution.
- Collector pods not healthy:
  - Check logs in `otel` namespace.
- Nexus metrics absent:
  - Confirm `nexus_device_password` is set and Nexus integration is enabled in variables.
- Intersight metrics absent:
  - Confirm `intersight_api_key_id` and `intersight_secret_key` are set and integration is enabled.
- YAML input errors:
  - Edit `.ezai.yaml` in Visual Studio Code with Red Hat YAML extension enabled.

Environment prep and schema setup:
- [docs/guide_prepare_the_environment.md](../../docs/guide_prepare_the_environment.md)
- [YAML schema validation section](../../docs/guide_prepare_the_environment.md#yaml-schema-for-auto-completion-help-and-error-validation)
