# Deploy Cisco Nexus Backend Fabric

The procedures in this chapter deploy a high-speed backend (east-west) fabric in the Cisco AI POD solution, built using Cisco Cloud Scale Nexus switches in a 2-tier spine-leaf Clos topology. The fabric is deployed using the pre-defined AI/ML fabric templates in Cisco Nexus Dashboard and provides the lossless RoCEv2 transport for GPU-to-GPU communication across the AI POD compute nodes. GPU compute node onboarding to the fabric is covered in a later chapter.

The procedures will:

- Deploy a VXLAN EVPN fabric using Nexus Dashboard templates on spine and leaf switches in the fabric.
- Configure AI QoS and queuing policies to support lossless GPU-to-GPU RDMA connectivity.

## Assumptions and Prerequisites

Before implementing the procedures in this chapter, verify that the following prerequisites are met:

- An operational Cisco Nexus Dashboard cluster at the target release.
- All spine and leaf switches in the backend fabric are cabled in a 2-tier spine-leaf topology using the connectivity plan in [Table X]{custom-style="Highlight"}.
- Out-of-band management interfaces on all switches are configured with IP addressing, default gateways, valid administrator credentials and routing in place to ensure reachability from Nexus Dashboard.
- DNS and NTP services are operational and reachable from the switch management interfaces.
- If an upgrade is required, the target NX-OS software image (per the HW&SW compatibility matrix in [Table X]{custom-style="Highlight"}) should be uploaded and staged on an HTTP or NFS server. The server should be reachable from Nexus Dashboard, and the SHA-512 of the NX-OS image matches the digest published on cisco.com.
- IP reachability for the initial seed switch for automated fabric discovery.

## Setup Information

Use the setup information in this section to complete the deployment procedures later in this chapter. The procedures are for manual deployment and use the parameters in the Value column of the tables below.

::: {custom-style="Note"}
The Variable and Value columns match the key-value pairs used by automation. Ignore the Variable column for manual deployment.
:::

### Credentials

**Table 1. Credentials**

::: {colwidths="24,28,16,32"}

| Description | Variable | Value | Notes |
| ---------------------------- | --------------------------------------------------- | ------------------ | ------------------------------------------------------------------ |
| Nexus Dashboard administrator | `nd_admin_username` | `admin` | Used for all Web UI and REST API operations. |
| Nexus Dashboard password | `vault_nd_admin_password` | `<user_input>` | Stored in inventory vault. |
| Switch administrator username | `be_switch.username` | `admin` | Administrative account across all backend switches. |
| Switch administrator password | `vault_be_sp1_password` ... `vault_be_lf2_password` | `<user_input>` | Per-switch credential; stored in inventory vault for automation. |
| Fabric switch password | `vault_be_fabric_switch_password` | `<user_input>` | Stored in inventory vault; referenced during fabric discovery. |

:::

### Fabric-wide Parameters

**Table 2. Fabric-wide Setup Parameters**

::: {colwidths="22,26,20,32"}

