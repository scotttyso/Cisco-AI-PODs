#!/usr/bin/env python3
"""Paired ND upgrades: one spine and one leaf per guarded wave.

This is deliberately separate from the active 2026-09-28 serial install.
No POST is retried after an ambiguous response; a later run reads ND state.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
import os
import pathlib
import re
import signal
import sys
import time
import warnings

import requests
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.lib.orchestrator_telemetry import (  # noqa: E402
    RunLog,
    RunStatusHeartbeat,
    _atomic_json_write,
    capture_run_output,
    make_run_dir,
    prune_completed_runs,
    run_state_for_exit,
    write_run_status,
)


FABRIC = "AIPOD-BE-SG2-Fabric"
IMAGE = "nxos64-s1.10.6.4.M.bin"
IMAGE_SIZE = 3_430_233_088
TARGET_VERSION = "10.6(4)"
WAVES = (
    ("BE-SG2-SP1", "BE-SG2-LF1"),
    ("BE-SG2-SP2", "BE-SG2-LF2"),
)
GROUPS = ("AIPOD-SG2-1064M-PAIR1", "AIPOD-SG2-1064M-PAIR2")
PAIR_LABELS = ("Update-Pair-Left", "Update-Pair-Right")
ROLES = {"BE-SG2-SP1": "spine", "BE-SG2-SP2": "spine",
         "BE-SG2-LF1": "leaf", "BE-SG2-LF2": "leaf"}
MODELS = {name: "N9364E-SG2-O" for name in ROLES}
DEFAULT_RUN_LOG_ROOT = pathlib.Path(__file__).resolve().parents[1] / "run-logs"
CS_ENDPOINTS = {
    "BE-SP1": ("198.18.0.61", "vault_be_sp1_password"),
    "BE-SP2": ("198.18.0.62", "vault_be_sp2_password"),
    "BE-LF1": ("198.18.0.63", "vault_be_lf1_password"),
    "BE-LF2": ("198.18.0.64", "vault_be_lf2_password"),
}


def select_profile(profile: str) -> None:
    """Pin fabric, image, members, and platform models as one unit."""
    global FABRIC, IMAGE, IMAGE_SIZE, WAVES, GROUPS, ROLES, MODELS
    if profile == "sg2":
        return
    require(profile == "cs", "Unsupported upgrade profile")
    FABRIC = "AIPOD-BE-Fabric"
    IMAGE = "nxos64-cs.10.6.4.M.bin"
    IMAGE_SIZE = 2_962_740_224
    WAVES = (("BE-SP1", "BE-LF1"), ("BE-SP2", "BE-LF2"))
    # Keep ND's existing version-specific identifiers; expose stable operator
    # labels separately so historical update-plan records remain addressable.
    GROUPS = ("Update-Pair-Left", "Update-Pair-Right")
    ROLES = {"BE-SP1": "spine", "BE-SP2": "spine",
             "BE-LF1": "leaf", "BE-LF2": "leaf"}
    MODELS = {"BE-SP1": "N9K-C9364D-GX2A", "BE-SP2": "N9K-C9364D-GX2A",
              "BE-LF1": "N9K-C9332D-GX2B", "BE-LF2": "N9K-C9332D-GX2B"}


def require(condition: bool, message: str) -> None:
    if not condition:
        lowered = message.lower()
        if any(token in lowered for token in
               ("downgrade", "refus", "unsupported", "blocked", "no write is safe")):
            raise HardRefusal(message)
        if any(token in lowered for token in
               ("verification", "failed or skipped", "not healthy", "must validate",
                "not completed", "still running at observation limit")):
            raise CompletedFailure(message)
        raise RuntimeError(message)


class HardRefusal(RuntimeError):
    """An unsafe or unsupported request refused by an explicit gate."""


class CompletedFailure(RuntimeError):
    """A completed orchestration check whose result does not meet its gate."""


def read_switch_snapshot(vault: dict, name: str) -> dict[str, str]:
    """Read current NX-OS version and boot record without changing the switch."""
    import paramiko

    require(name in CS_ENDPOINTS, f"No read-only verification endpoint for {name}")
    address, password_key = CS_ENDPOINTS[name]
    password = vault.get(password_key)
    require(isinstance(password, str) and bool(password),
            f"Missing SSH credential for {name}")
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(address, username="admin", password=password,
                       look_for_keys=False, allow_agent=False,
                       timeout=10, auth_timeout=10)
        stdin, stdout, stderr = client.exec_command("show version", timeout=20)
        try:
            output = stdout.read().decode(errors="replace")
            exit_status = stdout.channel.recv_exit_status()
            require(exit_status == 0, f"{name} show version failed")
        finally:
            stdin.close()
            stdout.close()
            stderr.close()
    except paramiko.AuthenticationException:
        raise RuntimeError(f"SSH authentication failed for {name}; no retry") from None
    except paramiko.BadHostKeyException:
        raise RuntimeError(f"SSH host key changed for {name}; no retry") from None
    except (OSError, paramiko.SSHException):
        raise RuntimeError(f"SSH read temporarily unavailable on {name}") from None
    finally:
        client.close()

    version = re.search(r"^\s*NXOS:\s+version\s+(\S+)", output, re.MULTILINE)
    uptime = re.search(r"^\s*Kernel uptime is\s+(.+)$", output, re.MULTILINE)
    reset = re.search(r"^\s*Last reset at\s+(.+)$", output, re.MULTILINE)
    require(version and uptime and reset,
            f"{name} show version omitted required version or boot details")
    return {"version": version.group(1), "uptime": uptime.group(1).strip(),
            "lastReset": reset.group(1).strip()}


def read_switch_snapshots(vault: dict, names: tuple[str, ...]) -> dict[str, dict[str, str]]:
    return {name: read_switch_snapshot(vault, name) for name in names}


def wait_for_switch_snapshots(
    vault: dict, names: tuple[str, ...], *, limit: int = 900,
) -> dict[str, dict[str, str]]:
    """Wait for switches to answer read-only checks after ND reports completion."""
    deadline = time.monotonic() + limit
    while True:
        try:
            return read_switch_snapshots(vault, names)
        except RuntimeError as error:
            if any(marker in str(error) for marker in (
                "SSH authentication failed", "SSH host key changed", "Missing SSH credential",
                "No read-only verification endpoint", "show version omitted",
            )):
                raise
            require(time.monotonic() < deadline,
                    "Switch-side version and reboot verification did not recover")
            time.sleep(30)


def emit_upgrade_result(
    names: tuple[str, ...], before: dict[str, dict[str, str]],
    after: dict[str, dict[str, str]], *, nd_status: str,
) -> None:
    """Emit a stable, sanitized result for the frontend to render."""
    all_at_target_before = all(
        before[name]["version"].startswith(TARGET_VERSION) for name in names
    )
    all_at_target_after = all(
        after[name]["version"].startswith(TARGET_VERSION) for name in names
    )
    rebooted = [name for name in names
                if before[name]["lastReset"] != after[name]["lastReset"]]
    if all_at_target_before and all_at_target_after and not rebooted:
        headline = "All switches at target release: No upgrade or reboot required"
        outcome = "already_at_target"
    elif all_at_target_before and all_at_target_after:
        headline = "Switches remained at target release; reboot detected"
        outcome = "already_at_target_rebooted"
    elif all_at_target_after:
        headline = "Upgrade finished: All switches are at the target release"
        outcome = "target_release_verified"
    else:
        headline = "Upgrade finished: Switch version verification needs review"
        outcome = "verification_mismatch"
    versions = sorted({
        (before[name]["version"], after[name]["version"]) for name in names
    })
    if len(versions) == 1:
        before_version, after_version = versions[0]
        if before_version == after_version:
            version_text = f"Version before and after: {after_version}"
        else:
            version_text = f"Version: {before_version} → {after_version}"
    else:
        version_text = "Version details: " + "; ".join(
            f"{name}: {before[name]['version']} → {after[name]['version']}"
            for name in names
        )
    detail = f"ND result: {nd_status.title()} · {version_text}"
    if rebooted:
        detail += " · Reboot observed: " + ", ".join(rebooted)
    payload = {
        "type": "switch_upgrade_result",
        "outcome": outcome,
        "headline": headline,
        "detail": detail,
        "ndStatus": nd_status,
        "targetVersion": TARGET_VERSION,
        "switches": {
            name: {
                "versionBefore": before[name]["version"],
                "versionAfter": after[name]["version"],
                "lastResetBefore": before[name]["lastReset"],
                "lastResetAfter": after[name]["lastReset"],
                "uptimeBefore": before[name]["uptime"],
                "uptimeAfter": after[name]["uptime"],
                "rebootObserved": before[name]["lastReset"] != after[name]["lastReset"],
            }
            for name in names
        },
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return payload


def _plan_maps(plan: list[dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    switches = {}
    groups = {}
    for group in plan:
        name = group.get("updateGroupName")
        if name:
            groups[name] = group
        for item in group.get("updateGroupSwitches", []):
            switch_name = item.get("switchName")
            if switch_name:
                switches[switch_name] = item
    return switches, groups


def _outcome_badge(outcome: str | None, phase: str) -> dict[str, str]:
    labels = {
        "already_at_target": ("Already at target", "success"),
        "already_at_target_rebooted": ("Reboot detected", "warning"),
        "target_release_verified": ("Target verified", "success"),
        "verification_mismatch": ("Needs review", "danger"),
    }
    label, variant = labels.get(outcome, (phase.replace("-", " ").title(), "info"))
    return {"label": label, "variant": variant}


def build_telemetry(profile: str, phase: str, before_plan: list[dict],
                    after_plan: list[dict], run_log: RunLog,
                    switch_results: list[dict] | None = None, *, offline=False,
                    run_dir=None) -> dict:
    """Map ND's paired plan and verified switch result into the FE contract."""
    before_switches, _ = _plan_maps(before_plan)
    after_switches, after_groups = _plan_maps(after_plan)
    switch_results = switch_results or []
    result_switches = {}
    result_outcomes = {}
    nd_results = set()
    for result in switch_results:
        result_switches.update(result.get("switches", {}))
        nd_results.add(result.get("ndStatus"))
        for switch_name in result.get("switches", {}):
            result_outcomes[switch_name] = result.get("outcome")
    rows = []
    target_count = 0
    validated_count = 0
    completed_count = 0
    rebooted_count = 0

    if offline:
        switch_names = ("switch-1", "switch-2", "switch-3", "switch-4")
        roles = {"switch-1": "spine", "switch-2": "leaf",
                 "switch-3": "spine", "switch-4": "leaf"}
        pairs = {"switch-1": PAIR_LABELS[0], "switch-2": PAIR_LABELS[0],
                 "switch-3": PAIR_LABELS[1], "switch-4": PAIR_LABELS[1]}
    else:
        switch_names = tuple(name for wave in WAVES for name in wave)
        roles = ROLES
        pairs = {switch: PAIR_LABELS[index]
                 for index, wave in enumerate(WAVES) for switch in wave}

    for name in switch_names:
        before = before_switches.get(name, {})
        after = after_switches.get(name, {})
        result = result_switches.get(name, {})
        version_before = result.get("versionBefore", before.get("switchVersion"))
        version_after = result.get("versionAfter", after.get("switchVersion"))
        target_version = TARGET_VERSION
        at_target = bool(version_after and str(version_after).startswith(target_version))
        if at_target:
            target_count += 1
        image_state = after.get("imageValidatedStatus")
        update_state = after.get("switchUpdateStatus")
        if image_state == "success":
            validated_count += 1
        if update_state == "success":
            completed_count += 1
        reboot_observed = result.get("rebootObserved")
        if reboot_observed is True:
            rebooted_count += 1
        row_outcome = result_outcomes.get(name)
        row_badge = _outcome_badge(row_outcome, phase)
        if not result_outcomes and update_state in {"failed", "skipped"}:
            row_badge = {"label": "Needs review", "variant": "danger"}
        elif not result_outcomes and update_state == "inProgress":
            row_badge = {"label": "In progress", "variant": "warning"}
        group_name = GROUPS[0] if pairs[name] == PAIR_LABELS[0] else GROUPS[1]
        group = after_groups.get(group_name, {})
        rows.append({
            "switch_name": name,
            "role": roles[name],
            "update_pair": pairs[name],
            "version_before": version_before,
            "version_after": version_after,
            "nd_group_status": group.get("updateGroupStatus"),
            "nd_switch_status": update_state,
            "image_validation_status": image_state,
            "reboot_observed": reboot_observed,
            "outcome": row_outcome,
            "badge": row_badge,
        })

    outcome_set = {value for value in result_outcomes.values() if value}
    outcome_order = ("verification_mismatch", "already_at_target_rebooted",
                     "target_release_verified", "already_at_target")
    outcome = next((candidate for candidate in outcome_order
                    if candidate in outcome_set), None)
    if not outcome and not offline and phase in {"install", "install-left"}:
        before_versions = [before_switches.get(name, {}).get("switchVersion")
                           for name in switch_names]
        after_versions = [after_switches.get(name, {}).get("switchVersion")
                          for name in switch_names]
        if all(value and str(value).startswith(TARGET_VERSION)
               for value in after_versions):
            outcome = ("already_at_target"
                       if all(value and str(value).startswith(TARGET_VERSION)
                              for value in before_versions)
                       else "target_release_verified")
        elif any(after_versions):
            outcome = "verification_mismatch"
        for row in rows:
            row["outcome"] = outcome
            row["badge"] = _outcome_badge(outcome, phase)

    group_statuses = [after_groups.get(name, {}).get("updateGroupStatus")
                      for name in GROUPS]
    if switch_results:
        distinct_nd = {value for value in nd_results if value is not None}
        nd_status = next(iter(distinct_nd)) if len(distinct_nd) == 1 else (
            "mixed" if distinct_nd else None
        )
    elif offline:
        nd_status = None
    else:
        distinct = {status for status in group_statuses if status is not None}
        nd_status = next(iter(distinct)) if len(distinct) == 1 else (
            "mixed" if distinct else None
        )

    decision = outcome or ("OFFLINE_PLAN" if offline else phase.upper().replace("-", "_"))
    badge = _outcome_badge(outcome, "offline plan" if offline else phase)
    if offline:
        badge = {"label": "Offline example", "variant": "info"}
    reason = (switch_results[0].get("headline") if switch_results else None) or (
        "Sanitized example generated without ND access or credentials."
        if offline else f"ND {phase} phase completed; see per-switch ND and image state."
    )
    summary = {
        "decision": decision,
        "badge": badge,
        "reason": run_log.scrub(reason),
        "switch_outcome": outcome,
        "nd_status": nd_status,
        "switches_total": len(rows),
        "target_release_count": target_count,
        "image_validated_count": validated_count,
        "update_completed_count": completed_count,
        "reboot_observed_count": rebooted_count,
        "target_version": TARGET_VERSION,
    }
    payload = {
        "schema_version": "1.0",
        "telemetry_type": "backend_fabric_upgrade_telemetry",
        "profile": profile,
        "fabric": f"backend-fabric-{profile}",
        "phase": "offline_plan" if offline else phase,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "switches_table": rows,
        "console_drawer": {
            "title": "Raw Orchestrator Logs",
            "total_lines": len(run_log.lines[-500:]),
            "lines": run_log.lines[-500:],
            "collapsible": True,
            "default_expanded": False,
        },
    }
    if run_dir:
        payload["artifacts"] = {
            "run_id": pathlib.Path(run_dir).name,
            "run_dir": str(run_dir),
            "raw_log": str(pathlib.Path(run_dir) / "raw.log"),
            "telemetry_file": str(pathlib.Path(run_dir) / "telemetry.json"),
            "status_file": str(pathlib.Path(run_dir) / "status.json"),
        }
    return payload


