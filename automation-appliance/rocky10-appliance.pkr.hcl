packer {
  required_version = ">= 1.11.0"
  required_plugins {
    vsphere = {
      source  = "github.com/hashicorp/vsphere"
      version = ">= 1.4.0"
    }
  }
}

locals {
  export_directory = "${var.output_directory}/${var.vm_name}"

  ks_network = var.build_ip_address == "" ? "network --bootproto=dhcp --device=link --activate --onboot=on" : join(" ", compact([
    "network --bootproto=static --device=link --activate --onboot=on",
    "--ip=${var.build_ip_address}",
    "--netmask=${cidrnetmask("${var.build_ip_address}/${var.build_ip_prefix}")}",
    var.build_gateway == "" ? "" : "--gateway=${var.build_gateway}",
    length(var.build_dns_servers) == 0 ? "" : "--nameserver=${join(",", var.build_dns_servers)}",
  ]))

  kickstart = templatefile("${path.root}/http/ks.cfg.pkrtpl.hcl", {
    username      = var.build_username
    password_hash = var.build_password_hash
    network       = local.ks_network
  })

  sudo = "echo '${var.build_password}' | sudo -S -E"
}

source "vsphere-iso" "rocky10" {
  vcenter_server      = var.vsphere_server
  username            = var.vsphere_username
  password            = var.vsphere_password
  insecure_connection = var.vsphere_insecure_connection
  datacenter          = var.vsphere_datacenter
  cluster             = var.vsphere_cluster
  host                = var.vsphere_host
  resource_pool       = var.vsphere_resource_pool
  datastore           = var.vsphere_datastore
  folder              = var.vsphere_folder

  vm_name              = var.vm_name
  notes                = "Cisco AI PODs automation appliance ${var.appliance_version} (Rocky Linux 10.2)"
  guest_os_type        = var.vm_guest_os_type
  vm_version           = var.vm_version
  firmware             = "efi"
  CPUs                 = var.vm_cpus
  RAM                  = var.vm_memory_mb
  disk_controller_type = ["pvscsi"]
  storage {
    disk_size             = var.vm_disk_size_mb
    disk_thin_provisioned = true
  }
  network_adapters {
    network      = var.vsphere_network
    network_card = "vmxnet3"
  }

  iso_paths    = var.iso_paths
  iso_url      = var.iso_url == "" ? null : var.iso_url
  iso_checksum = var.iso_url == "" ? null : var.iso_checksum
  // Anaconda automatically loads ks.cfg from a volume labeled OEMDRV.
  cd_content   = { "ks.cfg" = local.kickstart }
  cd_label     = "OEMDRV"
  remove_cdrom = true

  boot_order = "disk,cdrom"
  boot_wait  = var.boot_wait
  // Select "Install Rocky Linux" instead of the default media test, then boot it.
  boot_command = [
    "<up>",
    "e",
    "<down><down><end><wait>",
    " inst.text inst.ks=hd:LABEL=OEMDRV:/ks.cfg",
    "<enter><wait><leftCtrlOn>x<leftCtrlOff>",
  ]

  ip_wait_timeout = "45m"
  communicator    = "ssh"
  ssh_host        = var.build_ip_address == "" ? null : var.build_ip_address
  ssh_username    = var.build_username
  ssh_password    = var.build_password
  ssh_timeout     = "45m"

  // Expire the build password inside the same root shell that powers off the VM.
  shutdown_command = "${local.sudo} sh -c 'passwd --expire ${var.build_username} && shutdown -P now'"
  shutdown_timeout = "15m"

  tools_upgrade_policy = false
  convert_to_template  = var.vsphere_convert_to_template

  export {
    force            = true
    output_format    = "ovf"
    manifest         = "sha256"
    output_directory = local.export_directory
  }
}

build {
  name    = "aipod-automation"
  sources = ["source.vsphere-iso.rocky10"]

  // The file provisioner copies a directory's contents only into an existing destination.
  provisioner "shell" {
    inline = ["mkdir -p /tmp/aipod-files"]
  }

  provisioner "file" {
    source      = "${path.root}/files/"
    destination = "/tmp/aipod-files"
  }

  provisioner "shell" {
    execute_command = "${local.sudo} env {{ .Vars }} bash '{{ .Path }}'"
    environment_vars = [
      "ADMIN_USER=${var.build_username}",
      "APPLIANCE_VERSION=${var.appliance_version}",
      "REPO_URL=${var.repo_url}",
      "REPO_BRANCH=${var.repo_branch}",
      "GITHUB_TOKEN=${var.github_token}",
      "SKIP_ISERVER=${var.skip_iserver ? 1 : 0}",
      "FILES_DIR=/tmp/aipod-files",
    ]
    scripts = [
      "${path.root}/scripts/provision.sh",
      "${path.root}/scripts/cleanup.sh",
    ]
  }

  post-processor "shell-local" {
    inline = [
      "python3 '${path.root}/scripts/build_artifacts.py' '${local.export_directory}' --version '${var.appliance_version}' ${var.build_qcow2 ? "" : "--skip-qcow2"}",
    ]
  }
}
