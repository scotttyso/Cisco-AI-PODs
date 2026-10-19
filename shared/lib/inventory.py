"""Canonical Ansible-inventory loading and validation for AI POD."""
from __future__ import annotations

import ipaddress
from copy import deepcopy
import json
import re
import shutil
import subprocess
import sys
from urllib.parse import urlparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError



class InventoryError(ValueError):
    pass


@dataclass(frozen=True)
class NetworkInterface:
    ip: str
    mask: int
    gateway: str
    vlan: int | None = None

    @property
    def cidr(self) -> str:
        return f"{self.ip}/{self.mask}"


@dataclass(frozen=True)
class Cimc:
    ip: str
    user: str
    pass_ref: str


@dataclass(frozen=True)
class Node:
    hostname: str
    type: str
    role: str
    cimc: Cimc
    mgmt: NetworkInterface
    data: NetworkInterface


@dataclass(frozen=True)
class IsoConfig:
    url: str
    sha512: str


@dataclass(frozen=True)
class NetworkConfig:
    mgmt_subnet: str
    mgmt_gateway: str
    data_subnet: str
    data_gateway: str
    # An ND node touches three networks: ND-MGMT, ND-DATA, and the OOB subnet
    # its CIMC sits on. ND has no interface on the third, so it is optional
    # here and absent from older inventories.
    oob_subnet: str | None = None
    oob_gateway: str | None = None


@dataclass(frozen=True)
class InternalNetworks:
    app_network: str
    service_network: str


@dataclass(frozen=True)
class ExternalServices:
    management_service_ips: list[str]
    data_service_ips: list[str]


@dataclass(frozen=True)
class DnsConfig:
    servers: list[str]
    search_domains: list[str]


@dataclass(frozen=True)
class NtpServer:
    host: str
    preferred: bool = False


@dataclass(frozen=True)
class ProxyConfig:
    skip: bool
    url: str | None = None
    ignore_hosts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Cluster:
    start_mode: str
    name: str
    implementation_type: str
    timezone: str
    iso: IsoConfig
    network: NetworkConfig
    internal_networks: InternalNetworks
    dns: DnsConfig
    ntp: list[NtpServer]
    proxy: ProxyConfig
    external_services: ExternalServices

    @property
    def persistent_ips(self) -> list[str]:
        """Compatibility name used by the existing post-install validator."""
        return self.external_services.data_service_ips


@dataclass(frozen=True)
class Runtime:
    state_dir: str
    ca_bundle: str | None
    verify_tls: bool
    cluster_bringup_timeout_s: int


@dataclass(frozen=True)
class Inventory:
    cluster: Cluster
    runtime: Runtime
    nodes: list[Node]
    admin_username: str
    admin_pass_ref: str

    @property
    def bootstrap_node(self) -> Node:
        for n in self.nodes:
            if n.role == "bootstrap":
                return n
        raise InventoryError("no node has role: bootstrap")

    @property
    def secondary_nodes(self) -> list[Node]:
        return [n for n in self.nodes if n.role != "bootstrap"]


def _ip(value: str) -> str:
    try:
        ipaddress.ip_address(value)
    except ValueError as e:
        raise InventoryError(f"invalid IP {value!r}: {e}") from e
    return value


def _subnet(value: str) -> str:
    try:
        ipaddress.ip_network(value, strict=False)
    except ValueError as e:
        raise InventoryError(f"invalid subnet {value!r}: {e}") from e
    return value


def _mask(value: int) -> int:
    if not isinstance(value, int) or not 0 < value <= 32:
        raise InventoryError(f"invalid mask {value!r}; expected 1..32")
    return value


def _net(d: dict[str, Any], where: str) -> NetworkInterface:
    if not isinstance(d, dict):
        raise InventoryError(f"{where}: expected mapping, got {type(d).__name__}")
    return NetworkInterface(
        ip=_ip(d["ip"]),
        mask=_mask(d["mask"]),
        gateway=_ip(d["gateway"]),
        vlan=d.get("vlan"),
    )


