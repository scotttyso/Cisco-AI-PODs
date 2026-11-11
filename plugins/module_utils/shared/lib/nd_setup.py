"""Pure mapping from canonical ND inventory to ``cisco.nd.nd_setup`` args."""
from __future__ import annotations

from typing import Any, Callable

from .inventory import Inventory, InventoryError


def _serials_by_host(artifact: dict[str, Any]) -> dict[str, dict[str, str]]:
    nodes = artifact.get("nodes")
    if not isinstance(nodes, dict):
        raise InventoryError("serial artifact is missing its nodes mapping")
    normalized: dict[str, dict[str, str]] = {}
    for hostname, record in nodes.items():
        key = str(hostname).casefold()
        if key in normalized:
            raise InventoryError(
                f"serial artifact has duplicate hostname keys differing only by case: "
                f"{hostname!r}"
            )
        normalized[key] = record
    return normalized


def build_nd_setup_args(
    inv: Inventory,
    serial_artifact: dict[str, Any],
    *,
    admin_password: str,
    resolve_cimc_password: Callable[[str], str],
) -> dict[str, Any]:
    """Return the exact argument dictionary for ``cisco.nd.nd_setup``.

    Serial numbers are deliberately absent from editable inventory. The
    runtime artifact binds each discovered serial to both the product hostname
    and its CIMC IP; a mismatch fails before any setup request is sent. Lookup
    is case-insensitive so a pre-migration artifact keyed by ``nd-1`` remains
    usable after the product hostname becomes ``ND-1``.
    """
    serials = _serials_by_host(serial_artifact)
    nodes: list[dict[str, Any]] = []
    for node in inv.nodes:
        discovered = serials.get(node.hostname.casefold())
        if not isinstance(discovered, dict):
            raise InventoryError(
                f"serial artifact has no entry for {node.hostname}"
            )
        if discovered.get("cimc_ip") != node.cimc.ip:
            raise InventoryError(
                f"serial artifact CIMC mismatch for {node.hostname}: "
                f"{discovered.get('cimc_ip')!r} != {node.cimc.ip!r}"
            )
        serial = str(discovered.get("serial_number") or "").strip()
        if not serial:
            raise InventoryError(
                f"serial artifact has an empty serial for {node.hostname}"
            )
        mapped: dict[str, Any] = {
            "hostname": node.hostname,
            "serial_number": serial,
            "deployment_type": "physical",
            "role": node.type.lower(),
            "management_ip_address": node.cimc.ip,
            "username": node.cimc.user,
            "password": resolve_cimc_password(node.cimc.pass_ref),
            "management_network": {
                "ipv4_address": node.mgmt.cidr,
                "ipv4_gateway": node.mgmt.gateway,
            },
            "data_network": {
                "ipv4_address": node.data.cidr,
                "ipv4_gateway": node.data.gateway,
            },
        }
        if node.data.vlan is not None:
            mapped["data_network"]["vlan"] = node.data.vlan
        nodes.append(mapped)

    bootstrap = inv.bootstrap_node
    cluster = inv.cluster
    external_services: dict[str, list[str]] = {}
    if cluster.external_services.management_service_ips:
        external_services["management_service_ips"] = list(
            cluster.external_services.management_service_ips
        )
    if cluster.external_services.data_service_ips:
        external_services["data_service_ips"] = list(
            cluster.external_services.data_service_ips
        )

    setup_args: dict[str, Any] = {
        "host": bootstrap.mgmt.ip,
        "username": inv.admin_username,
        "password": admin_password,
        "use_ssl": True,
        "validate_certs": inv.runtime.verify_tls,
        "timeout": inv.runtime.cluster_bringup_timeout_s,
        "output_level": "info",
        "cluster_name": cluster.name,
        "persona": cluster.implementation_type.lower(),
        "dns_server": list(cluster.dns.servers),
        "ntp_config": {
            "servers": [
                {
                    "ntp_host": server.host,
                    "preferred": server.preferred,
                }
                for server in cluster.ntp
            ]
        },
        "app_network": cluster.internal_networks.app_network,
        "service_network": cluster.internal_networks.service_network,
        # cisco.nd 1.5.0 tests ``is not None`` rather than truthiness. Omit an
        # empty pool so it does not emit an invalid externalServices entry
        # whose pool is []. The outer dictionary must still exist on ND 4.1+.
        "external_services": external_services,
        "nodes": nodes,
        "state": "present",
    }
    # DNS search domains are optional in ND. Omitting the argument when the
    # canonical list is empty preserves the UI's "Not configured" state.
    if cluster.dns.search_domains:
        setup_args["dns_search_domain"] = list(cluster.dns.search_domains)

    return setup_args
