#!/usr/bin/env bash
# Generalize the appliance before it is exported. Runs as root during the Packer build.
set -euo pipefail

: "${ADMIN_USER:?}"

dnf clean all
rm -rf /var/cache/dnf/* /root/.cache /home/automation-ui/.cache/pip "${FILES_DIR:-/tmp/aipod-files}"

# Every deployment starts with DHCP on its own NIC name until aipod-config runs.
rm -f /etc/NetworkManager/system-connections/*.nmconnection
rm -f /etc/aipod/.configured /etc/aipod/appliance.env
rm -f /etc/ssh/ssh_host_*

cloud-init clean --logs --seed
truncate -s 0 /etc/machine-id
rm -f /var/lib/dbus/machine-id
hostnamectl set-hostname localhost.localdomain

journalctl --rotate
journalctl --vacuum-time=1s
find /var/log -type f -exec truncate -s 0 {} +
rm -rf /tmp/* /var/tmp/*
rm -f /root/.bash_history "/home/${ADMIN_USER}/.bash_history" /home/automation-ui/.bash_history

fstrim -av || true
