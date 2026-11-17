# BIOS Policy Templates Reference

This document describes each BIOS template available in `intersight.policies.bios.templates`,
listing all BIOS tokens configured by that template along with a brief description of what each token controls.

## Table of Contents

- [AnalyticalDatabaseSystems-M6-Intel](#analyticaldatabasesystems-m6-intel)
- [AnalyticalDatabaseSystems-M7-Intel](#analyticaldatabasesystems-m7-intel)
- [Analytics-M8-AMD](#analytics-m8-amd)
- [Analytics-M8-Intel](#analytics-m8-intel)
- [AnalyticsDatabaseSystems-M5-Intel](#analyticsdatabasesystems-m5-intel)
- [AzureStack-M6-Intel](#azurestack-m6-intel)
- [AzureStack-M7-Intel](#azurestack-m7-intel)
- [CPUInference-M8-AMD](#cpuinference-m8-amd)
- [CPUInference-M8-Intel](#cpuinference-m8-intel)
- [CPUIntensive-M6-Intel](#cpuintensive-m6-intel)
- [CPUIntensive-M7-Intel](#cpuintensive-m7-intel)
- [CPUIntensive-M8-AMD](#cpuintensive-m8-amd)
- [CPUIntensive-M8-Intel](#cpuintensive-m8-intel)
- [ComputationIntensive-M6-AMD](#computationintensive-m6-amd)
- [DataAnalytics-M6-Intel](#dataanalytics-m6-intel)
- [DataAnalytics-M7-Intel](#dataanalytics-m7-intel)
- [EdgeAI-M8-AMD](#edgeai-m8-amd)
- [EdgeAI-M8-Intel](#edgeai-m8-intel)
- [EnergyEfficiency-M5-Intel](#energyefficiency-m5-intel)
- [EnergyEfficiency-M6-AMD](#energyefficiency-m6-amd)
- [EnergyEfficiency-M6-Intel](#energyefficiency-m6-intel)
- [EnergyEfficiency-M8-AMD](#energyefficiency-m8-amd)
- [EnergyEfficiency-M8-Intel](#energyefficiency-m8-intel)
- [EnergyEfficient-M7-Intel](#energyefficient-m7-intel)
- [GPUInference-M8-AMD](#gpuinference-m8-amd)
- [GPUInference-M8-Intel](#gpuinference-m8-intel)
- [GPUTraining-M8-AMD](#gputraining-m8-amd)
- [GPUTraining-M8-Intel](#gputraining-m8-intel)
- [HPC-M8-AMD](#hpc-m8-amd)
- [HPC-M8-Intel](#hpc-m8-intel)
- [HighPerformanceComputing-M5-Intel](#highperformancecomputing-m5-intel)
- [HighPerformanceComputing-M6-AMD](#highperformancecomputing-m6-amd)
- [HighPerformanceComputing-M6-Intel](#highperformancecomputing-m6-intel)
- [HighPerformanceComputing-M7-Intel](#highperformancecomputing-m7-intel)
- [IOIntensive-M6-AMD](#iointensive-m6-amd)
- [IOIntensive-M6-Intel](#iointensive-m6-intel)
- [IOIntensive-M8-AMD](#iointensive-m8-amd)
- [JavaApplicationServer-M5-Intel](#javaapplicationserver-m5-intel)
- [LowLatency-M5-Intel](#lowlatency-m5-intel)
- [LowLatency-M6-AMD](#lowlatency-m6-amd)
- [LowLatency-M6-Intel](#lowlatency-m6-intel)
- [LowLatency-M7-Intel](#lowlatency-m7-intel)
- [LowLatency-M8-AMD](#lowlatency-m8-amd)
- [LowLatency-M8-Intel](#lowlatency-m8-intel)
- [M5-amd-virtual](#m5-amd-virtual)
- [M5-intel-virtual](#m5-intel-virtual)
- [M6-amd-virtual](#m6-amd-virtual)
- [M6-intel-virtual](#m6-intel-virtual)
- [MLPerf-Inference-C885A-M8-AMD](#mlperf-inference-c885a-m8-amd)
- [MaximumPerformance-M5-Intel](#maximumperformance-m5-intel)
- [OnlineTransactionProcessing-M5-Intel](#onlinetransactionprocessing-m5-intel)
- [RDBMS-M8-AMD](#rdbms-m8-amd)
- [RDBMS-M8-Intel](#rdbms-m8-intel)
- [RelationalDatabaseSystems-M6-Intel](#relationaldatabasesystems-m6-intel)
- [RelationalDatabaseSystems-M7-Intel](#relationaldatabasesystems-m7-intel)
- [SystemDefault](#systemdefault)
- [UnifiedEdgeBios](#unifiededgebios)
- [VDI-M6-AMD](#vdi-m6-amd)
- [Virtualization-M5-Intel](#virtualization-m5-intel)
- [Virtualization-M6-AMD](#virtualization-m6-amd)
- [Virtualization-M6-Intel](#virtualization-m6-intel)
- [Virtualization-M7-Intel](#virtualization-m7-intel)
- [Virtualization-M8-AMD](#virtualization-m8-amd)
- [Virtualization-M8-Intel](#virtualization-m8-intel)
- [tpm](#tpm)
- [tpm_disabled](#tpm_disabled)

---

## AnalyticalDatabaseSystems-M6-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `cpu_perf_enhancement` | `Auto` | Enables Enhanced CPU Performance mode, applying additional microarchitecture optimizations for throughput |
| `energy_efficient_turbo` | `enabled` | Enables Intel Energy Efficient Turbo, which limits maximum turbo frequency to balance performance and power consumption |
| `intel_virtualization_technology` | `disabled` | Enables Intel VT-x hardware virtualization extensions required by hypervisors for guest VM isolation |
| `intel_vt_for_directed_io` | `disabled` | Enables Intel VT-d (Virtualization Technology for Directed I/O), providing IOMMU support for PCIe device assignment to V |
| `memory_refresh_rate` | `1x Refresh` | Sets the DRAM refresh rate (1x or 2x) to balance power savings and memory reliability at elevated temperatures |
| `patrol_scrub` | `disabled` | Enables background patrol scrubbing of DRAM to proactively detect and correct ECC errors before they accumulate |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `processor_c6report` | `enabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |
| `work_load_config` | `Balanced` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |

[⬆ Back to Top](#table-of-contents)

---

## AnalyticalDatabaseSystems-M7-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `intel_virtualization_technology` | `disabled` | Enables Intel VT-x hardware virtualization extensions required by hypervisors for guest VM isolation |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `processor_c6report` | `enabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |
| `work_load_config` | `Balanced` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |

[⬆ Back to Top](#table-of-contents)

---

## Analytics-M8-AMD

| BIOS Key | Value | Description |
|---|---|---|
| `cbs_cmn_apbdis` | `1` | Disables the Automatic Power Budget management to give software full control over power limits |
| `cbs_cmn_apbdis_df_pstate_rs` | `0` | Controls APBDIS interaction with Data Fabric P-states on Rome/Milan platforms |
| `cbs_cmn_cpu_cpb` | `Auto` | Controls Core Performance Boost (AMD's Turbo), allowing cores to run above base clock when thermal headroom allows |
| `cbs_cmn_cpu_global_cstate_ctrl` | `Auto` | Enables or disables global CPU C-states, controlling whether the processor can enter deep power-saving states |
| `cbs_cmn_cpu_l1stream_hw_prefetcher` | `Auto` | Enables or disables the L1 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_cpu_l2stream_hw_prefetcher` | `Auto` | Enables or disables the L2 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_determinism_slider` | `Auto` | Sets the performance-vs-power determinism trade-off; Performance maximizes throughput, Power maximizes efficiency |
| `cbs_cmn_efficiency_mode_en_rs` | `High Performance Mode` | Enhanced Efficiency Mode control for Genoa/Bergamo, supporting High Performance and Efficiency mode profiles |
| `cbs_cmn_gnb_nb_iommu` | `Auto` | Enables the IOMMU in the northbridge/GNB for DMA isolation and SR-IOV support |
| `cbs_cmn_gnb_smu_df_cstates` | `Auto` | Controls Data Fabric C-states; disabling prevents the fabric from entering low-power states, reducing GPU/memory access latency |
| `cbs_cmn_gnb_smucppc` | `enabled` | Enables Collaborative Processor Performance Control (CPPC) via the SMU for OS-driven frequency scaling |
| `cbs_cpu_smt_ctrl` | `disabled` | Enables or disables Simultaneous Multi-Threading (SMT) on AMD processors |
| `cbs_df_cmn4link_max_xgmi_speed` | `Auto` | Sets the maximum xGMI link speed for 4-link configurations |
| `cbs_df_cmn_acpi_srat_l3numa` | `disabled` | Reports AMD L3 cache slices as separate NUMA domains in the ACPI SRAT table for OS topology awareness |
| `cbs_df_cmn_dram_nps` | `Auto` | Sets NUMA Nodes Per Socket (NPS) to control how DRAM is presented as NUMA domains; NPS1=single domain, NPS4=four domains per socket |
| `cbs_df_cmn_mem_intlv_control` | `Auto` | Controls the memory interleave granularity for AMD platforms |
| `cpu_perf_enhancement` | `Disabled` | Enables Enhanced CPU Performance mode, applying additional microarchitecture optimizations for throughput |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |

[⬆ Back to Top](#table-of-contents)

---

## Analytics-M8-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `cpu_perf_enhancement` | `Auto` | Enables Enhanced CPU Performance mode, applying additional microarchitecture optimizations for throughput |
| `cpu_performance` | `enterprise` | Sets the CPU performance profile (enterprise, high-throughput, HPC) controlling prefetcher, turbo, and bandwidth setting |
| `epp_profile` | `Performance` | Sets the default EPP profile (Performance, Balanced Performance, Balanced Power, Power) used for hardware-guided P-state |
| `intel_virtualization_technology` | `disabled` | Enables Intel VT-x hardware virtualization extensions required by hypervisors for guest VM isolation |
| `latency_optimized_mode` | `enabled` | Enables latency-optimized memory mode on platforms that support it, reducing worst-case memory access time |
| `llc_alloc` | `disabled` | Controls Intel LLC (Last Level Cache) dead-line allocation, determining whether lines with no future reuse are placed in |
| `llc_prefetch` | `disabled` | Enables LLC prefetching from L2 to L3 cache to improve data availability for memory-bandwidth-intensive workloads |
| `patrol_scrub` | `disabled` | Enables background patrol scrubbing of DRAM to proactively detect and correct ECC errors before they accumulate |
| `pwr_perf_tuning` | `bios` | Controls whether BIOS, OS, or PECI manages power/performance tuning bias |
| `select_memory_ras_configuration` | `adddc-sparing` | Selects the memory RAS configuration (JBOD, Mirror, Lockstep, Sparing) for fault tolerance |
| `snc` | `enabled` | Enables Intel Sub-NUMA Clustering (SNC2 or SNC4), splitting the LLC and memory into sub-NUMA domains to reduce average m |

[⬆ Back to Top](#table-of-contents)

---

## AnalyticsDatabaseSystems-M5-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `cpu_power_management` | `custom` | Sets the overall CPU power management policy (performance, energy-efficient, custom) controlling P-state and C-state beh |
| `intel_vt_for_directed_io` | `disabled` | Enables Intel VT-d (Virtualization Technology for Directed I/O), providing IOMMU support for PCIe device assignment to V |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `processor_c1e` | `disabled` | Enables processor C1E (Enhanced Halt State) to reduce voltage and frequency when cores are halted |
| `processor_c6report` | `disabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |

[⬆ Back to Top](#table-of-contents)

---

## AzureStack-M6-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `adjacent_cache_line_prefetch` | `enabled` | Controls whether the CPU prefetches the adjacent cache line alongside the requested line, improving sequential workload  |
| `autonumous_cstate_enable` | `disabled` | Enables the CPU's autonomous C-state feature, allowing hardware to decide when to transition cores to low-power states |
| `boot_performance_mode` | `Max Performance` | Selects the CPU performance state used during the boot process before the OS takes control |
| `c1auto_demotion` | `enabled` | Allows the processor to automatically demote C3/C6/C7 requests to C1, reducing exit latency for lightly loaded cores |
| `c1auto_un_demotion` | `enabled` | Allows the processor to automatically un-demote previously demoted C-state requests when workload increases |
| `cmci_enable` | `enabled` | Enables Corrected Machine Check Interrupt (CMCI) so the OS is notified of corrected hardware errors |
| `config_tdp_level` | `Normal` | Sets the cTDP level (Normal, Level 1, Level 2) to run the processor at a lower or higher TDP envelope |
| `core_multi_processing` | `all` | Sets the number of active cores per processor, allowing partial core disabling for licensing or power reasons |
| `cpu_energy_performance` | `balanced-performance` | Sets the CPU energy/performance bias hint that the OS and hardware use to balance power consumption versus throughput |
| `cpu_pa_limit` | `enabled` | Limits the CPU physical address space to 46 bits for compatibility with legacy hypervisors or security requirements |
| `cpu_perf_enhancement` | `Disabled` | Enables Enhanced CPU Performance mode, applying additional microarchitecture optimizations for throughput |
| `cpu_performance` | `custom` | Sets the CPU performance profile (enterprise, high-throughput, HPC) controlling prefetcher, turbo, and bandwidth setting |
| `dma_ctrl_opt_in` | `enabled` | Enables kernel DMA protection opt-in flag, allowing the OS to enable IOMMU-based DMA isolation for Thunderbolt and PCIe |
| `enable_mktme` | `disabled` | Enables Intel Multi-Key Total Memory Encryption (MK-TME) for per-VM memory encryption with unique keys |
| `enable_sgx` | `disabled` | Enables Intel Software Guard Extensions (SGX) for hardware-based trusted execution enclave support |
| `enable_tme` | `enabled` | Enables Intel Total Memory Encryption (TME) to transparently encrypt all data written to DRAM |
| `energy_efficient_turbo` | `disabled` | Enables Intel Energy Efficient Turbo, which limits maximum turbo frequency to balance performance and power consumption |
| `enhanced_intel_speed_step_tech` | `enabled` | Enables Intel Enhanced SpeedStep Technology (EIST), allowing dynamic voltage and frequency scaling based on workload |
| `epoch_update` | `Manual User Defined Owner EPOCHs` | Controls how SGX Owner EPOCH values are updated; used to invalidate sealed SGX data for security |
| `epp_profile` | `Balanced Performance` | Sets the default EPP profile (Performance, Balanced Performance, Balanced Power, Power) used for hardware-guided P-state |
| `hardware_prefetch` | `enabled` | Enables the hardware prefetcher in the DCU to speculatively fetch cache lines based on observed access patterns |
| `hwpm_enable` | `Disabled` | Enables Intel Hardware P-state Management (HWPM) so the hardware controls P-state selection autonomously without OS inte |
| `intel_dynamic_speed_select` | `disabled` | Enables Intel Dynamic Speed Select Technology, allowing different cores to run at different base frequencies |
| `intel_hyper_threading_tech` | `enabled` | Enables Intel Hyper-Threading Technology, presenting each physical core as two logical threads to the OS |
| `intel_speed_select` | `Base` | Selects the Intel Speed Select configuration that determines which core group runs at the highest turbo frequency |
| `intel_turbo_boost_tech` | `enabled` | Enables Intel Turbo Boost Technology, allowing cores to run above the rated base clock frequency when thermal and power  |
| `intel_virtualization_technology` | `enabled` | Enables Intel VT-x hardware virtualization extensions required by hypervisors for guest VM isolation |
| `intel_vt_for_directed_io` | `enabled` | Enables Intel VT-d (Virtualization Technology for Directed I/O), providing IOMMU support for PCIe device assignment to V |
| `intel_vtd_coherency_support` | `disabled` | Enables Intel VT-d hardware queue invalidation with coherency support for improved IOMMU performance |
| `intel_vtdats_support` | `enabled` | Enables Intel VT-d Address Translation Services (ATS) for PCIe devices to cache IOMMU mappings locally |
| `ip_prefetch` | `enabled` | Enables the Intel DCU IP (Instruction Pointer) prefetcher for code-access pattern prediction |
| `ipv4http` | `disabled` | Enables IPv4 HTTP boot support in the UEFI network stack |
| `ipv4pxe` | `enabled` | Enables IPv4 PXE (Preboot Execution Environment) network boot support |
| `ipv6http` | `disabled` | Enables IPv6 HTTP boot support in the UEFI network stack |
| `ipv6pxe` | `enabled` | Enables IPv6 PXE network boot support |
| `kti_prefetch` | `enabled` | Enables Intel KTI (UPI) prefetch to preload data from remote NUMA nodes across the inter-socket link, reducing remote me |
| `llc_alloc` | `enabled` | Controls Intel LLC (Last Level Cache) dead-line allocation, determining whether lines with no future reuse are placed in |
| `llc_prefetch` | `enabled` | Enables LLC prefetching from L2 to L3 cache to improve data availability for memory-bandwidth-intensive workloads |
| `package_cstate_limit` | `C0 C1 State` | Sets the maximum C-state the processor package is allowed to enter; restricting to C0/C1 prevents deep sleep for low-lat |
| `patrol_scrub` | `enabled` | Enables background patrol scrubbing of DRAM to proactively detect and correct ECC errors before they accumulate |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `pop_support` | `disabled` | Enables Power-On Password protection requiring a password before the system can boot |
| `processor_c1e` | `disabled` | Enables processor C1E (Enhanced Halt State) to reduce voltage and frequency when cores are halted |
| `pstate_coord_type` | `HW ALL` | Sets the P-state coordination type between OS and hardware (HW_ALL, SW_ALL, SW_ANY) for multi-core frequency scaling |
| `pwr_perf_tuning` | `os` | Controls whether BIOS, OS, or PECI manages power/performance tuning bias |
| `qpi_link_frequency` | `auto` | Sets the Intel QPI/UPI inter-socket link frequency |
| `qpi_link_speed` | `Auto` | Sets the Intel QPI/UPI link speed for inter-socket communication |
| `sgx_auto_registration_agent` | `disabled` | Enables the SGX automatic multi-package registration agent for platforms with multiple processor packages |
| `sgx_epoch0` | `0` | The default value is `platform-default` |
| `sgx_epoch1` | `0` | The default value is `platform-default` |
| `sgx_factory_reset` | `disabled` | Performs an SGX factory reset, clearing all SGX provisioning data and sealed storage |
| `sgx_le_pub_key_hash0` | `0` | The default value is `platform-default` |
| `sgx_le_pub_key_hash1` | `0` | The default value is `platform-default` |
| `sgx_le_pub_key_hash2` | `0` | The default value is `platform-default` |
| `sgx_le_pub_key_hash3` | `0` | The default value is `platform-default` |
| `sgx_le_wr` | `enabled` | Enables writing the SGX Launch Enclave public key hash to the LE hash MSRs |
| `sgx_package_info_in_band_access` | `disabled` | Enables in-band access to SGX package information for multi-package platform management |
| `sgx_qos` | `enabled` | Enables SGX Quality of Service to reserve LLC capacity for SGX enclave pages |
| `sha256pcr_bank` | `enabled` | Enables the SHA-256 PCR bank in the TPM for secure boot measurements |
| `sha384pcr_bank` | `enabled` | Enables the SHA-384 PCR bank in the TPM for higher-security measured boot |
| `snc` | `disabled` | Enables Intel Sub-NUMA Clustering (SNC2 or SNC4), splitting the LLC and memory into sub-NUMA domains to reduce average m |
| `streamer_prefetch` | `enabled` | Enables the Intel DCU streamer prefetcher, which detects forward sequential access patterns and prefetches into L1 cache |
| `tpm_control` | `enabled` | Enables or disables the Trusted Platform Module (TPM) security chip |
| `tpm_pending_operation` | `None` | Sets a pending TPM operation (None or TpmClear) to be performed on the next boot |
| `tpm_ppi_required` | `enabled` | Controls whether physical presence confirmation is required for TPM operations |
| `tpm_support` | `enabled` | Enables Security Device (TPM) support, making the TPM visible to the OS and UEFI Secure Boot |
| `txt_support` | `enabled` | Enables Intel Trusted Execution Technology (TXT/TPM), providing hardware-based measured launch environment for server at |
| `ufs_disable` | `enabled` | Disables Intel Uncore Frequency Scaling, locking the uncore (LLC, memory controller) at a fixed frequency for determinis |
| `upi_link_enablement` | `Auto` | Sets the number of active Intel UPI (Ultra Path Interconnect) links between sockets (1, 2, 3, Auto) |
| `upi_power_management` | `disabled` | Enables Intel UPI link power management to reduce idle power consumption on inter-socket links |
| `virtual_numa` | `disabled` | Enables virtual NUMA topology presentation to VMs for improved guest NUMA-aware scheduling |
| `vmd_enable` | `disabled` | Enables Intel VMD (Volume Management Device), required for hot-plug NVMe support in PCIe slots behind a VMD controller |
| `work_load_config` | `I/O Sensitive` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |
| `x2apic_opt_out` | `disabled` | Sets the x2APIC opt-out flag, preventing the OS from enabling x2APIC mode even if the hardware supports it |
| `xpt_prefetch` | `Auto` | Enables Intel XPT (Cross Package Transfer) prefetch to speculatively fetch data across NUMA domains for remote memory ac |
| `xpt_remote_prefetch` | `Auto` | Enables Intel XPT remote prefetch specifically for cross-socket remote memory access patterns |

[⬆ Back to Top](#table-of-contents)
---

## AzureStack-M7-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `adjacent_cache_line_prefetch` | `enabled` | Controls whether the CPU prefetches the adjacent cache line alongside the requested line, improving sequential workload  |
| `autonumous_cstate_enable` | `disabled` | Enables the CPU's autonomous C-state feature, allowing hardware to decide when to transition cores to low-power states |
| `boot_performance_mode` | `Max Performance` | Selects the CPU performance state used during the boot process before the OS takes control |
| `c1auto_demotion` | `enabled` | Allows the processor to automatically demote C3/C6/C7 requests to C1, reducing exit latency for lightly loaded cores |
| `c1auto_un_demotion` | `enabled` | Allows the processor to automatically un-demote previously demoted C-state requests when workload increases |
| `cmci_enable` | `enabled` | Enables Corrected Machine Check Interrupt (CMCI) so the OS is notified of corrected hardware errors |
| `config_tdp_level` | `Normal` | Sets the cTDP level (Normal, Level 1, Level 2) to run the processor at a lower or higher TDP envelope |
| `core_multi_processing` | `all` | Sets the number of active cores per processor, allowing partial core disabling for licensing or power reasons |
| `cpu_energy_performance` | `balanced-performance` | Sets the CPU energy/performance bias hint that the OS and hardware use to balance power consumption versus throughput |
| `cpu_pa_limit` | `enabled` | Limits the CPU physical address space to 46 bits for compatibility with legacy hypervisors or security requirements |
| `cpu_perf_enhancement` | `Disabled` | Enables Enhanced CPU Performance mode, applying additional microarchitecture optimizations for throughput |
| `cpu_performance` | `custom` | Sets the CPU performance profile (enterprise, high-throughput, HPC) controlling prefetcher, turbo, and bandwidth setting |
| `dma_ctrl_opt_in` | `enabled` | Enables kernel DMA protection opt-in flag, allowing the OS to enable IOMMU-based DMA isolation for Thunderbolt and PCIe |
| `enable_mktme` | `disabled` | Enables Intel Multi-Key Total Memory Encryption (MK-TME) for per-VM memory encryption with unique keys |
| `enable_sgx` | `disabled` | Enables Intel Software Guard Extensions (SGX) for hardware-based trusted execution enclave support |
| `enable_tme` | `enabled` | Enables Intel Total Memory Encryption (TME) to transparently encrypt all data written to DRAM |
| `energy_efficient_turbo` | `disabled` | Enables Intel Energy Efficient Turbo, which limits maximum turbo frequency to balance performance and power consumption |
| `enhanced_intel_speed_step_tech` | `enabled` | Enables Intel Enhanced SpeedStep Technology (EIST), allowing dynamic voltage and frequency scaling based on workload |
| `epoch_update` | `Manual User Defined Owner EPOCHs` | Controls how SGX Owner EPOCH values are updated; used to invalidate sealed SGX data for security |
| `epp_profile` | `Balanced Performance` | Sets the default EPP profile (Performance, Balanced Performance, Balanced Power, Power) used for hardware-guided P-state |
| `hardware_prefetch` | `enabled` | Enables the hardware prefetcher in the DCU to speculatively fetch cache lines based on observed access patterns |
| `hwpm_enable` | `Disabled` | Enables Intel Hardware P-state Management (HWPM) so the hardware controls P-state selection autonomously without OS inte |
| `intel_dynamic_speed_select` | `disabled` | Enables Intel Dynamic Speed Select Technology, allowing different cores to run at different base frequencies |
| `intel_hyper_threading_tech` | `enabled` | Enables Intel Hyper-Threading Technology, presenting each physical core as two logical threads to the OS |
| `intel_speed_select` | `Base` | Selects the Intel Speed Select configuration that determines which core group runs at the highest turbo frequency |
| `intel_turbo_boost_tech` | `enabled` | Enables Intel Turbo Boost Technology, allowing cores to run above the rated base clock frequency when thermal and power  |
| `intel_virtualization_technology` | `enabled` | Enables Intel VT-x hardware virtualization extensions required by hypervisors for guest VM isolation |
| `intel_vt_for_directed_io` | `enabled` | Enables Intel VT-d (Virtualization Technology for Directed I/O), providing IOMMU support for PCIe device assignment to V |
| `intel_vtd_coherency_support` | `disabled` | Enables Intel VT-d hardware queue invalidation with coherency support for improved IOMMU performance |
| `intel_vtdats_support` | `enabled` | Enables Intel VT-d Address Translation Services (ATS) for PCIe devices to cache IOMMU mappings locally |
| `ip_prefetch` | `enabled` | Enables the Intel DCU IP (Instruction Pointer) prefetcher for code-access pattern prediction |
| `ipv4http` | `disabled` | Enables IPv4 HTTP boot support in the UEFI network stack |
| `ipv4pxe` | `enabled` | Enables IPv4 PXE (Preboot Execution Environment) network boot support |
| `ipv6http` | `disabled` | Enables IPv6 HTTP boot support in the UEFI network stack |
| `ipv6pxe` | `enabled` | Enables IPv6 PXE network boot support |
| `kti_prefetch` | `enabled` | Enables Intel KTI (UPI) prefetch to preload data from remote NUMA nodes across the inter-socket link, reducing remote me |
| `llc_alloc` | `enabled` | Controls Intel LLC (Last Level Cache) dead-line allocation, determining whether lines with no future reuse are placed in |
| `llc_prefetch` | `enabled` | Enables LLC prefetching from L2 to L3 cache to improve data availability for memory-bandwidth-intensive workloads |
| `package_cstate_limit` | `C0 C1 State` | Sets the maximum C-state the processor package is allowed to enter; restricting to C0/C1 prevents deep sleep for low-lat |
| `patrol_scrub` | `enabled` | Enables background patrol scrubbing of DRAM to proactively detect and correct ECC errors before they accumulate |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `pop_support` | `disabled` | Enables Power-On Password protection requiring a password before the system can boot |
| `processor_c1e` | `disabled` | Enables processor C1E (Enhanced Halt State) to reduce voltage and frequency when cores are halted |
| `pstate_coord_type` | `HW ALL` | Sets the P-state coordination type between OS and hardware (HW_ALL, SW_ALL, SW_ANY) for multi-core frequency scaling |
| `pwr_perf_tuning` | `os` | Controls whether BIOS, OS, or PECI manages power/performance tuning bias |
| `qpi_link_frequency` | `auto` | Sets the Intel QPI/UPI inter-socket link frequency |
| `qpi_link_speed` | `Auto` | Sets the Intel QPI/UPI link speed for inter-socket communication |
| `sgx_auto_registration_agent` | `disabled` | Enables the SGX automatic multi-package registration agent for platforms with multiple processor packages |
| `sgx_epoch0` | `0` | The default value is `platform-default` |
| `sgx_epoch1` | `0` | The default value is `platform-default` |
| `sgx_factory_reset` | `disabled` | Performs an SGX factory reset, clearing all SGX provisioning data and sealed storage |
| `sgx_le_pub_key_hash0` | `0` | The default value is `platform-default` |
| `sgx_le_pub_key_hash1` | `0` | The default value is `platform-default` |
| `sgx_le_pub_key_hash2` | `0` | The default value is `platform-default` |
| `sgx_le_pub_key_hash3` | `0` | The default value is `platform-default` |
| `sgx_le_wr` | `enabled` | Enables writing the SGX Launch Enclave public key hash to the LE hash MSRs |
| `sgx_package_info_in_band_access` | `disabled` | Enables in-band access to SGX package information for multi-package platform management |
| `sgx_qos` | `enabled` | Enables SGX Quality of Service to reserve LLC capacity for SGX enclave pages |
| `sha256pcr_bank` | `enabled` | Enables the SHA-256 PCR bank in the TPM for secure boot measurements |
| `sha384pcr_bank` | `enabled` | Enables the SHA-384 PCR bank in the TPM for higher-security measured boot |
| `snc` | `disabled` | Enables Intel Sub-NUMA Clustering (SNC2 or SNC4), splitting the LLC and memory into sub-NUMA domains to reduce average m |
| `streamer_prefetch` | `enabled` | Enables the Intel DCU streamer prefetcher, which detects forward sequential access patterns and prefetches into L1 cache |
| `tpm_control` | `enabled` | Enables or disables the Trusted Platform Module (TPM) security chip |
| `tpm_pending_operation` | `None` | Sets a pending TPM operation (None or TpmClear) to be performed on the next boot |
| `tpm_ppi_required` | `enabled` | Controls whether physical presence confirmation is required for TPM operations |
| `tpm_support` | `enabled` | Enables Security Device (TPM) support, making the TPM visible to the OS and UEFI Secure Boot |
| `txt_support` | `enabled` | Enables Intel Trusted Execution Technology (TXT/TPM), providing hardware-based measured launch environment for server at |
| `ufs_disable` | `enabled` | Disables Intel Uncore Frequency Scaling, locking the uncore (LLC, memory controller) at a fixed frequency for determinis |
| `upi_link_enablement` | `Auto` | Sets the number of active Intel UPI (Ultra Path Interconnect) links between sockets (1, 2, 3, Auto) |
| `upi_power_management` | `disabled` | Enables Intel UPI link power management to reduce idle power consumption on inter-socket links |
| `virtual_numa` | `disabled` | Enables virtual NUMA topology presentation to VMs for improved guest NUMA-aware scheduling |
| `vmd_enable` | `disabled` | Enables Intel VMD (Volume Management Device), required for hot-plug NVMe support in PCIe slots behind a VMD controller |
| `work_load_config` | `I/O Sensitive` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |
| `x2apic_opt_out` | `disabled` | Sets the x2APIC opt-out flag, preventing the OS from enabling x2APIC mode even if the hardware supports it |
| `xpt_prefetch` | `Auto` | Enables Intel XPT (Cross Package Transfer) prefetch to speculatively fetch data across NUMA domains for remote memory ac |
| `xpt_remote_prefetch` | `Auto` | Enables Intel XPT remote prefetch specifically for cross-socket remote memory access patterns |

[⬆ Back to Top](#table-of-contents)
---

## CPUInference-M8-AMD

| BIOS Key | Value | Description |
|---|---|---|
| `cbs_cmn_cpu_cpb` | `Auto` | Controls Core Performance Boost (AMD's Turbo), allowing cores to run above base clock when thermal headroom allows |
| `cbs_cmn_determinism_slider` | `Performance` | Sets the performance-vs-power determinism trade-off; Performance maximizes throughput, Power maximizes efficiency |
| `cbs_cmn_efficiency_mode_en_rs` | `High Performance Mode` | Enhanced Efficiency Mode control for Genoa/Bergamo, supporting High Performance and Efficiency mode profiles |
| `cbs_cmn_gnb_smu_df_cstates` | `Auto` | Controls Data Fabric C-states; disabling prevents the fabric from entering low-power states, reducing GPU/memory access latency |
| `cbs_df_cmn_acpi_srat_l3numa` | `enabled` | Reports AMD L3 cache slices as separate NUMA domains in the ACPI SRAT table for OS topology awareness |
| `cpu_energy_performance` | `performance` | Sets the CPU energy/performance bias hint that the OS and hardware use to balance power consumption versus throughput |
| `cpu_performance` | `high-throughput` | Sets the CPU performance profile (enterprise, high-throughput, HPC) controlling prefetcher, turbo, and bandwidth setting |
| `cpu_power_management` | `performance` | Sets the overall CPU power management policy (performance, energy-efficient, custom) controlling P-state and C-state beh |
| `llc_prefetch` | `enabled` | Enables LLC prefetching from L2 to L3 cache to improve data availability for memory-bandwidth-intensive workloads |

[⬆ Back to Top](#table-of-contents)
---

## CPUInference-M8-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `cpu_energy_performance` | `performance` | Sets the CPU energy/performance bias hint that the OS and hardware use to balance power consumption versus throughput |
| `cpu_performance` | `high-throughput` | Sets the CPU performance profile (enterprise, high-throughput, HPC) controlling prefetcher, turbo, and bandwidth setting |
| `cpu_power_management` | `performance` | Sets the overall CPU power management policy (performance, energy-efficient, custom) controlling P-state and C-state beh |
| `hwpm_enable` | `HWPM Native Mode` | Enables Intel Hardware P-state Management (HWPM) so the hardware controls P-state selection autonomously without OS inte |
| `intel_turbo_boost_tech` | `enabled` | Enables Intel Turbo Boost Technology, allowing cores to run above the rated base clock frequency when thermal and power  |
| `llc_prefetch` | `enabled` | Enables LLC prefetching from L2 to L3 cache to improve data availability for memory-bandwidth-intensive workloads |
| `numa_optimized` | `enabled` | Enables NUMA optimization in the BIOS, ensuring memory is allocated to the NUMA node closest to the requesting CPU |
| `xpt_prefetch` | `enabled` | Enables Intel XPT (Cross Package Transfer) prefetch to speculatively fetch data across NUMA domains for remote memory ac |

[⬆ Back to Top](#table-of-contents)
---

## CPUIntensive-M6-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `adjacent_cache_line_prefetch` | `disabled` | Controls whether the CPU prefetches the adjacent cache line alongside the requested line, improving sequential workload  |
| `cpu_perf_enhancement` | `Auto` | Enables Enhanced CPU Performance mode, applying additional microarchitecture optimizations for throughput |
| `kti_prefetch` | `enabled` | Enables Intel KTI (UPI) prefetch to preload data from remote NUMA nodes across the inter-socket link, reducing remote me |
| `llc_alloc` | `disabled` | Controls Intel LLC (Last Level Cache) dead-line allocation, determining whether lines with no future reuse are placed in |
| `llc_prefetch` | `disabled` | Enables LLC prefetching from L2 to L3 cache to improve data availability for memory-bandwidth-intensive workloads |
| `memory_refresh_rate` | `1x Refresh` | Sets the DRAM refresh rate (1x or 2x) to balance power savings and memory reliability at elevated temperatures |
| `patrol_scrub` | `disabled` | Enables background patrol scrubbing of DRAM to proactively detect and correct ECC errors before they accumulate |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `processor_c1e` | `enabled` | Enables processor C1E (Enhanced Halt State) to reduce voltage and frequency when cores are halted |
| `processor_c6report` | `enabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |
| `snc` | `enabled` | Enables Intel Sub-NUMA Clustering (SNC2 or SNC4), splitting the LLC and memory into sub-NUMA domains to reduce average m |
| `streamer_prefetch` | `disabled` | Enables the Intel DCU streamer prefetcher, which detects forward sequential access patterns and prefetches into L1 cache |
| `upi_link_enablement` | `1` | Sets the number of active Intel UPI (Ultra Path Interconnect) links between sockets (1, 2, 3, Auto) |
| `upi_power_management` | `enabled` | Enables Intel UPI link power management to reduce idle power consumption on inter-socket links |
| `work_load_config` | `Balanced` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |
| `xpt_prefetch` | `enabled` | Enables Intel XPT (Cross Package Transfer) prefetch to speculatively fetch data across NUMA domains for remote memory ac |

[⬆ Back to Top](#table-of-contents)
---

## CPUIntensive-M7-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `kti_prefetch` | `enabled` | Enables Intel KTI (UPI) prefetch to preload data from remote NUMA nodes across the inter-socket link, reducing remote me |
| `llc_alloc` | `disabled` | Controls Intel LLC (Last Level Cache) dead-line allocation, determining whether lines with no future reuse are placed in |
| `llc_prefetch` | `disabled` | Enables LLC prefetching from L2 to L3 cache to improve data availability for memory-bandwidth-intensive workloads |
| `patrol_scrub` | `disabled` | Enables background patrol scrubbing of DRAM to proactively detect and correct ECC errors before they accumulate |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `processor_c6report` | `enabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |
| `select_memory_ras_configuration` | `maximum-performance` | Selects the memory RAS configuration (JBOD, Mirror, Lockstep, Sparing) for fault tolerance |
| `snc` | `SNC4` | Enables Intel Sub-NUMA Clustering (SNC2 or SNC4), splitting the LLC and memory into sub-NUMA domains to reduce average m |
| `upi_link_enablement` | `2` | Sets the number of active Intel UPI (Ultra Path Interconnect) links between sockets (1, 2, 3, Auto) |
| `upi_power_management` | `enabled` | Enables Intel UPI link power management to reduce idle power consumption on inter-socket links |
| `xpt_prefetch` | `enabled` | Enables Intel XPT (Cross Package Transfer) prefetch to speculatively fetch data across NUMA domains for remote memory ac |

[⬆ Back to Top](#table-of-contents)
---

## CPUIntensive-M8-AMD

| BIOS Key | Value | Description |
|---|---|---|
| `cbs_cmn_apbdis` | `1` | Disables the Automatic Power Budget management to give software full control over power limits |
| `cbs_cmn_apbdis_df_pstate_rs` | `0` | Controls APBDIS interaction with Data Fabric P-states on Rome/Milan platforms |
| `cbs_cmn_cpu_cpb` | `Auto` | Controls Core Performance Boost (AMD's Turbo), allowing cores to run above base clock when thermal headroom allows |
| `cbs_cmn_cpu_global_cstate_ctrl` | `Auto` | Enables or disables global CPU C-states, controlling whether the processor can enter deep power-saving states |
| `cbs_cmn_cpu_l1stream_hw_prefetcher` | `Auto` | Enables or disables the L1 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_cpu_l2stream_hw_prefetcher` | `Auto` | Enables or disables the L2 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_determinism_slider` | `Power` | Sets the performance-vs-power determinism trade-off; Performance maximizes throughput, Power maximizes efficiency |
| `cbs_cmn_efficiency_mode_en_rs` | `High Performance Mode` | Enhanced Efficiency Mode control for Genoa/Bergamo, supporting High Performance and Efficiency mode profiles |
| `cbs_cmn_gnb_nb_iommu` | `Auto` | Enables the IOMMU in the northbridge/GNB for DMA isolation and SR-IOV support |
| `cbs_cmn_gnb_smu_df_cstates` | `Auto` | Controls Data Fabric C-states; disabling prevents the fabric from entering low-power states, reducing GPU/memory access latency |
| `cbs_cmn_gnb_smucppc` | `Auto` | Enables Collaborative Processor Performance Control (CPPC) via the SMU for OS-driven frequency scaling |
| `cbs_cpu_smt_ctrl` | `Auto` | Enables or disables Simultaneous Multi-Threading (SMT) on AMD processors |
| `cbs_df_cmn4link_max_xgmi_speed` | `Auto` | Sets the maximum xGMI link speed for 4-link configurations |
| `cbs_df_cmn_acpi_srat_l3numa` | `enabled` | Reports AMD L3 cache slices as separate NUMA domains in the ACPI SRAT table for OS topology awareness |
| `cbs_df_cmn_dram_nps` | `NPS4` | Sets NUMA Nodes Per Socket (NPS) to control how DRAM is presented as NUMA domains; NPS1=single domain, NPS4=four domains per socket |
| `cbs_df_cmn_mem_intlv_control` | `Auto` | Controls the memory interleave granularity for AMD platforms |
| `cpu_perf_enhancement` | `Auto` | Enables Enhanced CPU Performance mode, applying additional microarchitecture optimizations for throughput |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `svm_mode` | `enabled` | Enables AMD SVM (Secure Virtual Machine) hardware virtualization extensions required by hypervisors on AMD platforms |

[⬆ Back to Top](#table-of-contents)
---

## CPUIntensive-M8-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `adjacent_cache_line_prefetch` | `disabled` | Controls whether the CPU prefetches the adjacent cache line alongside the requested line, improving sequential workload  |
| `cpu_perf_enhancement` | `Auto` | Enables Enhanced CPU Performance mode, applying additional microarchitecture optimizations for throughput |
| `energy_efficient_turbo` | `enabled` | Enables Intel Energy Efficient Turbo, which limits maximum turbo frequency to balance performance and power consumption |
| `epp_profile` | `Performance` | Sets the default EPP profile (Performance, Balanced Performance, Balanced Power, Power) used for hardware-guided P-state |
| `kti_prefetch` | `disabled` | Enables Intel KTI (UPI) prefetch to preload data from remote NUMA nodes across the inter-socket link, reducing remote me |
| `latency_optimized_mode` | `enabled` | Enables latency-optimized memory mode on platforms that support it, reducing worst-case memory access time |
| `llc_alloc` | `enabled` | Controls Intel LLC (Last Level Cache) dead-line allocation, determining whether lines with no future reuse are placed in |
| `patrol_scrub` | `disabled` | Enables background patrol scrubbing of DRAM to proactively detect and correct ECC errors before they accumulate |
| `pwr_perf_tuning` | `bios` | Controls whether BIOS, OS, or PECI manages power/performance tuning bias |
| `select_memory_ras_configuration` | `maximum-performance` | Selects the memory RAS configuration (JBOD, Mirror, Lockstep, Sparing) for fault tolerance |
| `snc` | `enabled` | Enables Intel Sub-NUMA Clustering (SNC2 or SNC4), splitting the LLC and memory into sub-NUMA domains to reduce average m |
| `streamer_prefetch` | `disabled` | Enables the Intel DCU streamer prefetcher, which detects forward sequential access patterns and prefetches into L1 cache |
| `work_load_config` | `Balanced` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |
| `xpt_prefetch` | `disabled` | Enables Intel XPT (Cross Package Transfer) prefetch to speculatively fetch data across NUMA domains for remote memory ac |
| `xpt_remote_prefetch` | `disabled` | Enables Intel XPT remote prefetch specifically for cross-socket remote memory access patterns |

[⬆ Back to Top](#table-of-contents)
---

## ComputationIntensive-M6-AMD

| BIOS Key | Value | Description |
|---|---|---|
| `cbs_cmn_apbdis` | `1` | Disables the Automatic Power Budget management to give software full control over power limits |
| `cbs_cmn_cpu_cpb` | `Auto` | Controls Core Performance Boost (AMD's Turbo), allowing cores to run above base clock when thermal headroom allows |
| `cbs_cmn_cpu_global_cstate_ctrl` | `Auto` | Enables or disables global CPU C-states, controlling whether the processor can enter deep power-saving states |
| `cbs_cmn_cpu_l1stream_hw_prefetcher` | `Auto` | Enables or disables the L1 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_cpu_l2stream_hw_prefetcher` | `Auto` | Enables or disables the L2 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_determinism_slider` | `Power` | Sets the performance-vs-power determinism trade-off; Performance maximizes throughput, Power maximizes efficiency |
| `cbs_cmn_efficiency_mode_en` | `Auto` | Enables Efficiency Mode to optimize the processor for power-efficient operation at the cost of peak performance |
| `cbs_cmn_fixed_soc_pstate` | `P0` | Pins the SoC (data fabric/IO) to a fixed P-state for deterministic I/O and memory latency |
| `cbs_cmn_gnb_nb_iommu` | `Auto` | Enables the IOMMU in the northbridge/GNB for DMA isolation and SR-IOV support |
| `cbs_cpu_smt_ctrl` | `Auto` | Enables or disables Simultaneous Multi-Threading (SMT) on AMD processors |
| `cbs_df_cmn_acpi_srat_l3numa` | `enabled` | Reports AMD L3 cache slices as separate NUMA domains in the ACPI SRAT table for OS topology awareness |
| `cbs_df_cmn_dram_nps` | `NPS4` | Sets NUMA Nodes Per Socket (NPS) to control how DRAM is presented as NUMA domains; NPS1=single domain, NPS4=four domains per socket |
| `cisco_xgmi_max_speed` | `enabled` | Enables or disables Cisco control over xGMI maximum link speed for inter-socket GPU fabric |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `svm_mode` | `enabled` | Enables AMD SVM (Secure Virtual Machine) hardware virtualization extensions required by hypervisors on AMD platforms |

[⬆ Back to Top](#table-of-contents)
---

## DataAnalytics-M6-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `cpu_perf_enhancement` | `Auto` | Enables Enhanced CPU Performance mode, applying additional microarchitecture optimizations for throughput |
| `energy_efficient_turbo` | `enabled` | Enables Intel Energy Efficient Turbo, which limits maximum turbo frequency to balance performance and power consumption |
| `intel_vt_for_directed_io` | `disabled` | Enables Intel VT-d (Virtualization Technology for Directed I/O), providing IOMMU support for PCIe device assignment to V |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `processor_c1e` | `enabled` | Enables processor C1E (Enhanced Halt State) to reduce voltage and frequency when cores are halted |
| `processor_c6report` | `enabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |
| `work_load_config` | `Balanced` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |

[⬆ Back to Top](#table-of-contents)
---

## DataAnalytics-M7-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `intel_virtualization_technology` | `disabled` | Enables Intel VT-x hardware virtualization extensions required by hypervisors for guest VM isolation |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `processor_c6report` | `enabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |

[⬆ Back to Top](#table-of-contents)
---

## EdgeAI-M8-AMD

| BIOS Key | Value | Description |
|---|---|---|
| `cbs_cmn_cpu_cpb` | `Auto` | Controls Core Performance Boost (AMD's Turbo), allowing cores to run above base clock when thermal headroom allows |
| `cbs_cmn_determinism_slider` | `Power` | Sets the performance-vs-power determinism trade-off; Performance maximizes throughput, Power maximizes efficiency |
| `cbs_cmn_efficiency_mode_en_rs` | `Efficiency Mode` | Enhanced Efficiency Mode control for Genoa/Bergamo, supporting High Performance and Efficiency mode profiles |
| `cbs_cmn_gnb_smu_df_cstates` | `Auto` | Controls Data Fabric C-states; disabling prevents the fabric from entering low-power states, reducing GPU/memory access latency |
| `cbs_cmn_gnb_smucppc` | `enabled` | Enables Collaborative Processor Performance Control (CPPC) via the SMU for OS-driven frequency scaling |
| `cbs_df_cmn_acpi_srat_l3numa` | `enabled` | Reports AMD L3 cache slices as separate NUMA domains in the ACPI SRAT table for OS topology awareness |
| `cpu_energy_performance` | `balanced-performance` | Sets the CPU energy/performance bias hint that the OS and hardware use to balance power consumption versus throughput |
| `cpu_performance` | `enterprise` | Sets the CPU performance profile (enterprise, high-throughput, HPC) controlling prefetcher, turbo, and bandwidth setting |
| `cpu_power_management` | `energy-efficient` | Sets the overall CPU power management policy (performance, energy-efficient, custom) controlling P-state and C-state beh |
| `llc_prefetch` | `enabled` | Enables LLC prefetching from L2 to L3 cache to improve data availability for memory-bandwidth-intensive workloads |

[⬆ Back to Top](#table-of-contents)
---

## EdgeAI-M8-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `cpu_energy_performance` | `balanced-performance` | Sets the CPU energy/performance bias hint that the OS and hardware use to balance power consumption versus throughput |
| `cpu_performance` | `enterprise` | Sets the CPU performance profile (enterprise, high-throughput, HPC) controlling prefetcher, turbo, and bandwidth setting |
| `cpu_power_management` | `energy-efficient` | Sets the overall CPU power management policy (performance, energy-efficient, custom) controlling P-state and C-state beh |
| `energy_efficient_turbo` | `enabled` | Enables Intel Energy Efficient Turbo, which limits maximum turbo frequency to balance performance and power consumption |
| `hwpm_enable` | `HWPM Native Mode` | Enables Intel Hardware P-state Management (HWPM) so the hardware controls P-state selection autonomously without OS inte |
| `intel_turbo_boost_tech` | `enabled` | Enables Intel Turbo Boost Technology, allowing cores to run above the rated base clock frequency when thermal and power  |
| `llc_prefetch` | `enabled` | Enables LLC prefetching from L2 to L3 cache to improve data availability for memory-bandwidth-intensive workloads |
| `numa_optimized` | `enabled` | Enables NUMA optimization in the BIOS, ensuring memory is allocated to the NUMA node closest to the requesting CPU |

[⬆ Back to Top](#table-of-contents)
---

## EnergyEfficiency-M5-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `auto_cc_state` | `enabled` | Enables autonomous core C-state transitions, allowing cores to independently enter lower power states without OS coordin |
| `cpu_power_management` | `custom` | Sets the overall CPU power management policy (performance, energy-efficient, custom) controlling P-state and C-state beh |
| `intel_turbo_boost_tech` | `disabled` | Enables Intel Turbo Boost Technology, allowing cores to run above the rated base clock frequency when thermal and power  |
| `package_cstate_limit` | `C6 Retention` | Sets the maximum C-state the processor package is allowed to enter; restricting to C0/C1 prevents deep sleep for low-lat |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |

[⬆ Back to Top](#table-of-contents)
---

## EnergyEfficiency-M6-AMD

| BIOS Key | Value | Description |
|---|---|---|
| `cbs_cmn_apbdis` | `0` | Disables the Automatic Power Budget management to give software full control over power limits |
| `cbs_cmn_cpu_cpb` | `Auto` | Controls Core Performance Boost (AMD's Turbo), allowing cores to run above base clock when thermal headroom allows |
| `cbs_cmn_cpu_global_cstate_ctrl` | `Auto` | Enables or disables global CPU C-states, controlling whether the processor can enter deep power-saving states |
| `cbs_cmn_cpu_l1stream_hw_prefetcher` | `disabled` | Enables or disables the L1 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_cpu_l2stream_hw_prefetcher` | `disabled` | Enables or disables the L2 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_determinism_slider` | `Performance` | Sets the performance-vs-power determinism trade-off; Performance maximizes throughput, Power maximizes efficiency |
| `cbs_cmn_efficiency_mode_en` | `Auto` | Enables Efficiency Mode to optimize the processor for power-efficient operation at the cost of peak performance |
| `cbs_cmn_fixed_soc_pstate` | `P3` | Pins the SoC (data fabric/IO) to a fixed P-state for deterministic I/O and memory latency |
| `cbs_cmn_gnb_nb_iommu` | `Auto` | Enables the IOMMU in the northbridge/GNB for DMA isolation and SR-IOV support |
| `cbs_cpu_smt_ctrl` | `Auto` | Enables or disables Simultaneous Multi-Threading (SMT) on AMD processors |
| `cbs_df_cmn_acpi_srat_l3numa` | `Auto` | Reports AMD L3 cache slices as separate NUMA domains in the ACPI SRAT table for OS topology awareness |
| `cbs_df_cmn_dram_nps` | `NPS1` | Sets NUMA Nodes Per Socket (NPS) to control how DRAM is presented as NUMA domains; NPS1=single domain, NPS4=four domains per socket |
| `cisco_xgmi_max_speed` | `disabled` | Enables or disables Cisco control over xGMI maximum link speed for inter-socket GPU fabric |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `svm_mode` | `enabled` | Enables AMD SVM (Secure Virtual Machine) hardware virtualization extensions required by hypervisors on AMD platforms |

[⬆ Back to Top](#table-of-contents)
---

## EnergyEfficiency-M6-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `adjacent_cache_line_prefetch` | `disabled` | Controls whether the CPU prefetches the adjacent cache line alongside the requested line, improving sequential workload  |
| `energy_efficient_turbo` | `enabled` | Enables Intel Energy Efficient Turbo, which limits maximum turbo frequency to balance performance and power consumption |
| `hardware_prefetch` | `disabled` | Enables the hardware prefetcher in the DCU to speculatively fetch cache lines based on observed access patterns |
| `ip_prefetch` | `disabled` | Enables the Intel DCU IP (Instruction Pointer) prefetcher for code-access pattern prediction |
| `package_cstate_limit` | `C6 Non Retention` | Sets the maximum C-state the processor package is allowed to enter; restricting to C0/C1 prevents deep sleep for low-lat |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `processor_c1e` | `enabled` | Enables processor C1E (Enhanced Halt State) to reduce voltage and frequency when cores are halted |
| `processor_c6report` | `enabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |
| `streamer_prefetch` | `disabled` | Enables the Intel DCU streamer prefetcher, which detects forward sequential access patterns and prefetches into L1 cache |
| `work_load_config` | `Balanced` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |

[⬆ Back to Top](#table-of-contents)
---

## EnergyEfficiency-M8-AMD

| BIOS Key | Value | Description |
|---|---|---|
| `cbs_cmn_apbdis` | `Auto` | Disables the Automatic Power Budget management to give software full control over power limits |
| `cbs_cmn_apbdis_df_pstate_rs` | `0` | Controls APBDIS interaction with Data Fabric P-states on Rome/Milan platforms |
| `cbs_cmn_cpu_cpb` | `Auto` | Controls Core Performance Boost (AMD's Turbo), allowing cores to run above base clock when thermal headroom allows |
| `cbs_cmn_cpu_global_cstate_ctrl` | `Auto` | Enables or disables global CPU C-states, controlling whether the processor can enter deep power-saving states |
| `cbs_cmn_cpu_l1stream_hw_prefetcher` | `disabled` | Enables or disables the L1 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_cpu_l2stream_hw_prefetcher` | `disabled` | Enables or disables the L2 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_determinism_slider` | `Power` | Sets the performance-vs-power determinism trade-off; Performance maximizes throughput, Power maximizes efficiency |
| `cbs_cmn_efficiency_mode_en_rs` | `Efficiency Mode` | Enhanced Efficiency Mode control for Genoa/Bergamo, supporting High Performance and Efficiency mode profiles |
| `cbs_cmn_gnb_nb_iommu` | `Auto` | Enables the IOMMU in the northbridge/GNB for DMA isolation and SR-IOV support |
| `cbs_cmn_gnb_smu_df_cstates` | `Auto` | Controls Data Fabric C-states; disabling prevents the fabric from entering low-power states, reducing GPU/memory access latency |
| `cbs_cmn_gnb_smucppc` | `enabled` | Enables Collaborative Processor Performance Control (CPPC) via the SMU for OS-driven frequency scaling |
| `cbs_cpu_smt_ctrl` | `Auto` | Enables or disables Simultaneous Multi-Threading (SMT) on AMD processors |
| `cbs_df_cmn4link_max_xgmi_speed` | `Auto` | Sets the maximum xGMI link speed for 4-link configurations |
| `cbs_df_cmn_acpi_srat_l3numa` | `Auto` | Reports AMD L3 cache slices as separate NUMA domains in the ACPI SRAT table for OS topology awareness |
| `cbs_df_cmn_dram_nps` | `Auto` | Sets NUMA Nodes Per Socket (NPS) to control how DRAM is presented as NUMA domains; NPS1=single domain, NPS4=four domains per socket |
| `cbs_df_cmn_mem_intlv_control` | `Auto` | Controls the memory interleave granularity for AMD platforms |
| `cpu_perf_enhancement` | `Disabled` | Enables Enhanced CPU Performance mode, applying additional microarchitecture optimizations for throughput |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `svm_mode` | `enabled` | Enables AMD SVM (Secure Virtual Machine) hardware virtualization extensions required by hypervisors on AMD platforms |

[⬆ Back to Top](#table-of-contents)
---

## EnergyEfficiency-M8-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `adjacent_cache_line_prefetch` | `disabled` | Controls whether the CPU prefetches the adjacent cache line alongside the requested line, improving sequential workload  |
| `energy_efficient_turbo` | `enabled` | Enables Intel Energy Efficient Turbo, which limits maximum turbo frequency to balance performance and power consumption |
| `epp_profile` | `Power` | Sets the default EPP profile (Performance, Balanced Performance, Balanced Power, Power) used for hardware-guided P-state |
| `package_cstate_limit` | `C6 Non Retention` | Sets the maximum C-state the processor package is allowed to enter; restricting to C0/C1 prevents deep sleep for low-lat |
| `processor_c1e` | `enabled` | Enables processor C1E (Enhanced Halt State) to reduce voltage and frequency when cores are halted |
| `processor_c6report` | `enabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |
| `pwr_perf_tuning` | `bios` | Controls whether BIOS, OS, or PECI manages power/performance tuning bias |
| `select_memory_ras_configuration` | `adddc-sparing` | Selects the memory RAS configuration (JBOD, Mirror, Lockstep, Sparing) for fault tolerance |
| `streamer_prefetch` | `disabled` | Enables the Intel DCU streamer prefetcher, which detects forward sequential access patterns and prefetches into L1 cache |
| `work_load_config` | `Balanced` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |

[⬆ Back to Top](#table-of-contents)
---

## EnergyEfficient-M7-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `energy_efficient_turbo` | `enabled` | Enables Intel Energy Efficient Turbo, which limits maximum turbo frequency to balance performance and power consumption |
| `package_cstate_limit` | `C6 Non Retention` | Sets the maximum C-state the processor package is allowed to enter; restricting to C0/C1 prevents deep sleep for low-lat |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `processor_c1e` | `enabled` | Enables processor C1E (Enhanced Halt State) to reduce voltage and frequency when cores are halted |
| `processor_c6report` | `enabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |
| `work_load_config` | `Balanced` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |

[⬆ Back to Top](#table-of-contents)
---

## GPUInference-M8-AMD

| BIOS Key | Value | Description |
|---|---|---|
| `acs_control_gpu1state` | `enabled` | Enables or disables ACS (Access Control Services) for GPU slot 1, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu2state` | `enabled` | Enables or disables ACS for GPU slot 2, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu3state` | `enabled` | Enables or disables ACS for GPU slot 3, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu4state` | `enabled` | Enables or disables ACS for GPU slot 4, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu5state` | `enabled` | Enables or disables ACS for GPU slot 5, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu6state` | `enabled` | Enables or disables ACS for GPU slot 6, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu7state` | `enabled` | Enables or disables ACS for GPU slot 7, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu8state` | `enabled` | Enables or disables ACS for GPU slot 8, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_slot11state` | `enabled` | Enables or disables ACS for PCIe slot 11, controlling peer-to-peer transaction isolation for that slot |
| `acs_control_slot12state` | `enabled` | Enables or disables ACS for PCIe slot 12, controlling peer-to-peer transaction isolation for that slot |
| `acs_control_slot13state` | `enabled` | Enables or disables ACS for PCIe slot 13, controlling peer-to-peer transaction isolation for that slot |
| `acs_control_slot14state` | `enabled` | Enables or disables ACS for PCIe slot 14, controlling peer-to-peer transaction isolation for that slot |
| `cbs_cmn_determinism_slider` | `Performance` | Sets the performance-vs-power determinism trade-off; Performance maximizes throughput, Power maximizes efficiency |
| `cbs_cmn_efficiency_mode_en_rs` | `High Performance Mode` | Enhanced Efficiency Mode control for Genoa/Bergamo, supporting High Performance and Efficiency mode profiles |
| `cbs_cmn_gnb_smu_df_cstates` | `disabled` | Controls Data Fabric C-states; disabling prevents the fabric from entering low-power states, reducing GPU/memory access latency |
| `cbs_df_cmn_acpi_srat_l3numa` | `enabled` | Reports AMD L3 cache slices as separate NUMA domains in the ACPI SRAT table for OS topology awareness |
| `cpu_energy_performance` | `performance` | Sets the CPU energy/performance bias hint that the OS and hardware use to balance power consumption versus throughput |
| `cpu_performance` | `high-throughput` | Sets the CPU performance profile (enterprise, high-throughput, HPC) controlling prefetcher, turbo, and bandwidth setting |
| `cpu_power_management` | `performance` | Sets the overall CPU power management policy (performance, energy-efficient, custom) controlling P-state and C-state beh |
| `llc_prefetch` | `enabled` | Enables LLC prefetching from L2 to L3 cache to improve data availability for memory-bandwidth-intensive workloads |
| `sr_iov` | `enabled` | Enables PCI SR-IOV (Single Root I/O Virtualization) to allow a single PCIe device to appear as multiple virtual function |

[⬆ Back to Top](#table-of-contents)
---

## GPUInference-M8-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `acs_control_gpu1state` | `enabled` | Enables or disables ACS (Access Control Services) for GPU slot 1, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu2state` | `enabled` | Enables or disables ACS for GPU slot 2, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu3state` | `enabled` | Enables or disables ACS for GPU slot 3, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu4state` | `enabled` | Enables or disables ACS for GPU slot 4, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu5state` | `enabled` | Enables or disables ACS for GPU slot 5, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu6state` | `enabled` | Enables or disables ACS for GPU slot 6, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu7state` | `enabled` | Enables or disables ACS for GPU slot 7, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu8state` | `enabled` | Enables or disables ACS for GPU slot 8, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_slot11state` | `enabled` | Enables or disables ACS for PCIe slot 11, controlling peer-to-peer transaction isolation for that slot |
| `acs_control_slot12state` | `enabled` | Enables or disables ACS for PCIe slot 12, controlling peer-to-peer transaction isolation for that slot |
| `acs_control_slot13state` | `enabled` | Enables or disables ACS for PCIe slot 13, controlling peer-to-peer transaction isolation for that slot |
| `acs_control_slot14state` | `enabled` | Enables or disables ACS for PCIe slot 14, controlling peer-to-peer transaction isolation for that slot |
| `autonumous_cstate_enable` | `disabled` | Enables the CPU's autonomous C-state feature, allowing hardware to decide when to transition cores to low-power states |
| `cpu_energy_performance` | `performance` | Sets the CPU energy/performance bias hint that the OS and hardware use to balance power consumption versus throughput |
| `cpu_performance` | `high-throughput` | Sets the CPU performance profile (enterprise, high-throughput, HPC) controlling prefetcher, turbo, and bandwidth setting |
| `cpu_power_management` | `performance` | Sets the overall CPU power management policy (performance, energy-efficient, custom) controlling P-state and C-state beh |
| `hwpm_enable` | `Disabled` | Enables Intel Hardware P-state Management (HWPM) so the hardware controls P-state selection autonomously without OS inte |
| `llc_prefetch` | `enabled` | Enables LLC prefetching from L2 to L3 cache to improve data availability for memory-bandwidth-intensive workloads |
| `numa_optimized` | `enabled` | Enables NUMA optimization in the BIOS, ensuring memory is allocated to the NUMA node closest to the requesting CPU |
| `package_cstate_limit` | `C0 C1 State` | Sets the maximum C-state the processor package is allowed to enter; restricting to C0/C1 prevents deep sleep for low-lat |
| `sr_iov` | `enabled` | Enables PCI SR-IOV (Single Root I/O Virtualization) to allow a single PCIe device to appear as multiple virtual function |
| `xpt_prefetch` | `enabled` | Enables Intel XPT (Cross Package Transfer) prefetch to speculatively fetch data across NUMA domains for remote memory ac |

[⬆ Back to Top](#table-of-contents)
---

## GPUTraining-M8-AMD

| BIOS Key | Value | Description |
|---|---|---|
| `acs_control_gpu1state` | `enabled` | Enables or disables ACS (Access Control Services) for GPU slot 1, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu2state` | `enabled` | Enables or disables ACS for GPU slot 2, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu3state` | `enabled` | Enables or disables ACS for GPU slot 3, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu4state` | `enabled` | Enables or disables ACS for GPU slot 4, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu5state` | `enabled` | Enables or disables ACS for GPU slot 5, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu6state` | `enabled` | Enables or disables ACS for GPU slot 6, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu7state` | `enabled` | Enables or disables ACS for GPU slot 7, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu8state` | `enabled` | Enables or disables ACS for GPU slot 8, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_slot11state` | `enabled` | Enables or disables ACS for PCIe slot 11, controlling peer-to-peer transaction isolation for that slot |
| `acs_control_slot12state` | `enabled` | Enables or disables ACS for PCIe slot 12, controlling peer-to-peer transaction isolation for that slot |
| `acs_control_slot13state` | `enabled` | Enables or disables ACS for PCIe slot 13, controlling peer-to-peer transaction isolation for that slot |
| `acs_control_slot14state` | `enabled` | Enables or disables ACS for PCIe slot 14, controlling peer-to-peer transaction isolation for that slot |
| `cbs_cmn_determinism_slider` | `Performance` | Sets the performance-vs-power determinism trade-off; Performance maximizes throughput, Power maximizes efficiency |
| `cbs_cmn_efficiency_mode_en_rs` | `High Performance Mode` | Enhanced Efficiency Mode control for Genoa/Bergamo, supporting High Performance and Efficiency mode profiles |
| `cbs_cmn_gnb_smu_df_cstates` | `disabled` | Controls Data Fabric C-states; disabling prevents the fabric from entering low-power states, reducing GPU/memory access latency |
| `cbs_df_cmn_acpi_srat_l3numa` | `enabled` | Reports AMD L3 cache slices as separate NUMA domains in the ACPI SRAT table for OS topology awareness |
| `cpu_energy_performance` | `performance` | Sets the CPU energy/performance bias hint that the OS and hardware use to balance power consumption versus throughput |
| `cpu_performance` | `high-throughput` | Sets the CPU performance profile (enterprise, high-throughput, HPC) controlling prefetcher, turbo, and bandwidth setting |
| `cpu_power_management` | `performance` | Sets the overall CPU power management policy (performance, energy-efficient, custom) controlling P-state and C-state beh |
| `llc_prefetch` | `enabled` | Enables LLC prefetching from L2 to L3 cache to improve data availability for memory-bandwidth-intensive workloads |
| `sr_iov` | `enabled` | Enables PCI SR-IOV (Single Root I/O Virtualization) to allow a single PCIe device to appear as multiple virtual function |
| `work_load_config` | `Balanced` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |

[⬆ Back to Top](#table-of-contents)
---

## GPUTraining-M8-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `acs_control_gpu1state` | `enabled` | Enables or disables ACS (Access Control Services) for GPU slot 1, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu2state` | `enabled` | Enables or disables ACS for GPU slot 2, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu3state` | `enabled` | Enables or disables ACS for GPU slot 3, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu4state` | `enabled` | Enables or disables ACS for GPU slot 4, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu5state` | `enabled` | Enables or disables ACS for GPU slot 5, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu6state` | `enabled` | Enables or disables ACS for GPU slot 6, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu7state` | `enabled` | Enables or disables ACS for GPU slot 7, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_gpu8state` | `enabled` | Enables or disables ACS for GPU slot 8, controlling peer-to-peer PCIe transaction isolation |
| `acs_control_slot11state` | `enabled` | Enables or disables ACS for PCIe slot 11, controlling peer-to-peer transaction isolation for that slot |
| `acs_control_slot12state` | `enabled` | Enables or disables ACS for PCIe slot 12, controlling peer-to-peer transaction isolation for that slot |
| `acs_control_slot13state` | `enabled` | Enables or disables ACS for PCIe slot 13, controlling peer-to-peer transaction isolation for that slot |
| `acs_control_slot14state` | `enabled` | Enables or disables ACS for PCIe slot 14, controlling peer-to-peer transaction isolation for that slot |
| `autonumous_cstate_enable` | `disabled` | Enables the CPU's autonomous C-state feature, allowing hardware to decide when to transition cores to low-power states |
| `cpu_energy_performance` | `performance` | Sets the CPU energy/performance bias hint that the OS and hardware use to balance power consumption versus throughput |
| `cpu_performance` | `high-throughput` | Sets the CPU performance profile (enterprise, high-throughput, HPC) controlling prefetcher, turbo, and bandwidth setting |
| `cpu_power_management` | `performance` | Sets the overall CPU power management policy (performance, energy-efficient, custom) controlling P-state and C-state beh |
| `hwpm_enable` | `Disabled` | Enables Intel Hardware P-state Management (HWPM) so the hardware controls P-state selection autonomously without OS inte |
| `llc_prefetch` | `enabled` | Enables LLC prefetching from L2 to L3 cache to improve data availability for memory-bandwidth-intensive workloads |
| `numa_optimized` | `enabled` | Enables NUMA optimization in the BIOS, ensuring memory is allocated to the NUMA node closest to the requesting CPU |
| `package_cstate_limit` | `C0 C1 State` | Sets the maximum C-state the processor package is allowed to enter; restricting to C0/C1 prevents deep sleep for low-lat |
| `sr_iov` | `enabled` | Enables PCI SR-IOV (Single Root I/O Virtualization) to allow a single PCIe device to appear as multiple virtual function |
| `work_load_config` | `Balanced` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |
| `xpt_prefetch` | `enabled` | Enables Intel XPT (Cross Package Transfer) prefetch to speculatively fetch data across NUMA domains for remote memory ac |

[⬆ Back to Top](#table-of-contents)
---

## HPC-M8-AMD

| BIOS Key | Value | Description |
|---|---|---|
| `cbs_cmn_apbdis` | `1` | Disables the Automatic Power Budget management to give software full control over power limits |
| `cbs_cmn_apbdis_df_pstate_rs` | `0` | Controls APBDIS interaction with Data Fabric P-states on Rome/Milan platforms |
| `cbs_cmn_cpu_cpb` | `Auto` | Controls Core Performance Boost (AMD's Turbo), allowing cores to run above base clock when thermal headroom allows |
| `cbs_cmn_cpu_global_cstate_ctrl` | `Auto` | Enables or disables global CPU C-states, controlling whether the processor can enter deep power-saving states |
| `cbs_cmn_cpu_l1stream_hw_prefetcher` | `Auto` | Enables or disables the L1 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_cpu_l2stream_hw_prefetcher` | `Auto` | Enables or disables the L2 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_determinism_slider` | `Power` | Sets the performance-vs-power determinism trade-off; Performance maximizes throughput, Power maximizes efficiency |
| `cbs_cmn_efficiency_mode_en_rs` | `High Performance Mode` | Enhanced Efficiency Mode control for Genoa/Bergamo, supporting High Performance and Efficiency mode profiles |
| `cbs_cmn_gnb_nb_iommu` | `Auto` | Enables the IOMMU in the northbridge/GNB for DMA isolation and SR-IOV support |
| `cbs_cmn_gnb_smu_df_cstates` | `Auto` | Controls Data Fabric C-states; disabling prevents the fabric from entering low-power states, reducing GPU/memory access latency |
| `cbs_cmn_gnb_smucppc` | `Auto` | Enables Collaborative Processor Performance Control (CPPC) via the SMU for OS-driven frequency scaling |
| `cbs_cpu_smt_ctrl` | `disabled` | Enables or disables Simultaneous Multi-Threading (SMT) on AMD processors |
| `cbs_df_cmn4link_max_xgmi_speed` | `Auto` | Sets the maximum xGMI link speed for 4-link configurations |
| `cbs_df_cmn_acpi_srat_l3numa` | `Auto` | Reports AMD L3 cache slices as separate NUMA domains in the ACPI SRAT table for OS topology awareness |
| `cbs_df_cmn_dram_nps` | `NPS4` | Sets NUMA Nodes Per Socket (NPS) to control how DRAM is presented as NUMA domains; NPS1=single domain, NPS4=four domains per socket |
| `cbs_df_cmn_mem_intlv_control` | `Auto` | Controls the memory interleave granularity for AMD platforms |
| `cpu_perf_enhancement` | `Auto` | Enables Enhanced CPU Performance mode, applying additional microarchitecture optimizations for throughput |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |

[⬆ Back to Top](#table-of-contents)
---

## HPC-M8-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `cpu_perf_enhancement` | `Auto` | Enables Enhanced CPU Performance mode, applying additional microarchitecture optimizations for throughput |
| `cpu_performance` | `hpc` | Sets the CPU performance profile (enterprise, high-throughput, HPC) controlling prefetcher, turbo, and bandwidth setting |
| `epp_profile` | `Performance` | Sets the default EPP profile (Performance, Balanced Performance, Balanced Power, Power) used for hardware-guided P-state |
| `intel_hyper_threading_tech` | `disabled` | Enables Intel Hyper-Threading Technology, presenting each physical core as two logical threads to the OS |
| `intel_virtualization_technology` | `disabled` | Enables Intel VT-x hardware virtualization extensions required by hypervisors for guest VM isolation |
| `latency_optimized_mode` | `enabled` | Enables latency-optimized memory mode on platforms that support it, reducing worst-case memory access time |
| `llc_alloc` | `disabled` | Controls Intel LLC (Last Level Cache) dead-line allocation, determining whether lines with no future reuse are placed in |
| `pwr_perf_tuning` | `bios` | Controls whether BIOS, OS, or PECI manages power/performance tuning bias |
| `select_memory_ras_configuration` | `adddc-sparing` | Selects the memory RAS configuration (JBOD, Mirror, Lockstep, Sparing) for fault tolerance |

[⬆ Back to Top](#table-of-contents)
---

## HighPerformanceComputing-M5-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `intel_hyper_threading_tech` | `disabled` | Enables Intel Hyper-Threading Technology, presenting each physical core as two logical threads to the OS |
| `intel_virtualization_technology` | `disabled` | Enables Intel VT-x hardware virtualization extensions required by hypervisors for guest VM isolation |
| `intel_vt_for_directed_io` | `disabled` | Enables Intel VT-d (Virtualization Technology for Directed I/O), providing IOMMU support for PCIe device assignment to V |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `work_load_config` | `Balanced` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |

[⬆ Back to Top](#table-of-contents)
---

## HighPerformanceComputing-M6-AMD

| BIOS Key | Value | Description |
|---|---|---|
| `cbs_cmn_apbdis` | `1` | Disables the Automatic Power Budget management to give software full control over power limits |
| `cbs_cmn_cpu_cpb` | `Auto` | Controls Core Performance Boost (AMD's Turbo), allowing cores to run above base clock when thermal headroom allows |
| `cbs_cmn_cpu_global_cstate_ctrl` | `Auto` | Enables or disables global CPU C-states, controlling whether the processor can enter deep power-saving states |
| `cbs_cmn_cpu_l1stream_hw_prefetcher` | `Auto` | Enables or disables the L1 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_cpu_l2stream_hw_prefetcher` | `Auto` | Enables or disables the L2 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_determinism_slider` | `Power` | Sets the performance-vs-power determinism trade-off; Performance maximizes throughput, Power maximizes efficiency |
| `cbs_cmn_efficiency_mode_en` | `Auto` | Enables Efficiency Mode to optimize the processor for power-efficient operation at the cost of peak performance |
| `cbs_cmn_fixed_soc_pstate` | `P0` | Pins the SoC (data fabric/IO) to a fixed P-state for deterministic I/O and memory latency |
| `cbs_cmn_gnb_nb_iommu` | `disabled` | Enables the IOMMU in the northbridge/GNB for DMA isolation and SR-IOV support |
| `cbs_cpu_smt_ctrl` | `disabled` | Enables or disables Simultaneous Multi-Threading (SMT) on AMD processors |
| `cbs_df_cmn_acpi_srat_l3numa` | `Auto` | Reports AMD L3 cache slices as separate NUMA domains in the ACPI SRAT table for OS topology awareness |
| `cbs_df_cmn_dram_nps` | `NPS4` | Sets NUMA Nodes Per Socket (NPS) to control how DRAM is presented as NUMA domains; NPS1=single domain, NPS4=four domains per socket |
| `cisco_xgmi_max_speed` | `enabled` | Enables or disables Cisco control over xGMI maximum link speed for inter-socket GPU fabric |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `svm_mode` | `disabled` | Enables AMD SVM (Secure Virtual Machine) hardware virtualization extensions required by hypervisors on AMD platforms |

[⬆ Back to Top](#table-of-contents)
---

## HighPerformanceComputing-M6-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `cpu_perf_enhancement` | `Auto` | Enables Enhanced CPU Performance mode, applying additional microarchitecture optimizations for throughput |
| `intel_virtualization_technology` | `disabled` | Enables Intel VT-x hardware virtualization extensions required by hypervisors for guest VM isolation |
| `intel_vt_for_directed_io` | `disabled` | Enables Intel VT-d (Virtualization Technology for Directed I/O), providing IOMMU support for PCIe device assignment to V |
| `llc_alloc` | `disabled` | Controls Intel LLC (Last Level Cache) dead-line allocation, determining whether lines with no future reuse are placed in |
| `llc_prefetch` | `disabled` | Enables LLC prefetching from L2 to L3 cache to improve data availability for memory-bandwidth-intensive workloads |
| `memory_refresh_rate` | `1x Refresh` | Sets the DRAM refresh rate (1x or 2x) to balance power savings and memory reliability at elevated temperatures |
| `patrol_scrub` | `disabled` | Enables background patrol scrubbing of DRAM to proactively detect and correct ECC errors before they accumulate |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `snc` | `enabled` | Enables Intel Sub-NUMA Clustering (SNC2 or SNC4), splitting the LLC and memory into sub-NUMA domains to reduce average m |
| `upi_power_management` | `enabled` | Enables Intel UPI link power management to reduce idle power consumption on inter-socket links |
| `work_load_config` | `Balanced` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |
| `xpt_prefetch` | `enabled` | Enables Intel XPT (Cross Package Transfer) prefetch to speculatively fetch data across NUMA domains for remote memory ac |

[⬆ Back to Top](#table-of-contents)
---

## HighPerformanceComputing-M7-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `intel_virtualization_technology` | `disabled` | Enables Intel VT-x hardware virtualization extensions required by hypervisors for guest VM isolation |
| `llc_alloc` | `disabled` | Controls Intel LLC (Last Level Cache) dead-line allocation, determining whether lines with no future reuse are placed in |
| `llc_prefetch` | `disabled` | Enables LLC prefetching from L2 to L3 cache to improve data availability for memory-bandwidth-intensive workloads |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `processor_c6report` | `enabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |
| `work_load_config` | `Balanced` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |

[⬆ Back to Top](#table-of-contents)
---

## IOIntensive-M6-AMD

| BIOS Key | Value | Description |
|---|---|---|
| `cbs_cmn_apbdis` | `1` | Disables the Automatic Power Budget management to give software full control over power limits |
| `cbs_cmn_cpu_cpb` | `Auto` | Controls Core Performance Boost (AMD's Turbo), allowing cores to run above base clock when thermal headroom allows |
| `cbs_cmn_cpu_global_cstate_ctrl` | `Auto` | Enables or disables global CPU C-states, controlling whether the processor can enter deep power-saving states |
| `cbs_cmn_cpu_l1stream_hw_prefetcher` | `Auto` | Enables or disables the L1 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_cpu_l2stream_hw_prefetcher` | `Auto` | Enables or disables the L2 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_determinism_slider` | `Power` | Sets the performance-vs-power determinism trade-off; Performance maximizes throughput, Power maximizes efficiency |
| `cbs_cmn_efficiency_mode_en` | `Auto` | Enables Efficiency Mode to optimize the processor for power-efficient operation at the cost of peak performance |
| `cbs_cmn_fixed_soc_pstate` | `P0` | Pins the SoC (data fabric/IO) to a fixed P-state for deterministic I/O and memory latency |
| `cbs_cmn_gnb_nb_iommu` | `Auto` | Enables the IOMMU in the northbridge/GNB for DMA isolation and SR-IOV support |
| `cbs_cpu_smt_ctrl` | `Auto` | Enables or disables Simultaneous Multi-Threading (SMT) on AMD processors |
| `cbs_df_cmn_acpi_srat_l3numa` | `Auto` | Reports AMD L3 cache slices as separate NUMA domains in the ACPI SRAT table for OS topology awareness |
| `cbs_df_cmn_dram_nps` | `NPS4` | Sets NUMA Nodes Per Socket (NPS) to control how DRAM is presented as NUMA domains; NPS1=single domain, NPS4=four domains per socket |
| `cisco_xgmi_max_speed` | `enabled` | Enables or disables Cisco control over xGMI maximum link speed for inter-socket GPU fabric |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `svm_mode` | `enabled` | Enables AMD SVM (Secure Virtual Machine) hardware virtualization extensions required by hypervisors on AMD platforms |

[⬆ Back to Top](#table-of-contents)
---

## IOIntensive-M6-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `adjacent_cache_line_prefetch` | `disabled` | Controls whether the CPU prefetches the adjacent cache line alongside the requested line, improving sequential workload  |
| `hardware_prefetch` | `disabled` | Enables the hardware prefetcher in the DCU to speculatively fetch cache lines based on observed access patterns |
| `llc_prefetch` | `disabled` | Enables LLC prefetching from L2 to L3 cache to improve data availability for memory-bandwidth-intensive workloads |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `streamer_prefetch` | `disabled` | Enables the Intel DCU streamer prefetcher, which detects forward sequential access patterns and prefetches into L1 cache |

[⬆ Back to Top](#table-of-contents)
---

## IOIntensive-M8-AMD

| BIOS Key | Value | Description |
|---|---|---|
| `cbs_cmn_apbdis` | `1` | Disables the Automatic Power Budget management to give software full control over power limits |
| `cbs_cmn_apbdis_df_pstate_rs` | `0` | Controls APBDIS interaction with Data Fabric P-states on Rome/Milan platforms |
| `cbs_cmn_cpu_cpb` | `Auto` | Controls Core Performance Boost (AMD's Turbo), allowing cores to run above base clock when thermal headroom allows |
| `cbs_cmn_cpu_global_cstate_ctrl` | `Auto` | Enables or disables global CPU C-states, controlling whether the processor can enter deep power-saving states |
| `cbs_cmn_cpu_l1stream_hw_prefetcher` | `Auto` | Enables or disables the L1 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_cpu_l2stream_hw_prefetcher` | `Auto` | Enables or disables the L2 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_determinism_slider` | `Power` | Sets the performance-vs-power determinism trade-off; Performance maximizes throughput, Power maximizes efficiency |
| `cbs_cmn_efficiency_mode_en_rs` | `Maximum IO Performance Mode` | Enhanced Efficiency Mode control for Genoa/Bergamo, supporting High Performance and Efficiency mode profiles |
| `cbs_cmn_gnb_nb_iommu` | `Auto` | Enables the IOMMU in the northbridge/GNB for DMA isolation and SR-IOV support |
| `cbs_cmn_gnb_smu_df_cstates` | `disabled` | Controls Data Fabric C-states; disabling prevents the fabric from entering low-power states, reducing GPU/memory access latency |
| `cbs_cmn_gnb_smucppc` | `Auto` | Enables Collaborative Processor Performance Control (CPPC) via the SMU for OS-driven frequency scaling |
| `cbs_cpu_smt_ctrl` | `Auto` | Enables or disables Simultaneous Multi-Threading (SMT) on AMD processors |
| `cbs_df_cmn4link_max_xgmi_speed` | `Auto` | Sets the maximum xGMI link speed for 4-link configurations |
| `cbs_df_cmn_acpi_srat_l3numa` | `Auto` | Reports AMD L3 cache slices as separate NUMA domains in the ACPI SRAT table for OS topology awareness |
| `cbs_df_cmn_dram_nps` | `NPS4` | Sets NUMA Nodes Per Socket (NPS) to control how DRAM is presented as NUMA domains; NPS1=single domain, NPS4=four domains per socket |
| `cbs_df_cmn_mem_intlv_control` | `Auto` | Controls the memory interleave granularity for AMD platforms |
| `cpu_perf_enhancement` | `Disabled` | Enables Enhanced CPU Performance mode, applying additional microarchitecture optimizations for throughput |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `svm_mode` | `enabled` | Enables AMD SVM (Secure Virtual Machine) hardware virtualization extensions required by hypervisors on AMD platforms |

[⬆ Back to Top](#table-of-contents)
---

## JavaApplicationServer-M5-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `cpu_power_management` | `custom` | Sets the overall CPU power management policy (performance, energy-efficient, custom) controlling P-state and C-state beh |
| `intel_virtualization_technology` | `disabled` | Enables Intel VT-x hardware virtualization extensions required by hypervisors for guest VM isolation |
| `intel_vt_for_directed_io` | `disabled` | Enables Intel VT-d (Virtualization Technology for Directed I/O), providing IOMMU support for PCIe device assignment to V |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `processor_c1e` | `disabled` | Enables processor C1E (Enhanced Halt State) to reduce voltage and frequency when cores are halted |
| `processor_c6report` | `disabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |

[⬆ Back to Top](#table-of-contents)
---

## LowLatency-M5-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `cpu_power_management` | `custom` | Sets the overall CPU power management policy (performance, energy-efficient, custom) controlling P-state and C-state beh |
| `intel_hyper_threading_tech` | `disabled` | Enables Intel Hyper-Threading Technology, presenting each physical core as two logical threads to the OS |
| `intel_virtualization_technology` | `disabled` | Enables Intel VT-x hardware virtualization extensions required by hypervisors for guest VM isolation |
| `intel_vt_for_directed_io` | `disabled` | Enables Intel VT-d (Virtualization Technology for Directed I/O), providing IOMMU support for PCIe device assignment to V |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `processor_c1e` | `disabled` | Enables processor C1E (Enhanced Halt State) to reduce voltage and frequency when cores are halted |
| `processor_c6report` | `disabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |
| `work_load_config` | `Balanced` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |

[⬆ Back to Top](#table-of-contents)
---

## LowLatency-M6-AMD

| BIOS Key | Value | Description |
|---|---|---|
| `cbs_cmn_apbdis` | `Auto` | Disables the Automatic Power Budget management to give software full control over power limits |
| `cbs_cmn_cpu_cpb` | `disabled` | Controls Core Performance Boost (AMD's Turbo), allowing cores to run above base clock when thermal headroom allows |
| `cbs_cmn_cpu_global_cstate_ctrl` | `disabled` | Enables or disables global CPU C-states, controlling whether the processor can enter deep power-saving states |
| `cbs_cmn_cpu_l1stream_hw_prefetcher` | `Auto` | Enables or disables the L1 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_cpu_l2stream_hw_prefetcher` | `Auto` | Enables or disables the L2 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_determinism_slider` | `Power` | Sets the performance-vs-power determinism trade-off; Performance maximizes throughput, Power maximizes efficiency |
| `cbs_cmn_efficiency_mode_en` | `Auto` | Enables Efficiency Mode to optimize the processor for power-efficient operation at the cost of peak performance |
| `cbs_cmn_fixed_soc_pstate` | `Auto` | Pins the SoC (data fabric/IO) to a fixed P-state for deterministic I/O and memory latency |
| `cbs_cmn_gnb_nb_iommu` | `disabled` | Enables the IOMMU in the northbridge/GNB for DMA isolation and SR-IOV support |
| `cbs_cpu_smt_ctrl` | `disabled` | Enables or disables Simultaneous Multi-Threading (SMT) on AMD processors |
| `cbs_df_cmn_acpi_srat_l3numa` | `Auto` | Reports AMD L3 cache slices as separate NUMA domains in the ACPI SRAT table for OS topology awareness |
| `cbs_df_cmn_dram_nps` | `Auto` | Sets NUMA Nodes Per Socket (NPS) to control how DRAM is presented as NUMA domains; NPS1=single domain, NPS4=four domains per socket |
| `cisco_xgmi_max_speed` | `disabled` | Enables or disables Cisco control over xGMI maximum link speed for inter-socket GPU fabric |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `svm_mode` | `enabled` | Enables AMD SVM (Secure Virtual Machine) hardware virtualization extensions required by hypervisors on AMD platforms |

[⬆ Back to Top](#table-of-contents)
---

## LowLatency-M6-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `cpu_performance` | `enterprise` | Sets the CPU performance profile (enterprise, high-throughput, HPC) controlling prefetcher, turbo, and bandwidth setting |
| `energy_efficient_turbo` | `enabled` | Enables Intel Energy Efficient Turbo, which limits maximum turbo frequency to balance performance and power consumption |
| `intel_turbo_boost_tech` | `disabled` | Enables Intel Turbo Boost Technology, allowing cores to run above the rated base clock frequency when thermal and power  |
| `intel_virtualization_technology` | `disabled` | Enables Intel VT-x hardware virtualization extensions required by hypervisors for guest VM isolation |
| `intel_vt_for_directed_io` | `disabled` | Enables Intel VT-d (Virtualization Technology for Directed I/O), providing IOMMU support for PCIe device assignment to V |
| `memory_refresh_rate` | `1x Refresh` | Sets the DRAM refresh rate (1x or 2x) to balance power savings and memory reliability at elevated temperatures |
| `patrol_scrub` | `disabled` | Enables background patrol scrubbing of DRAM to proactively detect and correct ECC errors before they accumulate |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `work_load_config` | `Balanced` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |

[⬆ Back to Top](#table-of-contents)
---

## LowLatency-M7-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `intel_hyper_threading_tech` | `disabled` | Enables Intel Hyper-Threading Technology, presenting each physical core as two logical threads to the OS |
| `intel_turbo_boost_tech` | `disabled` | Enables Intel Turbo Boost Technology, allowing cores to run above the rated base clock frequency when thermal and power  |
| `intel_virtualization_technology` | `disabled` | Enables Intel VT-x hardware virtualization extensions required by hypervisors for guest VM isolation |
| `intel_vt_for_directed_io` | `disabled` | Enables Intel VT-d (Virtualization Technology for Directed I/O), providing IOMMU support for PCIe device assignment to V |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `work_load_config` | `Balanced` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |

[⬆ Back to Top](#table-of-contents)
---

## LowLatency-M8-AMD

| BIOS Key | Value | Description |
|---|---|---|
| `cbs_cmn_apbdis` | `Auto` | Disables the Automatic Power Budget management to give software full control over power limits |
| `cbs_cmn_apbdis_df_pstate_rs` | `0` | Controls APBDIS interaction with Data Fabric P-states on Rome/Milan platforms |
| `cbs_cmn_cpu_cpb` | `disabled` | Controls Core Performance Boost (AMD's Turbo), allowing cores to run above base clock when thermal headroom allows |
| `cbs_cmn_cpu_global_cstate_ctrl` | `Auto` | Enables or disables global CPU C-states, controlling whether the processor can enter deep power-saving states |
| `cbs_cmn_cpu_l1stream_hw_prefetcher` | `Auto` | Enables or disables the L1 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_cpu_l2stream_hw_prefetcher` | `Auto` | Enables or disables the L2 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_determinism_slider` | `Performance` | Sets the performance-vs-power determinism trade-off; Performance maximizes throughput, Power maximizes efficiency |
| `cbs_cmn_efficiency_mode_en_rs` | `High Performance Mode` | Enhanced Efficiency Mode control for Genoa/Bergamo, supporting High Performance and Efficiency mode profiles |
| `cbs_cmn_gnb_nb_iommu` | `disabled` | Enables the IOMMU in the northbridge/GNB for DMA isolation and SR-IOV support |
| `cbs_cmn_gnb_smu_df_cstates` | `disabled` | Controls Data Fabric C-states; disabling prevents the fabric from entering low-power states, reducing GPU/memory access latency |
| `cbs_cmn_gnb_smucppc` | `Auto` | Enables Collaborative Processor Performance Control (CPPC) via the SMU for OS-driven frequency scaling |
| `cbs_cpu_smt_ctrl` | `disabled` | Enables or disables Simultaneous Multi-Threading (SMT) on AMD processors |
| `cbs_df_cmn4link_max_xgmi_speed` | `Auto` | Sets the maximum xGMI link speed for 4-link configurations |
| `cbs_df_cmn_acpi_srat_l3numa` | `Auto` | Reports AMD L3 cache slices as separate NUMA domains in the ACPI SRAT table for OS topology awareness |
| `cbs_df_cmn_dram_nps` | `Auto` | Sets NUMA Nodes Per Socket (NPS) to control how DRAM is presented as NUMA domains; NPS1=single domain, NPS4=four domains per socket |
| `cbs_df_cmn_mem_intlv_control` | `disabled` | Controls the memory interleave granularity for AMD platforms |
| `cpu_perf_enhancement` | `Disabled` | Enables Enhanced CPU Performance mode, applying additional microarchitecture optimizations for throughput |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `svm_mode` | `disabled` | Enables AMD SVM (Secure Virtual Machine) hardware virtualization extensions required by hypervisors on AMD platforms |

[⬆ Back to Top](#table-of-contents)
---

## LowLatency-M8-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `adjacent_cache_line_prefetch` | `disabled` | Controls whether the CPU prefetches the adjacent cache line alongside the requested line, improving sequential workload  |
| `epp_profile` | `Balanced Power` | Sets the default EPP profile (Performance, Balanced Performance, Balanced Power, Power) used for hardware-guided P-state |
| `intel_hyper_threading_tech` | `disabled` | Enables Intel Hyper-Threading Technology, presenting each physical core as two logical threads to the OS |
| `intel_turbo_boost_tech` | `disabled` | Enables Intel Turbo Boost Technology, allowing cores to run above the rated base clock frequency when thermal and power  |
| `intel_virtualization_technology` | `disabled` | Enables Intel VT-x hardware virtualization extensions required by hypervisors for guest VM isolation |
| `pwr_perf_tuning` | `bios` | Controls whether BIOS, OS, or PECI manages power/performance tuning bias |
| `select_memory_ras_configuration` | `adddc-sparing` | Selects the memory RAS configuration (JBOD, Mirror, Lockstep, Sparing) for fault tolerance |
| `streamer_prefetch` | `disabled` | Enables the Intel DCU streamer prefetcher, which detects forward sequential access patterns and prefetches into L1 cache |
| `work_load_config` | `Balanced` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |

[⬆ Back to Top](#table-of-contents)
---

## M5-amd-virtual

| BIOS Key | Value | Description |
|---|---|---|
| `cpu_power_management` | `custom` | Sets the overall CPU power management policy (performance, energy-efficient, custom) controlling P-state and C-state beh |
| `nvmdimm_perform_config` | `Balanced Profile` | Sets the performance profile for Intel Optane NVDIMMs (Bandwidth Optimized, Latency Optimized, Balanced) |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `processor_c1e` | `disabled` | Enables processor C1E (Enhanced Halt State) to reduce voltage and frequency when cores are halted |
| `processor_c3report` | `disabled` | Enables the processor to report C3 state to the OS via ACPI for power management coordination |
| `processor_c6report` | `disabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |
| `processor_cstate` | `disabled` | Enables CPU C-state support globally, allowing processors to enter low-power states when idle |

[⬆ Back to Top](#table-of-contents)
---

## M5-intel-virtual

| BIOS Key | Value | Description |
|---|---|---|
| `cpu_power_management` | `custom` | Sets the overall CPU power management policy (performance, energy-efficient, custom) controlling P-state and C-state beh |
| `nvmdimm_perform_config` | `Balanced Profile` | Sets the performance profile for Intel Optane NVDIMMs (Bandwidth Optimized, Latency Optimized, Balanced) |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `processor_c1e` | `disabled` | Enables processor C1E (Enhanced Halt State) to reduce voltage and frequency when cores are halted |
| `processor_c3report` | `disabled` | Enables the processor to report C3 state to the OS via ACPI for power management coordination |
| `processor_c6report` | `disabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |
| `processor_cstate` | `disabled` | Enables CPU C-state support globally, allowing processors to enter low-power states when idle |
| `txt_support` | `enabled` | Enables Intel Trusted Execution Technology (TXT/TPM), providing hardware-based measured launch environment for server at |

[⬆ Back to Top](#table-of-contents)
---

## M6-amd-virtual

| BIOS Key | Value | Description |
|---|---|---|
| `cbs_cmn_fixed_soc_pstate` | `P0` | Pins the SoC (data fabric/IO) to a fixed P-state for deterministic I/O and memory latency |
| `cbs_df_cmn_acpi_srat_l3numa` | `enabled` | Reports AMD L3 cache slices as separate NUMA domains in the ACPI SRAT table for OS topology awareness |
| `cbs_df_cmn_dram_nps` | `NPS4` | Sets NUMA Nodes Per Socket (NPS) to control how DRAM is presented as NUMA domains; NPS1=single domain, NPS4=four domains per socket |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |

[⬆ Back to Top](#table-of-contents)
---

## M6-intel-virtual

| BIOS Key | Value | Description |
|---|---|---|
| `cpu_perf_enhancement` | `Auto` | Enables Enhanced CPU Performance mode, applying additional microarchitecture optimizations for throughput |
| `energy_efficient_turbo` | `enabled` | Enables Intel Energy Efficient Turbo, which limits maximum turbo frequency to balance performance and power consumption |
| `nvmdimm_perform_config` | `Balanced Profile` | Sets the performance profile for Intel Optane NVDIMMs (Bandwidth Optimized, Latency Optimized, Balanced) |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `processor_c1e` | `enabled` | Enables processor C1E (Enhanced Halt State) to reduce voltage and frequency when cores are halted |
| `processor_c6report` | `enabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |
| `txt_support` | `enabled` | Enables Intel Trusted Execution Technology (TXT/TPM), providing hardware-based measured launch environment for server at |

[⬆ Back to Top](#table-of-contents)
---

## MLPerf-Inference-C885A-M8-AMD

| BIOS Key | Value | Description |
|---|---|---|
| `cbs_cmn_apbdis` | `1` | Disables the Automatic Power Budget management to give software full control over power limits |
| `cbs_cmn_cpu_global_cstate_ctrl` | `Auto` | Enables or disables global CPU C-states, controlling whether the processor can enter deep power-saving states |
| `cbs_cmn_determinism_slider` | `Power` | Sets the performance-vs-power determinism trade-off; Performance maximizes throughput, Power maximizes efficiency |
| `cbs_cmn_gnb_nb_iommu` | `Enabled` | Enables the IOMMU in the northbridge/GNB for DMA isolation and SR-IOV support |
| `cbs_cmn_gnb_smu_df_cstates` | `Auto` | Controls Data Fabric C-states; disabling prevents the fabric from entering low-power states, reducing GPU/memory access latency |
| `cbs_cpu_smt_ctrl` | `Enable` | Enables or disables Simultaneous Multi-Threading (SMT) on AMD processors |
| `cbs_df_cmn4link_max_xgmi_speed` | `32Gbps` | Sets the maximum xGMI link speed for 4-link configurations |
| `cbs_df_cmn_dram_nps` | `NPS4` | Sets NUMA Nodes Per Socket (NPS) to control how DRAM is presented as NUMA domains; NPS1=single domain, NPS4=four domains per socket |
| `cbs_df_cmn_mem_intlv` | `Auto` | Controls AMD memory interleaving across channels, dies, and sockets for bandwidth optimization |
| `sha384pcr_bank` | `Enabled` | Enables the SHA-384 PCR bank in the TPM for higher-security measured boot |
| `terminal_type` | `VT-UTF8` | Sets the terminal emulation type for serial console redirection (VT100, VT100+, VT-UTF8, PC-ANSI) |

[⬆ Back to Top](#table-of-contents)
---

## MaximumPerformance-M5-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `cpu_power_management` | `custom` | Sets the overall CPU power management policy (performance, energy-efficient, custom) controlling P-state and C-state beh |
| `imc_interleave` | `1-way Interleave` | Sets the Intel memory controller interleave mode (1-way, 2-way, Auto) to distribute traffic across memory channels |
| `intel_virtualization_technology` | `disabled` | Enables Intel VT-x hardware virtualization extensions required by hypervisors for guest VM isolation |
| `intel_vt_for_directed_io` | `disabled` | Enables Intel VT-d (Virtualization Technology for Directed I/O), providing IOMMU support for PCIe device assignment to V |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `processor_c1e` | `disabled` | Enables processor C1E (Enhanced Halt State) to reduce voltage and frequency when cores are halted |
| `processor_c6report` | `disabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |
| `snc` | `enabled` | Enables Intel Sub-NUMA Clustering (SNC2 or SNC4), splitting the LLC and memory into sub-NUMA domains to reduce average m |
| `work_load_config` | `Balanced` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |

[⬆ Back to Top](#table-of-contents)
---

## OnlineTransactionProcessing-M5-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `cpu_power_management` | `custom` | Sets the overall CPU power management policy (performance, energy-efficient, custom) controlling P-state and C-state beh |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `processor_c1e` | `disabled` | Enables processor C1E (Enhanced Halt State) to reduce voltage and frequency when cores are halted |
| `processor_c6report` | `disabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |

[⬆ Back to Top](#table-of-contents)
---

## RDBMS-M8-AMD

| BIOS Key | Value | Description |
|---|---|---|
| `cbs_cmn_apbdis` | `1` | Disables the Automatic Power Budget management to give software full control over power limits |
| `cbs_cmn_apbdis_df_pstate_rs` | `0` | Controls APBDIS interaction with Data Fabric P-states on Rome/Milan platforms |
| `cbs_cmn_cpu_cpb` | `Auto` | Controls Core Performance Boost (AMD's Turbo), allowing cores to run above base clock when thermal headroom allows |
| `cbs_cmn_cpu_global_cstate_ctrl` | `Auto` | Enables or disables global CPU C-states, controlling whether the processor can enter deep power-saving states |
| `cbs_cmn_cpu_l1stream_hw_prefetcher` | `Auto` | Enables or disables the L1 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_cpu_l2stream_hw_prefetcher` | `Auto` | Enables or disables the L2 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_determinism_slider` | `Auto` | Sets the performance-vs-power determinism trade-off; Performance maximizes throughput, Power maximizes efficiency |
| `cbs_cmn_efficiency_mode_en_rs` | `Maximum IO Performance Mode` | Enhanced Efficiency Mode control for Genoa/Bergamo, supporting High Performance and Efficiency mode profiles |
| `cbs_cmn_gnb_nb_iommu` | `Auto` | Enables the IOMMU in the northbridge/GNB for DMA isolation and SR-IOV support |
| `cbs_cmn_gnb_smu_df_cstates` | `disabled` | Controls Data Fabric C-states; disabling prevents the fabric from entering low-power states, reducing GPU/memory access latency |
| `cbs_cmn_gnb_smucppc` | `Auto` | Enables Collaborative Processor Performance Control (CPPC) via the SMU for OS-driven frequency scaling |
| `cbs_cpu_smt_ctrl` | `enabled` | Enables or disables Simultaneous Multi-Threading (SMT) on AMD processors |
| `cbs_df_cmn4link_max_xgmi_speed` | `Auto` | Sets the maximum xGMI link speed for 4-link configurations |
| `cbs_df_cmn_acpi_srat_l3numa` | `Auto` | Reports AMD L3 cache slices as separate NUMA domains in the ACPI SRAT table for OS topology awareness |
| `cbs_df_cmn_dram_nps` | `NPS4` | Sets NUMA Nodes Per Socket (NPS) to control how DRAM is presented as NUMA domains; NPS1=single domain, NPS4=four domains per socket |
| `cbs_df_cmn_mem_intlv_control` | `Auto` | Controls the memory interleave granularity for AMD platforms |
| `cpu_perf_enhancement` | `Disabled` | Enables Enhanced CPU Performance mode, applying additional microarchitecture optimizations for throughput |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |

[⬆ Back to Top](#table-of-contents)
---

## RDBMS-M8-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `cpu_perf_enhancement` | `Auto` | Enables Enhanced CPU Performance mode, applying additional microarchitecture optimizations for throughput |
| `cpu_performance` | `enterprise` | Sets the CPU performance profile (enterprise, high-throughput, HPC) controlling prefetcher, turbo, and bandwidth setting |
| `energy_efficient_turbo` | `enabled` | Enables Intel Energy Efficient Turbo, which limits maximum turbo frequency to balance performance and power consumption |
| `epp_profile` | `Performance` | Sets the default EPP profile (Performance, Balanced Performance, Balanced Power, Power) used for hardware-guided P-state |
| `intel_virtualization_technology` | `disabled` | Enables Intel VT-x hardware virtualization extensions required by hypervisors for guest VM isolation |
| `latency_optimized_mode` | `enabled` | Enables latency-optimized memory mode on platforms that support it, reducing worst-case memory access time |
| `llc_alloc` | `disabled` | Controls Intel LLC (Last Level Cache) dead-line allocation, determining whether lines with no future reuse are placed in |
| `llc_prefetch` | `disabled` | Enables LLC prefetching from L2 to L3 cache to improve data availability for memory-bandwidth-intensive workloads |
| `patrol_scrub` | `disabled` | Enables background patrol scrubbing of DRAM to proactively detect and correct ECC errors before they accumulate |
| `processor_c1e` | `disabled` | Enables processor C1E (Enhanced Halt State) to reduce voltage and frequency when cores are halted |
| `pwr_perf_tuning` | `bios` | Controls whether BIOS, OS, or PECI manages power/performance tuning bias |
| `select_memory_ras_configuration` | `adddc-sparing` | Selects the memory RAS configuration (JBOD, Mirror, Lockstep, Sparing) for fault tolerance |
| `snc` | `enabled` | Enables Intel Sub-NUMA Clustering (SNC2 or SNC4), splitting the LLC and memory into sub-NUMA domains to reduce average m |

[⬆ Back to Top](#table-of-contents)
---

## RelationalDatabaseSystems-M6-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `cpu_perf_enhancement` | `Auto` | Enables Enhanced CPU Performance mode, applying additional microarchitecture optimizations for throughput |
| `llc_alloc` | `disabled` | Controls Intel LLC (Last Level Cache) dead-line allocation, determining whether lines with no future reuse are placed in |
| `llc_prefetch` | `disabled` | Enables LLC prefetching from L2 to L3 cache to improve data availability for memory-bandwidth-intensive workloads |
| `memory_refresh_rate` | `1x Refresh` | Sets the DRAM refresh rate (1x or 2x) to balance power savings and memory reliability at elevated temperatures |
| `patrol_scrub` | `disabled` | Enables background patrol scrubbing of DRAM to proactively detect and correct ECC errors before they accumulate |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `processor_c6report` | `enabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |
| `snc` | `enabled` | Enables Intel Sub-NUMA Clustering (SNC2 or SNC4), splitting the LLC and memory into sub-NUMA domains to reduce average m |
| `upi_power_management` | `enabled` | Enables Intel UPI link power management to reduce idle power consumption on inter-socket links |
| `xpt_prefetch` | `enabled` | Enables Intel XPT (Cross Package Transfer) prefetch to speculatively fetch data across NUMA domains for remote memory ac |

[⬆ Back to Top](#table-of-contents)
---

## RelationalDatabaseSystems-M7-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `llc_alloc` | `disabled` | Controls Intel LLC (Last Level Cache) dead-line allocation, determining whether lines with no future reuse are placed in |
| `llc_prefetch` | `disabled` | Enables LLC prefetching from L2 to L3 cache to improve data availability for memory-bandwidth-intensive workloads |
| `patrol_scrub` | `disabled` | Enables background patrol scrubbing of DRAM to proactively detect and correct ECC errors before they accumulate |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `snc` | `Auto` | Enables Intel Sub-NUMA Clustering (SNC2 or SNC4), splitting the LLC and memory into sub-NUMA domains to reduce average m |
| `xpt_prefetch` | `enabled` | Enables Intel XPT (Cross Package Transfer) prefetch to speculatively fetch data across NUMA domains for remote memory ac |

[⬆ Back to Top](#table-of-contents)
---

## SystemDefault

_No BIOS tokens are overridden (system defaults apply)._

---

## UnifiedEdgeBios

_No BIOS tokens are overridden (system defaults apply)._

---

## VDI-M6-AMD

| BIOS Key | Value | Description |
|---|---|---|
| `cbs_cmn_apbdis` | `1` | Disables the Automatic Power Budget management to give software full control over power limits |
| `cbs_cmn_cpu_cpb` | `Auto` | Controls Core Performance Boost (AMD's Turbo), allowing cores to run above base clock when thermal headroom allows |
| `cbs_cmn_cpu_global_cstate_ctrl` | `disabled` | Enables or disables global CPU C-states, controlling whether the processor can enter deep power-saving states |
| `cbs_cmn_cpu_l1stream_hw_prefetcher` | `Auto` | Enables or disables the L1 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_cpu_l2stream_hw_prefetcher` | `Auto` | Enables or disables the L2 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_determinism_slider` | `Power` | Sets the performance-vs-power determinism trade-off; Performance maximizes throughput, Power maximizes efficiency |
| `cbs_cmn_efficiency_mode_en` | `Auto` | Enables Efficiency Mode to optimize the processor for power-efficient operation at the cost of peak performance |
| `cbs_cmn_fixed_soc_pstate` | `P0` | Pins the SoC (data fabric/IO) to a fixed P-state for deterministic I/O and memory latency |
| `cbs_cmn_gnb_nb_iommu` | `Auto` | Enables the IOMMU in the northbridge/GNB for DMA isolation and SR-IOV support |
| `cbs_cpu_smt_ctrl` | `Auto` | Enables or disables Simultaneous Multi-Threading (SMT) on AMD processors |
| `cbs_df_cmn_acpi_srat_l3numa` | `enabled` | Reports AMD L3 cache slices as separate NUMA domains in the ACPI SRAT table for OS topology awareness |
| `cbs_df_cmn_dram_nps` | `NPS4` | Sets NUMA Nodes Per Socket (NPS) to control how DRAM is presented as NUMA domains; NPS1=single domain, NPS4=four domains per socket |
| `cisco_xgmi_max_speed` | `enabled` | Enables or disables Cisco control over xGMI maximum link speed for inter-socket GPU fabric |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `svm_mode` | `enabled` | Enables AMD SVM (Secure Virtual Machine) hardware virtualization extensions required by hypervisors on AMD platforms |

[⬆ Back to Top](#table-of-contents)
---

## Virtualization-M5-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `cpu_power_management` | `custom` | Sets the overall CPU power management policy (performance, energy-efficient, custom) controlling P-state and C-state beh |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `processor_c1e` | `disabled` | Enables processor C1E (Enhanced Halt State) to reduce voltage and frequency when cores are halted |
| `processor_c6report` | `disabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |

[⬆ Back to Top](#table-of-contents)
---

## Virtualization-M6-AMD

| BIOS Key | Value | Description |
|---|---|---|
| `cbs_cmn_apbdis` | `1` | Disables the Automatic Power Budget management to give software full control over power limits |
| `cbs_cmn_cpu_cpb` | `Auto` | Controls Core Performance Boost (AMD's Turbo), allowing cores to run above base clock when thermal headroom allows |
| `cbs_cmn_cpu_global_cstate_ctrl` | `Auto` | Enables or disables global CPU C-states, controlling whether the processor can enter deep power-saving states |
| `cbs_cmn_cpu_l1stream_hw_prefetcher` | `Auto` | Enables or disables the L1 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_cpu_l2stream_hw_prefetcher` | `Auto` | Enables or disables the L2 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_determinism_slider` | `Power` | Sets the performance-vs-power determinism trade-off; Performance maximizes throughput, Power maximizes efficiency |
| `cbs_cmn_efficiency_mode_en` | `Auto` | Enables Efficiency Mode to optimize the processor for power-efficient operation at the cost of peak performance |
| `cbs_cmn_fixed_soc_pstate` | `P0` | Pins the SoC (data fabric/IO) to a fixed P-state for deterministic I/O and memory latency |
| `cbs_cmn_gnb_nb_iommu` | `Auto` | Enables the IOMMU in the northbridge/GNB for DMA isolation and SR-IOV support |
| `cbs_cpu_smt_ctrl` | `Auto` | Enables or disables Simultaneous Multi-Threading (SMT) on AMD processors |
| `cbs_df_cmn_acpi_srat_l3numa` | `enabled` | Reports AMD L3 cache slices as separate NUMA domains in the ACPI SRAT table for OS topology awareness |
| `cbs_df_cmn_dram_nps` | `NPS4` | Sets NUMA Nodes Per Socket (NPS) to control how DRAM is presented as NUMA domains; NPS1=single domain, NPS4=four domains per socket |
| `cisco_xgmi_max_speed` | `disabled` | Enables or disables Cisco control over xGMI maximum link speed for inter-socket GPU fabric |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `svm_mode` | `enabled` | Enables AMD SVM (Secure Virtual Machine) hardware virtualization extensions required by hypervisors on AMD platforms |

[⬆ Back to Top](#table-of-contents)
---

## Virtualization-M6-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `cpu_perf_enhancement` | `Auto` | Enables Enhanced CPU Performance mode, applying additional microarchitecture optimizations for throughput |
| `energy_efficient_turbo` | `enabled` | Enables Intel Energy Efficient Turbo, which limits maximum turbo frequency to balance performance and power consumption |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `processor_c1e` | `enabled` | Enables processor C1E (Enhanced Halt State) to reduce voltage and frequency when cores are halted |
| `processor_c6report` | `enabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |

[⬆ Back to Top](#table-of-contents)
---

## Virtualization-M7-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |
| `processor_c6report` | `enabled` | Enables the processor to report C6 state to the OS, allowing deep power reduction when cores are idle |
| `work_load_config` | `Balanced` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |

[⬆ Back to Top](#table-of-contents)
---

## Virtualization-M8-AMD

| BIOS Key | Value | Description |
|---|---|---|
| `cbs_cmn_apbdis` | `0` | Disables the Automatic Power Budget management to give software full control over power limits |
| `cbs_cmn_apbdis_df_pstate_rs` | `0` | Controls APBDIS interaction with Data Fabric P-states on Rome/Milan platforms |
| `cbs_cmn_cpu_cpb` | `Auto` | Controls Core Performance Boost (AMD's Turbo), allowing cores to run above base clock when thermal headroom allows |
| `cbs_cmn_cpu_global_cstate_ctrl` | `Auto` | Enables or disables global CPU C-states, controlling whether the processor can enter deep power-saving states |
| `cbs_cmn_cpu_l1stream_hw_prefetcher` | `Auto` | Enables or disables the L1 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_cpu_l2stream_hw_prefetcher` | `Auto` | Enables or disables the L2 stream hardware prefetcher for predictive data loading |
| `cbs_cmn_determinism_slider` | `Power` | Sets the performance-vs-power determinism trade-off; Performance maximizes throughput, Power maximizes efficiency |
| `cbs_cmn_efficiency_mode_en_rs` | `High Performance Mode` | Enhanced Efficiency Mode control for Genoa/Bergamo, supporting High Performance and Efficiency mode profiles |
| `cbs_cmn_gnb_nb_iommu` | `Auto` | Enables the IOMMU in the northbridge/GNB for DMA isolation and SR-IOV support |
| `cbs_cmn_gnb_smu_df_cstates` | `Auto` | Controls Data Fabric C-states; disabling prevents the fabric from entering low-power states, reducing GPU/memory access latency |
| `cbs_cmn_gnb_smucppc` | `enabled` | Enables Collaborative Processor Performance Control (CPPC) via the SMU for OS-driven frequency scaling |
| `cbs_cpu_smt_ctrl` | `enabled` | Enables or disables Simultaneous Multi-Threading (SMT) on AMD processors |
| `cbs_df_cmn4link_max_xgmi_speed` | `Auto` | Sets the maximum xGMI link speed for 4-link configurations |
| `cbs_df_cmn_acpi_srat_l3numa` | `Auto` | Reports AMD L3 cache slices as separate NUMA domains in the ACPI SRAT table for OS topology awareness |
| `cbs_df_cmn_dram_nps` | `Auto` | Sets NUMA Nodes Per Socket (NPS) to control how DRAM is presented as NUMA domains; NPS1=single domain, NPS4=four domains per socket |
| `cbs_df_cmn_mem_intlv_control` | `Auto` | Controls the memory interleave granularity for AMD platforms |
| `cpu_perf_enhancement` | `Disabled` | Enables Enhanced CPU Performance mode, applying additional microarchitecture optimizations for throughput |
| `pcie_slots_cdn_enable` | `enabled` | Enables Consistent Device Naming for PCIe expansion slots |

[⬆ Back to Top](#table-of-contents)
---

## Virtualization-M8-Intel

| BIOS Key | Value | Description |
|---|---|---|
| `cpu_performance` | `enterprise` | Sets the CPU performance profile (enterprise, high-throughput, HPC) controlling prefetcher, turbo, and bandwidth setting |
| `energy_efficient_turbo` | `enabled` | Enables Intel Energy Efficient Turbo, which limits maximum turbo frequency to balance performance and power consumption |
| `epp_profile` | `Performance` | Sets the default EPP profile (Performance, Balanced Performance, Balanced Power, Power) used for hardware-guided P-state |
| `latency_optimized_mode` | `enabled` | Enables latency-optimized memory mode on platforms that support it, reducing worst-case memory access time |
| `processor_c1e` | `disabled` | Enables processor C1E (Enhanced Halt State) to reduce voltage and frequency when cores are halted |
| `pwr_perf_tuning` | `bios` | Controls whether BIOS, OS, or PECI manages power/performance tuning bias |
| `select_memory_ras_configuration` | `adddc-sparing` | Selects the memory RAS configuration (JBOD, Mirror, Lockstep, Sparing) for fault tolerance |
| `work_load_config` | `Balanced` | Sets the platform workload configuration hint (Balanced, I/O Sensitive, NUMA, UMA) to tune CPU-to-memory topology |

[⬆ Back to Top](#table-of-contents)
---

## tpm

| BIOS Key | Value | Description |
|---|---|---|
| `sha1pcr_bank` | `disabled` | Enables the SHA-1 PCR bank in the TPM for legacy measured boot support |
| `sha256pcr_bank` | `enabled` | Enables the SHA-256 PCR bank in the TPM for secure boot measurements |
| `tpm_control` | `enabled` | Enables or disables the Trusted Platform Module (TPM) security chip |
| `tpm_ppi_required` | `enabled` | Controls whether physical presence confirmation is required for TPM operations |
| `tpm_support` | `enabled` | Enables Security Device (TPM) support, making the TPM visible to the OS and UEFI Secure Boot |

[⬆ Back to Top](#table-of-contents)
---

## tpm_disabled

| BIOS Key | Value | Description |
|---|---|---|
| `tpm_control` | `disabled` | Enables or disables the Trusted Platform Module (TPM) security chip |
| `tpm_support` | `disabled` | Enables Security Device (TPM) support, making the TPM visible to the OS and UEFI Secure Boot |

[⬆ Back to Top](#table-of-contents)