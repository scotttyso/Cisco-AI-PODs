# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog.

## [Unreleased]

## [0.1.43] - 2026-11-20

### Added
- `scripts/vmedia_diagnose.py` (`inspect`, `mount`) diagnoses virtual media mount failures on FI attached blades by talking Redfish to the Fabric Interconnect directly: CIMC firmware, clock and network, every virtual media slot with the CIMC's own message, the web server certificate, a timestamped mount timeline, and the requests the CIMC makes to Nginx. See docs/openshift.md.

## [0.1.42] - 2026-11-19

### Fixed
- The bundled schema's `x-schema-version` was left at v0.1.36, so the `Publish release` workflow rejected every tag after it. The schema is regenerated for this release, and a test now fails when `VERSION` and the bundled schema stamp differ.

## [0.1.41] - 2026-11-19

### Fixed
- Intersight bulk updates (PATCH) failed with `The property 'macpool.Pool:pmoid' does not exist`: the internal `pmoid` key was removed from the working copy but still sent in the request body. It is now removed from the body.

## [0.1.40] - 2026-11-19

### Fixed
- Intersight Validate/Deploy stopped with `Vault file not found: ~/.config/cisco-ai-pods/vault.yaml` on appliances without that legacy per-user file. The environment check now uses the Intersight credentials the job exports from the selected environment's vault (`intersight_api_key_id`, `intersight_secret_key`) and reports a clear message when they are missing. The legacy vault is still used when the file exists.

## [0.1.39] - 2026-11-19

### Fixed
- `iso_web_server.image_base_url` and `image_upload_directory` are written without a trailing `/` (the trailing slash added in 0.1.38 broke the install script). The `/os-images` Nginx redirect is unchanged.

### Changed
- Prepare install no longer generates `manifests/ciliumconfig.yaml` (the current iserver version fails with it). The task is commented out in `roles/openshift_install/tasks/main.yaml` and `cilium-config.yaml.j2` is kept. `enable_hubble_metrics` and `enable_kube_proxy_replacement` are accepted but have no effect until it is re-enabled.

## [0.1.38] - 2026-11-17

### Fixed
- The OpenShift install seed writes `iso_web_server.image_base_url` and `image_upload_directory` with a trailing `/`, and the default media URL is `https://<appliance>/os-images` (Nginx only serves HTTPS).
- Nginx redirects `/os-images` to `/os-images/`; without the slash the request fell through to the UI and returned 404. Existing appliances need the one-time Nginx change in docs/rocky_linux_vm.md (the appliance file is `/etc/nginx/conf.d/automation-ui.conf`).

## [0.1.37] - 2026-11-17

### Changed
- Cilium settings are a `cilium` block under `openshift.install.bare_metal.cluster_networking`: `version` (required, replaces `container_network_version`), `enable_hubble_metrics` and `enable_kube_proxy_replacement` (both default `false`). An existing `container_network_version` must be replaced; Apply to YAML on Cluster Deployment does it.
- When the CNI is Cilium, Prepare install renders `cilium-config.yaml.j2` to `assisted-installer/manifests/ciliumconfig.yaml` (the CiliumConfig name iserver uses), including Hubble metrics, kube-proxy replacement and a single operator replica on single-node clusters.
- Cluster Deployment has Enable Hubble metrics and Replace kube-proxy checkboxes next to the Cilium version.

## [0.1.36] - 2026-11-17

### Fixed
- Install cluster (iserver) failed with `Key dns_search missing`. `cluster.json` now has `dns_search`, built from `cluster_networking.dns_search_domains` (comma-separated like `dns_ip`), or from `base_dns_domain` when no search domains are set.

## [0.1.35] - 2026-11-17

### Fixed
- Install cluster (iserver) failed with `'str' object does not support item assignment`: on Ansible 2.19 and newer `cluster.json` was written as a quoted JSON string instead of an object. `cluster.json` and `web.json` are now parsed and written as JSON objects on every Ansible version.
- The web server payload is written to `web.json`, the name iserver reads (it was `web_server.json`), and the template no longer emits a trailing comma for plain `http` image URLs.

## [0.1.34] - 2026-11-17

### Changed
- The OpenShift list on Cluster Deployment offers only the latest production release (default) and the latest stable release of each supported channel. A saved `cluster_version` that is not in the list (such as 4.20.16) is no longer added to it; the form shows the latest production release instead.
- The offline fallback release for 4.20 is 4.20.46.