| Description | Variable | Value | Notes |
| ---------------------------- | --------------------------------------------------- | ------------------ | ------------------------------------------------------------------ |
| Domain name | `aipod.domain_name` | `aipod.local` | Site domain across AI POD infrastructure. |
| DNS server 1 | `aipod.dns_servers[0]` | `192.0.2.53` | Primary DNS server. |
| DNS server 2 | `aipod.dns_servers[1]` | `192.0.2.54` | Secondary DNS server. |
| NTP server 1 | `aipod.ntp_servers[0]` | `198.51.100.124` | Primary NTP server. |
| NTP server 2 | `aipod.ntp_servers[1]` | `198.51.100.125` | Secondary NTP server. |
| Timezone | `aipod.timezone` | `America/New_York` |  |
| Fabric spec | `be_fabric_spec` | NA | Required for automation; ignore for manual. Parent structure for relative variable keys below; for example, `.name` is `be_fabric_spec.name`. |
| Fabric name | `.name` | `AIPOD-BE-Fabric` | Fabric Name in Nexus Dashboard. |
| Fabric template | `.fabric_template` | `Easy_Fabric_eBGP` | BGP EVPN fabric template. |
| Unified fabric type | `.unified_fabric_type` | `aimlVxlanEbgp` | Fabric type: VXLAN EVPN – eBGP. |
| BGP AS | `.bgp_as` | `65100` | BGP Autonomous System number. |
| BGP AS mode | `.bgp_as_mode` | `Multi-AS` | Spine and leaf switches allocate discrete AS numbers. |
| Fabric MTU | `.fabric_mtu` | `9216` | Jumbo frames enabled across all fabric interfaces. |
| Link-state routing | `.link_state_routing` | `ebgp` | External BGP underlay routing. |
| Underlay pool first octet | `.underlay_first_octet` | `20` (`20.0.0.0/16`) | First octet for automated underlay addressing. |
| Loopback 0 IP range | `.loopback0_range` | `20.2.0.0/22` | Switch router ID and BGP EVPN peering addresses. |
| Loopback 1 IP range | `.loopback1_range` | `20.3.0.0/22` | Switch VTEP / NVE overlay source IP addresses. |
| Underlay subnet range | `.subnet_range` | `20.4.0.0/16` | Point-to-point fabric link IP address pool. |
| Per-VRF loopback range | `.vrf_loopback_range` | `20.5.0.0/22` | EVPN tenant VRF loopback pool. |
| Replication mode | `.replication_mode` | `Multicast` | BGP EVPN multicast replication mode. |
| Bidirectional Forwarding Detection | `.bfd` | `true` | Fast sub-second link failure detection. |
| Precision Time Protocol (PTP) | `.ptp` | `true` (Domain ID 0, Loopback 0) | PTP fabric clocking enabled across Cloud Scale switches. |
| AI ML QoS policy | `.enable_ai_ml_qos_policy` | `true` | Enables AI fabric queuing and lossless RoCEv2 transport. |
| QoS policy name | `.qos_policy` | `AI_Fabric_QOS_400G` | Pre-defined Nexus Dashboard 400G AI QoS template. |
| Interface breakout | `.breakout_commands` | Native 400G | Native 400GbE ports; no port breakout required. |
| Real-time backup | `.real_time_backup` | `true` | Hourly configuration backup enabled in Nexus Dashboard. |
| Telemetry streaming | `.enable_telemetry` | `true` | In-band telemetry enabled for AI fabric monitoring. |
| Telemetry collection mode | `.telemetry_collection_mode` | `in_band` | In-band streaming collection. |
| Telemetry VRF | `.telemetry_vrf` | `Telemetry_VRF` | Dedicated VRF for telemetry transport. |
| Telemetry source interface | `.telemetry_source_interface` | `loopback0` | Router loopback interface for telemetry packets. |
| License tier | `.license_tier` | `Premier` | Enables flow telemetry and traffic analytics. |
| Fabric location | `.location` | `Example City, US` | Coordinates: 37.3382, -121.8863. |

:::

::: {custom-style="Note"}
For automation, ensure the BGP Autonomous System number does not conflict with any AS number already in use in the same Nexus Dashboard, or with any other BGP AS number used elsewhere in the enterprise.
:::

### Per-Switch Setup Parameters

**Table 3. Per-Switch Setup Parameters**

::: {colwidths="18,22,15,15,15,15"}

| Description | Variable | Spine 1 | Spine 2 | Leaf 1 | Leaf 2 |
| ----------------- | ------------------------- | ---------------------- | ---------------------- | ---------------------- | ---------------------- |
| Switch hostname | `be_switch.hostname` | `BE-SP1` | `BE-SP2` | `BE-LF1` | `BE-LF2` |
| Hardware model | `be_switch.model` | Cisco Nexus 9364D-GX2A | Cisco Nexus 9364D-GX2A | Cisco Nexus 9332D-GX2B | Cisco Nexus 9332D-GX2B |
| Switch role | `be_switch.role` | Spine | Spine | Leaf | Leaf |
| Management IP | `be_switch.mgmt_ip` | `198.18.0.61` | `198.18.0.62` | `198.18.0.63` | `198.18.0.64` |
| Default gateway | `be_switch.gateway` | `198.18.0.254` | `198.18.0.254` | `198.18.0.254` | `198.18.0.254` |

