# Cisco AI PODs Automation Appliance (Rocky Linux 10.2)

HashiCorp Packer build for the AI PODs automation appliance. One vSphere build creates:

| Artifact | Platform |
| --- | --- |
| vSphere VM template `aipod-automation-rocky10` | VMware (clone from template) |
| `output/<vm_name>-<version>.ova` with vApp properties | VMware (Deploy OVF Template) |
| `output/<vm_name>-<version>.qcow2` | OpenShift Virtualization |

The appliance contains:

- The Cisco-AI-PODs repository at `/home/automation-ui/Cisco-AI-PODs`, prepared by `scripts/setup.sh` (Python venv, Ansible tooling, collections, iServer).
- The NiceGUI automation UI (`scripts/automation_ui.py`) as `automation-ui.service`, published by Nginx on HTTPS 443. ISO library at `https://<appliance>/os-images/`.
- `kea` pre-installed for DHCP services, plus `firewalld`, `chrony`, SELinux enforcing, `open-vm-tools`, `qemu-guest-agent`, and `cloud-init`.
- `aipod-config`, which sets hostname, domain, IPv4 (static or DHCP), DNS servers and search domains, NTP, timezone, the OS admin password, and the first automation UI account.

## Build Host Prerequisites

The build host needs network access to vCenter and to the build VM.

```bash
sudo dnf install -y xorriso qemu-img python3   # xorriso builds the kickstart CD; qemu-img builds the qcow2
# Packer (HashiCorp repo), or put the binary from releases.hashicorp.com in ~/.local/bin
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --add-repo https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo
sudo dnf install -y packer
```

Upload `Rocky-10.2-x86_64-dvd1.iso` to a datastore, or set `iso_url` and `iso_checksum` so Packer uploads it.

> Rocky Linux 10 requires x86-64-v3 CPUs. The vSphere cluster EVC mode, if used, must expose AVX2.

## Build

```bash
cd automation-appliance
cp appliance.example.pkrvars.hcl appliance.auto.pkrvars.hcl   # git-ignored; edit for your vCenter

export PKR_VAR_vsphere_password='<vcenter password>'
export PKR_VAR_build_password='<temporary OS admin password>'
export PKR_VAR_build_password_hash="$(openssl passwd -6 "$PKR_VAR_build_password")"
export PKR_VAR_github_token='<optional GitHub PAT>'   # avoids iServer API rate limits

packer init .
packer validate .
packer build -force -on-error=ask .
```

The build:

1. Boots the DVD and installs Rocky Linux from a kickstart CD labeled `OEMDRV` (no HTTP server needed). The build port group needs DHCP unless `build_ip_address` is set.
2. Runs [scripts/provision.sh](scripts/provision.sh): updates packages, clones `repo_url`/`repo_branch`, runs `scripts/setup.sh` as `automation-ui`, and installs the UI service, Nginx, SELinux labels, and firewall rules.
3. Runs [scripts/cleanup.sh](scripts/cleanup.sh) to remove machine ID, SSH host keys, NIC connections, logs, and cloud-init state.
4. Expires the build password, powers off, converts the VM to a template, and exports an OVF.
5. Runs [scripts/build_artifacts.py](scripts/build_artifacts.py) to add the vApp properties in [scripts/ovf-properties.xml](scripts/ovf-properties.xml), package the OVA, and convert the disk to qcow2.

The image clones the published repository, so commit and push before building. Set `repo_branch` to build from a feature branch.

## First Boot Configuration

`aipod-firstboot.service` runs `aipod-config --firstboot` once. It reads settings from these sources, in priority order:

1. `/etc/aipod/appliance.env` (written by cloud-init on OpenShift, or by hand). See [files/appliance.env.example](files/appliance.env.example).
2. VMware vApp properties (OVA deployments).
3. VMware `guestinfo.<key>` advanced settings, such as `guestinfo.hostname` or `guestinfo.ip_address` (for clones of the vSphere template).

If none are found, the VM keeps DHCP and the console shows:

```text
Cisco AI PODs Automation Appliance
  Automation UI : https://<ip>/
  Configure     : sudo aipod-config
```

Log in as the build admin (`aipod` by default). If no `ADMIN_PASSWORD` was supplied, you must change the expired build password. Then run `sudo aipod-config` to complete the prompts. You can rerun it any time; it recreates the NIC connection, so use the console when changing the IP.

| Key | vApp / guestinfo key | Notes |
| --- | --- | --- |
| `HOSTNAME` | `guestinfo.hostname` | Short name or FQDN |
| `DOMAIN` | `guestinfo.domain` | Appended to a short hostname |
| `IP_SOURCE` | `guestinfo.ip_source` | `STATIC` (recommended because the appliance serves DHCP) or `DHCP` |
| `IP_ADDRESS`, `PREFIX`, `GATEWAY` | `guestinfo.ip_address`, `.prefix`, `.gateway` | Required for `STATIC` |
| `DNS_SERVERS`, `DNS_SEARCH` | `guestinfo.dns_servers`, `.dns_search` | Comma separated |
| `NTP_SERVERS`, `TIMEZONE` | `guestinfo.ntp_servers`, `.timezone` | Chrony servers, IANA zone |
| `ADMIN_PASSWORD` | `guestinfo.admin_password` | OS admin password, 12+ characters |
| `UI_ADMIN_USER`, `UI_ADMIN_PASSWORD` | `guestinfo.ui_admin_user`, `.ui_admin_password` | Creates the NiceGUI login |