def load_ansible(
    inventory_path: str | Path,
    *,
    inventory_bin: str | Path | None = None,
    schema_path: str | Path | None = None,
) -> Inventory:
    """Load the ND inventory after Ansible has merged its vars.

    The Ansible inventory is the operator-facing source for the lab.  This
    adapter deliberately shells out to ``ansible-inventory --list`` rather
    than reimplementing Ansible's precedence rules.  The merged result is
    reshaped into the ND schema structure, schema-validated, and passed through
    ``_build_inventory`` so cross-field semantic checks remain in force.
    """
    path = Path(inventory_path)
    if not path.exists():
        raise InventoryError(f"missing Ansible inventory: {path}")

    if inventory_bin:
        executable = str(inventory_bin)
    else:
        executable = shutil.which("ansible-inventory")
        if not executable:
            sibling = Path(sys.executable).with_name("ansible-inventory")
            executable = str(sibling) if sibling.is_file() else None
    if not executable:
        raise InventoryError(
            "ansible-inventory was not found on PATH or beside the active "
            "Python interpreter; use the AI POD environment or pass "
            "inventory_bin explicitly"
        )

    command = [executable, "-i", str(path), "--list"]
    try:
        completed = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as e:
        raise InventoryError(f"could not run ansible-inventory: {e}") from e
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise InventoryError(
            f"ansible-inventory failed with exit {completed.returncode}: {detail}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as e:
        raise InventoryError(f"ansible-inventory returned invalid JSON: {e}") from e

    composed = _composed_from_ansible(payload)
    resolved_schema = Path(schema_path) if schema_path else (
        Path(__file__).resolve().parents[2] / "schemas" / "nd-cluster.schema.json"
    )
    _validate_schema_instance(composed, resolved_schema)
    return _inventory_from_composed_dict(composed)


def resolve_nd_site_services(
    cluster_spec: dict[str, Any], aipod: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Map shared aipod values to ND's existing internal API shape.

    Legacy fully expanded specifications stay compatible when no aipod
    mapping is supplied. Shared and local copies must not coexist.
    Host domain and DNS search domains have deliberately separate meanings.
    Timezone is retained as intent, not an unsupported nd_setup argument.
    """
    if not isinstance(cluster_spec, dict):
        raise InventoryError("nd_cluster_spec must be a mapping")
    result = deepcopy(cluster_spec)
    if aipod is None and all(key in result for key in ("dns", "ntp")):
        return result
    if any(key in result for key in ("dns", "ntp", "timezone")):
        raise InventoryError("shared ND services cannot have local dns/ntp/timezone overrides")
    if not isinstance(aipod, dict):
        raise InventoryError("missing aipod mapping")
    required = {
        "domain_name", "dns_servers", "dns_search_domains", "ntp_servers",
        "ntp_preferred_server", "timezone",
    }
    if not required.issubset(aipod):
        raise InventoryError("aipod is missing required service fields")

    def domain(value):
        return isinstance(value, str) and len(value) <= 253 and all(
            re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", part)
            for part in value.split(".")
        )

    if not domain(aipod["domain_name"]):
        raise InventoryError("invalid aipod.domain_name")
    search = aipod["dns_search_domains"]
    if (not isinstance(search, list) or not all(domain(item) for item in search)
            or len(set(search)) != len(search)):
        raise InventoryError("invalid aipod.dns_search_domains")
    dns = aipod["dns_servers"]
    if (not isinstance(dns, list) or not dns or not all(isinstance(x, str) for x in dns)
            or len(set(dns)) != len(dns)):
        raise InventoryError("invalid aipod.dns_servers")
    for address in dns:
        try:
            ipaddress.IPv4Address(address)
        except ValueError as exc:
            raise InventoryError("invalid aipod.dns_servers") from exc
    ntp = aipod["ntp_servers"]
    if (not isinstance(ntp, list) or len(ntp) < 2 or not all(domain(x) for x in ntp)
            or len(set(ntp)) != len(ntp)):
        raise InventoryError("invalid aipod.ntp_servers")
    preferred = aipod["ntp_preferred_server"]
    if not isinstance(preferred, str) or preferred not in ntp:
        raise InventoryError("ntp_preferred_server must be one of ntp_servers")
    timezone = aipod["timezone"]
    try:
        if not isinstance(timezone, str):
            raise ValueError("timezone is not a string")
        ZoneInfo(timezone)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise InventoryError("invalid aipod.timezone") from exc
    result.update(
        dns={"servers": deepcopy(dns), "search_domains": deepcopy(search)},
        ntp={"servers": [{"host": host, "preferred": host == preferred} for host in ntp]},
        timezone=timezone,
    )
    return result


def inventory_from_merged_vars(
    cluster_spec: dict[str, Any],
    runtime: dict[str, Any],
    admin_username: str,
    admin_pass_ref: str,
    nodes: list[dict[str, Any]],
    *,
    aipod: dict[str, Any] | None = None,
) -> Inventory:
    """Build an Inventory from vars Ansible has already merged.

    Controller-side filter plugins use this to share the exact same semantic
    validation and dataclasses as the Python CLI without recursively invoking
    ``ansible-inventory`` from inside an Ansible run.
    """
    return _inventory_from_composed_dict(
        {
            "cluster": resolve_nd_site_services(cluster_spec, aipod),
            "runtime": runtime,
            "admin_username": admin_username,
            "admin_pass_ref": admin_pass_ref,
            "nodes": nodes,
        }
    )


def _group_hosts(payload: dict[str, Any], group: str) -> list[str]:
    """Return a group's hosts in Ansible's declared order, recursively."""
    groups = payload.get(group)
    if not isinstance(groups, dict):
        raise InventoryError(f"Ansible inventory is missing group {group!r}")

    result: list[str] = []

    def add(name: str) -> None:
        if name not in result:
            result.append(name)

    for host in groups.get("hosts", []) or []:
        if isinstance(host, str):
            add(host)
    for child in groups.get("children", []) or []:
        if not isinstance(child, str) or child not in payload:
            raise InventoryError(f"Ansible group {group!r} references missing child {child!r}")
        for host in _group_hosts(payload, child):
            add(host)
    if not result:
        raise InventoryError(f"Ansible group {group!r} contains no hosts")
    return result


def _composed_from_ansible(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert ``ansible-inventory --list`` JSON to the ND schema shape."""
    if not isinstance(payload, dict):
        raise InventoryError("Ansible inventory output must be a JSON object")
    metadata = payload.get("_meta", {})
    if not isinstance(metadata, dict):
        raise InventoryError("Ansible inventory output has invalid _meta data")
    hostvars = metadata.get("hostvars", {})
    if not isinstance(hostvars, dict):
        raise InventoryError("Ansible inventory output has no usable _meta.hostvars")

    hosts = _group_hosts(payload, "nd_cluster")
    nodes: list[dict[str, Any]] = []
    cluster_spec: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None
    admin_username: str | None = None
    admin_ref: str | None = None

    for host in hosts:
        values = hostvars.get(host)
        if not isinstance(values, dict):
            raise InventoryError(f"Ansible inventory has no hostvars for {host!r}")
        node = values.get("nd_node")
        if not isinstance(node, dict):
            raise InventoryError(f"host {host!r} is missing nd_node host vars")
        nodes.append(node)

        candidate_cluster = values.get("nd_cluster_spec")
        if not isinstance(candidate_cluster, dict):
            raise InventoryError(f"host {host!r} is missing nd_cluster_spec group vars")
        candidate_cluster = resolve_nd_site_services(
            candidate_cluster, values.get("aipod")
        )
        if cluster_spec is None:
            cluster_spec = candidate_cluster
        elif candidate_cluster != cluster_spec:
            raise InventoryError(
                f"nd_cluster_spec differs between hosts; first mismatch at {host!r}"
            )

        candidate_runtime = values.get("nd_runtime", {})
        if not isinstance(candidate_runtime, dict):
            raise InventoryError(f"host {host!r} has invalid nd_runtime group vars")
        if runtime is None:
            runtime = candidate_runtime
        elif candidate_runtime != runtime:
            raise InventoryError(f"nd_runtime differs between hosts; mismatch at {host!r}")

        candidate_username = values.get("nd_admin_username")
        if not isinstance(candidate_username, str) or not candidate_username:
            raise InventoryError(f"host {host!r} is missing nd_admin_username")
        if admin_username is None:
            admin_username = candidate_username
        elif candidate_username != admin_username:
            raise InventoryError(
                f"nd_admin_username differs between hosts; mismatch at {host!r}"
            )

        candidate_admin = values.get("nd_admin_pass_ref")
        if not isinstance(candidate_admin, str) or not candidate_admin:
            raise InventoryError(f"host {host!r} is missing nd_admin_pass_ref")
        if admin_ref is None:
            admin_ref = candidate_admin
        elif candidate_admin != admin_ref:
            raise InventoryError(f"nd_admin_pass_ref differs between hosts; mismatch at {host!r}")

    assert cluster_spec is not None and admin_username is not None and admin_ref is not None
    return {
        "cluster": cluster_spec,
        "runtime": runtime or {},
        "admin_username": admin_username,
        "admin_pass_ref": admin_ref,
        "nodes": nodes,
    }


def _validate_schema_instance(instance: dict[str, Any], schema_path: Path) -> None:
    """Validate one instance with the repository's local JSON Schema tree."""
    if not schema_path.exists():
        raise InventoryError(f"inventory schema not found: {schema_path}")
    try:
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
        from referencing.jsonschema import DRAFT202012
    except ImportError as e:
        raise InventoryError(
            "JSON Schema validation requires the inventory environment's "
            "jsonschema and referencing packages"
        ) from e

    seen: dict[Path, dict[str, Any]] = {}
    registry = Registry()

    def load_schema(path: Path) -> dict[str, Any]:
        nonlocal registry
        path = path.resolve()
        if path in seen:
            return seen[path]
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise InventoryError(f"could not read schema {path}: {e}") from e
        seen[path] = document
        resource = Resource(contents=document, specification=DRAFT202012)
        if "$id" in document:
            registry = registry.with_resource(uri=document["$id"], resource=resource)
        registry = registry.with_resource(uri=path.as_uri(), resource=resource)

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                ref = value.get("$ref")
                if isinstance(ref, str) and not ref.startswith(("#", "http://", "https://")):
                    target = ref.split("#", 1)[0]
                    if target:
                        load_schema(path.parent / target)
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(document)
        return document

    load_schema(schema_path)
    validator = Draft202012Validator(
        {"$ref": schema_path.resolve().as_uri()}, registry=registry
    )
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.absolute_path))
    if errors:
        details = []
        for error in errors:
            location = "/".join(str(part) for part in error.absolute_path) or "(root)"
            details.append(f"{location}: {error.message}")
        raise InventoryError(
            f"Ansible inventory failed schema validation against {schema_path}: "
            + "; ".join(details)
        )


