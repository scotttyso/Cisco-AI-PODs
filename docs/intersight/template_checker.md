# Intersight Template Checker and CVA/PVA Support

These are maintenance tools for keeping the Intersight policy templates in `roles/intersight_ucs_provision` in step with the Intersight API, plus the environment handling that lets the same deployment target Intersight SaaS, a Connected Virtual Appliance (CVA), or a Private Virtual Appliance (PVA). You do not need either to deploy.

## Template Difference Checker

Compares the attributes in the Jinja2 templates with the attributes Intersight SaaS accepts, and reports attributes the templates are missing or that no longer exist in the API.

```bash
python roles/intersight_ucs_provision/library/src/intersight/check_template_differences.py -c all -f all
```

| Option | Meaning |
|--------|---------|
| `-c`, `--category` | `policies`, `pools`, `profiles`, `templates`, `system`, or `all` (default) |
| `-f`, `--formats` | `json`, `csv`, `markdown`, or `all` (default) |
| `-o`, `--output` | Report filename prefix (default `template_differences`, written to the current directory) |
| `-d`, `--details` | List the individual attributes in the markdown report |
| `--config` | Attribute exclusion file; the default list is `attribute_exclusions.yaml` in the same folder |
| `--vault`, `--vault-password` | Encrypted credentials file and its password file |
| `--api-key-id`, `--api-secret-key` | Credentials given directly instead of the vault |
| `--no-cache` | Query the API again instead of using cached schemas |
| `-v`, `--verbose` | Debug logging |

Credentials default to `~/.config/cisco-ai-pods/vault.yaml` with the password in `~/.config/cisco-ai-pods/vault-password`.

Each template gets a match ratio. A ratio below 100% means the API has attributes the template does not carry yet; the markdown report lists them. Read-only and system-managed attributes (identifiers, timestamps, references to profiles and groups) are excluded through `attribute_exclusions.yaml`, so add a name there if a harmless attribute keeps appearing.

Reports are generated files and are not tracked in git. Tests:

```bash
cd roles/intersight_ucs_provision && python -m pytest tests/test_check_template_differences.py -v
```

## BIOS and Adapter Template Checker

Compares the BIOS, Ethernet adapter, and Fibre Channel adapter policy templates with the policies in your Intersight account.

```bash
python roles/intersight_ucs_provision/library/src/intersight/check_bios_adapter_templates.py --vault
```

Use `--vault` to read the API key from `~/.config/cisco-ai-pods/vault.yaml`, or pass `--api-key-id` and `--api-secret-key`. Reports are written to `build/reports/template-checker` (change it with `-o`), and `-v` turns on verbose logging.

## Targeting SaaS, CVA, or PVA

`deploy_intersight_ucs.py` decides which Intersight to talk to in this order:

1. `--intersight-environment saas|cva|pva` (short form `-ie`)
2. The `INTERSIGHT_ENVIRONMENT` environment variable
3. The endpoint URL (a URL containing `cva` or `pva` selects that environment)
4. SaaS

Credentials for each environment come from the same vault file:

```yaml
intersight:
  saas:
    endpoint: https://intersight.com
    apikey: <key id>
    secretkey: <secret key>
  cva:
    endpoint: https://cva.example.com
    apikey: <key id>
    secretkey: <secret key>
  pva:
    endpoint: https://pva.example.com
    apikey: <key id>
    secretkey: <secret key>
```

The run stops before deploying if the selected environment has no endpoint, key, or secret. A `secretkey_file` path can be used instead of `secretkey`.

**Attribute filtering is not active yet.** For CVA and PVA the deployment is designed to drop attributes the appliance's API does not accept, but nothing creates the schema cache it reads from (`~/.cache/cisco-ai-pods/schemas/<environment>_v1_schema.json`), and without it requests are sent unchanged. If an appliance rejects an attribute, remove it from the policy YAML for that run. SaaS requests are never filtered.

Tests: `roles/intersight_ucs_provision/tests/test_feature2.py` and `test_feature2_standalone.py`.
