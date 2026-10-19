# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog.

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
