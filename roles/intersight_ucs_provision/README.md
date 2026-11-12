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

Pools, policies, and templates are processed before profiles. Profiles are processed
in dependency order across all configured organizations: UCS domains (and Unified
Edge domains), then chassis, then servers. Each profile type finishes its configured
deployment actions before the next type starts. Check mode uses the same order.
The `name_prefix` and `name_suffix` settings are naming metadata, not deployable
resources. They remain available for resource naming but are excluded from
resource deployment selection.
A/B switch profiles and templates use the fully decorated cluster name followed
by `-A` or `-B`; the prefix and suffix are applied only once. Existing children
are matched within their parent by `SwitchId`, allowing apply mode to correct
names from older deployments in place without recreating the children. Check
mode reports the rename without submitting it. Template attachment also resolves
existing A/B children by identity even when their names need correction.
For domain and Unified Edge profiles, `action: Deploy` deploys the assigned A/B
switch profiles through `fabric/SwitchProfiles`, then waits for both to finish.
The console logs each switch profile's deployment start, successful PATCH submission,
each 60-second polling wait with its check number, and deployment completion.
Missing assignments, failed deployments, and polling timeouts stop the workflow
before chassis/server processing. Already-deployed switch profiles without pending
changes are skipped; check mode reports the deployment without submitting it.

## Troubleshooting

- Verify API key and endpoint credentials.
- Confirm required variables are present in the selected host vars.
- Domain, chassis, and server profile serial numbers must resolve to hardware
  visible in Intersight. A lookup that returns none or only some of the requested
  serials fails explicitly, listing the missing serials. Check for typos, claim
  status, and API-key access before retrying; this also applies in check mode.
- Review output for validation errors before retrying.
- Attaching a domain or Unified Edge profile requires an existing cluster template
  and its A/B switch templates. Template references are resolved by organization
  and name before creating profiles; missing template IDs fail explicitly instead
  of submitting placeholder IDs. Each switch profile uses its matching switch
  template, not the cluster template's ID.
  After creating/updating the cluster and both switch profiles, provisioning uses
  `bulk/MoMergers` to attach their templates when the relationship or inherited
  policies are missing. It reads back each profile and waits for its template
  relationship and template policy references before submitting deployment.
  A template reference alone is not treated as proof of policy inheritance.
  Rerunning profiles repairs reference-only attachments; `attach_template: false`
  still copies configuration without binding the template. Check mode never
  submits merges.
- Check mode allows empty lookups on a new deployment. If referenced pools,
  policies, or templates do not exist yet, it reports deferred payload validation
  for the dependent resource type rather than requiring IDs that have not been
  created. Deferred payloads are not validated or submitted. Define the missing
  resources in the deployment configuration or create them separately before
  applying, then rerun check mode once they exist. Apply mode still requires
  referenced resources to exist when their dependent payloads are built.
  This includes attached domain and Unified Edge profile templates: a missing
  cluster template defers profile payload validation in check mode. Local template
  copying with `attach_template: false` does not require an API template.