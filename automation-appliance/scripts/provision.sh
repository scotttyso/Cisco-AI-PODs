#!/usr/bin/env bash
# Provision the Cisco AI PODs automation appliance. Runs as root during the Packer build.
set -euo pipefail

: "${ADMIN_USER:?}" "${APPLIANCE_VERSION:?}" "${REPO_URL:?}" "${REPO_BRANCH:?}"
FILES_DIR="${FILES_DIR:-/tmp/aipod-files}"
APP_USER=automation-ui
APP_HOME="/home/${APP_USER}"
REPO_DIR="${APP_HOME}/Cisco-AI-PODs"
STATE_DIR="${APP_HOME}/.automation-ui"
MEDIA_DIR=/var/www/html/os-images

log() { printf '\n==> %s\n' "$*"; }

log "Updating Rocky Linux and installing appliance packages"
dnf -y update
# kea replaces ISC dhcp-server, which is not shipped in EL10.
dnf -y install \
    bash-completion chrony cloud-init cloud-utils-growpart firewalld git-core jq kea nginx \
    open-vm-tools openssl policycoreutils-python-utils python3 python3-pip qemu-guest-agent \
    rsync tar unzip vim-enhanced

log "Installing appliance configuration files"
install -d -m 0755 /etc/aipod /etc/issue.d /etc/cloud/cloud.cfg.d
install -m 0755 "${FILES_DIR}/aipod-config" /usr/local/sbin/aipod-config
install -m 0755 "${FILES_DIR}/aipod-update" /usr/local/sbin/aipod-update
install -m 0644 "${FILES_DIR}/aipod-firstboot.service" "${FILES_DIR}/automation-ui.service" /etc/systemd/system/
install -m 0644 "${FILES_DIR}/nginx-automation-ui.conf" /etc/nginx/conf.d/automation-ui.conf
install -m 0644 "${FILES_DIR}/cloud-init-99-aipod.cfg" /etc/cloud/cloud.cfg.d/99-aipod.cfg
install -m 0644 "${FILES_DIR}/aipod.issue" /etc/issue.d/aipod.issue
install -m 0600 "${FILES_DIR}/appliance.env.example" /etc/aipod/appliance.env.example
cat > /etc/aipod/build.env <<EOF
APPLIANCE_VERSION=${APPLIANCE_VERSION}
ADMIN_USER=${ADMIN_USER}
APP_USER=${APP_USER}
APP_STATE_DIR=${STATE_DIR}
REPO_DIR=${REPO_DIR}
EOF

log "Creating the ${APP_USER} service account"
id "$APP_USER" &>/dev/null || useradd --create-home --shell /bin/bash "$APP_USER"
# Playbooks launched from the UI (for example deploy_dhcp_server.yaml) use become on localhost.
printf '%s ALL=(ALL) NOPASSWD: ALL\n' "$APP_USER" > "/etc/sudoers.d/${APP_USER}"
chmod 0440 "/etc/sudoers.d/${APP_USER}"
visudo -cf "/etc/sudoers.d/${APP_USER}"

log "Cloning ${REPO_URL} (${REPO_BRANCH})"
cd "$APP_HOME"
runuser -u "$APP_USER" -- git clone --branch "$REPO_BRANCH" "$REPO_URL" "$REPO_DIR"

log "Running scripts/setup.sh as ${APP_USER}"
cd "$REPO_DIR"
runuser -u "$APP_USER" -- env HOME="$APP_HOME" PYTHON_BIN=python3.12 \
    GITHUB_TOKEN="${GITHUB_TOKEN:-}" SKIP_ISERVER="${SKIP_ISERVER:-0}" \
    ./scripts/setup.sh --skip-apt
runuser -u "$APP_USER" -- env HOME="$APP_HOME" \
    .venv/bin/python3 -m pip install -r scripts/requirements-webui.txt

log "Preparing automation UI directories"
install -d -o "$APP_USER" -g "$APP_USER" -m 0700 "$STATE_DIR"
install -d -o "$APP_USER" -g "$APP_USER" -m 0750 "${APP_HOME}/playbooks" "${APP_HOME}/playbooks/vars" "${APP_HOME}/deployments"
install -d -o "$APP_USER" -g nginx -m 2775 "$MEDIA_DIR"
if ! grep -q 'aipod-appliance' "${APP_HOME}/.bashrc"; then
    cat >> "${APP_HOME}/.bashrc" <<EOF

# aipod-appliance: Cisco AI PODs tooling
source "${REPO_DIR}/.venv/bin/activate"
cd "${REPO_DIR}"
EOF
fi

log "Applying SELinux policy"
# systemd cannot execute the venv interpreter symlink with its default user_home_t label.
venv_python="${REPO_DIR}/\.venv/bin/python(3(\.[0-9]+)?)?"
semanage fcontext -a -t bin_t "$venv_python" 2>/dev/null || semanage fcontext -m -t bin_t "$venv_python"
restorecon -RF "${REPO_DIR}/.venv/bin" "$MEDIA_DIR"
setsebool -P httpd_can_network_connect 1

log "Opening HTTPS in firewalld"
if systemctl is-active -q firewalld; then
    firewall-cmd --permanent --add-service=https
else
    firewall-offline-cmd --add-service=https
fi

log "Enabling appliance services"
systemctl daemon-reload
systemctl enable aipod-firstboot.service automation-ui.service nginx.service firewalld.service chronyd.service
