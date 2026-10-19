#!/usr/bin/env python3
"""Automated configuration and verification of Procedure 1 & 2 for Cisco UCS C880A M8.

Configures:
- Hostname and Domain / FQDN (Procedure 1)
- Static DNS Servers (Procedure 1)
- NTP Servers and Protocol Enabled (Procedure 1)
- Timezone / DateTimeLocalOffset (Procedure 1)
- Verifies SSH / SOL Service enabled on port 22 (Procedure 2)
- Audits settings persistence post-configuration
"""

import argparse
import base64
import json
from pathlib import Path
import ssl
import sys
import time
import urllib.error
import urllib.request
import yaml

from probe_c880_readonly import _read_vault_password, RedfishReader
from probe_c880_huu_postcheck import _read_host_spec, _read_shared_spec, _timezone_offset, audit_settings_persistence

HOSTS = ("ucs-c880-1", "ucs-c880-2", "ucs-c880-3", "ucs-c880-4")


def _get_opener(allow_self_signed=True):
    if allow_self_signed:
        context = ssl._create_unverified_context()
    else:
        context = ssl.create_default_context()
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))


def _redfish_patch(opener, url, auth, payload, retries=3):
    """Execute Redfish PATCH with mandatory ETag handling and retry on HTTP 412.
    
    Handles BMC-specific behavior where patching an already-applied value returns
    HTTP 400 with MessageId SyncAgent.1.0.PatchValueAlreadyExists.
    """
    for attempt in range(retries):
        time.sleep(3)  # MIN_REQUEST_SPACING_SECONDS to respect BMC controller
        # GET resource to acquire fresh ETag
        get_req = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "Authorization": auth},
            method="GET",
        )
        with opener.open(get_req, timeout=20) as resp:
            etag = resp.headers.get("ETag")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": auth,
        }
        if etag:
            headers["If-Match"] = etag

        body = json.dumps(payload).encode("utf-8")
        patch_req = urllib.request.Request(url, data=body, headers=headers, method="PATCH")
        try:
            with opener.open(patch_req, timeout=25) as resp:
                return resp.status
        except urllib.error.HTTPError as err:
            err_body = ""
            try:
                err_body = err.read().decode("utf-8")
            except Exception:
                pass
            if err.code in (200, 202, 204):
                return err.code
            if "PatchValueAlreadyExists" in err_body or "already applied" in err_body:
                return 204
            if err.code == 412 and attempt < retries - 1:
                time.sleep(5)
                continue
            raise
        except (http.client.RemoteDisconnected, ConnectionResetError):
            # Network interface reset during eth0 PATCH is an accepted BMC transition
            return 202
    raise RuntimeError(f"Redfish PATCH failed on {url} after {retries} attempts")


