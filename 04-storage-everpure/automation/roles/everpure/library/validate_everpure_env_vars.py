"""
Everpure Environment Variable Validator

Validates sensitive environment variables required for Everpure configuration via configure_everpure_arrays.yaml Ansible playbook.

Sensitive Variable Patterns:
  - everpure_api_token_{1-64}       — API Token for Everpure Array
  - cert_mgmt_certificate_{1-64} — Certificate path/content
  - cert_mgmt_intermediate_certificate_{1-64} — Intermediate certificate (optional)
  - cert_mgmt_passphrase_{1-64}  — Private key passphrase (if encrypted)
  - cert_mgmt_private_key_{1-64} — Private key path/content
  - ldap_bind_password_{1-64}    — LDAP binding password
  - local_user_password_{1-64}   — Local user password
  - snmp_community_{1-64}        — SNMP community string
  - snmp_auth_passphrase_{1-64}  — SNMP v3 auth passphrase
  - snmp_privacy_passphrase_{1-64} — SNMP v3 privacy passphrase

Usage:
  python3 validate_everpure_env_vars.py --config host_vars/everpure/everpure.ezai.yaml

Exit Codes:
  0 — All required sensitive variables validated successfully
  1 — Missing or invalid sensitive variables
"""

import json
import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, Optional

# Schema path
_SCHEMA_PATH = Path(__file__).parent.parent / "schema" / "cisco-ai-pods.json"

# Module-level variable to cache sensitive schema properties
_SENSITIVE_SCHEMA_PROPS: Dict[str, Any] = {}


def load_schema() -> None:
    """Load schema and populate sensitive variable properties."""
    global _SENSITIVE_SCHEMA_PROPS  # pylint: disable=global-statement
    if not _SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema not found at {_SCHEMA_PATH}")

    with open(_SCHEMA_PATH, encoding='utf-8') as schema_file:
        schema = json.load(schema_file)

    if "definitions" not in schema or "abstract.sensitive_variables" not in schema[
            "definitions"]:
        raise ValueError(
            "Schema missing 'definitions.abstract.sensitive_variables'")

    _SENSITIVE_SCHEMA_PROPS = schema["definitions"]["abstract.sensitive_variables"].get(
        "properties", {})


def _wrap_cli_text(text: str, indent: str = "  ", width: int = 100) -> str:
    """Wrap text to specified width with indentation for CLI output."""
    return textwrap.fill(
        text,
        width=width,
        subsequent_indent=indent,
        break_long_words=False,
        break_on_hyphens=False)


def _format_sensitive_constraints(
        schema_key: str, schema_rule: Dict[str, Any]) -> str:  # pylint: disable=unused-argument
    """Format schema constraints (description, pattern, min/max) as readable text block."""
    if not isinstance(schema_rule, dict):
        return ""

    parts = []

    description = schema_rule.get("description", "").strip()
    if description:
        wrapped_desc = _wrap_cli_text(description)
        parts.append(f"\n  Description:\n    {wrapped_desc}")

    pattern = schema_rule.get("pattern")
    if isinstance(pattern, str) and pattern:
        parts.append(f"\n  Pattern: {pattern}")

    min_length = schema_rule.get("minLength")
    max_length = schema_rule.get("maxLength")
    if isinstance(min_length, int) or isinstance(max_length, int):
        if isinstance(min_length, int) and isinstance(max_length, int):
            parts.append(
                f"\n  Length: {min_length} to {max_length} characters")
        elif isinstance(min_length, int):
            parts.append(f"\n  Minimum length: {min_length} characters")
        elif isinstance(max_length, int):
            parts.append(f"\n  Maximum length: {max_length} characters")

    return "".join(parts)