def _inventory_from_composed_dict(composed: dict[str, Any]) -> Inventory:
    """Build the existing dataclass model from a validated composed dict."""
    return _build_inventory(
        {"cluster": composed["cluster"], "runtime": composed.get("runtime", {})},
        {
            "admin_username": composed["admin_username"],
            "admin_pass_ref": composed["admin_pass_ref"],
            "nodes": composed["nodes"],
        },
    )


def _build_inventory(c_raw: dict[str, Any], n_raw: dict[str, Any]) -> Inventory:
    """Validate a cluster dict + nodes dict into an Inventory.

    Both the CLI adapter and the Ansible filter funnel through here so
    validation is identical in either execution path.
    """
    try:
        c = c_raw["cluster"]
        rt = c_raw.get("runtime", {})

        cluster = Cluster(
            start_mode=str(c["start_mode"]),
            name=str(c["name"]),
            implementation_type=str(c.get("implementation_type", "LAN")),
            timezone=str(c.get("timezone", "UTC")),
            iso=IsoConfig(url=str(c["iso"]["url"]), sha512=str(c["iso"]["sha512"])),
            network=NetworkConfig(
                mgmt_subnet=_subnet(c["network"]["mgmt_subnet"]),
                mgmt_gateway=_ip(c["network"]["mgmt_gateway"]),
                data_subnet=_subnet(c["network"]["data_subnet"]),
                data_gateway=_ip(c["network"]["data_gateway"]),
                oob_subnet=(_subnet(c["network"]["oob_subnet"])
                            if c["network"].get("oob_subnet") else None),
                oob_gateway=(_ip(c["network"]["oob_gateway"])
                             if c["network"].get("oob_gateway") else None),
            ),
            internal_networks=InternalNetworks(
                app_network=_subnet(c["internal_networks"]["app_network"]),
                service_network=_subnet(c["internal_networks"]["service_network"]),
            ),
            dns=DnsConfig(
                servers=[_ip(s) for s in c["dns"].get("servers", [])],
                search_domains=list(c["dns"].get("search_domains", [])),
            ),
            ntp=[NtpServer(host=str(s["host"]), preferred=bool(s.get("preferred", False)))
                 for s in c["ntp"]["servers"]],
            proxy=ProxyConfig(
                skip=bool(c["proxy"].get("skip", True)),
                url=c["proxy"].get("url"),
                ignore_hosts=list(c["proxy"].get("ignore_hosts", []) or []),
            ),
            external_services=ExternalServices(
                management_service_ips=[
                    _ip(s) for s in c["external_services"].get(
                        "management_service_ips", []
                    )
                ],
                data_service_ips=[
                    _ip(s) for s in c["external_services"]["data_service_ips"]
                ],
            ),
        )

        runtime = Runtime(
            state_dir=str(rt.get("state_dir", "state/")),
            ca_bundle=rt.get("ca_bundle"),
            verify_tls=bool(rt.get("verify_tls", True)),
            cluster_bringup_timeout_s=int(rt.get("cluster_bringup_timeout_s", 3600)),
        )
    except KeyError as e:
        raise InventoryError(f"cluster inventory missing required field: {e}") from e

    if cluster.start_mode not in {"factory_preinstalled", "iso_reimage"}:
        raise InventoryError(
            "start_mode must be factory_preinstalled or iso_reimage, got "
            f"{cluster.start_mode!r}"
        )
    if len(cluster.external_services.data_service_ips) < 5:
        raise InventoryError(
            "external_services.data_service_ips: need at least 5 IPs, got "
            f"{len(cluster.external_services.data_service_ips)}"
        )
    if len(cluster.ntp) < 2:
        raise InventoryError(
            f"ntp.servers: need at least 2 NTP servers, got {len(cluster.ntp)}"
        )

    try:
        admin_username = str(n_raw["admin_username"])
        admin_ref = str(n_raw["admin_pass_ref"])
        nodes_raw = n_raw["nodes"]
    except KeyError as e:
        raise InventoryError(f"node inventory missing required field: {e}") from e

    if not isinstance(nodes_raw, list) or len(nodes_raw) != 3:
        raise InventoryError(f"nodes: expected exactly 3 nodes, got {len(nodes_raw)}")

    nodes: list[Node] = []
    for i, n in enumerate(nodes_raw):
        try:
            nodes.append(Node(
                hostname=str(n["hostname"]),
                type=str(n.get("type", "Primary")),
                role=str(n.get("role", "secondary" if i > 0 else "bootstrap")),
                cimc=Cimc(ip=_ip(n["cimc"]["ip"]),
                          user=str(n["cimc"]["user"]),
                          pass_ref=str(n["cimc"]["pass_ref"])),
                mgmt=_net(n["mgmt"], f"nodes[{i}].mgmt"),
                data=_net(n["data"], f"nodes[{i}].data"),
            ))
        except KeyError as e:
            raise InventoryError(f"nodes[{i}] missing required field: {e}") from e

    bootstrap_count = sum(1 for n in nodes if n.role == "bootstrap")
    if bootstrap_count != 1:
        raise InventoryError(
            f"exactly one node must have role: bootstrap, found {bootstrap_count}"
        )

    _validate_internal_networks(cluster, nodes)

    if not admin_username:
        raise InventoryError("admin_username must not be empty")

    return Inventory(
        cluster=cluster,
        runtime=runtime,
        nodes=nodes,
        admin_username=admin_username,
        admin_pass_ref=admin_ref,
    )


