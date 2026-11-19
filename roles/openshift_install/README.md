# OpenShift Install Role

Generates and validates manifests for bare-metal OpenShift cluster deployment via Cisco iServer and OpenShift Assisted Installer.

**Main Documentation:** [docs/openshift.md — Cluster Installation](../../docs/openshift.md#cluster-installation)

## Role Tasks

- `main.yaml` — Loads merged YAML, validates required keys, runs schema validation
- `templates/cilium-config.yaml.j2` — CiliumConfig template; its task in `main.yaml` is commented out for now
- `persistent_net_rules.yaml` — Renders NVIDIA Network Operator udev rules (conditional)
- `proxy.yaml` — Renders HTTP/HTTPS proxy manifests (conditional)

## Python Module

**Path:** `roles/openshift_install/library/generate_server_and_nmstate_templates.py`

Generates:
- `server.json` — Assisted Installer server inventory from variables
- `nmstate_*.yaml` — Network profiles for each unique interface configuration
- `ssh.pub` — SSH public key from `ssh_public_key_<suffix>` environment variable

### Usage

```bash
cd roles/openshift_install
python library/generate_server_and_nmstate_templates.py --check-env  # Validate only
python library/generate_server_and_nmstate_templates.py               # Generate output into <repository>/assisted-installer
python library/generate_server_and_nmstate_templates.py --output-dir /tmp/preview  # Generate somewhere else
```

## Files

| File | Description |
|------|-------------|
| `tasks/main.yaml` | Role entry point |
| `tasks/persistent_net_rules.yaml` | Network operator task handler |
| `tasks/proxy.yaml` | Proxy task handler |
| `defaults/main.yaml` | Role defaults (None) |
| `library/generate_server_and_nmstate_templates.py` | Manifest generator script |
| `library/src/initialize.py` | Initialization utilities |
| `library/src/shared_functions.py` | Shared functions and schema path resolution |
| `templates/*.j2` | Jinja2 templates for manifest generation |

## Key Variables

Set in `host_vars/openshift/install.ezai.yaml`:

- `openshift.install.bare_metal.*` — Cluster configuration, servers, networking
- `openshift.operators.*` — Cilium, NVIDIA, Portworx settings for install-time manifests

Set via environment variables:

- `redfish_password_<N>` — BMC passwords (one per server type)
- `fi_password_<N>` — Fabric Interconnect passwords
- `ssh_public_key_<N>` — SSH public keys (base64 safe variant recommended)
- `GITHUB_TOKEN` — Optional, prevents GitHub API rate-limit issues

## Generated Artifacts

After running, `assisted-installer/` contains:

- `cluster.json` — iServer cluster payload
- `server.json` — Assisted Installer server inventory
- `nmstate_*.yaml` — Network profiles
- `ssh.pub` — SSH public key
- `web.json` — iServer web server payload
- `proxy.json` — iServer proxy payload (if configured)
- `manifests/` — Install-time MachineConfigs and operator manifests

## Idempotency

Safe to re-run. Existing files are overwritten with current values from variables.

## Troubleshooting

- **Schema validation fails:** Verify `schema/cisco-ai-pods.json` exists at repo root
- **SSH key rejected:** Check format (PEM, not base64) and environment variable name matches suffix in config
- **Server templates fail:** Ensure all required server fields are defined (hostname, role, interfaces, MACs)
- **Network template fails:** Check interface MTU, VLAN, and IP assignment consistency

See [docs/openshift.md — Cluster Installation](../../docs/openshift.md#cluster-installation) for full setup guide.