def _validate_sensitive_value(  # pylint: disable=too-many-arguments
    value: Any,
    schema_rule: Dict[str, Any],
    env_var_name: str,
    context: str,
    schema_key: Optional[str] = None,
    sensitive_properties: Optional[Dict[str, Any]] = None,
) -> None:
    """Validate a resolved sensitive value against schema minLength/maxLength/pattern."""
    if value in (None, ""):
        error_msg = (
            f"Missing required environment variable '{env_var_name}' for {context}.\n"
            f"\n  To fix this, run:\n"
            f"    export {env_var_name}='<your_value_here>'")
        if schema_key and sensitive_properties and schema_key in sensitive_properties:
            error_msg += _format_sensitive_constraints(
                schema_key, sensitive_properties[schema_key])
        raise ValueError(error_msg)

    if not isinstance(schema_rule, dict):
        return

    text_value = str(value)
    min_length = schema_rule.get("minLength")
    max_length = schema_rule.get("maxLength")
    pattern = schema_rule.get("pattern")
    constraint_info = _format_sensitive_constraints(context, schema_rule)

    if isinstance(min_length, int) and len(text_value) < min_length:
        raise ValueError(
            f"Environment variable '{env_var_name}' for {context} is too short "
            f"({len(text_value)} < {min_length}). Value is sensitive and hidden."
            f"{constraint_info}")

    if isinstance(max_length, int) and len(text_value) > max_length:
        raise ValueError(
            f"Environment variable '{env_var_name}' for {context} is too long "
            f"({len(text_value)} > {max_length}). Value is sensitive and hidden."
            f"{constraint_info}")

    if isinstance(pattern, str) and pattern:
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            raise ValueError(
                f"Invalid regex pattern in abstract.sensitive_variables for {context}: {exc}"
            ) from exc
        if compiled.search(text_value) is None:
            raise ValueError(
                f"Environment variable '{env_var_name}' for {context} does not match "
                f"the schema pattern. Value is sensitive and hidden."
                f"{constraint_info}")


def _resolve_sensitive_identifier(  # pylint: disable=too-many-arguments
    var_id: Any,
    env_prefix: str,
    schema_key: Optional[str],
    context: str,
    sensitive_properties: Dict[str, Any],
    resolved_vars: Dict[str, str],
) -> None:
    """Resolve one sensitive variable identifier to its env value and validate.

    Args:
        var_id:               Integer identifier from the model (1-64).
        env_prefix:           Environment variable name prefix (without _N suffix).
        schema_key:           Key inside abstract.sensitive_variables for validation rules,
                              or None if no schema entry exists.
        context:              Human-readable path used in error messages.
        sensitive_properties: Dict from abstract.sensitive_variables.properties.
        resolved_vars:        Mutable dict where resolved env_var_name -> value is stored.
    """
    if var_id in (None, ""):
        return
    if not isinstance(var_id, int) or var_id <= 0:
        raise ValueError(
            f"{context} must be a positive integer sensitive variable identifier."
        )

    env_var_name = f"{env_prefix}_{var_id}"
    env_value = os.environ.get(env_var_name)
    if env_value in (None, ""):
        error_msg = (
            f"Missing required environment variable '{env_var_name}' for {context}.\n"
            f"\n  To fix this, run:\n"
            f"    export {env_var_name}='<your_value_here>'")
        if schema_key and schema_key in sensitive_properties:
            error_msg += _format_sensitive_constraints(
                schema_key,
                sensitive_properties[schema_key],
            )
        raise ValueError(error_msg)

    if schema_key:
        schema_rule = sensitive_properties.get(schema_key, {})
        _validate_sensitive_value(
            env_value,
            schema_rule,
            env_var_name,
            context,
            schema_key,
            sensitive_properties,
        )

    resolved_vars[env_var_name] = env_value


def _resolve_sensitive_var(
    var_id: Any,
    env_prefix: str,
    schema_key: Optional[str],
    context: str,
) -> str:
    """Wrapper to resolve a sensitive variable and return its value directly."""
    resolved_vars: Dict[str, str] = {}
    _resolve_sensitive_identifier(
        var_id,
        env_prefix,
        schema_key,
        context,
        _SENSITIVE_SCHEMA_PROPS,
        resolved_vars,
    )
    env_var_name = f"{env_prefix}_{var_id}"
    return resolved_vars.get(env_var_name, "")


def validate_pure_api_token(cfg: Dict[str, Any]) -> None:  # pylint: disable=redefined-outer-name
    """Validate pure_api_token for each FlashArray and FlashBlade."""
    for array_type in ["flash_arrays", "flash_blades"]:
        if array_type not in cfg.get("everpure", {}):
            continue

        arrays = cfg["everpure"][array_type]
        if not isinstance(arrays, list):
            continue

        for array in arrays:
            if not isinstance(array, dict):
                continue

            api_token_id = array.get("api_token_id")
            if api_token_id in (None, ""):
                continue

            fqdn = array.get("array_fqdn", f"{array_type}_array")
            context = f"everpure.{array_type}[{fqdn}].api_token_id"

            _resolve_sensitive_identifier(
                api_token_id,
                "pure_api_token",
                "pure_api_token",
                context,
                _SENSITIVE_SCHEMA_PROPS,
                {},
            )


