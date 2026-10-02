# Rocky Linux Web Automation Interface Deployment Guide

This guide deploys the maintained Cisco AI PODs workspace on **Rocky Linux 9 or 10**, using Python 3.12, NiceGUI, and an HTTPS Nginx reverse proxy. It includes dark and light themes, multiple order-spreadsheet imports, editable inventory, schema-validated shared services, ISO file management, and self-service password changes.

---

## Step 1: Install Pre-requisites & System Packages

Run these commands as `root` or via `sudo` to enable the EPEL repository, update system packages, and install Python, Nginx, and Ansible.

```bash
# Enable the EPEL repository (required for Nginx and Ansible)
sudo dnf install epel-release -y

# Update the system package lists
sudo dnf update -y

# Install Python 3.12, Nginx, Ansible Core, and security tools
sudo dnf install python3.12 python3.12-pip nginx ansible-core openssl firewalld policycoreutils-python-utils -y

# Create a dedicated, non-privileged system user for running the UI
sudo useradd -m -s /bin/bash automation-ui
```

---

## Step 2: Set Up the Python Virtual Environment & Application

From the root of a Cisco-AI-PODs checkout, copy the maintained application, inventory builder, and source schemas to the service user's application directory. Do not recreate the old embedded `app.py` prototype.

```bash
sudo install -d -o automation-ui -g automation-ui -m 755 \
    /home/automation-ui/automation-app/scripts \
    /home/automation-ui/automation-app/schemas/source
sudo cp scripts/automation_ui.py scripts/build_initial_inventory.py \
    scripts/requirements-webui.txt /home/automation-ui/automation-app/scripts/
sudo cp schemas/source/*.json /home/automation-ui/automation-app/schemas/source/
sudo chown -R automation-ui:automation-ui /home/automation-ui/automation-app

# Switch to the application user
sudo su - automation-ui

# Create a virtual environment and upgrade pip
python3.12 -m venv ~/app-env
~/app-env/bin/pip install --upgrade pip

# Install the UI, workbook reader, YAML writer, and JSON Schema validator
~/app-env/bin/pip install -r ~/automation-app/scripts/requirements-webui.txt

# Create the output directory and first login account
mkdir -p ~/playbooks/vars
AI_PODS_APP_DIR=~/automation-app ~/app-env/bin/python3 \
    ~/automation-app/scripts/automation_ui.py --create-user admin
```

Enter and confirm a password of at least 12 characters directly in the terminal. Repeat `--create-user <username>` to add accounts or reset a password. Accounts use salted PBKDF2-SHA256 hashes in `users.json`; the file and automatically generated `.storage-secret` are permission-restricted to `0600`. There are no built-in default accounts.

Signed-in users can select **Change password** in the header. The dialog verifies the current password and requires matching new passwords of at least 12 characters.

The UI uses the NiceGUI 3 upload API (`event.file.save()`), verified with version 3.17.1. Large ISO uploads are copied in chunks. Allow enough temporary and destination disk space for both the incoming upload and saved copy.

Exit back to the sudo user by typing `exit`.

---

## Step 3: Create the Systemd Service

Before starting NiceGUI, create its upload directory as the sudo user. The application accesses this directory during startup and cannot create it under `/var/www/html` itself.

```bash
sudo mkdir -p /var/www/html/os-images
sudo chown automation-ui:nginx /var/www/html/os-images
sudo chmod 775 /var/www/html/os-images
```

Keep SELinux enforcing. Systemd can fail with `status=203/EXEC` and `Permission denied` when the virtual environment's `python3` symlink has the default `user_home_t` label. Apply a persistent executable label to this specific path before starting the service:

```bash
sudo semanage fcontext -a -t bin_t '/home/automation-ui/app-env/bin/python3'
sudo restorecon -v /home/automation-ui/app-env/bin/python3
```

If this exact local context rule already exists, use `semanage fcontext -m` instead of `-a`. Do not disable SELinux or make the application user's home directory world-writable.

Create a system service manager file to supervise the Python application and execute it continuously in the background.

```bash
sudo nano /etc/systemd/system/automation-ui.service
```

Paste the following configurations:

```ini
[Unit]
Description=NiceGUI Ansible Automation Web Interface
After=network.target

[Service]
Type=simple
User=automation-ui
WorkingDirectory=/home/automation-ui/automation-app
ExecStart=/home/automation-ui/app-env/bin/python3 /home/automation-ui/automation-app/scripts/automation_ui.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=AI_PODS_APP_DIR=/home/automation-ui/automation-app

[Install]
WantedBy=multi-user.target
```

