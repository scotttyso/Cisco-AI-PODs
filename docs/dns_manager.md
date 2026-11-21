# DNS Manager

The DNS Manager page (Environment Preparation > DNS Manager) builds the list of A records for a deployment and compares it with your DNS server. Validate reports what is missing. Synchronize creates the missing records in Active Directory DNS, together with the pointer (PTR) records and any forward or reverse zone that does not exist yet.

## What it does

| Action | Active Directory | Infoblox, BlueCat, Efficient IP, BIND |
|---|---|---|
| Validate | Queries the AD DNS server for every record and reports matching, missing, changed, and stale records. Nothing is changed. | Not implemented yet |
| Synchronize | Creates missing A records and replaces the address of a record that exists with a different one. | Not implemented yet; stops without changing DNS |

Synchronize never deletes records, and other record types on a name (TXT, CNAME, and so on) are kept.

## Where the records come from

Generate Configuration builds `dns/dns_config.ezai.yaml` for the active environment from the sources you tick:

| Source | Records |
|---|---|
| OpenShift Cluster Deployment (`openshift/install.ezai.yaml`) | Each node, `api.<cluster>.<domain>`, and `*.apps.<cluster>.<domain>` |
| Initial Inventory | Every device with a hostname and IP, including storage arrays |

Add storage arrays (Everpure, NetApp, VAST, and so on) to **Initial Inventory** with the **Storage array** role so they are included. A hostname without a domain gets the OpenShift base domain (or the Active Directory domain when there is none). A hostname that is already fully qualified is kept as it is.

The `records` list in the saved file is what Validate and Synchronize use. You can edit it by hand and Save before running an action.

```yaml
dns:
  providers:
    ad_primary:
      type: active_directory
      use_shared_ldap: true
      server: dc1.example.com
      domain: example.com
      bind_dn: CN=dns-automation,CN=Users,DC=example,DC=com
      timeout: 10
  records:
    - hostname: node1.example.com
      ipv4: 198.18.0.1
    - hostname: "*.apps.cluster.example.com"
      ipv4: 198.18.0.10
```

Hover over any field in the editor for its description, including which attributes are required.

## Credentials

Passwords are never written to the YAML. They are stored in the vault and passed to the updater when an action runs.

- **Active Directory with `use_shared_ldap: true`:** the server, domain, and bind DN come from Initial Inventory > Shared services > LDAP, and the bind password saved there is used. The DNS Manager page shows whether it is stored.
- **Active Directory without shared LDAP, and the other providers:** enter the username and password under Passwords and secrets on the DNS Manager page. Only the fields for the provider in the saved file are listed.

## Checking DNS before the OpenShift install

On the OpenShift Cluster Deployment page, **Check DNS records** (Pre-check) resolves every record in the saved DNS Manager configuration against the DNS server: each node, `api.<cluster>.<domain>`, and `*.apps.<cluster>.<domain>`. It fails when any record is missing or resolves to a different address, so run it before **Install cluster**. Generate and save the DNS Manager configuration first.

## Typical run

1. Save the OpenShift install file and the Initial Inventory (devices, storage arrays, and the LDAP shared service with its bind password).
2. Open DNS Manager, pick the provider, tick the sources, and click Generate Configuration. Review the YAML and Save.
3. Run **Validate** and review the report.
4. Run **Synchronize** and confirm.
5. When Synchronize writes over LDAP it stays running to confirm the result: it checks DNS up to 4 times, 60 seconds apart (the DNS service polls Active Directory about every 3 minutes), and stops as soon as every record resolves. A run that ends with "Verified: all N records resolve" needs no further check. If records are written but still not resolving after about 4 minutes, the job fails and says so; refresh the zone on the domain controller and run **Validate**. Writes made over WinRM take effect immediately and are not waited on. Every record should now be matching.

Example Validate report:

```text
+ MISSING (2 records - would be created):
  api.cluster.example.com                  -> 198.18.0.9
  node2.example.com                        -> 198.18.0.2

~ CHANGED (1 records - exist with another address, would be replaced):
  node1.example.com                        198.18.0.99 -> 198.18.0.1
```

## How Active Directory records are written

**Validate** only asks the DNS server (port 53) for each name, so it works without an LDAP bind. **Synchronize** writes through LDAP and needs a working bind.

Synchronize binds to the domain controller over LDAP with the bind account, finds the AD-integrated DNS zones, and writes each A record into the zone with the longest matching name. The bind account needs permission to create and modify DNS records in those zones.

