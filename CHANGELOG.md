# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog.

## [Unreleased]

## [0.1.19] - 2026-11-17

### Fixed
- DNS Manager: with "Use LDAP settings from Shared Services" the Passwords and secrets panel shows the Shared Services bind password as stored (entered on Initial Inventory) instead of asking for a separate Active Directory password; separate AD username/password fields appear only when shared LDAP is not used.

### Changed
- The Initial Inventory save message lists DNS Manager among the pages that pre-fill from it.

## [0.1.18] - 2026-11-17

### Fixed
- DNS Manager now reads the OpenShift install file, Everpure file, and Initial Inventory from the active environment (any environment name) instead of paths that only existed in a development checkout, so Generate Configuration finds the records on an installed appliance.
- Hostnames without a domain use the OpenShift base domain, then the Active Directory domain from Shared Services; hostnames that are already FQDNs are kept.
- Generate Configuration no longer inserts `example.com` placeholder records when nothing is found; it warns instead.
- The Shared Services LDAP bind password is no longer reported as missing: the DNS Manager page shows whether it is stored, and the Active Directory username and password fields are optional and default to the Shared Services bind account.
- Passwords and secrets lists only the credentials for the provider in the saved DNS configuration.

## [0.1.17] - 2026-11-17

### Fixed
- v0.1.16 could not be installed: `requirements.txt` pinned `ldap3>=4.1.0`, which does not exist (latest is 2.9.1), so `setup.sh` failed and the UI stayed down. It now requires `ldap3>=2.9.1`.
- Removed `pyad` from `requirements.txt`; it is Windows-only and unused.
- v0.1.16 shipped UI runtime data under `scripts/deployments/` (an example environment's DHCP, Initial Inventory, and site settings). It is no longer tracked and `scripts/deployments/` and `scripts/jobs/` are ignored.

## [0.1.16] - 2026-11-17

### Added
- **DNS Manager**: Web UI page and `scripts/dns_updater.py` to compare DNS records built from the OpenShift install, Initial Inventory, and Everpure inventories with Active Directory, Infoblox, BlueCat, Efficient IP, or BIND DNS. The schema (`dns_manager.json`) documents Required and Optional attributes for every provider.
- Pre-installation DNS validation (`scripts/dns_validator.py`) of node, API, and wildcard names before an OpenShift install.
- Active Directory validation queries the AD DNS server for each expected record and reports matching and missing records. Credentials come from the web UI vault; the Shared Services LDAP bind password is reused with shared LDAP settings.

### Fixed
- DNS Manager Validate and Synchronize buttons did nothing because the saved configuration was looked up in the wrong folder; they now run, and the updater reads the `dns.providers` / `dns.records` structure the UI writes.
- Generated DNS provider YAML no longer contains an unresolved `password` placeholder.
- Read activation workflow lookup and polling responses without configuration-object caching, avoiding an unhashable DotMap error while preserving workflow failure checks.

### Changed
- Synchronize stops with a "not implemented" error and makes no DNS changes: writing records is not implemented for any provider yet. Use Validate to see missing records.
- Move Intersight troubleshooting controls into a collapsed panel inside Automation on System (Orgs), UCS Domains, and UCS Servers; preserve per-page debug settings.

## [0.1.15] - 2026-11-16

### Added
- **Corrected BIOS and Adapter Template Checker**: Rewritten with correct Intersight API endpoints (bios/Policies, vnic/EthAdapterPolicies, vnic/FcAdapterPolicies).
  - Templates identified via organization filter (Moid: 5ddfd9ff6972652d31ee6582), not separate endpoints.
  - Discovers 49 BIOS templates (475 attributes), 23 Ethernet Adapter templates (18 attributes), 9 FC Adapter templates (13 attributes).
  - Generates JSON and Markdown reports for schema validation and compliance checking.
- **Platform-Specific Policy Attributes** for UCS Domain vs Unified Edge distinction:
  - Switch Control: LldpSettings, MacLearningSettings (UCS Domain + End Host mode), StpSettings.
  - VLAN Policy: AutoAllowOnInterSwitchPorts, AutoAllowOnSecureRouterRoles.
  - Pattern documented in POLICY_TEMPLATE_PATTERN.md for future policy enhancements.
- **Enhanced Attribute Filtering** in template difference checker:
  - Policy-specific exclusions (IsAesPrimaryKeySet for switch_control, etc.).
  - Proper handling of reference objects and read-only attributes.
  - Improved accuracy for compliance gap reporting.

### Fixed
- API endpoint mappings in template checker (critical):
  - BIOS: use bios/Policies (not compute/BiosProfileTemplates).
  - Ethernet Adapter: use vnic/EthAdapterPolicies (not ether/AdapterProfileTemplates).
  - FC Adapter: use vnic/FcAdapterPolicies (not fc/AdapterProfileTemplates).
  - Eliminated 403 errors and invalid compliance reports.
- JSON attribute extraction depth handling to capture only top-level attributes.
- Reference object filtering to exclude Profiles, Groups, Providers from compliance gaps.

### Changed
- Removed incorrect template objects checker (check_template_objects.py).
- Separated concerns: check_bios_adapter_templates.py handles template discovery and reporting.

## [0.1.14] - 2026-11-14

### Added
- **Template Difference Checker**: Standalone maintenance tool to analyze and report differences between local Jinja2 templates and Intersight API schemas.
  - Automatic template discovery across policies, pools, profiles, templates, and system configurations.
  - Multi-format report generation: JSON (machine-parseable), CSV (spreadsheet), Markdown (human-readable).
  - Bidirectional analysis identifying attributes missing in API or templates.
  - Console summary with sorted issue priority.
  - Verbose logging for detailed execution tracking.
- Framework for future Feature 2 (Dynamic Payload Adapter) integration with live API schema queries.
- 37 comprehensive unit tests covering template analysis, API schema handling, comparisons, and all report formats.
- Complete documentation for template difference checker tool (TEMPLATE_DIFFERENCE_CHECKER.md).

### Features
- **Template Analysis**: Extracts Jinja2 variables and JSON attributes from 100+ templates using AST and regex.
- **Category-Based Scanning**: Analyzes policies (78), pools (9), profiles (4), templates (8), and system (5) configurations.
- **Match Ratio Calculation**: Computes alignment percentage between template and API attributes.
- **Batch Processing**: Analyzes all 104 templates in <1 second with <50 MB memory.
- **Extensible Design**: Ready for live API integration and dynamic filtering in future releases.

## [0.1.13] - 2026-11-14

### Added
- PCIe Connectivity Policy firmware validation: check mode now validates that server firmware meets minimum requirement (6.0(1.252039)) before deploying PCIe connectivity policies.
- Firmware version comparison and validation module for semantic version checking.
- Comprehensive unit tests for firmware validation (20 test cases covering edge cases and error conditions).
- Clear warning documentation in X-Series compute policy examples highlighting PCIe firmware requirements.
- Formatted compatibility reports displayed at end of check mode logs for high visibility.

### Fixed
- Server firmware incompatibility detection during check mode prevents failed deployments due to PCIe policy firmware conflicts.

## [0.1.12] - 2026-11-12

### Added
- Per-page Intersight API debug level controls for GUI validation and deployment, including full level 7 output in job logs.
- Deployment wrapper `-dl` / `--debug-level` forwarding for scoped and complete Intersight runs.

### Fixed
- Associated server profiles inconsistent only because of `Not-activated` proceed to activation instead of failing deployment.
- Check for pending server activation after deployment, including changes introduced by deployment; activation failures still stop template synchronization.

## [0.1.7] - 2026-11-11

### Added
- PCIe connectivity policies: configurable CPU-to-GPU mappings and optional SmartNICs, with schema validation and server profile/template references.
- Post-deployment template synchronization for attached server and domain profiles, including A/B switch profiles.
- Chassis template-policy inheritance verification and reconciliation.

### Changed
- Redeploy synchronized profile changes once, activate pending server changes, and verify synchronization afterward.
- Deployment, activation, and synchronization failures or timeouts stop the run instead of reporting success.
- Check mode and detached profiles remain non-mutating; template-driven redeployment can require a server reboot.

## [0.1.6] - 2026-11-11

### Changed
- Intersight automatic tags use `managed-by: cisco-ai-pods` and `release: <VERSION>` instead of script-name/version keys.
- Runtime tags and bundled schema release metadata read VERSION rather than a duplicated schema version.
- Release validation rejects bundled `x-schema-version` values that do not match VERSION.

## [0.1.5] - 2026-11-11

### Fixed
- System (Orgs): deploy standalone organizations and resource groups without requiring organization-scoped policies or profiles.
- UI updates: create the log directory before starting the updater and wait for successful process execution.
- UI updates: report launcher failures with a journal command for diagnosis.

## [0.1.4] - 2026-11-11

### Added
- Initial Inventory: duplicate selected rows with fresh row IDs while preserving field values.
- Appliance builds: load build credentials from Ansible Vault and hash the temporary OS password via stdin.
- Appliance image: include tmux and configure sudo to find appliance tools in `/usr/local/sbin`.

### Fixed
- Claim Targets: accept FI and CIMC passwords of at least 8 characters, including target overrides, and display Cisco password guidelines.
- Credential validation errors report the actual minimum length.
- Normalize nested VLAN multicast policy references using the referenced organization's name prefix and suffix.
- Correct Intersight profile/template prefix and suffix schema references and name patterns; refresh the bundled schema.
- Remove the unused Ethernet Network Control policy from the domain example.

## [0.1.3] - 2026-10-24

### Added
- WebUI: select individual saved Intersight YAML files for domain/server validation and deployment.
- UCS Domains: read-only uplink connectivity validation with CDP/LLDP neighbors when available.
- WebUI: bulk download retained page or environment logs as ZIP archives.
- Domain switch-profile deployment progress logs, including PATCH submission and polling waits.
- Regression coverage for Intersight provisioning, domain connectivity, file selection, and log downloads.

### Changed
- Domain/server page deployments exclude System organization files; organization deployment remains on System (Orgs).
- Profile processing follows domain, chassis, then server dependency order.
- Domain and Unified Edge profiles honor `action: Deploy` on A/B switch profiles and wait for completion.
- Domain template attachment verifies template relationships and inherited policies before deployment.
- Documented retention of the latest 25 completed automation runs per page.

### Fixed
- Check mode tolerates missing dependencies on new deployments and reports deferred payload validation.
- Corrected System QoS JSON rendering, internal reserved VLAN handling, and example thermal policy references.
- Corrected domain template platform values, parent/child template ID resolution, and copied-state handling.
- Hardware serial lookups filter by Serial rather than Name and explicitly reject missing domain, chassis, or server hardware.

## [0.1.2] - 2026-10-19

### Added
- Initial Inventory: drag-and-drop ordering for imported and manually added nodes.
- Initial Inventory: bulk assignment of incrementing hostnames/IP addresses and roles to checked rows in displayed order.
- Initial Inventory: per-row and bulk Pool IP settings, persisted with blank addresses and excluded from DHCP reservations; imported X-Series compute nodes default to Pool IP.

### Changed
- Shared Services displays LDAP / Active Directory before Proxy settings.
- Bulk inventory edits allow temporary duplicate addresses while editing; Validate and Save identify conflicts before persisting.
- C845A nodes use the standalone UCS C-Series workflow with `target_platform: Standalone` and `server_family: UCSC845A`.
- C880A and C885A use the separate HGX Servers workflow and are excluded from generated Intersight claim inventory and profiles.
- Updated HGX examples, source and bundled schemas, help text, and inventory regression tests.

## [0.1.1] - 2026-10-19

### Added
- WebUI: Intersight pages reworked (System organizations, UCS Domains and UCS Servers with pools and policies, collapsed X-Series and Standalone variables).
- WebUI: Nexus Dashboard fabric POAP script and fabric seeding.
- WebUI: certificate management uploads (servers and domains), and multi-value policy secrets (local user, SNMP auth/priv, LDAP binding, MACsec).
- WebUI: YAML upload buttons for Network fabrics, Everpure, Intersight, System, HGX, OpenShift install/certificates/LDAP and Splunk Observability.
- WebUI: Everpure certificate uploads with passphrases, SNMP community strings and users, and per-appliance key/CSR generation.
- WebUI: OpenShift certificate CSRs include subject alternative names; ingress CN is `apps.<cluster>.<domain>`.
- WebUI: certificate private keys are committed to the deployments repository only inside the encrypted `certificate-keys.vault.yaml`.
- WebUI: push rendered OpenShift GitOps content to an external repository (`scripts/gitops_push.py`) and "Build from inputs".
- Ubuntu 26.04 support for the automation appliance.

### Changed
- Python 3.12 or later is required (Python 3.9 support dropped).
- Release workflow pinned to `ubuntu-24.04`.
- Stage 01 documentation no longer links to lab logs and lab inventories.

## [0.1.0] - 2026-05-21

### Added
- Initial public collection metadata and role-based deployment workflows for Cisco AI PODs.
- Documentation consolidation for OpenShift and Everpure guides.
- Role-level README files for OpenShift, Everpure, Portworx Enterprise, and Splunk Observability.

### Changed
- Updated lint-related role references and legacy module defaults for Kubernetes module groups.