Enable and start the service daemon:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now automation-ui
sudo systemctl status automation-ui --no-pager
```

---

## Step 4: Configure the HTTPS Nginx Reverse Proxy

Nginx terminates TLS on port **443** and proxies requests and WebSockets to NiceGUI on **127.0.0.1:8080**. Keep the application's `ui.run` address and port unchanged. Clients must use HTTPS directly when HTTP is blocked.

### TLS Certificate

For production, install a trusted certificate (including its intermediate chain) at `/etc/pki/nginx/automation-ui.crt` and its private key at `/etc/pki/nginx/private/automation-ui.key`.

For an initial test deployment without a trusted certificate, generate a temporary self-signed certificate instead. Replace the example DNS name and IP address with your VM's values. Do not run the certificate-generation command over existing certificate or key files.

```bash
TLS_HOST=ai-staging.rich.ciscolabs.com
TLS_IP=64.100.14.52

sudo install -d -m 755 /etc/pki/nginx
sudo install -d -m 700 /etc/pki/nginx/private
sudo openssl req -x509 -nodes -newkey rsa:3072 -sha256 -days 90 \
    -keyout /etc/pki/nginx/private/automation-ui.key \
    -out /etc/pki/nginx/automation-ui.crt \
    -subj "/CN=${TLS_HOST}" \
    -addext "subjectAltName=DNS:${TLS_HOST},IP:${TLS_IP}"
sudo chmod 600 /etc/pki/nginx/private/automation-ui.key
sudo chmod 644 /etc/pki/nginx/automation-ui.crt
sudo restorecon -RF /etc/pki/nginx
```

The self-signed certificate expires after **90 days** and causes a browser trust warning. Replace it with a trusted certificate before production use, then validate and reload Nginx.

### Reverse Proxy Configuration

Create an Nginx configuration optimized for streaming **15GB HTTPS payloads**. Back up any existing configuration first.

```bash
sudo nano /etc/nginx/conf.d/automation.conf
```

Paste the following configuration parameters, replacing `server_name` with your VM's DNS name and IP address:

```nginx
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name ai-staging.rich.ciscolabs.com 64.100.14.52;

    ssl_certificate /etc/pki/nginx/automation-ui.crt;
    ssl_certificate_key /etc/pki/nginx/private/automation-ui.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers PROFILE=SYSTEM;
    ssl_session_cache shared:AutomationTLS:10m;
    ssl_session_timeout 10m;

    # Allow up to 15 Gigabyte file transfers
    client_max_body_size 15000M;
    
    # Fully disable buffering to local disk segments for massive streams
    proxy_request_buffering off;
    proxy_buffering off;

    # Extend connection timeouts to protect long-running 12GB transfers
    client_body_timeout 1800s;
    client_header_timeout 1800s;
    keepalive_timeout 1800s;
    send_timeout 1800s;
    proxy_read_timeout 1800s;
    proxy_connect_timeout 1800s;

    # Backend NiceGUI/FastAPI Reverse Proxy
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Mandatory WebSockets upgrade rules for NiceGUI execution state
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # ISO Directory mapped for downstream endpoint deployment (iDRAC/iLO/PXE)
    location /os-images/ {
        alias /var/www/html/os-images/;
        autoindex on;
        allow all;
    }
}
```

---

## Step 5: Directory Permissions, Firewall & SELinux Compliance

Run these commands as the sudo user to permit Nginx to reach NiceGUI and serve the shared media directory while keeping SELinux enforcing.

```bash
# 1. Modify SELinux Boolean Policies to allow network proxies
sudo setsebool -P httpd_can_network_connect 1

# 2. Apply permanent context markers to the shared directory structure
sudo semanage fcontext -a -t httpd_sys_content_t "/var/www/html/os-images(/.*)?"
sudo restorecon -R -v /var/www/html/os-images

# 3. Allow HTTPS in both the running and persistent firewall configuration
sudo systemctl enable --now firewalld
sudo firewall-cmd --get-active-zones
sudo firewall-cmd --zone=public --add-service=https
sudo firewall-cmd --permanent --zone=public --add-service=https

# 4. Verify configuration formatting and start or reload Nginx
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx
```

Use the zone attached to your network interface instead of `public` if different. Permit TCP 443 in any upstream network firewall as well. Opening HTTP port 80 is not required for this application.

### Verify and Troubleshoot

```bash
sudo systemctl is-active automation-ui nginx
curl -sS -o /dev/null -w 'Backend: HTTP %{http_code}\n' http://127.0.0.1:8080/login

# Validate HTTPS locally using the self-signed certificate as the trust anchor
curl -sS --cacert /etc/pki/nginx/automation-ui.crt \
    --resolve ai-staging.rich.ciscolabs.com:443:127.0.0.1 \
    -o /dev/null -w 'HTTPS: HTTP %{http_code}\n' \
    https://ai-staging.rich.ciscolabs.com/login

