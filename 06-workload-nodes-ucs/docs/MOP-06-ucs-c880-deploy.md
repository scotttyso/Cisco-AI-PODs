# Deploy Cisco UCS C880A M8 Servers

The procedures in this chapter cover the initial setup of Cisco UCS C880A M8 rack servers, including firmware upgrades, to prepare them for operating system (OS) deployment. Operating system installation and OpenShift worker node onboarding are covered in subsequent chapters.

The procedures will:

- Perform initial server setup, including hostname, DNS, and Network Time Protocol (NTP).
- Configure console and administration settings, including Serial over LAN (SOL) and virtual KVM (vKVM) verification.
- Verify pre-upgrade hardware, sensors, and logs per [Cisco UCS C880A M8 Rack Server Getting Started Guide](https://www.cisco.com/c/en/us/products/collateral/computing/servers-unified-computing-systems/ucs-c-series-rack-servers/ucs-c880a-m8-rack-server-guide.html) recommendations.
- Upgrade firmware (BMC, BIOS, GPU, CPLD, and ERoT) using the Cisco Python Redfish upgrade utility.
- Upgrade host-level component firmware (BlueField-3 NIC, Intel X710-T2L OCP, Micron 9550 NVMe, and Cisco Boot-optimized M.2 RAID) using the Cisco Host Upgrade Utility (HUU).
- Configure host BIOS for bare metal AI workloads, including setting the BlueField-3 (BF3) adapters to NIC mode for host-managed LACP port-channeling on uplinks to the frontend fabric.

UCS C880 does not support Intersight claim. This chapter uses Cisco BMC, Redfish, and HUU for server setup and firmware deployment; Intersight claim is excluded from the C880 workflow.

## Assumptions and Prerequisites

Before implementing the procedures in this chapter, verify that the following prerequisites are met:

- Out-of-band management connectivity in place to the server's Cisco BMC 4.0 network interface.
- Server configured with valid administrator credentials. You will be prompted to change the password the first time you access the server via BMC.
- Cisco BMC management access via HTTPS (TCP 443) and SSH (TCP 22).
- Management workstation with Python 3 and OpenSSL 3.x packages installed for running firmware upgrade script, and network reachability to server for Redfish API access.
- Firmware packages obtained from Cisco Software Central. This includes the firmware bundle itself, upgrade script, Cisco HUU ISO and release notes.

## Setup Information

Use the setup information in this section to complete the deployment procedures later in this chapter. The procedures are for manual deployment using the parameters in the Value column.

::: {custom-style="Note"}
The Variable and Value columns match the key-value pairs used by automation. Ignore the Variable column for manual deployment.
:::

### Credentials

**Table 1. Credentials**

::: {colwidths="24,28,16,32"}

| Description                      | Variable                                                              | Value          | Notes                                                                  |
| -------------------------------- | --------------------------------------------------------------------- | -------------- | ---------------------------------------------------------------------- |
| Cisco BMC administrator username | `ucs.cimc.user`                                                       | `admin`        | Default administrative account.                                        |
| Cisco BMC administrator password | `vault_ucs_c880_1_cimc_password` ... `vault_ucs_c880_4_cimc_password` | `<user_input>` | One secret key per server; for automation, save it in inventory vault. |

:::

### Base Setup Parameters

**Table 2. Base Setup Parameters**

::: {colwidths="16,23,20,41"}

| Description          | Variable               | Value              | Notes                                                                                 |
| -------------------- | ---------------------- | ------------------ | ------------------------------------------------------------------------------------- |
| Domain name          | `aipod.domain_name`    | `aipod.local`      | Local domain suffix.                                                                  |
| DNS server 1         | `aipod.dns_servers[0]` | `192.0.2.53`      | Primary DNS server.                                                                   |
| DNS server 2         | `aipod.dns_servers[1]` | `192.0.2.54`      | Secondary DNS server.                                                                 |
| NTP server 1         | `aipod.ntp_servers[0]` | `198.51.100.124`    | Enter the first address in Primary NTP Server and the second in Secondary NTP Server. |
| NTP server 2         | `aipod.ntp_servers[1]` | `198.51.100.125`    | Enter the first address in Primary NTP Server and the second in Secondary NTP Server. |
| Timezone             | `aipod.timezone`       | `America/New_York` | Eastern Time (ET).                                                                    |
| SOL service          | `ucs_c880.sol_enabled` | `Enabled`          | Serial over LAN on SSH port 22.                                                       |

:::

### Per-Server Parameters

**Table 3. Per-Server Setup Parameters**

::: {colwidths="16,19,16,16,16,17"}

| Description     | Variable       | Server 1           | Server 2           | Server 3           | Server 4           |
| --------------- | -------------- | ------------------ | ------------------ | ------------------ | ------------------ |
| Hostname        | `ucs.hostname` | `AIPOD-UCS-C880-1` | `AIPOD-UCS-C880-2` | `AIPOD-UCS-C880-3` | `AIPOD-UCS-C880-4` |
| UCS BMC IP      | `ucs.cimc.ip`  | `198.18.0.81`      | `198.18.0.82`      | `198.18.0.83`      | `198.18.0.84`      |
| Subnet mask     | `ucs.cimc.netmask` | `255.255.255.0`    | `255.255.255.0`    | `255.255.255.0`    | `255.255.255.0`    |
| Default gateway | `ucs.cimc.gateway` | `198.18.0.254`     | `198.18.0.254`     | `198.18.0.254`     | `198.18.0.254`     |

:::

### Firmware Packages and Release Baselines

**Table 4. Firmware Packages and Release Baselines**

::: {colwidths="19,19,31,31"}

| Description              | Variable                    | Value                                     | Notes                                                   |
| ------------------------ | --------------------------- | ----------------------------------------- | ------------------------------------------------------- |
| Firmware bundle          | `ucs_c880.firmware.bundle`  | `ucs-c880a-m8-4.0.2.260009.tar.gz`        | BMC, BIOS, GPU, CPLD, and ERoT firmware bundle.         |
| Upgrade script           | `ucs_c880.firmware.script`  | `ucs-c880a-m8-upgrade-script-v1.2.tar.gz` | Cisco-provided Python Redfish upgrade utility.          |
| Host Upgrade Utility ISO | `ucs_c880.firmware.huu_iso` | `ucsc-880a-m8-huu-4.0.2.260022.iso`       | Bootable ISO with firmware for NICs and storage drives. |

:::

::: {custom-style="Note"}
Review the [Cisco Baseboard Management Controller 4.0 Release Notes](https://www.cisco.com/c/en/us/td/docs/unified_computing/ucs/release/notes/Cisco-BMC-Release-Notes/4-0-1/b_cisco-bmc-4-0-release-notes-release-4-0.html) for detailed component firmware baselines and release-specific guidance for the Cisco UCS C880A M8 server. When upgrading firmware, always select the option to update all components to ensure compatibility. Confirm the target component baselines against the HW&SW compatibility matrix in [Table X]{custom-style="Highlight"}.
:::

### Host BIOS Factory Defaults

**Table 5. Host BIOS Factory Defaults for UCS C880 M8 Server**

::: {colwidths="34,16,50"}

| BIOS Parameter / Token | Factory Default | Description |
| ---------------------- | --------------- | ----------- |
| Memory Mapped I/O Above 4GB (`STR_PCI_4G_PROMPT`) | `Enabled` | Allocates 64-bit PCI MMIO window above 4GB; required to map the 2.3 TB HBM3e Base Address Register (BAR) address space across all eight NVIDIA B300 SXM6 GPUs for GPUDirect RDMA. |
| Access Control Services (`NvidiaAcsEnable`) | `Disable` | Prevents peer-to-peer (P2P) PCIe traffic from routing through the CPU root complex, maintaining line-rate GPUDirect RDMA throughput. Cisco C880A M8 isolates this setting from virtualization controls and disables it by default. |
| Intel Virtualization Technology for Directed I/O (`ControlIommu`) | `Enable` | Enables I/O Memory Management Unit (IOMMU) translation, required for VFIO device passthrough and the OpenShift NVIDIA GPU and Network Operators. |
| Intel Virtualization Technology (`ProcessorVmxEnable`) | `Enable` | Hardware virtualization support for host container and virtualization orchestration. |
| PCIe Relaxed Ordering (`PcieRelaxedOrdering`, `P2pRelaxedOrdering`) | `Enable` | Permits PCIe switches to reorder independent data packets, improving streaming RDMA write bandwidth across PCIe switches. |
| PCIe Max Read Request Size (`PcieMaxReadRequestSize`) | `4096B` | Sets maximum read request payload sizing to 4096 bytes, matching the adapter's maximum supported TLP payload to optimize PCIe read throughput for streaming RDMA. |
| Single Root I/O Virtualization (`SriovSupport`) | `Enabled` | Enables hardware-assisted virtual function creation on PCIe adapters. |

:::

### Deferred BIOS and Kernel Settings

**Table 6. Deferred BIOS and Kernel Settings**

::: {colwidths="19,18,21,42"}

| Component / Parameter | Factory Default | Target Configuration | Operational Layer and Deployment Notes |
| --------------------- | --------------- | -------------------- | -------------------------------------- |
| PCIe Access Control Services (ACS) | `Disable` (`NvidiaAcsEnable`) | Verified `Disable` in BIOS | **Verified in BIOS.** Unlike platforms that force ACS on when virtualization is enabled, Cisco C880A M8 isolates ACS in BIOS. |
| Intel VT for Directed I/O (IOMMU / VT-d) | `Enable` (`ControlIommu`) | Verified `Enable` in BIOS | **Verified in BIOS.** Intel VT-d remains enabled in BIOS to support VFIO device assignment. |
| BlueField-3 Operating Mode | Active (DPU Mode) | `Disabled` (NIC Mode) | **Configured in UEFI Setup; verified after OS installation.** The internal Arm CPU offload engine is disabled so the host operating system manages the physical ports directly to enable LACP bonding to upstream frontend leaf switches. |
| Intel RDMA Kernel Module (`irdma`) | Active (in-box kernel driver) | `module_blacklist=irdma` | **Deferred to OpenShift deployment chapter.** Blacklisted on GPU worker nodes via OpenShift `MachineConfig` (`kernelArguments`) to prevent driver collision when the NVIDIA Network Operator loads DOCA drivers. |
| RPC RDMA Kernel Module (`rpcrdma`) | Inactive / default kernel module | Managed via DOCA `NicClusterPolicy` (`ENABLE_NFSRDMA=true`) | **Deferred to OpenShift deployment chapter.** [RE-CONFIRM DURING GDS TESTING with Everpure] Provides NFS-over-RDMA transport for GPUDirect Storage (GDS). Module loading and dependency lifecycle are orchestrated through the NVIDIA Network Operator DOCA container on OpenShift worker nodes. |

:::

## Deployment Workflow

The workflow below outlines the sequence for onboarding standalone Cisco UCS C880A M8 servers and establishing the certified firmware baseline prior to operating system deployment and OpenShift worker node onboarding.

**Figure 1. Cisco UCS C880A M8 Onboarding and Firmware Upgrade Workflow**

![The workflow begins with BMC management setup (hostname, DNS, NTP), enables SOL and verifies vKVM, validates system health against pre-upgrade checks, performs firmware updates using the upgrade script, updates host components via the Host Upgrade Utility (HUU), and verifies host BIOS and network adapter operating modes.](workflows/ucs-c880-deployment-workflow.png){width=6in}

## Deployment Steps

Complete the procedures below for each Cisco UCS C880A M8 server in the deployment using the parameters in the **Setup Information** tables.

::: {custom-style="Note"}
Screenshots provided in this section will be from one of the Cisco UCS C880A M8 servers in the validation testbed. The hostnames and IP addresses are unique but otherwise they are identically configured using the parameters provided in the Setup Information section.
:::

### Procedure 1. Configure Hostname, DNS and NTP

1. Use a web browser to navigate to the UCS BMC IP and log in with administrator credentials.
2. In the left navigation pane, choose **Settings**. Click on the **Network Settings** tile, followed by the **DNS Configuration** tile.
3. Scroll to **Host Name Setting** section and select the radio button for **Manual**. Fill in the new **Host Name** in the field below.
4. Scroll down to the **Domain Setting** section. Select the radio button for **Manual** and enter the **Domain Name** in the field provided.
5. Scroll down to **Domain Name Server Setting** section. Specify **DNS Server 1** and **DNS Server 2** IP addresses.
6. Click **Save**.
7. Click **OK** to the question in the pop-up window to restart BMC network services.
8. In the left navigation pane, choose **Settings**. Click on the **Date & Time** tile.
9. Scroll down and set the **Timezone** by selecting it from the drop-down list.
10. Verify **Automatic NTP Date & Time** is enabled. Enter the **Primary NTP Server** and **Secondary NTP Server** addresses from Table 2.
11. Click **Save**. Click **OK** to the question in the pop-up window.
12. Log back in and verify that the NTP synchronization status is good.

### Procedure 2. Enable Serial over LAN (SOL) and Verify Virtual KVM (vKVM)

1. In the left navigation pane, choose **Settings**. Click on the **Services** tile.
2. Locate the **SOL-over-SSH** service row.
3. Click on the pencil icon to the right to enable the service.
4. Select the **Active** checkbox and click **Save**.
5. Click **OK** to the question in the pop-up window.
6. Confirm the `solssh` row shows a status of **Active**.
7. Test SOL connectivity from the management workstation by establishing an SSH connection to the UCS BMC IP:

    ```bash
    ssh -p 22 admin@<UCS-BMC-IP>
    ```

::: {custom-style="Note"}
A web-based Serial over LAN console is also available directly from the BMC web interface by navigating to Remote Control and clicking Activate in the Serial Over LAN section.
:::

8. Navigate to **Remote Control** in the left navigation menu.
9. In the **H5Viewer** section, click **Launch H5Viewer** to launch vKVM.
10. Confirm that the HTML5 vKVM console opens cleanly, displays live host output (such as the UEFI Shell), and responds to keystrokes.
11. Close the test vKVM session.

### Procedure 3. Pre-Upgrade System Health and Hardware Verification

1. On the BMC Dashboard, confirm that the server power state is **On** and overall health indicators report healthy.
2. Choose **System Inventory > Processors and Memory** and verify:
  - Both CPU sockets are populated and enabled.
  - All 32 DIMM slots are enabled, reporting expected memory capacity.
3. Choose **GPU Information** in the left navigation pane and verify that all eight NVIDIA B300 SXM6 AC GPUs are enumerated with status operational.
4. Choose **Sensor Readings** and verify:
  - Zero critical threshold sensors are present.
  - Temperature sensors for CPUs and GPUs report within normal operating ranges.
  - All 12 Power Supply Units (PSUs) report present and redundant.
  - Core status sensors (`PECIReady`, `GPUFPGAReady`, `HMCReady`, and `BIOS_Done`) report asserted.
5. Choose **Logs > System Event Log (SEL)** and inspect recent entries:
  - Confirm that no active uncorrectable memory, bus, or thermal trip errors are logged.
  - If historical alerts exist, verify that matching deassertion events are present.

### Procedure 4. Upgrade Firmware using Upgrade Script

Use the Cisco-provided upgrade script to perform an automated Redfish-based upgrade of the BMC, BIOS, GPU baseboard, and ERoT components.

1. From a management workstation, extract the upgrade script package from Table 4:

    ```bash
    tar -xzf <upgrade-script>
    ```

2. Run discovery mode (`-D`) to inventory the running firmware versus the packaged bundle from Table 4 (substitute `<firmware-bundle>`, `<CIMC-admin-password>`, and `<UCS-BMC-IP>` with the values from Table 1, Table 3, and Table 4):

    ```bash
    python3 <upgrade-script-path>/ucs-c880a-m8-upgrade-v1.2.py \
      -B <firmware-bundle> \
      -U admin \
      -P <CIMC-admin-password> \
      -I <UCS-BMC-IP> \
      -D
    ```

3. Review the generated inventory table. Confirm that components with version differences (BMC, BIOS, GPU, ERoT) indicate **Update Required: Yes**, while matching CPLD components report **No**.
4. Execute the firmware upgrade (`-F`), substituting `<firmware-bundle>`, `<CIMC-admin-password>`, and `<UCS-BMC-IP>` with the values from Table 1, Table 3, and Table 4:

    ```bash
    python3 <upgrade-script-path>/ucs-c880a-m8-upgrade-v1.2.py \
      -B <firmware-bundle> \
      -U admin \
      -P <CIMC-admin-password> \
      -I <UCS-BMC-IP> \
      -F \
      --skip-power-cycle-confirmation
    ```

::: {custom-style="Note"}
When running the upgrade script manually, passing credentials with `-P` exposes the password in command arguments and local log files. In automated deployments, reference vault credentials rather than entering plaintext passwords on the command line. The operation initiates multiple host power cycles and BMC reboots; ensure no active workloads are running.
:::

5. Monitor the automated script execution until complete. The utility stages the images, coordinates host power cycles to flash components, and handles BMC reboots during ERoT activation.
6. The component upgrade process takes time as each component firmware image is staged and verified. Wait for the script to report `Update completed successfully`.
7. Re-run discovery mode (`-D`) to confirm all components are at the target versions in the bundle—see release notes.

### Procedure 5. Upgrade Host Components via Host Upgrade Utility (HUU)

Use this procedure to update the network adapters and storage devices using Cisco HUU.

1. Use a web browser to navigate to the UCS BMC IP and log in with administrator credentials.
2. Navigate to **Remote Control** in the left navigation menu.
3. In the **H5Viewer** section, click **Launch H5Viewer** to open the HTML5 vKVM console.
4. In the vKVM console, locate the **CD Image** section in the upper right, click **Browse File** to select the Host Upgrade Utility ISO image from Table 4, and click **Start Media**.
5. In the vKVM menu bar, choose **Hot Keys > Add Hot Keys** and configure an entry for **F7** so the boot menu shortcut is ready prior to rebooting.
6. In the vKVM menu bar, choose **Power > Force Restart** to reboot the server.

::: {custom-style="Note"}
A standard Power Cycle may not reliably exit an active UEFI shell session; use Force Restart to guarantee a full reboot into POST.
:::

7. During BIOS boot, when the Cisco splash screen appears (*"Press `<F7>` to enter Boot Menu"*), choose **Hot Keys > F7**. You should see a message saying 'Entering Boot Menu...'
8. In the blue boot selection menu, select **UEFI: CISCO Virtual CDROM0 1.00** and press Enter.

::: {custom-style="Note"}
After selecting the virtual CD, the screen remains black for several minutes while the virtual media buffers over the network and the byte counter next to **CD Image** in the top right increments. Boot progress and container extraction will display once initial blocks load.
:::

9. Wait while the Cisco Host Upgrade Utility initializes. This step takes several minutes before the graphical interface loads.
10. When the Cisco Host Upgrade Utility GUI loads, review the Cisco Software License Agreement and click **Accept**.
11. In the **Firmware Update** dashboard, review the detected adapters and storage controllers under **Components**, then click **Update** in the upper right.
12. In the **Update All** dialog, verify that **Power cycle to activate** is selected, then click **Update**.

::: {custom-style="Note"}
Component updates require several minutes each.
:::

13. Monitor firmware update progress. Wait for the blue progress bar at the bottom to reach 100%, then click **View Details**.
14. In the **Task 1 - Update & Activate** view, verify that each component under **Execution Flow** reports **Success**, then click the back arrow to return to **Tasks Summary**.
15. In the **Tasks Summary** view, verify that **Task 1 - Update & Activate** reports **State** as **Completed** and **Status** as **Ok**.
16. The server automatically power cycles to activate the firmware and reboots. During POST, the Cisco splash screen appears.
17. Following boot completion, the server enters the UEFI ready state (`Shell>`), confirming that the boot controller and NVMe drives are operational.

### Procedure 6. Verify and Configure Host BIOS and NIC Operating Modes

To prepare the Cisco UCS C880A M8 for bare metal AI workloads, verify the factory BIOS settings against Table 5 and apply the operational configurations in Table 6.

1. In the vKVM console, reboot or power on the server. During BIOS POST, press **DEL** or **ESC** on your keyboard (or choose **Hot Keys > Add Hot Keys** to configure and send the **DEL** or **ESC** keystroke) to enter the UEFI BIOS Setup utility.
2. Verify Processor, Virtualization, and Memory factory defaults against Table 5:
   - Navigate to **Advanced > Processor Configuration** and verify **Intel Virtualization Technology**, **VT for Directed I/O (VT-d)**, and **SR-IOV Support** are **Enabled**.
   - Navigate to **Advanced > PCI Subsystem Settings** and verify **Memory Mapped I/O Above 4GB** is **Enabled**, **PCIe Relaxed Ordering** is **Enabled**, **PCIe Max Read Request Size** is set to **4096B**, and **Access Control Services (ACS)** is **Disabled**.
3. Configure NVIDIA BlueField-3 Network Adapters into standard PCIe NIC Mode. This allows the host operating system to manage the network ports directly and form a LACP bond to connect to frontend leaf switches:
   - Navigate to **Advanced** and select the first **Nvidia Network Adapter** entry (identified by its MAC address).
   - Select **BlueField Internal Cpu Configuration**.
   - Set **Internal Cpu Offload Engine** to **Disabled**.
   - Press **ESC** to return to the **Advanced** menu and repeat this configuration for the second BlueField-3 adapter.

4. Press **F4** to save the configuration changes and reset the server.
5. Following reboot, verify that the host initializes cleanly to the UEFI shell or boot device selection menu.