def _offline_plan(profile: str, run_log: RunLog) -> dict:
    select_profile(profile)
    run_log("Generated offline backend-fabric telemetry example")
    payload = build_telemetry(profile, "offline_plan", [], [], run_log, offline=True)
    payload["summary"].update({
        "decision": "already_at_target",
        "badge": {"label": "Already at target", "variant": "success"},
        "switch_outcome": "already_at_target",
        "nd_status": "not requested",
        "target_release_count": 4,
        "image_validated_count": 4,
    })
    for row in payload["switches_table"]:
        row.update({
            "version_before": TARGET_VERSION,
            "version_after": TARGET_VERSION,
            "nd_group_status": "success",
            "nd_switch_status": "success",
            "image_validation_status": "success",
            "reboot_observed": False,
            "outcome": "already_at_target",
            "badge": {"label": "Already at target", "variant": "success"},
        })
    return payload


def _parse_switch_results(stdout: str) -> list[dict]:
    results = []
    for line in stdout.splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict) and value.get("type") == "switch_upgrade_result":
            results.append(value)
    return results


def transient_read_error(error: RuntimeError) -> bool:
    """Only controller read failures are retryable while an install runs."""
    message = str(error)
    return ("ND GET outcome ambiguous" in message or
            any(f"ND GET returned HTTP {code}" in message
                for code in (429, 500, 502, 503, 504)))


