"""Semantic comparison for manual and automated Nexus Dashboard baselines."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


def _project(value: Any, shape: Any) -> Any:
    """Project observed data onto the inventory-owned comparison shape."""
    if isinstance(shape, Mapping):
        observed = value if isinstance(value, Mapping) else {}
        return {key: _project(observed.get(key), child) for key, child in shape.items()}
    if isinstance(shape, list):
        observed = value if isinstance(value, list) else []
        if shape and all(isinstance(item, Mapping) and "hostname" in item for item in shape):
            by_name = {
                str(item.get("hostname")).casefold(): item
                for item in observed
                if isinstance(item, Mapping)
            }
            return [
                _project(by_name.get(str(item["hostname"]).casefold(), {}), item)
                for item in shape
            ]
        return observed
    return value


def _without_unverifiable_preference(
    cluster: Mapping[str, Any], unverifiable: set[str]
) -> dict[str, Any]:
    result = deepcopy(dict(cluster))
    if "cluster.ntp_servers[].preferred" in unverifiable:
        result["ntp_servers"] = [
            {"host": server.get("host")}
            for server in result.get("ntp_servers", [])
            if isinstance(server, Mapping)
        ]
    return result


def compare_nd_baselines(
    manual: Mapping[str, Any], automated: Mapping[str, Any]
) -> list[str]:
    """Return semantic parity errors; an empty list is a pass."""
    errors: list[str] = []
    if manual.get("baseline_kind") != "manual":
        errors.append("manual artifact has baseline_kind != manual")
    if automated.get("baseline_kind") != "automated":
        errors.append("automated artifact has baseline_kind != automated")

    manual_expected = manual.get("expected_from_inventory")
    automated_expected = automated.get("expected_from_inventory")
    if manual_expected != automated_expected:
        errors.append("canonical inventory projection changed between runs")
    if not isinstance(manual_expected, Mapping):
        errors.append("manual artifact is missing expected_from_inventory")
        return errors

    for label, baseline in (("manual", manual), ("automated", automated)):
        observed = baseline.get("observed_from_nd")
        if not isinstance(observed, Mapping):
            errors.append(f"{label} artifact is missing observed_from_nd")
            continue
        expected_cluster = manual_expected.get("cluster", {})
        observed_cluster = observed.get("cluster", {})
        unverifiable = set(baseline.get("api_unverifiable_fields") or [])
        projected_cluster = _project(observed_cluster, expected_cluster)
        expected_comparable = _without_unverifiable_preference(
            expected_cluster, unverifiable
        )
        observed_comparable = _without_unverifiable_preference(
            projected_cluster, unverifiable
        )
        if observed_comparable != expected_comparable:
            errors.append(f"{label} cluster configuration differs from inventory")

        expected_nodes = manual_expected.get("nodes", [])
        if _project(observed.get("nodes", []), expected_nodes) != expected_nodes:
            errors.append(f"{label} node configuration differs from inventory")

    for field in ("software_version", "setup_state", "runtime_state"):
        if manual.get(field) != automated.get(field):
            errors.append(f"{field} differs between manual and automated runs")

    manual_observed = manual.get("observed_from_nd")
    automated_observed = automated.get("observed_from_nd")
    if isinstance(manual_observed, Mapping) and isinstance(automated_observed, Mapping):
        unverifiable = set(manual.get("api_unverifiable_fields") or []) | set(
            automated.get("api_unverifiable_fields") or []
        )
        manual_cluster = _without_unverifiable_preference(
            manual_observed.get("cluster", {}), unverifiable
        )
        automated_cluster = _without_unverifiable_preference(
            automated_observed.get("cluster", {}), unverifiable
        )
        if manual_cluster != automated_cluster:
            errors.append("observed cluster differs between manual and automated runs")
        if manual_observed.get("nodes") != automated_observed.get("nodes"):
            errors.append("observed nodes differ between manual and automated runs")

    return errors
