# Template Difference Analysis Report

Generated: 2026-11-16T09:37:35.040408

## Summary

- **Total Templates Analyzed**: 78
- **Templates with Gaps**: 10

## Detailed Findings

### policies/ethernet_network

- **Template Attributes**: 2
- **API Attributes**: 2
- **Match Ratio**: 50.00%

#### Missing in API (1)

- `VlanSettings`

#### Missing in Template (1)

- `Profiles`

### policies/fibre_channel_network

- **Template Attributes**: 1
- **API Attributes**: 2
- **Match Ratio**: 0.00%

#### Missing in API (1)

- `VsanSettings`

#### Missing in Template (2)

- `EnableTrunking`
- `Profiles`

### policies/switch_control

- **Template Attributes**: 13
- **API Attributes**: 14
- **Match Ratio**: 85.71%

#### Missing in API (1)

- `AesPrimaryKey`

#### Missing in Template (2)

- `IsAesPrimaryKeySet`
- `Profiles`

### policies/adapter_configuration

- **Template Attributes**: 1
- **API Attributes**: 1
- **Match Ratio**: 100.00%

### policies/auditd

- **Template Attributes**: 2
- **API Attributes**: 2
- **Match Ratio**: 100.00%

### policies/bios

- **Template Attributes**: 471
- **API Attributes**: 471
- **Match Ratio**: 100.00%

### policies/boot_order

- **Template Attributes**: 0
- **API Attributes**: 0
- **Match Ratio**: 0.00%

### policies/certificate_management

- **Template Attributes**: 1
- **API Attributes**: 1
- **Match Ratio**: 100.00%

### policies/device_connector

- **Template Attributes**: 1
- **API Attributes**: 1
- **Match Ratio**: 100.00%

### policies/drive_security

- **Template Attributes**: 2
- **API Attributes**: 2
- **Match Ratio**: 100.00%

### policies/ethernet_adapter

- **Template Attributes**: 17
- **API Attributes**: 17
- **Match Ratio**: 100.00%

### policies/ethernet_network_control

- **Template Attributes**: 6
- **API Attributes**: 6
- **Match Ratio**: 100.00%

### policies/ethernet_network_group

- **Template Attributes**: 1
- **API Attributes**: 1
- **Match Ratio**: 100.00%

### policies/ethernet_qos

- **Template Attributes**: 6
- **API Attributes**: 6
- **Match Ratio**: 100.00%

### policies/fc_zone

- **Template Attributes**: 2
- **API Attributes**: 2
- **Match Ratio**: 100.00%

### policies/fibre_channel_adapter

- **Template Attributes**: 12
- **API Attributes**: 12
- **Match Ratio**: 100.00%

### policies/fibre_channel_qos

- **Template Attributes**: 5
- **API Attributes**: 5
- **Match Ratio**: 100.00%

### policies/firmware

- **Template Attributes**: 3
- **API Attributes**: 3
- **Match Ratio**: 100.00%

### policies/flow_control

- **Template Attributes**: 3
- **API Attributes**: 3
- **Match Ratio**: 100.00%

### policies/id_mapping

- **Template Attributes**: 1
- **API Attributes**: 1
- **Match Ratio**: 100.00%

### policies/imc_access

- **Template Attributes**: 7
- **API Attributes**: 7
- **Match Ratio**: 100.00%

### policies/ipmi_over_lan

- **Template Attributes**: 3
- **API Attributes**: 3
- **Match Ratio**: 100.00%

### policies/iscsi_adapter

- **Template Attributes**: 3
- **API Attributes**: 3
- **Match Ratio**: 100.00%

### policies/iscsi_boot

- **Template Attributes**: 14
- **API Attributes**: 14
- **Match Ratio**: 100.00%

### policies/iscsi_static_target

- **Template Attributes**: 5
- **API Attributes**: 5
- **Match Ratio**: 100.00%

### policies/lan_connectivity

- **Template Attributes**: 6
- **API Attributes**: 6
- **Match Ratio**: 100.00%

### policies/lan_connectivity.vnics

- **Template Attributes**: 19
- **API Attributes**: 19
- **Match Ratio**: 100.00%

### policies/lan_connectivity.vnics_from_template

- **Template Attributes**: 9
- **API Attributes**: 9
- **Match Ratio**: 100.00%

### policies/ldap

- **Template Attributes**: 5
- **API Attributes**: 8
- **Match Ratio**: 62.50%

#### Missing in Template (3)

- `Groups`
- `Profiles`
- `Providers`

### policies/ldap.ldap_groups

- **Template Attributes**: 4
- **API Attributes**: 4
- **Match Ratio**: 100.00%

### policies/ldap.ldap_servers

- **Template Attributes**: 4
- **API Attributes**: 4
- **Match Ratio**: 100.00%

### policies/link_aggregation

- **Template Attributes**: 2
- **API Attributes**: 2
- **Match Ratio**: 100.00%

### policies/link_control

- **Template Attributes**: 1
- **API Attributes**: 1
- **Match Ratio**: 100.00%

### policies/local_user

- **Template Attributes**: 1
- **API Attributes**: 1
- **Match Ratio**: 100.00%

### policies/local_user.users

- **Template Attributes**: 0
- **API Attributes**: 0
- **Match Ratio**: 0.00%

### policies/local_user.users_roles

- **Template Attributes**: 5
- **API Attributes**: 5
- **Match Ratio**: 100.00%

### policies/mac_sec

- **Template Attributes**: 0
- **API Attributes**: 0
- **Match Ratio**: 0.00%

### policies/memory

- **Template Attributes**: 1
- **API Attributes**: 1
- **Match Ratio**: 100.00%