def wave_action(devices: list[dict]) -> str:
    """Choose a read-backed action, never a second ambiguous write."""
    require(len(devices) == 2, "Wave must contain exactly two switches")
    statuses = [item.get("switchUpdateStatus", "none") for item in devices]
    require(not any(value in {"failed", "skipped"} for value in statuses),
            "Wave has a failed or skipped switch; diagnose before proceeding")
    if statuses == ["success", "success"]:
        return "done"
    if "inProgress" in statuses:
        return "observe"
    if statuses == ["none", "none"]:
        return "start"
    raise RuntimeError("Partial or unknown wave state; no install write is safe")


def require_all_validated(groups: list[dict]) -> None:
    require(len(groups) == 2 and
            all(len(group.get("updateGroupSwitches", [])) == 2 for group in groups) and
            all(item.get("imageValidatedStatus") == "success"
                for group in groups for item in group["updateGroupSwitches"]),
            "All four SG2 switches must validate the image before any install")


class Nd:
    def __init__(self, host: str, password: str, verify_tls: bool) -> None:
        self.base = "https://" + host
        self.manage = self.base + "/api/v1/manage"
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.verify = verify_tls
        if not verify_tls:
            warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        self.password = password

    def request(self, method: str, path: str, *, payload: dict | None = None,
                accepted: tuple[int, ...] = (200,)) -> dict:
        try:
            response = self.session.request(
                method, self.base + path, json=payload,
                timeout=(20, 120 if method == "POST" else 45),
            )
        except requests.RequestException as error:
            raise RuntimeError(
                f"ND {method} outcome ambiguous ({type(error).__name__}); "
                "inspect controller state before any write retry"
            ) from None
        require(response.status_code in accepted,
                f"ND {method} returned HTTP {response.status_code}; response body suppressed")
        if not response.content:
            return {}
        try:
            result = response.json()
        except ValueError:
            raise RuntimeError("ND returned non-JSON response; body suppressed") from None
        require(isinstance(result, dict) or isinstance(result, list),
                "ND returned unexpected JSON shape")
        return result

    def __enter__(self) -> Nd:
        try:
            self.request("POST", "/api/v1/infra/login", payload={
                "userName": "admin", "userPasswd": self.password, "domain": "DefaultAuth",
            })
        except RuntimeError:
            self.session.close()
            raise
        return self

    def __exit__(self, *_: object) -> None:
        try:
            self.request("POST", "/api/v1/infra/logout", accepted=(200, 204))
        except RuntimeError:
            pass
        self.session.close()

    def inventory(self, *, healthy: bool) -> dict[str, dict]:
        path = ("/appcenter/cisco/ndfc/api/v1/lan-fabric/rest/control/fabrics/"
                f"{FABRIC}/inventory/switchesByFabric")
        records = self.request("GET", path)
        require(isinstance(records, list) and len(records) == 4,
                "Fabric inventory is not exactly four switches")
        by_name = {item.get("logicalName"): item for item in records}
        require(set(by_name) == set(ROLES), "Fabric inventory hostnames changed")
        for name, role in ROLES.items():
            item = by_name[name]
            require(item.get("model") == MODELS[name] and
                    item.get("switchRole") == role and item.get("serialNumber"),
                    f"Model, role, or identity changed for {name}")
            if healthy:
                require(item.get("status") == "ok", f"{name} is not healthy")
        return by_name

    def groups(self) -> list[dict]:
        result = self.request("GET", f"/api/v1/manage/fabrics/{FABRIC}/updateGroups")
        return result.get("updateGroups", [])

    def plan(self) -> list[dict]:
        result = self.request(
            "GET", f"/api/v1/manage/fabrics/{FABRIC}/softwareUpdatePlan/summary")
        return result.get("updateGroups", [])

    def action(self, action: str, names: list[str]) -> None:
        self.request(
            "POST", f"/api/v1/manage/fabrics/{FABRIC}/softwareUpdatePlan/actions/{action}",
            payload={"updateGroupNames": names}, accepted=(200, 202),
        )


