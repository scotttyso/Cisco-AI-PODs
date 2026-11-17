#!/usr/bin/env python3
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
import socket
import ssl
import struct
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from pathlib import Path
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


class DNSProvider(ABC):
    """Abstract base class for DNS providers"""

    # Providers only report on the desired records until their create/update/delete calls are really implemented
    supports_write = False
    # Providers that only replace a name's addresses on update leave differing records alone on apply
    deletes_stale = True
    writable = False

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
        pass

    @abstractmethod
    def get_records(self, zone: str) -> Set[DNSRecord]:
        """Retrieve all DNS records from a zone"""
        pass

    @abstractmethod
    def create_record(self, record: DNSRecord) -> bool:
        """Create a new DNS record"""
        pass

    @abstractmethod
    def update_record(self, record: DNSRecord) -> bool:
        """Update an existing DNS record"""
        pass

    @abstractmethod
    def delete_record(self, record: DNSRecord) -> bool:
        """Delete a DNS record"""
        pass

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

    def __init__(self, config: Dict, vault_client: Optional[VaultClient] = None):
        super().__init__(config, vault_client)
        self.server = None
        self.username = None
        self.password = None

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
        raise RuntimeError(f"Cannot bind to {self.server} as {self.username}: " + "; ".join(errors))

    def _load_zones(self):
        """Connect over LDAP and list the AD-integrated DNS zones (needed to write; optional to validate)"""
        self.connection = None
        self.zones: Dict[str, str] = {}
        self.serials: Dict[str, int] = {}
        if not (self.username and self.password):
            if self.writable:
                raise RuntimeError("Active Directory credentials are not set")
            self.logger.warning("No credentials; zones are inferred from the hostnames")
            return
        try:
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
                            if not name.startswith('..'):
                                self.zones.setdefault(name, entry.entry_dn)
                except LDAPException:
                    continue
            self.connection = connection
            self.logger.info(f"AD DNS zones: {', '.join(sorted(self.zones)) or 'none found'}")
        except Exception as e:
            if self.writable:
                raise
            self.logger.warning(f"LDAP unavailable ({e}); zones are inferred from the hostnames")

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

        self.logger.info(f"Comparison results:")
        self.logger.info(f"  Matching records: {len(matching)}")
        self.logger.info(f"  Missing records: {len(missing)}")
        self.logger.info(f"  Stale records: {len(stale)}")

        return missing, stale, matching


