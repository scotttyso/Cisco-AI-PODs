#!/usr/bin/env python3
"""Paced GET-only post-HUU firmware baseline and settings persistence audit for Cisco UCS C880A M8.

Audits:
1. Procedure 5 (HUU) firmware baselines:
   - NVIDIA BlueField-3 DPU/NIC (NIC3, NIC9): 32.47.1088
   - Intel X710-T2L OCP 3.0 (NIC4): 1.3862.0
   - Micron 9550 NVMe controllers (StorageUnit_0, StorageUnit_1): F3MU111
2. Procedure 1 Settings Persistence (surviving OOB and HUU power cycles):
   - BMC Static IPv4, Netmask, Gateway (EthernetInterfaces/eth0)
   - NTP configuration & protocol enabled (NetworkProtocol)
   - SSH service enabled on port 22 (NetworkProtocol)
   - Timezone offset configured (DateTimeLocalOffset)
"""

import argparse
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import sys
import time
import yaml
from zoneinfo import ZoneInfo

from probe_c880_readonly import (
    MIN_REQUEST_SPACING_SECONDS,
    RedfishReader,
    _read_vault_password,
    _resource_path,
)

HUU_TARGETS = {
    "network_adapters": {
        "NIC3": {"model": "D3B6", "expected_package": "32.47.1088", "desc": "NVIDIA BlueField-3 #1"},
        "NIC9": {"model": "D3B6", "expected_package": "32.47.1088", "desc": "NVIDIA BlueField-3 #2"},
        "NIC4": {"model": "CAI-O-ID10GC", "expected_package": "1.3862.0", "desc": "Intel X710-T2L OCP"},
    },
    "storage_controllers": {
        "StorageUnit_0": {"expected_version": "F3MU111", "desc": "Micron 9550 NVMe #1"},
        "StorageUnit_1": {"expected_version": "F3MU111", "desc": "Micron 9550 NVMe #2"},
    },
}


def _read_host_spec(inventory_dir, host):
    path = Path(inventory_dir) / "host_vars" / f"{host}.yml"
    if not path.is_file():
        raise FileNotFoundError(f"Host vars not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    ucs = data.get("ucs", {})
    if ucs.get("platform") != "standalone" or ucs.get("role") != "gpu":
        raise ValueError(f"Host {host} is not a standalone GPU server")
    cimc = ucs.get("cimc", {})
    return {
        "hostname": ucs.get("hostname", f"AIPOD-UCS-{host.replace('ucs-', '').upper()}"),
        "ip": cimc.get("ip"),
        "netmask": cimc.get("netmask", "255.255.255.0"),
        "gateway": cimc.get("gateway", "198.18.0.254"),
        "user": cimc.get("user", "admin"),
        "pass_ref": cimc.get("pass_ref"),
    }


def _read_shared_spec(inventory_dir):
    all_path = Path(inventory_dir) / "group_vars" / "all.yml"
    data = yaml.safe_load(all_path.read_text(encoding="utf-8")) or {}
    aipod = data.get("aipod") if isinstance(data, dict) else None
    return _validate_shared_spec(aipod)


def _validate_shared_spec(aipod):
    """Require the existing site globals; never substitute lab defaults."""
    if not isinstance(aipod, dict):
        raise ValueError("Missing or invalid aipod mapping")
    for field in ("dns_servers", "ntp_servers"):
        values = aipod.get(field)
        if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v.strip() for v in values):
            raise ValueError(f"Missing or invalid aipod.{field}")
        if len(set(values)) != len(values):
            raise ValueError(f"Duplicate aipod.{field}")
    for server in aipod["dns_servers"]:
        ipaddress.ip_address(server)
    domain = aipod.get("domain_name")
    if not isinstance(domain, str) or not domain.strip() or any(c.isspace() for c in domain):
        raise ValueError("Missing or invalid aipod.domain_name")
    zone = aipod.get("timezone")
    if not isinstance(zone, str) or not zone:
        raise ValueError("Missing or invalid aipod.timezone")
    ZoneInfo(zone)
    return {"dns_servers": list(aipod["dns_servers"]), "ntp_servers": list(aipod["ntp_servers"]),
            "domain_name": domain, "timezone": zone}