def _validate_internal_networks(cluster: Cluster, nodes: list[Node]) -> None:
    """Enforce Cisco's ND 4.3.x internal-network constraints.

    Both IPv4 networks must be /16, must not overlap each other, and must not
    contain or overlap any externally reachable address represented by the
    canonical inventory. This is intentionally repeated after JSON Schema
    validation because JSON Schema cannot express cross-field overlap rules.
    """
    app = ipaddress.ip_network(cluster.internal_networks.app_network, strict=False)
    service = ipaddress.ip_network(
        cluster.internal_networks.service_network, strict=False
    )
    for label, network in (("app_network", app), ("service_network", service)):
        if network.prefixlen != 16:
            raise InventoryError(
                f"internal_networks.{label}: ND 4.3.x requires an IPv4 /16, "
                f"got {network}"
            )
    if app.overlaps(service):
        raise InventoryError(
            f"internal ND networks overlap: {app} and {service}"
        )

    external_subnets = {
        "ND-MGMT": ipaddress.ip_network(cluster.network.mgmt_subnet, strict=False),
        "ND-DATA": ipaddress.ip_network(cluster.network.data_subnet, strict=False),
    }
    if cluster.network.oob_subnet:
        external_subnets["CIMC/OOB-MGMT"] = ipaddress.ip_network(
            cluster.network.oob_subnet, strict=False
        )
    for internal_name, internal in (("app_network", app), ("service_network", service)):
        for external_name, external in external_subnets.items():
            if internal.overlaps(external):
                raise InventoryError(
                    f"internal_networks.{internal_name} {internal} overlaps "
                    f"{external_name} {external}"
                )

    endpoints: dict[str, str] = {}
    endpoints.update({f"DNS[{i}]": value for i, value in enumerate(cluster.dns.servers)})
    for i, server in enumerate(cluster.ntp):
        try:
            ipaddress.ip_address(server.host)
        except ValueError:
            continue
        endpoints[f"NTP[{i}]"] = server.host
    for node in nodes:
        endpoints[f"{node.hostname}.CIMC"] = node.cimc.ip
        endpoints[f"{node.hostname}.ND-MGMT"] = node.mgmt.ip
        endpoints[f"{node.hostname}.ND-DATA"] = node.data.ip
    iso_host = urlparse(cluster.iso.url).hostname
    if iso_host:
        try:
            ipaddress.ip_address(iso_host)
        except ValueError:
            pass
        else:
            endpoints["ISO server"] = iso_host

    for endpoint_name, value in endpoints.items():
        endpoint = ipaddress.ip_address(value)
        for internal_name, internal in (("app_network", app), ("service_network", service)):
            if endpoint in internal:
                raise InventoryError(
                    f"internal_networks.{internal_name} {internal} contains "
                    f"external endpoint {endpoint_name} ({endpoint})"
                )