def select_groups(records: list[dict]) -> list[dict]:
    selected = []
    for name in GROUPS:
        matches = [item for item in records if item.get("updateGroupName") == name]
        require(len(matches) == 1, f"Paired update group {name} is absent or duplicated")
        selected.append(matches[0])
    return selected


def check_group_config(nd: Nd, inventory: dict[str, dict]) -> None:
    groups = select_groups(nd.groups())
    for index, group in enumerate(groups):
        expected_ids = {inventory[name]["serialNumber"] for name in WAVES[index]}
        require(set(group.get("updateGroupSwitches", [])) == expected_ids and
                group.get("execution") == "parallel" and
                group.get("contingency") == "pause" and
                group.get("isDisruptiveUpdate") is True and
                group.get("installImageData", {}).get("nosImageName") == IMAGE,
                f"Paired update group {GROUPS[index]} has conflicting settings")


def check_plan(nd: Nd) -> list[dict]:
    all_groups = nd.plan()
    for group in all_groups:
        if group.get("updateGroupName") not in GROUPS:
            require(group.get("updateGroupStatus") not in {"inProgress", "paused"} and
                    not any(item.get("switchUpdateStatus") == "inProgress"
                            for item in group.get("updateGroupSwitches", [])),
                    "Another install in this fabric is active; paired mode will not overlap it")
    selected = select_groups(all_groups)
    for index, group in enumerate(selected):
        devices = group.get("updateGroupSwitches", [])
        require(len(devices) == 2 and
                {item.get("switchName") for item in devices} == set(WAVES[index]),
                f"Paired update plan {GROUPS[index]} has incorrect members")
    return selected


