"""Pure, offline-testable C880 condition and HGX component checks.

ServiceConditions can retain old entries even when their origin currently has
Health OK and no Status.Conditions. A pre-window fingerprint baseline detects
new entries observed by later samples; it does not prove that an event did not
appear and disappear between samples. Never persist raw Redfish bodies here.
"""

from collections import Counter
from hashlib import sha256
import json
import re


MAX_CONDITIONS = 128
BASELINE_SCHEMA = 1
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_LOG_LINK = re.compile(
    r"^(/redfish/v1/(?:[A-Za-z0-9_-]+/)+LogServices/[A-Za-z0-9_-]+/Entries)/([0-9]+)$")


def condition_fingerprints(conditions):
    """Return opaque, stable fingerprints; fail closed on incomplete entries."""
    if not isinstance(conditions, list) or len(conditions) > MAX_CONDITIONS:
        raise ValueError("Unexpected service-condition collection")
    fingerprints = []
    for entry in conditions:
        if not isinstance(entry, dict):
            raise ValueError("Unexpected service condition")
        origin = entry.get("OriginOfCondition")
        log = entry.get("LogEntry")
        fields = {
            "severity": entry.get("Severity"),
            "timestamp": entry.get("Timestamp"),
            "message_id": entry.get("MessageId"),
            "origin": origin.get("@odata.id") if isinstance(origin, dict) else None,
            "log": log.get("@odata.id") if isinstance(log, dict) else None,
        }
        if any(not isinstance(value, str) or not value for value in fields.values()):
            raise ValueError("Incomplete service condition")
        encoded = json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
        fingerprints.append(sha256(encoded).hexdigest())
    return sorted(fingerprints)


def make_baseline(conditions):
    """A sanitized artifact suitable for capture before a maintenance window."""
    return {"schema": BASELINE_SCHEMA, "fingerprints": condition_fingerprints(conditions)}


def compare_same_log_sequence(conditions, entries):
    """Place linked conditions within one log stream; ignore unreliable clocks.

    This cannot compare IDs from different LogServices or prove what an
    unobserved entry contained. It intentionally emits no raw messages.
    """
    if not isinstance(conditions, list) or len(conditions) > MAX_CONDITIONS:
        raise ValueError("Unexpected service conditions")
    if not isinstance(entries, list) or len(entries) > 1000:
        raise ValueError("Unexpected log collection")
    links = []
    streams = set()
    for condition in conditions:
        log = condition.get("LogEntry") if isinstance(condition, dict) else None
        path = log.get("@odata.id") if isinstance(log, dict) else None
        match = _LOG_LINK.fullmatch(path) if isinstance(path, str) else None
        if not match:
            raise ValueError("Missing numeric condition-log sequence")
        streams.add(match.group(1))
        links.append(int(match.group(2)))
    if len(streams) > 1:
        raise ValueError("Cannot compare different log sequence streams")
    ids = []
    for entry in entries:
        value = entry.get("Id") if isinstance(entry, dict) else None
        path = entry.get("@odata.id") if isinstance(entry, dict) else None
        match = _LOG_LINK.fullmatch(path) if isinstance(path, str) else None
        if (not isinstance(value, str) or not re.fullmatch(r"[0-9]+", value)
                or not match or int(match.group(2)) != int(value)):
            raise ValueError("Missing numeric log sequence")
        streams.add(match.group(1))
        if len(streams) > 1:
            raise ValueError("Cannot compare different log sequence streams")
        ids.append(int(value))
    if not ids or len(set(ids)) != len(ids) or not set(links).issubset(ids):
        raise ValueError("Log sequence is incomplete or duplicated")
    newest_condition = max(links) if links else None
    return {
        "condition_linked_count": len(links),
        "oldest_linked_sequence": min(links) if links else None,
        "newest_linked_sequence": newest_condition,
        "newer_entries_in_same_stream": (sum(value > newest_condition for value in ids)
                                         if links else len(ids)),
        "newest_observed_sequence": max(ids),
        "timestamp_used_for_order": False,
        "upgrade_completion_proven": False,
    }


def compare_conditions(conditions, baseline=None):
    current = condition_fingerprints(conditions)
    if baseline is None:
        return {"baseline_available": False, "new_observed_conditions": None,
                "historical_count_is_not_failure": True}
    if not isinstance(baseline, dict) or baseline.get("schema") != BASELINE_SCHEMA:
        raise ValueError("Invalid condition baseline schema")
    previous = baseline.get("fingerprints")
    if (not isinstance(previous, list) or len(previous) > MAX_CONDITIONS
            or any(not isinstance(value, str) or not _DIGEST.fullmatch(value)
                   for value in previous)):
        raise ValueError("Invalid condition baseline fingerprints")
    added = Counter(current) - Counter(previous)
    return {"baseline_available": True,
            "new_observed_conditions": sum(added.values()),
            "historical_count_is_not_failure": True}


def _component_ok(resource):
    if not isinstance(resource, dict):
        return False
    status = resource.get("Status")
    return (isinstance(status, dict) and status.get("Health") == "OK"
            and status.get("State") == "Enabled"
            and status.get("Conditions") == [])


def evaluate_components(hgx_baseboard, hgx_bmc, processors, switches):
    """Check the actual HGX components, not only a summary rollup."""
    if not isinstance(processors, list) or not isinstance(switches, list):
        raise ValueError("Missing HGX component collection")
    gpus = [p for p in processors if isinstance(p, dict) and p.get("ProcessorType") == "GPU"]
    fpga = [p for p in processors if isinstance(p, dict) and p.get("ProcessorType") == "FPGA"]
    return {
        "hgx_baseboard_ok_and_no_conditions": _component_ok(hgx_baseboard),
        "hgx_bmc_ok_and_no_conditions": _component_ok(hgx_bmc),
        "eight_b300_gpus_ok_and_no_conditions": len(gpus) == 8 and all(
            isinstance(p.get("Model"), str) and "B300" in p["Model"]
            and _component_ok(p) for p in gpus),
        "all_processor_resources_ok_and_no_conditions": len(processors) == 9
        and len(fpga) == 1 and all(_component_ok(p) for p in processors),
        "two_nvswitches_ok_and_no_conditions": len(switches) == 2
        and all(_component_ok(s) for s in switches),
    }


def evaluate_gate(conditions, components, baseline=None):
    comparison = compare_conditions(conditions, baseline)
    checks = dict(components)
    if not checks or any(not isinstance(value, bool) for value in checks.values()):
        raise ValueError("Invalid component checks")
    if not all(checks.values()) or comparison["new_observed_conditions"] not in (None, 0):
        decision = "fail"
    elif not comparison["baseline_available"]:
        decision = "baseline_required"
    else:
        decision = "pass_observed_snapshot"
    return {
        "decision": decision,
        "component_checks": checks,
        "current_condition_count": len(conditions),
        **comparison,
        "no_unobserved_transient_claim": True,
    }
