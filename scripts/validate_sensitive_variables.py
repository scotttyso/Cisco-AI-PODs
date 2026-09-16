"""
Comprehensive Sensitive Variables Validator

Validates all sensitive environment variables required across all Ansible playbooks
(intersight_ucs_provision, openshift_install, everpure, splunk_observability)
against merged data models.

This script consolidates validation from multiple roles into a single comprehensive check,
supporting multiple merged model files and reporting all discovered sensitive variables.

Usage:
    python3 validate_sensitive_variables.py --models model1.json model2.json ... [--schema schema.json]
    python3 validate_sensitive_variables.py --models model.json [--verbose]

Exit Codes:
  0 — All required sensitive variables found and valid
  1 — One or more sensitive variables missing or invalid
"""

import json
import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Schema path
_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "sensitive" / "variables.json"

# All sensitive variable patterns indexed by prefix
# Maps env_prefix -> (schema_key, description)
_SENSITIVE_VAR_PATTERNS = {
    "cert_mgmt_private_key": ("private_key", "Pure Storage Private Key"),
    "cco_password": ("cco_password", "Cisco.com Password"),
    "cco_user": ("cco_user", "Cisco.com User Email"),
    "drive_security_authentication_password": (
        "drive_security_authentication_password",
        "Drive Security Authentication Password",
    ),
    "drive_security_current_security_key_passphrase": (
        "drive_security_current_security_key_passphrase",
        "Drive Security Current Security Key Passphrase",
    ),
    "drive_security_new_security_key_passphrase": (
        "drive_security_new_security_key_passphrase",
        "Drive Security New Security Key Passphrase",
    ),
    "everpure_api_token": ("everpure_api_token", "Everpure Array API Token"),
    "everpure_snmp_community": ("everpure_snmp_community", "Everpure SNMP Community"),
    "everpure_snmp_auth_passphrase": ("everpure_snmp_auth_passphrase", "Everpure SNMP Auth Passphrase"),
    "everpure_snmp_privacy_passphrase": ("everpure_snmp_privacy_passphrase", "Everpure SNMP Privacy Passphrase"),
    "fabric_interconnect_password": (
        "fabric_interconnect_password",
        "Fabric Interconnect Password",
    ),
    "intersight_api_key_id": ("intersight_api_key_id", "Intersight API Key ID"),
    "ipmi_encryption_key": ("ipmi_encryption_key", "IPMI Encryption Key"),
    "iscsi_boot_password": ("iscsi_boot_password", "iSCSI Boot Password"),
    "iso_web_server_password": ("iso_web_server_password", "ISO Web Server Password"),
    "ldap_binding_password": ("ldap_binding_password", "LDAP Binding Password"),
    "linux_password": ("linux_password", "Linux Password"),
    "local_user_password": ("local_user_password", "Local User Password"),
    "mac_sec_fallback_key_chain_secret": (
        "mac_sec_fallback_key_chain_secret",
        "MacSec Fallback Key Chain Secret",
    ),
    "mac_sec_primary_key_chain_secret": (
        "mac_sec_primary_key_chain_secret",
        "MacSec Primary Key Chain Secret",
    ),
    "persistent_passphrase": ("persistent_passphrase", "Persistent Memory Passphrase"),
    "private_key_passphrase": ("private_key_passphrase", "Private Key Passphrase"),
    "proxy_password": ("proxy_password", "Proxy Password"),
    "redfish_password": ("redfish_password", "Redfish/BMC Password"),
    "root_password": ("root_password", "Root Password"),
    "snmp_auth_passphrase": ("snmp_password", "SNMP Auth Passphrase"),
    "snmp_community_string": ("snmp_community_string", "SNMP Community String"),
    "snmp_trap_community": ("snmp_community_string", "SNMP Trap Community String"),
    "snmp_access_community_string": ("snmp_community_string", "SNMP Access Community String"),
    "snmp_user_auth_password": ("snmp_password", "SNMP User Auth Password"),
    "snmp_user_privacy_password": ("snmp_password", "SNMP User Privacy Password"),
    "snmp_password": ("snmp_password", "SNMP Password"),
    "snmp_privacy_passphrase": ("snmp_password", "SNMP Privacy Passphrase"),
    "splunk_observability_access_token": (
        "splunk_observability_access_token",
        "Splunk Observability Access Token",
    ),
    "splunk_observability_nexus_password": (
        "splunk_observability_nexus_password",
        "Splunk Observability Nexus Password",
    ),
    "splunk_platform_token": ("splunk_platform_token", "Splunk Platform Token"),
    "switch_control_aes_primary_key": (
        "switch_control_aes_primary_key",
        "Switch Control AES Primary Key",
    ),
    "ssh_public_key": ("ssh_public_key", "SSH Public Key"),
    "vmedia_password": ("vmedia_password", "Virtual Media Password"),
    "vmware_esxi_password": ("vmware_esxi_password", "VMware ESXi Password"),
    "windows_admin_password": ("windows_admin_password", "Windows Admin Password"),
}