def wait_plan_groups(nd: Nd) -> list[dict]:
    """Allow ND's read model to catch up after group creation; no write retry."""
    for attempt in range(12):
        all_groups = nd.plan()
        counts = [sum(group.get("updateGroupName") == name for group in all_groups)
                  for name in GROUPS]
        require(all(count <= 1 for count in counts),
                "Duplicate paired update group in ND plan")
        if counts == [1, 1]:
            return check_plan(nd)
        if attempt < 11:
            time.sleep(5)
    raise RuntimeError("Paired groups not visible in ND plan; inspect before retry")


def ensure_groups(nd: Nd, inventory: dict[str, dict]) -> None:
    present = {item.get("updateGroupName") for item in nd.groups()}
    missing = [i for i, name in enumerate(GROUPS) if name not in present]
    if missing:
        payload = {"updateGroups": [
            {"updateGroupName": GROUPS[i],
             "updateGroupSwitches": [inventory[name]["serialNumber"] for name in WAVES[i]],
             "installImageData": {"nosImageName": IMAGE},
             "execution": "parallel", "contingency": "pause", "analysis": "snapshot",
             "reports": "noReport", "reportSelection": "noReport",
             "isMaintenance": False, "isDisruptiveUpdate": True}
            for i in missing
        ]}
        nd.request("POST", f"/api/v1/manage/fabrics/{FABRIC}/updateGroups",
                   payload=payload, accepted=(200, 201, 202, 207))
    check_group_config(nd, inventory)


def require_image(nd: Nd) -> None:
    result = nd.request("GET", "/api/v1/manage/fabricSoftware/images")
    matches = [item for item in result.get("uploadedImages", [])
               if item.get("imageName") == IMAGE]
    require(len(matches) == 1 and matches[0].get("imagePresent") == "present" and
            matches[0].get("imageSize") == IMAGE_SIZE,
            "Pinned image is missing or incomplete in ND")


def wait_for(nd: Nd, index: int, field: str, *, interval: int, limit: int) -> list[dict]:
    deadline = time.monotonic() + limit
    while True:
        try:
            devices = check_plan(nd)[index]["updateGroupSwitches"]
        except RuntimeError as error:
            if not transient_read_error(error):
                raise
            require(time.monotonic() < deadline,
                    f"{GROUPS[index]} controller reads did not recover; no write repeated")
            time.sleep(interval)
            continue
        statuses = [item.get(field, "none") for item in devices]
        require(not any(value in {"failed", "skipped"} for value in statuses),
                f"{GROUPS[index]} reports a failed or skipped {field}")
        if statuses == ["success", "success"]:
            return devices
        require(time.monotonic() < deadline,
                f"{GROUPS[index]} still running at observation limit; no write repeated")
        time.sleep(interval)


def wait_inventory(nd: Nd, limit: int = 900) -> None:
    deadline = time.monotonic() + limit
    while True:
        try:
            nd.inventory(healthy=True)
            return
        except RuntimeError as error:
            if "is not healthy" not in str(error) and not transient_read_error(error):
                raise
            require(time.monotonic() < deadline,
                    "Fabric inventory did not return healthy; next wave is blocked")
            time.sleep(30)


