# Nexus Dashboard 4.2.x — Troubleshooting & Recovery

Empirical findings from a 4.2.1.10 lab build. Everything in this document was
observed live; nothing is theoretical. Where API responses or CLI output is
quoted, it was captured verbatim from the lab.

This is the single source of truth. The `automation/README.md` and
`docs/MOP-ND4-install.md` link here rather than duplicating it.

---

## Quick index

| Symptom | Section |
|---|---|
| `POST /v2/bootstrap/cluster` → 500 `Pending cluster bootstrap exists` | [§1](#1-pending-cluster-bootstrap-exists) |
| `POST /bootstrap/verifyremoteservices` → 500 `Could not resolve host` | [§2](#2-verifyremoteservices-fails-on-ntp-dns-resolution) |
| Data plane (`bond0`) shows no carrier; ND-2/ND-3 unreachable from ND-1 | [§3](#3-stp-bridge-assurance-blocks-the-data-vlan) |
| `acs reboot ...` from SSH returns immediately, ND stays online | [§4](#4-acs-reboot-from-ssh-doesnt-take-effect) |
| `sudo: command not found` in `rescue-user` shell | [§5](#5-sudo-does-not-exist-in-the-rescue-user-shell) |
| `acs show cluster` hangs forever | [§6](#6-acs-show-cluster-hangs-when-no-cluster-is-formed) |
| `/bootstrap/status` returns `bootstrapped=false` but commits still fail | [§7](#7-bootstrapstatus-is-not-authoritative-when-a-pending-record-exists) |
| `fabric0/fabric1` admin-down after first-boot dialog | [§8](#8-fabric0fabric1-stay-down-until-cluster-commit-this-is-normal) |
| ND-1 CIMC IP doesn't match the mgmt subnet | [§9](#9-ND-1-cimc-may-live-on-the-data-subnet-not-the-mgmt-subnet) |
| Need to start over without re-installing the OS (~3 h saved) | [§10](#10-recovery-without-os-reinstall-acs-reboot-factory-reset) |
| "What is ND-1 showing right now?" (no human eyes on KVM) | [§11](#11-sol-peek-with-nudge-as-programmatic-state-source) |
| First-boot dialog asks for fewer fields than older docs say | [§12](#12-nd-42x-first-boot-dialog-is-only-5-prompts) |
| `error: Invalid ip address - expecting A.B.C.D` after a nudge | [§13](#13-do-not-nudge-at-strictly-validating-prompts) |
| `POST /v2/bootstrap/cluster` → 500 `Node CIMC/Mgmt IP <off-mgmt-VLAN IP> is not reachable` | [§14](#14-cluster-commit-fails-because-mgmt-vlan-cant-route-to-cimcs-on-another-vlan) |
| Need to allocate any IP (CIMC, persistent pool, future node) | [§15](#15-never-allocate-an-ip-without-lab-owner-approval) |
| "What VLAN/subnet is _that_? Which VRF is it in?" | [§16](#16-lab-network-topology-reference) |
| Cluster bootstrap fails at `Setup boot time configuration` with "installed firmware version is incompatible" | [§17](#17-secondary-node-firmware-version-mismatch-blocks-cluster-commit) |
| Restarting a failed bootstrap: which wizard values are retained? | [§18](#18-restart-bootstrap-retains-non-secret-wizard-configuration-on-431) |

---

## 1. Pending cluster bootstrap exists

### Symptom

```
POST /v2/bootstrap/cluster
HTTP/1.1 500
{"error":"Pending cluster bootstrap exists - please cleanup and retry"}
```

This sticks across logout, browser refresh, and re-login. The wizard UI
re-shows the same form indefinitely; submitting it always returns the same
500.

### Why

ND persists a "draft" cluster record the moment any wizard step writes
state — long before the final commit. There is **no API endpoint** to abort,
delete, or supersede that draft. We confirmed this empirically with
[`scripts/probe_cleanup.py`](../scripts/probe_cleanup.py); the matrix below
shows every endpoint we tried:

| Method | Path | Result |
|---|---|---|
| `DELETE` | `/v2/bootstrap/cluster` | 405 Method Not Allowed |
| `DELETE` | `/bootstrap/cluster` | 405 |
| `POST` | `/bootstrap/reset` | 500 (only valid in `failed` state, not `pending`) |
| `POST` | `/v2/bootstrap/recover` | 500 (same) |
| `POST` | `/bootstrap/abort` | 404 |
| `POST` | `/bootstrap/cancel` | 404 |
| `POST` | `/bootstrap/cleanup` | 404 |
| `POST` | `/bootstrap/clear` | 404 |
| `POST` | `/bootstrap/discard` | 404 |
| `POST` | `/v2/bootstrap/abort` | 404 |
| `POST` | `/v2/bootstrap/cancel` | 404 |
| `POST` | `/v2/bootstrap/cleanup` | 404 |
| `PUT` | `/v2/bootstrap/cluster` | 405 |
| `POST` | `/v2/bootstrap/cluster?force=true` | 500 (same pending error) |
| `POST` | `/v2/bootstrap/cluster?reconfigureBootstrap=true` | 500 (same) |
| `POST` | `/v2/bootstrap/node?force=true` (with empty payload) | 500 |

The verify steps (`/bootstrap/verifyexternalservice`,
`/verifyclustersubnets`, `/verifyremoteservices`) and the persona POST
(`/v2/bootstrap/persona`) **return 200 but do not transition or clear the
pending record.** They are stateless precondition checks.

### Fix

Run `acs reboot factory-reset` on ND-1. See [§10](#10-recovery-without-os-reinstall-acs-reboot-factory-reset)
for the exact procedure. This wipes only the bootstrap config (not the OS),
takes ~5–6 min, and returns you to the first-boot console dialog.

### Prevention

- Don't run partial wizard flows. If you POST `/v2/bootstrap/persona` you
  have created a pending record, even if you never POST `/v2/bootstrap/cluster`.
- The automation now structures the wizard flow as **verify-only by default**,
  and only writes the persona + cluster on the final `--commit` flag (see
  [`scripts/wizard_flow_retry.py`](../scripts/wizard_flow_retry.py)).
- A best-effort precheck heuristic catches the common retry case:
  [`scripts/precheck.py --category bootstrap`](../scripts/precheck.py)
  (`bootstrap.no_pending_state`) authenticates to ND-1 and inspects the
  bootstrap state. **Honest API limitation:** `GET /bootstrap/status`
  returns the same body
  (`{"bootstrapped":false,"message":"Cluster is not bootstrapped"}`)
  whether the node is in a clean-not-bootstrapped state or has a pending
  draft from a half-failed prior commit — verified empirically against
  ND 4.2.1.10 ([`logs/probe-cleanup-20260425T040218Z.log`](../logs/probe-cleanup-20260425T040218Z.log)
  shows POST returning 500 with the pending error while the simultaneous
  GET returns the clean shape). The precheck therefore WARNs (not FAILs)
  with both interpretations spelled out and a pointer to this section,
  rather than emitting a noisy false-positive on every legit first run.
  We deliberately did **not** add a destructive write probe to a
  non-destructive precheck. The recovery is the same regardless:
  [§10](#10-recovery-without-os-reinstall-acs-reboot-factory-reset)
  on ND-1.

---

## 2. `verifyremoteservices` fails on NTP DNS resolution

### Symptom

```
POST /bootstrap/verifyremoteservices
HTTP/1.1 500
{
  "ntpErrors": [
    "[{1.ntp.esl.cisco.com Could not resolve host with any provided nameserver }
      {2.ntp.esl.cisco.com ...}]"
  ]
}
```

DNS check passed; only NTP failed.

### Why

ND only uses the DNS servers listed in the bootstrap payload to resolve NTP
hostnames. The lab DNS (`192.0.2.53`, `192.0.2.54`) does not have a
forwarder for `*.esl.cisco.com`, so the lookups fail before NTP can run.

### Fix (pick one)

| Option | Pros | Cons |
|---|---|---|
| Use NTP **IP literals** (`198.51.100.124`, `198.51.100.125`) and keep the lab DNS | No DNS dependency for NTP | If NTP IPs ever change you have to update the bootstrap payload |
| Use a DNS server that **can** resolve `*.esl.cisco.com` | NTP hostnames are portable | Lab DNS may not be able to reach that DNS |

This lab uses **NTP IP literals + lab DNS**, configured in
[`inventories/lab/group_vars/nd_cluster.yml`](../../../inventories/lab/group_vars/nd_cluster.yml) and mirrored to
[`logs/bootstrap-final-payload.json`](../logs/bootstrap-final-payload.json):

```yaml
ntp:
  servers:
    - host: 198.51.100.124
      preferred: true
    - host: 198.51.100.125
dns:
  providers:
    - 192.0.2.53
    - 192.0.2.54
```

### Prevention

Add a pre-flight DNS check to your runbook:

```bash
# From a host on the same subnet ND-1 will sit on:
for ntp in 1.ntp.esl.cisco.com 2.ntp.esl.cisco.com; do
  for dns in 192.0.2.53 192.0.2.54; do
    echo -n "  $dns -> $ntp : "
    dig @"$dns" +short +time=2 +tries=1 "$ntp" || echo "(no answer)"
  done
done
```

If any combination returns no answer, switch that NTP entry to an IP literal
**before** running the bootstrap.

---

## 3. STP Bridge Assurance blocks the data VLAN

### Symptom

ND-1 came up on its mgmt IP. The cluster wizard validated CIMC reachability
to ND-2/ND-3 (out-of-band). But the eventual data-plane handshake silently
failed and ND-1 could not orchestrate ND-2/ND-3 over the data network.

On the FEX:

```
AB05-9336-FEX# sh spanning-tree vlan 1240

VLAN1240
  Spanning tree enabled protocol rstp
  ...
  Eth106/1/3       Desg BA_Inc 4 P2p Bound(PVST)
                                    ^^^^^^
                                    Bridge-assurance inconsistent
```

`BA_Inc` = Bridge Assurance Inconsistent. The port forwards BPDUs but blocks
data because the upstream port type doesn't match.

### Why

The ND data NICs come up as access ports on VLAN 1240. The FEX server-facing
port was configured as `spanning-tree port type network` (expecting BPDUs
from the peer) but the ND VIC is an end-station and does not send BPDUs. The
fabric saw the absence of BPDUs as a peer failure and put the port in
inconsistent state.

### Fix

On the access switch, set the ND-facing port type to `edge` (or `normal`,
depending on platform), **not** `network`:

```
interface Ethernet106/1/3
  spanning-tree port type edge
```

Validate:

```
sh spanning-tree vlan 1240 | inc Eth106/1/3
# expect: Eth106/1/3   Desg FWD ...   (no BA_Inc)
```

### Prevention — add to deployment prerequisites

Before installing ND, verify the data-plane access ports:

```
sh interface eth<x>/<y> switchport          # confirm access mode + correct VLAN
sh spanning-tree interface eth<x>/<y> detail # port type must be 'edge' or 'normal',
                                            # NOT 'network'
sh cdp neighbor eth<x>/<y>                  # confirm correct ND chassis
```

This is captured as a prerequisite in
[`docs/MOP-ND4-install.md`](../../docs/MOP-ND4-install.md#assumptions-and-prerequisites)
and [`README.md` § Prerequisites > Network](../../README.md#network).

The automation also has a **partial signal** for this failure mode once
ND-1 has its mgmt IP: `precheck.py` runs `network.nd1_data_to_gw`
(SSHes `rescue-user@nd-1` and pings the data gateway from bond0). If
BA_Inc has blocked the data VLAN, the data gateway will be unreachable
from ND-1 and the check FAILs with a pointer back to this section.
This is *partial* — gateway might still be reachable in some BA_Inc
edge cases while inter-node data-plane is broken — so the switch-side
`sh spanning-tree` capture above remains the authoritative check and
should be in your change ticket regardless.

---

## 4. `acs reboot ...` from SSH doesn't take effect

### Symptom

```bash
ssh rescue-user@<nd-mgmt> 'nohup acs reboot factory-reset &'
# command returns immediately; ND stays online
```

### Why

`nohup` writes the daemon file but the SSH `exec` channel still SIGHUPs the
process when the channel closes. `acs reboot` exits before its async work
fires.

### Fix

Run `acs reboot ...` **foreground** with stdin piped to answer the
confirmation prompt. The SSH session terminating *is* the success signal:

```bash
# Correct: foreground, stdin pipe, no -tt (a real TTY consumes the pipe early)
ssh -o ServerAliveInterval=15 -o ServerAliveCountMax=2 \
    rescue-user@<nd-mgmt> \
    "printf 'y\n' | acs reboot factory-reset"
# expect: SSH connection drops within a few seconds (the node is rebooting)
```

| Pitfall | Why it fails |
|---|---|
| `ssh ... 'nohup acs reboot ... &'` | SIGHUP on channel close |
| `ssh -tt ... 'echo y \| acs ...'` | `-tt` forces a real TTY; `acs` reads the prompt before the pipe writes |
| `ssh ... 'sudo acs reboot ...'` | `sudo` is not in `rescue-user`'s `PATH` (see [§5](#5-sudo-does-not-exist-in-the-rescue-user-shell)) |

---

## 5. `sudo` does not exist in the `rescue-user` shell

### Symptom

```bash
$ sudo systemctl status whatever
sudo: command not found
```

Earlier `sudo systemctl ...` invocations appeared to "work" silently — they
were actually failing the same way; their stdout was just empty so nothing
was visible.

### Why

`rescue-user` is a hardened maintenance account. Its `PATH` does not include
`/usr/bin/sudo`, and the user already owns the `acs` toolchain — there is no
need to escalate.

### Fix

Drop `sudo`. Run `acs` and most diagnostic tools directly:

```bash
ssh rescue-user@<nd-mgmt>
acs health
acs version
acs reboot factory-reset
```

NB: the command on ND 4.2.x is `acs version` — *not* `acs show version`.
`acs show` only accepts `{cluster,nodes,masters,workers,...}` as subcommands
and rejects `version` with a usage error. Verified empirically against
ND-1 (4.2.1.10) on 2026-04-28 while writing the
[`version.*` precheck category](../scripts/precheck.py).

For tools genuinely outside the `acs` umbrella, you must use the host
console (CIMC vKVM) and become root via the OS install path, not from
`rescue-user`.

---

## 6. `acs show cluster` hangs when no cluster is formed

### Symptom

```bash
$ acs show cluster
# (hangs indefinitely; no output)
```

### Why

The command waits for a cluster manager response. Pre-bootstrap there is no
cluster manager.

### Fix

Don't use `acs show cluster` as a probe in the bootstrap window. Use the
HTTPS API instead — `GET /bootstrap/status` is fast and returns even when
no cluster exists (subject to caveat in [§7](#7-bootstrapstatus-is-not-authoritative-when-a-pending-record-exists)).

```bash
curl -ksS -X GET "https://<nd-mgmt>/bootstrap/status" \
    -H "Authorization: Bearer $JWT" | jq .
```

---

## 7. `/bootstrap/status` is not authoritative when a pending record exists

### Symptom

```json
GET /bootstrap/status
{ "bootstrapped": false }
```

…immediately followed by:

```
POST /v2/bootstrap/cluster
500 Pending cluster bootstrap exists
```

### Why

`/bootstrap/status` reports whether the cluster has finished bringing up
services. It does **not** report on draft/pending records that block new
commits. They are different state machines.

### Fix

Treat `/bootstrap/status` as informational only. To know whether the system
will accept a new commit, send a real (idempotent) probe — e.g. a
`/bootstrap/verifyclustersubnets` POST. A 200 means "the wizard is open"; a
500 with the pending-bootstrap error means [§1](#1-pending-cluster-bootstrap-exists)
applies.

---

## 8. `fabric0`/`fabric1` stay down until cluster commit — this is normal

### Symptom

After the first-boot dialog completes and ND-1 is reachable on its mgmt IP,
SSH in and check:

```
$ ip -br link show fabric0 fabric1 bond0
fabric0   DOWN
fabric1   DOWN
bond0     DOWN
```

### Why

ND only configures the data bond after it learns the data-network details
from the cluster bootstrap commit. Until then there is no IP, no link mode
selected, and no carrier. This is by design.

### Fix

Do **not** try to `ip link set fabric0 up` manually — you'll race the
bootstrap configuration. Just commit the cluster (Procedure 3 in the MOP);
the bond comes up as part of that flow.

If after the cluster commit `bond0` still has no carrier, **then** check:
- Switch port: VLAN, mode, STP type ([§3](#3-stp-bridge-assurance-blocks-the-data-vlan))
- Cabling: physical link LEDs on the VIC
- LLDP: `lldpcli show neighbors` to confirm the right switch/port

---

## 9. ND-1 CIMC may live on the data subnet, not the mgmt subnet

### Symptom

You assume CIMCs are on `<mgmt-subnet>`/x and try to reach them there; only
2 of 3 answer.

### Why

In some lab topologies (this one included), one or more ND chassis CIMCs
are cabled to the data subnet, not the mgmt subnet. ND-1's CIMC in this lab
is `198.18.0.7` (data), while ND-1's host mgmt IP is `192.0.2.7` (mgmt).

This is **not** wrong — ND CIMC and ND host networking are independent — but
it surprises automation that infers CIMC IP from host mgmt IP.

### Fix

Always read the CIMC IP from canonical inventory (`inventories/lab/host_vars/nd-*.yml`), never infer
it. The automation does this; document it explicitly in your runbook so a
human troubleshooter doesn't go looking on the wrong subnet.

```yaml
# inventories/lab/host_vars/nd-*.yml — CIMC and ND-MGMT are different subnets
- hostname: nd-1
  cimc:  { ip: 198.18.0.7,   user: admin, pass_ref: CIMC_PASSWORD }
  mgmt:  { ip: 192.0.2.7,   mask: 24, gateway: 192.0.2.254 }
  data:  { ip: 198.18.0.17,  mask: 24, gateway: 198.18.0.254 }
```

---

## 10. Recovery without OS reinstall: `acs reboot factory-reset`

This is the operator's most important recovery primitive for ND 4.2.x. It
saves ~3 hours per node compared to a CIMC-driven ISO reinstall.

### What it does

- **Wipes** the cluster bootstrap configuration (admin password, mgmt IP,
  cluster identity, pending records — see [§1](#1-pending-cluster-bootstrap-exists)).
- **Preserves** the OS install on disk.
- Reboots the node in ~5 min and lands back at the **first-boot setup**
  console dialog (the same one the orchestrator drives in
  [`scripts/sol_bootstrap.py`](../scripts/sol_bootstrap.py)).

### When to use it

| Situation | Use factory-reset? |
|---|---|
| `Pending cluster bootstrap exists` 500 you can't clear ([§1](#1-pending-cluster-bootstrap-exists)) | **Yes** |
| Wrong mgmt IP / admin password committed at first-boot | **Yes** |
| Want to swap a node between Primary and Standby personas pre-cluster | **Yes** |
| Cluster is healthy but a service is misconfigured | **No** — use `acs` service commands |
| Disk replacement / hardware swap | **No** — re-image via CIMC ISO |

### Procedure

```bash
# 1. Source CIMC + ND admin passwords from macOS Keychain (no plaintext!)
export CIMC_PASSWORD=$(security find-generic-password -s "nd-lab-cimc"  -a asharma -w)
export ND_ADMIN_PASSWORD=$(security find-generic-password -s "nd-lab-admin" -w)

# 2. Trigger factory-reset (foreground, stdin pipe, no -tt; see §4)
ssh -o ServerAliveInterval=15 -o ServerAliveCountMax=2 \
    rescue-user@192.0.2.7 \
    "printf 'y\n' | acs reboot factory-reset"
# expect: SSH connection drops within seconds; ND-1 is rebooting

# 3. Wait for the first-boot dialog (poll the CIMC SOL or the KVM console)
#    Typical wall time from command issue -> first-boot prompt: ~6-11 min.

# 4. Mark only the 'bootstrap' phase un-done in state, so the orchestrator
#    re-drives the SOL dialog without re-doing the install.
python -c '
import json, pathlib
p = pathlib.Path("state/node1.json")
s = json.loads(p.read_text())
s.setdefault("phases", {}).pop("bootstrap", None)
s.setdefault("_history", []).append({
    "ts": "<UTC-timestamp>",
    "note": "acs reboot factory-reset cleared bootstrap config; bootstrap phase removed",
})
p.write_text(json.dumps(s, indent=2))
'

# 5. Re-run the orchestrator. It skips installer phases and drives only the
#    SOL first-boot dialog.
.venv/bin/python scripts/main.py node1
```

After ND-1 comes back up on its mgmt IP, run the cluster bringup with
`scripts/wizard_flow_retry.py --commit`.

### Why not `acs reset`, `acs cluster reset`, etc.?

We probed every `acs` subcommand on a `rescue-user` shell:

| Command | Result |
|---|---|
| `acs reset` | Not a command |
| `acs cluster reset` | Hangs (no cluster — see [§6](#6-acs-show-cluster-hangs-when-no-cluster-is-formed)) |
| `acs reboot` | Plain reboot; preserves all config |
| `acs reboot factory-reset` | **The one we want** |
| `acs reboot upgrade` | Different code path; for upgrades only |

`acs reboot factory-reset` is the only command that clears bootstrap
config without a full OS reinstall.

---

## 11. SOL peek-with-nudge as programmatic state source

### Symptom (or really: wrong reflex)

You want to know what ND-X is currently displaying. You ask a human to
KVM in and read the screen, or you wait for someone to send a screenshot.

### Why this happens

A bare SSH-into-CIMC + `connect host` SOL session only forwards **live**
console bytes — it does **not** replay history. So if the OS is sitting
quiescently at a prompt (waiting for input), your SOL session sees only
the CIMC banner (`Press Ctrl+x to Exit the session`) and nothing else.
This makes SOL *look* useless for state inspection, and the natural
fallback is human eyeballs on KVM.

### Fix

Send a single CR (`\r`) immediately after `connect host`. Most prompts
will repaint themselves on a fresh newline (the underlying `read` loop
re-emits the prompt). For input-validating prompts that reject empty
input, the validator's error message itself is informative — see
[§13](#13-do-not-nudge-at-strictly-validating-prompts) for caveats.

The minimal one-shot peek (no production code involved):

```python
# logs/firstboot-explore/<ts>-peek.py — throwaway form
import os, time, paramiko, re
pw = os.environ['CIMC_PASSWORD']
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("198.18.0.7", username="admin", password=pw, timeout=15,
          allow_agent=False, look_for_keys=False)
ch = c.invoke_shell(); ch.settimeout(2.0); time.sleep(1.0)
while ch.recv_ready(): ch.recv(65536)
ch.send(b"connect host\n"); time.sleep(1.0)
while ch.recv_ready(): ch.recv(65536)
ch.send(b"\r"); time.sleep(0.5)            # the nudge
buf = bytearray(); deadline = time.time()+12
while time.time() < deadline:
    if ch.recv_ready(): buf.extend(ch.recv(65536))
    time.sleep(0.2)
ch.send(b"\x18q"); ch.close(); c.close()
print(re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', bytes(buf).decode().replace('\r','')))
```

For a one-liner, use the `tail-sol` orchestrator subcommand:

```bash
.venv/bin/python scripts/main.py tail-sol --node nd-1 --seconds 12
```

That wraps the same connect → nudge → drain → cleanup, sourcing the
CIMC password from `$CIMC_PASSWORD` (Keychain).

### Prevention

Treat KVM as a last resort, not a first reflex. SOL-peek-with-nudge is:
- programmatic (no human in the loop),
- idempotent (repeated peeks don't change box state — except the deliberate
  nudge, which is bounded by [§13](#13-do-not-nudge-at-strictly-validating-prompts)),
- cheap (~12 s wall-clock per peek).

This pattern was added on 2026-04-25 after we caught ourselves asking
for a screenshot to confirm post-`acs reboot factory-reset` state when
SOL could have answered the same question in 12 seconds.

---

## 12. ND 4.2.x first-boot dialog is only 5 prompts

### Symptom

You write a SOL expect/send script based on documentation from an older
ND minor (or from CVDs that target Cisco APIC), expecting prompts for
admin password, IP/mask, gateway, **DNS**, **NTP**, **hostname**, **search
domain**, and **timezone**. Your script blocks on a DNS prompt that
never appears, and the OS quietly proceeds to reboot.

### Why this happens

ND 4.2.1.10 deliberately keeps the console first-boot minimal. Only the
fields needed to make the box reachable on its mgmt IP are asked on
serial. Everything else (DNS, NTP, search domain, hostname, timezone,
persistent IPs, internal pod/service CIDRs, app/service deployments) is
configured **after** the box is reachable, via `POST /v2/bootstrap/cluster`
and the cluster bringup wizard.

### The complete first-boot prompt sequence (verified)

Captured via `logs/firstboot-explore/` against ND 4.2.1.10 on 2026-04-25:

| # | Exact prompt text | Acceptable input | Notes |
|---|---|---|---|
| 1 | `Admin Password: ` | password (echoed `*`) | Stored in iText hash; used for `admin` role on REST and console. |
| 2 | `Re-enter Admin Password: ` | same password | Mismatch re-prompts both. |
| 3 | `IP Address/Mask: ` | `A.B.C.D/NN` | Slash-CIDR is required; bare IP is rejected. |
| 4 | `Gateway: ` | `A.B.C.D` | Bare IP only; CIDR or empty is rejected (see §13). |
| 5 | `Re-enter config?(y/N): ` | `y` (re-enter) / `n` (accept) | Default capital N = accept. We send `n` explicitly. |

After prompt 5 the OS prints:
```
System configured successfully
Initializing System on first boot. Please wait..
Sat Apr 25 19:52:48 UTC 2026: Nexus Dashboard setup complete.
```
…and reboots into normal multi-user. ~3-5 minutes later the mgmt IP
answers HTTPS on `:443`.

### Fix

`scripts/sol_bootstrap.py::bootstrap_first_primary` was updated to the
verified 5-prompt sequence on 2026-04-25 (CHANGELOG D-006). The
production flow is now:

```
nudge → expect FIRSTBOOT|BOOTSTRAP_PRIMARY|ADMIN_PASSWORD →
admin_password → reenter → ip/mask → gateway → re-enter? n
→ wait_for_bootstrap_complete (≤8 min on slow disks)
```

### Prevention

If a future ND minor adds prompts, the regex for the new prompt **must**
be added to the sequence; otherwise the script will send the wrong value
into the new field. Always run `scripts/main.py tail-sol --node NDx`
once on a fresh install to confirm the prompt list before changing
`bootstrap_first_primary`.

---

## 13. Do not nudge at strictly-validating prompts

### Symptom

```
error: Invalid ip address - expecting A.B.C.D
  Gateway: 
```

You sent a bare CR (`\r`) to "repaint" or "wake up" the console, and the
OS interpreted the empty input as an attempted answer to a strict-IPv4
prompt, failed validation, and re-prompted with an error.

### Why this happens

Prompts 3 (`IP Address/Mask: `) and 4 (`Gateway: `) of the first-boot
dialog are backed by a `read` loop that pipes the input into a strict
`A.B.C.D[/NN]` validator. Empty input fails validation. The same is true
of the `Re-enter config?(y/N):` prompt, where empty input is silently
treated as the default (`N`) and advances state — equally undesirable
during a peek.

### Fix

Restrict the nudge to the entry-screen disambiguation only:

```python
# scripts/sol_bootstrap.py::bootstrap_first_primary
self._nudge()                                    # OK: at firstboot/menu/password
self._expect_one_of([                            # OK: branches on which screen
    PROMPT_FIRSTBOOT,
    PROMPT_BOOTSTRAP_PRIMARY,
    PROMPT_ADMIN_PASSWORD,
], timeout_s=timeout_s)
# ...
self._send_line(inp.admin_password, redact=True) # FROM HERE DOWN, NO NUDGES
self._expect(PROMPT_REENTER_PASSWORD, ...)       #   each prompt strictly validates
self._send_line(inp.admin_password, redact=True) #   input - a bare CR will
self._expect(PROMPT_MGMT_IP, ...)                #   trigger a validator error
self._send_line(f"{inp.mgmt_ip}/{inp.mgmt_mask}")#   and re-prompt.
self._expect(PROMPT_MGMT_GW, ...)
self._send_line(inp.mgmt_gateway)
self._expect(PROMPT_CONFIRM_CONFIG, ...)
self._send_line("n")
```

### Prevention

When using `tail-sol` (or the inline peek snippet from §11) to inspect
state past the admin-password step, **do not send a CR**. Instead, just
attach SOL and wait the full drain window (`--seconds 12`). The console
is silent only because it's holding at a prompt; you don't need to
poke it to see what's there as long as you can wait for the next byte.

If you absolutely must induce output (e.g., the box is mid-systemd
"Wait for Network" with no recent log lines), prefer reading from
`acs status` over SSH on the mgmt IP once it's up, rather than SOL.

---

## 14. Cluster commit fails because mgmt VLAN can't route to CIMCs on another VLAN

### Symptom

```
POST /v2/bootstrap/cluster
HTTP/1.1 500
Node CIMC/Mgmt IP 198.18.0.8 is not reachable
```

The verify steps (`/bootstrap/verifyexternalservice`, `verifyclustersubnets`,
`verifyremoteservices`) all returned 200. Persona POST (`/v2/bootstrap/persona`)
also returned 200. Only the final `/v2/bootstrap/cluster` commit fails, with a
`not reachable` message naming a CIMC IP that lives on a VLAN/subnet other than
the ND-MGMT VLAN.

### Why

ND-1's `bond1` (mgmt) is the only interface up at this stage of bringup. The data
interface (`bond0` on the ND-DATA VLAN) is held down by ND until cluster commit
pre-flight succeeds — which itself requires reachability to the other nodes' CIMCs.
If those CIMCs sit on a VLAN other than ND-MGMT (e.g. on the ND-DATA VLAN, as in
[§9](#9-ND-1-cimc-may-live-on-the-data-subnet-not-the-mgmt-subnet), or on a
dedicated CIMC VLAN), and there is no L3 route from the ND-MGMT-VLAN gateway to
that CIMC subnet, ND-1 has zero L3 path to the CIMCs at the moment of pre-flight
and commit fails before `bond0` can be lit.

The L1 link state on the data ports is **not** the issue here. We confirmed via
Redfish that all 3 nodes have `LinkStatus=Up Speed=10000Mbps` on VIC `Port-1` and
`Port-2`. The cabling is in, the leaf ports are up, the optics are seated. The
gap is purely L3 reachability from the mgmt VLAN to the CIMC VLAN.

### Diagnosis recipe (read-only, safe)

From the workstation, prove the gap end-to-end:

```bash
ssh rescue-user@<ND-1-mgmt-IP> 'for ip in <mgmt-gw> <CIMC-1> <CIMC-2> <CIMC-3>; do
  printf "%-15s : " "$ip"
  ping -c 2 -W 2 "$ip" >/dev/null 2>&1 && echo OK || echo FAIL
done'
```

The mgmt GW must be `OK`. CIMC IPs being `FAIL` while a workstation on the campus
VPN (or any other vantage point with a route to the CIMC subnet) can ping them is
the smoking gun.

The same probe is now automated in
[`scripts/precheck.py`](../scripts/precheck.py) as
`network.nd1_to_cimc.<host>` — once ND-1 has its mgmt IP, the precheck
SSHes `rescue-user@nd-1` and pings each *secondary's* CIMC over the same
default-routing path the cluster-commit pre-flight will use, then FAILs
with a pointer back to this section if any are unreachable. This catches
the failure ~30 s after Phase 5 completes (i.e. before any cluster-commit
attempt is made), instead of mid-commit. See `--category network` in
[§A of the precheck checklist](precheck-checklist.md#a-automation-side-runs-precheckpy).

For the complete original evidence (Linux state, route table, Redfish link state,
ND-side and workstation-side reachability matrix), see the captured snapshot:
[`automation/logs/lab-routing-diag-20260425T210723Z.log`](../logs/lab-routing-diag-20260425T210723Z.log)

### Fix — two paths, choose by lab topology

#### Path A (preferred, what we did in this pod): re-IP the CIMCs onto a lab segment ND-1 can reach without a tenant-VRF/FW change

Move the CIMC IPs to addresses on a segment that ND-1's mgmt interface
(`bond1`) reaches over a single, lab-owned L3 path — i.e. either L2-adjacent
to ND-MGMT, or in the same VRF as ND-MGMT with a pre-permitted FW between
them. In this pod that is the **Lab OOB-MGMT VLAN** (`198.51.100.0/24`,
VLAN 10): same lab VRF as ND-MGMT (`192.0.2.0/24`, VLAN 4), reachable
through a pre-permitted lab firewall, no rule change needed. We re-IP'd to
`198.51.100.87/88/89` (allocation approved by the subnet owner per
[D-010](../../CHANGELOG.md#d-010--never-allocate-an-ip-without-explicit-lab-owner-approval)).
See [decision D-011](../../CHANGELOG.md#d-011--cimcs-live-on-the-lab-oob-mgmt-vlan-to-keep-cluster-commit-pre-flight-on-a-single-lab-vrf-path)
for the full rationale, including why an earlier proposal to co-locate CIMCs
on ND-MGMT itself ([D-009](../../CHANGELOG.md#d-009--cimcs-live-on-the-nd-mgmt-vlan-superseded-by-d-011), now
superseded) was abandoned. See [§16](#16-lab-network-topology-reference) for
the lab/tenant VRF map this guidance is tuned to.

Per-CIMC procedure (web UI or SSH):

```text
ssh admin@<old-CIMC-IP>
scope cimc
scope network
set dhcp-enabled no
set v4-addr <new-CIMC-IP-on-target-segment>
set v4-netmask 255.255.255.0
set v4-gateway <target-segment-gateway>
commit                    # session drops; reconnect at new IP
```

**Lab-side prerequisite:** the switch access port carrying each CIMC `M`
RJ-45 must be in the target VLAN before the new IP comes up. In this pod the
CIMC `M` ports were already in the Lab OOB-MGMT VLAN (VLAN 10), so no port
flip was needed. If the chassis `M` ports are cabled to a port in the wrong
VLAN, the lab admin must flip the access VLAN as part of this change — and
the order matters: change the IP first (over the still-working old VLAN),
*then* flip the port. Flipping the port first leaves the CIMC stranded on
the old subnet on a switch port for a different VLAN, and the only recovery
is a console cable to the chassis or a port-flip-back.

After all 3 CIMCs are at their new IPs, update inventory + payload + MOP, then
re-run `scripts/wizard_flow_retry.py --commit`.

#### Path B (only viable when no firewall / VRF separates the segments): add an L3 route

Add a static route on the lab's ND-MGMT-VLAN gateway for the CIMC subnet,
next-hop being the L3 device that already terminates the campus mgmt prefix
and reaches the CIMC subnet. **Critical caveat:** this only works if the CIMC
VLAN sits in the **same VRF** as ND-MGMT *and* there is no firewall in the path
that would block the new flows. In our pod we confirmed the two segments live
in **different VRFs** with a firewall in between, which is why we took Path A.

For the original (now-superseded) Path B writeup with the route command and
validation recipe, see
the site network team's routing request (lab copy kept outside the repository)
(retained as a reference for pods where Path B is feasible).

### Recovery after either path

Re-run the diagnosis recipe above; all four rows must say `OK`. Then re-run
`scripts/wizard_flow_retry.py --commit`. Persona is likely already accepted
from the prior attempt, so the wizard will go straight through verifies,
re-POST persona (which is idempotent for an unchanged payload), then succeed
at `/v2/bootstrap/cluster`. If instead it returns
`Pending cluster bootstrap exists`, fall through to [§1](#1-pending-cluster-bootstrap-exists)
+ [§10](#10-recovery-without-os-reinstall-acs-reboot-factory-reset).

### Prevention

Treat **CIMCs on a lab-VRF segment ND-1 can reach without a tenant-VRF/FW
change** as the default deployment posture in
[`MOP § Assumptions and Prerequisites`](../../docs/MOP-ND4-install.md#assumptions-and-prerequisites) — Lab OOB-MGMT in this pod's
topology, but the principle (single lab-owned L3 path from ND-MGMT to every
CIMC) is what matters. Only fall back to Path B when re-IPing is blocked by
external constraints (e.g. CIMCs cabled to a fabric you don't own). Either
way, do not start cluster bringup until the diagnosis recipe shows OK for the
mgmt GW and all 3 CIMC IPs from inside ND-1. `precheck.py` should be extended
to call this same matrix from the cluster-leader perspective once we have a
non-disruptive way to do it (today precheck runs from the workstation, which
can mask this gap if the workstation reaches the CIMC subnet via a different
path than ND-1 does).

---

## 15. Never allocate an IP without lab-owner approval

### Symptom

You (or the automation) needs an address — a new CIMC, an extra entry in the
persistent IP pool, a future ND node, a service VIP — and you assume "this looks
free in the subnet, I'll just use it." Then one of:

- the IP collides with a host the lab owner provisioned but didn't tell you about
- the IP lands in a range the lab owner has reserved for another service (DHCP
  scope, ND persistent pool extension, future leaf interface, etc.)
- the IP works today but is reclaimed next quarter, breaking ND silently

### Why

In a shared lab the **only** authoritative source for "is this IP free, and may
I have it?" is the human/team that owns the subnet. IP-address-management
inferred from `ping`/`arp` is a snapshot, not a reservation; nothing prevents
someone else from taking the same address tomorrow. We hit this twice in two
days on the same change:

1. **2026-04-25.** We picked CIMC re-IP candidates `192.0.2.107/108/109` on
   inference rather than asking. The lab owner immediately corrected us to
   `192.0.2.77/78/79` — their actual reserved range for this purpose on the
   ND-MGMT VLAN, under the (then-current) plan to co-locate CIMCs on
   ND-MGMT.
2. **2026-04-27.** When that plan was superseded by D-011 (CIMCs on Lab
   OOB-MGMT instead — see §14 Path A), the destination subnet *changed*
   entirely (`198.51.100.0/24`, not `192.0.2.0/24`). We did **not** assume
   the host-portion offsets (`.77/.78/.79`) carried over to the new subnet.
   We asked the subnet owner; they assigned `198.51.100.87/88/89`. Different
   subnet, different reservation, different allocation request.

The rule applies per-subnet, every time. Re-IPing to a new subnet is a fresh
allocation, not a port of the host-portion bits.

### Rule

When the automation or operator needs to allocate any IP:

1. **Stop.** Do not write the candidate into any tracked file yet.
2. **Surface the request to the lab/subnet owner**, with: the prefix, the count
   of IPs needed, the purpose, the proposed labels (e.g. "ND-x CIMCs"), and any
   adjacency constraints (e.g. "must be in same /27 as the existing nodes").
3. **Wait for explicit approval.** "Looks fine" / "go for it" by IP is enough;
   "I'll get back to you" is not. Don't proceed on inference.
4. **Record the approval** in CHANGELOG (entry under the change that uses the
   IPs) so a future operator can trace why those specific addresses were used
   and who owns the reservation.

### Apply to

- New node CIMCs (this is the case that bit us)
- New persistent IP pool entries (extending an existing pool counts)
- New ND nodes added to an existing cluster
- VIPs for any service ND will expose externally
- Any address range used by automation that is not already in the cluster
  bootstrap payload signed off by the lab owner

### Decision reference

See [decision D-010](../../CHANGELOG.md#d-010--never-allocate-an-ip-without-explicit-lab-owner-approval).

---

## 16. Lab network topology reference

This is the authoritative map of the lab subnets and VLANs we use for this pod.
It exists because we kept rediscovering it the hard way: VLAN IDs encode the
third octet of the tenant subnets, lab and tenant segments are in different
VRFs, and reachability between any two segments depends on which two you pick.
Keep this in sync with the lab when it changes.

### Lab management segments (lab VRF)

| Segment | Subnet | VLAN | Purpose | Reaches |
|---|---|---|---|---|
| Lab IB-MGMT | `192.0.2.0/24` | 4 | In-band mgmt; ND `bond1` (ND-MGMT) lives here | Lab OOB-MGMT |
| Lab OOB-MGMT | `198.51.100.0/24` | 10 | Out-of-band mgmt; CIMCs live here | Lab IB-MGMT |

The two lab segments route to each other through the lab firewall (capacity
~1 Gbps). The FW is pre-permitted for this traffic — no rule change needed.
Confirmed empirically on 2026-04-27 with `ping 198.51.100.124 / 198.51.100.125`
from ND-1 (rescue-user @ 192.0.2.7); see
[`automation/logs/lab-ib-oob-routing-verify-20260427T123154Z.log`](../logs/lab-ib-oob-routing-verify-20260427T123154Z.log).

### Tenant segments (tenant VRF, this pod)

This pod is one tenant; the tenant has been allocated **four** /24s in a single
tenant VRF, one per tenant VLAN. The lab convention is:

```
VLAN 1240 + N  →  198.18.N.0/24    (third octet matches the last digit of the VLAN)
```

| Subnet | VLAN | Status |
|---|---|---|
| `198.18.0.0/24` | 1240 | In use — ND `bond0` (ND-DATA) and persistent IP pool `198.18.0.20-24` |
| `198.18.1.0/24` | 1241 | Reserved — available for future apps |
| `198.18.2.0/24` | 1242 | Reserved — available for future apps |
| `198.18.3.0/24` | 1243 | Reserved — available for future apps |

All four tenant /24s share a single VRF and route to each other directly
(no FW between them). Other tenants in the lab live in their own VRFs and
cannot reach this pod's tenant segments without explicit FW rules.

### Inter-VRF reachability (lab VRF ↔ tenant VRF)

Lab segments and tenant segments are in **different VRFs**. Traffic between
them traverses the lab firewall, and changing FW policy is a multi-team
request. **This is the constraint we design around**: place anything ND-1 must
reach during cluster-commit pre-flight (CIMCs in particular) on a segment that
ND-1's mgmt interface can reach without crossing the lab/tenant VRF boundary —
i.e. on a lab segment, not a tenant segment. See the CHANGELOG decision for
CIMC placement for the current ruling.

### When this needs to change

- New tenant VLAN allocated → add a row to the tenant table; check that the
  `VLAN 1240 + N` convention still holds.
- A lab segment is moved between VRFs, or the IB↔OOB FW policy changes →
  update the lab-segments section immediately; CIMC placement may need to be
  revisited.
- Different pod with a different VLAN-to-subnet convention → fork this
  section, do not generalize this one.

---

## 17. Secondary node firmware version mismatch blocks cluster commit

### Symptom

The cluster commit (`POST /v2/bootstrap/cluster`) returns `200 OK`, the
orchestrator advances cleanly through `Initialize node` and the duplicate-IP
check, then fails ~8 minutes later at stage **"Setup boot time configuration"**:

```text
GET /api/v1/infra/cluster/status
{
  "state": "bootstrap",
  "status": {
    "overallStatus": {
      "status": "Failed",
      "statusMessage": "Software Install/Upgrade encountered an issue at stage 'Setup boot time configuration'\nBootstrapStageIdFirstBootSetup: Install stage failed on one more nodes:\n[nd-2]: Node CIMC error response: The installed firmware version is incompatible with cluster's. [Node: 4.1.1g. Cluster: 4.2.1.10]\n[nd-3]: Node CIMC error response: The installed firmware version is incompatible with cluster's. [Node: 4.1.1g. Cluster: 4.2.1.10]"
    }
  }
}
```

All three nodes show `bootstrapStatus: BootstrapFailed`. ND-1 is on the target
release (4.2.1.10) but ND-2 and ND-3 still have an older ND OS on disk
(4.1.1g in our case).

### Why

ND-1's cluster orchestrator does not push an OS image to a secondary during
cluster bringup. It SSHes to each secondary's CIMC SOL, drives the first-boot
dialog, and then queries the secondary's CIMC for its installed ND firmware
version. If that version does not exactly match the cluster leader's, the
orchestrator aborts the stage and marks the cluster commit Failed.

This trap is easy to fall into because two earlier recovery steps both
**preserve** the OS image on disk:

- `acs reboot factory-reset` (§10) clears bootstrap config only — same OS.
- A Redfish `ForceRestart` (`Actions/ComputerSystem.Reset`) just power-cycles
  — same OS.

So a secondary that was previously installed with an older ND ISO will keep
showing as 4.1.1g across any number of factory-resets and power-cycles, even
though `/bootstrap/status` and SOL appear to show it "back at the first-boot
prompt." The first-boot dialog being there does **not** imply the underlying
image matches the cluster leader.

A second easy-to-confuse symptom comes from §10: if the secondary is at any
post-first-boot screen (e.g. stuck at `Admin Password:` because someone hit
Enter on the "Press Enter to manually bootstrap…" screen), the orchestrator
reports it as "node is not in a fresh state and must be factory-reset" instead
of the firmware-mismatch message. In that case factory-reset *is* the right
fix and the firmware error has not yet been reached. We hit "fresh-state" first
on this cluster, fixed it, then immediately hit the firmware-mismatch error
on the next cluster commit attempt.

### Recovery (mandatory: re-image the mismatched secondaries)

There is no API or `acs` shortcut for this — the secondary must be **re-installed
from the same ISO that ND-1 was installed from**. This is the same Phase 1–4
work that `install_node1.py` does, but for the secondary nodes.

`scripts/install_secondaries.py` does exactly this in parallel for every node
whose `nd_node.role != bootstrap` in `inventories/lab/host_vars/nd-*.yml`:

1. **mount_and_boot** — Redfish: eject any old vMedia, insert
   `cluster.iso.url`, set one-time UEFI vDVD boot, force-restart (or power-on
   if Off).
2. **installer_skip_sent** — SOL: send `skip` at the CIMC vMedia
   "Press <Enter> to install/skip" prompt.
3. **installer_complete** — SOL: wait up to 4 hours for the installer to
   finish and power the box off.
4. **post_install_poweron** — Redfish: eject vMedia, power back on. The node
   boots into the freshly-installed ND OS and presents
   "Press Enter to manually bootstrap your first primary node" — this is the
   "fresh state" the orchestrator requires **and** it is now on the matching
   release.

It does **not** drive Phase 5 (the SOL first-boot dialog) on the secondaries:
ND-1's cluster bootstrap will SSH into each secondary's CIMC SOL and drive
that dialog itself during stage `Setup boot time configuration` (which is the
whole point of that stage). Driving it from the workstation would conflict
with ND-1 and waste the SOL session.

State is per-node (`state/node2.json`, `state/node3.json`) using the same
schema as `state/node1.json`, so the script is idempotent and resumable. To
force a re-install of a single secondary, delete its state file (or pop the
phase you want to re-drive, mirroring the §10 pattern for ND-1).

```bash
# Run from automation/ (alongside install_node1.py)
.venv/bin/python3 scripts/install_secondaries.py
```

After both secondaries finish (~3 hours, parallel), follow the standard
recovery flow on ND-1 to clear its `BootstrapFailed` state and recommit:

1. Factory-reset ND-1 (§10) — clears the Failed cluster record on the leader.
   `POST /v2/bootstrap/cluster` will otherwise still return
   `Pending cluster bootstrap exists` (§1) because the failed commit is itself
   a pending record.
2. Pop the `bootstrap` phase from `state/node1.json` and re-run
   `scripts/main.py node1` — re-drives Phase 5 only (~2 minutes).
3. Re-run `scripts/wizard_flow_retry.py --commit` — should now pass
   `Setup boot time configuration` because all three nodes are at 4.2.1.10.
4. Watch `logs/bringup-monitor/watch.py` for stage progression.

### Pre-flight check (so we never hit this again)

**Implemented as `precheck.py`'s `version.*` category** (added 2026-04-28).
The check SSHes `rescue-user` to each node's mgmt IP, runs `acs version`,
parses the release, and compares: per-node vs. the ISO release encoded in
`cluster.iso.url`, and across nodes for drift. It runs cleanly any time
all 3 nodes have a mgmt IP up; before that, it SKIPs with a pointer at
`install_secondaries.py`. Run it standalone:

```bash
.venv/bin/python scripts/precheck.py --category version
```

Why this works only post-mgmt-IP. There is no Redfish/CIMC field that reports
"what ND release is installed on the local disk"; the only first-class signal
is `acs version` (rescue-user SSH) once the OS has booted and answers on its
mgmt IP. Pre-bootstrap, the chicken-and-egg means the *operational rule*
remains the safety net: **if you re-IP, re-image, or replace a secondary CIMC,
run `install_secondaries.py` BEFORE running `wizard_flow_retry.py --commit`**,
otherwise expect this failure mode and a +3 hour recovery loop.

### Decision reference

See [decision D-012](../../CHANGELOG.md#d-012--secondary-nodes-must-be-re-imaged-when-firmware-version-differs-from-cluster-leader)
(when added).

---

## 18. Restart bootstrap retains non-secret wizard configuration on 4.3.1

### Observed behavior

During the 2026-09-23 ND 4.3.1 lab deployment, cluster bringup failed because
ND-3 was powered off. After ND-3 was powered on, the UI's **Restart bootstrap**
recovery retained the previously entered non-secret cluster, network, node,
and persistent-IP values. Passwords were not retained and had to be supplied
again.

This can shorten an operator recovery because the wizard does not have to be
re-entered from the beginning. It does not make the retained UI state a source
of truth and it does not remove the need to verify the Summary before retrying.

### Automation rule

- Prevent this failure before commit: immediately before `cisco.nd.nd_setup`,
  read each node's Redfish `PowerState` and require every node to report `On`.
- If a retry is needed, rebuild the complete request from canonical Ansible
  inventory and resolve every password from the vault. Never assume a retained
  wizard form is complete or contains credentials.
- Keep retry behavior idempotent. Do not add a second editable recovery
  payload derived from the UI.

---

## Appendix A — Useful read-only API probes

All require a JWT from `POST /login` and the `X-Nd-Csrf-Token` header.
See [`scripts/nd_api.py`](../scripts/nd_api.py).

```bash
# ND release and node state
curl -ksS https://$ND/api/v1/version | jq .
curl -ksS https://$ND/bootstrap/status | jq .

# Verify (stateless — safe to call repeatedly; do NOT call persona/cluster
# until you intend to commit)
curl -ksS -X POST https://$ND/bootstrap/verifyexternalservice  -d @verify.json
curl -ksS -X POST https://$ND/bootstrap/verifyclustersubnets   -d @verify.json
curl -ksS -X POST https://$ND/bootstrap/verifyremoteservices   -d @verify.json
```

## Appendix B — Useful read-only `acs` commands

```bash
acs health                  # cluster health summary (post-bringup)
acs version                 # ND release (NOT `acs show version`)
acs report                  # tarball of diagnostic logs
acs show certificate        # cluster certs
```
