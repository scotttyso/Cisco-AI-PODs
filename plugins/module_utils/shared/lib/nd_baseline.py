"""Normalize read-only Nexus Dashboard setup queries for parity comparison."""
from __future__ import annotations

from typing import Any, Mapping

from .inventory import InventoryError


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InventoryError(f"ND baseline query is missing {label}")
    return value


def _network(value: Any) -> dict[str, Any]:
    data = _mapping(value, "node network data")
    return {
        "ipv4_address": data.get("ipSubnet"),
        "ipv4_gateway": data.get("gateway"),
        "vlan": data.get("vlan"),
    }


def _external_services(value: Any) -> list[dict[str, Any]]:
    services = value if isinstance(value, list) else []
    normalized = [
        {
            "target": service.get("target"),
            "pool": sorted(service.get("pool") or []),
        }
        for service in services
        if isinstance(service, Mapping) and service.get("pool")
    ]
    return sorted(normalized, key=lambda item: str(item["target"]))


def _ntp_servers(cluster_config: Mapping[str, Any]) -> list[dict[str, Any]]:
    ntp_config = cluster_config.get("ntpConfig")
    if isinstance(ntp_config, Mapping) and isinstance(ntp_config.get("servers"), list):
        return [
            {
                "host": server.get("host"),
                "preferred": (
                    bool(server.get("preferred"))
                    if "preferred" in server
                    else bool(server.get("prefer"))
                    if "prefer" in server
                    else None
                ),
            }
            for server in ntp_config["servers"]
            if isinstance(server, Mapping)
        ]
    return [
        {"host": host, "preferred": None}
        for host in (cluster_config.get("ntpServers") or [])
    ]