# Cache for schema properties
_SENSITIVE_SCHEMA_PROPS: Dict[str, Any] = {}

_MODEL_TOP_KEYS = [
    "intersight",
    "openshift",
    "everpure",
    "splunk_observability",
    "shared_services",
]

_CERT_KIND = "certificate"
_PRIVATE_KEY_KIND = "private_key"

_CERT_HEADER_RE = re.compile(r"-----BEGIN CERTIFICATE-----")
_PRIVATE_KEY_HEADER_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")


def _is_true(value: Any) -> bool:
    """Return True when a value represents an enabled boolean flag."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on", "enabled"}
    return False


def _requires_intersight_credentials(model_data: Dict[str, Any]) -> bool:
    """Return True when Intersight credentials must be validated."""
    intersight_present = isinstance(model_data.get("intersight"), dict) and bool(model_data.get("intersight"))

    splunk_intersight_enabled = _is_true(
        model_data.get("splunk_observability", {})
        .get("intersight", {})
        .get("enable")
    )

    # Backward-compatible fallback for alternate model shape.
    legacy_splunk_intersight_enabled = _is_true(
        model_data.get("splunk", {})
        .get("observability", {})
        .get("intersight", {})
        .get("enable")
    )

    return intersight_present or splunk_intersight_enabled or legacy_splunk_intersight_enabled


def _supports_color(stream) -> bool:
    """Return True when ANSI colors should be used for the given stream."""
    if os.environ.get("NO_COLOR") is not None:
        return False
    return hasattr(stream, "isatty") and stream.isatty()


def _colorize(text: str, color_code: str, stream=sys.stderr) -> str:
    """Wrap text in ANSI color when supported."""
    if not _supports_color(stream):
        return text
    return f"\033[{color_code}m{text}\033[0m"


def load_schema(schema_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load schema and extract sensitive variable properties."""
    if schema_path is None:
        schema_path = _SCHEMA_PATH

    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found at {schema_path}")

    with open(schema_path, encoding="utf-8") as schema_file:
        schema = json.load(schema_file)

    definitions = schema.get("definitions")
    if not isinstance(definitions, dict):
        raise ValueError("Schema missing 'definitions'")

    sensitive_definition = definitions.get("abstract.sensitive_variables")
    if isinstance(sensitive_definition, dict):
        props = sensitive_definition.get("properties", {})
    elif schema.get("$id") == "variables.json":
        props = definitions
    else:
        raise ValueError(
            "Schema missing 'definitions.abstract.sensitive_variables' or standalone variables.json definitions"
        )

    if not isinstance(props, dict):
        raise ValueError("Schema contains no sensitive-variable definitions")
    _SENSITIVE_SCHEMA_PROPS.clear()
    _SENSITIVE_SCHEMA_PROPS.update(props)
    return schema


def _wrap_cli_text(text: str, indent: str = "  ", width: int = 100) -> str:
    """Wrap text to specified width with indentation for CLI output."""
    return textwrap.fill(
        text,
        width=width,
        subsequent_indent=indent,
        break_long_words=False,
        break_on_hyphens=False,
    )