:::

## Pre-Deployment Verification

Before executing configuration workflows, verify that all software and cabling prerequisites are met:

- Verify that all spine-leaf links are up and that you can see LLDP neighbors on each port per the connectivity table in [Table X]{custom-style="Highlight"}.
- Verify switches are operating at target releases per [Table X]{custom-style="Highlight"} or follow procedures below for upgrading them.

## Deployment Steps

Complete the procedures below using the Setup Information provided earlier in this section.

### Procedure 1. Prerequisite: Upgrade Switch Firmware to Target Release Using Nexus Dashboard

1. Use a web browser to navigate to the Nexus Dashboard IP and log in with administrator credentials.
2. From the left navigation menu, choose **Admin > Software Management > Images**.
3. Verify that the target Cisco NX-OS image (see [Table X]{custom-style="Highlight"}) is uploaded and marked active.
4. Navigate to **Manage > Fabrics**, select the backend switches listed in Table 3, and click **Actions > Upgrade**.
5. Select the target NX-OS release (see [Table X]{custom-style="Highlight"}), verify upgrade criteria, and proceed with the upgrade.
6. Wait for all target switches to complete rebooting and confirm that status displays as **Healthy** with operating version matching the target release.

### Procedure 2. Pre-Deployment Verification of Cabling Connectivity and Firmware Baseline

1. Establish an SSH connection to the initial seed switch using the management IP in Table 3 and administrator credentials.
2. Verify the system software version by issuing the `show version` command. Confirm that the switch is operating at the target software release (see [Table X]{custom-style="Highlight"}):

    ```text
    switch# show version | include "system: version"
      system:    version 10.6(4)M
    ```

3. Confirm that the management interface (`mgmt0`) is configured with the IP address and gateway specified in Table 3:

    ```text
    switch# show ip interface mgmt0
    IP Interface Status for VRF "management"(2)
    mgmt0, Interface status: protocol-up/link-up/admin-up, iod: 2, iod-sub: 0
      IP address: 198.18.0.61, IP subnet: 198.18.0.0/24
    ```

4. Verify physical layer link status and reciprocal LLDP neighbor relationships across spine-leaf fabric links using the `show lldp neighbors` command per [Table X]{custom-style="Highlight"}:

    ```text
    switch# show lldp neighbors
    Capability codes:
      (R) Router, (B) Bridge, (T) Telephone, (C) DOCSIS Cable Device
      (W) WLAN Access Point, (P) Repeater, (S) Station, (O) Other
    Device ID            Local Intf      Hold-time  Capability  Port ID
    BE-LF1               Eth1/1          120        BR          Eth1/1
    BE-LF2               Eth1/2          120        BR          Eth1/1
    Total entries displayed: 2
    ```

5. Confirm that DNS and NTP network services from Table 2 are reachable from the management VRF:

    ```text
    switch# ping 192.0.2.53 vrf management count 3
    PING 192.0.2.53 (192.0.2.53): 56 data bytes
    64 bytes from 192.0.2.53: icmp_seq=0 ttl=60 time=0.812 ms
    64 bytes from 192.0.2.53: icmp_seq=1 ttl=60 time=0.584 ms
    64 bytes from 192.0.2.53: icmp_seq=2 ttl=60 time=0.572 ms

    switch# ping 198.51.100.124 vrf management count 3
    PING 198.51.100.124 (198.51.100.124): 56 data bytes
    64 bytes from 198.51.100.124: icmp_seq=0 ttl=60 time=0.438 ms
    ```

6. Repeat steps 1 through 5 for each switch listed in Table 3.

### Procedure 3. Deploy Backend Fabric Using Nexus Dashboard Template