def _timezone_offset(zone, at=None):
    """Current offset only: this does not establish stored IANA zone/DST support."""
    instant = at if at is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("Timezone comparison requires an aware instant")
    minutes = int(instant.astimezone(ZoneInfo(zone)).utcoffset().total_seconds() // 60)
    return f"{'+' if minutes >= 0 else '-'}{abs(minutes)//60:02d}:{abs(minutes)%60:02d}"


def audit_huu_firmware(reader, targets=HUU_TARGETS, pause=None):
    """Audit Procedure 5 firmware baselines for BlueField-3, Intel OCP, and Micron NVMe."""
    results = {"adapters": {}, "storage": {}, "all_passed": True}
    
    # Audit Network Adapters
    for nic_id, spec in targets["network_adapters"].items():
        if pause:
            pause(MIN_REQUEST_SPACING_SECONDS)
        na = reader(f"/redfish/v1/Chassis/DGX/NetworkAdapters/{nic_id}")
        controllers = na.get("Controllers", [])
        actual_pkg = controllers[0].get("FirmwarePackageVersion") if controllers else None
        health = na.get("Status", {}).get("Health")
        state = na.get("Status", {}).get("State")
        
        passed = (actual_pkg == spec["expected_package"]) and (health == "OK")
        if not passed:
            results["all_passed"] = False
            
        results["adapters"][nic_id] = {
            "description": spec["desc"],
            "expected_version": spec["expected_package"],
            "actual_version": actual_pkg,
            "health": health,
            "state": state,
            "passed": passed,
        }
        
    # Audit Storage Controllers
    if pause:
        pause(MIN_REQUEST_SPACING_SECONDS)
    st_coll = reader("/redfish/v1/Systems/DGX/Storage")
    storage_members = {
        m.get("@odata.id").split("/")[-1]: m.get("@odata.id")
        for m in st_coll.get("Members", [])
        if isinstance(m, dict) and "@odata.id" in m
    }
    
    for st_id, spec in targets["storage_controllers"].items():
        if st_id not in storage_members:
            results["storage"][st_id] = {
                "description": spec["desc"],
                "expected_version": spec["expected_version"],
                "actual_version": None,
                "passed": False,
                "error": "Storage unit not found in Redfish collection",
            }
            results["all_passed"] = False
            continue
            
        if pause:
            pause(MIN_REQUEST_SPACING_SECONDS)
        st = reader(storage_members[st_id])
        ctrls = st.get("StorageControllers", [])
        actual_ver = ctrls[0].get("FirmwareVersion") if ctrls else None
        health = st.get("Status", {}).get("Health")
        state = st.get("Status", {}).get("State")
        
        passed = (actual_ver == spec["expected_version"]) and (health == "OK")
        if not passed:
            results["all_passed"] = False
            
        results["storage"][st_id] = {
            "description": spec["desc"],
            "expected_version": spec["expected_version"],
            "actual_version": actual_ver,
            "health": health,
            "state": state,
            "passed": passed,
        }
        
    return results


def audit_settings_persistence(reader, host_spec, shared_spec, pause=None, *, at=None):
    """Audit Procedure 1 settings persistence surviving BMC reboot and electronic power cycles."""
    shared_spec = _validate_shared_spec(shared_spec)
    expected_offset = _timezone_offset(shared_spec["timezone"], at)
    if pause:
        pause(MIN_REQUEST_SPACING_SECONDS)
    
    # Query eth0 with retry to allow BMC network services to settle if recovering from reboot
    eth0 = None
    for attempt in range(5):
        if pause and attempt > 0:
            pause(MIN_REQUEST_SPACING_SECONDS)
        eth0 = reader("/redfish/v1/Managers/BMC/EthernetInterfaces/eth0")
        if eth0.get("LinkStatus") != "NoLink" and eth0.get("IPv4Addresses"):
            break
        if attempt < 4 and pause:
            pause(3)

    if pause:
        pause(MIN_REQUEST_SPACING_SECONDS)
    net = reader("/redfish/v1/Managers/BMC/NetworkProtocol")
    
    if pause:
        pause(MIN_REQUEST_SPACING_SECONDS)
    mgr = reader("/redfish/v1/Managers/BMC")
    
    ipv4_list = eth0.get("IPv4Addresses", [])
    ipv4 = ipv4_list[0] if (isinstance(ipv4_list, list) and ipv4_list) else {}
    actual_ip = ipv4.get("Address")
    actual_mask = ipv4.get("SubnetMask")
    actual_gw = ipv4.get("Gateway")
    
    actual_hn = eth0.get("HostName")
    actual_fqdn = eth0.get("FQDN")
    actual_dns = eth0.get("StaticNameServers") or []
    
    ntp = net.get("NTP", {})
    ntp_servers = ntp.get("NTPServers", [])
    ntp_enabled = ntp.get("ProtocolEnabled", False)
    
    ssh = net.get("SSH", {})
    ssh_enabled = ssh.get("ProtocolEnabled", False)
    ssh_port = ssh.get("Port", 22)
    
    tz_offset = mgr.get("DateTimeLocalOffset")
    
    expected_ip = host_spec.get("ip")
    expected_mask = host_spec.get("netmask", "255.255.255.0")
    expected_gw = host_spec.get("gateway", "198.18.0.254")
    expected_ntp = shared_spec["ntp_servers"]
    
    expected_hn = host_spec.get("hostname")
    hn_ok = (actual_hn == expected_hn) if (expected_hn is not None and "HostName" in eth0) else True

    expected_domain = shared_spec.get("domain_name")
    expected_fqdn = f"{expected_hn}.{expected_domain}" if (expected_hn and expected_domain) else None
    fqdn_ok = (actual_fqdn == expected_fqdn) if (expected_fqdn is not None and "FQDN" in eth0) else True

    expected_dns = shared_spec.get("dns_servers")
    dns_ok = set(expected_dns).issubset(set(actual_dns)) if (expected_dns is not None and "StaticNameServers" in eth0) else True

    ip_ok = (actual_ip == expected_ip)
    mask_ok = (actual_mask == expected_mask)
    gw_ok = (actual_gw == expected_gw)
    ntp_ok = set(expected_ntp).issubset(set(ntp_servers)) and ntp_enabled
    ssh_ok = ssh_enabled and (ssh_port == 22)
    tz_ok = tz_offset == expected_offset
    
    all_passed = all([ip_ok, mask_ok, gw_ok, ntp_ok, ssh_ok, tz_ok, hn_ok, fqdn_ok, dns_ok])
    
    details = {
        "ipv4_address": {"expected": expected_ip, "actual": actual_ip, "passed": ip_ok},
        "subnet_mask": {"expected": expected_mask, "actual": actual_mask, "passed": mask_ok},
        "gateway": {"expected": expected_gw, "actual": actual_gw, "passed": gw_ok},
        "ntp_servers": {"expected": expected_ntp, "actual": ntp_servers, "enabled": ntp_enabled, "passed": ntp_ok},
        "ssh_service": {"expected_port": 22, "actual_port": ssh_port, "enabled": ssh_enabled, "passed": ssh_ok},
        "timezone_offset": {
            "expected": expected_offset,
            "desired_timezone": shared_spec["timezone"],
            "scope": "current_offset_only",
            "actual": tz_offset,
            "passed": tz_ok,
        },
    }
    if expected_hn is not None and "HostName" in eth0:
        details["hostname"] = {"expected": expected_hn, "actual": actual_hn, "passed": hn_ok}
    if expected_fqdn is not None and "FQDN" in eth0:
        details["fqdn"] = {"expected": expected_fqdn, "actual": actual_fqdn, "passed": fqdn_ok}
    if expected_dns is not None and "StaticNameServers" in eth0:
        details["dns_servers"] = {"expected": expected_dns, "actual": actual_dns, "passed": dns_ok}

    return {
        "all_passed": all_passed,
        "details": details,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory_dir", type=Path)
    parser.add_argument("--host", choices=["ucs-c880-1", "ucs-c880-2", "ucs-c880-3", "ucs-c880-4"], required=True)
    parser.add_argument("--allow-self-signed", action="store_true", default=True)
    args = parser.parse_args()

    host_spec = _read_host_spec(args.inventory_dir, args.host)
    shared_spec = _read_shared_spec(args.inventory_dir)
    password = _read_vault_password(args.inventory_dir, host_spec["pass_ref"])

    reader = RedfishReader(
        host_spec["ip"],
        host_spec["user"],
        password,
        allow_self_signed_lab=args.allow_self_signed,
    )

    print(f"Auditing HUU firmware baselines on {args.host} ({host_spec['ip']})...")
    huu_res = audit_huu_firmware(reader)
    print(f"HUU Firmware Audit Passed: {huu_res['all_passed']}")
    print(json.dumps(huu_res, indent=2))

    print(f"\nAuditing Procedure 1 settings persistence on {args.host} ({host_spec['ip']})...")
    persist_res = audit_settings_persistence(reader, host_spec, shared_spec)
    print(f"Settings Persistence Audit Passed: {persist_res['all_passed']}")
    print(json.dumps(persist_res, indent=2))

    if not (huu_res["all_passed"] and persist_res["all_passed"]):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
