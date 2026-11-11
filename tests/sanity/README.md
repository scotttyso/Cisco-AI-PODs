# Sanity Ignore Entries

This directory contains versioned Ansible sanity ignore files:

- `ignore-2.20.txt` is the source of truth.
- `ignore-2.16.txt` is kept in sync for compatibility.

## File Format Rules

The ignore files use a strict format. Each non-empty line must be a valid ignore rule.

- Do not add blank lines.
- Do not add comment-only lines.
- Keep one ignore rule per line.

If comments or blank lines are added, sanity can fail with errors similar to:
"Line cannot be empty or contain only a comment".

## Why These Entries Exist

Current sanity ignore entries are intentionally minimal:

- `roles/splunk_observability/library/get_helm.sh shellcheck!skip`
  - Shellcheck skip for helper script behavior not aligned with shellcheck expectations.
- `automation-appliance/files/aipod-config shebang` and `automation-appliance/files/aipod-update shebang`
  - These privileged appliance helpers deliberately use `/usr/bin/python3`, not a caller-selected interpreter
    from `PATH`. Keep their fixed interpreter; the generic non-module sanity rule expects `env python`.
- Six explicit Helm template paths with `yamllint:error` and `yamllint:unparsable-with-libyaml`
  - Unrendered Go template expressions are not YAML. These entries ignore the known syntax diagnostics for those
    files (yamllint reports parser syntax errors with the `error` code), without skipping the test or excluding
    ordinary YAML elsewhere in the repository.

Important:

- `yamllint!skip` entries are not permitted by ansible sanity (`sanity[cannot-ignore]`).
- Standalone yamllint uses `.yamllint` to exclude raw Helm templates. Ansible sanity uses its own built-in
  configuration and does not read that file, so its known Helm syntax diagnostics require the explicit entries above.

## Maintenance

When updating ignore entries:

1. Edit `tests/sanity/ignore-2.20.txt`.
2. Run `make sanity-ignore-sync`.
3. Run `make sanity-ignore-check`.
4. Run sanity checks as needed in CI/local validation.
