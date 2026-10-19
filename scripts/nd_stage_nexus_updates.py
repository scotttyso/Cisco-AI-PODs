#!/usr/bin/env python3
"""Create Nexus Dashboard update groups (named multi-switch or per-switch) and stage NX-OS images."""

import argparse
import copy
import getpass
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote

import requests
import urllib3
import yaml


API_PREFIX = "/api/v1"
REPORT_CHECKS = "/manage/updateReports/reportChecks"
SWITCHES = "/manage/fabricSoftware/switches"
IMAGES = "/manage/fabricSoftware/images"
DEFAULT_VAULT_PASSWORD_FILE = Path.home() / ".config" / "cisco-ai-pods" / "vault-password"


@dataclass(frozen=True)
class UpgradeRule:
    models: Tuple[str, ...]
    source_version: str
    target_version: str


DEFAULT_UPGRADE_RULES = (
    UpgradeRule(("*",), "9.3", "9.3.16"),
    UpgradeRule(("*93180YC-EX*", "*93108TC-EX*"), "10.3", "10.3.10"),
    UpgradeRule(("*",), "10.3", "10.6.4"),
)


@dataclass(frozen=True)
class Switch:
    serial: str
    name: str
    address: str
    model: str
    version: str
    platform: str
    vpc_peer: str
    vpc_role: str
    fabric: str

    @property
    def is_vpc(self) -> bool:
        role = self.vpc_role.casefold()
        peer = self.vpc_peer.casefold()
        return role in {"primary", "secondary"} or peer not in {
            "",
            "none",
            "n/a",
            "na",
            "unknown",
        }


@dataclass(frozen=True)
class Plan:
    switches: Tuple[Switch, ...]
    target_version: str
    image_name: str
    group_name: str
    check_names: Tuple[str, ...]

    @property
    def fabric(self) -> str:
        return self.switches[0].fabric

    @property
    def serials(self) -> List[str]:
        return [switch.serial for switch in self.switches]


class NexusDashboard:
    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        verify_tls: bool,
        request_timeout: int,
        domain: str = "local",
    ):
        self.url = url.rstrip("/")
        self.session = requests.Session()
        self.session.verify = verify_tls
        self.request_timeout = request_timeout
        if not verify_tls:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = self.session.post(
            f"{self.url}{API_PREFIX}/infra/login",
            json={"domain": domain, "userName": username, "userPasswd": password},
            timeout=(10, self.request_timeout),
        )
        self._check(response)
        try:
            token = response.json().get("jwttoken") or response.json().get("token")
        except ValueError:
            token = None
        auth_cookies = [cookie for cookie in self.session.cookies if cookie.name == "AuthCookie"]
        if token and not auth_cookies:
            self.session.cookies.set("AuthCookie", token)
            auth_cookies = [cookie for cookie in self.session.cookies if cookie.name == "AuthCookie"]
        if not auth_cookies:
            raise RuntimeError("ND login succeeded but did not return an AuthCookie token")

    @staticmethod
    def _check(response: requests.Response) -> None:
        if not response.ok:
            raise RuntimeError(
                f"ND API returned HTTP {response.status_code}: {response.text[:1200]}"
            )

    def request(
        self, method: str, path: str, payload: Optional[Dict[str, Any]] = None
    ) -> Any:
        print(f"ND API {method.upper()} {path}", flush=True)
        try:
            response = self.session.request(
                method,
                f"{self.url}{API_PREFIX}{path}",
                json=payload,
                timeout=(10, self.request_timeout),
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"ND API {method.upper()} {path} failed: {exc}") from exc
        self._check(response)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text


