# Deploy Cisco Nexus Backend Fabric

The procedures in this chapter deploy a high-speed backend (east-west) fabric in the Cisco AI POD solution, built using Cisco Silicon One Nexus switches in a 2-tier spine-leaf Clos topology. The fabric is deployed using the pre-defined AI/ML fabric templates in Cisco Nexus Dashboard and provides the lossless RoCEv2 transport for GPU-to-GPU communication across the AI POD compute nodes. GPU compute node onboarding to the fabric is covered in a later chapter.

The procedures will:

- Configure breakout ports for 400GbE connectivity on the 800GbE switch ports interconnecting the spine-leaf switches.
- Deploy a VXLAN EVPN fabric using Nexus Dashboard templates on spine and leaf switches in the fabric.
- Customize default AI QoS and queuing policies to support lossless GPU-to-GPU RDMA connectivity.
- Deploy Bidirectional Forwarding Detection (BFD) for eBGP underlay.



## Assumptions and Prerequisites

Before implementing the procedures in this chapter, verify that the following prerequisites are met:

- An operational Cisco Nexus Dashboard cluster at the target release.
- All spine and leaf switches in the backend fabric are cabled in a 2-tier spine-leaf topology using the connectivity plan in [Table X]{custom-style="Highlight"}.
- Out-of-band management interfaces on all switches are configured with IP addressing, default gateways, a local administrator account, and routing in place to ensure reachability from Nexus Dashboard.
- DNS and NTP services are operational and reachable from the switch management interfaces.
- If an upgrade is required, the target NX-OS software image (per the HW&SW compatibility matrix in [Table X]{custom-style="Highlight"}) should be staged on an SCP/SFTP server, such as the AI POD automation node. This server should be reachable from Nexus Dashboard, and the SHA-512 of the NX-OS image matches the digest published on cisco.com.
- IP reachability for the initial seed switch for automated fabric discovery.
- If using breakouts for core connections, configure breakout before switches are added to the fabric so that spine-leaf interfaces are detected and configured properly. This configuration must also be done before the first deployment of fabric using **Recalculate and deploy** from Nexus Dashboard. More details in the Deployment Procedures section.



## Setup Information

Use the setup information below to complete the deployment procedures later in this chapter. The procedures are for manual deployment and use the parameters in the **Value** column of the tables below.

::: {custom-style="Note"}
The Variable and Value columns match the key-value pairs used by automation. Ignore the Variable column for manual deployment.
:::

### Credentials

**Table 1. Credentials**

::: {colwidths="24,28,16,32"}


| Description                    | Variable                          | Value          | Notes                                                                    |
| ------------------------------ | --------------------------------- | -------------- | ------------------------------------------------------------------------ |
| Nexus Dashboard username       | `nd_admin_username`               | `admin`        | Used for all Web UI and REST API operations.                             |
| Nexus Dashboard password       | `vault_nd_admin_password`         | `<user_input>` | Stored in inventory vault.                                               |
| Seed switch username           | `be_switch.username`              | `admin`        | Discovery seed switch username; also used for Set Default Credentials.   |
| Seed switch password           | `be_switch.pass_ref`              | `<user_input>` | Discovery seed switch password.                                          |
| Default Fabric switch password | `vault_be_fabric_switch_password` | `<user_input>` | Set Default Credentials password – used by ND to configure all switches. |


:::

### Fabric-wide Parameters

**Table 2. Fabric-wide Setup Parameters**

::: {colwidths="19,22,23,36"}


