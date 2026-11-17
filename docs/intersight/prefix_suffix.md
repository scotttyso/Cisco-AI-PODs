# Intersight Name Prefix and Suffix Support

This document describes how name prefix and suffix values are applied by the Intersight provisioning roles:

- `roles/intersight_policies/`: Applies name decoration to Intersight policies
- `roles/intersight_pools/`: Applies name decoration to Intersight pools
- `roles/intersight_profiles/`: Applies name decoration to Intersight profiles and templates

## Overview

The playbooks support name decoration using `name_prefix` and `name_suffix` values from the merged model files.

The behavior is:

- Pools: type-specific prefix/suffix is used when present (`mac`, `uuid`, `ip`), otherwise `default` is used.
- Policies: `default` prefix/suffix is used for all policy types.
- Profiles: type-specific prefix/suffix is used when present (`domain`, `chassis`, `server`), otherwise `default` is used.
- Templates: type-specific prefix/suffix is used when present (`server` currently used by the playbook), otherwise `default` is used.

If no prefix/suffix values are provided, names are unchanged.

## Where It Applies

### Intersight Pools Role

- Applies prefix/suffix to pool object names for:
  - MAC pools
  - UUID pools
  - IP pools

### Intersight Policies Role

- Applies `policies.name_prefix.default` and `policies.name_suffix.default` to all supported policy names.

### Intersight Profiles Role

- Applies prefix/suffix to:
  - Domain profile names
  - Chassis profile names
  - Server profile names
  - Server profile template names

## YAML Model Format

Add these sections to your model files as needed:

```yaml
intersight:
  organizations:
    <org-name>
      pools:
        name_prefix:
          default: ""      # applies to all pools
          mac: "mac-"      # optional per-type override
          uuid: "uuid-"
          ip: "ip-"
        name_suffix:
          default: "-prod"

      policies:
        name_prefix:
          default: "prod-"
        name_suffix:
          default: "-policy"

      profiles:
        name_prefix:
          default: ""
          server: "srv-"
          domain: "dom-"
          chassis: "ch-"
        name_suffix:
          default: ""

      templates:
        name_prefix:
          default: ""
          server: "tmpl-"
        name_suffix:
          default: "-template"
        ```

## Effective Name Examples

Given:

- Pool name: `MGMT`
- `pools.name_prefix.ip: ip-`
- `pools.name_suffix.default: -prod`

The resulting Intersight pool name becomes:

- `ip-MGMT-prod`

Given:

- Profile name: `compute01`
- `profiles.name_prefix.server: srv-`
- `profiles.name_suffix.default: -a`

The resulting Intersight profile name becomes:

- `srv-compute01-a`

## Notes

- Prefix/suffix values are concatenated directly to the base `name` value.
- User-provided `name` values remain the base; prefix/suffix decoration is applied at deploy time.
- Keep resulting names within Intersight object name length constraints.