def _format_export_command(
    env_var_name: str,
    schema_key: Optional[str] = None,
) -> str:
    """Format export command suggestion for a missing variable."""
    lines = [
        "",
        _colorize("  To fix this, run:", "1;33"),
        _colorize(f"    export {env_var_name}='<your_value_here>'", "33"),
    ]

    if schema_key and schema_key in _SENSITIVE_SCHEMA_PROPS:
        schema_rule = _SENSITIVE_SCHEMA_PROPS[schema_key]
        description = schema_rule.get("description", "").strip()
        if description:
            wrapped_description = _wrap_cli_text(description, indent="    ")
            if _supports_color(sys.stderr):
                wrapped_description = "\n".join(
                    _colorize(line, "36")
                    for line in wrapped_description.splitlines()
                )
            lines.append("")
            lines.append(_colorize("  Description:", "1;36"))
            lines.append(wrapped_description)

    return "\n".join(lines)


def _validate_value_against_schema(
    env_var_name: str,
    env_value: str,
    schema_key: Optional[str],
) -> Optional[str]:
    """Validate env var value against schema constraints and return error text when invalid."""
    if not schema_key or schema_key not in _SENSITIVE_SCHEMA_PROPS:
        return None

    rule = _SENSITIVE_SCHEMA_PROPS[schema_key]

    min_len = rule.get("minLength")
    if isinstance(min_len, int) and len(env_value) < min_len:
        return (
            f"Environment variable '{env_var_name}' is invalid: length "
            f"{len(env_value)} is less than minimum {min_len}."
        )

    max_len = rule.get("maxLength")
    if isinstance(max_len, int) and len(env_value) > max_len:
        return (
            f"Environment variable '{env_var_name}' is invalid: length "
            f"{len(env_value)} exceeds maximum {max_len}."
        )

    pattern = rule.get("pattern")
    if isinstance(pattern, str) and pattern:
        try:
            # Use fullmatch so only fully compliant values pass.
            if re.fullmatch(pattern, env_value) is None:
                return (
                    f"Environment variable '{env_var_name}' is invalid: "
                    "value does not match required pattern "
                    f"for '{schema_key}'."
                )
        except re.error:
            # If the schema regex is malformed, do not block validation.
            return None

    return None


def _map_var_name_to_schema_key(env_var_name: str) -> Optional[str]:
    """
    Map an environment variable name to its schema key.

    Tries multiple strategies:
    1. Exact match in schema
    2. Strip _N suffix and match
    3. Pattern-based mapping
    """
    # Strategy 1: Direct lookup
    if env_var_name in _SENSITIVE_SCHEMA_PROPS:
        return env_var_name

    # Strategy 2: Strip trailing _N and try again
    match = re.match(r'^(.+?)_\d{1,2}$', env_var_name)
    if match:
        base_name = match.group(1)
        if base_name in _SENSITIVE_SCHEMA_PROPS:
            return base_name

    # Strategy 3: Pattern-based mapping from predefined patterns
    for pattern_prefix, (schema_key, unused_desc) in _SENSITIVE_VAR_PATTERNS.items():
        if env_var_name.startswith(pattern_prefix):
            return schema_key

    return None