Each run also regenerates the self-signed Nginx certificate (1 year) for the hostname and IP. To use a trusted certificate, replace `/etc/pki/nginx/automation-ui.crt` and `/etc/pki/nginx/private/automation-ui.key`, then delete `/etc/pki/nginx/.aipod-self-signed` so the appliance stops overwriting them.

## Deploy on VMware

**OVA:** Use *Deploy OVF Template* with the OVA, and fill in the *Networking*, *Time*, and *Credentials* properties.

**Template:** Clone the template, then add the `guestinfo.*` keys under *Edit Settings > Advanced Parameters* before first power-on. Alternatively, configure the clone on the console with `sudo aipod-config`.

## Deploy on OpenShift Virtualization

The appliance must be on the management/staging L2 network to provide DHCP, so it uses a Linux bridge secondary network rather than the pod network.

```bash
# 1. Upload the golden image (virtctl from the OpenShift console "Command Line Tools" page)
oc new-project aipod-images
virtctl image-upload pvc aipod-automation-rocky10 -n aipod-images \
  --size=256Gi --image-path=output/aipod-automation-rocky10-1.0.0.qcow2 \
  --storage-class=<storage-class> --insecure

# 2. Bridge on the workers (requires the Kubernetes NMState operator; edit NIC and VLAN first)
oc apply -f openshift/node-network-policy.yaml
oc new-project aipod-automation
oc apply -f openshift/network-attachment-definition.yaml

# 3. First-boot settings, then the VM
oc apply -f openshift/cloudinit-secret.yaml      # edit values and passwords first
oc apply -f openshift/virtualmachine.yaml
virtctl console aipod-automation -n aipod-automation
```

Cloud-init is limited to NoCloud and ConfigDrive, with network config turned off. It writes `/etc/aipod/appliance.env`, then `aipod-config` applies it, so OpenShift and VMware produce the same result. Password values are removed from the env file after use. Cloning across namespaces needs DataVolume clone permissions on `aipod-images`.

## Software Updates

Select **Check for software updates** in the WebUI header to compare the installed `VERSION` with the latest published GitHub release. When a newer release exists, finish all active playbooks and uploads, then select **Install vX.Y.Z now** (the UI runs the updater in its own systemd unit, reconnects after the restart, and keeps the log under **Last update log**), or run the displayed command from an administrative shell:

```bash
sudo /usr/local/sbin/aipod-update --version vX.Y.Z
```

The updater confirms the outage, backs up UI state, `~/playbooks`, and system configuration to `/var/backups/aipod-update-*`, checks out the verified release tag, reruns `setup.sh`, and waits for the UI to become healthy. On failure the service stays stopped and recovery commands are printed. Appliances built before the updater existed need a one-time bootstrap; see [Releases and Updates](../docs/releasing.md#bootstrap-older-installations). Appliances cloned from a fork must be updated manually.

To run the same stack on an Ubuntu 24.04 bare-metal server instead of this image, see [Deploy on Ubuntu Bare Metal](../docs/deploy_ubuntu_baremetal.md).

## Security Notes

- `automation-ui` has passwordless sudo so UI-launched playbooks can use `become` on the appliance (for example `playbooks/deploy_dhcp_server.yaml`). Protect UI accounts accordingly.
- Users with read access to the vSphere VM, and local users through `vmtoolsd`, can read vApp and guestinfo values. Change passwords supplied this way after deployment, or leave them blank and use `sudo aipod-config` on the console.
- The build password is expired before export, so every deployment must replace it.
- Only SSH and HTTPS are open in firewalld. The DHCP role opens `dhcp` when it runs.

## DHCP on Rocky Linux 10

EL10 no longer ships ISC `dhcp-server`. The `dhcp_server` role in `00-environment-prep/automation/roles/` configures the pre-installed `kea` (`kea-dhcp4`) service instead. The Automation UI generates the DHCP data model; run `playbooks/deploy_dhcp_server.yaml` (or the stage playbook) to apply it.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Packer waits at *Waiting for IP* | DHCP on `vsphere_network`, or set `build_ip_address`; open the VM console to see Anaconda |
| Installer stops at the boot menu | Increase `boot_wait`; confirm `firmware = "efi"` |
| `setup.sh` iServer API rate limit | Set `PKR_VAR_github_token`, or `skip_iserver = true` |
| UI returns 502 | `sudo journalctl -u automation-ui`, `sudo ausearch -m AVC -ts recent` |
| First boot did not apply settings | `sudo journalctl -u aipod-firstboot`; rerun `sudo aipod-config` |
| `aipod-update` reports local changes | `sudo -u automation-ui git -C /home/automation-ui/Cisco-AI-PODs status`; commit, stash, or discard tracked edits |
| Update failed and UI is stopped | Follow the printed recovery commands; backups are in `/var/backups/aipod-update-*` |
| OVA over 8 GB fails to package | Reduce disk content or use the OVF export directory directly |
