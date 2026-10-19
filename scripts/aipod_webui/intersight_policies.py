"""Policy secrets for the Intersight and Everpure pages: the vault values each policy references by number in the
YAML."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .vault import SecretField

MAX_ENTRIES = 16
STATE_KEY = "policy_secrets"
# Shared services stores the LDAP bind password once; the automation also receives it as ldap_binding_password_1.
LDAP_SOURCE = ("openshift", "ldap_bind_password")
LDAP_ALIAS = "ldap_binding_password_1"


@dataclass(frozen=True)
class PolicySecrets:
    key: str
    title: str
    fields: tuple[tuple[str, str], ...]
    multi: bool = False
    help: str = ""
    linked: bool = False
    # Each field has its own number of entries (SNMP communities, users, and passwords are independent).
    per_field: bool = False
    # Where the YAML references each field, when it differs from the page-independent YAML_KEYS entry.
    yaml: tuple[tuple[str, str], ...] = ()


POLICIES = {item.key: item for item in (
    PolicySecrets("certificate_management", "Certificate Management", (("private_key_passphrase", "Private key passphrase"),),
                  help="Upload the certificate and key files below and use the paths shown as certificate_file / "
                       "private_key_file."),
    PolicySecrets("drive_security", "Drive Security", (
        ("drive_security_authentication_password", "KMIP authentication password"),
        ("drive_security_current_security_key_passphrase", "Current security key passphrase"),
        ("drive_security_new_security_key_passphrase", "New security key passphrase"))),
    PolicySecrets("firmware_authenticate", "Firmware Authentication", (
        ("cco_user", "Cisco.com user (email)"), ("cco_password", "Cisco.com password")),
        help="Cisco.com account used to download firmware from cisco.com."),
    PolicySecrets("ipmi_over_lan", "IPMI over LAN", (("ipmi_encryption_key", "IPMI encryption key"),),
                  help="Even number of hexadecimal characters, up to 40."),
    PolicySecrets("iscsi_boot", "iSCSI Boot", (("iscsi_boot_password", "iSCSI CHAP password"),), multi=True),
    PolicySecrets("ldap", "LDAP", (("ldap_binding_password", "LDAP binding password"),), linked=True,
                  help="Uses the LDAP bind password from Initial Inventory - Shared services (ldap_binding_password: 1)."),
    PolicySecrets("local_user", "Local User", (("local_user_password", "Local user password"),), multi=True,
                  help="One password per number; reference each user's password as password: 1, 2, ..."),
    PolicySecrets("mac_sec", "MACsec", (
        ("mac_sec_primary_key_chain_secret", "Primary key chain secret"),
        ("mac_sec_fallback_key_chain_secret", "Fallback key chain secret")), multi=True),
    PolicySecrets("persistent_memory", "Persistent Memory", (("persistent_passphrase", "Security passphrase"),)),
    PolicySecrets("snmp", "SNMP", (
        ("snmp_community_string", "Community string"),
        ("snmp_access_community_string", "Access community string"),
        ("snmp_trap_community", "Trap community"),
        ("snmp_password", "Password"),
        ("snmp_user_auth_password", "User auth password"),
        ("snmp_user_privacy_password", "User privacy password")), multi=True, per_field=True,
        help="Set how many of each value the SNMP policy references (0 for none); users reference theirs as "
             "auth_password: 1, privacy_password: 1, ..."),
    PolicySecrets("switch_control", "Switch Control", (("switch_control_aes_primary_key", "AES primary key"),)),
    PolicySecrets("virtual_media", "Virtual Media", (("vmedia_password", "Virtual media mount password"),), multi=True),
    PolicySecrets("everpure_certificates", "Array Certificates", (("private_key_passphrase", "Private key passphrase"),),
                  multi=True, help="Upload the certificate and key files below. Add a passphrase for each encrypted "
                                   "private key; leave Entries at 1 and the value empty if none are encrypted.",
                  yaml=(("private_key_passphrase", "array_certificates[].private_key_passphrase"),)),
    PolicySecrets("everpure_ldap", "Directory Service (LDAP)", (("ldap_binding_password", "LDAP binding password"),),
                  linked=True, help="Uses the LDAP bind password from Initial Inventory - Shared services "
                                    "(bind_password: 1)."),
    PolicySecrets("everpure_local_user", "Local Users", (("local_user_password", "Local user password"),), multi=True,
                  help="One password per number; reference each user's password as password: 1, 2, ...",
                  yaml=(("local_user_password", "settings.security.users[].password"),)),
    PolicySecrets("everpure_snmp", "SNMP", (
        ("everpure_snmp_community", "Community string"),
        ("everpure_snmp_auth_passphrase", "Auth passphrase"),
        ("everpure_snmp_privacy_passphrase", "Privacy passphrase")), multi=True, per_field=True,
        help="Set how many of each value the SNMP managers and agent reference (0 for none): community: 1, "
             "auth_passphrase: 1, privacy_passphrase: 1, ...",
        yaml=(("everpure_snmp_community", "v2c[].community or edit_snmp_agent.community"),
              ("everpure_snmp_auth_passphrase", "v3[].auth_passphrase or edit_snmp_agent.auth_passphrase"),
              ("everpure_snmp_privacy_passphrase", "v3[].privacy_passphrase or edit_snmp_agent.privacy_passphrase"))),
)}

PAGE_POLICIES = {
    "intersight-domains": ("certificate_management", "ipmi_over_lan", "ldap", "local_user", "mac_sec", "snmp",
                           "switch_control"),
    "intersight-servers": ("certificate_management", "drive_security", "firmware_authenticate", "ipmi_over_lan",
                           "iscsi_boot", "ldap", "local_user", "persistent_memory", "snmp", "virtual_media"),
    "everpure": ("everpure_certificates", "everpure_ldap", "everpure_local_user", "everpure_snmp"),
}
# Vault section that stores each page's policy values (local_user_password_N exists in both).
PAGE_SECTIONS = {"everpure": "everpure"}
CERTIFICATE_POLICIES = frozenset({"certificate_management", "everpure_certificates"})

# Fields that are optional within an enabled policy (only some apply to a given SNMP / drive security setup).
OPTIONAL_PREFIXES = frozenset({
    "snmp_community_string", "snmp_access_community_string", "snmp_trap_community", "snmp_password",
    "snmp_user_auth_password", "snmp_user_privacy_password", "drive_security_new_security_key_passphrase",
    "private_key_passphrase", "everpure_snmp_community", "everpure_snmp_auth_passphrase",
    "everpure_snmp_privacy_passphrase",
})

# Where the policy YAML references each vault value (the key name differs from the vault prefix for most policies).
YAML_KEYS = {
    "drive_security_authentication_password": "remote_key_management ... password",
    "drive_security_current_security_key_passphrase": "current_security_key_passphrase",
    "drive_security_new_security_key_passphrase": "manual_key.new_security_key_passphrase",
    "ipmi_encryption_key": "encryption_key",
    "iscsi_boot_password": "password",
    "local_user_password": "users[].password",
    "mac_sec_primary_key_chain_secret": "mac_sec_primary_key_chain ... secret",
    "mac_sec_fallback_key_chain_secret": "mac_sec_fallback_key_chain ... secret",
    "snmp_access_community_string": "access_community_string",
    "snmp_trap_community": "trap_community_string or snmp_trap_destinations[].community_string",
    "snmp_user_auth_password": "snmp_users[].auth_password",
    "snmp_user_privacy_password": "snmp_users[].privacy_password",
    "switch_control_aes_primary_key": "aes_primary_key",
}

CERTIFICATE_SUFFIXES = (".crt", ".cer", ".pem", ".key")
CERTIFICATE_MAX_BYTES = 256 * 1024


def field_key(policy: str, prefix: str) -> str:
    return f"{policy}.{prefix}"


def field_count(saved: dict, policy: str, prefix: str) -> int:
    """Entries of one field of a per-field policy; until set, the policy's own entry count (older saved state)."""
    value = saved.get(field_key(policy, prefix), saved.get(policy) or 1)
    try:
        return max(0, min(int(value), MAX_ENTRIES))
    except (TypeError, ValueError):
        return 1


