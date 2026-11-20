"""Diagnose virtual media mounts on Fabric Interconnect attached blades, talking Redfish to the FI directly.

Nothing here goes through iserver, so every request and CIMC answer is visible.

  inspect  read-only: per blade the CIMC firmware and clock (compared with this host), CIMC IP/gateway/VLAN/DNS,
           every virtual media slot with the CIMC's own message, the CIMC log, and from this host the image URL
           and the web server's TLS certificate (validity window against the CIMC clock).
  mount    eject, insert an image URL and show a timestamped timeline of the slot (state, health, CIMC message),
           the requests the CIMC makes to the web server (nginx log), then eject and clean up.

Where the FI and credentials come from (first match):
  --fi IP --username U with the password from --password-env (default FI_PASSWORD) or from an Ansible vault
    (--vault-file / --vault-password-file / --vault-key), blades chosen with --blade (repeatable, or "all");
  otherwise the FI attached servers in <dir>/server.json (default: assisted-installer).
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import ssl
import subprocess
import sys
import time
import urllib.parse
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import requests
import urllib3

urllib3.disable_warnings()
REPO_ROOT = Path(__file__).resolve().parents[1]
REDFISH = "/api-explorer/resources/redfish/v1"
DEFAULT_DIR = REPO_ROOT / "assisted-installer"
DEFAULT_ACCESS_LOG = Path("/var/log/nginx/access.log")
CLOCK_SKEW_LIMIT = datetime.timedelta(minutes=10)

# What a CIMC message tells you; matched in order, case-insensitive substring.
MESSAGE_HINTS = (
    ("not found on server", "The CIMC reached the web server but the file is not there or not readable by Nginx "
                            "(wrong name or path, permissions, SELinux label)."),
    ("mount failed", "Generic failure, reported immediately when the connection is refused or reset (lab: closed "
                     "port). The CIMC does not validate the web server certificate. If Nginx logged no request from "
                     "the CIMC, the TCP/TLS connection never completed: check the web server's listener and TLS "
                     "settings, firewall, and the CIMC route/VLAN to it."),
)


class FiError(Exception):
    pass


class Fi:
    """One FI session; blades are addressed with the Inventory-Type/Inventory-Id headers."""

    def __init__(self, ip: str, username: str, password: str):
        self.ip, self.username, self.password = ip, username, password
        self.session = requests.Session()
        self.session.verify = False

    def __enter__(self) -> "Fi":
        try:
            response = self.session.post(f"https://{self.ip}/Login", json={"User": self.username, "Password": self.password},
                                         timeout=20)
        except requests.RequestException as error:
            raise FiError(f"cannot reach {self.ip}: {type(error).__name__}") from None
        if response.status_code != 200:
            raise FiError(f"login to {self.ip} failed ({response.status_code}): {response.text.strip()[:120]}")
        return self

    def __exit__(self, *exc_info):
        try:
            self.session.post(f"https://{self.ip}/Logout", headers=self.csrf(), timeout=10)
        except requests.RequestException:
            pass

    def csrf(self) -> dict:
        return {"X-Csrf-Token": urllib.parse.unquote(self.session.cookies.get("csrf", ""))}

    def blades(self) -> list[str]:
        response = self.session.get(f"https://{self.ip}/Servers", timeout=30)
        response.raise_for_status()
        return [item.get("Name", "") for item in response.json().get("Results", []) if item.get("Name")]

    def get(self, blade: str, uri: str) -> tuple[int, dict | str]:
        response = self.session.get(f"https://{self.ip}{REDFISH}{uri}", headers={"Inventory-Type": "Server",
                                    "Inventory-Id": blade}, timeout=40)
        try:
            return response.status_code, response.json()
        except ValueError:
            return response.status_code, response.text[:200]

    def post(self, blade: str, uri: str, body: dict) -> tuple[int, str]:
        response = self.session.post(f"https://{self.ip}{REDFISH}{uri}", json=body, timeout=60,
                                     headers={"Inventory-Type": "Server", "Inventory-Id": blade, **self.csrf()})
        return response.status_code, response.text[:300]


class Output:
    def __init__(self, secrets: list[str]):
        self.secrets = [secret for secret in secrets if secret]

    def line(self, text: str = "") -> None:
        for secret in self.secrets:
            text = text.replace(secret, "********")
        print(text, flush=True)


def slot_summary(body: dict | str) -> dict:
    if not isinstance(body, dict):
        return {"error": str(body)}
    status = body.get("Status") or {}
    messages = status.get("Health@Message.ExtendedInfo") or []
    return {"id": str(body.get("Id", "")), "name": body.get("Name", ""), "inserted": bool(body.get("Inserted")),
            "state": status.get("State", "?"), "health": status.get("Health", "?"), "image": body.get("Image") or "",
            "message": messages[0].get("Message", "") if messages else ""}


def slot_text(slot: dict) -> str:
    if "error" in slot:
        return slot["error"]
    text = f"inserted={slot['inserted']} state={slot['state']} health={slot['health']}"
    if slot["image"]:
        text += f" image={slot['image']}"
    if slot["message"]:
        text += f" message={slot['message']!r}"
    return text


def hint_for(message: str) -> str:
    lowered = message.lower()
    return next((hint for key, hint in MESSAGE_HINTS if key in lowered), "")


def parse_time(value: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def server_certificate(url: str) -> dict:
    """Certificate the web server presents, read from this host (no verification)."""
    parts = urlsplit(url)
    if parts.scheme != "https":
        return {"note": "not https"}
    host, port = parts.hostname, parts.port or 443
    try:
        pem = ssl.get_server_certificate((host, port), timeout=10)
    except OSError as error:
        return {"error": f"cannot fetch the certificate from {host}:{port}: {error}"}
    try:
        from cryptography import x509
    except ImportError:
        return {"note": "cryptography is not installed; certificate not parsed"}
    certificate = x509.load_pem_x509_certificate(pem.encode())
    try:
        names = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        san = [str(item.value) for item in names]
    except x509.ExtensionNotFound:
        san = []
    return {"subject": certificate.subject.rfc4514_string(), "issuer": certificate.issuer.rfc4514_string(),
            "not_before": certificate.not_valid_before_utc, "not_after": certificate.not_valid_after_utc, "san": san,
            "self_signed": certificate.subject == certificate.issuer, "host": host}


def head_request(url: str) -> str:
    try:
        response = requests.head(url, verify=False, timeout=15, allow_redirects=False)
    except requests.RequestException as error:
        return f"HEAD failed: {type(error).__name__}"
    size = response.headers.get("Content-Length", "?")
    return f"HEAD {response.status_code} size={size} ranges={response.headers.get('Accept-Ranges', 'none')}"


def cimc_facts(fi: Fi, blade: str, out: Output, findings: list[str]) -> datetime.datetime | None:
    code, manager = fi.get(blade, "/Managers/CIMC")
    clock = None
    if code == 200 and isinstance(manager, dict):
        clock = parse_time(manager.get("DateTime", ""))
        status = manager.get("Status") or {}
        out.line(f"  CIMC: model={manager.get('Model')} firmware={manager.get('FirmwareVersion')} "
                 f"health={status.get('Health')} clock={manager.get('DateTime')}")
        if clock:
            skew = abs(datetime.datetime.now(clock.tzinfo) - clock)
            out.line(f"  CIMC clock differs from this host by {skew}")
            if skew > CLOCK_SKEW_LIMIT:
                findings.append(f"{blade}: CIMC clock is off by {skew}; HTTPS downloads can fail certificate "
                                "validity checks (set NTP on the CIMC)")
    else:
        out.line(f"  CIMC: GET /Managers/CIMC -> {code} {manager}")
    code, interfaces = fi.get(blade, "/Managers/CIMC/EthernetInterfaces")
    for member in (interfaces.get("Members", []) if isinstance(interfaces, dict) else []):
        code, interface = fi.get(blade, member["@odata.id"].replace("/redfish/v1", ""))
        if code != 200 or not isinstance(interface, dict) or not interface.get("InterfaceEnabled"):
            continue
        addresses = [item.get("Address") for item in interface.get("IPv4Addresses", []) if item.get("Address")]
        gateway = next((item.get("Gateway") for item in interface.get("IPv4Addresses", []) if item.get("Gateway")), None)
        vlan = (interface.get("VLAN") or {}).get("VLANId")
        out.line(f"  CIMC {interface.get('Name', '').split()[-1]}: ip={addresses} gateway={gateway} vlan={vlan} "
                 f"dns={interface.get('NameServers')}")
        if not addresses:
            findings.append(f"{blade}: enabled CIMC interface has no IPv4 address")
    code, protocol = fi.get(blade, "/Managers/CIMC/NetworkProtocol")
    if code == 200 and isinstance(protocol, dict):
        out.line(f"  CIMC virtual media service enabled: {(protocol.get('VirtualMedia') or {}).get('ProtocolEnabled')}")
    return clock


def read_slots(fi: Fi, blade: str, ids: list[int] | None = None) -> list[dict]:
    code, collection = fi.get(blade, "/Managers/CIMC/VirtualMedia")
    members = [int(item["@odata.id"].rsplit("/", 1)[1]) for item in collection.get("Members", [])] \
        if code == 200 and isinstance(collection, dict) else ids or []
    return [slot_summary(fi.get(blade, f"/Managers/CIMC/VirtualMedia/{number}")[1]) for number in members
            if ids is None or number in ids]


def command_inspect(clients: list[tuple[Fi, list[str]]], args: argparse.Namespace, out: Output) -> int:
    findings: list[str] = []
    certificate = server_certificate(args.url_base) if args.url_base else {}
    if certificate:
        out.line("Web server certificate (read from this host):")
        if "error" in certificate or "note" in certificate:
            out.line(f"  {certificate.get('error') or certificate.get('note')}")
        else:
            out.line(f"  subject={certificate['subject']} issuer={certificate['issuer']}")
            out.line(f"  valid {certificate['not_before']:%Y-%m-%d %H:%M} to {certificate['not_after']:%Y-%m-%d %H:%M} UTC "
                     f"self_signed={certificate['self_signed']} san={certificate['san']}")
            if certificate["host"] not in certificate["san"]:
                out.line(f"  note: {certificate['host']} is not in the certificate's subject alternative names")
        out.line()
    for fi, blades in clients:
        for blade in blades:
            out.line(f"== {blade} (via FI {fi.ip})")
            clock = cimc_facts(fi, blade, out, findings)
            if clock and "not_before" in certificate:
                if clock.astimezone(datetime.timezone.utc) < certificate["not_before"]:
                    findings.append(f"{blade}: CIMC clock is before the web server certificate's start date")
                if clock.astimezone(datetime.timezone.utc) > certificate["not_after"]:
                    findings.append(f"{blade}: CIMC clock is after the web server certificate's end date")
            for slot in read_slots(fi, blade):
                out.line(f"  slot {slot.get('id', '?')}: {slot_text(slot)}")
                if "error" not in slot and slot["id"] == str(args.slot) and (slot["health"] != "OK"
                                                                             or slot["state"] == "UnavailableOffline"):
                    findings.append(f"{blade}: slot {args.slot} is {slot['state']}/{slot['health']} "
                                    f"({slot['message'] or 'no message'})")
            code, log = fi.get(blade, "/Managers/CIMC/LogServices/CIMC/Entries")
            entries = log.get("Members", []) if code == 200 and isinstance(log, dict) else []
            out.line(f"  CIMC log: {len(entries)} entries")
            for entry in entries[-10:]:
                out.line(f"    {entry.get('Created', '')} {entry.get('Severity', '')} {entry.get('Message', '')}")
            out.line()
    if args.url:
        out.line(f"Image URL from this host: {args.url} -> {head_request(args.url)}\n")
    out.line("Findings:" if findings else "Findings: none from the checks above")
    for finding in findings:
        out.line(f"  - {finding}")
    return 1 if findings else 0


def web_requests(access_log: Path, name: str, since: datetime.datetime) -> list[str] | None:
    try:
        lines = access_log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    found = []
    for line in lines:
        if f"/{name} " not in line and f"/{name}?" not in line:
            continue
        try:
            stamp = datetime.datetime.strptime(line.split("[", 1)[1].split("]", 1)[0], "%d/%b/%Y:%H:%M:%S %z")
        except (IndexError, ValueError):
            continue
        if stamp >= since:
            found.append(line)
    return found


def summarize_requests(lines: list[str]) -> str:
    counts: dict[tuple[str, str, str], int] = {}
    for line in lines:
        parts = line.split('"')
        key = (line.split(" ", 1)[0], parts[1].split(" ", 1)[0] if len(parts) > 1 else "?",
               parts[2].split()[0] if len(parts) > 2 and parts[2].split() else "?")
        counts[key] = counts.get(key, 0) + 1
    return ", ".join(f"{client} {method} {status} x{count}" for (client, method, status), count in sorted(counts.items()))


def task_text(fi: Fi, blade: str, response_text: str) -> str:
    """What the Redfish task started by InsertMedia says (state, status and messages), or an explanation."""
    try:
        location = json.loads(response_text).get("@odata.id", "")
    except ValueError:
        return "the insert response was not JSON"
    if "/Tasks/" not in location:
        return "the insert response named no task"
    code, task = fi.get(blade, location.replace("/redfish/v1", ""))
    if code != 200 or not isinstance(task, dict):
        return f"task {location} -> HTTP {code}"
    parts = [f"{key}={task[key]}" for key in ("TaskState", "TaskStatus") if key in task]
    for message in task.get("Messages", []) or []:
        parts.append(f"message={message.get('Message') or message.get('MessageId')!r}")
    if task.get("Oem"):
        parts.append(f"oem={json.dumps(task['Oem'])[:300]}")
    return f"task {location.rsplit('/', 1)[-1]}: " + (" ".join(parts) or json.dumps(task)[:300])


def cimc_addresses(fi: Fi, blade: str) -> list[str]:
    code, interfaces = fi.get(blade, "/Managers/CIMC/EthernetInterfaces")
    found = []
    for member in (interfaces.get("Members", []) if code == 200 and isinstance(interfaces, dict) else []):
        code, interface = fi.get(blade, member["@odata.id"].replace("/redfish/v1", ""))
        if code == 200 and isinstance(interface, dict) and interface.get("InterfaceEnabled"):
            found += [item["Address"] for item in interface.get("IPv4Addresses", []) if item.get("Address")]
    return found


def start_capture(addresses: list[str], port: int):
    """tcpdump of TCP traffic on the web server port; needs root.

    With CIMC addresses it records everything those hosts send; without them it records only connection setup
    and teardown (SYN/RST) from every client, so the sources show which CIMCs reach this host at all."""
    if not shutil.which("tcpdump"):
        return None, "tcpdump is not installed (dnf install tcpdump); capture skipped"
    if addresses:
        expression = f"tcp port {port} and (" + " or ".join(f"host {address}" for address in addresses) + ")"
        note = ""
    else:
        expression = f"tcp port {port} and tcp[tcpflags] & (tcp-syn|tcp-rst) != 0"
        note = "no CIMC address known (use --cimc-ip); recording connection setup from every client"
    process = subprocess.Popen(["tcpdump", "-nn", "-tt", "-l", "-i", "any", expression],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1)
    if process.poll() is not None:
        return None, f"tcpdump could not start (run as root): {process.stderr.read().strip()[:120]}"
    return process, note


def summarize_capture(text: str, port: int) -> list[str]:
    """What the packets between the CIMC and the web server say about where the connection fails."""
    packets = [line for line in text.splitlines() if "Flags [" in line]
    flags = [line.split("Flags [", 1)[1].split("]", 1)[0] for line in packets]
    syn = sum(1 for item in flags if item == "S")
    syn_ack = sum(1 for item in flags if item == "S.")
    reset = sum(1 for item in flags if "R" in item)
    data = sum(1 for line in packets if "length" in line and not line.rstrip().endswith("length 0"))
    verdict = f"{len(packets)} packets: SYN={syn} SYN-ACK={syn_ack} RST={reset} with-data={data}"
    if not packets:
        meaning = f"No packet from the CIMC reached this host on port {port}: the path (route, VLAN, firewall) is the problem."
    elif syn and not syn_ack:
        meaning = "The CIMC's SYN arrived but this host never answered: a host firewall or listener is dropping it."
    elif syn_ack and not data and not reset:
        meaning = "TCP connected but the CIMC sent no TLS data and closed: it gave up right after connecting."
    elif reset and not data:
        meaning = "The connection was reset before any data: refused by the listener or a firewall."
    elif reset:
        meaning = "Connected and exchanged data, then reset: look at the TLS handshake (protocol or cipher mismatch) and the Nginx error log."
    else:
        meaning = "The CIMC connected and exchanged data; see the web server requests below."
    return [verdict, f"meaning: {meaning}", *("   " + line for line in packets[:30])]


def mount_one(fi: Fi, blade: str, args: argparse.Namespace, out: Output) -> bool:
    slot_uri = f"/Managers/CIMC/VirtualMedia/{args.slot}"
    created = None
    name = args.image or (urlsplit(args.url).path.rsplit("/", 1)[-1] if args.url else "")
    if not args.url:
        if not args.url_base:
            raise FiError("mount needs --url, or --image/--size-mb with --url-base and --upload-dir")
        if args.image:
            if not (args.upload_dir / args.image).is_file():
                raise FiError(f"{args.upload_dir / args.image} does not exist")
        else:
            name = f"vmedia-diag-{uuid.uuid4().hex[:8]}.iso"
            created = args.upload_dir / name
            created.write_bytes(b"\0" * (args.size_mb * 1024 * 1024))
            created.chmod(0o644)
        url = f"{args.url_base.rstrip('/')}/{name}"
    else:
        url = args.url
    out.line(f"== {blade}: mounting {url}")
    out.line(f"   from this host: {head_request(url)}")
    started = datetime.datetime.now().astimezone().replace(microsecond=0)
    capture = None
    port = urlsplit(url).port or (443 if url.startswith("https") else 80)
    try:
        fi.post(blade, f"{slot_uri}/Actions/VirtualMedia.EjectMedia", {})
        time.sleep(2)
        if args.capture:
            addresses = args.cimc_ip or cimc_addresses(fi, blade)
            capture, note = start_capture(addresses, port)
            if note:
                out.line(f"   capture: {note}")
        out.line(f"   [{time.strftime('%H:%M:%S')}] before: {slot_text(slot_summary(fi.get(blade, slot_uri)[1]))}")
        body = {"Image": url, "WriteProtected": True, "TransferProtocolType": urlsplit(url).scheme.upper(),
                "TransferMethod": "Stream", "Inserted": True}
        code, text = fi.post(blade, f"{slot_uri}/Actions/VirtualMedia.InsertMedia", body)
        out.line(f"   [{time.strftime('%H:%M:%S')}] InsertMedia -> HTTP {code}")
        out.line(f"   [{time.strftime('%H:%M:%S')}] request body sent: {json.dumps(body)}")
        last, deadline, ok = None, time.time() + args.timeout, False
        while time.time() < deadline:
            slot = slot_summary(fi.get(blade, slot_uri)[1])
            current = slot_text(slot)
            if current != last:
                out.line(f"   [{time.strftime('%H:%M:%S')}] {current}")
                last = current
            if "error" not in slot and slot["health"] != "OK":
                break
            if "error" not in slot and slot["inserted"] and slot["health"] == "OK" and slot["state"] == "Enabled":
                ok = True
                break
            time.sleep(args.interval)
        out.line(f"   [{time.strftime('%H:%M:%S')}] {task_text(fi, blade, text)}")
        if not ok and "error" not in slot:
            if slot["message"]:
                out.line(f"   meaning: {hint_for(slot['message']) or 'no built-in explanation for this message'}")
            elif slot["health"] == "OK":
                out.line(f"   meaning: no result after {args.timeout}s (state {slot['state']}). A CIMC that cannot "
                         "reach the web server at all (traffic dropped) stays in Updating; check routing, VLAN and "
                         "firewalls between the CIMC in-band address and the web server.")
        time.sleep(2)
        if capture:
            capture.terminate()
            try:
                packets = capture.communicate(timeout=10)[0]
            except subprocess.TimeoutExpired:
                capture.kill()
                packets = capture.communicate()[0]
            capture = None
            out.line("   packet capture (CIMC <-> web server):")
            for line in summarize_capture(packets or "", port):
                out.line("   " + line)
        requests_seen = web_requests(args.access_log, name, started) if name else None
        if requests_seen is None:
            out.line(f"   web server: access log {args.access_log} not readable here")
        elif requests_seen:
            out.line(f"   web server saw: {summarize_requests(requests_seen)}")
        else:
            out.line("   web server saw: NO request for this file from any client (the CIMC did not connect, "
                     "or the request failed before HTTP: route, VLAN, firewall or TLS)")
        return ok
    finally:
        if capture:
            capture.kill()
        fi.post(blade, f"{slot_uri}/Actions/VirtualMedia.EjectMedia", {})
        out.line(f"   ejected; slot after: {slot_text(slot_summary(fi.get(blade, slot_uri)[1]))}\n")
        if created:
            created.unlink(missing_ok=True)


def command_mount(clients: list[tuple[Fi, list[str]]], args: argparse.Namespace, out: Output) -> int:
    failures = 0
    for fi, blades in clients:
        for blade in blades:
            failures += not mount_one(fi, blade, args, out)
    return 1 if failures else 0


def vault_password(vault_file: Path, password_file: Path, key: str) -> str:
    result = subprocess.run(["ansible-vault", "view", str(vault_file), "--vault-password-file", str(password_file)],
                            capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise FiError(f"cannot read the vault {vault_file}")
    import yaml
    value = (yaml.safe_load(result.stdout) or {}).get(key)
    if not value:
        raise FiError(f"{key} is not set in {vault_file}")
    return str(value)


def build_clients(args: argparse.Namespace) -> tuple[list[tuple[Fi, list[str]]], list[str]]:
    clients: list[tuple[Fi, list[str]]] = []
    secrets: list[str] = []
    if args.fi:
        password = os.environ.get(args.password_env, "")
        if args.vault_file:
            password = vault_password(args.vault_file, args.vault_password_file, args.vault_key)
        if not password:
            raise FiError(f"set {args.password_env} or pass --vault-file")
        secrets.append(password)
        fi = Fi(args.fi, args.username, password)
        clients.append((fi, args.blade))
        return clients, secrets
    path = args.dir / "server.json"
    if not path.is_file():
        raise FiError(f"{path} not found; pass --fi/--blade or run Prepare install first")
    by_fi: dict[tuple[str, str, str], list[str]] = {}
    for server in json.loads(path.read_text(encoding="utf-8")):
        redfish = server.get("redfish") or {}
        if redfish.get("endpoint_type") != "fi":
            continue
        if args.blade and args.blade != ["all"] and redfish.get("inventory_id") not in args.blade \
                and server.get("hostname") not in args.blade:
            continue
        key = (redfish["endpoint_ip"], redfish.get("username", ""), redfish.get("password", ""))
        by_fi.setdefault(key, []).append(redfish.get("inventory_id", ""))
        secrets.append(key[2])
    if not by_fi:
        raise FiError("no Fabric Interconnect attached servers selected")
    return [(Fi(ip, user, password), blades) for (ip, user, password), blades in by_fi.items()], secrets


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("inspect", "mount"))
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="directory with server.json and web.json")
    parser.add_argument("--fi", help="FI management IP (instead of server.json)")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password-env", default="FI_PASSWORD")
    parser.add_argument("--vault-file", type=Path)
    parser.add_argument("--vault-password-file", type=Path, default=Path.home() / ".config/cisco-ai-pods/vault-password")
    parser.add_argument("--vault-key", default="fabric_interconnect_password_1")
    parser.add_argument("--blade", action="append", default=[], help="blade inventory id such as r142c-2-1; repeatable")
    parser.add_argument("--slot", type=int, default=3, help="virtual media id (CIMC-Mapped vDVD is 3)")
    parser.add_argument("--url", help="image URL to mount (or to HEAD from this host with inspect)")
    parser.add_argument("--image", help="mount: existing file in the upload directory (for example the real ISO)")
    parser.add_argument("--size-mb", type=int, default=1, help="mount: size of the generated test image")
    parser.add_argument("--url-base", default="", help="web server base URL (default: image_base_url in web.json)")
    parser.add_argument("--upload-dir", type=Path, help="web server directory (default: image_upload_directory in web.json)")
    parser.add_argument("--access-log", type=Path, default=DEFAULT_ACCESS_LOG)
    parser.add_argument("--cimc-ip", action="append", default=[],
                        help="mount --capture: CIMC in-band address to record (repeatable); default: read from the FI")
    parser.add_argument("--capture", action="store_true",
                        help="mount: record the CIMC's TCP traffic to the web server with tcpdump (run as root)")
    parser.add_argument("--timeout", type=int, default=90, help="mount: seconds to watch the slot")
    parser.add_argument("--interval", type=float, default=2.0, help="mount: seconds between slot reads")
    args = parser.parse_args(argv)
    web = args.dir / "web.json"
    if web.is_file():
        settings = json.loads(web.read_text(encoding="utf-8"))
        args.url_base = args.url_base or settings.get("image_base_url", "")
        args.upload_dir = args.upload_dir or Path(settings.get("image_upload_directory", ""))
    if args.url and not args.url_base:
        parts = urlsplit(args.url)
        args.url_base = f"{parts.scheme}://{parts.netloc}"
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        clients, secrets = build_clients(args)
        out = Output(secrets)
        status = 0
        opened = []
        for fi, blades in clients:
            fi.__enter__()
            opened.append(fi)
            if not blades or blades == ["all"]:
                blades[:] = fi.blades()
        try:
            status = {"inspect": command_inspect, "mount": command_mount}[args.command](clients, args, out)
        finally:
            for fi in opened:
                fi.__exit__()
        return status
    except FiError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