def walk_records(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_records(child)


def field(item: Dict[str, Any], *names: str) -> str:
    lowered = {str(key).lower(): value for key, value in item.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def load_switches(payload: Any) -> List[Switch]:
    result = {}
    for item in walk_records(payload):
        serial = field(item, "switchId", "serialNumber", "serial")
        fabric = field(item, "fabricName")
        if not serial or not fabric:
            continue
        result[serial] = Switch(
            serial=serial,
            name=field(item, "switchName", "name") or serial,
            address=field(item, "switchIp", "ipAddress", "managementIpAddress"),
            model=field(item, "switchModel", "model", "productId"),
            version=field(item, "switchVersion", "softwareVersion", "version"),
            platform=field(item, "switchPlatform", "platform"),
            vpc_peer=field(item, "vpcPeer"),
            vpc_role=field(item, "vpcRole"),
            fabric=fabric,
        )
    return sorted(result.values(), key=lambda switch: (switch.fabric, switch.name))


def target_for(
    switch: Switch, upgrade_rules: Sequence[UpgradeRule] = DEFAULT_UPGRADE_RULES
) -> Optional[str]:
    model = switch.model.upper()
    version = switch.version.strip()
    is_n9k = switch.platform.casefold() in {"n9k", "nexus 9000"} or model.startswith("N9K")
    if not is_n9k:
        return None
    for rule in upgrade_rules:
        if any(fnmatchcase(model, pattern.upper()) for pattern in rule.models) and re.match(
            rf"^{re.escape(rule.source_version)}(?:[.(]|$)", version
        ):
            return rule.target_version
    return None


def version_key(value: str) -> Tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", value))


def select_image(payload: Any, switch: Switch, target: str) -> str:
    candidates = []
    for item in walk_records(payload):
        image_name = field(item, "imageName")
        if not image_name:
            continue
        image_version = field(item, "releaseVersion", "imageVersion")
        if not image_version:
            image_version = image_name
        platform = field(item, "platform").casefold()
        present = field(item, "imagePresent").casefold()
        image_subtype = field(item, "imageSubType").casefold()
        if version_key(image_version) != version_key(target):
            continue
        if platform and platform not in {"n9k", "nexus 9000"}:
            continue
        if present and present != "present":
            continue
        if image_subtype and image_subtype not in {"nx-os", "nxos"}:
            continue
        candidates.append(image_name)

    candidates = sorted(set(candidates))
    if len(candidates) != 1:
        found = ", ".join(candidates) if candidates else "none"
        raise ValueError(
            f"Expected one uploaded N9K image for {target} on {switch.name}; found {found}. "
            "Upload the target image to ND and remove any ambiguous duplicate."
        )
    return candidates[0]


REQUESTED_CHECK_NAMES = (
    "Diag_module",
    "All_filesystem_free_space",
    "General_log_messages",
    "BGP_stability",
    "Management_console",
    "vPC_state",
    "BGP_state",
    "HSRP_mgo_state_active",
    "Module_status",
    "Modules_health_and_backup_power",
    "Interface_status",
    "OSPF_stability",
    "vPC_sticky_bit",
    "Dual_supervisor_redundancy",
    "NVRAM_log_messages",
    "HSRP_mgo_state_standby",
    "vPC_secondary_role",
    "OSPF_state",
)
# Custom checks with no ND built-in source; cloned from NEW_CHECK_TEMPLATE for the schema.
NEW_CHECKS = {
    "Running_config": "show running-config",
    "Default_route": "show ip route 0.0.0.0 vrf all",
    "mac_address": "show mac address dynamic | sort",
}
NEW_CHECK_TEMPLATE = "Interface_status"
POST_UPDATE_DELAY = 360
CUSTOM_CHECK_PREFIX = "nxos_"
GROUP_NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,48}")


def select_switches(switches: Sequence[Switch], selectors: Sequence[str]) -> List[Switch]:
    if selectors:
        selected = []
        for selector in selectors:
            matches = [
                switch
                for switch in switches
                if selector.casefold()
                in {switch.serial.casefold(), switch.name.casefold(), switch.address.casefold()}
            ]
            if len(matches) != 1:
                raise ValueError(f"Device selector {selector!r} matched {len(matches)} switches")
            selected.append(matches[0])
        if len({switch.serial for switch in selected}) != len(selected):
            raise ValueError("A switch was selected more than once")
        return selected

    print("Available switches:")
    for index, switch in enumerate(switches, 1):
        print(
            f"{index:>3}. {switch.name:<24} {switch.address:<16} "
            f"{switch.model:<24} {switch.version:<12} "
            f"{'vPC' if switch.is_vpc else 'standalone':<10} {switch.fabric}"
        )
    raw = input("Select switch numbers (comma-separated): ").strip()
    try:
        indexes = [int(value.strip()) for value in raw.split(",") if value.strip()]
    except ValueError as exc:
        raise ValueError("Enter a comma-separated list of switch numbers") from exc
    if not indexes or any(index < 1 or index > len(switches) for index in indexes):
        raise ValueError("Selection is empty or contains an invalid switch number")
    if len(set(indexes)) != len(indexes):
        raise ValueError("A switch was selected more than once")
    return [switches[index - 1] for index in indexes]


def load_check_catalog(client: NexusDashboard):
    payload = client.request("GET", REPORT_CHECKS)
    current = {
        field(item, "reportCheckName"): item
        for item in walk_records(payload)
        if field(item, "reportCheckName")
    }
    missing = [name for name in REQUESTED_CHECK_NAMES if name not in current]
    if missing:
        raise ValueError("ND is missing required existing report checks: " + ", ".join(missing))
    checks = [
        dict(
            copy.deepcopy(current[name]),
            reportCheckName=CUSTOM_CHECK_PREFIX + name,
            checkType="custom",
            postUpdateDelay=POST_UPDATE_DELAY,
        )
        for name in REQUESTED_CHECK_NAMES
    ]
    checks += [
        dict(
            copy.deepcopy(current[NEW_CHECK_TEMPLATE]),
            reportCheckName=CUSTOM_CHECK_PREFIX + name,
            reportCheckDescription=command,
            checkType="custom",
            cliCommand=command,
            postUpdateDelay=POST_UPDATE_DELAY,
            advancedChecks=[],
        )
        for name, command in NEW_CHECKS.items()
    ]
    for check in checks:
        check["advancedChecks"] = [
            entry for entry in check.get("advancedChecks", [])
            if entry.get("checkMustContains") or entry.get("checkMustNotContains")
        ]
    return current, checks


def check_applies_to_switch(check: Dict[str, Any], switch: Switch) -> bool:
    name = field(check, "reportCheckName")
    if name.startswith(CUSTOM_CHECK_PREFIX):
        name = name[len(CUSTOM_CHECK_PREFIX):]
    if name == "Dual_supervisor_redundancy":
        return "9508" in switch.model.upper()
    is_vpc_check = any(
        "vpc" in field(check, key).casefold()
        for key in ("reportCheckName", "cliCommand", "reportCheckDescription")
    )
    return switch.is_vpc or not is_vpc_check


def ensure_check_catalog(
    client: NexusDashboard,
    current: Dict[str, Dict[str, Any]],
    checks: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    for desired in checks:
        name = desired["reportCheckName"]
        if name not in current:
            print(f"Creating custom report check {name}", flush=True)
            client.request("POST", REPORT_CHECKS, {"updateChecks": [dict(desired, postUpdateDelay=0)]})
        path = "{}/{}".format(REPORT_CHECKS, quote(name, safe=""))
        saved = client.request("GET", path)
        matches = [item for item in walk_records(saved) if field(item, "reportCheckName") == name]
        if len(matches) != 1:
            raise RuntimeError(f"Cannot verify saved custom check {name}")
        definition = matches[0]
        definition["advancedChecks"] = [
            entry for entry in definition.get("advancedChecks", [])
            if entry.get("checkMustContains") or entry.get("checkMustNotContains")
        ]
        expected = {key: value for key, value in desired.items() if key != "postUpdateDelay"}
        if any(definition.get(key) != value for key, value in expected.items()):
            raise RuntimeError(f"Existing custom check {name} differs from its source; refusing to overwrite it")
        if definition.get("postUpdateDelay") != POST_UPDATE_DELAY:
            client.request(
                "PUT",
                path,
                dict(definition, postUpdateDelay=POST_UPDATE_DELAY),
            )
    verified, refreshed = load_check_catalog(client)
    if any(verified[check["reportCheckName"]].get("postUpdateDelay") != POST_UPDATE_DELAY for check in checks):
        raise RuntimeError(f"ND did not retain the requested {POST_UPDATE_DELAY}-second report delays")
    return refreshed


def device_group_name(switch: Switch) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "-", switch.name).strip("-")[:30]
    serial_suffix = re.sub(r"[^A-Za-z0-9]", "", switch.serial)[-8:]
    return f"{safe_name}-{serial_suffix}".strip("-")[:48]


def make_plan(
    group_name: str, members: Sequence[Switch], checks: Sequence[Dict[str, Any]], images: Any,
    upgrade_rules: Sequence[UpgradeRule] = DEFAULT_UPGRADE_RULES,
) -> Optional[Plan]:
    targets = [target_for(switch, upgrade_rules) for switch in members]
    if not any(targets):
        return None
    outside = [switch.name for switch, target in zip(members, targets) if not target]
    if outside:
        raise ValueError(f"Update group {group_name}: {', '.join(outside)} outside the N9K upgrade rules")
    fabrics = sorted({switch.fabric for switch in members})
    if len(fabrics) != 1:
        raise ValueError(f"Update group {group_name} spans fabrics: {', '.join(fabrics)}")
    images_by_switch = {
        switch.name: select_image(images, switch, target) for switch, target in zip(members, targets)
    }
    if len(set(images_by_switch.values())) != 1:
        detail = ", ".join(f"{name}={image}" for name, image in images_by_switch.items())
        raise ValueError(f"Update group {group_name} needs different images: {detail}")
    check_sets = {
        tuple(field(check, "reportCheckName") for check in checks if check_applies_to_switch(check, switch))
        for switch in members
    }
    if len(check_sets) != 1:
        raise ValueError(
            f"Update group {group_name} mixes switches that need different checks "
            "(vPC vs standalone, or 9508 vs other models)"
        )
    return Plan(
        switches=tuple(members),
        target_version=targets[0],
        image_name=next(iter(images_by_switch.values())),
        group_name=group_name,
        check_names=check_sets.pop(),
    )


def fabric_path(fabric: str, suffix: str) -> str:
    return "/manage/fabrics/{}/{}".format(quote(fabric, safe=""), suffix)


def group_path(fabric: str, group: str) -> str:
    return fabric_path(fabric, "updateGroups/{}".format(quote(group, safe="")))


def load_vault_password(vault_file: Path, password_file: Path) -> str:
    executable = shutil.which("ansible-vault")
    if executable is None:
        raise RuntimeError("ansible-vault was not found on PATH")
    vault_file = vault_file.expanduser().resolve()
    password_file = password_file.expanduser().resolve()
    if not vault_file.is_file() or not password_file.is_file():
        raise ValueError("Vault file and vault password file must both exist")
    if password_file.stat().st_mode & 0o777 != 0o600:
        raise ValueError("Vault password file must have mode 0600")
    with vault_file.open("rb") as stream:
        if not stream.readline().startswith(b"$ANSIBLE_VAULT;"):
            raise ValueError("--vault-file must be an encrypted Ansible Vault file")
    try:
        result = subprocess.run(
            [executable, "view", "--vault-password-file", str(password_file), str(vault_file)],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Unable to decrypt ND credentials from Ansible Vault") from exc
    try:
        document = yaml.safe_load(result.stdout)
    except yaml.YAMLError:
        raise ValueError("Decrypted vault must contain valid YAML") from None
    section = document.get("nexus_dashboard") if isinstance(document, dict) else None
    password = section.get("nexus_dashboard_password") if isinstance(section, dict) else None
    if not isinstance(password, str) or not password:
        raise ValueError("Vault must contain nexus_dashboard.nexus_dashboard_password")
    return password


def apply_plan(
    client: NexusDashboard,
    plan: Plan,
    checks: Sequence[Dict[str, Any]],
    attach_serials: Sequence[str],
    run_pre_report: bool = False,
) -> None:
    fabric = plan.fabric
    if attach_serials:
        client.request(
            "POST",
            fabric_path(fabric, "softwareUpdatePlan/actions/attachGroup"),
            {
                "attachUpdateGroups": [
                    {
                        "forceCreated": True,
                        "switchIds": list(attach_serials),
                        "updateGroupName": plan.group_name,
                    }
                ]
            },
        )
    client.request(
        "PUT",
        group_path(fabric, plan.group_name),
        {
            "analysis": "noAnalysis",
            "contingency": "pause",
            "execution": "serial",
            "isDisruptiveUpdate": True,
            "isMaintenance": True,
            "reportSelection": "advanced",
            "reports": "useAdvancePreAndPostReports",
            "updateGroupName": plan.group_name,
            "updateGroupSwitches": plan.serials,
            "installImageData": {
                "nosImageName": plan.image_name,
                "uninstallPackage": False,
            },
            "updateReportChecks": [{"reportCheckName": name} for name in plan.check_names],
        },
    )
    saved_group = client.request("GET", group_path(fabric, plan.group_name))
    saved_checks = saved_group.get("updateReportChecks", []) if isinstance(saved_group, dict) else []
    saved_names = [field(item, "reportCheckName") for item in saved_checks]
    if set(saved_names) != set(plan.check_names) or len(saved_names) != len(plan.check_names):
        raise RuntimeError(
            f"Group {plan.group_name} did not retain the custom-only check selection; "
            "report execution and staging were not requested"
        )
    if run_pre_report:
        client.request(
            "POST",
            fabric_path(fabric, "updateReportActions/startPreReport"),
            {"updateGroupName": plan.group_name},
        )
        print(f"Pre-report requested for {plan.group_name}; check execution results in ND")
    client.request(
        "POST",
        fabric_path(fabric, "softwareUpdatePlan/actions/stage"),
        {"updateGroupNames": [plan.group_name]},
    )


def load_upgrade_rules(raw: Any) -> Tuple[UpgradeRule, ...]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("upgrade_rules must be a nonempty list")
    rules = []
    for index, rule in enumerate(raw, 1):
        location = f"upgrade_rules entry {index}"
        if not isinstance(rule, dict) or set(rule) != {"models", "source_version", "target_version"}:
            raise ValueError(f"{location} requires only models, source_version, and target_version")
        models = rule["models"]
        if not isinstance(models, list) or not models or any(
            not isinstance(model, str) or not model.strip() for model in models
        ):
            raise ValueError(f"{location}.models must be a nonempty list of model patterns")
        for key in ("source_version", "target_version"):
            value = rule[key]
            if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d+)+", value):
                raise ValueError(f"{location}.{key} must be a quoted dotted version, e.g. '10.6'")
        rules.append(UpgradeRule(tuple(model.strip() for model in models),
                                 rule["source_version"], rule["target_version"]))
    return tuple(rules)


def apply_config(args: argparse.Namespace) -> argparse.Namespace:
    settings = {}
    selectors = {}
    raw_groups = {}
    args.upgrade_rules = DEFAULT_UPGRADE_RULES
    if args.config:
        try:
            with args.config.expanduser().open(encoding="utf-8") as stream:
                document = yaml.safe_load(stream)
        except yaml.YAMLError:
            raise ValueError("Input sheet must contain valid YAML") from None
        if not isinstance(document, dict):
            raise ValueError("Input sheet must be a YAML mapping")
        if set(document) - {"nexus_dashboard", "switches", "update_groups", "upgrade_rules"}:
            raise ValueError(
                "Input sheet accepts only nexus_dashboard, switches, update_groups, and upgrade_rules sections"
            )
        if "upgrade_rules" in document:
            args.upgrade_rules = load_upgrade_rules(document["upgrade_rules"])
        settings = document.get("nexus_dashboard") or {}
        selectors = document.get("switches") or {}
        raw_groups = document.get("update_groups") or {}
        if not all(isinstance(value, dict) for value in (settings, selectors, raw_groups)):
            raise ValueError("nexus_dashboard, switches, and update_groups must be YAML mappings")
        if set(settings) - {
            "host", "username", "domain", "verify_ssl", "timeout", "password_env",
            "vault_file", "vault_password_file",
        } or set(selectors) - {"hosts"}:
            raise ValueError("Input sheet contains unsupported settings; plaintext passwords are not supported")

    defaults = {
        "nd_url": settings.get("host", "https://nd.example.com"),
        "username": settings.get("username", "admin"),
        "domain": settings.get("domain", "local"),
        "request_timeout": settings.get("timeout", 600),
        "password_env": settings.get("password_env", "NEXUS_PASSWORD"),
        "vault_file": settings.get("vault_file"),
        "vault_password_file": settings.get("vault_password_file", DEFAULT_VAULT_PASSWORD_FILE),
        "device": selectors.get("hosts", []),
    }
    for name, value in defaults.items():
        if getattr(args, name) is None:
            setattr(args, name, value)
    for name in ("nd_url", "username", "domain", "password_env"):
        if not isinstance(getattr(args, name), str) or not getattr(args, name).strip():
            raise ValueError(f"{name} must be a nonempty string")
    if not args.nd_url.startswith("https://"):
        if "://" in args.nd_url:
            raise ValueError("Nexus Dashboard URL must use HTTPS")
        args.nd_url = "https://" + args.nd_url
    verify_ssl = settings.get("verify_ssl", True)
    if not isinstance(verify_ssl, bool):
        raise ValueError("verify_ssl must be true or false")
    if args.insecure is None:
        args.insecure = not verify_ssl
    if isinstance(args.request_timeout, bool) or not isinstance(args.request_timeout, int) or args.request_timeout <= 0:
        raise ValueError("timeout must be a positive integer")
    if not isinstance(args.device, list) or any(not isinstance(host, str) or not host.strip() for host in args.device):
        raise ValueError("switches.hosts must be a list of switch names, IPs, or serials")
    if raw_groups and selectors.get("hosts"):
        raise ValueError("Use either switches.hosts or update_groups, not both")
    args.update_groups = []
    for name, group in raw_groups.items():
        if not isinstance(name, str) or not GROUP_NAME_RE.fullmatch(name):
            raise ValueError(f"Update group name {name!r} must be 1-48 letters, digits, '_' or '-'")
        hosts = group.get("hosts") if isinstance(group, dict) else None
        if not isinstance(group, dict) or set(group) - {"hosts"}:
            raise ValueError(f"update_groups.{name} accepts only a hosts list")
        if not isinstance(hosts, list) or not hosts or any(not isinstance(h, str) or not h.strip() for h in hosts):
            raise ValueError(f"update_groups.{name}.hosts must be a nonempty list of switch names, IPs, or serials")
        args.update_groups.append((name, hosts))
    for name in ("vault_file", "vault_password_file"):
        value = getattr(args, name)
        if value is None:
            continue
        if not isinstance(value, (str, Path)) or not str(value).strip():
            raise ValueError(f"{name} must be a nonempty path")
        path = Path(value).expanduser()
        if args.config and isinstance(value, str) and not path.is_absolute():
            path = args.config.expanduser().resolve().parent / path
        setattr(args, name, path)
    return args


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select Nexus switches, create update groups, and stage NX-OS images."
    )
    parser.add_argument("--config", type=Path, help="YAML input sheet; command-line settings override YAML")
    parser.add_argument("--nd-url")
    parser.add_argument("--username")
    parser.add_argument("--domain", help="ND authentication domain (default: local)")
    parser.add_argument("--password-env", help="Password environment variable (default: NEXUS_PASSWORD)")
    parser.add_argument(
        "--device", action="append",
        help="Switch name, IP, or serial for a per-device group; repeatable; overrides YAML update_groups",
    )
    parser.add_argument("--apply", action="store_true", help="Create groups and stage images; default only plans")
    tls = parser.add_mutually_exclusive_group()
    tls.add_argument("--insecure", action="store_true", default=None, help="Skip TLS certificate verification")
    tls.add_argument("--verify-tls", action="store_false", dest="insecure", default=None, help="Verify TLS even if disabled in YAML")
    parser.add_argument("--vault-file", type=Path, help="Encrypted Ansible Vault with ND credentials")
    parser.add_argument(
        "--vault-password-file", type=Path,
        help="Ansible Vault password file (must have mode 0600)",
    )
    parser.add_argument(
        "--run-pre-report", action="store_true",
        help="With --apply, request execution of the group's pre-update checks before staging",
    )
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=None,
        help="Per-request read timeout in seconds (default: 600)",
    )
    args = parser.parse_args(argv)
    try:
        return apply_config(args)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