def configure_node(inventory_dir, host, *, allow_self_signed=True, logger=print):
    def log(msg):
        logger(msg, flush=True)

    if host not in HOSTS:
        raise ValueError(f"Host {host} is outside C880 workflow")

    host_spec = _read_host_spec(inventory_dir, host)
    shared_spec = _read_shared_spec(inventory_dir)
    password = _read_vault_password(inventory_dir, host_spec["pass_ref"])

    # Read hostname from host_vars
    h_path = Path(inventory_dir) / "host_vars" / f"{host}.yml"
    h_data = yaml.safe_load(h_path.read_text(encoding="utf-8")) or {}
    hostname = h_data.get("ucs", {}).get("hostname", f"AIPOD-UCS-{host.replace('ucs-', '').upper()}")

    ip = host_spec["ip"]
    user = host_spec["user"]
    domain = shared_spec["domain_name"]
    dns_servers = shared_spec["dns_servers"]
    ntp_servers = shared_spec["ntp_servers"]
    desired_offset = _timezone_offset(shared_spec["timezone"])

    auth = "Basic " + base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    opener = _get_opener(allow_self_signed)
    base_url = f"https://{ip}"
    reader = RedfishReader(ip, user, password, allow_self_signed_lab=allow_self_signed)

    log(f"Configuring Procedure 1 parameters on {host} ({ip})...")

    # Inspect current state to avoid redundant PATCH calls
    curr_net = reader("/redfish/v1/Managers/BMC/NetworkProtocol")
    curr_mgr = reader("/redfish/v1/Managers/BMC")
    curr_eth0 = reader("/redfish/v1/Managers/BMC/EthernetInterfaces/eth0")

    # 1. Configure NTP (NetworkProtocol)
    curr_ntp = curr_net.get("NTP", {})
    if curr_ntp.get("NTPServers") == ntp_servers and curr_ntp.get("ProtocolEnabled") is True:
        log(f"  - NTP servers already match target ({ntp_servers}); skipping PATCH.")
    else:
        ntp_payload = {
            "NTP": {
                "NTPServers": ntp_servers,
                "ProtocolEnabled": True,
            }
        }
        log("  - Applying NTP servers and enabling NTP protocol...")
        _redfish_patch(opener, f"{base_url}/redfish/v1/Managers/BMC/NetworkProtocol", auth, ntp_payload)

    # 2. Configure Timezone offset (DateTimeLocalOffset)
    curr_tz = curr_mgr.get("DateTimeLocalOffset")
    if curr_tz == desired_offset:
        log(f"  - Timezone offset already {desired_offset}; skipping PATCH.")
    else:
        log(f"  - Applying current offset {desired_offset} for {shared_spec['timezone']} (not a stored IANA-zone setting)...")
        tz_payload = {"DateTimeLocalOffset": desired_offset}
        _redfish_patch(opener, f"{base_url}/redfish/v1/Managers/BMC", auth, tz_payload)

    # 3. Configure Hostname, FQDN, StaticNameServers (eth0)
    static_dns = list(dns_servers)
    if "::" not in static_dns:
        static_dns.append("::")
    
    curr_dns = curr_eth0.get("StaticNameServers", [])
    curr_hn = curr_eth0.get("HostName")
    curr_fqdn = curr_eth0.get("FQDN")
    fqdn_target = f"{hostname}.{domain}"

    if curr_hn == hostname and curr_fqdn == fqdn_target and set(dns_servers).issubset(set(curr_dns)):
        log(f"  - Interface eth0 already configured (HostName={hostname}, FQDN={fqdn_target}); skipping PATCH.")
    else:
        eth0_payload = {
            "HostName": hostname,
            "FQDN": fqdn_target,
            "StaticNameServers": static_dns,
        }
        log(f"  - Applying HostName={hostname}, FQDN={fqdn_target}, StaticNameServers={dns_servers}...")
        try:
            _redfish_patch(opener, f"{base_url}/redfish/v1/Managers/BMC/EthernetInterfaces/eth0", auth, eth0_payload)
        except Exception as e:
            log(f"  - (Notice) eth0 interface reset triggered BMC network service restart: {e}")

        # Wait for BMC network interface restart to settle
        log("Waiting for BMC network services to settle after interface reconfiguration...")
        time.sleep(15)

    # 4. Verify Settings Persistence & Audit
    log(f"Verifying Procedure 1 settings persistence on {host}...")
    audit_res = None
    for attempt in range(15):
        try:
            audit_res = audit_settings_persistence(reader, host_spec, shared_spec)
            if audit_res["all_passed"]:
                log(f"  - Audit verified on attempt {attempt+1}.")
                break
        except Exception as e:
            log(f"  - Attempt {attempt+1}: waiting for BMC to become responsive ({type(e).__name__})...")
        time.sleep(5)

    if not audit_res or not audit_res["all_passed"]:
        raise RuntimeError(f"Procedure 1 settings verification failed on {host}: {audit_res}")

    log(f"SUCCESS: Procedure 1 & 2 fully configured and verified on {host}.")
    return audit_res


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory_dir", type=Path)
    parser.add_argument("--host", choices=HOSTS, required=True)
    parser.add_argument("--allow-self-signed", action="store_true", default=True)
    args = parser.parse_args()

    res = configure_node(args.inventory_dir, args.host, allow_self_signed=args.allow_self_signed)
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    import http.client
    main()
