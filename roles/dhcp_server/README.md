# dhcp_server

Configures ISC DHCP (`dhcp-server`) on a RHEL 9 bare metal host or VM used to stage an
AI Pod / OpenShift deployment. Serves addresses for CIMC out-of-band management, the
in-band management network, and Nexus switches via POAP (DHCP options 66/67/150 pointing
at the Nexus Dashboard data interface IP).

The role installs the package, renders `/etc/dhcp/dhcpd.conf` from a YAML data model,
validates the config with `dhcpd -t`, enables/starts `dhcpd`, and opens the firewall.

## Usage

```bash
ansible-playbook playbooks/deploy_dhcp_server.yaml \
  -i examples/dhcp/inventory.ini \
  -e dhcp_vars_file=$(pwd)/examples/dhcp/dhcp.yaml
```

Requires the `ansible.posix` collection for firewalld management.

## Role Variables

| Variable | Default | Description |
| --- | --- | --- |
| `dhcp_vars_file` | `""` | Path to a YAML file containing the `dhcp` object. When empty, `dhcp` must be supplied by the playbook or host_vars. |
| `dhcp_config_path` | `/etc/dhcp/dhcpd.conf` | Rendered config destination. |
| `dhcp_sysconfig_path` | `/etc/sysconfig/dhcpd` | Where `DHCPDARGS` (listening interfaces) is written. |
| `dhcp_service_enabled` / `dhcp_service_state` | `true` / `started` | systemd unit handling. |
| `dhcp_manage_firewall` | `true` | Install/enable firewalld and open services. |
| `dhcp_firewall_services` | `['dhcp']` | Add `tftp` if the host also serves TFTP. |
| `dhcp_firewall_zone` | `""` | Optional firewalld zone; omitted when empty. |

## Data Model

```yaml
dhcp:
  interfaces: [eth0]            # DHCPDARGS
  authoritative: true
  domain_name: aipod.example.com
  domain_name_servers: [10.10.10.10]
  ntp_servers: [10.10.10.20]
  default_lease_time: 3600
  max_lease_time: 86400
  global_options:               # raw dhcpd options
    - {name: vendor-class-identifier, value: '"ccm"'}

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
        - {name: time-offset, value: -21600}

  reservations:
    - hostname: leaf-01         # dhcpd host label + option 12 (host-name)
      subnet: nexus-mgmt        # inherits tftp_server / bootfile from the subnet
      mac: "aa:bb:cc:00:00:11"
      ip: 10.10.40.11
      tftp_server: 10.10.40.50  # optional per-host override
      bootfile: poap.py         # optional per-host override
```

Notes:

- `hostname` is the dhcpd host declaration label and the DHCP `host-name` option (option 12).
  When omitted, the MAC address is used as the label and no `host-name` is sent.
- Option 150 (`tftp-server-address`) is declared in the template because it is not a
  built-in ISC option; NX-OS POAP prefers it over option 66.
- `subnet` on a reservation is optional but must match a defined subnet name when set;
  it is only used to inherit the TFTP/bootfile values.
- DHCP relay must be configured on the upstream SVI (`ip dhcp relay address <staging-host>`)
  for subnets not directly attached to this host.
