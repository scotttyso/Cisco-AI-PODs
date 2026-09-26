# provisioning_web_server

Configures Nginx to serve provisioning images over HTTPS. The role uses Ansible's
generic package and service modules and supports Ubuntu, Debian, RHEL-family,
Fedora, and SUSE-family systems.

By default, files placed in `/usr/share/nginx/html/images` are available from
`https://<server>/`. Directory listing is enabled so provisioning clients can
discover hosted artifacts.

## Usage

Add the target to an inventory group named `provisioning_web_servers`, then run:

```bash
ansible-playbook playbooks/deploy_provisioning_web_server.yaml -i <inventory>
```

Copy images to the server after deployment:

```bash
scp rhcos-live.iso <server>:/tmp/
ssh <server> sudo mv /tmp/rhcos-live.iso /usr/share/nginx/html/images/
```

Set the OpenShift `iso_web_server.image_base_url` to `https://<server>/`.

## TLS

The role generates a self-signed certificate by default. Provisioning clients
must trust that certificate. Add every hostname or address used by clients:

```yaml
provisioning_web_server_name: images.example.com
provisioning_web_tls_subject_alt_name:
  - DNS:images.example.com
  - IP:192.0.2.25
```

To use an existing certificate, install its files on the managed server and set:

```yaml
provisioning_web_tls_self_signed: false
provisioning_web_tls_certificate_path: /etc/pki/tls/certs/images.crt
provisioning_web_tls_private_key_path: /etc/pki/tls/private/images.key
```

## Variables

| Variable | Default | Description |
| --- | --- | --- |
| `provisioning_web_packages` | `[nginx]` | Web server packages installed through the detected package manager. |
| `provisioning_web_service_name` | `nginx` | Service to enable and start. |
| `provisioning_web_root` | `/usr/share/nginx/html/images` | Directory containing provisioning images. |
| `provisioning_web_server_name` | `ansible_fqdn` | Nginx server name and certificate common name. |
| `provisioning_web_tls_self_signed` | `true` | Generate a private key, CSR, and self-signed certificate. |
| `provisioning_web_tls_subject_alt_name` | Server DNS name | Certificate DNS and IP subject alternative names. |
| `provisioning_web_manage_firewall` | `true` | Allow TCP port 443 using UFW or firewalld. |
| `provisioning_web_firewall_backend` | `auto` | Use `ufw`, `firewalld`, `none`, or automatic OS-family selection. |

For unrecognized OS families, web-service configuration still proceeds and the
role reports that port 443 must be opened separately. Override package, service,
configuration, and firewall variables when a distribution uses different paths.