def validate_certificates(cfg: Dict[str, Any]) -> None:  # pylint: disable=redefined-outer-name
    """Validate certificate management variables in Everpure settings."""
    settings = cfg.get("everpure", {}).get("settings", {})
    if not isinstance(settings, dict):
        return

    certs = settings.get(
        "security",
        {}).get(
        "certificates",
        {}).get(
            "array_certificates",
        [])
    if not isinstance(certs, list):
        return

    for idx, cert in enumerate(certs):
        if not isinstance(cert, dict):
            continue

        # Validate certificate
        cert_id = cert.get("certificate")
        if cert_id not in (None, "", 0):
            context = f"everpure.settings.security.certificates.array_certificates[{idx}].certificate"
            _resolve_sensitive_identifier(
                cert_id,
                "cert_mgmt_certificate",
                "certificate",
                context,
                _SENSITIVE_SCHEMA_PROPS,
                {},
            )

        # Validate intermediate certificate (optional)
        inter_cert_id = cert.get("intermediate_certificate")
        if inter_cert_id not in (None, "", 0):
            context = f"everpure.settings.security.certificates.array_certificates[{idx}].intermediate_certificate"
            _resolve_sensitive_identifier(
                inter_cert_id,
                "cert_mgmt_intermediate_certificate",
                "certificate",
                context,
                _SENSITIVE_SCHEMA_PROPS,
                {},
            )

        # Validate private key
        key_id = cert.get("private_key")
        if key_id not in (None, "", 0):
            context = f"everpure.settings.security.certificates.array_certificates[{idx}].private_key"
            _resolve_sensitive_identifier(
                key_id,
                "cert_mgmt_private_key",
                "private_key",
                context,
                _SENSITIVE_SCHEMA_PROPS,
                {},
            )

        # Validate passphrase (if private key is encrypted)
        passphrase_id = cert.get("key_passphrase")
        if passphrase_id not in (None, "", 0):
            context = f"everpure.settings.security.certificates.array_certificates[{idx}].key_passphrase"
            _resolve_sensitive_identifier(
                passphrase_id,
                "cert_mgmt_passphrase",
                "cert_mgmt_passphrase",
                context,
                _SENSITIVE_SCHEMA_PROPS,
                {},
            )


def validate_directory_service(cfg: Dict[str, Any]) -> None:  # pylint: disable=redefined-outer-name
    """Validate LDAP binding password in directory service configuration."""
    settings = cfg.get("everpure", {}).get("settings", {})
    if not isinstance(settings, dict):
        return

    dir_service = settings.get(
        "security",
        {}).get(
        "directory_service",
        {}).get(
            "configuration",
        [])
    if not isinstance(dir_service, list):
        return

    for idx, config_item in enumerate(dir_service):
        if not isinstance(config_item, dict):
            continue

        bind_pwd_id = config_item.get("bind_password")
        if bind_pwd_id not in (None, "", 0):
            context = f"everpure.settings.security.directory_service.configuration[{idx}].bind_password"
            _resolve_sensitive_identifier(
                bind_pwd_id,
                "ldap_bind_password",
                "ldap_binding_password",
                context,
                _SENSITIVE_SCHEMA_PROPS,
                {},
            )


def validate_local_users(cfg: Dict[str, Any]) -> None:  # pylint: disable=redefined-outer-name
    """Validate local user passwords."""
    settings = cfg.get("everpure", {}).get("settings", {})
    if not isinstance(settings, dict):
        return

    users = settings.get("security", {}).get("users", [])
    if not isinstance(users, list):
        return

    for idx, user in enumerate(users):
        if not isinstance(user, dict):
            continue

        pwd_id = user.get("password")
        if pwd_id not in (None, "", 0):
            username = user.get("username", f"user[{idx}]")
            context = f"everpure.settings.security.users[{username}].password"
            _resolve_sensitive_identifier(
                pwd_id,
                "local_user_password",
                "local_user_password",
                context,
                _SENSITIVE_SCHEMA_PROPS,
                {},
            )


