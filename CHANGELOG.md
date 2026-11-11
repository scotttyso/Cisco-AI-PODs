# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog.

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
