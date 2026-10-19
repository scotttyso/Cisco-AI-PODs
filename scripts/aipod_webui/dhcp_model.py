"""Build the dhcp_server (Kea) data model from the initial inventory and shared services."""

import ipaddress
import json
import subprocess

DEFAULT_BOOTSTRAP_NETWORK = "198.18.0.0/24"


def host_interfaces() -> list[dict]:
    """IPv4 interfaces on this host as dicts with name, address, and network."""
    try:
        output = subprocess.run(["ip", "-j", "-4", "addr"], check=False, capture_output=True, text=True, timeout=5).stdout
        links = json.loads(output or "[]")
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    interfaces = []
    for link in links:
        if "LOOPBACK" in link.get("flags", []):
            continue
        for address in link.get("addr_info", []):
            if address.get("family") == "inet":
                interface = ipaddress.ip_interface(f"{address['local']}/{address['prefixlen']}")
                interfaces.append(dict(name=link["ifname"], address=str(interface.ip), network=str(interface.network)))
    return interfaces


def default_gateway() -> str:
    """This host's IPv4 default gateway, or an empty string."""
    try:
        output = subprocess.run(["ip", "-j", "-4", "route", "show", "default"], check=False, capture_output=True,
                                text=True, timeout=5).stdout
        routes = json.loads(output or "[]")
    except (OSError, ValueError, subprocess.SubprocessError):
        return ""
    return next((route["gateway"] for route in routes if route.get("gateway")), "")


def covering_network(addresses, smallest: int = 24, largest: int = 16) -> str:
    """The smallest network (no smaller than /24, no larger than /16) that holds every IPv4 address given."""
    ips = []
    for value in addresses or []:
        try:
            ips.append(ipaddress.IPv4Address(str(value).strip()))
        except ValueError:
            continue
    if not ips:
        return ""
    for prefix in range(smallest, largest - 1, -1):
        network = ipaddress.IPv4Network(f"{ips[0]}/{prefix}", strict=False)
        if all(ip in network for ip in ips):
            return str(network)
    return ""


def suggest_network(interfaces: list[dict], addresses) -> tuple[str, str]:
    """(network, source) for the bootstrap subnet: a host interface holding the inventory addresses, else the
    smallest network that covers them, else the documentation default."""
    addresses = [str(value).strip() for value in addresses or [] if str(value).strip()]
    for item in interfaces:
        network = ipaddress.ip_network(item["network"])
        if addresses and any(_inside(address, network) for address in addresses):
            return item["network"], f"host interface {item['name']}"
    covering = covering_network(addresses)
    if covering:
        return covering, "the Initial Inventory addresses"
    return DEFAULT_BOOTSTRAP_NETWORK, "the default bootstrap network"


def _inside(address: str, network) -> bool:
    try:
        return ipaddress.ip_address(address) in network
    except ValueError:
        return False


def _ipv4(values) -> tuple[list[str], list[str]]:
    kept, skipped = [], []
    for value in values or []:
        try:
            kept.append(str(ipaddress.IPv4Address(str(value).strip())))
        except ValueError:
            skipped.append(str(value))
    return kept, skipped