## [0.1.33] - 2026-11-17

### Changed
- OpenShift 4.19, 4.20, 4.21, 4.22 and 5.0 are all supported, and `cluster_version` accepts 5.x releases.
- The OpenShift list on Cluster Deployment defaults to **Latest production release** (`the-latest-production-version`) and then offers the latest stable release of each supported channel, newest first. An earlier patch release in a supported channel is marked "older patch" instead of "pinned".
- The channel table has an **Assisted Installer** column (when the Console Registration login is available), and Apply warns when the chosen release is not offered by the installer.

## [0.1.32] - 2026-11-17

### Changed
- **Versions and container network** shows the latest stable release of each active OpenShift channel with Red Hat's support phase and its end date, and whether Cisco AI PODs supports the channel (like console.redhat.com/openshift/releases). It loads when the page opens. The OpenShift list offers only the latest stable release of a supported channel instead of every patch release. Releases come from iserver (Assisted Installer) or Red Hat's public update graph, support phases from Red Hat's public product life cycle API; no token is needed for the public sources.
- The drift check (`version_support_matrix.py check`) now reports policy drift: a supported OpenShift channel reaching end of life, and newer channels that are generally available. OpenShift no longer has a pinned "recommended" patch; it is always the latest stable release of a supported channel.
- New `version_support_matrix.py channels` command prints the channel table.

## [0.1.31] - 2026-11-17

### Changed
- Cluster Deployment cards are in alphabetical order: Cluster access, Node MAC addresses, Node SSH key, Versions and container network.

## [0.1.30] - 2026-11-17

### Added
- **Supported OpenShift and Cilium versions** (`scripts/version_support_matrix.py`): a maintained matrix of supported minor releases and the recommended patch, live version lists, and a drift check (`check`) for cron or CI. OpenShift versions come from iserver (the versions the Assisted Installer accepts), falling back to Red Hat's public update graph; Cilium versions come from your registry's Helm index (optional **Version catalog URL** on the Cilium Registry page), falling back to the tested versions in the matrix.
- Cluster Deployment **Versions and container network** card with restricted pick-lists and a Refresh button for each live list.
- Prepare install validates the OpenShift and Cilium versions against the matrix and stops with the reason.
- A weekly GitHub Actions job (`version-check.yml`) runs the drift check against the public sources.

### Changed
- `cluster_version` is optional and defaults to `the-latest-production-version`, so iserver installs the latest production OpenShift release unless you pin a supported version. The default is checked against what it resolves to; if that release is not supported yet, Prepare install asks you to pin one.

## [0.1.29] - 2026-11-17

### Changed
- **Cilium uses iserver's automated fixups; Prepare install (phase 1) no longer generates Cilium manifests.** The Cilium version is now set with the install settings (`cluster_networking.container_network_version`, next to `container_network_interface: Cilium`) and shown on the Cluster Deployment page (Container network (CNI) > Apply to YAML). Phase 1 writes the version into `cluster.json`, and iserver downloads the Isovalent manifests and fixes up the cluster pool CIDR and mask and the operator replicas. Prepare install fails with a clear message when Cilium is selected without a version.
- Cilium is no longer an operator setting: `openshift.operators.cilium` is removed from the schema, the OpenShift GitOps page, and the examples. Delete the block from an existing `operators.ezai.yaml` (or run Build from inputs on the OpenShift GitOps page, which removes it).
- **Install cluster** checks the Cilium registry when the install file selects Cilium (it previously looked at the operators file).

### Removed
- The Cilium manifest templates and tasks, and the settings only they used: `download_url`, `cluster_network`, `enable_kube_proxy_replacement`, and `enable_hubble_metrics`. iserver's fixups do not apply kube-proxy replacement or Hubble metrics; apply them after the install if needed.

## [0.1.28] - 2026-11-17

### Added
- **Cilium Registry** page (OpenShift > Cilium Registry): registers the registry host and identity token with iServer (`iserver set ocp cilium registry`) and verifies them. Choose the Isovalent registry for customers, or enter any other registry host name. The identity token is stored in the vault and masked in job logs.
- **Install cluster** checks the Cilium registry first when `openshift.operators.cilium` is configured, so an expired token stops the job before any node is touched.

### Changed
- The Isovalent registry registration moved from the OpenShift GitOps page to the Cilium Registry page (the read-only check stays on the GitOps page).

## [0.1.27] - 2026-11-17

