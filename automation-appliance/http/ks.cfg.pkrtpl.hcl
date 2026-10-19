# Rocky Linux 10.2 kickstart for the Cisco AI PODs automation appliance (rendered by Packer).
text
cdrom
lang en_US.UTF-8
keyboard us
timezone Etc/UTC
${network} --hostname=localhost.localdomain
firewall --enabled --service=ssh
selinux --enforcing
services --enabled=sshd,chronyd,NetworkManager

rootpw --lock
user --name=${username} --groups=wheel --iscrypted --password=${password_hash}

# Serial console output keeps `virtctl console` usable on OpenShift Virtualization.
bootloader --timeout=1 --append="console=tty0 console=ttyS0,115200n8"
zerombr
clearpart --all --initlabel
reqpart --add-boot
# A plain XFS root (no LVM) lets cloud-init growpart expand larger OpenShift PVCs.
part / --fstype=xfs --size=8192 --grow --label=root

skipx
firstboot --disabled
reboot --eject

%packages
@^minimal-environment
open-vm-tools
qemu-guest-agent
cloud-init
cloud-utils-growpart
-iwl*-firmware
%end

%post --erroronfail
# sshd uses the first value it reads, so this overrides cloud-init's 50-cloud-init.conf.
printf 'PasswordAuthentication yes\nKbdInteractiveAuthentication yes\n' > /etc/ssh/sshd_config.d/01-aipod.conf
chmod 0600 /etc/ssh/sshd_config.d/01-aipod.conf
mkdir -p /etc/cloud/cloud.cfg.d
printf 'datasource_list: [NoCloud, ConfigDrive]\nssh_pwauth: true\nusers: []\nnetwork:\n  config: disabled\n' > /etc/cloud/cloud.cfg.d/99-aipod.cfg

# Build a hypervisor-agnostic initramfs so the VMware-built disk boots with virtio on KubeVirt.
echo 'hostonly="no"' > /etc/dracut.conf.d/90-aipod-generic.conf
dracut --force --regenerate-all
%end
