"""
DNS Updater - Synchronize DNS records across multiple providers
Supports: Active Directory, Infoblox, BlueCat, Efficient IP, BindDNS

Usage:
    python dns_updater.py --config inventory.yaml --provider ad --dry-run
    python dns_updater.py --config inventory.yaml --provider infoblox --apply
"""

import argparse
import json
import logging
import os
import re
import socket
import ssl
import struct
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import yaml
from hvac import Client as VaultClient


@dataclass
class DNSRecord:
    """Represents a DNS A/AAAA record"""
    hostname: str
    ip_address: str
    zone: str
    record_type: str = "A"
    ttl: int = 3600
    description: str = ""

    def __hash__(self):
        return hash((self.hostname, self.ip_address, self.zone))

    def __eq__(self, other):
        if not isinstance(other, DNSRecord):
            return False
        return (self.hostname == other.hostname and
                self.ip_address == other.ip_address and
                self.zone == other.zone)


@dataclass
class PtrRecord:
    """A pointer record: the reverse name of ``ip_address`` -> ``target`` (a host name), in a reverse zone"""
    ip_address: str
    target: str
    zone: str
    label: str
    ttl: int = 3600

    def __hash__(self):
        return hash((self.ip_address, self.target.lower().rstrip('.'), self.zone))

    def __eq__(self, other):
        return (isinstance(other, PtrRecord) and self.ip_address == other.ip_address
                and self.target.lower().rstrip('.') == other.target.lower().rstrip('.') and self.zone == other.zone)


@dataclass
class ZonePlan:
    """A DNS zone that does not exist yet. ``network_id`` (10.1.2.0/24) is set for reverse zones."""
    name: str
    reverse: bool = False
    network_id: str = ""


@dataclass
class PtrPlan:
    missing: List[PtrRecord] = field(default_factory=list)     # to create (no PTR on that name yet)
    changed: Dict[PtrRecord, List[str]] = field(default_factory=dict)  # to replace -> current targets
    matching: List[PtrRecord] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def to_write(self) -> List[PtrRecord]:
        return self.missing + list(self.changed)


def reverse_name(ip_address: str) -> str:
    """61.1.124.10.in-addr.arpa for 10.124.1.61"""
    return '.'.join(reversed(ip_address.split('.'))) + '.in-addr.arpa'


def dns_wire_name(fqdn: str) -> Tuple[bytes, int]:
    """Labels as length-prefixed strings ending with the root label, and how many labels there are"""
    labels = [label for label in fqdn.rstrip('.').split('.') if label]
    if not labels or len(fqdn.rstrip('.')) > 253 or any(len(label.encode('utf-8')) > 63 for label in labels):
        raise ValueError(f"'{fqdn}' is not a valid DNS name")
    raw = b''.join(bytes([len(label.encode('utf-8'))]) + label.encode('utf-8') for label in labels) + b'\x00'
    return raw, len(labels)


class DNSProvider(ABC):
    """Abstract base class for DNS providers"""

    # Providers only report on the desired records until their create/update/delete calls are really implemented
    supports_write = False
    # Providers that only replace a name's addresses on update leave differing records alone on apply
    deletes_stale = True
    writable = False
    # True when written records only show up in DNS after the server loads them (AD over LDAP)
    needs_settle = False
    # Providers that can also manage zones and pointer (PTR) records
    supports_ptr = False

    def plan_zones(self, records: Set[DNSRecord], ptr_plan: Optional['PtrPlan'] = None) -> List[ZonePlan]:
        return []

    def plan_ptr(self, records: Set[DNSRecord]) -> 'PtrPlan':
        return PtrPlan()

    def create_zones(self, plans: List[ZonePlan]) -> Tuple[List[ZonePlan], List[Tuple[ZonePlan, str]]]:
        return [], [(plan, "this provider cannot create zones") for plan in plans]

    def create_ptr(self, ptr: PtrRecord) -> bool:
        return False

    def ptr_resolves(self, ptr: PtrRecord) -> bool:
        return False

    def __init__(self, config: Dict, vault_client: Optional[VaultClient] = None):
        self.config = config
        self.vault_client = vault_client
        self.logger = logging.getLogger(self.__class__.__name__)
        self.expected: Set[DNSRecord] = set()

    def normalize(self, records: Set[DNSRecord]) -> Set[DNSRecord]:
        """Let a provider adjust the desired records (for example assign its real zones) after authenticating"""
        return records

    @abstractmethod
    def authenticate(self):
        """Authenticate with the DNS provider"""

    @abstractmethod
    def get_records(self, zone: str) -> Set[DNSRecord]:
        """Retrieve all DNS records from a zone"""

    @abstractmethod
    def create_record(self, record: DNSRecord) -> bool:
        """Create a new DNS record"""

    @abstractmethod
    def update_record(self, record: DNSRecord) -> bool:
        """Update an existing DNS record"""

    @abstractmethod
    def delete_record(self, record: DNSRecord) -> bool:
        """Delete a DNS record"""

    def get_credentials(self, secret_path: str) -> Dict:
        """Retrieve credentials from Vault"""
        if not self.vault_client:
            raise RuntimeError("Vault client not initialized")

        try:
            secret = self.vault_client.secrets.kv.read_secret_version(path=secret_path)
            return secret['data']['data']
        except Exception as e:
            self.logger.error(f"Failed to retrieve secret from Vault: {e}")
            raise


