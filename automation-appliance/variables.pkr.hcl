// vCenter connection and placement.
variable "vsphere_server" {
  type        = string
  description = "vCenter FQDN or IP address."
}

variable "vsphere_username" {
  type = string
}

variable "vsphere_password" {
  type      = string
  sensitive = true
}

variable "vsphere_insecure_connection" {
  type    = bool
  default = false
}

variable "vsphere_datacenter" {
  type = string
}

variable "vsphere_cluster" {
  type    = string
  default = null
}

variable "vsphere_host" {
  type        = string
  default     = null
  description = "Optional ESXi host when building without a cluster or to pin the build."
}

variable "vsphere_resource_pool" {
  type    = string
  default = null
}

variable "vsphere_datastore" {
  type = string
}

variable "vsphere_folder" {
  type    = string
  default = null
}

variable "vsphere_network" {
  type        = string
  description = "Port group for the build VM. Needs DHCP unless build_ip_address is set, and Internet access for dnf, pip, git and Ansible Galaxy."
}

variable "vsphere_convert_to_template" {
  type    = bool
  default = true
}

// Installation media: either a datastore path or a URL Packer uploads.
variable "iso_paths" {
  type        = list(string)
  default     = []
  description = "Datastore ISO path, for example [\"[datastore1] iso/Rocky-10.2-x86_64-dvd1.iso\"]."
}

variable "iso_url" {
  type    = string
  default = ""
}

variable "iso_checksum" {
  type        = string
  default     = ""
  description = "Required with iso_url, for example \"file:https://download.rockylinux.org/pub/rocky/10/isos/x86_64/CHECKSUM\"."
}

// Virtual hardware.
variable "vm_name" {
  type    = string
  default = "aipod-automation-rocky10"
}

variable "vm_guest_os_type" {
  type        = string
  default     = "rockylinux_64Guest"
  description = "Use other5xLinux64Guest on vSphere releases without the Rocky Linux guest type."
}

variable "vm_version" {
  type        = number
  default     = 20
  description = "Virtual hardware version (20 = vSphere 8.0)."
}

variable "vm_cpus" {
  type    = number
  default = 4
}

variable "vm_memory_mb" {
  type    = number
  default = 32768
}

variable "vm_disk_size_mb" {
  type        = number
  default     = 262144
  description = "Root disk size. The ISO library can hold multiple 10+ GB images."
}

variable "boot_wait" {
  type    = string
  default = "5s"
}

// Build-time OS account. It remains as the appliance administrator and its
// password is expired at the end of the build unless replaced at first boot.
variable "build_username" {
  type    = string
  default = "aipod"
}

variable "build_password" {
  type      = string
  sensitive = true
}

variable "build_password_hash" {
  type        = string
  sensitive   = true
  description = "SHA-512 crypt hash of build_password, for example from: openssl passwd -6"
}

// Optional static address for the build VM when the build network has no DHCP.
variable "build_ip_address" {
  type    = string
  default = ""
}

variable "build_ip_prefix" {
  type    = number
  default = 24
}

variable "build_gateway" {
  type    = string
  default = ""
}

variable "build_dns_servers" {
  type    = list(string)
  default = []
}

// Appliance content.
variable "appliance_version" {
  type    = string
  default = "1.0.0"
}

variable "repo_url" {
  type    = string
  default = "https://github.com/scotttyso/Cisco-AI-PODs.git"
}

variable "repo_branch" {
  type    = string
  default = "main"
}

variable "github_token" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Optional GitHub token passed to setup.sh to avoid API rate limits."
}

variable "skip_iserver" {
  type    = bool
  default = false
}

variable "output_directory" {
  type    = string
  default = "output"
}

variable "build_qcow2" {
  type        = bool
  default     = true
  description = "Convert the exported disk to qcow2 for OpenShift Virtualization (requires qemu-img)."
}
