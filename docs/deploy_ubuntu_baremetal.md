# Deploy on Ubuntu 24.04 or 26.04 Bare Metal

This guide installs the Cisco AI PODs automation WebUI on an Ubuntu Server 24.04
or 26.04 LTS host with the same service account, paths, systemd unit, Nginx front end,
and updater as the [automation appliance](../automation-appliance/README.md).
Keeping those paths identical lets `aipod-update` manage both deployments.

> **Status:** This procedure mirrors the appliance build but has not yet been
> validated on physical hardware. Test it on a lab server first.

## Requirements

- Ubuntu Server 24.04 LTS (system Python 3.12) or 26.04 LTS (system Python
  3.14), x86_64. The system `python3` is used on both releases.
- An administrator account with `sudo`.
- Outbound HTTPS to `github.com`, `raw.githubusercontent.com`, `api.github.com`,
  PyPI, and Ansible Galaxy (directly or through `http_proxy`/`https_proxy`).
- Enough disk for the virtual environment, Ansible collections, and ISO media
  in `/var/www/html/os-images` (plan for at least 100 GiB).

| Item | Location |
| --- | --- |
| Service account | `automation-ui` |
| Repository checkout | `/home/automation-ui/Cisco-AI-PODs` |
| UI accounts and session secret | `/home/automation-ui/.automation-ui` |
| Deployment environments (git repository, one folder per environment) | `/home/automation-ui/deployments` |
| Pre-environment output (migrated once into `default`) | `/home/automation-ui/playbooks/vars` |
| ISO media served by Nginx | `/var/www/html/os-images` |
| Backend | `http://127.0.0.1:8080` (Nginx publishes HTTPS on 443) |

## 1. Install Packages

```bash
sudo apt update
sudo apt -y full-upgrade
sudo apt -y install git python3 python3-venv python3-pip tmux nginx openssl curl \
    ca-certificates jq rsync tar unzip
```

## 2. Create the Service Account

```bash
sudo useradd --create-home --shell /bin/bash automation-ui
```

Playbooks launched from the UI that target `localhost` with `become` (for
example `playbooks/deploy_dhcp_server.yaml`) need passwordless sudo. Grant it
only if you need those playbooks, and protect UI accounts accordingly:

```bash
printf '%s ALL=(ALL) NOPASSWD: ALL\n' automation-ui | sudo tee /etc/sudoers.d/automation-ui >/dev/null
sudo chmod 0440 /etc/sudoers.d/automation-ui
sudo visudo -cf /etc/sudoers.d/automation-ui
```

## 3. Clone a Release and Run Setup