def collect_required_sensitive_variables(
    model_data: Dict[str, Any],
) -> Dict[str, Tuple[str, Optional[str]]]:
    """
    Dynamically collect ALL sensitive variable references from model.

    Discovers any value that is an integer 1-64, treats the key as a variable name,
    and maps it to its schema key if available.

    Returns:
        Dict mapping env_var_name -> (env_prefix, schema_key_or_none)
    """
    required_vars: Dict[str, Tuple[str, Optional[str]]] = {}

    def _sensitive_id(value: Any) -> Optional[int]:
        """Return a valid sensitive variable ID (1-64) from int or numeric string."""
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value if 0 < value <= 64 else None
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.isdigit():
                parsed = int(stripped)
                return parsed if 0 < parsed <= 64 else None
        return None

    def _add_env_var(env_prefix: str, sid: int) -> None:
        env_var_name = f"{env_prefix}_{sid}"
        if env_var_name not in required_vars:
            schema_key = _map_var_name_to_schema_key(env_var_name)
            required_vars[env_var_name] = (env_prefix, schema_key)

    def traverse_model(obj: Any, path: str = "") -> None:
        """Recursively traverse model and dynamically discover all sensitive variable patterns."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                current_path = f"{path}.{key}" if path else key
                sid = _sensitive_id(value)

                # DYNAMIC DISCOVERY: If the value is a sensitive ID (1-64),
                # treat the key as a potential variable name prefix
                if sid is not None:
                    # Generic direct detection for explicit sensitive-looking keys.
                    if key in _SENSITIVE_VAR_PATTERNS:
                        _add_env_var(key, sid)

                    # Path-aware mappings for generic key names.
                    if key == "password":
                        if "binding_parameters" in current_path:
                            _add_env_var("ldap_binding_password", sid)
                        elif "local_user" in current_path and "users" in current_path:
                            _add_env_var("local_user_password", sid)
                        elif "profiles" in current_path and "server" in current_path and "targets" in current_path:
                            _add_env_var("local_user_password", sid)
                        elif "redfish" in current_path:
                            _add_env_var("redfish_password", sid)
                        elif "fabric_interconnects" in current_path:
                            _add_env_var("fabric_interconnect_password", sid)
                        elif "iso_web_server" in current_path:
                            _add_env_var("iso_web_server_password", sid)
                        elif "nexus" in current_path and "splunk_observability" in current_path:
                            _add_env_var("splunk_observability_nexus_password", sid)

                    if key == "api_token_id" and (
                        "everpure" in current_path
                        or "flash_arrays" in current_path
                        or "flash_blades" in current_path
                    ):
                        _add_env_var("everpure_api_token", sid)

                    if key == "private_key_passphrase":
                        _add_env_var("private_key_passphrase", sid)

                    if key == "bind_password":
                        _add_env_var("ldap_binding_password", sid)

                    if key == "community" and "everpure" in current_path:
                        _add_env_var("everpure_snmp_community", sid)

                    if key == "auth_password":
                        if "snmp_users" in current_path:
                            _add_env_var("snmp_user_auth_password", sid)
                        elif "everpure" in current_path:
                            _add_env_var("everpure_snmp_auth_passphrase", sid)

                    if key == "privacy_password":
                        if "snmp_users" in current_path:
                            _add_env_var("snmp_user_privacy_password", sid)
                        elif "everpure" in current_path:
                            _add_env_var("everpure_snmp_privacy_passphrase", sid)

                    if key == "access_token" and "splunk_observability" in current_path:
                        _add_env_var("splunk_observability_access_token", sid)

                    if key == "token" and "splunk_platform" in current_path:
                        _add_env_var("splunk_platform_token", sid)

                    if key == "encryption_key":
                        if "ipmi" in current_path:
                            _add_env_var("ipmi_encryption_key", sid)
                        elif "switch_control" in current_path:
                            _add_env_var("switch_control_aes_primary_key", sid)

                # Also check predefined patterns for context-aware detection
                # (keeps backward compatibility with path-aware detection)
                for env_prefix, pattern_values in _SENSITIVE_VAR_PATTERNS.items():
                    schema_key = pattern_values[0]
                    if key == env_prefix or key.endswith(f"_{env_prefix}"):
                        sid_check = _sensitive_id(value)
                        if sid_check is not None:
                            env_var_name = f"{env_prefix}_{sid_check}"
                            if env_var_name not in required_vars:
                                required_vars[env_var_name] = (env_prefix, schema_key)

                traverse_model(value, current_path)

        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                traverse_model(item, f"{path}[{idx}]")

    traverse_model(model_data)
    return required_vars


def validate_all_sensitive_variables(
    model_data: Dict[str, Any],
    schema_path: Optional[Path] = None,
) -> Tuple[bool, List[str], List[str], Dict[str, str]]:
    """
    Validate all sensitive variables in model and return their values.

    Returns:
        Tuple of success, missing vars, validation errors, and found values.
    """
    load_schema(schema_path)

    required_vars = collect_required_sensitive_variables(model_data)
    missing_vars: List[str] = []
    error_messages: List[str] = []
    sensitive_vars: Dict[str, str] = {}

    for env_var_name, required_var_values in sorted(required_vars.items()):
        env_prefix, schema_key = required_var_values
        env_value = os.environ.get(env_var_name)

        if env_value in (None, ""):
            missing_vars.append(env_var_name)
            error_msg = f"Missing required environment variable '{env_var_name}'"
            error_msg += _format_export_command(env_var_name, schema_key)
            error_messages.append(error_msg)
        else:
            validation_error = _validate_value_against_schema(
                env_var_name,
                env_value,
                schema_key,
            )
            if validation_error:
                missing_vars.append(env_var_name)
                validation_error += _format_export_command(
                    env_var_name,
                    schema_key,
                )
                error_messages.append(validation_error)
            else:
                sensitive_vars[env_var_name] = env_value

    success = len(missing_vars) == 0
    return success, missing_vars, error_messages, sensitive_vars


def _validate_file_content_kind(
    file_path: Path,
    kind: str,
    label: str,
) -> Optional[str]:
    """Validate file content matches expected certificate/private key kind."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as err:
        return f"Invalid {label}: unable to read file '{file_path}': {err}"

    if kind == _CERT_KIND and _CERT_HEADER_RE.search(content) is None:
        return (
            f"Invalid {label}: '{file_path}' does not appear to be a PEM certificate "
            "(missing '-----BEGIN CERTIFICATE-----')."
        )

    if kind == _PRIVATE_KEY_KIND and _PRIVATE_KEY_HEADER_RE.search(content) is None:
        return (
            f"Invalid {label}: '{file_path}' does not appear to be a PEM private key "
            "(missing private key header)."
        )

    return None


