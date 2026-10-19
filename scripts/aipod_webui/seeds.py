"""Device role classification and inventory-driven seeding of schema YAML documents.

Seeders update a round-tripped YAML document in place: values that come from the
initial inventory or shared services are refreshed, list entries are matched by
their natural key (hostname, name), and anything else the user edited is kept.
"""

import ipaddress
import re
from dataclasses import dataclass, field
from io import StringIO
from urllib.parse import urlsplit

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

ROLES = {
    "nd-node": "Nexus Dashboard node",
    "switch-backend": "Switch - backend fabric",
    "switch-frontend": "Switch - frontend fabric",
    "switch-mgmt": "Switch - management fabric",
    "fabric-interconnect": "UCS Fabric Interconnect",
    "x-direct": "UCS X-Direct (S9108)",
    "chassis": "UCS X9508 chassis",
    "ucs-blade": "UCS X-Series compute node",
    "ucs-server": "UCS C-Series standalone server",
    "hgx-node": "UCS HGX node (C845A / C880A)",
    "storage": "Storage array",
    "other": "Other",
}
SWITCH_ROLES = {"switch-backend": "backend", "switch-frontend": "frontend", "switch-mgmt": "mgmt"}
COMPUTE_ROLES = ("ucs-blade", "ucs-server", "hgx-node")
REGISTRATION_ROLES = ("fabric-interconnect", "x-direct", "ucs-server", "hgx-node")
BACKEND_PIDS = ("9364D-GX2A", "9332D-GX2B", "9364E-SG2", "9332D-H2R", "9364C-H1", "9808", "9804")
MGMT_PIDS = ("9348GC", "93108TC", "93180YC", "92348GC", "93216TC", "9300-48")
_HINTS = {"be": "switch-backend", "backend": "switch-backend", "fe": "switch-frontend", "frontend": "switch-frontend",
          "mgmt": "switch-mgmt", "oob": "switch-mgmt"}


def guess_role(row: dict) -> str:
    pid = str(row.get("pid", "")).upper()
    host = str(row.get("hostname", "")).lower()
    if re.search(r"ND-NODE|SE-NODE|ND-CLUSTER", pid):
        return "nd-node"
    if pid.startswith(("N9K", "N3K")):
        hint = re.search(r"(?:^|[-_.])(be|backend|fe|frontend|mgmt|oob)(?=[-_.\d]|$)", host)
        if hint:
            return _HINTS[hint.group(1)]
        if any(part in pid for part in BACKEND_PIDS):
            return "switch-backend"
        if any(part in pid for part in MGMT_PIDS):
            return "switch-mgmt"
        return "switch-frontend"
    if pid.startswith("UCS-FI") or re.match(r"UCS-?FI", pid):
        return "fabric-interconnect"
    if "S9108" in pid:
        return "x-direct"
    if pid.startswith("UCSX") and "9508" in pid:
        return "chassis"
    if re.search(r"C?8[48][05]A", pid) and not re.search(r"885A", pid):
        return "hgx-node"
    if pid.startswith("UCSX"):
        return "ucs-blade"
    if pid.startswith(("UCSC", "UCS-C", "HX")):
        return "ucs-server"
    if pid.startswith(("FA-", "FB-", "FLASHARRAY", "FLASHBLADE")) or "PURE" in pid:
        return "storage"
    return "other"


def row_role(row: dict) -> str:
    role = row.get("role") or ""
    return role if role in ROLES else guess_role(row)


def by_role(rows: list[dict], *roles: str) -> list[dict]:
    return [row for row in rows if row_role(row) in roles and row.get("hostname")]