class InventoryParser:
    """Parse inventory from YAML files"""

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)

    @staticmethod
    def load_shared_ldap_config(initial_inventory_path: str) -> Optional[Dict]:
        """Load LDAP configuration from shared_services in Initial Inventory
        
        Args:
            initial_inventory_path: Path to initial_inventory.ezai.yaml file
            
        Returns:
            Dictionary with ldap config (url, bind_dn, secure_ldap) or None if not found
        """
        try:
            with open(initial_inventory_path, 'r') as f:
                data = yaml.safe_load(f)
            
            if not data or 'shared_services' not in data:
                return None
            
            ldap_config = data['shared_services'].get('ldap', {})
            if ldap_config:
                return ldap_config
            
            return None
        except (FileNotFoundError, yaml.YAMLError) as e:
            logging.warning(f"Could not load shared LDAP config from {initial_inventory_path}: {e}")
            return None

    def parse_openshift(self, file_path: str) -> Set[DNSRecord]:
        """Parse OpenShift install.ezai.yaml inventory
        
        Extracts DNS records from cluster deployment configuration including:
        - Host primary interface DNS (hostname.base_dns_domain)
        - Interface-specific DNS (hostname-interface.base_dns_domain)
        - Cluster API endpoint (api.cluster_name.base_dns_domain)
        - Wildcard ingress (*.apps.cluster_name.base_dns_domain)
        """
        records = set()
        try:
            with open(file_path, 'r') as f:
                data = yaml.safe_load(f)
            
            if not data or 'openshift' not in data:
                self.logger.warning(f"No OpenShift config found in {file_path}")
                return records
            
            install_config = data['openshift'].get('install', {}).get('bare_metal', {})
            if not install_config:
                self.logger.warning(f"No bare_metal config found in {file_path}")
                return records
            
            base_dns_domain = install_config.get('base_dns_domain', 'local')
            cluster_name = install_config.get('cluster_name', '')
            
            # Add cluster API endpoint
            api_ip = None
            if 'cluster_networking' in install_config:
                api_ip = install_config['cluster_networking'].get('api', {}).get('v4')
            if api_ip and cluster_name:
                api_hostname = f"api.{cluster_name}.{base_dns_domain}"
                records.add(DNSRecord(
                    hostname=api_hostname,
                    ip_address=api_ip,
                    zone=base_dns_domain,
                    description="OpenShift API Endpoint"
                ))
                # Also add api-int (internal API)
                api_int_hostname = f"api-int.{cluster_name}.{base_dns_domain}"
                records.add(DNSRecord(
                    hostname=api_int_hostname,
                    ip_address=api_ip,
                    zone=base_dns_domain,
                    description="OpenShift API (Internal)"
                ))
            
            # Add wildcard ingress endpoint
            ingress_ip = None
            if 'cluster_networking' in install_config:
                ingress_ip = install_config['cluster_networking'].get('ingress', {}).get('v4')
            if ingress_ip and cluster_name:
                # Store wildcard pattern for later processing
                wildcard_hostname = f"*.apps.{cluster_name}.{base_dns_domain}"
                records.add(DNSRecord(
                    hostname=wildcard_hostname,
                    ip_address=ingress_ip,
                    zone=base_dns_domain,
                    description="OpenShift Wildcard Ingress"
                ))
            
            # Parse individual servers/nodes
            for server in install_config.get('servers', []):
                hostname = server.get('hostname')
                if not hostname:
                    continue
                
                fqdn = f"{hostname}.{base_dns_domain}"
                
                # Process network interfaces
                interfaces = server.get('interfaces', {})
                ethernet_interfaces = interfaces.get('ethernet', [])
                
                for idx, interface in enumerate(ethernet_interfaces):
                    iface_name = interface.get('name')
                    ipv4 = interface.get('ipv4')
                    
                    if ipv4:
                        # Extract IP without CIDR notation
                        ip_address = ipv4.split('/')[0]
                        
                        # Primary interface (first one)
                        if idx == 0:
                            records.add(DNSRecord(
                                hostname=fqdn,
                                ip_address=ip_address,
                                zone=base_dns_domain,
                                description=f"OpenShift {server.get('role', 'node')} - {hostname}"
                            ))
                        
                        # Interface-specific DNS entry
                        if iface_name:
                            iface_fqdn = f"{hostname}-{iface_name}.{base_dns_domain}"
                            records.add(DNSRecord(
                                hostname=iface_fqdn,
                                ip_address=ip_address,
                                zone=base_dns_domain,
                                description=f"OpenShift {hostname} interface {iface_name}"
                            ))
            
            self.logger.info(f"Parsed {len(records)} records from OpenShift inventory ({file_path})")
        except Exception as e:
            self.logger.error(f"Failed to parse OpenShift inventory: {e}")
        
        return records

    def parse_intersight(self, file_path: str) -> Set[DNSRecord]:
        """Parse Intersight inventory from shared_services inventory.yaml
        
        Extracts DNS records for Intersight-managed infrastructure including:
        - Server data network interfaces
        - Management network interfaces
        - Storage nodes
        - Network devices
        """
        records = set()
        try:
            with open(file_path, 'r') as f:
                data = yaml.safe_load(f)
            
            if not data:
                return records
            
            # Determine base DNS domain from configuration or default
            base_dns_domain = 'local'
            if 'shared_services' in data:
                base_dns_domain = data['shared_services'].get('dns_domain', 'local')
            
            # Parse compute servers
            servers = data.get('servers', [])
            if isinstance(servers, dict):
                # If servers is a dict, convert to list of values
                servers = list(servers.values()) if servers else []
            
            for server in servers:
                if isinstance(server, dict):
                    hostname = server.get('hostname')
                    # Try different field names for IP
                    ip = server.get('ip') or server.get('management_ip') or server.get('mgmt_ip')
                    
                    if hostname and ip:
                        fqdn = hostname if '.' in hostname else f"{hostname}.{base_dns_domain}"
                        zone = self._extract_zone(fqdn)
                        records.add(DNSRecord(
                            hostname=fqdn,
                            ip_address=ip,
                            zone=zone,
                            description="Intersight Server"
                        ))
            
            # Parse storage devices
            storage_devices = data.get('storage', [])
            if isinstance(storage_devices, dict):
                storage_devices = list(storage_devices.values()) if storage_devices else []
            
            for storage in storage_devices:
                if isinstance(storage, dict):
                    hostname = storage.get('hostname')
                    ip = storage.get('ip') or storage.get('management_ip') or storage.get('mgmt_ip')
                    
                    if hostname and ip:
                        fqdn = hostname if '.' in hostname else f"{hostname}.{base_dns_domain}"
                        zone = self._extract_zone(fqdn)
                        records.add(DNSRecord(
                            hostname=fqdn,
                            ip_address=ip,
                            zone=zone,
                            description="Intersight Storage"
                        ))
            
            # Parse network devices
            network_devices = data.get('network', [])
            if isinstance(network_devices, dict):
                network_devices = list(network_devices.values()) if network_devices else []
            
            for network in network_devices:
                if isinstance(network, dict):
                    hostname = network.get('hostname')
                    ip = network.get('management_ip') or network.get('mgmt_ip')
                    
                    if hostname and ip:
                        fqdn = hostname if '.' in hostname else f"{hostname}.{base_dns_domain}"
                        zone = self._extract_zone(fqdn)
                        records.add(DNSRecord(
                            hostname=fqdn,
                            ip_address=ip,
                            zone=zone,
                            description="Intersight Network Device"
                        ))
            
            self.logger.info(f"Parsed {len(records)} records from Intersight inventory ({file_path})")
        except Exception as e:
            self.logger.error(f"Failed to parse Intersight inventory: {e}")
        
        return records

    def parse_everpure(self, file_path: str) -> Set[DNSRecord]:
        """Parse EveryPure inventory from storage configuration
        
        Extracts DNS records for EveryPure appliances and cluster including:
        - Individual appliance management IPs
        - Cluster VIP
        - Cluster API endpoint
        """
        records = set()
        try:
            with open(file_path, 'r') as f:
                data = yaml.safe_load(f)
            
            if not data or 'everpure' not in data:
                return records
            
            everpure_config = data['everpure']
            
            # Determine base DNS domain
            base_dns_domain = 'local'
            if 'shared_services' in data:
                base_dns_domain = data['shared_services'].get('dns_domain', 'local')
            
            # Parse individual appliances
            appliances = everpure_config.get('appliances', [])
            if isinstance(appliances, dict):
                appliances = list(appliances.values()) if appliances else []
            
            for appliance in appliances:
                if isinstance(appliance, dict):
                    hostname = appliance.get('hostname')
                    # Try different field names for IP
                    ip = appliance.get('ip') or appliance.get('mgmt_ip') or appliance.get('management_ip')
                    
                    if hostname and ip:
                        fqdn = hostname if '.' in hostname else f"{hostname}.{base_dns_domain}"
                        zone = self._extract_zone(fqdn)
                        records.add(DNSRecord(
                            hostname=fqdn,
                            ip_address=ip,
                            zone=zone,
                            description="EveryPure Appliance"
                        ))
            
            # Parse cluster configuration
            cluster = everpure_config.get('cluster', {})
            if isinstance(cluster, dict):
                cluster_hostname = cluster.get('hostname')
                cluster_vip = cluster.get('vip')
                api_hostname = cluster.get('api_hostname')
                api_ip = cluster.get('api_ip')
                
                # Add cluster VIP
                if cluster_hostname and cluster_vip:
                    fqdn = cluster_hostname if '.' in cluster_hostname else f"{cluster_hostname}.{base_dns_domain}"
                    zone = self._extract_zone(fqdn)
                    records.add(DNSRecord(
                        hostname=fqdn,
                        ip_address=cluster_vip,
                        zone=zone,
                        description="EveryPure Cluster"
                    ))
                
                # Add API endpoint
                if api_hostname and api_ip:
                    fqdn = api_hostname if '.' in api_hostname else f"{api_hostname}.{base_dns_domain}"
                    zone = self._extract_zone(fqdn)
                    records.add(DNSRecord(
                        hostname=fqdn,
                        ip_address=api_ip,
                        zone=zone,
                        description="EveryPure API"
                    ))
            
            self.logger.info(f"Parsed {len(records)} records from EveryPure inventory ({file_path})")
        except Exception as e:
            self.logger.error(f"Failed to parse EveryPure inventory: {e}")
        
        return records

    def parse_all_sources(self, config: Dict) -> Set[DNSRecord]:
        """Parse all configured inventory sources
        
        Only processes inventory sources where files exist and are configured.
        Supports multiple formats:
        - Dictionary of {source_type: file_path}
        - Dictionary of {source_name: {file: path, enabled: bool}}
        """
        all_records = set()
        
        for source_key, source_config in config.items():
            # Handle both config formats
            if isinstance(source_config, str):
                # Simple format: source_type -> file_path
                file_path = source_config
                source_type = source_key
            elif isinstance(source_config, dict):
                # Complex format: source_name -> {file: path, enabled: bool, ...}
                if not source_config.get('enabled', True):
                    self.logger.debug(f"Skipping disabled inventory source: {source_key}")
                    continue
                
                file_path = source_config.get('file')
                # Try to infer source type from source_key if not explicit
                source_type = source_config.get('type', source_key)
            else:
                continue
            
            # Check if file exists before parsing
            if not file_path:
                self.logger.debug(f"No file path for inventory source: {source_key}")
                continue
            
            if not Path(file_path).exists():
                self.logger.warning(f"Inventory file not found: {file_path} (skipping {source_key})")
                continue
            
            self.logger.info(f"Processing inventory source: {source_key} from {file_path}")
            
            # Parse based on source type
            if source_type.lower() == 'openshift':
                all_records.update(self.parse_openshift(file_path))
            elif source_type.lower() == 'intersight':
                all_records.update(self.parse_intersight(file_path))
            elif source_type.lower() == 'everpure':
                all_records.update(self.parse_everpure(file_path))
            else:
                self.logger.warning(f"Unknown inventory source type: {source_type}")
        
        self.logger.info(f"Total records parsed from all sources: {len(all_records)}")
        return all_records

    @staticmethod
    def _extract_zone(hostname: str) -> str:
        """Extract zone from FQDN"""
        parts = hostname.split('.')
        if len(parts) > 1:
            return '.'.join(parts[1:])
        return 'local'