class ActiveDirectoryProvider(DNSProvider):
    """Active Directory DNS provider (AD-integrated zones, written over LDAP)"""

    supports_write = True
    deletes_stale = False

    @property
    def needs_settle(self) -> bool:
        return self.backend == 'ldap'

    def __init__(self, config: Dict, vault_client: Optional[VaultClient] = None):
        super().__init__(config, vault_client)
        self.server = None
        self.username = None
        self.password = None
        self.backend = None
        self.connection = None
        self.session = None
        self.zones: Dict[str, str] = {}
        self.reverse_zones: Dict[str, str] = {}
        self.serials: Dict[str, int] = {}

    supports_ptr = True

    def authenticate(self):
        """Authenticate with Active Directory"""
        try:
            if self.vault_client and 'vault_path' in self.config:
                creds = self.get_credentials(self.config['vault_path'])
                self.username = creds.get('username')
                self.password = creds.get('password')
            else:
                # Secrets come from the web UI vault as environment variables; with shared LDAP settings the
                # Shared Services LDAP bind password is reused.
                self.username = (os.environ.get('ad_username') or self.config.get('username')
                                 or self.config.get('bind_dn'))
                self.password = os.environ.get('ad_password') or self.config.get('password')
                if not self.password and self.config.get('use_shared_ldap'):
                    self.password = os.environ.get('ldap_bind_password')

            self.server = self.config.get('server')
            if not self.server:
                raise ValueError("AD server not configured")

            self.logger.info(f"AD server: {self.server} (credentials {'found' if self.password else 'not set'})")
            self._load_zones()
        except Exception as e:
            self.logger.error(f"AD authentication failed: {e}")
            raise

    # ---- LDAP access (AD-integrated DNS zones are stored as dnsZone/dnsNode objects) ----

    def _connect(self):
        from ldap3 import DSA, Connection, Server, Tls
        from ldap3.core.exceptions import LDAPException

        timeout = int(self.config.get('timeout', 10))
        port = int(self.config.get('ldap_port', 389))
        secure_port = int(self.config.get('secure_ldap_port', 636))
        use_ssl = bool(self.config.get('use_ssl'))
        # Domain controllers that require LDAP signing refuse simple binds on cleartext LDAP, so fall back to TLS.
        attempts = [(use_ssl, secure_port if use_ssl else port, False)]
        if not use_ssl:
            attempts += [(True, secure_port, False), (False, port, True)]
        errors = []
        for ssl_on, attempt_port, starttls in attempts:
            try:
                tls = Tls(validate=ssl.CERT_NONE) if ssl_on or starttls else None
                server = Server(self.server, port=attempt_port, use_ssl=ssl_on, tls=tls, get_info=DSA,
                                connect_timeout=timeout)
                connection = Connection(server, user=self.username, password=self.password,
                                        receive_timeout=timeout, raise_exceptions=False)
                connection.open()
                if starttls:
                    connection.start_tls()
                if not connection.bind():
                    errors.append(f"port {attempt_port}: {connection.result.get('description')}")
                    continue
                if (ssl_on or starttls) and not use_ssl:
                    self.logger.warning("Connected with TLS; the domain controller certificate is not verified")
                return connection
            except LDAPException as e:
                errors.append(f"port {attempt_port}: {e}")
        hint = ""
        if any('strongerAuthRequired' in error for error in errors):
            hint = (" The domain controller requires LDAP signing or TLS, so a plain bind on port 389 is refused. "
                    "Install a certificate on the domain controller so LDAPS (port 636) works, or relax the "
                    "'Domain controller: LDAP server signing requirements' policy.")
        raise RuntimeError(f"Cannot bind to {self.server} as {self.username}: " + "; ".join(errors) + "." + hint)

    def _load_zones(self):
        """Connect over LDAP and list the AD-integrated DNS zones (needed to write; optional to validate)"""
        self.connection = None
        self.backend = None
        self.session = None
        self.zones = {}
        self.reverse_zones = {}
        self.serials = {}
        if not (self.username and self.password):
            if self.writable:
                raise RuntimeError("Active Directory credentials are not set")
            self.logger.warning("No credentials; zones are inferred from the hostnames")
            return
        try:
            self._load_zones_ldap()
        except Exception as ldap_error:
            if not self.writable:
                self.logger.warning(f"LDAP unavailable ({ldap_error}); zones are inferred from the hostnames")
                return
            self.logger.warning(f"LDAP unavailable ({ldap_error}); trying WinRM on the domain controller")
            try:
                self._load_zones_winrm()
            except Exception as winrm_error:
                raise RuntimeError(f"LDAP failed: {ldap_error} WinRM fallback failed: {winrm_error}") from winrm_error

    def _load_zones_ldap(self):
        self.zones = {}
        self.reverse_zones = {}
        from ldap3 import SUBTREE
        from ldap3.core.exceptions import LDAPException
        connection = self._connect()
        info = connection.server.info
        default = (info.other.get('defaultNamingContext') or [''])[0]
        bases = [c for c in info.naming_contexts if c.upper().startswith(('DC=DOMAINDNSZONES', 'DC=FORESTDNSZONES'))]
        if default:
            bases.append(f"CN=MicrosoftDNS,CN=System,{default}")
        for base in bases:
            try:
                if connection.search(base, '(objectClass=dnsZone)', SUBTREE, attributes=['name']):
                    for entry in connection.entries:
                        name = str(entry.name.value).lower()
                        if name.startswith('..') or name.endswith('.ip6.arpa'):
                            continue
                        target = self.reverse_zones if name.endswith('.in-addr.arpa') else self.zones
                        target.setdefault(name, entry.entry_dn)
            except LDAPException:
                continue
        self.connection = connection
        self.backend = 'ldap'
        self.logger.info(f"AD DNS zones (LDAP): {', '.join(sorted(self.zones)) or 'none found'}; "
                         f"reverse: {', '.join(sorted(self.reverse_zones)) or 'none found'}")

    # ---- WinRM fallback: run the Windows DNS Server cmdlets on the domain controller ----

    HOSTNAME_PATTERN = re.compile(r'^[A-Za-z0-9*@_.-]+$')

    def _winrm_account(self) -> str:
        """NTLM needs user@domain or DOMAIN\\user, not a distinguished name"""
        user = self.username or ''
        if '=' not in user:
            return user
        first = user.split(',')[0]
        name = first.split('=', 1)[1] if '=' in first else first
        domain = self.config.get('domain') or '.'.join(
            part.split('=', 1)[1] for part in user.split(',') if part.strip().upper().startswith('DC='))
        return f"{name}@{domain}" if domain else name

    @staticmethod
    def _ps_quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def _run_ps(self, script: str) -> str:
        result = self.session.run_ps("$ErrorActionPreference = 'Stop'\n$ProgressPreference = 'SilentlyContinue'\n" + script)
        if result.status_code != 0:
            detail = (result.std_err or b'').decode('utf-8', 'replace').strip()
            detail = re.sub(r'<[^>]+>|#< CLIXML', ' ', detail)
            raise RuntimeError(' '.join(detail.split())[:400] or f"PowerShell exit code {result.status_code}")
        return (result.std_out or b'').decode('utf-8', 'replace').strip()

    ZONE_QUERY = ("$all = @(Get-DnsServerZone | Where-Object { $_.ZoneType -eq 'Primary' -and -not $_.IsAutoCreated })\n"
                  "@{ forward = @($all | Where-Object { -not $_.IsReverseLookupZone } | ForEach-Object { $_.ZoneName }); "
                  "reverse = @($all | Where-Object { $_.IsReverseLookupZone } | ForEach-Object { $_.ZoneName }) } "
                  "| ConvertTo-Json -Compress")

    def _open_winrm(self, probe: str) -> str:
        """Open a WinRM session on the domain controller (kept in self.session) and return the output of ``probe``"""
        try:
            import winrm
        except ImportError as e:
            raise RuntimeError("the pywinrm package is not installed") from e
        timeout = max(int(self.config.get('timeout', 10)), 10)
        account = self._winrm_account()
        errors = []
        for scheme, port in (('http', 5985), ('https', 5986)):
            try:
                session = winrm.Session(f"{scheme}://{self.server}:{port}/wsman", auth=(account, self.password),
                                        transport='ntlm', server_cert_validation='ignore',
                                        operation_timeout_sec=timeout, read_timeout_sec=timeout + 10)
                self.session = session
                output = self._run_ps(probe)
                self.logger.info(f"Connected over WinRM ({scheme}) as {account}")
                return output
            except Exception as e:
                self.session = None
                errors.append(f"{scheme} {port}: {e}")
        hint = (" Check that WinRM is enabled on the domain controller (winrm quickconfig) and that the account can "
                "manage DNS; for an account whose common name differs from its logon name, store the Active "
                "Directory username as user@domain.")
        raise RuntimeError("; ".join(errors) + hint)

    def _load_zones_winrm(self):
        names = self._open_winrm(self.ZONE_QUERY)
        data = json.loads(names) if names else []
        if isinstance(data, dict):
            forward, reverse = data.get('forward') or [], data.get('reverse') or []
        else:
            forward, reverse = data, []
        forward = [forward] if isinstance(forward, str) else forward
        reverse = [reverse] if isinstance(reverse, str) else reverse
        self.zones = {str(zone).lower(): str(zone) for zone in forward}
        self.reverse_zones = {str(zone).lower(): str(zone) for zone in reverse if str(zone).lower().endswith('.in-addr.arpa')}
        self.backend = 'winrm'
        self.logger.info(f"DNS zones (WinRM): {', '.join(sorted(self.zones)) or 'none found'}; "
                         f"reverse: {', '.join(sorted(self.reverse_zones)) or 'none found'}")

    def _winrm_upsert(self, record: DNSRecord) -> bool:
        zone = self._zone_of(record.hostname)
        if not zone:
            raise RuntimeError(f"No AD-integrated DNS zone found for {record.hostname}")
        name = record.hostname.rstrip('.')
        label = '@' if name.lower() == zone else name[:-(len(zone) + 1)]
        if not self.HOSTNAME_PATTERN.match(label):
            raise RuntimeError(f"Unsupported characters in {record.hostname}")
        ip_address = socket.inet_ntoa(socket.inet_aton(record.ip_address))
        quote = self._ps_quote
        add = ("Add-DnsServerResourceRecordA -ZoneName $zone -Name $name -IPv4Address $ip -TimeToLive $ttl "
               "| Out-Null")
        script = (
            f"$zone = {quote(self.zones[zone])}; $name = {quote(label)}; $ip = {quote(ip_address)}\n"
            f"$ttl = New-TimeSpan -Seconds {int(record.ttl)}\n"
            "$existing = @(Get-DnsServerResourceRecord -ZoneName $zone -Name $name -RRType A "
            "-ErrorAction SilentlyContinue | Where-Object { $_.HostName -ieq $name })\n"
            "$current = ($existing | ForEach-Object { $_.RecordData.IPv4Address.IPAddressToString }) -join ','\n"
            "if ($existing.Count -eq 1 -and $current -eq $ip) { 'UNCHANGED' } "
            "elseif ($existing.Count -eq 0) {\n"
            f"  {add}\n"
            "  'CREATED'\n"
            "} elseif ($existing.Count -eq 1) {\n"
            "  $new = $existing[0].Clone()\n"
            "  $new.RecordData.IPv4Address = [System.Net.IPAddress]::Parse($ip)\n"
            "  Set-DnsServerResourceRecord -ZoneName $zone -OldInputObject $existing[0] -NewInputObject $new "
            "| Out-Null\n"
            "  'REPLACED ' + $current\n"
            "} else {\n"
            "  foreach ($old in $existing) { Remove-DnsServerResourceRecord -ZoneName $zone -InputObject $old -Force }\n"
            f"  {add}\n"
            "  'REPLACED ' + $current\n"
            "}\n")
        output = self._run_ps(script).splitlines()
        outcome = output[-1].strip() if output else ''
        if outcome == 'UNCHANGED':
            self.logger.info(f"Already present: {record.hostname} -> {record.ip_address}")
        elif outcome.startswith('REPLACED'):
            self.logger.info(f"Replaced {record.hostname}: {outcome[len('REPLACED'):].strip()} -> {record.ip_address}")
        elif outcome == 'CREATED':
            self.logger.info(f"Created AD record: {record.hostname} -> {record.ip_address}")
        else:
            raise RuntimeError(f"Unexpected response from the domain controller: {outcome or 'empty'}")
        return True

    def _zone_of(self, hostname: str) -> Optional[str]:
        name = hostname.lower().rstrip('.')
        matches = [zone for zone in self.zones if name == zone or name.endswith('.' + zone)]
        return max(matches, key=len) if matches else None

    def normalize(self, records: Set[DNSRecord]) -> Set[DNSRecord]:
        if not self.zones:
            return records
        fixed = set()
        for record in records:
            zone = self._zone_of(record.hostname)
            fixed.add(DNSRecord(record.hostname, record.ip_address, zone or record.zone, record.record_type,
                                record.ttl, record.description))
        self.expected = fixed
        return fixed

    @staticmethod
    def _a_blob(ip_address: str, ttl: int, serial: int) -> bytes:
        """DNS_RPC_RECORD for an A record: static (timestamp 0), zone rank"""
        data = socket.inet_aton(ip_address)
        return (struct.pack('<HHBBHI', len(data), 1, 5, 240, 0, serial) + struct.pack('>I', ttl)
                + struct.pack('<II', 0, 0) + data)

    @staticmethod
    def _split_blobs(blobs) -> Tuple[List[bytes], List[str]]:
        """Separate existing dnsRecord values into non-A records (kept untouched) and A record addresses"""
        others, addresses = [], []
        for blob in blobs:
            blob = bytes(blob)
            if len(blob) >= 28 and struct.unpack_from('<H', blob, 2)[0] == 1 and struct.unpack_from('<H', blob, 0)[0] == 4:
                addresses.append(socket.inet_ntoa(blob[24:28]))
            else:
                others.append(blob)
        return others, addresses

    def _soa_serial(self, zone: str) -> int:
        if zone not in self.serials:
            import dns.resolver
            try:
                resolver = dns.resolver.Resolver(configure=False)
                resolver.nameservers = [socket.gethostbyname(self.server)]
                resolver.lifetime = float(self.config.get('timeout', 10))
                self.serials[zone] = int(resolver.resolve(zone, 'SOA')[0].serial)
            except Exception:
                self.serials[zone] = 1
        return self.serials[zone]

    def get_records(self, zone: str) -> Set[DNSRecord]:
        """Resolve the expected hostnames of a zone against the AD DNS server (read-only)"""
        import dns.exception
        import dns.resolver

        wanted = [record for record in self.expected if record.zone == zone]
        if not wanted:
            return set()
        self.logger.info(f"Querying {self.server} for zone: {zone}")
        try:
            nameserver = socket.gethostbyname(self.server)
        except OSError as e:
            raise RuntimeError(f"Cannot resolve the AD DNS server '{self.server}': {e}") from e
        resolver = dns.resolver.Resolver(configure=False)
        resolver.nameservers = [nameserver]
        resolver.lifetime = float(self.config.get('timeout', 10))
        found: Set[DNSRecord] = set()
        for record in wanted:
            try:
                answer = resolver.resolve(record.hostname, 'A')
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                continue
            except dns.exception.DNSException as e:
                raise RuntimeError(f"DNS query for {record.hostname} against {self.server} failed: "
                                   f"{e.__class__.__name__}") from e
            for rdata in answer:
                found.add(DNSRecord(record.hostname, rdata.address, zone, ttl=answer.rrset.ttl))
        return found

    def create_record(self, record: DNSRecord) -> bool:
        """Create the A record, or replace the A records already on that name; other record types are kept"""
        from ldap3 import LEVEL, MODIFY_REPLACE
        from ldap3.utils.conv import escape_filter_chars
        from ldap3.utils.dn import escape_rdn

        try:
            if self.backend == 'winrm':
                return self._winrm_upsert(record)
            if not self.connection:
                raise RuntimeError("Not connected to Active Directory")
            zone = self._zone_of(record.hostname)
            if not zone:
                raise RuntimeError(f"No AD-integrated DNS zone found for {record.hostname}")
            zone_dn = self.zones[zone]
            name = record.hostname.rstrip('.')
            label = '@' if name.lower() == zone else name[:-(len(zone) + 1)]
            blob = self._a_blob(record.ip_address, record.ttl, self._soa_serial(zone))
            self.connection.search(zone_dn, f"(&(objectClass=dnsNode)(name={escape_filter_chars(label)}))", LEVEL,
                                   attributes=['dnsRecord'])
            if self.connection.entries:
                entry = self.connection.entries[0]
                others, addresses = self._split_blobs(entry.dnsRecord.raw_values if 'dnsRecord' in entry else [])
                if addresses == [record.ip_address]:
                    self.logger.info(f"Already present: {record.hostname} -> {record.ip_address}")
                    return True
                self.logger.info(f"Replacing {record.hostname}: {', '.join(addresses) or 'no A record'} "
                                 f"-> {record.ip_address}")
                changes = {'dnsRecord': [(MODIFY_REPLACE, others + [blob])],
                           'dNSTombstoned': [(MODIFY_REPLACE, ['FALSE'])]}
                ok = self.connection.modify(entry.entry_dn, changes)
            else:
                self.logger.info(f"Creating AD record: {record.hostname} -> {record.ip_address}")
                ok = self.connection.add(f"DC={escape_rdn(label)},{zone_dn}", ['top', 'dnsNode'],
                                         {'dnsRecord': [blob], 'dNSTombstoned': 'FALSE'})
            if not ok:
                raise RuntimeError(self.connection.result.get('description', 'LDAP error')
                                   + f": {self.connection.result.get('message', '')}".rstrip(': '))
            return True
        except Exception as e:
            self.logger.error(f"Failed to write {record.hostname}: {e}")
            return False

    # ---- zones and pointer (PTR) records ----

    REPLICATION_SCOPES = ('Domain', 'Forest', 'Legacy')

    def _option(self, name: str, default):
        value = self.config.get(name, default)
        return default if value is None else value

    def _forward_zone_candidate(self, hostname: str) -> str:
        """The zone to create for a host name that no existing zone covers: the AD domain when the name is in it,
        otherwise the name without its first label (a wildcard counts as a label)."""
        name = hostname.lower().rstrip('.')
        domain = str(self.config.get('domain') or '').lower().strip('.')
        if domain and (name == domain or name.endswith('.' + domain)):
            return domain
        parts = name.split('.')
        return '.'.join(parts[1:]) if len(parts) > 2 else name

    def plan_zones(self, records: Set[DNSRecord], ptr_plan: Optional[PtrPlan] = None) -> List[ZonePlan]:
        """Forward and reverse zones that are missing. Empty when zones are not known (no credentials) or creating
        them is switched off (create_zones: false)."""
        if self.backend is None or not self._option('create_zones', True):
            return []
        candidates = {self._forward_zone_candidate(record.hostname) for record in records
                      if not self._zone_of(record.hostname)}
        # a zone that covers another candidate makes the narrower one unnecessary
        wanted = sorted(zone for zone in candidates if zone.count('.') >= 1 and not any(
            other != zone and zone.endswith('.' + other) for other in candidates))
        plans = [ZonePlan(zone) for zone in wanted]
        seen = set()
        for ptr in (ptr_plan.to_write if ptr_plan else []):
            if ptr.zone not in self.reverse_zones and ptr.zone not in seen:
                seen.add(ptr.zone)
                plans.append(ZonePlan(ptr.zone, True, self._network_id(ptr.ip_address)))
        return plans

    def _reverse_prefix(self) -> int:
        prefix = int(self._option('reverse_zone_prefix', 24))
        if prefix not in (8, 16, 24):
            raise ValueError("reverse_zone_prefix must be 8, 16 or 24")
        return prefix

    def _network_id(self, ip_address: str) -> str:
        prefix = self._reverse_prefix()
        octets = ip_address.split('.')[:prefix // 8]
        return '.'.join(octets + ['0'] * (4 - len(octets))) + f"/{prefix}"

    def _reverse_zone_for(self, ip_address: str) -> str:
        """The existing reverse zone that covers the address (the most specific one), else the zone to create"""
        name = reverse_name(ip_address)
        matches = [zone for zone in self.reverse_zones if name.endswith('.' + zone)]
        if matches:
            return max(matches, key=len)
        octets = ip_address.split('.')[:self._reverse_prefix() // 8]
        return '.'.join(reversed(octets)) + '.in-addr.arpa'

    def _ptr_targets(self, records: Set[DNSRecord]) -> Dict[str, str]:
        """One name per address: the shortest host name (then alphabetical). Wildcards and bad addresses are skipped."""
        chosen: Dict[str, str] = {}
        for record in sorted(records, key=lambda r: (len(r.hostname), r.hostname.lower())):
            host = record.hostname.rstrip('.')
            try:
                address = socket.inet_ntoa(socket.inet_aton(record.ip_address))
            except OSError:
                continue
            if '*' in host or address != record.ip_address:
                continue
            chosen.setdefault(address, host)
        return chosen

    def existing_ptr_targets(self, ip_address: str) -> List[str]:
        """What the DNS server answers for the address (read-only); empty when there is no reverse zone or name"""
        import dns.exception
        import dns.resolver

        try:
            nameserver = socket.gethostbyname(self.server)
        except OSError as e:
            raise RuntimeError(f"Cannot resolve the AD DNS server '{self.server}': {e}") from e
        resolver = dns.resolver.Resolver(configure=False)
        resolver.nameservers = [nameserver]
        resolver.lifetime = float(self.config.get('timeout', 10))
        try:
            answer = resolver.resolve(reverse_name(ip_address), 'PTR')
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            return []  # no reverse zone (a server that forwards may answer SERVFAIL)
        except dns.exception.DNSException as e:
            raise RuntimeError(f"PTR query for {ip_address} against {self.server} failed: {e.__class__.__name__}") from e
        return sorted(str(rdata.target).rstrip('.') for rdata in answer)

    def plan_ptr(self, records: Set[DNSRecord]) -> PtrPlan:
        """Compare the wanted pointer records with what the DNS server answers"""
        plan = PtrPlan()
        by_address = {}
        for record in records:
            by_address.setdefault(record.ip_address, []).append(record.hostname.rstrip('.'))
        chosen = self._ptr_targets(records)
        for address in sorted(chosen, key=lambda ip: tuple(int(part) for part in ip.split('.'))):
            others = sorted(set(by_address[address]) - {chosen[address]})
            if others:
                plan.notes.append(f"{address} is used by {len(others) + 1} names; the pointer record uses "
                                  f"{chosen[address]} (not {', '.join(others)})")
        skipped = sorted(r.hostname for r in records if '*' in r.hostname)
        if skipped:
            plan.notes.append("no pointer record for wildcard names: " + ", ".join(skipped))
        for address, host in chosen.items():
            zone = self._reverse_zone_for(address)
            name = reverse_name(address)
            ptr = PtrRecord(address, host + '.', zone, name[:-(len(zone) + 1)], 3600)
            current = self.existing_ptr_targets(address)
            if [t.lower() for t in current] == [host.lower()]:
                plan.matching.append(ptr)
            elif current:
                plan.changed[ptr] = current
            else:
                plan.missing.append(ptr)
        return plan

    def ptr_resolves(self, ptr: PtrRecord) -> bool:
        return [t.lower() for t in self.existing_ptr_targets(ptr.ip_address)] == [ptr.target.lower().rstrip('.')]

    def create_zones(self, plans: List[ZonePlan]) -> Tuple[List[ZonePlan], List[Tuple[ZonePlan, str]]]:
        """Create the zones as AD-integrated primary zones (secure dynamic updates) through the DNS Server cmdlets on
        the domain controller. Returns (created, [(plan, reason)])."""
        created: List[ZonePlan] = []
        failed: List[Tuple[ZonePlan, str]] = []
        if not plans:
            return created, failed
        scope = str(self._option('zone_replication_scope', 'Domain'))
        if scope not in self.REPLICATION_SCOPES:
            reason = f"zone_replication_scope must be one of {', '.join(self.REPLICATION_SCOPES)}"
            return created, [(plan, reason) for plan in plans]
        try:
            if self.session is None:
                self._open_winrm("'ok'")
        except RuntimeError as error:
            reason = (f"creating a zone needs WinRM on the domain controller (LDAP cannot create zones): {error} "
                      "Create the zone on the domain controller instead, for example: "
                      + "; ".join(self._manual_command(plan, scope) for plan in plans))
            return created, [(plan, reason) for plan in plans]
        quote = self._ps_quote
        for plan in plans:
            if not re.match(r'^[A-Za-z0-9_.-]+$', plan.name):
                failed.append((plan, "unsupported characters in the zone name"))
                continue
            create = (f"Add-DnsServerPrimaryZone -NetworkId {quote(plan.network_id)} " if plan.reverse
                      else f"Add-DnsServerPrimaryZone -Name {quote(plan.name)} ")
            script = (f"$zone = {quote(plan.name)}\n"
                      "if (Get-DnsServerZone -Name $zone -ErrorAction SilentlyContinue) { 'EXISTS' } else {\n"
                      f"  {create}-ReplicationScope {quote(scope)} -DynamicUpdate Secure | Out-Null\n"
                      "  'CREATED'\n}\n")
            try:
                outcome = (self._run_ps(script).splitlines() or [''])[-1].strip()
            except RuntimeError as error:
                failed.append((plan, str(error)))
                continue
            if outcome in ('CREATED', 'EXISTS'):
                self.logger.info(f"{'Created' if outcome == 'CREATED' else 'Already exists'}: "
                                 f"{'reverse ' if plan.reverse else ''}zone {plan.name}")
                created.append(plan)
            else:
                failed.append((plan, f"unexpected response from the domain controller: {outcome or 'empty'}"))
        if created and self.backend == 'ldap':
            self._load_zones_ldap()  # pick up the new zones' distinguished names
        elif created:
            for plan in created:
                (self.reverse_zones if plan.reverse else self.zones)[plan.name] = plan.name
        return created, failed

    @staticmethod
    def _manual_command(plan: ZonePlan, scope: str) -> str:
        if plan.reverse:
            return f"Add-DnsServerPrimaryZone -NetworkId '{plan.network_id}' -ReplicationScope {scope} -DynamicUpdate Secure"
        return f"Add-DnsServerPrimaryZone -Name '{plan.name}' -ReplicationScope {scope} -DynamicUpdate Secure"

    @staticmethod
    def _ptr_blob(target: str, ttl: int, serial: int) -> bytes:
        """DNS_RPC_RECORD for a PTR record: the target as DNS_COUNT_NAME (length incl. the final zero, label count,
        length-prefixed labels, zero)"""
        raw, labels = dns_wire_name(target)
        data = bytes([len(raw), labels]) + raw
        return (struct.pack('<HHBBHI', len(data), 12, 5, 240, 0, serial) + struct.pack('>I', ttl)
                + struct.pack('<II', 0, 0) + data)

    @staticmethod
    def _split_ptr_blobs(blobs) -> Tuple[List[bytes], List[str]]:
        """Separate existing dnsRecord values into non-PTR records (kept untouched) and PTR targets"""
        others, targets = [], []
        for blob in blobs:
            blob = bytes(blob)
            if len(blob) >= 26 and struct.unpack_from('<H', blob, 2)[0] == 12:
                data, labels, position, names = blob[24:], blob[25], 2, []
                for label_index in range(labels):
                    size = data[position]
                    names.append(data[position + 1:position + 1 + size].decode('utf-8', 'replace'))
                    position += size + 1
                targets.append('.'.join(names))
            else:
                others.append(blob)
        return others, targets

    def create_ptr(self, ptr: PtrRecord) -> bool:
        """Create the PTR record, or replace the PTR records already on that name; other record types are kept"""
        from ldap3 import LEVEL, MODIFY_REPLACE
        from ldap3.utils.conv import escape_filter_chars
        from ldap3.utils.dn import escape_rdn

        try:
            if self.backend == 'winrm':
                return self._winrm_upsert_ptr(ptr)
            if not self.connection:
                raise RuntimeError("Not connected to Active Directory")
            zone_dn = self.reverse_zones.get(ptr.zone)
            if not zone_dn:
                raise RuntimeError(f"The reverse zone {ptr.zone} does not exist")
            blob = self._ptr_blob(ptr.target, ptr.ttl, self._soa_serial(ptr.zone))
            self.connection.search(zone_dn, f"(&(objectClass=dnsNode)(name={escape_filter_chars(ptr.label)}))", LEVEL,
                                   attributes=['dnsRecord'])
            wanted = ptr.target.rstrip('.').lower()
            if self.connection.entries:
                entry = self.connection.entries[0]
                others, targets = self._split_ptr_blobs(entry.dnsRecord.raw_values if 'dnsRecord' in entry else [])
                if [t.lower() for t in targets] == [wanted]:
                    self.logger.info(f"Already present: {ptr.ip_address} -> {ptr.target}")
                    return True
                self.logger.info(f"Replacing PTR {ptr.ip_address}: {', '.join(targets) or 'no PTR record'} "
                                 f"-> {ptr.target}")
                changes = {'dnsRecord': [(MODIFY_REPLACE, others + [blob])],
                           'dNSTombstoned': [(MODIFY_REPLACE, ['FALSE'])]}
                ok = self.connection.modify(entry.entry_dn, changes)
            else:
                self.logger.info(f"Creating PTR record: {ptr.ip_address} -> {ptr.target}")
                ok = self.connection.add(f"DC={escape_rdn(ptr.label)},{zone_dn}", ['top', 'dnsNode'],
                                         {'dnsRecord': [blob], 'dNSTombstoned': 'FALSE'})
            if not ok:
                raise RuntimeError(self.connection.result.get('description', 'LDAP error')
                                   + f": {self.connection.result.get('message', '')}".rstrip(': '))
            return True
        except Exception as e:
            self.logger.error(f"Failed to write the PTR record for {ptr.ip_address}: {e}")
            return False

    def _winrm_upsert_ptr(self, ptr: PtrRecord) -> bool:
        if not (self.HOSTNAME_PATTERN.match(ptr.label) and self.HOSTNAME_PATTERN.match(ptr.target)):
            raise RuntimeError(f"Unsupported characters in the pointer record for {ptr.ip_address}")
        quote = self._ps_quote
        script = (
            f"$zone = {quote(ptr.zone)}; $name = {quote(ptr.label)}; $target = {quote(ptr.target)}\n"
            f"$ttl = New-TimeSpan -Seconds {int(ptr.ttl)}\n"
            "$existing = @(Get-DnsServerResourceRecord -ZoneName $zone -Name $name -RRType PTR "
            "-ErrorAction SilentlyContinue | Where-Object { $_.HostName -ieq $name })\n"
            "$current = ($existing | ForEach-Object { $_.RecordData.PtrDomainName }) -join ','\n"
            "if ($existing.Count -eq 1 -and $current -ieq $target) { 'UNCHANGED' } "
            "elseif ($existing.Count -eq 0) {\n"
            "  Add-DnsServerResourceRecordPtr -ZoneName $zone -Name $name -PtrDomainName $target -TimeToLive $ttl "
            "| Out-Null\n  'CREATED'\n"
            "} elseif ($existing.Count -eq 1) {\n"
            "  $new = $existing[0].Clone()\n  $new.RecordData.PtrDomainName = $target\n"
            "  Set-DnsServerResourceRecord -ZoneName $zone -OldInputObject $existing[0] -NewInputObject $new "
            "| Out-Null\n  'REPLACED ' + $current\n"
            "} else {\n"
            "  foreach ($old in $existing) { Remove-DnsServerResourceRecord -ZoneName $zone -InputObject $old -Force }\n"
            "  Add-DnsServerResourceRecordPtr -ZoneName $zone -Name $name -PtrDomainName $target -TimeToLive $ttl "
            "| Out-Null\n  'REPLACED ' + $current\n}\n")
        output = self._run_ps(script).splitlines()
        outcome = output[-1].strip() if output else ''
        if outcome == 'UNCHANGED':
            self.logger.info(f"Already present: {ptr.ip_address} -> {ptr.target}")
        elif outcome.startswith('REPLACED'):
            self.logger.info(f"Replaced PTR {ptr.ip_address}: {outcome[len('REPLACED'):].strip()} -> {ptr.target}")
        elif outcome == 'CREATED':
            self.logger.info(f"Created PTR record: {ptr.ip_address} -> {ptr.target}")
        else:
            raise RuntimeError(f"Unexpected response from the domain controller: {outcome or 'empty'}")
        return True

    def update_record(self, record: DNSRecord) -> bool:
        return self.create_record(record)

    def delete_record(self, record: DNSRecord) -> bool:
        """Records are never deleted from AD; a differing address is replaced by create_record"""
        self.logger.info(f"Not deleting {record.hostname} -> {record.ip_address}")
        return False


class InfobloxProvider(DNSProvider):
    """Infoblox DNS provider"""

    def __init__(self, config: Dict, vault_client: Optional[VaultClient] = None):
        super().__init__(config, vault_client)
        self.session = None

    def authenticate(self):
        """Authenticate with Infoblox"""
        try:
            if self.vault_client and 'vault_path' in self.config:
                creds = self.get_credentials(self.config['vault_path'])
            else:
                creds = self.config

            # TODO: Implement Infoblox API authentication
            self.logger.info("Authenticated with Infoblox")
        except Exception as e:
            self.logger.error(f"Infoblox authentication failed: {e}")
            raise

    def get_records(self, zone: str) -> Set[DNSRecord]:
        """Retrieve DNS records from Infoblox"""
        self.logger.info(f"Retrieving records from Infoblox zone: {zone}")
        # TODO: Implement Infoblox API call
        return set()

    def create_record(self, record: DNSRecord) -> bool:
        """Create a new DNS record in Infoblox"""
        try:
            self.logger.info(f"Creating Infoblox record: {record.hostname} -> {record.ip_address}")
            # TODO: Implement Infoblox API call
            return True
        except Exception as e:
            self.logger.error(f"Failed to create record: {e}")
            return False

    def update_record(self, record: DNSRecord) -> bool:
        """Update an existing DNS record in Infoblox"""
        try:
            self.logger.info(f"Updating Infoblox record: {record.hostname} -> {record.ip_address}")
            # TODO: Implement Infoblox API call
            return True
        except Exception as e:
            self.logger.error(f"Failed to update record: {e}")
            return False

    def delete_record(self, record: DNSRecord) -> bool:
        """Delete a DNS record from Infoblox"""
        try:
            self.logger.info(f"Deleting Infoblox record: {record.hostname}")
            # TODO: Implement Infoblox API call
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete record: {e}")
            return False


class BlueCatProvider(DNSProvider):
    """BlueCat DNS provider"""

    def authenticate(self):
        """Authenticate with BlueCat"""
        # TODO: Implement BlueCat authentication
        self.logger.info("Authenticated with BlueCat")

    def get_records(self, zone: str) -> Set[DNSRecord]:
        """Retrieve DNS records from BlueCat"""
        self.logger.info(f"Retrieving records from BlueCat zone: {zone}")
        # TODO: Implement BlueCat API call
        return set()

    def create_record(self, record: DNSRecord) -> bool:
        """Create a new DNS record in BlueCat"""
        try:
            self.logger.info(f"Creating BlueCat record: {record.hostname} -> {record.ip_address}")
            # TODO: Implement BlueCat API call
            return True
        except Exception as e:
            self.logger.error(f"Failed to create record: {e}")
            return False

    def update_record(self, record: DNSRecord) -> bool:
        """Update an existing DNS record in BlueCat"""
        try:
            self.logger.info(f"Updating BlueCat record: {record.hostname} -> {record.ip_address}")
            # TODO: Implement BlueCat API call
            return True
        except Exception as e:
            self.logger.error(f"Failed to update record: {e}")
            return False

    def delete_record(self, record: DNSRecord) -> bool:
        """Delete a DNS record from BlueCat"""
        try:
            self.logger.info(f"Deleting BlueCat record: {record.hostname}")
            # TODO: Implement BlueCat API call
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete record: {e}")
            return False


class EfficientIPProvider(DNSProvider):
    """Efficient IP DNS provider"""

    def authenticate(self):
        """Authenticate with Efficient IP"""
        # TODO: Implement Efficient IP authentication
        self.logger.info("Authenticated with Efficient IP")

    def get_records(self, zone: str) -> Set[DNSRecord]:
        """Retrieve DNS records from Efficient IP"""
        self.logger.info(f"Retrieving records from Efficient IP zone: {zone}")
        # TODO: Implement Efficient IP API call
        return set()

    def create_record(self, record: DNSRecord) -> bool:
        """Create a new DNS record in Efficient IP"""
        try:
            self.logger.info(f"Creating Efficient IP record: {record.hostname} -> {record.ip_address}")
            # TODO: Implement Efficient IP API call
            return True
        except Exception as e:
            self.logger.error(f"Failed to create record: {e}")
            return False

    def update_record(self, record: DNSRecord) -> bool:
        """Update an existing DNS record in Efficient IP"""
        try:
            self.logger.info(f"Updating Efficient IP record: {record.hostname} -> {record.ip_address}")
            # TODO: Implement Efficient IP API call
            return True
        except Exception as e:
            self.logger.error(f"Failed to update record: {e}")
            return False

    def delete_record(self, record: DNSRecord) -> bool:
        """Delete a DNS record from Efficient IP"""
        try:
            self.logger.info(f"Deleting Efficient IP record: {record.hostname}")
            # TODO: Implement Efficient IP API call
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete record: {e}")
            return False


class BindDNSProvider(DNSProvider):
    """BIND DNS provider"""

    def authenticate(self):
        """Authenticate with BIND DNS"""
        # TODO: Implement BIND DNS authentication (nsupdate, etc.)
        self.logger.info("Authenticated with BIND DNS")

    def get_records(self, zone: str) -> Set[DNSRecord]:
        """Retrieve DNS records from BIND DNS"""
        self.logger.info(f"Retrieving records from BIND DNS zone: {zone}")
        # TODO: Implement BIND DNS record retrieval (dig, etc.)
        return set()

    def create_record(self, record: DNSRecord) -> bool:
        """Create a new DNS record in BIND DNS"""
        try:
            self.logger.info(f"Creating BIND record: {record.hostname} -> {record.ip_address}")
            # TODO: Implement BIND DNS record creation (nsupdate)
            return True
        except Exception as e:
            self.logger.error(f"Failed to create record: {e}")
            return False

    def update_record(self, record: DNSRecord) -> bool:
        """Update an existing DNS record in BIND DNS"""
        try:
            self.logger.info(f"Updating BIND record: {record.hostname} -> {record.ip_address}")
            # TODO: Implement BIND DNS record update (nsupdate)
            return True
        except Exception as e:
            self.logger.error(f"Failed to update record: {e}")
            return False

    def delete_record(self, record: DNSRecord) -> bool:
        """Delete a DNS record from BIND DNS"""
        try:
            self.logger.info(f"Deleting BIND record: {record.hostname}")
            # TODO: Implement BIND DNS record deletion (nsupdate)
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete record: {e}")
            return False


class DNSComparator:
    """Compare desired and actual DNS records"""

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)

    def compare(self, desired: Set[DNSRecord], actual: Set[DNSRecord]) -> Tuple[Set[DNSRecord], Set[DNSRecord], Set[DNSRecord]]:
        """
        Compare desired vs actual records.

        Returns:
            (missing_records, stale_records, matching_records)
        """
        missing = desired - actual
        stale = actual - desired
        matching = desired & actual

        self.logger.info("Comparison results:")
        self.logger.info(f"  Matching records: {len(matching)}")
        self.logger.info(f"  Missing records: {len(missing)}")
        self.logger.info(f"  Stale records: {len(stale)}")

        return missing, stale, matching


def extract_zone(hostname: str) -> str:
    """Zone guess for a hostname: everything after the first label"""
    parts = hostname.split('.')
    return '.'.join(parts[1:]) if len(parts) > 1 else 'local'


class DNSUpdater:
    """Main DNS updater orchestrator"""

    PROVIDERS = {
        'ad': ActiveDirectoryProvider,
        'infoblox': InfobloxProvider,
        'bluecat': BlueCatProvider,
        'efficientip': EfficientIPProvider,
        'bind': BindDNSProvider,
    }

    # After writing, check DNS this many times, this many seconds apart (the AD DNS service polls about every 3 minutes)
    VERIFY_CHECKS = 4
    VERIFY_INTERVAL = 60

    def __init__(self, config_file: str, dry_run: bool = True, verbose: bool = False, check: bool = False):
        self.config_file = config_file
        self.check = check
        self.dry_run = dry_run
        self.verbose = verbose
        self.logger = self._setup_logging()
        self.vault_client = None

    def _setup_logging(self) -> logging.Logger:
        """Configure logging"""
        level = logging.DEBUG if self.verbose else logging.INFO
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)

    def _load_config(self) -> Dict:
        """Load configuration from YAML file"""
        try:
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f)
            self.logger.info(f"Loaded configuration from {self.config_file}")
            return config
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            sys.exit(1)

    def _initialize_vault(self, vault_config: Dict):
        """Initialize Vault client for secrets management"""
        try:
            if vault_config and vault_config.get('enabled'):
                self.vault_client = VaultClient(
                    url=vault_config.get('url'),
                    token=vault_config.get('token')
                )
                self.logger.info("Connected to HashiCorp Vault")
        except Exception as e:
            self.logger.warning(f"Failed to initialize Vault: {e}")

    def run(self, provider_name: str):
        """Execute DNS update for specified provider"""
        config = self._load_config()

        # The web UI writes everything under a top-level "dns" key; bare files are still accepted
        config = config.get('dns', config)
        self._initialize_vault(config.get('vault', {}))

        provider_config = self._find_provider(config.get('providers') or {}, provider_name)
        if not provider_config:
            self.logger.error(f"Provider '{provider_name}' not configured")
            sys.exit(1)

        desired_records = self._desired_records(config)
        if not desired_records:
            self.logger.error("No DNS records to process; add records to the configuration")
            sys.exit(1)
        self.logger.info(f"{len(desired_records)} desired records")

        # Initialize provider
        provider_class = self.PROVIDERS.get(provider_name)
        if not provider_class:
            self.logger.error(f"Unknown provider: {provider_name}")
            sys.exit(1)

        provider = provider_class(provider_config, self.vault_client)
        provider.expected = desired_records
        provider.writable = not self.dry_run
        provider.authenticate()
        desired_records = provider.normalize(desired_records)

        # Get actual records from provider
        zones = set(r.zone for r in desired_records)
        actual_records = set()
        for zone in zones:
            actual_records.update(provider.get_records(zone))

        # Compare and report
        comparator = DNSComparator(self.logger)
        missing, stale, matching = comparator.compare(desired_records, actual_records)

        # Pointer records and the zones they (and the host names) need; --check stays an A record gate
        ptr_plan = None
        zone_plans: List[ZonePlan] = []
        if provider.supports_ptr and not self.check:
            if provider_config.get('create_ptr_records', True):
                ptr_plan = provider.plan_ptr(desired_records)
            zone_plans = provider.plan_zones(desired_records, ptr_plan)

        # Print detailed report
        self._print_report(missing, stale, matching, ptr_plan, zone_plans)

        # Apply changes if not in dry-run mode
        if not self.dry_run:
            if not provider.supports_write:
                self.logger.error(f"Writing records to '{provider_name}' is not implemented yet; "
                                  "nothing was changed")
                sys.exit(2)
            self._apply_changes(provider, missing, stale, ptr_plan, zone_plans)
        else:
            self.logger.info("DRY-RUN MODE: No changes applied")
            if self.check and missing:
                self.logger.error(f"{len(missing)} records are missing or have a different address")
                sys.exit(1)

    PROVIDER_TYPES = {
        'ad': {'ad', 'active_directory'},
        'infoblox': {'infoblox'},
        'bluecat': {'bluecat'},
        'efficientip': {'efficientip', 'efficient_ip'},
        'bind': {'bind', 'bind_dns'},
    }

    def _find_provider(self, providers: Dict, provider_name: str) -> Dict:
        """Provider entries are named freely (ad_primary); match on the name or on the entry's type"""
        types = self.PROVIDER_TYPES.get(provider_name, {provider_name})
        for key, entry in providers.items():
            if isinstance(entry, dict) and (key == provider_name or str(entry.get('type', '')).lower() in types):
                return entry
        return {}

    def _desired_records(self, config: Dict) -> Set[DNSRecord]:
        """Records listed as hostname/ipv4 pairs"""
        records = set()
        for item in config.get('records') or []:
            hostname, ip = str(item.get('hostname', '')).strip().rstrip('.'), str(item.get('ipv4', '')).strip()
            if hostname and ip:
                records.add(DNSRecord(hostname, ip, extract_zone(hostname)))
        return records

    def _print_report(self, missing: Set[DNSRecord], stale: Set[DNSRecord], matching: Set[DNSRecord],
                      ptr_plan: Optional[PtrPlan] = None, zone_plans=()):
        """Print comparison report"""
        print("\n" + "=" * 80)
        print("DNS UPDATE REPORT")
        print("=" * 80)

        if matching:
            print(f"\n✓ MATCHING ({len(matching)} records):")
            for record in sorted(matching, key=lambda r: r.hostname):
                print(f"  {record.hostname:40} -> {record.ip_address}")

        by_name = {}
        for record in stale:
            by_name.setdefault(record.hostname.lower(), []).append(record)
        new = [r for r in missing if r.hostname.lower() not in by_name]
        changed = [r for r in missing if r.hostname.lower() in by_name]
        stale_only = [r for r in stale if r.hostname.lower() not in {c.hostname.lower() for c in changed}]

        if new:
            print(f"\n+ MISSING ({len(new)} records - would be created):")
            for record in sorted(new, key=lambda r: r.hostname):
                print(f"  {record.hostname:40} -> {record.ip_address}")

        if changed:
            print(f"\n~ CHANGED ({len(changed)} records - exist with another address, would be replaced):")
            for record in sorted(changed, key=lambda r: r.hostname):
                current = ", ".join(sorted(r.ip_address for r in by_name[record.hostname.lower()]))
                print(f"  {record.hostname:40} {current} -> {record.ip_address}")

        if stale_only:
            print(f"\n- STALE ({len(stale_only)} records):")
            for record in sorted(stale_only, key=lambda r: r.hostname):
                print(f"  {record.hostname:40} -> {record.ip_address}")

        print("\n" + "=" * 80)
        print(f"Summary: {len(matching)} matching, {len(new)} missing, {len(changed)} changed, {len(stale_only)} stale")
        print("=" * 80 + "\n")
        self._print_ptr_report(ptr_plan, zone_plans)

    @staticmethod
    def _print_ptr_report(ptr_plan: Optional[PtrPlan], zone_plans) -> None:
        if zone_plans:
            print(f"+ ZONES TO CREATE ({len(zone_plans)} - AD-integrated primary zones, secure dynamic updates):")
            for plan in zone_plans:
                detail = f" (network {plan.network_id})" if plan.reverse else ""
                print(f"  {'reverse' if plan.reverse else 'forward':8} {plan.name}{detail}")
            print()
        if ptr_plan is None:
            return
        print("=" * 80)
        print("POINTER (PTR) RECORDS")
        print("=" * 80)
        if ptr_plan.matching:
            print(f"\n✓ MATCHING ({len(ptr_plan.matching)} records):")
            for ptr in sorted(ptr_plan.matching, key=lambda p: p.ip_address):
                print(f"  {ptr.ip_address:16} -> {ptr.target}")
        if ptr_plan.missing:
            print(f"\n+ MISSING ({len(ptr_plan.missing)} records - would be created):")
            for ptr in sorted(ptr_plan.missing, key=lambda p: p.ip_address):
                print(f"  {ptr.ip_address:16} -> {ptr.target}   (zone {ptr.zone})")
        if ptr_plan.changed:
            print(f"\n~ CHANGED ({len(ptr_plan.changed)} records - point to another name, would be replaced):")
            for ptr, current in sorted(ptr_plan.changed.items(), key=lambda item: item[0].ip_address):
                print(f"  {ptr.ip_address:16} {', '.join(current)} -> {ptr.target}")
        for note in ptr_plan.notes:
            print(f"\n  note: {note}")
        print(f"\nPTR summary: {len(ptr_plan.matching)} matching, {len(ptr_plan.missing)} missing, "
              f"{len(ptr_plan.changed)} changed")
        print("=" * 80 + "\n")

    def _apply_changes(self, provider: DNSProvider, missing: Set[DNSRecord], stale: Set[DNSRecord],
                       ptr_plan: Optional[PtrPlan] = None, zone_plans=()):
        """Apply DNS changes to the provider"""
        self.logger.info("Applying changes...")

        zones_created, zones_failed = provider.create_zones(list(zone_plans)) if zone_plans else ([], [])
        for plan, reason in zones_failed:
            self.logger.error(f"Could not create the {'reverse ' if plan.reverse else ''}zone {plan.name}: {reason}")

        if zones_created:
            missing = provider.normalize(missing)  # the new zones now own their host names
        written = []
        deleted = 0

        for record in missing:
            if provider.create_record(record):
                written.append(record)

        created = len(written)
        failed = len(missing) - created
        ptr_written: List[PtrRecord] = []
        ptr_to_write = ptr_plan.to_write if ptr_plan else []
        for ptr in ptr_to_write:
            if provider.create_ptr(ptr):
                ptr_written.append(ptr)
        ptr_failed = len(ptr_to_write) - len(ptr_written)
        failed += ptr_failed + len(zones_failed)
        if provider.deletes_stale:
            for record in stale:
                if provider.delete_record(record):
                    deleted += 1

        zones_note = f", {len(zones_created)} zones created" if zone_plans else ""
        ptr_note = f", {len(ptr_written)} PTR records created or updated" if ptr_plan else ""
        self.logger.info(f"Changes applied: {created} created or updated{ptr_note}{zones_note}, {deleted} deleted, "
                         f"{failed} failed")
        unverified, ptr_unverified = ([], [])
        if (written or ptr_written) and provider.needs_settle:
            unverified, ptr_unverified = self._verify(provider, written, ptr_written)
        if failed:
            sys.exit(1)
        if unverified or ptr_unverified:
            self.logger.error(f"{len(unverified) + len(ptr_unverified)} records were written but do not resolve yet. "
                              "The DNS service loads AD changes on its polling interval (about 3 minutes by default, "
                              "and a new zone is loaded the same way); refresh the zone on the domain controller or "
                              "run Validate again shortly")
            sys.exit(1)

    def _verify(self, provider: DNSProvider, written: List[DNSRecord], written_ptr=()):
        """Wait for the DNS server to load the written records; returns the (A, PTR) ones still not resolving"""
        pending = set(written)
        pending_ptr = set(written_ptr)
        total = len(written) + len(pending_ptr)
        zones = {record.zone for record in written}
        for check in range(1, self.VERIFY_CHECKS + 1):
            self.logger.info(f"Waiting {self.VERIFY_INTERVAL}s for the DNS service to load the changes "
                             f"(check {check} of {self.VERIFY_CHECKS})")
            time.sleep(self.VERIFY_INTERVAL)
            visible = set()
            for zone in zones:
                visible |= provider.get_records(zone)
            pending = {record for record in pending if record not in visible}
            pending_ptr = {ptr for ptr in pending_ptr if not provider.ptr_resolves(ptr)}
            if not pending and not pending_ptr:
                self.logger.info(f"Verified: all {total} records resolve to their addresses")
                return [], []
            self.logger.info(f"{total - len(pending) - len(pending_ptr)} of {total} records resolve so far")
        for record in sorted(pending, key=lambda r: r.hostname):
            self.logger.warning(f"Not resolving yet: {record.hostname} -> {record.ip_address}")
        for ptr in sorted(pending_ptr, key=lambda p: p.ip_address):
            self.logger.warning(f"Not resolving yet: PTR {ptr.ip_address} -> {ptr.target}")
        return sorted(pending, key=lambda r: r.hostname), sorted(pending_ptr, key=lambda p: p.ip_address)


def main():
    parser = argparse.ArgumentParser(
        description='Synchronize DNS records across multiple providers'
    )
    parser.add_argument(
        '--config',
        required=True,
        help='Path to configuration YAML file'
    )
    parser.add_argument(
        '--provider',
        required=True,
        choices=['ad', 'infoblox', 'bluecat', 'efficientip', 'bind'],
        help='DNS provider to update'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Run in dry-run mode (default: enabled)'
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Apply changes (disable dry-run mode)'
    )
    parser.add_argument(
        '--check',
        action='store_true',
        help='Dry run that exits with an error when any record is missing or has a different address'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    updater = DNSUpdater(
        config_file=args.config,
        dry_run=not args.apply,
        verbose=args.verbose,
        check=args.check
    )
    try:
        updater.run(args.provider)
    except (RuntimeError, ValueError) as e:
        logging.getLogger(__name__).error(str(e))
        sys.exit(1)


if __name__ == '__main__':
    main()