def primary_underlay_counts(name: str, lldp: str, bgp: str) -> tuple[int, int]:
    """Return reciprocal expected LLDP links and established IPv4 peers."""
    remotes = ("BE-LF1", "BE-LF2") if name.startswith("BE-SP") else ("BE-SP1", "BE-SP2")
    lldp_counts = [len(re.findall(rf"(?<![A-Z0-9-]){remote}(?![A-Z0-9-])",
                                  lldp, re.IGNORECASE)) for remote in remotes]
    peer_rows = [line.split() for line in bgp.splitlines()
                 if re.match(r"^\s*\d+\.\d+\.\d+\.\d+\s", line)]
    established = sum(bool(row and row[-1].isdigit()) for row in peer_rows)
    require(lldp_counts == [2, 2] and len(peer_rows) == 4 and established == 4,
            f"{name} has not restored its four LLDP links and four underlay BGP peers")
    return sum(lldp_counts), established


def primary_underlay_once(vault: dict) -> None:
    """Known-host, read-only CLI verification; close every SSH session."""
    import paramiko

    for name, (address, password_key) in CS_ENDPOINTS.items():
        password = vault.get(password_key)
        require(isinstance(password, str) and bool(password),
                f"Missing SSH credential for {name}")
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            client.connect(address, username="admin", password=password,
                           look_for_keys=False, allow_agent=False,
                           timeout=10, auth_timeout=10)
            outputs = []
            for command in ("show lldp neighbors", "show bgp ipv4 unicast summary"):
                stdin, stdout, stderr = client.exec_command(command, timeout=20)
                try:
                    output = stdout.read().decode(errors="replace")
                    require(stdout.channel.recv_exit_status() == 0,
                            f"{name} underlay read command failed")
                    outputs.append(output)
                finally:
                    stdin.close()
                    stdout.close()
                    stderr.close()
            primary_underlay_counts(name, *outputs)
        except paramiko.AuthenticationException:
            raise RuntimeError(f"SSH authentication failed for {name}; no retry") from None
        except paramiko.BadHostKeyException:
            raise RuntimeError(f"SSH host key changed for {name}; no retry") from None
        except (OSError, paramiko.SSHException):
            raise RuntimeError(f"SSH underlay read temporarily unavailable on {name}") from None
        finally:
            client.close()


def wait_primary_underlay(vault: dict, limit: int = 900) -> None:
    deadline = time.monotonic() + limit
    while True:
        try:
            primary_underlay_once(vault)
            print("Primary reciprocal LLDP and underlay BGP restored", flush=True)
            return
        except RuntimeError as error:
            if ("authentication failed" in str(error).lower() or
                    "host key changed" in str(error).lower() or
                    "Missing SSH credential" in str(error)):
                raise
            require(time.monotonic() < deadline,
                    "Primary underlay did not recover; next wave is blocked")
            time.sleep(30)