- Current domain controllers refuse simple binds on cleartext LDAP (port 389, `strongerAuthRequired`). The updater then retries over LDAPS (636) and StartTLS, without verifying the domain controller certificate, and logs a warning. This only works when the domain controller has a server certificate installed.
- **WinRM fallback:** when no LDAP bind works, Synchronize connects to the domain controller over WinRM (HTTP 5985, then HTTPS 5986) with NTLM and runs the Windows DNS Server cmdlets there (`Get-DnsServerZone`, `Add-DnsServerResourceRecordA`, `Set-DnsServerResourceRecord`). WinRM is enabled by default on Windows Server 2012 and later, and the account needs rights to manage DNS (Administrator or DnsAdmins). The domain controller must also run the DNS Server role, which an AD DNS server does. Validate never uses WinRM.
- The WinRM logon name is derived from the bind DN as `<common name>@<domain>`. If the account's common name differs from its logon name, store the Active Directory username (as `user@domain`) under Passwords and secrets.
- Synchronize logs which method it used (`AD DNS zones (LDAP)` or `Connected over WinRM`).
- A hostname that is not inside any AD-integrated zone gets its zone created (see below); when that is switched off or fails, the record is reported as failed and the run exits with an error.
- Existing records are changed only for names in your `records` list.

## Pointer records and zones (Active Directory)

Validate and Synchronize also handle reverse lookups:

- **PTR records:** one per address, pointing to the host name. When several names share an address (for example `api` and `api-int`), the shortest name is used and the others are listed in a note. Wildcard names such as `*.apps...` get no PTR record. A PTR record that points to another name is replaced; nothing is deleted. Validate reads the current PTR records from the DNS server (port 53) and reports them as matching, missing, or changed.
- **Missing zones:** when no AD-integrated zone covers a host name, its forward zone is created (the `domain` of the provider when the name is inside it, otherwise the name without its first label). When no reverse zone covers an address, a `c.b.a.in-addr.arpa` zone is created (a /24); an existing reverse zone that covers the address is always used. Validate lists the zones that would be created.
- **How zones are created:** as AD-integrated primary zones with secure dynamic updates, through the DNS Server cmdlets over WinRM (`Add-DnsServerPrimaryZone`) with the bind account. LDAP alone cannot create a zone. If WinRM is not reachable, the job fails and prints the PowerShell command to run on the domain controller. A new zone is an authoritative zone: make sure the name is not already served elsewhere.
- **Order:** zones, then A records, then PTR records. The final check also covers the PTR records.

Options of the provider in `dns_config.ezai.yaml` (all optional):

| Option | Default | Meaning |
|---|---|---|
| `create_ptr_records` | `true` | Create PTR records. `false` leaves reverse lookups alone |
| `create_zones` | `true` | Create missing forward and reverse zones. `false` only reports them |
| `reverse_zone_prefix` | `24` | Size of a reverse zone that has to be created: `24`, `16` or `8` |
| `zone_replication_scope` | `Domain` | Where a new zone is stored: `Domain`, `Forest` or `Legacy` |

`--check` (used by the pre-install test) only gates on A records.

## Command line

The page runs `scripts/dns_updater.py`. To run it by hand:

```bash
python scripts/dns_updater.py --config <environment>/host_vars/dns/dns_config.ezai.yaml --provider ad            # validate
python scripts/dns_updater.py --config <environment>/host_vars/dns/dns_config.ezai.yaml --provider ad --check    # validate; exit 1 if anything is missing
python scripts/dns_updater.py --config <environment>/host_vars/dns/dns_config.ezai.yaml --provider ad --apply    # synchronize
```

Credentials are read from the environment: `ad_username` and `ad_password`, or `ldap_bind_password` with shared LDAP. The UI sets them from the vault. Unit tests are in `scripts/test_dns_updater.py`.

## Troubleshooting

| Symptom | Cause |
|---|---|
| "Save the DNS Manager configuration first" | No `dns/dns_config.ezai.yaml` saved in the active environment |
| "Active Directory credentials are not set" | The bind password is not stored in Shared services, or the AD password is not stored on the DNS Manager page |
| "LDAP failed: ... WinRM fallback failed: ..." | Neither method worked. The LDAP part says why LDAP failed (`strongerAuthRequired` means signing or TLS is required and there is no LDAPS certificate). The WinRM part says why WinRM failed: wrong account name or password, WinRM not enabled or blocked on 5985/5986, or no rights to manage DNS |
| "the pywinrm package is not installed" | Update the appliance with the release that includes it, or `pip install pywinrm` |
| "No AD-integrated DNS zone found for ..." | The zone could not be created; see the zone error above it (WinRM reachable? `create_zones` off?) |
| "Could not create the zone ..." | Zones are created over WinRM; open 5985/5986 to the domain controller or run the printed `Add-DnsServerPrimaryZone` command there |
| PTR records are "missing" although they were written | The DNS service loads new records and zones on its polling interval (about 3 minutes); run Validate again |
| Generate Configuration warns that no records were found | Save the OpenShift install file, or add devices to the Initial Inventory |
| Validate still shows missing records right after Synchronize | Records written over LDAP appear after the DNS service polls AD (about 3 minutes by default); refresh the zone or wait |