sudo firewall-cmd --zone=public --query-service=https
sudo firewall-cmd --permanent --zone=public --query-service=https
```

Replace the hostname and firewall zone in these checks as needed. Both HTTP checks should return **200**, both services should be **active**, and both firewall queries should return **yes**. Verify browser access over HTTPS from a client outside the VM as well.

If Nginx returns **502 Bad Gateway**, inspect the application and proxy logs:

```bash
sudo systemctl status automation-ui --no-pager -l
sudo journalctl -u automation-ui -n 50 --no-pager
sudo tail -n 30 /var/log/nginx/error.log
sudo ausearch -m AVC,USER_AVC -ts recent -i
```

`connect() failed (111: Connection refused)` to `127.0.0.1:8080` means the backend is not listening. If the service reports `203/EXEC` and the audit log denies systemd access to the `python3` symlink labeled `user_home_t`, apply the interpreter context rule in Step 3 and run `sudo systemctl restart automation-ui`.

---
### File Structure Mapping

* **Web UI Dashboard:** `https://<your-vm-hostname-or-ip>/`
* **Static Media Storage for Endpoint Mounting:** `https://<your-vm-hostname-or-ip>/os-images/` (endpoint clients must trust the TLS certificate)
* **Generated Inventory:** `/home/automation-ui/playbooks/vars/<username>/<browser-client-id>/initial_inventory.ezai.yaml`
* **Optional Proxy Secrets:** `initial_inventory.secrets.yaml` beside the generated inventory

## Using the Workspace

The header theme control switches between dark and light appearances and remembers the choice for that browser session.

In **Inventory**, spreadsheets are optional. Select **Add node** to create an editable inventory row without uploading a workbook. New rows start with hostname `unknown` and an unused `198.18.0.X` address when one is available; fill in the MAC address, product ID, and serial number, and change the hostname and IP as needed. Manual rows and imported rows can be used together.

To import inventory, select multiple `.xlsx` files together, or import additional files later. Each workbook must contain `PID`, `Serial number`, and `MAC Addresses` columns. The three `Serial_Num` sample files import 57 entries. Repeated MACs are not appended again, and reimporting an already imported filename is rejected.

Click cells to edit hostname, IP address, MAC address, product ID, or serial number. Select rows with the checkboxes and use the delete control to remove them from the draft. Short valid hexadecimal MACs are left-padded with zeros to 12 digits and formatted as six colon-separated octets. Invalid hex, overlong MACs, duplicate IPs, and duplicate MACs block generation.

Complete DNS servers, DNS search domains, domain name, NTP servers, and timezone under **Shared services**. DNS servers, search domains, NTP servers, and the proxy bypass list have individual value inputs with **plus** and **minus** controls. Enter one value per input; plus adds another input, and minus removes that value. The plus control is disabled at the schema's maximum item count. Removing the last value leaves a blank input available, and blank values are omitted from the generated arrays. **Proxy settings** includes optional HTTP/HTTPS URLs, username, password, password reference, and bypass list. Empty optional values are omitted rather than emitted as invalid empty schema values.

**Validate** and **Generate YAML** use `definitions/shared_services` in `schemas/source/cisco-ai-pods.json`, including its references to `shared.json`. This source schema is the validation authority; retain the source files together when deploying. Generation calls the inventory builder and writes both `initial_inventory` and `shared_services`, then offers a YAML preview and download. Drafts are isolated per browser page and are discarded when the page reloads; generated files remain on the server.

The schema's proxy `password` is a **reference number from 1 to 64**, not a literal password. If a proxy password is entered, the inventory contains its reference (default `1`), and a separate `0600` secrets file contains `proxy_password_<reference>`. The secrets download is explicit and excluded from the inventory preview. This file is not encrypted: protect downloaded copies and encrypt it with Ansible Vault before sharing or committing it.

In **ISO library**, search existing files, open their media URLs, upload new ISOs, or select files to delete. Deletion requires confirmation. Existing filenames are never overwritten; delete the old file explicitly if it must be replaced. Partial uploads and symlinks are hidden from file management. The Nginx `/os-images/` endpoint remains public for installation endpoints, independently of UI login.

### CLI Inventory Generation

The same builder can run without the WebUI. A shared-services YAML file can contain either the settings directly or a `shared_services` wrapper.

```bash
~/app-env/bin/python3 scripts/build_initial_inventory.py --folder ~/orders \
    --shared-services ~/shared-services.yaml \
    --output host_vars/initial_inventory.ezai.yaml
```

Use `--inventory <edited-inventory.yaml>` instead of `--folder` to regenerate an edited `initial_inventory` list. The original interactive folder prompt remains available when neither option is supplied.

### Validation Tests

From the checkout, using an environment with `scripts/requirements-webui.txt` installed:

```bash
~/app-env/bin/python3 -m unittest discover -s tests -p 'test_*.py' -v
```