### Fixed
- OpenShift install prep (`openshift_install` role) could not run, in check mode or for real. Four separate problems, found by running the phase 1 playbook end to end:
  - The temporary directory, saved variables, and manifest generator tasks were skipped in check mode, so Validate (check mode) failed with `object of type 'dict' has no attribute 'path'`. They now run in check mode; the generator writes to the temporary directory there, so Validate never writes install files.
  - `generate_server_and_nmstate_templates.py` was moved into the role without updating its paths and failed with "templates directory not found". It now takes `--templates-dir` and `--output-dir`, defaulting to the role's `templates/` and `<repository>/assisted-installer`, which is where the iserver step reads.
  - The role saved the OpenShift variables without their top-level `openshift:` key, so the generator found "No servers". 
  - A `set_fact` used a fact it defined in the same task; it is now two tasks.

## [0.1.26] - 2026-11-17

### Fixed
- Validate (check mode) on OpenShift Cluster Deployment failed with `object of type 'dict' has no attribute 'path'`: in check mode Ansible skipped the temporary model file that the sensitive-variable validation needs. The temporary-file, write, validate, and cleanup tasks now always run (`check_mode: false`) in the OpenShift, OpenShift phase 1/2, storage, and observability playbooks. They only write and remove a temporary file and run the read-only validator.

## [0.1.25] - 2026-11-17

### Fixed
- OpenShift Cluster Deployment no longer blocks Validate, Prepare install, or Install cluster on the Intersight API key, Fabric Interconnect, CIMC, or HGX BMC passwords. The install does not use them; they are still listed for reference from the Compute pages, and Collect MACs from Intersight and from BMC Redfish still check the credentials they need.

## [0.1.24] - 2026-11-17

### Fixed
- OpenShift Cluster Deployment no longer asks for the HGX BMC password when the Initial Inventory has no HGX nodes. The default HGX password is listed there only when an HGX node uses it; the HGX Servers page still offers it.

## [0.1.23] - 2026-11-17

### Changed
- Synchronize now confirms its work for Active Directory writes made over LDAP: it checks DNS up to 4 times, 60 seconds apart, stops as soon as every written record resolves, and fails with a clear message if some still do not resolve after about 4 minutes. The DNS service loads AD changes about every 3 minutes by default, not every minute as the previous messages said.

## [0.1.22] - 2026-11-17

### Added
- **WinRM fallback for Active Directory Synchronize.** When no LDAP bind works (for example the domain controller requires signing or TLS and has no LDAPS certificate), Synchronize connects to the domain controller over WinRM (NTLM, port 5985 then 5986) and uses the Windows DNS Server cmdlets to create or replace the A records. Validate is unchanged. Adds the `pywinrm` requirement.
- **Check DNS records** pre-check on the OpenShift Cluster Deployment page: fails unless every node, `api`, and `*.apps` name in the saved DNS Manager configuration resolves to its address (`dns_updater.py --check`).
- An optional Active Directory username in Passwords and secrets for accounts whose common name is not their logon name (`user@domain`).

### Changed
- A failed LDAP bind prints one clear error (including the signing/TLS explanation) instead of a traceback.

### Removed
- The unused `scripts/dns_validator.py` and the old file-based `inventory:` parsing in `dns_updater.py` and the DNS schema.

## [0.1.21] - 2026-11-17

### Changed
- DNS Manager no longer imports `everpure/everpure.ezai.yaml`; its format has no addresses for the arrays. Add Everpure, NetApp, VAST, or other storage arrays to Initial Inventory with the Storage array role and they are included with the Initial Inventory devices.
- Validate lists records that exist with a different address in their own "changed" section instead of as both missing and stale.

### Fixed
- Updated the DNS updater unit tests that still used made-up OpenShift and comparator behaviour; the DNS updater test suite passes.

## [0.1.20] - 2026-11-17

### Added
- **Synchronize writes A records to Active Directory DNS** over LDAP (AD-integrated zones). It finds the real zones from AD, creates missing records, and replaces the address of a record that exists with a different one. Other record types on the same name are kept, nothing is deleted, and a record outside any AD-integrated zone is reported as failed. If the domain controller refuses cleartext LDAP binds, it retries over LDAPS/StartTLS without verifying the certificate. The DNS service reads AD changes within about a minute.
- Validate assigns each record to its real AD zone instead of guessing it from the hostname.

### Changed
- Synchronize still reports "not implemented" and changes nothing for Infoblox, BlueCat, Efficient IP, and BIND.

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