def host_key(hostname: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", str(hostname).strip().lower()).strip("-")


def domain_name(hostname: str) -> str:
    """X-Direct / FI pairs share a domain name: hostname without the -a/-b suffix."""
    return re.sub(r"[-_]?(a|b|fi-?a|fi-?b)$", "", host_key(hostname)) or host_key(hostname)


def is_claimable(row: dict) -> bool:
    role = row_role(row)
    if role == "hgx-node":
        return "C880" not in str(row.get("pid", "")).upper()
    return role in REGISTRATION_ROLES


@dataclass
class SeedContext:
    rows: list[dict]
    services: dict
    state: dict = field(default_factory=dict)
    media_url: str = ""
    media_dir: str = ""
    media_files: list[str] = field(default_factory=list)
    macs: dict = field(default_factory=dict)


def _yaml() -> YAML:
    handler = YAML()
    handler.indent(mapping=2, sequence=4, offset=2)
    handler.preserve_quotes = True
    handler.width = 4096
    return handler


def load(text: str):
    data = _yaml().load(text or "") if (text or "").strip() else None
    return data if isinstance(data, CommentedMap) else CommentedMap()


def dump(data) -> str:
    stream = StringIO()
    _yaml().dump(data, stream)
    content = stream.getvalue()
    return content if content.startswith("---") else "---\n" + content


def ensure(node: CommentedMap, *path: str) -> CommentedMap:
    for key in path:
        if not isinstance(node.get(key), CommentedMap):
            node[key] = CommentedMap()
        node = node[key]
    return node


def seq(values) -> CommentedSeq:
    return CommentedSeq(list(values))


def set_if(node: CommentedMap, key: str, value) -> None:
    if value not in (None, "", [], {}):
        node[key] = value


def merge_list(existing, items: list[CommentedMap], key: str) -> CommentedSeq:
    """Return the seeded items, keeping user-entered fields of entries that match by key."""
    current = {str(item.get(key)): item for item in (existing or []) if isinstance(item, dict)}
    result = CommentedSeq()
    for item in items:
        previous = current.get(str(item.get(key)))
        if isinstance(previous, CommentedMap):
            for name, value in item.items():
                previous[name] = value
            result.append(previous)
        else:
            result.append(item)
    return result


def cmap(**values) -> CommentedMap:
    node = CommentedMap()
    for key, value in values.items():
        if value is not None:
            node[key] = value
    return node


def _proxy(services: dict) -> CommentedMap | None:
    proxy = services.get("proxy_servers") or {}
    out = CommentedMap()
    for key in ("http_proxy", "https_proxy"):
        if proxy.get(key):
            out[key] = proxy[key]
    if proxy.get("no_proxy"):
        out["no_proxy"] = seq(proxy["no_proxy"])
    return out or None


def _allocate(subnet: str, count: int, used: set[str], skip: tuple[str, ...] = ()) -> list[str]:
    try:
        network = ipaddress.ip_network(subnet, strict=False)
    except ValueError:
        return []
    reserved = set(used) | {value.split("/")[0] for value in skip if value}
    hosts = list(network.hosts())
    start = min(10, max(len(hosts) // 4, 0))
    picked = [str(address) for address in hosts[start:] if str(address) not in reserved]
    return picked[:count]


def _netmask(subnet: str) -> str:
    try:
        return str(ipaddress.ip_network(subnet, strict=False).netmask)
    except ValueError:
        return ""


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------
def seed_nd_cluster(data: CommentedMap, ctx: SeedContext) -> None:
    cluster = ensure(data, "nexus_dashboard", "cluster")
    services = ctx.services
    dns = ensure(cluster, "dns")
    set_if(dns, "servers", seq(services.get("dns_servers", [])))
    set_if(dns, "search_domains", seq(services.get("dns_search_domains", [])))
    if services.get("ntp_servers"):
        ensure(cluster, "ntp")["servers"] = seq(
            cmap(host=host, preferred=True) if index == 0 else cmap(host=host)
            for index, host in enumerate(services["ntp_servers"]))
    set_if(cluster, "timezone", services.get("timezone"))
    proxy = _proxy(services)
    if proxy:
        cluster["proxy"] = proxy
    iso = next((name for name in ctx.media_files if re.match(r"nd-dk9.*\.iso$", name)), "")
    if iso and ctx.media_url:
        parsed = urlsplit(ctx.media_url)
        node = ensure(cluster, "iso")
        node["url"] = f"{parsed.scheme}://{parsed.netloc}"
        node["file_path"] = "/".join(part for part in (parsed.path.strip("/"), iso) if part)
    network = cluster.get("network") or {}
    rows = by_role(ctx.rows, "nd-node")[:3]
    if not rows:
        return
    existing = {str(node.get("hostname")): node for node in cluster.get("nodes") or [] if isinstance(node, dict)}
    used = {str(node.get(part, {}).get("ip")) for node in existing.values() for part in ("mgmt", "data")
            if isinstance(node.get(part), dict)}
    used |= {str(address) for address in cluster.get("persistent_ips") or []}
    names = [host_key(row["hostname"]) for row in rows]
    mgmt_free = iter(_allocate(network.get("mgmt_subnet", ""), 3, used, (network.get("mgmt_gateway", ""),)))
    data_free = iter(_allocate(network.get("data_subnet", ""), 3, used, (network.get("data_gateway", ""),)))
    nodes = CommentedSeq()
    for index, (row, name) in enumerate(zip(rows, names)):
        node = existing.get(name) or CommentedMap()
        node["hostname"] = name
        node["type"] = "Primary"
        node["role"] = "bootstrap" if index == 0 else "secondary"
        cimc = node.get("cimc") if isinstance(node.get("cimc"), CommentedMap) else CommentedMap()
        cimc["ip"] = row.get("ip", "")
        cimc.setdefault("username", "admin")
        node["cimc"] = cimc
        for part, free, subnet, gateway in (("mgmt", mgmt_free, "mgmt_subnet", "mgmt_gateway"),
                                            ("data", data_free, "data_subnet", "data_gateway")):
            entry = node.get(part) if isinstance(node.get(part), CommentedMap) else CommentedMap()
            if not entry.get("ip"):
                entry["ip"] = next(free, "")
            entry["mask"] = _netmask(network.get(subnet, "")) or entry.get("mask", "")
            entry["gateway"] = network.get(gateway, entry.get("gateway", ""))
            node[part] = entry
        nodes.append(node)
    cluster["nodes"] = nodes


FABRIC_TYPES = {"backend": ("aiVxlanEvpn", "aiRouted"), "frontend": ("vxlanEbgp", "vxlanIbgp"), "mgmt": ("classicLan",)}


def seed_fabric(kind: str):
    role = next(role for role, name in SWITCH_ROLES.items() if name == kind)

    def seeder(data: CommentedMap, ctx: SeedContext) -> None:
        root = ensure(data, "nexus_dashboard")
        fabrics = root.get("fabrics") if isinstance(root.get("fabrics"), CommentedSeq) else CommentedSeq()
        types = FABRIC_TYPES[kind]
        matching = sorted((fabric for fabric in fabrics if isinstance(fabric, dict) and fabric.get("type") in types),
                          key=lambda fabric: types.index(fabric["type"]))
        fabric = matching[0] if matching else cmap(name=f"aipod-{kind}", type=types[0])
        rows = by_role(ctx.rows, role)
        if rows:
            switches = [cmap(ip=row.get("ip", ""), hostname=row["hostname"], model=row.get("pid", ""),
                             serialNumber=row.get("serial_number", ""),
                             softwareVersion=_existing_version(fabric, row["hostname"]),
                             switchRole=_switch_role(row["hostname"], kind)) for row in rows]
            fabric["switches"] = merge_list(fabric.get("switches"), switches, "hostname")
            for switch in fabric["switches"]:
                if not switch.get("switchRole"):
                    switch.pop("switchRole", None)
        root["fabrics"] = seq([fabric])

    return seeder


def _existing_version(fabric: dict, hostname: str) -> str:
    for switch in fabric.get("switches") or []:
        if isinstance(switch, dict) and switch.get("hostname") == hostname:
            return switch.get("softwareVersion", "")
    return ""


def _switch_role(hostname: str, kind: str) -> str | None:
    name = hostname.lower()
    if re.search(r"(^|[-_])(sp|spine|ss)\d*([-_]|$)|spine", name):
        return "spine"
    if re.search(r"(^|[-_])(bl|border)\d*([-_]|$)", name):
        return "border"
    if re.search(r"(^|[-_])(lf|leaf|tor|sw)\d*([-_]|$)|leaf", name) or kind == "mgmt":
        return "leaf"
    return None


# ---------------------------------------------------------------------------
# Compute
# ---------------------------------------------------------------------------
def _profiles(data: CommentedMap) -> CommentedMap:
    return ensure(data, "intersight", "configure", "default", "profiles")


def _domain_for(hostname: str, domains: list[str]) -> str:
    name = host_key(hostname)
    matches = [domain for domain in domains if name.startswith(domain)]
    return max(matches, key=len) if matches else (domains[0] if domains else "")


def _domains(ctx: SeedContext) -> dict[str, list[str]]:
    """Domain profile name -> Fabric Interconnect / X-Direct serial numbers."""
    domains: dict[str, list[str]] = {}
    for row in by_role(ctx.rows, "fabric-interconnect", "x-direct"):
        domains.setdefault(domain_name(row["hostname"]), []).append(row.get("serial_number", ""))
    return domains


def seed_domain_profiles(data: CommentedMap, ctx: SeedContext) -> None:
    """UCS Domains page: domain and chassis profiles."""
    profiles = _profiles(data)
    domains = _domains(ctx)
    if not domains:
        return
    template = next(iter(profiles.get("domain") or []), None) or cmap(action="Deploy", attach_template=True,
                                                                       ucs_domain_profile_template="XDirect")
    items = []
    for name, serials in domains.items():
        item = cmap(name=name)
        item.update((key, value) for key, value in template.items() if key not in ("name", "serial_numbers"))
        item["serial_numbers"] = seq(serial for serial in serials if serial)
        items.append(item)
    profiles["domain"] = merge_list(profiles.get("domain"), items, "name")
    chassis = by_role(ctx.rows, "chassis")
    if chassis:
        template = next(iter(profiles.get("chassis") or []), None) or cmap(action="No-op")
        entry = CommentedMap((key, value) for key, value in template.items() if key != "targets")
        entry["targets"] = merge_list(next(iter(profiles.get("chassis") or []), {}).get("targets"), [
            cmap(name=host_key(row["hostname"]), serial_number=row.get("serial_number", "")) for row in chassis], "name")
        profiles["chassis"] = seq([entry])


def seed_xseries_profiles(data: CommentedMap, ctx: SeedContext) -> None:
    """UCS Servers page: X-Series blade server profiles, one entry per domain."""
    names = list(_domains(ctx))
    blades = by_role(ctx.rows, "ucs-blade")
    if blades and names:
        profiles = _profiles(data)
        templates = {str(item.get("domain_name")): item for item in profiles.get("server") or [] if isinstance(item, dict)}
        fallback = next(iter(templates.values()), None) or cmap(action="No-op", attach_template=True,
                                                                target_platform="FIAttached",
                                                                ucs_server_profile_template="AIOptimized")
        servers = CommentedSeq()
        for domain in names:
            members = [row for row in blades if _domain_for(row["hostname"], names) == domain]
            if not members:
                continue
            base = templates.get(domain, fallback)
            entry = CommentedMap((key, value) for key, value in base.items() if key != "targets")
            entry["domain_name"] = domain
            entry["target_platform"] = "FIAttached"
            entry["targets"] = merge_list(base.get("targets") if domain in templates else None, [
                cmap(name=host_key(row["hostname"]), serial_number=row.get("serial_number", "")) for row in members], "name")
            for target in entry["targets"]:
                if target.get("serial_number"):
                    target.pop("pre_assign", None)
            servers.append(entry)
        profiles["server"] = servers


def seed_server_profiles(data: CommentedMap, ctx: SeedContext) -> None:
    rows = [row for row in by_role(ctx.rows, "ucs-server", "hgx-node") if is_claimable(row)]
    if not rows:
        return
    profiles = _profiles(data)
    existing = [item for item in profiles.get("server") or [] if isinstance(item, dict)]
    standalone = next((item for item in existing if item.get("target_platform") == "Standalone"), None)
    if standalone is None:
        standalone = cmap(action="No-op", attach_template=True, server_family="UCSC2XX/4XX",
                          target_platform="Standalone", ucs_server_profile_template="AIOptimized")
        existing.append(standalone)
    standalone["targets"] = merge_list(standalone.get("targets"), [
        cmap(name=row["hostname"], serial_number=row.get("serial_number", "")) for row in rows], "name")
    profiles["server"] = seq(existing)


# ---------------------------------------------------------------------------
# OpenShift and observability
# ---------------------------------------------------------------------------
def _bare_metal(data: CommentedMap) -> CommentedMap:
    return ensure(data, "openshift", "install", "bare_metal")


def _interfaces(hostname: str, macs: dict, previous) -> CommentedMap | None:
    collected = macs.get(hostname) or macs.get(host_key(hostname)) or {}
    if not collected:
        return previous if isinstance(previous, CommentedMap) else None
    if isinstance(previous, CommentedMap):
        members = [member for group in ("bond", "ethernet") for entry in previous.get(group) or []
                   for member in ((entry.get("interfaces") or []) if group == "bond" else [entry])]
        if any(member.get("name") in collected for member in members):
            for member in members:
                if member.get("name") in collected:
                    member["mac"] = collected[member["name"]]
        else:
            # Hardware sources (Redfish, Intersight) do not know the OS names, so fill in port order.
            ports = [collected[name] for name in sorted(collected, key=_port_order) if not name.startswith("mlx-")]
            for member, mac in zip(members, ports):
                member["mac"] = mac
        return previous
    return cmap(ethernet=seq(cmap(name=name, mac=mac, lldp_enabled=True, mtu=9000)
                             for name, mac in sorted(collected.items())))


def seed_ocp_install(data: CommentedMap, ctx: SeedContext) -> None:
    bare = _bare_metal(data)
    services = ctx.services
    set_if(bare, "base_dns_domain", services.get("domain_name"))
    networking = ensure(bare, "cluster_networking")
    set_if(networking, "dns_servers", seq(services.get("dns_servers", [])))
    set_if(bare, "ntp_servers", seq(services.get("ntp_servers", [])))
    if ctx.media_url:
        web = ensure(bare, "iso_web_server")
        web["image_base_url"] = ctx.media_url.rstrip("/")
        web["image_upload_directory"] = ctx.media_dir or web.get("image_upload_directory", "")
        web["server_address"] = "localhost"
        for key in ("username", "password", "ssh_public_key"):
            web.pop(key, None)
    fis = by_role(ctx.rows, "fabric-interconnect", "x-direct")
    if fis:
        bare["fabric_interconnects"] = merge_list(bare.get("fabric_interconnects"), [
            cmap(ip=row.get("ip", ""), username="admin", password=1) for row in fis], "ip")
    domains = [domain_name(row["hostname"]) for row in fis]
    domain_ip = {}
    for row in fis:
        domain_ip.setdefault(domain_name(row["hostname"]), row.get("ip", ""))
    rows = by_role(ctx.rows, *COMPUTE_ROLES)
    if not rows:
        return
    previous = {str(item.get("hostname")): item for item in bare.get("servers") or [] if isinstance(item, dict)}
    servers = CommentedSeq()
    for index, row in enumerate(rows):
        name = host_key(row["hostname"])
        item = previous.get(name) or CommentedMap()
        item["hostname"] = name
        item.setdefault("role", "master" if index < 3 and len(rows) > 3 else "worker")
        if row_role(row) == "ucs-blade":
            item.pop("redfish", None)
            fi = ensure(item, "fabric_interconnect")
            fi["id"] = domain_ip.get(_domain_for(name, domains), fi.get("id", 1)) or 1
            fi["inventory_id"] = name
        else:
            item.pop("fabric_interconnect", None)
            redfish = ensure(item, "redfish")
            redfish["ip"] = row.get("ip", "")
            redfish.setdefault("password", 2)
            redfish["type"] = "bmc" if row_role(row) == "hgx-node" else "cimc"
            redfish.setdefault("username", "root" if row_role(row) == "hgx-node" else "admin")
        interfaces = _interfaces(name, ctx.macs, item.get("interfaces"))
        item["interfaces"] = interfaces if interfaces is not None else cmap(ethernet=seq([
            cmap(name="eno5", mac="00:00:00:00:00:00", lldp_enabled=True, mtu=9000)]))
        servers.append(item)
    bare["servers"] = servers


def seed_ocp_certificates(data: CommentedMap, ctx: SeedContext) -> None:
    install = ctx.state.get("ocp-cluster", {})
    cluster, domain = install.get("cluster_name"), install.get("base_dns_domain") or ctx.services.get("domain_name")
    if cluster and domain:
        certificates = ensure(data, "openshift", "certificates")
        certificates["api_server_hostname"] = f"api.{cluster}.{domain}"


def seed_ocp_ldap(data: CommentedMap, ctx: SeedContext) -> None:
    shared = ctx.services.get("ldap") or {}
    if not shared:
        return
    ldap = ensure(data, "openshift", "ldap")
    for key in ("url", "base_dn", "bind_dn", "base_dn_users", "base_dn_groups", "secure_ldap"):
        if key in shared:
            ldap[key] = shared[key]
        elif key in ("base_dn_users", "base_dn_groups"):
            ldap.pop(key, None)


def hgx_model(pid: str) -> str:
    text = str(pid or "").upper()
    return "C845A" if re.search(r"C?845", text) else "C880A" if re.search(r"C?880", text) else ""


def seed_hgx(data: CommentedMap, ctx: SeedContext) -> None:
    """BMC settings from the shared services; servers from the HGX inventory rows and the Claim Targets addresses."""
    from .stage_inventory import HGX_PASSWORD_REF, registration_hosts

    root = ensure(data, "hgx_servers")
    settings = ensure(root, "bmc_settings")
    for key in ("dns_servers", "ntp_servers"):
        if ctx.services.get(key):
            settings[key] = seq(ctx.services[key])
    for key in ("domain_name", "timezone"):
        if ctx.services.get(key):
            settings[key] = ctx.services[key]
    registration = ctx.state.get("intersight-registration", {})
    if registration.get("cimc_username"):
        settings["username"] = registration["cimc_username"]
    settings["password_ref"] = HGX_PASSWORD_REF
    default_user = settings.get("username", "admin")
    hosts = [item["ucs"] for item in registration_hosts(ctx.rows, registration).values()
             if item["ucs"]["device_role"] == "hgx-node"]
    if not hosts:
        return
    servers = CommentedSeq()
    for ucs in hosts:
        server = CommentedMap()
        server["hostname"] = str(ucs["hostname"]).split(".")[0]
        model = hgx_model(ucs.get("pid", ""))
        if model:
            server["model"] = model
        if ucs.get("serial_number"):
            server["serial_number"] = ucs["serial_number"]
        bmc = CommentedMap()
        bmc["ip"] = ucs["cimc"]["ip"]
        if ucs["cimc"].get("user") and ucs["cimc"]["user"] != default_user:
            bmc["username"] = ucs["cimc"]["user"]
        if ucs["cimc"].get("pass_ref") and ucs["cimc"]["pass_ref"] != HGX_PASSWORD_REF:
            bmc["password_ref"] = ucs["cimc"]["pass_ref"]
        server["bmc"] = bmc
        servers.append(server)
    root["servers"] = servers


def _port_order(name: str) -> tuple:
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name))


def seed_ocp_operators(data: CommentedMap, ctx: SeedContext) -> None:
    operators = ensure(data, "openshift", "operators")
    network = operators.get("nvidia_network_operator")
    if not isinstance(network, CommentedMap) or not ctx.macs:
        return
    hosts = [host_key(row["hostname"]) for row in by_role(ctx.rows, *COMPUTE_ROLES)]
    previous = {str(item.get("hostname")): item for item in network.get("persistent_net_rules") or [] if isinstance(item, dict)}
    template = [entry.get("name") for entry in next(iter(previous.values()), {}).get("interfaces") or []]
    rules = CommentedSeq()
    for host in hosts:
        collected = ctx.macs.get(host, {})
        mellanox = {name: mac for name, mac in collected.items() if name.startswith(("ens", "enp", "mlx-")) and mac}
        if not mellanox:
            if host in previous:
                rules.append(previous[host])
            continue
        if template and not any(name in mellanox for name in template):
            ordered = [mellanox[name] for name in sorted(mellanox, key=_port_order)]
            mellanox = dict(zip(template, ordered))
        names = [name for name in template if name in mellanox] or sorted(mellanox)
        rules.append(cmap(hostname=host, interfaces=seq(cmap(name=name, mac=mellanox[name]) for name in names)))
    if rules:
        network["persistent_net_rules"] = rules


def seed_splunk(data: CommentedMap, ctx: SeedContext) -> None:
    root = ensure(data, "splunk_observability")
    proxy = _proxy(ctx.services)
    collector = root.get("otel_collector")
    if not proxy:
        # The example proxy is only a placeholder; without a shared proxy the collector connects directly.
        if isinstance(collector, dict):
            collector.pop("proxy", None)
    else:
        collector = ensure(root, "otel_collector")
        merged = CommentedMap()
        merged["http_proxy"] = proxy.get("http_proxy") or proxy.get("https_proxy")
        merged["https_proxy"] = proxy.get("https_proxy") or proxy.get("http_proxy")
        merged["no_proxy"] = seq(dict.fromkeys(list(proxy.get("no_proxy") or []) + suggested_no_proxy(ctx)))
        collector["proxy"] = merged
    cluster = ctx.state.get("ocp-cluster", {}).get("cluster_name")
    if cluster:
        ensure(root, "openshift_cluster")["cluster_name"] = cluster


def suggested_no_proxy(ctx: SeedContext) -> list[str]:
    """Destinations that must bypass the proxy for in-cluster and on-site traffic."""
    install = ctx.state.get("ocp-cluster", {})
    values = ["localhost", "127.0.0.1", ".svc.cluster.local", ".cluster.local",
              install.get("cluster_network") or "10.128.0.0/14", install.get("service_network") or "172.30.0.0/16"]
    domain = install.get("base_dns_domain") or ctx.services.get("domain_name")
    if domain and install.get("cluster_name"):
        values += [f"apps.{install['cluster_name']}.{domain}", f".{install['cluster_name']}.{domain}"]
    if domain:
        values.append(f".{domain}")
    if install.get("machine_network"):
        values.append(install["machine_network"])
    return values


SEEDERS = {
    "nd_cluster": seed_nd_cluster,
    "fabric_backend": seed_fabric("backend"),
    "fabric_frontend": seed_fabric("frontend"),
    "fabric_mgmt": seed_fabric("mgmt"),
    "domain_profiles": seed_domain_profiles,
    "xseries_profiles": seed_xseries_profiles,
    "server_profiles": seed_server_profiles,
    "ocp_install": seed_ocp_install,
    "ocp_certificates": seed_ocp_certificates,
    "ocp_ldap": seed_ocp_ldap,
    "hgx": seed_hgx,
    "ocp_operators": seed_ocp_operators,
    "splunk": seed_splunk,
}


def apply_seed(name: str, text: str, ctx: SeedContext) -> str:
    seeder = SEEDERS.get(name)
    if not seeder:
        return text
    data = load(text)
    seeder(data, ctx)
    return dump(data)