def main() -> int:
    args = parse_args()
    try:
        if args.request_timeout <= 0:
            raise ValueError("--request-timeout must be greater than zero")
        password = (
            load_vault_password(args.vault_file, args.vault_password_file)
            if args.vault_file
            else os.environ.get(args.password_env) or getpass.getpass("ND password: ")
        )
        client = NexusDashboard(
            args.nd_url,
            args.username,
            password,
            not args.insecure,
            args.request_timeout,
            args.domain,
        )
        switches = load_switches(client.request("GET", SWITCHES))
        if not switches:
            raise ValueError("ND returned no switches from /manage/fabricSoftware/switches")
        if args.device or not args.update_groups:
            groups = [(device_group_name(s), [s]) for s in select_switches(switches, args.device)]
        else:
            groups = [(name, select_switches(switches, hosts)) for name, hosts in args.update_groups]
            serials = [switch.serial for _, members in groups for switch in members]
            if len(set(serials)) != len(serials):
                raise ValueError("A switch is listed in more than one update group")
        current_checks, checks = load_check_catalog(client)
        images = client.request("GET", IMAGES)
        plans = []
        for name, members in groups:
            plan = make_plan(name, members, checks, images, args.upgrade_rules)
            if plan is None:
                detail = ", ".join(f"{s.name} {s.model} {s.version}" for s in members)
                print(f"Skipping {name}: {detail} outside the N9K upgrade rules")
                continue
            plans.append(plan)
        if not plans:
            raise ValueError("No selected switches match the configured N9K upgrade rules")

        existing_by_fabric = {}
        for fabric in {plan.fabric for plan in plans}:
            update_groups_path = fabric_path(fabric, "updateGroups")
            payload = client.request("GET", update_groups_path)
            existing_by_fabric[fabric] = {
                field(item, "updateGroupName"): item
                for item in walk_records(payload)
                if field(item, "updateGroupName")
            }
        attach_by_name = {}
        for plan in plans:
            existing = existing_by_fabric[plan.fabric].get(plan.group_name)
            attach_by_name[plan.group_name] = plan.serials
            if existing is not None:
                member_ids = existing.get("updateGroupSwitches") or []
                if not isinstance(member_ids, list):
                    member_ids = []
                others = [str(member) for member in member_ids if member not in plan.serials]
                if others:
                    raise ValueError(
                        f"Update group {plan.group_name} already contains other switches: {', '.join(others)}"
                    )
                attach_by_name[plan.group_name] = [s for s in plan.serials if s not in member_ids]
                print(f"Reusing existing update group {plan.group_name}")

        print("Planned staging:")
        for plan in plans:
            print(
                f"group={plan.group_name} fabric={plan.fabric} -> {plan.target_version} "
                f"({plan.image_name}); checks={', '.join(plan.check_names)}"
            )
            for switch in plan.switches:
                print(f"    {switch.name} [{switch.serial}] {switch.address} {switch.model} {switch.version}")
        if not args.apply:
            print("Plan only; pass --apply to create groups, attach checks, and stage images.")
            return 0

        print(
            f"Preparing {CUSTOM_CHECK_PREFIX} custom checks with {POST_UPDATE_DELAY}-second delays; "
            "default checks remain unchanged"
        )
        checks = ensure_check_catalog(client, current_checks, checks)
        plans = [make_plan(name, members, checks, images, args.upgrade_rules) for name, members in groups]
        plans = [plan for plan in plans if plan is not None]
        for plan in plans:
            apply_plan(client, plan, checks, attach_by_name[plan.group_name], args.run_pre_report)
            print(f"Staging requested for update group {plan.group_name} ({len(plan.switches)} switches)")
        print("Staging requests submitted. The NX-OS upgrade was not started.")
        return 0
    except (requests.RequestException, RuntimeError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())