def build_dhcp_model(inventory: list[dict], shared_services: dict, options: dict) -> tuple[dict, list[str]]:
    """Return ({'dhcp': ...}, warnings). Raises ValueError for unusable input."""
    warnings = []
    network = ipaddress.IPv4Network(str(options.get("network") or DEFAULT_BOOTSTRAP_NETWORK).strip(), strict=False)
    subnet = {"name": str(options.get("subnet_name") or "bootstrap").strip(), "network": str(network.network_address),
              "netmask": str(network.netmask)}

    routers, bad = _ipv4(options.get("routers") or [])
    if bad:
        raise ValueError(f"Router must be an IPv4 address: {', '.join(bad)}")
    for router in routers:
        if ipaddress.IPv4Address(router) not in network:
            raise ValueError(f"Router {router} is outside {network}")
    if routers:
        subnet["routers"] = routers

    for key, label in (("tftp_server", "TFTP/POAP server"),):
        value = str(options.get(key) or "").strip()
        if value:
            try:
                subnet[key] = str(ipaddress.IPv4Address(value))
            except ValueError as error:
                raise ValueError(f"{label} must be an IPv4 address") from error
    bootfile = str(options.get("bootfile") or "").strip()
    if bootfile:
        subnet["bootfile"] = bootfile

    start, end = str(options.get("pool_start") or "").strip(), str(options.get("pool_end") or "").strip()
    if start or end:
        if not (start and end):
            raise ValueError("Set both the pool start and end addresses, or neither")
        first, last = ipaddress.IPv4Address(start), ipaddress.IPv4Address(end)
        if first not in network or last not in network or first > last:
            raise ValueError(f"Pool {start} - {end} must be an ascending range inside {network}")
        subnet["ranges"] = [{"start": str(first), "end": str(last)}]
    subnet["deny_unknown_clients"] = bool(options.get("deny_unknown_clients", True))

    dhcp = {}
    interfaces = [name for name in options.get("interfaces") or [] if name]
    if interfaces:
        dhcp["interfaces"] = interfaces
    dhcp["authoritative"] = True
    if shared_services.get("domain_name"):
        dhcp["domain_name"] = shared_services["domain_name"]
    for key, target in (("dns_servers", "domain_name_servers"), ("ntp_servers", "ntp_servers")):
        kept, skipped = _ipv4(shared_services.get(key))
        if skipped:
            warnings.append(f"Kea needs IPv4 addresses for {target}; skipped {', '.join(skipped)}")
        if kept:
            dhcp[target] = kept
    if shared_services.get("dns_search_domains"):
        dhcp["global_options"] = [{"name": "domain-search", "value": ", ".join(shared_services["dns_search_domains"])}]
    lease = int(options.get("lease_time") or 3600)
    dhcp["default_lease_time"] = lease
    dhcp["max_lease_time"] = max(lease, 86400)
    dhcp["subnets"] = [subnet]

    reservations, macs, addresses = [], set(), set()
    for row in inventory:
        mac, address = str(row.get("mac", "")).strip().lower(), str(row.get("ip", "")).strip()
        hostname = str(row.get("hostname", "")).strip()
        label = hostname if hostname and hostname != "unknown" else mac
        if not mac or not address:
            continue
        try:
            ip = ipaddress.IPv4Address(address)
        except ValueError:
            warnings.append(f"{label}: {address} is not IPv4; skipped")
            continue
        if ip not in network:
            warnings.append(f"{label}: {address} is outside {network}; skipped")
            continue
        if mac in macs or address in addresses:
            raise ValueError(f"{label}: duplicate MAC or IP address in the inventory")
        macs.add(mac)
        addresses.add(address)
        reservation = {"subnet": subnet["name"], "mac": mac, "ip": address}
        if hostname and hostname != "unknown":
            reservation["hostname"] = hostname
        reservations.append(reservation)
    if not reservations and "ranges" not in subnet:
        raise ValueError(f"No inventory addresses fall inside {network}, and no dynamic pool is set")
    dhcp["reservations"] = reservations
    return {"dhcp": dhcp}, warnings


def apply_commands(repository: str, vars_file: str) -> str:
    return (
        f"cd {repository}\n"
        "# Render and validate only (no changes to the host):\n"
        "ansible-playbook 00-environment-prep/automation/playbooks/deploy_dhcp_server.yml \\\n"
        "  -i localhost, -c local -e dhcp_hosts=localhost \\\n"
        f"  -e dhcp_vars_file={vars_file} \\\n"
        "  -e dhcp_render_only=true -e dhcp_render_dest=/tmp/kea-dhcp4.conf\n\n"
        "# Install, configure, and start Kea (requires sudo):\n"
        "ansible-playbook 00-environment-prep/automation/playbooks/deploy_dhcp_server.yml \\\n"
        "  -i localhost, -c local -e dhcp_hosts=localhost \\\n"
        f"  -e dhcp_vars_file={vars_file} --ask-become-pass\n\n"
        "# Check the service and leases:\n"
        "systemctl status kea-dhcp4 || systemctl status kea-dhcp4-server\n"
        "sudo tail -f /var/lib/kea/kea-leases4.csv\n"
    )
