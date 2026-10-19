# Copy to appliance.auto.pkrvars.hcl (git-ignored) and adjust.
# Supply secrets through the environment instead of this file:
#   export PKR_VAR_vsphere_password='...'
#   export PKR_VAR_build_password='...'
#   export PKR_VAR_build_password_hash="$(openssl passwd -6 "$PKR_VAR_build_password")"
#   export PKR_VAR_github_token='...'   # optional

vsphere_server              = "vcenter.example.com"
vsphere_username            = "administrator@vsphere.local"
vsphere_insecure_connection = false
vsphere_datacenter          = "Datacenter"
vsphere_cluster             = "Cluster"
vsphere_datastore           = "datastore1"
vsphere_folder              = "Templates"
vsphere_network             = "VM Network"

iso_paths = ["[datastore1] iso/Rocky-10.2-x86_64-dvd1.iso"]
# Or let Packer upload the ISO instead of iso_paths:
# iso_url      = "https://download.rockylinux.org/pub/rocky/10/isos/x86_64/Rocky-10.2-x86_64-dvd1.iso"
# iso_checksum = "file:https://download.rockylinux.org/pub/rocky/10/isos/x86_64/CHECKSUM"

# Optional static build address when the build port group has no DHCP.
# build_ip_address  = "192.0.2.50"
# build_ip_prefix   = 24
# build_gateway     = "192.0.2.1"
# build_dns_servers = ["192.0.2.53"]

appliance_version = "1.0.0"
repo_url          = "https://github.com/scotttyso/Cisco-AI-PODs.git"
repo_branch       = "main"