### policies/multicast

- **Template Attributes**: 5
- **API Attributes**: 5
- **Match Ratio**: 100.00%

### policies/netflow_configuration

- **Template Attributes**: 0
- **API Attributes**: 0
- **Match Ratio**: 0.00%

### policies/network_connectivity

- **Template Attributes**: 9
- **API Attributes**: 9
- **Match Ratio**: 100.00%

### policies/ntp

- **Template Attributes**: 4
- **API Attributes**: 4
- **Match Ratio**: 100.00%

### policies/persistent_memory

- **Template Attributes**: 0
- **API Attributes**: 0
- **Match Ratio**: 0.00%

### policies/port

- **Template Attributes**: 1
- **API Attributes**: 2
- **Match Ratio**: 50.00%

#### Missing in Template (1)

- `Profiles`

### policies/port.port_channel_appliances

- **Template Attributes**: 11
- **API Attributes**: 11
- **Match Ratio**: 100.00%

### policies/port.port_channel_ethernet_uplinks

- **Template Attributes**: 11
- **API Attributes**: 11
- **Match Ratio**: 100.00%

### policies/port.port_channel_fc_uplinks

- **Template Attributes**: 7
- **API Attributes**: 7
- **Match Ratio**: 100.00%

### policies/port.port_channel_fcoe_uplinks

- **Template Attributes**: 8
- **API Attributes**: 8
- **Match Ratio**: 100.00%

### policies/port.port_modes

- **Template Attributes**: 5
- **API Attributes**: 5
- **Match Ratio**: 100.00%

### policies/port.port_role_appliances

- **Template Attributes**: 11
- **API Attributes**: 11
- **Match Ratio**: 100.00%

### policies/port.port_role_ethernet_uplinks

- **Template Attributes**: 11
- **API Attributes**: 11
- **Match Ratio**: 100.00%

### policies/port.port_role_fc_storage

- **Template Attributes**: 7
- **API Attributes**: 7
- **Match Ratio**: 100.00%

### policies/port.port_role_fc_uplinks

- **Template Attributes**: 8
- **API Attributes**: 8
- **Match Ratio**: 100.00%

### policies/port.port_role_fcoe_uplinks

- **Template Attributes**: 8
- **API Attributes**: 8
- **Match Ratio**: 100.00%

### policies/port.port_role_servers

- **Template Attributes**: 9
- **API Attributes**: 9
- **Match Ratio**: 100.00%

### policies/power

- **Template Attributes**: 9
- **API Attributes**: 9
- **Match Ratio**: 100.00%

### policies/san_connectivity

- **Template Attributes**: 5
- **API Attributes**: 5
- **Match Ratio**: 100.00%

### policies/san_connectivity.vhbas

- **Template Attributes**: 13
- **API Attributes**: 13
- **Match Ratio**: 100.00%

### policies/san_connectivity.vhbas_from_template

- **Template Attributes**: 10
- **API Attributes**: 10
- **Match Ratio**: 100.00%

### policies/scrub

- **Template Attributes**: 1
- **API Attributes**: 1
- **Match Ratio**: 100.00%

### policies/sd_card

- **Template Attributes**: 1
- **API Attributes**: 1
- **Match Ratio**: 100.00%

### policies/serial_over_lan

- **Template Attributes**: 4
- **API Attributes**: 4
- **Match Ratio**: 100.00%

### policies/server_pool_qualification

- **Template Attributes**: 2
- **API Attributes**: 2
- **Match Ratio**: 100.00%

### policies/smtp

- **Template Attributes**: 11
- **API Attributes**: 11
- **Match Ratio**: 100.00%

### policies/snmp

- **Template Attributes**: 12
- **API Attributes**: 12
- **Match Ratio**: 100.00%

### policies/ssh

- **Template Attributes**: 3
- **API Attributes**: 3
- **Match Ratio**: 100.00%

### policies/storage.drive_groups

- **Template Attributes**: 5
- **API Attributes**: 5
- **Match Ratio**: 100.00%

### policies/storage

- **Template Attributes**: 10
- **API Attributes**: 12
- **Match Ratio**: 83.33%

#### Missing in Template (2)

- `DriveGroup`
- `Profiles`

### policies/syslog

- **Template Attributes**: 2
- **API Attributes**: 2
- **Match Ratio**: 100.00%

### policies/system_qos

- **Template Attributes**: 3
- **API Attributes**: 4
- **Match Ratio**: 75.00%

#### Missing in Template (1)

- `Profiles`

### policies/thermal

- **Template Attributes**: 1
- **API Attributes**: 1
- **Match Ratio**: 100.00%

### policies/virtual_kvm

- **Template Attributes**: 6
- **API Attributes**: 6
- **Match Ratio**: 100.00%

### policies/virtual_media

- **Template Attributes**: 4
- **API Attributes**: 4
- **Match Ratio**: 100.00%

### policies/vlan

- **Template Attributes**: 1
- **API Attributes**: 2
- **Match Ratio**: 50.00%

#### Missing in Template (1)

- `Profiles`

### policies/vlan.vlans

- **Template Attributes**: 10
- **API Attributes**: 10
- **Match Ratio**: 100.00%

### policies/vsan

- **Template Attributes**: 1
- **API Attributes**: 2
- **Match Ratio**: 50.00%

#### Missing in Template (1)

- `Profiles`

### policies/vsan.vsans

- **Template Attributes**: 6
- **API Attributes**: 6
- **Match Ratio**: 100.00%

### policies/pcie_connectivity

- **Template Attributes**: 1
- **API Attributes**: 2
- **Match Ratio**: 50.00%

#### Missing in Template (1)

- `Profiles`