1. Use a web browser to navigate to the Nexus Dashboard IP and log in with administrator credentials.
2. From the left navigation menu, choose **Manage > Fabrics**.
3. Click **Actions > Create Fabric**.
4. Select **Create a new LAN fabric** and click **Next**.
5. Select **AI > AI VXLAN EVPN** to configure a high-speed fabric for GPU-to-GPU connectivity, and click **Next**.
6. In the **General Settings** tab, configure the fabric name, BGP ASN, location, and license tier using the parameters in Table 2.
7. Click **Advanced Settings**. Configure the replication mode, PTP, and switch reload settings using the parameters from Table 2.
8. Navigate to the **Resources** tab and configure IP pools using the underlay subnet and loopback IP ranges from Table 2.
9. Review the fabric summary and click **Submit**.
10. Click **View fabric details** to confirm that the fabric dashboard renders with healthy status.

### Procedure 4. Discover and Add Spine and Leaf Switches to the Backend Fabric

1. From the **Manage > Fabrics** view, select the backend fabric created in the previous procedure.
2. Click **Actions > Add switches**.
3. In the switch discovery window, enter the **Seed IP** using the management IP of the first spine switch from Table 3, enter administrator credentials, set **Max Hops** to `1`, and leave **Preserve Config** unchecked.
4. Click **Discover Switches**.
5. Filter the discovered switch list to confirm all target switches listed in Table 3 are discovered.
6. Click **Add Switches**. When status changes to **Switch Added**, click **Close**.

### Procedure 5. Configure Switch Roles

1. In the fabric inventory view, select the **Switches** tab.
2. Select the spine switches listed in Table 3, and click **Actions > Set Role > Spine**.
3. Select the leaf switches listed in Table 3, and click **Actions > Set Role > Leaf**.
4. Confirm that all switches display native 400G interfaces without port breakouts.

### Procedure 6. Configure AI QoS Policies and RoCEv2 Network Intent

1. From the left navigation menu, choose **Manage > Template Library**.
2. Filter on `QOS` in the search bar.
3. Select the default AI QoS policy template and click **Actions > Duplicate template**.
4. In template properties, enter the QoS policy name from Table 2.
5. Under template content, configure queue bandwidth allocations and set PFC MTU to `9216`. Click **Save**.
6. Navigate to **Manage > Fabrics**, select the backend fabric, and choose **Actions > Edit Fabric Settings**.
7. In the **General** tab, select the QoS policy configured above for the AI QoS & Queueing Policy, and click **Save**.

### Procedure 7. Save, Recalculate, and Deploy Fabric Configuration

1. In the fabric view, click **Actions > Recalculate and deploy**.
2. Review the pending configuration generated for each spine and leaf switch by clicking the link in the **Pending Config** column.
3. Confirm that the generated configuration includes BGP EVPN underlay peering, multicast replication groups, PTP domain 0, and AI QoS priority flow control.
4. Click **Deploy All**.
5. When configuration deployment completes successfully, click **Close**.

### Procedure 8. Verify Backend Fabric Health and BGP EVPN Adjacencies

1. In the Nexus Dashboard dashboard, verify that the backend fabric reports **Healthy** with status **In-Sync** across all switches.
2. Establish an SSH session to a leaf switch from Table 3 and verify BGP EVPN peering:

    ```text
    switch# show bgp l2vpn evpn summary
    BGP summary information for VRF default, address family L2VPN EVPN
    BGP table version is 24, Local Router ID is 20.2.0.3
    Status: s-suppressed, x-deleted, S-stale, d-damped, h-history, *-valid, >-best
    Neighbor        V    AS    MsgRcvd    MsgSent   TblVer  InQ OutQ Up/Down  State/PfxRcd
    20.2.0.1        4 65100        452        455       24    0    0 03:14:22 8
    20.2.0.2        4 65100        451        454       24    0    0 03:14:20 8
    ```

3. Confirm that RoCEv2 priority flow control counters are registered and clean:

    ```text
    switch# show interface priority-flow-control
    =============================================================================
    Port               Mode Oper(Rx/Tx)  Pg-drop  No-drop   Send-pause Rcv-pause
    =============================================================================
    Eth1/1             On   On  /On      0        3         0          0
    Eth1/2             On   On  /On      0        3         0          0
    ```

4. Verify that no critical anomalies remain unacknowledged in the **Anomalies** dashboard.