| Description                        | Variable               | Value                                               | Notes                                                                                                                                                                                                                                                                                                                                                                                                                    |
| ---------------------------------- | ---------------------- | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Fabric spec                        | `be_fabric_spec`       | NA                                                  | Ignore for manual. In automation, this is the parent object holding sub-parameters, for e.g., `be_fabric_spec.<var_name>`.                                                                                                                                                                                                                                                                                               |
| Fabric name                        | `.name`                | `AIPOD-BE-SG2-Fabric`                               | Fabric Name in Nexus Dashboard.                                                                                                                                                                                                                                                                                                                                                                                          |
| BGP AS                             | `.bgp_as`              | `65201`                                             | BGP Autonomous System number.                                                                                                                                                                                                                                                                                                                                                                                            |
| Fabric location                    | `.location`            | `Example City, US`                                       |                                                                                                                                                                                                                                                                                                                                                                                                                          |
| License tier                       | `.license_tier`        | `Premier`                                           | Other options: Essentials, Advantage.                                                                                                                                                                                                                                                                                                                                                                                    |
| QoS policy mode                    | `.qos_policy`          | `400G`                                              | Template default. Aligns with 2×400G breakout config on spine-leaf links.                                                                                                                                                                                                                                                                                                                                                |
| Loopback 0 IP range                | `.loopback0_range`     | `21.2.0.0/22`                                       | Router ID and BGP EVPN peering IPs.                                                                                                                                                                                                                                                                                                                                                                                      |
| Loopback 1 IP range                | `.loopback1_range`     | `21.3.0.0/22`                                       | Switch VTEP / NVE overlay source IP addresses.                                                                                                                                                                                                                                                                                                                                                                           |
| Underlay subnet range              | `.subnet_range`        | `21.4.0.0/16`                                       | Point-to-point fabric link IP address pool.                                                                                                                                                                                                                                                                                                                                                                              |
| Replication mode                   | `.replication_mode`    | `Ingress`                                           | For VXLAN BUM (Broadcast, Unknown-unicast, Multicast) underlay traffic; multicast replication is not supported on the Cisco Nexus 9364E-SG2 switches. See the [Cisco Nexus 9000 NX-OS VXLAN Configuration Guide, Release 10.6(x)](https://www.cisco.com/c/en/us/td/docs/dcn/nx-os/nexus9000/106x/configuration/vxlan/cisco-nexus-9000-series-nx-os-vxlan-configuration-guide-release-106x/m_configuring_vxlan_93x.html). |
| Bidirectional Forwarding Detection | `.bfd`                 | `true`                                              | Provides sub-second failure detection on the eBGP underlay.                                                                                                                                                                                                                                                                                                                                                              |
| BFD for BGP                        | `.bfd_for_bgp`       | `true`                                              | Enables BFD for the eBGP neighbors on the underlay.  |
| Interface breakout                 | `.breakout_commands`   | `interface breakout module 1 port 1-64 map 400g-2x` | Configured on all ports of all fabric switches.                                                                                                                                                                                                                                                                                                                                                                          |
| Scheduled fabric backup            | `.scheduled_backup`    | `true`                                              | Schedule for a set time or hourly.                                                                                                                                                                                                                                                                                                                                                                                       |
| AI QoS bandwidth remaining         | `.qos_bandwidth_remaining` | `10`                                                | Bandwidth remaining percent for the default queue in the User-defined AI QoS and queuing policy.  |




:::

::: {custom-style="Note"}
The BGP Autonomous System number should not overlap with any existing AS number already in use.
:::

::: {custom-style="Note"}
Flow Telemetry and Traffic Analytics require Precision Time Protocol (PTP). Currently, Nexus Dashboard supports this only on Cloud Scale fabrics and therefore not enabled on this fabric with Silicon One Cisco Nexus 9364E-SG2 switches. See [Editing Fabric Settings for an AI/ML Data Center VXLAN Fabric](https://www.cisco.com/c/en/us/td/docs/dcn/nd/4x/articles-431/editing-fabric-settings-ai_ml-data-center-vxlan.html) for more information.
:::

### Per-Switch Setup Parameters

**Table 3. Per-Switch Setup Parameters**

::: {colwidths="18,22,15,15,15,15"}


| Description     | Variable             | Spine 1        | Spine 2        | Leaf 1         | Leaf 2         |
| --------------- | -------------------- | -------------- | -------------- | -------------- | -------------- |
| Switch hostname | `be_switch.hostname` | `BE-SG2-SP1`   | `BE-SG2-SP2`   | `BE-SG2-LF1`   | `BE-SG2-LF2`   |
| Switch role     | `be_switch.role`     | `Spine`        | `Spine`        | `Leaf`         | `Leaf`         |
| Management IP   | `be_switch.mgmt_ip`  | `198.18.0.65`  | `198.18.0.66`  | `198.18.0.67`  | `198.18.0.68`  |
| Default gateway | `be_switch.gateway`  | `198.18.0.254` | `198.18.0.254` | `198.18.0.254` | `198.18.0.254` |


:::

### Firmware and Software Baseline

**Table 4. Firmware and Software Baseline**

::: {colwidths="19,18,27,36"}


| Description          | Variable          | Value                    | Notes                                                                                                                       |
| -------------------- | ----------------- | ------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| Software image spec  | `be_sg2_software` | NA                       | Ignore for manual. In automation, this is the parent object holding sub-parameters, for e.g., `be_sg2_software.<var_name>`. |
| Target NX-OS release | `.target_release` | `10.6(4)M`               | Target release per the HW&SW compatibility matrix in [Table X]{custom-style="Highlight"}.                                   |
| NX-OS image file     | `.image`          | `nxos64-s1.10.6.4.M.bin` | Cisco Silicon One image.                                                                                                    |
| Image source         | `.image_source`   | `SCP`                    | Upload local file or via SCP/SFTP from the AI POD automation node.                                                          |


:::

## Deployment Workflow

The high-level workflow below shows the end-to-end deployment path for the backend fabric built using Cisco Nexus 9364E-SG2 switches. It begins with deploying prerequisites and fabric creation, then discovers and onboards the spine and leaf switches, upgrades NX-OS only if required, applies the optional QoS and BFD policies, and ends when the backend fabric is healthy.

**Figure 1. Cisco Nexus 9364E-SG2 Backend Fabric Deployment Workflow**

![The workflow checks prerequisites, configures the 2×400G breakout, and creates the fabric with the Nexus Dashboard AI template; it then discovers and adds the spine and leaf switches, assigns roles and deploys, upgrades NX-OS with Procedure 4 only if required, optionally customizes AI QoS queueing and enables BFD for BGP, and verifies backend fabric health, connectivity, BGP EVPN, QoS, and BFD.](workflows/backend-sg2-deployment-workflow.png){width=6in}

## Deployment Steps

Complete the procedures below using the Setup Information provided earlier in this section.

### Deploy prerequisites: Configure 2×400G breakout on switches

1. On each Cisco Nexus 9364E-SG2 backend switch, configure 2×400GbE breakout on all 64 ports of Module 1 and save the configuration to startup-config before fabric discovery so that spine-leaf interfaces establish link connectivity at 400GbE and the breakout interfaces are configured correctly:

   ```text
   switch# configure terminal
   switch(config)# interface breakout module 1 port 1-64 map 400g-2x
   switch(config)# copy running-config startup-config
   ```

2. Confirm the breakout mapping using `show interface brief` or `show interface status`.



### Procedure 1. Create the Backend Fabric Using the Nexus Dashboard AI Template

1. Use a web browser to navigate to the Nexus Dashboard IP and log in with administrator credentials.
2. From the left navigation menu, choose **Manage > Fabrics**, then click **Actions > Create fabric**.

> *Screenshot omitted (lab capture): On the Manage > Fabrics page, Actions > Create fabric opens the fabric creation wizard.*

1. On the **Create/Onboard Fabric > Select a category** page, select **Create new LAN fabric**.

> *Screenshot omitted (lab capture): On the Select a category page, Create new LAN fabric is selected.*

1. Click **Next**. On the **Create/Onboard Fabric > Select a type** page, select **AI** > **AI VXLAN EVPN**.

> *Screenshot omitted (lab capture): In the Create Fabric wizard, the AI category is selected on the left and the AI VXLAN EVPN type on the right, provisioning a spine-leaf VXLAN EVPN fabric optimized for RoCEv2.*

1. Click **Next**. On the **Create/Onboard Fabric > Settings** page, configure the fabric **Name**, **Location**, **BGP ASN for spines**, and **License tier for fabric**.
2. Before clicking **Next**, switch to **Advanced** for **Configuration mode**.

> *Screenshot omitted (lab capture): On the Settings page, the fabric name, location, BGP ASN, and license tier are set.*

1. Click **Next**. On the **Create/Onboard Fabric > AI Settings** page, select **AI QoS & queuing policy** from the drop-down list.
2. (Optional) Enable **Dynamic load balancing** and corresponding settings to change from default Equal Cost Multipathing (ECMP).

> *Screenshot omitted (lab capture): On the AI Settings page, the AI QoS & queuing policy selection mode and dynamic load balancing are configured.*

1. Click **Next**. On the **Create/Onboard Fabric > Advanced settings** page, review each tab and configure **Underlay routing loopback IP range**, **Underlay subnet IP range**, **Replication mode**, **Underlay VTEP loopback IP range**, and **Configuration Backup**. Leave everything else as is.

::: {custom-style="Note"}

Changing the IP ranges is optional; it ensures unique subnets when there are multiple fabrics.

:::

> *Screenshot omitted (lab capture): On the Advanced settings page, each tab is reviewed and only the required values are set, leaving Nexus Dashboard defaults in place elsewhere.*

1. Click **Next**. On the **Create/Onboard Fabric > Summary** page, review the selections.

> *Screenshot omitted (lab capture): On the Summary page, the wizard recaps the fabric configuration before Submit.*

1. Click **Submit**.

> *Screenshot omitted (lab capture): The wizard reports that the fabric was created successfully, with an option to view the fabric details.*

1. Click **View fabric details** to view the deployed fabric settings.

> *Screenshot omitted (lab capture): On the fabric Overview page, the newly created backend fabric details and healthy anomaly status are displayed.*

1. Review and address any anomalies and advisories (see corresponding tabs) in this fabric.

### Procedure 2. Discover and Add Spine and Leaf Switches to the Backend Fabric

Nexus Dashboard discovers and onboards backend switches using out-of-band management (`mgmt0`) connectivity. The edge-facing fabric interfaces do not need to be up during discovery, but all core-facing links should ideally be connected correctly, with breakouts configured. Also, adding switches triggers a greenfield reload that erases all prior switch configuration except the switch hostname, management IP address, default gateway, and boot variables. Interface breakout configuration is also retained. The reload and configuration behaviour is determined by the **Add switches without reload** (default = disabled) template settings and **Preserve config** variable (greyed out/cannot be changed) in the **Add Switches/Discovery** page.

1. From the left navigation menu, choose **Manage > Fabrics**, then select and click on the fabric name to open the fabric view.
2. Navigate to **Inventory > Switches** tab, click **Actions > Add switches**.

> *Screenshot omitted (lab capture): On the fabric Inventory > Switches tab, Actions > Add switches starts switch onboarding.*

1. In the **Set default credentials** pop-up window, configure the following:
  - **Username**: switch administrator username
  - **Password**: Default Fabric switch password
  - Leave **Robot** unchecked

> *Screenshot omitted (lab capture): In the Set default credentials dialog, the switch administrator username and default fabric password are entered.*

::: {custom-style="Note"}
**Set default credentials** typically pops up only for first-time discovery of switches.
:::

1. Click **Save**.
2. In the **Add Switches** page, for **Switch addition mechanism**, select **Discover**, then configure the following:
  - **Seed IP**: management IP of the first spine switch
  - **Authentication/Privacy**: `SHA_AES`
  - **Username**: seed switch administrator username
  - **Password**: seed switch's password
  - Check **Set as individual device write credential** (sets the Discovery/Read credentials as the LAN/Write credential for individual devices)
  - **Max hops**: `2`
  - Note that **Preserve config** is greyed out (disabled by default and cannot be changed for AI fabrics)

> *Screenshot omitted (lab capture): On the Add Switches page, the Discover mechanism is configured with the seed switch IP, SNMP authentication, and credentials; Preserve config is greyed out and cannot be modified.*

1. Click **Actions > Discover switches**.
2. Click **Confirm** in the pop-up window.

> *Screenshot omitted (lab capture): Nexus Dashboard warns that all switch configuration except hostname, management IP, default gateway, and boot variables is removed after import because Preserve config is disabled.*

1. In the **Discovery results** list, select the spine and leaf switches.

> *Screenshot omitted (lab capture): The discovery results list the spine and leaf switches with model, serial number, and NX-OS version; the four backend switches are selected for addition to the fabric.*

1. Click **Add switches**. Wait until each selected switch shows **Status** of **Switch added**.

> *Screenshot omitted (lab capture): In the Add Switches page, the Discovery results table confirms each selected switch shows a Status of Switch added.*

1. Click **Close**. Navigate to the **Inventory > Switches** tab and confirm that all four backend switches report as **Healthy** and with a **Discovery status** of **Ok**.

::: {custom-style="Note"}
It is normal to see anomaly levels at Warning or Critical at this stage since configuration hasn't been deployed yet. Some switches may also need to be individually rediscovered to get an Ok status.
:::

> *Screenshot omitted (lab capture): On the Inventory > Switches tab, all four backend switches report Healthy with a Discovery status of Ok after they are added to the fabric.*

::: {custom-style="Note"}
Do not Recalculate and deploy fabric to the newly discovered switches at this stage — complete procedures for assigning switch roles first.
:::

### Procedure 3. Configure Switch Roles and Deploy Fabric

1. From the **Inventory > Switches** tab, confirm that the leaf switches already carry the **Leaf** role assigned at discovery. If any leaf shows a different role, select it, choose **Actions > Set role**, select **Leaf** in the dialog, and click **Select**.
2. Select the spine switches, choose **Actions > Set role**, select **Spine** in the dialog.

> *Screenshot omitted (lab capture): In the Set role dialog, the Spine role is applied to the selected spine switches.*

1. Click **Select**. Click **Ok** in the pop-up window.

> *Screenshot omitted (lab capture): Nexus Dashboard prompts that a Recalculate and deploy is required to complete the role change.*

1. Click on the top **Actions > Recalculate and deploy** to push the base fabric configuration — the BGP EVPN underlay, overlay, and other settings in the fabric template used.
2. Nexus Dashboard recalculates the intended configuration; the progress dialog reports **Recalculating config on switches** and **Generating configuration** for the spine and leaf roles.

> *Screenshot omitted (lab capture): After Recalculate and deploy, Nexus Dashboard saves the configuration and generates the spine and leaf role configuration.*

1. Click **Close** and/or wait for the configuration generation to complete.
2. From the **Deploy Configuration > Config preview** page, review the pending configuration by clicking on the **Pending config** and **Diff** column values for each switch.

> *Screenshot omitted (lab capture): On the Deploy Configuration Config preview page, the pending configuration and diff are shown for each switch.*

1. Confirm that the configured settings, including breakout interfaces are present. Click **Deploy all**.

> *Screenshot omitted (lab capture): On the Deploy progress page, each switch moves from Out of sync to Started to Success as the configuration is applied.*

1. Click **Close**. From the **Inventory > Switches** tab, confirm all switches show **Healthy** with **Configuration sync status** of **In sync**.

> *Screenshot omitted (lab capture): The fabric inventory shows all four backend switches Healthy with Configuration sync status of In sync after the configuration is deployed.*

1. Navigate to the **Anomalies** and **Advisories** tabs for the fabric. Review any anomalies or advisories, and address, acknowledge, or clear them before proceeding.



### Procedure 4. Upgrade Backend Switches to target release using Nexus Dashboard

1. Use a web browser to navigate to the Nexus Dashboard IP and log in with administrator credentials.
2. To upload an upgrade image to Nexus Dashboard, from the left navigation menu, choose **Manage > Fabric Software** and select the **NX-OS/IOS-XE** tab, followed by the **Images** tab. Click **Actions** and select **Upload image** from the drop-down menu.
3. In the **Upload image** pop-up window, select the radio button for **Import from SCP/SFTP**.
4. For **Remote server name**, select the AI POD automation node, or click **Create remote storage location** to configure and save a location. For the latter, in the **Create Remote Storage Location** window, select or specify the following. Leave everything else as is.
  - **Protocol**: SCP (or SFTP)
  - **Hostname/IP** and **Username** of the AI POD automation node
  - **Default path** to the image directory
  - **Authorization type**: Password
5. Click **Save**, then **Confirm** the host key.
6. Back in the **Upload new image** dialog, select the remote server from the drop-down list and set **File path** to the image file name, using a path relative to the one specified in the pre-configured remote storage location. Click **Save** and wait until the image shows **Present** on the **Images** tab.

> *Screenshot omitted (lab capture): On the Fabric Software Images tab, the target Cisco NX-OS image shows Present after the upload completes.*

1. To configure an update group to upgrade switches in groups, select the **Update groups** tab, click **Actions**, and select **Auto-generate groups**. In the **Auto-generate groups** dialog, select:
  - **Fabric**: select the name of the fabric
  - **Type**: `Even odd`

> *Screenshot omitted (lab capture): In the Auto-generate groups dialog, the fabric is selected and the Even odd type splits the spine and leaf switches into two update groups that upgrade in stages.*

1. Click **Save**. Nexus Dashboard creates an even and an odd update group, each containing half of the spine and leaf switches so that the switches upgrade in stages to maintain network stability.

> *Screenshot omitted (lab capture): Nexus Dashboard creates an even and an odd update group, each containing one spine and one leaf switch.*

1. For a given update group, click **Prepare** to open the **Prepare Update Group** wizard. On the **Group name and device selection** page, confirm the group name and member switches.

> *Screenshot omitted (lab capture): The Prepare Update Group wizard opens on Group name and device selection, showing the group name and its member spine and leaf switches.*

1. Click **Next**. On the **Version selection** page, choose the target Cisco Silicon One (`nxos64-s1`) image from the uploaded images list. Non-disruptive update is not supported for the switches in this fabric. However, this setting is changed only later in the procedure, during the install stage.

> *Screenshot omitted (lab capture): On the Version selection page, the target Cisco Silicon One (nxos64-s1) image is selected from the uploaded images.*

1. Click **Next**. On the **Update check selection** page, select **Basic** to run the standard checks.

> *Screenshot omitted (lab capture): On the Update check selection page, Basic is selected to run the standard checks.*

1. Click **Next**. Review the selections on the **Summary** page.

> *Screenshot omitted (lab capture): The Summary page recaps the group, version, and update checks before Stage and validate.*

1. Click **Stage and validate**, then click **Close**. Preparation continues in the background.

> *Screenshot omitted (lab capture): The Prepare Update Group wizard stages the update group in the background, showing per-switch preparation progress before the dialog is closed.*

> *Screenshot omitted (lab capture): On the Update groups tab, the update group shows Preparing update group while the staging operation runs in the background.*

1. On the **Update groups** tab, wait for **Prepare** to complete and **Install update** to become selectable.

> *Screenshot omitted (lab capture): On the Update groups tab, the prepared group shows Ready for update with the disruptive update type, and the Install update button is now selectable.*

1. Click **Install update**. In the **Install Update Group** wizard, verify the group name and member switches.

> *Screenshot omitted (lab capture): In the Install Update Group wizard, the group name and member switches are verified on the Group name and device selection page.*

1. Click **Next**. On the **Update options** page, select **Disruptive** and leave everything else as is.

> *Screenshot omitted (lab capture): On the Update options page, Nexus Dashboard flags the non-disruptive update as unsupported and recommends the disruptive update; maintenance-mode isolation is No, execution paradigm is Serial, and on failure is Pause.*

1. Click **Next**. On the **Update check selection** page, select **Run basic Pre-analysis and run Post-analysis**.

> *Screenshot omitted (lab capture): On the Update check selection page, Run basic Pre-analysis and run Post-analysis is selected.*

1. Click **Next**. On the **Pre-update report** page, wait for the pre-update report to generate.
2. Click **Next**. On the **Summary** page, wait until the **Pre-update report** status shows **Passed**.

> *Screenshot omitted (lab capture): On the Summary page, the pre-update report status shows Passed and the Install update button is selectable.*

1. Click **Install update**. Confirm the **Install Update Group** page shows per-switch install progress.

> *Screenshot omitted (lab capture): The update group installs in the background with per-switch progress shown; the update continues after the page is closed.*

1. Click **Close**. Installation continues in the background.
2. On the **Update groups** tab, confirm the group shows **Update in progress** until the upgrade completes.

> *Screenshot omitted (lab capture): On the Update groups tab, the group shows Update in progress with the install start time.*

1. Repeat steps 9-22 for the next update group so that all backend switches are upgraded.
2. Select the **History** tab and confirm that the **Validate**, **Snapshot**, and **Upgrade** operations report **Success** for each switch, and that each switch is operating at the target NX-OS release.



### Procedure 5. (Optional) Configure Custom AI QoS Policies

A default AI QoS policy is selected and deployed during fabric creation. To modify default QoS parameters, complete the procedures outlined below:

1. Navigate to **Manage > Fabrics**, select the fabric from the list and click on the fabric name.
2. From the fabric view, select **Actions > Edit Fabric Settings**.
3. In the **AI settings** tab, for **AI QoS & Queueing Policy**, select **User-defined** from the drop-down list and change the **Bandwidth remaining (%)** as shown.

> *Screenshot omitted (lab capture): On the fabric AI settings tab, the AI QoS & queuing policy selection mode is set to User-defined to apply the custom policy.*

4. Click **Save**. Go back to fabric view and click **Actions > Recalculate and deploy**.
5. On the **Deploy Configuration > Config preview** page, review the pending configuration changes.

> *Screenshot omitted (lab capture): On the Deploy Configuration Config preview page, all four backend switches show the pending QoS configuration before it is deployed.*

1. Click the **Pending config** value for a switch to confirm the updated QoS queuing policy and bandwidth-remaining percentages.

> *Screenshot omitted (lab capture): The pending configuration shows the updated QOS_EGRESS_PORT queuing policy with the custom bandwidth-remaining percentages.*

1. Click **Close** to go back to deployment view. Click **Deploy all**.
2. When all switches report a **Configuration sync status** of **Success**, click **Close**.



### Procedure 6. (Optional) Enable Bidirectional Forwarding Detection on the Underlay

BFD provides sub-second failure detection on the eBGP underlay; without it, eBGP falls back to the default hold timer of 180s. BFD is disabled by default in the template but can be enabled using the procedures below.

1. From the left navigation menu, select **Manage > Fabrics** and select the fabric from the list.
2. Click to open the fabric view. Select **Actions > Edit Fabric Settings > Fabric Management > Protocols** tab.
3. Locate the BFD settings and enable the following:
  - **Enable BFD** to enable the feature.
  - **Enable BFD for BGP** to enable the feature for BGP.

> *Screenshot omitted (lab capture): On the fabric Protocols tab, Enable BFD and Enable BFD for BGP are selected.*

1. Click **Save**.
5. Click **Got it** in the pop-up window.
6. Go back to fabric view and click **Actions > Recalculate and deploy**.
7. On the **Deploy Configuration > Config preview** page, review the pending configuration changes.

   ```text
   feature bfd
   router bgp 1002
     neighbor 21.2.0.1
       bfd
       exit
   …
   interface ethernet1/33/1
     priority-flow-control mode on
     service-policy type qos input QOS_CLASSIFICATION
     priority-flow-control watch-dog-interval on
     no switchport
     ip address 21.4.0.133/30
     description connected-to-BE-SG2-SP1-Ethernet1/17/1
     mtu 9216
     no ip redirects
     no shutdown
     no ipv6 redirects
   ```

::: {custom-style="Note"}
The `router bgp 1002` shown in the preview is the switch's local eBGP ASN assigned within the fabric; it is expected to differ from the fabric-level `.bgp_as` value and is not a misconfiguration.
:::

> *Screenshot omitted (lab capture): On the Deploy Configuration Config preview page, all four backend switches show the pending BFD configuration before it is deployed.*

1. Click **Deploy all**.
2. When all switches report a **Configuration sync status** of **Success**, click **Close**.



### Procedure 7. Verify Backend Fabric Health, Connectivity, and BGP EVPN Adjacencies

The backend switches are now managed by the fabric. Verify the fabric health as outlined below.

1. In the Nexus Dashboard fabric dashboard, confirm the backend fabric reports **Healthy** with status **In-Sync** across all switches.

> *Screenshot omitted (lab capture): The fabric Overview reports Healthy anomaly and advisory levels, Config-sync status In sync, and the AI VXLAN EVPN eBGP fabric with all four backend switches.*

1. From the **Connectivity > Interfaces** tab, confirm for each backend switch that:
  - it is running at the target software release (see [Table X]{custom-style="Highlight"})
  - its breakouts are correct, including interface **Operational status** and **Sync status**

> *Screenshot omitted (lab capture): On the Connectivity Interfaces tab, the backend switch interfaces are Admin and Operationally Up at 400G with a Sync status of In sync.*

1. From the fabric **Topology** view, confirm the spine-leaf cabling is up and operational across switches.

> *Screenshot omitted (lab capture): The fabric topology view shows the two spine and two leaf switches connected in a complete spine-leaf topology.*

1. From the **Connectivity > Links** tab, confirm the expected Link Layer Discovery Protocol (LLDP) neighbor relationships on each fabric link is correct.

> *Screenshot omitted (lab capture): On the Connectivity Links tab, each fabric link lists its spine-leaf endpoint pair, confirming the expected LLDP neighbor relationships.*

1. From the **Connectivity > Links** tab, under **Protocol view**, confirm the BGP EVPN control plane is established across the fabric, with the underlay eBGP neighbor relationships and the overlay EVPN adjacencies up for every spine-leaf pair.

> *Screenshot omitted (lab capture): On the Connectivity Links Protocol view, the BGP links between spine and leaf switches, including loopback peerings, report a Link state of Established.*

1. Confirm the AI QoS policy and RoCEv2 priority flow control are applied on the fabric interfaces.
2. If BFD was enabled in the optional BFD procedure, confirm the BFD sessions on the underlay are up.
3. Address/acknowledge/clear any critical anomalies in the **Anomalies** dashboard.
4. Address/acknowledge/clear any critical advisories in the **Advisories** dashboard.