class DNSUpdater:
    """Main DNS updater orchestrator"""

    PROVIDERS = {
        'ad': ActiveDirectoryProvider,
        'infoblox': InfobloxProvider,
        'bluecat': BlueCatProvider,
        'efficientip': EfficientIPProvider,
        'bind': BindDNSProvider,
    }

    def __init__(self, config_file: str, dry_run: bool = True, verbose: bool = False):
        self.config_file = config_file
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

        # Print detailed report
        self._print_report(missing, stale, matching)

        # Apply changes if not in dry-run mode
        if not self.dry_run:
            if not provider.supports_write:
                self.logger.error(f"Writing records to '{provider_name}' is not implemented yet; "
                                  "nothing was changed")
                sys.exit(2)
            self._apply_changes(provider, missing, stale)
        else:
            self.logger.info("DRY-RUN MODE: No changes applied")

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
        """Records listed as hostname/ipv4 pairs, plus any legacy inventory sources"""
        records = set()
        for item in config.get('records') or []:
            hostname, ip = str(item.get('hostname', '')).strip().rstrip('.'), str(item.get('ipv4', '')).strip()
            if hostname and ip:
                records.add(DNSRecord(hostname, ip, InventoryParser._extract_zone(hostname)))
        if config.get('inventory'):
            records |= InventoryParser(self.logger).parse_all_sources(config['inventory'])
        return records

    def _print_report(self, missing: Set[DNSRecord], stale: Set[DNSRecord], matching: Set[DNSRecord]):
        """Print comparison report"""
        print("\n" + "="*80)
        print("DNS UPDATE REPORT")
        print("="*80)

        if matching:
            print(f"\n✓ MATCHING ({len(matching)} records):")
            for record in sorted(matching, key=lambda r: r.hostname):
                print(f"  {record.hostname:40} -> {record.ip_address}")

        if missing:
            print(f"\n+ MISSING ({len(missing)} records - would be created):")
            for record in sorted(missing, key=lambda r: r.hostname):
                print(f"  {record.hostname:40} -> {record.ip_address}")

        if stale:
            print(f"\n- STALE ({len(stale)} records - present with a different address):")
            for record in sorted(stale, key=lambda r: r.hostname):
                print(f"  {record.hostname:40} -> {record.ip_address}")

        print("\n" + "="*80)
        print(f"Summary: {len(matching)} matching, {len(missing)} missing, {len(stale)} stale")
        print("="*80 + "\n")

    def _apply_changes(self, provider: DNSProvider, missing: Set[DNSRecord], stale: Set[DNSRecord]):
        """Apply DNS changes to the provider"""
        self.logger.info("Applying changes...")

        created = 0
        deleted = 0

        for record in missing:
            if provider.create_record(record):
                created += 1

        failed = len(missing) - created
        if provider.deletes_stale:
            for record in stale:
                if provider.delete_record(record):
                    deleted += 1

        self.logger.info(f"Changes applied: {created} created or updated, {deleted} deleted, {failed} failed")
        if created:
            self.logger.info("The DNS service reads AD changes within about a minute; run Validate again to confirm")
        if failed:
            sys.exit(1)


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
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    updater = DNSUpdater(
        config_file=args.config,
        dry_run=not args.apply,
        verbose=args.verbose
    )
    updater.run(args.provider)


if __name__ == '__main__':
    main()