def _validate_path_entry(
    raw_path: str,
    kind: str,
    label: str,
) -> Optional[str]:
    """Validate that a configured certificate/private-key path exists and has expected content."""
    expanded = Path(os.path.expandvars(os.path.expanduser(raw_path)))

    if not expanded.exists():
        return f"Missing {label}: file not found at '{expanded}'"

    if not expanded.is_file():
        return f"Invalid {label}: path is not a regular file: '{expanded}'"

    return _validate_file_content_kind(expanded, kind, label)


def _append_file_check(
    checks: List[Tuple[str, str, str]],
    seen: Set[Tuple[str, str]],
    raw_path: Any,
    kind: str,
    label: str,
) -> None:
    """Add a file-check request if a non-empty path is provided."""
    if not isinstance(raw_path, str):
        return
    stripped = raw_path.strip()
    if not stripped:
        return
    dedupe_key = (stripped, kind)
    if dedupe_key in seen:
        return
    seen.add(dedupe_key)
    checks.append((stripped, kind, label))


def collect_certificate_file_checks(model_data: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """Collect certificate/private-key paths that should be validated from merged model data."""
    checks: List[Tuple[str, str, str]] = []
    seen: Set[Tuple[str, str]] = set()

    # everpure.settings.security.certificates.array_certificates[*]
    array_certs = (
        model_data.get("everpure", {})
        .get("settings", {})
        .get("security", {})
        .get("certificates", {})
        .get("array_certificates", [])
    )
    if isinstance(array_certs, list):
        for idx, cert_entry in enumerate(array_certs):
            if not isinstance(cert_entry, dict):
                continue
            _append_file_check(
                checks,
                seen,
                cert_entry.get("certificate_file"),
                _CERT_KIND,
                f"everpure.settings.security.certificates.array_certificates[{idx}].certificate_file",
            )
            _append_file_check(
                checks,
                seen,
                cert_entry.get("intermediate_certificate_file"),
                _CERT_KIND,
                f"everpure.settings.security.certificates.array_certificates[{idx}].intermediate_certificate_file",
            )
            _append_file_check(
                checks,
                seen,
                cert_entry.get("private_key_file"),
                _PRIVATE_KEY_KIND,
                f"everpure.settings.security.certificates.array_certificates[{idx}].private_key_file",
            )

    # intersight.policies.certificate_management.certificates[*]
    intersight_policies = model_data.get("intersight", {}).get("policies", [])
    if isinstance(intersight_policies, list):
        for policy_idx, policy in enumerate(intersight_policies):
            if not isinstance(policy, dict):
                continue
            cert_mgmt = policy.get("certificate_management")
            if not isinstance(cert_mgmt, dict):
                continue
            certs = cert_mgmt.get("certificates", [])
            if not isinstance(certs, list):
                continue
            for cert_idx, cert in enumerate(certs):
                if not isinstance(cert, dict):
                    continue
                _append_file_check(
                    checks,
                    seen,
                    cert.get("certificate_file"),
                    _CERT_KIND,
                    (
                        "intersight.policies"
                        f"[{policy_idx}].certificate_management.certificates[{cert_idx}].certificate_file"
                    ),
                )
                _append_file_check(
                    checks,
                    seen,
                    cert.get("private_key_file"),
                    _PRIVATE_KEY_KIND,
                    (
                        "intersight.policies"
                        f"[{policy_idx}].certificate_management.certificates[{cert_idx}].private_key_file"
                    ),
                )

    # openshift.certificates.*
    openshift_certs = model_data.get("openshift", {}).get("certificates", {})
    if isinstance(openshift_certs, dict):
        _append_file_check(
            checks,
            seen,
            openshift_certs.get("api_cert_chain_file"),
            _CERT_KIND,
            "openshift.certificates.api_cert_chain_file",
        )
        _append_file_check(
            checks,
            seen,
            openshift_certs.get("ingress_cert_chain_file"),
            _CERT_KIND,
            "openshift.certificates.ingress_cert_chain_file",
        )
        _append_file_check(
            checks,
            seen,
            openshift_certs.get("api_key_file"),
            _PRIVATE_KEY_KIND,
            "openshift.certificates.api_key_file",
        )
        _append_file_check(
            checks,
            seen,
            openshift_certs.get("ingress_key_file"),
            _PRIVATE_KEY_KIND,
            "openshift.certificates.ingress_key_file",
        )

    return checks


def validate_certificate_files(model_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate configured certificate/private-key file paths and file content types."""
    errors: List[str] = []

    checks = collect_certificate_file_checks(model_data)
    for raw_path, kind, label in checks:
        error = _validate_path_entry(raw_path, kind, label)
        if error:
            errors.append(error)

    return len(errors) == 0, errors


def validate_intersight_credentials(model_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate Intersight credential env vars when required by model content."""
    errors: List[str] = []

    if not _requires_intersight_credentials(model_data):
        return True, errors

    secret_key_path = os.environ.get("intersight_secret_key", "").strip()
    if not secret_key_path:
        errors.append(
            "Missing required environment variable 'intersight_secret_key' when intersight is defined "
            "or splunk_observability.intersight.enable is true."
        )
    else:
        secret_key_error = _validate_path_entry(
            secret_key_path,
            _PRIVATE_KEY_KIND,
            "env.intersight_secret_key",
        )
        if secret_key_error:
            errors.append(secret_key_error)

    api_key_id = os.environ.get("intersight_api_key_id", "").strip()
    if not api_key_id:
        errors.append(
            "Missing required environment variable 'intersight_api_key_id' when intersight is defined "
            "or splunk_observability.intersight.enable is true."
            + _format_export_command("intersight_api_key_id", "intersight_api_key_id")
        )
    else:
        api_key_error = _validate_value_against_schema(
            "intersight_api_key_id",
            api_key_id,
            "intersight_api_key_id",
        )
        if api_key_error:
            errors.append(
                api_key_error
                + _format_export_command("intersight_api_key_id", "intersight_api_key_id")
            )

    return len(errors) == 0, errors


def print_covered_variables(models: List[Dict[str, Any]], verbose: bool = False) -> None:
    """Print all sensitive variables that would be validated from all models."""
    all_required_vars: Dict[str, Tuple[str, Optional[str]]] = {}

    for idx, model_data in enumerate(models):
        required_vars = collect_required_sensitive_variables(model_data)
        all_required_vars.update(required_vars)

    if not all_required_vars:
        print(_colorize("\n  No sensitive variables found in models.", "33"))
        return

    # Group by schema key for readability
    schema_keys: Dict[Optional[str], Set[str]] = {}
    undocumented_vars: List[str] = []

    for env_var_name, (env_prefix, schema_key) in sorted(all_required_vars.items()):
        if schema_key is None:
            undocumented_vars.append(env_var_name)
        else:
            if schema_key not in schema_keys:
                schema_keys[schema_key] = set()
            schema_keys[schema_key].add(env_var_name)

    print(_colorize(f"\nSensitive Variables Covered ({len(all_required_vars)} total):\n", "1;32"))

    for schema_key in sorted([k for k in schema_keys.keys() if k is not None]):
        env_vars = sorted(schema_keys[schema_key])
        if _SENSITIVE_SCHEMA_PROPS.get(schema_key):
            description = _SENSITIVE_SCHEMA_PROPS[schema_key].get("description", "").split("\n")[0]
        else:
            description = ""

        print(_colorize(f"  {schema_key}:", "1;36"))
        if description and verbose:
            wrapped_desc = _wrap_cli_text(description, indent="    ")
            print(wrapped_desc)

        for env_var in env_vars:
            status = "✓" if os.environ.get(env_var) else "✗"
            print(f"    {status} {env_var}")

        print()

    # Show undocumented variables
    if undocumented_vars:
        print(_colorize(f"\nUndocumented Variables ({len(undocumented_vars)} not in schema):\n", "1;33"))
        for env_var in undocumented_vars:
            status = "✓" if os.environ.get(env_var) else "✗"
            print(f"  {status} {env_var}")
        print()


def normalize_model_sections(model_data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a model containing only known top-level role sections.

    Supports both root-level and spec-scoped documents.
    """
    source = model_data.get("spec") if isinstance(model_data.get("spec"), dict) else model_data
    normalized: Dict[str, Any] = {}
    for top_key in _MODEL_TOP_KEYS:
        if isinstance(source.get(top_key), dict):
            normalized[top_key] = source[top_key]
    return normalized


def merge_dicts(base: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge dictionaries and extend lists."""
    result = dict(base)
    for key, value in new.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        elif isinstance(result.get(key), list) and isinstance(value, list):
            result[key] = result[key] + value
        else:
            result[key] = value
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Validate all sensitive environment variables required by all data models "
            "(intersight_ucs_provision, openshift_install, everpure, splunk_observability)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--models",
        type=str,
        nargs="+",
        required=True,
        help="Paths to one or more merged model JSON files",
    )
    parser.add_argument(
        "--schema",
        type=str,
        help="Path to JSON schema (default: schemas/sensitive/variables.json)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print descriptions for each sensitive variable type",
    )

    args = parser.parse_args()

    try:
        load_schema(Path(args.schema) if args.schema else None)

        # Load all models
        all_models: List[Dict[str, Any]] = []
        for model_path_str in args.models:
            model_path = Path(model_path_str)
            if not model_path.exists():
                print(
                    f"ERROR: Model file not found: {model_path}",
                    file=sys.stderr,
                )
                sys.exit(1)

            with open(model_path, encoding="utf-8") as model_file:
                raw_model = json.load(model_file)
                all_models.append(normalize_model_sections(raw_model))

        # Print what would be covered
        print_covered_variables(all_models, verbose=args.verbose)

        # Validate all models together
        merged_model: Dict[str, Any] = {}
        for model in all_models:
            merged_model = merge_dicts(merged_model, model)

        validation_ok, missing_env_vars, validation_errors, _found_sensitive_vars = (
            validate_all_sensitive_variables(merged_model)
        )
        certs_ok, certificate_errors = validate_certificate_files(merged_model)
        intersight_creds_ok, intersight_credential_errors = validate_intersight_credentials(merged_model)

        all_ok = validation_ok and certs_ok and intersight_creds_ok

        combined_errors = list(validation_errors)
        combined_errors.extend(certificate_errors)
        combined_errors.extend(intersight_credential_errors)

        combined_count = len(missing_env_vars) + len(certificate_errors) + len(intersight_credential_errors)

        if all_ok:
            print(
                _colorize(
                    "\n✓ All required sensitive environment variables and certificate/private-key files are valid.",
                    "1;32",
                )
            )
            sys.exit(0)

        print(
            _colorize(
                (
                    "\n✗ ERROR: "
                    f"{combined_count} validation issue(s) found "
                    "(sensitive variables and/or certificate/private-key files):\n"
                ),
                "1;31",
            ),
            file=sys.stderr,
        )
        for msg in combined_errors:
            print(msg, file=sys.stderr)
        print(file=sys.stderr)
        sys.exit(1)

    except FileNotFoundError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as err:
        print(f"ERROR: Invalid JSON: {err}", file=sys.stderr)
        sys.exit(1)
    except ValueError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)