def normalize_nd_baseline(
    current: Mapping[str, Any],
    version: Mapping[str, Any],
    cluster: Mapping[str, Any],
    nodes: list[Mapping[str, Any]],
    *,
    baseline_kind: str,
    captured_at: str,
    bootstrap: Mapping[str, Any] | None = None,
    cluster_status: Mapping[str, Any] | None = None,
    serial_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a deterministic, secret-free manual or automated baseline."""
    if baseline_kind not in {"manual", "automated"}:
        raise InventoryError("baseline_kind must be manual or automated")

    current = _mapping(current, "current setup object")
    bootstrap = bootstrap if isinstance(bootstrap, Mapping) else {}
    cluster_status = cluster_status if isinstance(cluster_status, Mapping) else {}
    serial_artifact = (
        serial_artifact if isinstance(serial_artifact, Mapping) else {}
    )
    serial_nodes = serial_artifact.get("nodes")
    serial_nodes = serial_nodes if isinstance(serial_nodes, Mapping) else {}
    serials_by_name = {
        str(name).casefold(): record
        for name, record in serial_nodes.items()
        if isinstance(record, Mapping)
    }
    # /clusterstatus/install is the supported nd_setup query but can collapse
    # physical node masks/gateways after completion. GET /bootstrap/cluster
    # returns the full submitted setup document on ND 4.3.1, so prefer that
    # richer read-only projection when available.
    source = bootstrap if bootstrap.get("clusterConfig") else current
    cluster_config = _mapping(source.get("clusterConfig"), "clusterConfig")
    current_nodes = source.get("nodes")
    if not isinstance(current_nodes, list) or len(current_nodes) != len(nodes):
        raise InventoryError(
            "ND baseline node count does not match canonical inventory"
        )
    if current.get("state") != "Completed":
        raise InventoryError(
            f"ND setup state is not Completed: {current.get('state')!r}"
        )

    observed_nodes = []
    for raw in current_nodes:
        node = _mapping(raw, "node")
        controller = node.get("nodeController")
        controller = controller if isinstance(controller, Mapping) else {}
        hardware = serials_by_name.get(str(node.get("hostName", "")).casefold(), {})
        observed_nodes.append(
            {
                "hostname": node.get("hostName"),
                "serial_number": hardware.get(
                    "serial_number", node.get("serialNumber")
                ),
                "power_state": hardware.get("power_state"),
                "role": {
                    "master": "primary",
                }.get(
                    str(node.get("role", "")).casefold(),
                    str(node.get("role", "")).lower(),
                ),
                "deployment_type": controller.get("id"),
                "cimc_ip": hardware.get("cimc_ip", controller.get("ipAddress")),
                "management_network": _network(node.get("managementNetwork")),
                "data_network": _network(node.get("dataNetwork")),
            }
        )
    observed_nodes.sort(key=lambda item: str(item["hostname"]).casefold())

    expected_services = []
    external = _mapping(cluster.get("external_services"), "inventory external_services")
    if external.get("management_service_ips"):
        expected_services.append(
            {
                "target": "Management",
                "pool": sorted(external["management_service_ips"]),
            }
        )
    if external.get("data_service_ips"):
        expected_services.append(
            {"target": "Data", "pool": sorted(external["data_service_ips"])}
        )
    expected_services.sort(key=lambda item: item["target"])

    expected_nodes = [
        {
            "hostname": node.get("hostname"),
            "role": str(node.get("type", "")).lower(),
            "deployment_type": "cimc",
            "cimc_ip": _mapping(node.get("cimc"), "inventory CIMC").get("ip"),
            "management_network": {
                "ipv4_address": (
                    f"{_mapping(node.get('mgmt'), 'inventory management network').get('ip')}"
                    f"/{_mapping(node.get('mgmt'), 'inventory management network').get('mask')}"
                ),
                "ipv4_gateway": _mapping(
                    node.get("mgmt"), "inventory management network"
                ).get("gateway"),
                "vlan": None,
            },
            "data_network": {
                "ipv4_address": (
                    f"{_mapping(node.get('data'), 'inventory data network').get('ip')}"
                    f"/{_mapping(node.get('data'), 'inventory data network').get('mask')}"
                ),
                "ipv4_gateway": _mapping(
                    node.get("data"), "inventory data network"
                ).get("gateway"),
                "vlan": _mapping(node.get("data"), "inventory data network").get(
                    "vlan"
                ),
            },
        }
        for node in nodes
    ]
    expected_nodes.sort(key=lambda item: str(item["hostname"]).casefold())

    observed_ntp = _ntp_servers(cluster_config)
    unverifiable_fields = []
    if any(server["preferred"] is None for server in observed_ntp):
        unverifiable_fields.append("cluster.ntp_servers[].preferred")

    return {
        "schema_version": 1,
        "baseline_kind": baseline_kind,
        "captured_at_utc": captured_at,
        "software_version": version.get("platformVersion"),
        "setup_state": current.get("state"),
        "runtime_state": cluster_status.get("state"),
        "api_unverifiable_fields": unverifiable_fields,
        "expected_from_inventory": {
            "cluster": {
                "name": cluster.get("name"),
                "persona": str(cluster.get("implementation_type", "LAN")).upper(),
                "name_servers": sorted(
                    _mapping(cluster.get("dns"), "inventory DNS").get("servers") or []
                ),
                "search_domains": sorted(
                    _mapping(cluster.get("dns"), "inventory DNS").get(
                        "search_domains"
                    )
                    or []
                ),
                "ntp_servers": [
                    {
                        "host": server.get("host"),
                        "preferred": bool(server.get("preferred", False)),
                    }
                    for server in _mapping(
                        cluster.get("ntp"), "inventory NTP"
                    ).get("servers", [])
                ],
                "app_network": _mapping(
                    cluster.get("internal_networks"), "inventory internal networks"
                ).get("app_network"),
                "service_network": _mapping(
                    cluster.get("internal_networks"), "inventory internal networks"
                ).get("service_network"),
                "external_services": expected_services,
            },
            "nodes": expected_nodes,
        },
        "observed_from_nd": {
            "cluster": {
                "name": cluster_config.get("name"),
                "persona": cluster_config.get("persona"),
                "name_servers": sorted(cluster_config.get("nameServers") or []),
                "search_domains": sorted(cluster_config.get("searchDomains") or []),
                "ntp_servers": observed_ntp,
                "app_network": cluster_config.get("appNetwork"),
                "service_network": cluster_config.get("serviceNetwork"),
                "external_services": _external_services(
                    cluster_config.get("externalServices")
                ),
            },
            "nodes": observed_nodes,
        },
        "evidence": {
            "chapter_source": "01-nd-cluster/docs/MOP-ND4-install.md",
            "screenshots_manifest": "01-nd-cluster/docs/screenshots/manifest.yaml",
        },
    }
