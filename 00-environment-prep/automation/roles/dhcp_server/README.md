# dhcp_server

Configures ISC Kea DHCPv4 on the deployment host (Rocky Linux 9/10, RHEL, or Ubuntu 24.04/26.04)
used to bootstrap an AI Pod. Serves addresses for CIMC out-of-band management, the in-band
management network, and Nexus switches via POAP (DHCP options 66/67/150 pointing at the
Nexus Dashboard data interface IP).

The role installs Kea (`kea` on EL, `kea-dhcp4-server` on Ubuntu), renders
`/etc/kea/kea-dhcp4.conf` from a YAML data model, validates it with `kea-dhcp4 -t`,
enables/starts the service (`kea-dhcp4` on EL, `kea-dhcp4-server` on Ubuntu), and opens
UDP 67 in firewalld or ufw. ISC dhcpd is no longer used because EL10 and Ubuntu 24.04 do not
ship it. The rendered configuration has been validated with Kea 2.4.1 (Ubuntu 24.04) and
3.0.3 (Rocky Linux 10 and Ubuntu 26.04).

## Usage

```bash
ansible-playbook 00-environment-prep/automation/playbooks/deploy_dhcp_server.yml \
  -i <inventory> \
  -e dhcp_vars_file=$(pwd)/00-environment-prep/automation/examples/dhcp.yaml
```

`playbooks/deploy_dhcp_server.yaml` remains as a compatibility entry point. Add
`-e dhcp_render_only=true -e dhcp_render_dest=/tmp/kea-dhcp4.conf` to render the file
without installing packages or changing services. The Automation UI generates the same
`dhcp` data model from the initial inventory.

Requires `ansible.posix` (firewalld) and `community.general` (ufw).

## Role Variables

| Variable | Default | Description |
| --- | --- | --- |
| `dhcp_vars_file` | `""` | Path to a YAML file containing the `dhcp` object. When empty, `dhcp` must be supplied by the playbook or host_vars. |
| `dhcp_config_path` | `/etc/kea/kea-dhcp4.conf` | Rendered config destination. |
| `dhcp_lease_file` | `/var/lib/kea/kea-leases4.csv` | Kea memfile lease database. |
| `dhcp_packages` / `dhcp_service_name` | per OS family | Kea package list and systemd unit. |
| `dhcp_service_enabled` / `dhcp_service_state` | `true` / `started` | systemd unit handling. |
| `dhcp_kea_version` | detected | Selects `client-class` (before 2.7.4) or `client-classes` syntax. |
| `dhcp_render_only` / `dhcp_render_dest` | `false` / `""` | Render the configuration only. |
| `dhcp_manage_firewall` | `true` | firewalld on EL; ufw on Ubuntu when installed. |
| `dhcp_firewall_services` | `['dhcp']` | firewalld services. Add `tftp` if the host also serves TFTP. |
| `dhcp_firewall_zone` | `""` | Optional firewalld zone; omitted when empty. |

## Data Model

```yaml
dhcp:
  interfaces: [eth0]            # Kea interfaces-config; defaults to all
  authoritative: true
  domain_name: aipod.example.com
  domain_name_servers: [10.10.10.10]
  ntp_servers: [10.10.10.20]
  default_lease_time: 3600
  max_lease_time: 86400
  global_options:               # Kea option-data (name + data)
    - {name: vendor-class-identifier, value: ccm}

  subnets:
    - name: nexus-mgmt
      network: 10.10.40.0
      netmask: 255.255.255.0
      routers: 10.10.40.1       # scalar or list
      broadcast_address: 10.10.40.255
      mtu: 9000
      domain_name_servers: [10.10.10.10]
      tftp_server: 10.10.40.50  # Nexus Dashboard data IP -> next-server + options 66/150
      bootfile: poap.py         # option 67
      deny_unknown_clients: false
      ranges:
        - {start: 10.10.40.100, end: 10.10.40.150}
      options:
        - {name: time-offset, value: '-21600'}

  reservations:
    - hostname: leaf-01         # Kea reservation hostname (option 12)
      subnet: nexus-mgmt        # inherits tftp_server / bootfile from the subnet
      mac: "aa:bb:cc:00:00:11"
      ip: 10.10.40.11
      tftp_server: 10.10.40.50  # optional per-host override
      bootfile: poap.py         # optional per-host override
```

Notes:

- `global_options`, subnet `options`, and reservation `options` map to Kea `option-data`.
  `value` (or `data`) uses Kea's text format; surrounding double quotes are removed.
  Optional `code`, `space`, `csv-format`, and `always-send` keys pass through.
- Option 150 (`tftp-server-address`) is defined as a custom option; NX-OS POAP prefers it
  over option 66. `tftp_server` also sets `next-server`, and `bootfile` sets both the
  `boot-file-name` field and option 67.
- Reservations are placed in the subnet named by `subnet`, or in the subnet that contains
  their IP when `subnet` is omitted. Kea does not inherit per-host values from another
  subnet, so set `tftp_server` / `bootfile` on the subnet or the reservation.
- `deny_unknown_clients: true` limits the subnet pools to hosts with reservations (`KNOWN`).
- `ntp_servers` and `domain_name_servers` must be IPv4 addresses for Kea.
- DHCP relay must be configured on the upstream SVI (`ip dhcp relay address <staging-host>`)
  for subnets not directly attached to this host.