def vault_section(page: str) -> str:
    return PAGE_SECTIONS.get(page, "intersight")


def certificate_dir(output_dir: Path, page: str = "") -> Path:
    """Where uploaded certificate files live; the YAML references them by absolute path."""
    return output_dir / "certificates" / ("everpure" if page == "everpure" else "intersight")


def certificate_file_name(name: str) -> str:
    """Safe file name that keeps a certificate / key suffix (``.pem`` when the upload has none)."""
    base = Path(name or "").name
    stem, dot, suffix = base.rpartition(".")
    if not dot or f".{suffix.lower()}" not in CERTIFICATE_SUFFIXES:
        stem, suffix = base, "pem"
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._") or "certificate"
    return f"{stem}.{suffix.lower()}"


def check_certificate(content: bytes) -> tuple[str, str]:
    """(text, kind) for a PEM upload; kind is ``private_key`` or ``certificate``. Raises ValueError otherwise."""
    if len(content) > CERTIFICATE_MAX_BYTES:
        raise ValueError("file is larger than 256 KB")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("not a PEM text file") from error
    if "-----BEGIN" not in text:
        raise ValueError("not a PEM file (no -----BEGIN line)")
    kind = "private_key" if re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", text) else "certificate"
    return (text if text.endswith("\n") else text + "\n"), kind


def counts(state: dict, page: str) -> dict[str, int]:
    """Enabled policy -> number of entries (1 for single-value policies), from the page state."""
    saved = state.get(STATE_KEY) if isinstance(state.get(STATE_KEY), dict) else {}
    result = {}
    for key in PAGE_POLICIES.get(page, ()):
        try:
            count = int(saved.get(key) or 0)
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            result[key] = min(count, MAX_ENTRIES) if POLICIES[key].multi else 1
    return result


def fields(state: dict, page: str) -> list[SecretField]:
    """Credential inputs for the enabled policies (LDAP is entered on Shared services)."""
    result = []
    section = vault_section(page)
    for key, count in counts(state, page).items():
        policy = POLICIES[key]
        if policy.linked:
            continue
        saved = state.get(STATE_KEY) if isinstance(state.get(STATE_KEY), dict) else {}
        entries = [(prefix, label, number) for prefix, label in policy.fields
                   for number in range(1, field_count(saved, key, prefix) + 1)] if policy.per_field else [
            (prefix, label, number) for number in range(1, count + 1) for prefix, label in policy.fields]
        for prefix, label, number in entries:
            name = f"{prefix}_{number}"
            suffix = f" #{number}" if policy.multi else ""
            result.append(SecretField(name, f"{policy.title}: {label}{suffix} (vault key {name})",
                                      ((section, name),),
                                      help=f"Reference it in the YAML as "
                                           f"{dict(policy.yaml).get(prefix) or YAML_KEYS.get(prefix, prefix)}: {number}.",
                                      optional=prefix in OPTIONAL_PREFIXES))
    return result