def validate_snmp(cfg: Dict[str, Any]) -> None:  # pylint: disable=redefined-outer-name,too-many-branches
    """Validate SNMP configuration variables (community strings and passphrases)."""
    settings = cfg.get("everpure", {}).get("settings", {})
    if not isinstance(settings, dict):
        return

    monitoring = settings.get(
        "system",
        {}).get(
        "monitoring",
        {}).get(
            "snmp",
        {})
    if not isinstance(monitoring, dict):
        return

    # Validate SNMP v2c community strings
    v2c_managers = monitoring.get("add_snmp_manager", {}).get("v2c", [])
    if isinstance(v2c_managers, list):
        for idx, manager in enumerate(v2c_managers):
            if not isinstance(manager, dict):
                continue

            community_id = manager.get("community")
            if community_id not in (None, "", 0):
                context = f"everpure.settings.system.monitoring.snmp.add_snmp_manager.v2c[{idx}].community"
                _resolve_sensitive_identifier(
                    community_id,
                    "snmp_community",
                    "snmp_community_string",
                    context,
                    _SENSITIVE_SCHEMA_PROPS,
                    {},
                )

    # Validate SNMP v3 auth and privacy passphrases
    v3_managers = monitoring.get("add_snmp_manager", {}).get("v3", [])
    if isinstance(v3_managers, list):
        for idx, manager in enumerate(v3_managers):
            if not isinstance(manager, dict):
                continue

            auth_id = manager.get("auth_passphrase")
            if auth_id not in (None, "", 0):
                context = f"everpure.settings.system.monitoring.snmp.add_snmp_manager.v3[{idx}].auth_passphrase"
                _resolve_sensitive_identifier(
                    auth_id,
                    "snmp_auth_passphrase",
                    "snmp_password",
                    context,
                    _SENSITIVE_SCHEMA_PROPS,
                    {},
                )

            priv_id = manager.get("privacy_passphrase")
            if priv_id not in (None, "", 0):
                context = f"everpure.settings.system.monitoring.snmp.add_snmp_manager.v3[{idx}].privacy_passphrase"
                _resolve_sensitive_identifier(
                    priv_id,
                    "snmp_privacy_passphrase",
                    "snmp_password",
                    context,
                    _SENSITIVE_SCHEMA_PROPS,
                    {},
                )

    # Validate edit SNMP agent
    edit_agent = monitoring.get("edit_snmp_agent", {})
    if isinstance(edit_agent, dict):
        auth_id = edit_agent.get("auth_passphrase")
        if auth_id not in (None, "", 0):
            context = "everpure.settings.system.monitoring.snmp.edit_snmp_agent.auth_passphrase"
            _resolve_sensitive_identifier(
                auth_id,
                "snmp_auth_passphrase",
                "snmp_password",
                context,
                _SENSITIVE_SCHEMA_PROPS,
                {},
            )

        community_id = edit_agent.get("community")
        if community_id not in (None, "", 0):
            context = "everpure.settings.system.monitoring.snmp.edit_snmp_agent.community"
            _resolve_sensitive_identifier(
                community_id,
                "snmp_community",
                "snmp_community_string",
                context,
                _SENSITIVE_SCHEMA_PROPS,
                {},
            )

        priv_id = edit_agent.get("privacy_passphrase")
        if priv_id not in (None, "", 0):
            context = "everpure.settings.system.monitoring.snmp.edit_snmp_agent.privacy_passphrase"
            _resolve_sensitive_identifier(
                priv_id,
                "snmp_privacy_passphrase",
                "snmp_password",
                context,
                _SENSITIVE_SCHEMA_PROPS,
                {},
            )


def validate_all(cfg: Dict[str, Any]) -> None:  # pylint: disable=redefined-outer-name
    """Validate all Everpure sensitive environment variables."""
    validate_pure_api_token(cfg)
    validate_certificates(cfg)
    validate_directory_service(cfg)
    validate_local_users(cfg)
    validate_snmp(cfg)


if __name__ == "__main__":
    import argparse
    import yaml

    parser = argparse.ArgumentParser(
        description="Validate Everpure environment variables",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to Everpure YAML configuration file",
        required=True,
    )

    args = parser.parse_args()

    try:
        load_schema()

        config_path = Path(args.config)
        if not config_path.exists():
            print(
                f"ERROR: Configuration file not found: {config_path}",
                file=sys.stderr)
            sys.exit(1)

        with open(config_path, encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        validate_all(config)
        print("✓ All Everpure sensitive environment variables validated successfully.")
        sys.exit(0)

    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"ERROR: Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)