def run(nd: Nd, phase: str, vault: dict) -> None:
    require_image(nd)
    inventory = nd.inventory(healthy=False)
    if phase == "plan":
        plan = nd.plan()
        for name in GROUPS:
            matches = [group for group in plan
                       if group.get("updateGroupName") == name]
            if matches:
                require(len(matches) == 1, f"Duplicate paired plan for {name}")
                print(f"{PAIR_LABELS[GROUPS.index(name)]} [{name}]: "
                      f"{wave_action(matches[0].get('updateGroupSwitches', []))}")
            else:
                print(f"{PAIR_LABELS[GROUPS.index(name)]} [{name}]: not created")
        print("Read-only paired plan complete")
        return
    if phase == "groups":
        # Group preparation is safe after a completed upgrade: it never stages
        # an image or requests another install. A later run reads ND before any
        # write, and an active install in this fabric blocks group creation.
        require(not any(group.get("updateGroupStatus") in {"inProgress", "paused"} or
                        any(item.get("switchUpdateStatus") == "inProgress"
                            for item in group.get("updateGroupSwitches", []))
                        for group in nd.plan()),
                "An install in this fabric is active; paired groups are blocked")
        nd.inventory(healthy=True)
        ensure_groups(nd, inventory)
        wait_plan_groups(nd)
        print("Paired update groups verified; no image staged or installed")
        return
    if phase == "stage":
        # Never create groups while a different install is in progress.
        require(not any(group.get("updateGroupStatus") in {"inProgress", "paused"} or
                        any(item.get("switchUpdateStatus") == "inProgress"
                            for item in group.get("updateGroupSwitches", []))
                        for group in nd.plan()),
                "An install in this fabric is active; paired staging is blocked")
        nd.inventory(healthy=True)
        ensure_groups(nd, inventory)
        groups = wait_plan_groups(nd)
        devices = [item for group in groups for item in group["updateGroupSwitches"]]
        statuses = [item.get("imageValidatedStatus", "none") for item in devices]
        stage_states = [item.get("imageStagedStatus", "none") for item in devices]
        require(not any(value == "failed" for value in statuses),
                "Prior image validation failed")
        require(not any(value == "failed" for value in stage_states),
                "Prior image staging failed")
        if statuses == ["none"] * 4 and stage_states == ["none"] * 4:
            nd.action("stage", list(GROUPS))
        elif statuses != ["success"] * 4:
            require(any(value == "inProgress" for value in statuses),
                    "Partial stage is ambiguous; no stage write repeated")
        for index in range(2):
            wait_for(nd, index, "imageValidatedStatus", interval=30, limit=3600)
            print(f"{PAIR_LABELS[index]} [{GROUPS[index]}]: image validated on both switches")
        return
    if phase == "stage-left":
        current_plan = nd.plan()
        require(not any(
            any(item.get("switchUpdateStatus") == "inProgress"
                for item in group.get("updateGroupSwitches", [])) or
            (group.get("updateGroupName") != GROUPS[0] and
             group.get("updateGroupStatus") in {"inProgress", "paused"})
            for group in current_plan),
                "An install in this fabric is active; Update-Pair-Left staging is blocked")
        nd.inventory(healthy=True)
        ensure_groups(nd, inventory)
        groups = wait_plan_groups(nd)
        devices = groups[0]["updateGroupSwitches"]
        statuses = [item.get("imageValidatedStatus", "none") for item in devices]
        stage_states = [item.get("imageStagedStatus", "none") for item in devices]
        require(not any(value == "failed" for value in statuses + stage_states),
                "Prior Update-Pair-Left staging or validation failed")
        if statuses == ["none"] * 2 and stage_states == ["none"] * 2:
            nd.action("stage", [GROUPS[0]])
        elif statuses != ["success"] * 2:
            require(any(value == "inProgress" for value in statuses),
                    "Partial Update-Pair-Left stage is ambiguous; no stage write repeated")
        wait_for(nd, 0, "imageValidatedStatus", interval=30, limit=3600)
        print("Update-Pair-Left: image validated on BE-SP1 and BE-LF1; right pair untouched")
        return
    groups = check_plan(nd)
    if phase == "verify":
        for index, group in enumerate(groups):
            devices = group["updateGroupSwitches"]
            require(wave_action(devices) == "done" and
                    all(item.get("switchVersion", "").startswith(TARGET_VERSION)
                        for item in devices),
                    f"{GROUPS[index]} has not completed target version")
        nd.inventory(healthy=True)
        print("Both fabric pairs reached target version and healthy inventory")
        return
    if phase == "rehearsal":
        # Exercise the read-side install safeguards against the live ND plan,
        # but never send updateSoftware. This is intended for same-version
        # rehearsals where an actual firmware install must not occur.
        groups = check_plan(nd)
        require_all_validated(groups)
        devices = [item for group in groups for item in group["updateGroupSwitches"]]
        require(all(item.get("switchVersion", "").startswith(TARGET_VERSION)
                    for item in devices),
                "No-install rehearsal requires all four switches at the pinned target version")
        nd.inventory(healthy=True)
        print("No-install rehearsal passed: both pairs, image validation, and target versions verified; no install requested")
        return
    if phase == "install-left":
        # Explicit, one-group experiment for the approved same-version test.
        # This branch always returns after observing Update-Pair-Left and can
        # never fall through to Update-Pair-Right.
        require(set(ROLES).issubset(CS_ENDPOINTS),
                "install-left is available only for the CS fabric profile")
        left_switches = groups[0]["updateGroupSwitches"]
        require(len(left_switches) == 2 and
                all(item.get("imageValidatedStatus") == "success"
                    for item in left_switches),
                "Update-Pair-Left image validation must succeed before install")
        action = wave_action(left_switches)
        require(action == "start",
                f"Update-Pair-Left is {action}; refusing to send a duplicate install request")
        require(not any(group.get("updateGroupStatus") in {"inProgress", "paused"} or
                        any(item.get("switchUpdateStatus") == "inProgress"
                            for item in group.get("updateGroupSwitches", []))
                        for group in nd.plan()
                        if group.get("updateGroupName") != GROUPS[0]),
                "Another install in this fabric is active; Update-Pair-Left is blocked")
        nd.inventory(healthy=True)
        before = read_switch_snapshots(vault, WAVES[0])
        nd.action("updateSoftware", [GROUPS[0]])
        devices = wait_for(nd, 0, "switchUpdateStatus", interval=60, limit=10800)
        require(all(item.get("switchVersion", "").startswith(TARGET_VERSION)
                    for item in devices), "Update-Pair-Left version verification failed")
        wait_inventory(nd)
        after = wait_for_switch_snapshots(vault, WAVES[0])
        final_group = check_plan(nd)[0]
        emit_upgrade_result(
            WAVES[0], before, after,
            nd_status=final_group.get("updateGroupStatus", "success"),
        )
        return
    if phase == "install":
        devices = [item for group in groups for item in group["updateGroupSwitches"]]
        if all(item.get("switchVersion", "").startswith(TARGET_VERSION)
               for item in devices):
            nd.inventory(healthy=True)
            if set(ROLES).issubset(CS_ENDPOINTS):
                names = tuple(name for wave in WAVES for name in wave)
                before = read_switch_snapshots(vault, names)
                after = read_switch_snapshots(vault, names)
                emit_upgrade_result(names, before, after, nd_status="not requested")
            else:
                print(f"All SG2 switches already run {TARGET_VERSION}; "
                      "no ND install action sent")
            return
    require(phase == "install", "Unknown phase")
    require_all_validated(groups)
    # Existing pre-deployment LLDP/BGP errors are diagnostic context, not an
    # upgrade gate. Keep the guarded sequence based on ND inventory, image,
    # per-switch update state, and target-version recovery instead.
    for index in range(2):
        devices = check_plan(nd)[index]["updateGroupSwitches"]
        action = wave_action(devices)
        before = None
        if action == "start":
            require(not any(item.get("switchVersion", "").startswith(TARGET_VERSION)
                            for item in devices),
                    "Target version already present without completed group state; inspect")
            nd.inventory(healthy=True)
            require(not any(group.get("updateGroupStatus") in {"inProgress", "paused"} or
                            any(item.get("switchUpdateStatus") == "inProgress"
                                for item in group.get("updateGroupSwitches", []))
                            for group in nd.plan()
                            if group.get("updateGroupName") not in GROUPS),
                    "Another install in this fabric is active; paired install is blocked")
            if set(ROLES).issubset(CS_ENDPOINTS):
                before = read_switch_snapshots(vault, WAVES[index])
            nd.action("updateSoftware", [GROUPS[index]])
        if action != "done":
            devices = wait_for(nd, index, "switchUpdateStatus", interval=60, limit=10800)
        require(all(item.get("switchVersion", "").startswith(TARGET_VERSION)
                    for item in devices), f"{GROUPS[index]} version verification failed")
        wait_inventory(nd)
        if before is not None:
            after = wait_for_switch_snapshots(vault, WAVES[index])
            emit_upgrade_result(
                WAVES[index], before, after,
                nd_status=check_plan(nd)[index].get("updateGroupStatus", "success"),
            )
        else:
            print(f"{PAIR_LABELS[index]} [{GROUPS[index]}]: ND reports {action}; "
                  "no pre-install switch baseline was captured")
    print("Paired upgrade complete; review carrier, optics, LLDP and underlay as diagnostics")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("plan", "groups", "stage", "stage-left", "install", "install-left", "verify", "rehearsal"),
                        default="plan")
    parser.add_argument("--profile", choices=("sg2", "cs"), default="sg2")
    parser.add_argument("--nd-host")
    parser.add_argument("--vault", type=pathlib.Path)
    parser.add_argument("--verify-tls", action="store_true")
    parser.add_argument("--run-log-root", type=pathlib.Path,
                        default=DEFAULT_RUN_LOG_ROOT)
    parser.add_argument("--telemetry-only", action="store_true",
                        help="Print a sanitized offline telemetry example; no credentials or network")
    args = parser.parse_args()
    select_profile(args.profile)

    if args.telemetry_only:
        with RunLog() as offline_log:
            print(json.dumps(_offline_plan(args.profile, offline_log),
                             ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    run_dir = make_run_dir(args.run_log_root, f"backend-fabric-{args.profile}", args.phase)
    started_utc = datetime.now(timezone.utc).isoformat()
    exit_code = 2
    raised = False
    error = None
    run_log = RunLog(run_dir=run_dir)
    heartbeat = RunStatusHeartbeat(run_dir, started_utc, scrubber=run_log)
    write_run_status(run_dir, "running", started_utc=started_utc, scrubber=run_log)
    heartbeat.start()
    previous_handlers = {}

    def on_signal(signum, _frame):
        raise SystemExit(128 + signum)

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, on_signal)
        run_log(f"Starting {args.profile} backend fabric {args.phase} run")
        with capture_run_output(run_log) as (stdout_stream, _stderr_stream):
            try:
                require(bool(args.nd_host), "--nd-host is required for live phases")
                require(bool(args.vault), "--vault is required for live phases")
                vault = yaml.safe_load(args.vault.read_text(encoding="utf-8"))
                require(isinstance(vault, dict), "ND vault unavailable or unreadable")
            except (OSError, ValueError, yaml.YAMLError):
                raise RuntimeError("ND vault unavailable or unreadable") from None
            for key, value in vault.items():
                if "password" in str(key).lower() and isinstance(value, str):
                    run_log.add_secret(value)
            password = vault.get("vault_nd_admin_password")
            require(isinstance(password, str) and bool(password), "ND credential unavailable")
            with Nd(args.nd_host, password, args.verify_tls) as nd:
                before_plan = nd.plan()
                run(nd, args.phase, vault)
                after_plan = nd.plan()
            parsed_results = _parse_switch_results(stdout_stream.getvalue())
            telemetry = build_telemetry(
                args.profile, args.phase, before_plan, after_plan, run_log,
                parsed_results, run_dir=run_dir,
            )
            _atomic_json_write(run_dir / "telemetry.json", telemetry)
            # A completed invocation with an explicit version mismatch is a
            # result failure (exit 1), even if ND's API request itself worked.
            if any(item.get("outcome") == "verification_mismatch"
                   for item in parsed_results):
                exit_code = 1
            else:
                exit_code = 0
    except SystemExit as exc:
        exit_code = int(exc.code or 0)
        raised = exit_code != 0
        error = f"terminated with exit code {exit_code}" if raised else None
    except CompletedFailure as exc:
        exit_code = 1
        raised = True
        error = str(exc)
        run_log(f"Completed with failed verification: {exc}")
    except HardRefusal as exc:
        exit_code = 3
        raised = True
        error = str(exc)
        run_log(f"Refused: {exc}")
    except Exception as exc:  # operational errors become exit 2
        exit_code = 2
        raised = True
        error = f"{type(exc).__name__}: {exc}"
        run_log(error)
    finally:
        heartbeat.stop()
        write_run_status(run_dir, run_state_for_exit(exit_code, raised),
                         exit_code=exit_code, error=error,
                         started_utc=started_utc, scrubber=run_log)
        run_log.close()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        prune_completed_runs(args.run_log_root, f"backend-fabric-{args.profile}")
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