Use the latest tag from the
[releases page](https://github.com/scotttyso/Cisco-AI-PODs/releases). Keep the
official `origin` URL; the updater refuses checkouts from forks.

```bash
tag=v0.1.0
sudo -u automation-ui -H bash -euc '
cd "$HOME"
git clone https://github.com/scotttyso/Cisco-AI-PODs.git
cd Cisco-AI-PODs
git -c advice.detachedHead=false checkout --detach "$1"
PYTHON_BIN=python3 ./scripts/setup.sh --skip-apt --skip-iserver
.venv/bin/python3 -m pip install -r scripts/requirements-webui.txt
' _ "$tag"
```

Ubuntu creates home directories with mode `0750`, so these commands run
entirely as `automation-ui`, and later steps use absolute paths with `sudo`.

Omit `--skip-iserver` if you need the Intersight iServer tooling; set
`GITHUB_TOKEN` in that environment if GitHub API rate limits are hit.

## 4. Create Data Directories

```bash
sudo install -d -o automation-ui -g automation-ui -m 0700 /home/automation-ui/.automation-ui
sudo install -d -o automation-ui -g automation-ui -m 0750 \
    /home/automation-ui/playbooks /home/automation-ui/playbooks/vars /home/automation-ui/deployments
sudo install -d -o automation-ui -g www-data -m 2775 /var/www/html/os-images
```

Optionally make interactive shells for the service account start in the repository:

```bash
sudo -u automation-ui tee -a /home/automation-ui/.bashrc >/dev/null <<'EOF'

# aipod-appliance: Cisco AI PODs tooling
source /home/automation-ui/Cisco-AI-PODs/.venv/bin/activate
cd /home/automation-ui/Cisco-AI-PODs
EOF
```

## 5. Install the Service and Updater

Both files are installed from the checked-out release:

```bash
files=/home/automation-ui/Cisco-AI-PODs/automation-appliance/files
sudo install -o root -g root -m 0644 "$files/automation-ui.service" /etc/systemd/system/
sudo install -o root -g root -m 0755 "$files/aipod-update" /usr/local/sbin/aipod-update
sudo systemctl daemon-reload
```

Create the first UI account before starting the service:

```bash
sudo -u automation-ui -H env AI_PODS_APP_DIR=/home/automation-ui/.automation-ui \
    /home/automation-ui/Cisco-AI-PODs/.venv/bin/python3 \
    /home/automation-ui/Cisco-AI-PODs/scripts/automation_ui.py --create-user admin
sudo systemctl enable --now automation-ui.service
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/login   # expect 200
```

## 6. Configure TLS and Nginx

Use a certificate issued by your CA when possible. Install it as
`/etc/pki/nginx/automation-ui.crt` with the key at
`/etc/pki/nginx/private/automation-ui.key`. For a lab, create a self-signed
certificate (replace the name and address):

```bash
sudo install -d -m 0755 /etc/pki/nginx
sudo install -d -m 0700 /etc/pki/nginx/private
sudo openssl req -x509 -newkey rsa:3072 -sha256 -days 825 -nodes \
    -subj "/CN=aipod-automation.example.com" \
    -addext "subjectAltName=DNS:aipod-automation.example.com,IP:192.0.2.10" \
    -keyout /etc/pki/nginx/private/automation-ui.key -out /etc/pki/nginx/automation-ui.crt
sudo chmod 0600 /etc/pki/nginx/private/automation-ui.key
```

The appliance Nginx file uses the RHEL-only `PROFILE=SYSTEM` cipher policy, so
remove that line on Ubuntu (Nginx then uses OpenSSL defaults for TLS 1.2/1.3):

```bash
sudo sed '/ssl_ciphers PROFILE=SYSTEM;/d' \
    /home/automation-ui/Cisco-AI-PODs/automation-appliance/files/nginx-automation-ui.conf \
    | sudo tee /etc/nginx/conf.d/automation-ui.conf >/dev/null
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx
```

## 7. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

Roles that run services on this host (for example DHCP) must open their own ports.

## 8. Acceptance Checks

```bash
systemctl is-active automation-ui nginx
curl -kfsS -o /dev/null -w '%{http_code}\n' https://localhost/login   # expect 200
sudo cat /home/automation-ui/Cisco-AI-PODs/VERSION
```

Browse to `https://<server>/`, sign in, upload a small test file in **ISO
library**, and confirm it is listed at `https://<server>/os-images/`.

## Updating

Select **Check for software updates** in the WebUI header and then
**Install vX.Y.Z now**, or check the releases page and run:

```bash
sudo /usr/local/sbin/aipod-update --version vX.Y.Z
```

The updater is the same one used on the appliance; see
[Releases and Updates](releasing.md#install-a-release) for its checks, backups,
and recovery behavior. It replaces `/etc/systemd/system/automation-ui.service`
and itself from the release, but never changes Nginx or TLS configuration. If
you customize the unit, use a drop-in under
`/etc/systemd/system/automation-ui.service.d/` that keeps the standard user,
working directory, and `127.0.0.1:8080` backend.

## Backups

Back up these paths under your normal backup policy:

- `/home/automation-ui/.automation-ui` (UI accounts, session secret, git settings, and the git token vault)
- `/home/automation-ui/deployments` (every environment: inventory, page files, encrypted vaults). You can also
  push it to a private Git repository from **Initial Inventory → Git repository** in the UI.
- `/home/automation-ui/.config/cisco-ai-pods/vault-password` (needed to decrypt the environment vaults; never
  committed)
- `/home/automation-ui/playbooks`
- `/etc/pki/nginx`, `/etc/nginx/conf.d/automation-ui.conf`, and
  `/etc/systemd/system/automation-ui.service*`
- `/var/www/html/os-images` if the ISO media is not easy to re-download

`aipod-update` also keeps per-update recovery archives in
`/var/backups/aipod-update-*`; prune old ones periodically.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `setup.sh` fails creating `.venv` | `python3.12 -m venv --help`; confirm `python3.12-venv` is installed |
| UI service will not start | `sudo journalctl -u automation-ui -n 100` |
| Browser shows 502 | `curl http://127.0.0.1:8080/login`; `sudo tail /var/log/nginx/error.log` |
| `nginx -t` reports `ssl_ciphers` | The `PROFILE=SYSTEM` line was not removed |
| ISO uploads fail | Ownership/mode of `/var/www/html/os-images` (`automation-ui:www-data`, `2775`) and free disk space |
| `aipod-update` reports custom service | Remove unit overrides that change `User`, `WorkingDirectory`, or `ExecStart` |
