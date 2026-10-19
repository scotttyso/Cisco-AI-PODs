# Pre-validation checklist — ND 4.3.x cluster install

Run this **before** touching the lab. Every item here exists because we hit
the failure during the 4.2.1.10 lab build and don't want anyone (customer
or future-self) to hit it again. Each item links to the troubleshooting
section that explains what happens if you skip it.

The list has two halves:

- **Automation-side** (§A): a single Python script runs ~30 checks against
  your inventory and prints a colored pass/fail table. Run this every time
  before the ND Ansible playbook.
- **Switch-side** (§B): manual `show` commands on the access switch / FEX
  facing the ND data NICs. There is no general-purpose automation for this
  yet (different vendors, different management planes). Run once per fabric
  and capture the output in your change ticket.

Immediately before cluster formation, the role also performs a second,
point-of-use hardware gate while discovering serial numbers: every inventory
node's CIMC must report Redfish `PowerState=On`. A powered-off node stops the
play before `cisco.nd.nd_setup` commits cluster bringup. The gate is read-only;
it does not power on hardware implicitly.

---

## §A. Automation-side — runs `precheck.py`

```bash
cd <repo>/cisco-aipod/01-nd-cluster/automation

# Standalone run — exits 0 only if every critical check passes. The Ansible
# playbook injects vault values when it runs this same check.
.venv-aipod-inf/bin/python scripts/precheck.py

# Or as part of the orchestrator (auto-runs precheck before each phase)
.venv-aipod-inf/bin/python scripts/main.py precheck
```

Output legend:

| Status | Meaning | Blocks install? |
|---|---|---|
| `PASS` (green) | Check held | No |
| `WARN` (yellow) | Non-blocking; operator should know | No (review and proceed) |
| `FAIL` (red) | Critical; install will fail or behave wrong | **Yes** |
| `SKIP` (gray) | Skipped (dependency missing or `--skip` flag) | No |

### Checks performed

| ID | What it confirms | If it fails |
|---|---|---|
| `inventory.parse` | Canonical Ansible host/group vars merge, schema-validate, and pass cross-field checks | Fix `inventories/<site>/` YAML / add missing fields |
| `secrets.<env-var>` | Each `pass_ref` env var is set + length >= 8 | `export` from your secret manager (macOS Keychain in lab; Vault in prod) |
| `secrets.no_plaintext_in_repo` | No hardcoded `password='...'` in tracked `*.md/*.py/*.sh/*.yaml/*.json` (regression guard for the historical `RESUME.md` leak) | Move the literal into the secret manager and reference via env var |
| `network.cimc_subnet.<host>` | Each CIMC IP is on a subnet `nd_cluster_spec.network` declares | PASS on the OOB subnet (`oob_subnet`, the intended placement) or ND-MGMT. WARN on ND-DATA or on no declared subnet. Never FAIL |
| `network.cimc_tcp_443.<host>` | TCP/443 reachable from your **workstation** to each CIMC (Redfish path) | Check VPN, CIMC power, firewall, routing. **Note:** workstation→CIMC is necessary but not sufficient — see `network.nd1_to_cimc.<host>` below for the leader-vantage check that catches the D-008/D-011 commit-time path |
| `network.cimc_tcp_22.<host>` | TCP/22 reachable from your workstation to each CIMC. Cisco's [ND 4.2.x prerequisites](https://www.cisco.com/c/en/us/td/docs/dcn/nd/4x/deployment/42x/cisco-nexus-dashboard-deployment-guide-42x/m-prerequisites.html) explicitly require **both** TCP/22 + 443 | Check VPN/firewall/routing — same as 443 above. Cisco mandates both ports |
| `network.nd1_to_cimc.<host>` (post-Phase-5) | After ND-1 has its mgmt IP, SSHes `rescue-user@nd-1` and pings each secondary's CIMC over `ping -c 2 -W 2`. This is the **leader-vantage path** that cluster-commit pre-flight actually uses (ND-1 bond1 → CIMC), distinct from your workstation→CIMC path | **FAIL** — cluster commit will block at stage `Setup boot time configuration`. The workstation→CIMC checks above passing is **not** sufficient (different L3 path). Verify the route from your `mgmt_subnet` to the CIMC subnet, including any FW rules. See [decisions D-008/D-011](../../CHANGELOG.md#d-008--when-cimcs-live-on-the-data-subnet-the-lab-must-route-mgmt-vlan--data-vlan) and [troubleshooting §14 + §16](troubleshooting.md#14-cluster-commit-fails-because-mgmt-vlan-cant-route-to-cimcs-on-another-vlan) |
| `network.nd1_data_to_gw` (post-Phase-5) | After ND-1 has its mgmt IP, SSHes `rescue-user@nd-1` and pings the data gateway from bond0. Partial signal for STP Bridge Assurance Inconsistent on the data VLAN | **FAIL** — most common cause is the data-plane access port set to `port type network` instead of `port type edge` (ND VICs are end-stations and don't send BPDUs). Run the §B switch capture to confirm. See [troubleshooting §3](troubleshooting.md#3-stp-bridge-assurance-blocks-the-data-vlan). _Note:_ this is a *partial* signal — gateway might be reachable while inter-node data-plane is broken; the §B switch-side `sh spanning-tree` capture remains the authoritative check |
| `iso.sha512_set` | The vendor-published SHA-512 has been pasted (not the `TO_CONFIRM` placeholder) | Look up the digest on cisco.com and paste it into `cluster.iso.sha512` |
| `iso.url_reachable` | HTTP HEAD on the ISO URL works and the size looks sane | Fix the HTTP server or the URL |
| `iso.sha512_url` | The complete ISO served at `cluster.iso.url` hashes to the vendor-published SHA-512 | Replace the hosted image with the verified vendor download; do not image any node from mismatched bytes |
| `dns.ntp.<host>.via.<dns>` | Every DNS server in `cluster.dns.servers` resolves every NTP hostname in `cluster.ntp.servers` | Fix DNS, or replace the failing NTP entry with an IP literal — see [troubleshooting §2](troubleshooting.md#2-verifyremoteservices-fails-on-ntp-dns-resolution) |
| `topology.mgmt_in_subnet.<host>`<br/>`topology.data_in_subnet.<host>` | Each node's ND-MGMT/ND-DATA IP belongs to the declared subnet, with the matching mask | Fix `inventories/<site>/host_vars/nd-*.yml` |
| `topology.persistent_ips_count` | At least 5 persistent IPs configured | Add more |
| `topology.persistent_ip.<ip>` | Each persistent IP is in the data subnet and doesn't collide with a node IP | Pick a non-overlapping range |
| `version.iso_parse` | A release tag (e.g. `4.3.1.175`) was extracted from `cluster.iso.url` so the per-node check has a baseline | **FAIL** for `factory_preinstalled`; WARN for `iso_reimage`. Use an ISO filename that contains the selected release. |
| `version.node.<host>` | SSH `acs version` to each node's mgmt IP returns the release selected by the inventory ISO | `factory_preinstalled` requires PASS on every node. `iso_reimage` may SKIP an unreachable current-state probe because the role images every node afterward. |
| `version.cluster_match` | All three nodes positively report the inventory-selected release for `factory_preinstalled` | **FAIL** if any node cannot be verified or reports another release. For `iso_reimage`, current release drift does not replace the required all-node imaging pass. See [troubleshooting §17](troubleshooting.md#17-secondary-node-firmware-version-mismatch-blocks-cluster-commit). |
| `bootstrap.no_pending_state` (best-effort) | Heuristic for the [troubleshooting §1](troubleshooting.md#1-pending-cluster-bootstrap-exists) "Pending cluster bootstrap exists" footgun. SKIPs cleanly if ND-1 isn't reachable yet; PASSes if admin pw is unset (no draft is possible without auth) or if the cluster is fully bootstrapped | **WARN** if ND-1 admin pw is set AND the cluster reports not-bootstrapped — that state matches both (a) a legit first attempt mid-flow [no action] and (b) a retry after a previous failed cluster commit [must `acs reboot factory-reset` ND-1 before re-attempting]. The `/bootstrap/status` API cannot distinguish (a) from (b) — see the docstring on `check_bootstrap_no_pending_state` for the API limitation. If you have NOT previously run a cluster commit against this node, ignore the warning |
| `config.timezone` | Timezone is an IANA string (not the ambiguous `EST`/`PST`) | WARN; replace `EST` with `America/New_York` etc. |

### Useful flags

```bash
# Just the DNS↔NTP cross-check (the historical footgun)
.venv/bin/python scripts/precheck.py --category dns

# Just the leader-vantage path probes (post-Phase-5 sanity sweep before commit)
.venv/bin/python scripts/precheck.py --category network --category bootstrap

# Just the version uniformity check (run mid-window if a re-image was needed)
.venv/bin/python scripts/precheck.py --category version

# Skip a check that's intentionally unfit for your environment
.venv/bin/python scripts/precheck.py --skip iso.sha512_set

# Machine-readable output (CI gates, dashboards)
.venv/bin/python scripts/precheck.py --json | jq '.[] | select(.status=="FAIL")'

# Disable color (CI logs)
.venv/bin/python scripts/precheck.py --no-color
```

---

## §B. Switch-side — manual checks

The automation cannot reach the upstream switches. Run these on each access
switch (or FEX) port that faces an ND data NIC. Capture the output in your
change ticket so an auditor can see the prerequisite was met.

### B.1. Port mode and VLAN

```
sh interface eth<x>/<y> switchport
```

Expected:

- `Operational Mode: access`
- `Access Mode VLAN: <data-vlan>` (matches the ND-DATA VLAN in your design)
- `Trunking Native Mode VLAN:` not used in access mode

If the port is a trunk or on the wrong VLAN, fix it before installing.

### B.2. STP port type — must NOT be `network`

```
sh spanning-tree interface eth<x>/<y> detail
```

Expected on the relevant VLAN line:

- Port Type: **`edge`** (preferred) or `normal`
- Status: `forwarding`
- **NOT** `network` (that's the §3 footgun — `BA_Inc` will silently block data)

If you see `Port Type: network` or status `BA_Inc`, edit the interface
config:

```
interface Ethernet<x>/<y>
  spanning-tree port type edge
```

Then re-validate:

```
sh spanning-tree vlan <data-vlan> | inc Eth<x>/<y>
# expect: Eth<x>/<y>   Desg FWD ...   (no BA_Inc)
```

See [troubleshooting §3](troubleshooting.md#3-stp-bridge-assurance-blocks-the-data-vlan)
for the full background.

### B.3. CDP/LLDP neighbor — confirm the right chassis

```
sh cdp neighbor eth<x>/<y>
sh lldp neighbor eth<x>/<y>          # if CDP is disabled
```

Expected:

- The neighbor hostname / chassis ID matches the ND chassis you intend to
  cable to that port. If you find a different device, you've miscabled the
  rack.

### B.4. Spanning-tree VLAN-wide health

```
sh spanning-tree vlan <data-vlan> brief
```

Expected:

- Root bridge identity matches your design (usually a core switch, not the
  FEX or the access switch).
- No `BA_Inc`, no `BPDUGuard`, no `Bkn` (broken) ports facing ND.

### B.5. MTU consistency

ND data plane defaults to standard MTU (1500). If your fabric uses jumbo
frames, confirm consistency end-to-end. If the fabric MTU and the host MTU
disagree, large packets are silently dropped:

```
sh interface eth<x>/<y> | inc MTU
sh run interface eth<x>/<y> | inc mtu
```

### B.6. Routing for ND-MGMT and ND-DATA gateways

From the access switch / SVI host, confirm the gateway IPs configured in
`group_vars/nd_cluster.yml` (`mgmt_gateway`, `data_gateway`) are reachable:

```
ping <mgmt-gateway>
ping <data-gateway>
```

If a gateway doesn't ping, the cluster commit will succeed but the cluster
will be unable to reach DNS / NTP / Persistent IP next-hops.

### B.7. Persistent IP subnet — L2 mode requirement

ND 4.2.x in L2 persistent-IP mode requires the persistent IP pool to be on
the **same L2 broadcast domain** as the ND-DATA NICs. Confirm:

- The persistent IPs in `cluster.persistent_ips` are in the same subnet as
  every node's `data.ip` (the automation check `topology.persistent_ip.*`
  enforces this).
- That subnet is a single VLAN reachable on every ND data port — not split
  across VLANs.

If you need persistent IPs on a different subnet from the data NICs, you
have to switch to L3 persistent-IP mode (different `target` and BGP config
in the cluster bootstrap payload). That's outside the scope of this MOP.

### B.8. All 3 nodes on the same ND release before scheduling the maintenance window

This isn't a switch check, but it belongs on the same human-confirmation
checklist. Confirm with the customer (or the chassis admin who racked the
boxes) that **all three nodes will be on the same ND OS release** when
cluster commit runs. The most reliable promise is "we will image all 3 from
the same ISO via Cisco's UEFI vDVD path before the change window" — this is
exactly what `scripts/install_secondaries.py` does.

If a node was previously installed at a different release (e.g. shipped from
a refurbisher, or part of a prior pod that was decommissioned), `acs reboot
factory-reset` alone will NOT reconcile the drift — that command preserves
the OS image. Re-image is the only path. The post-bootstrap automated check
(`precheck.py --category version`) catches this once mgmt IPs are up, but
catching it before scheduling the maintenance window saves the customer a
3-hour reimage cycle inside that window.

See [troubleshooting §17](troubleshooting.md#17-secondary-node-firmware-version-mismatch-blocks-cluster-commit)
and [CHANGELOG D-012](../../CHANGELOG.md#d-012--secondaries-must-match-cluster-leader-os-release-acs-reboot-factory-reset-preserves-the-os-image)
for the full background.

---

## §C. Operator-environment checks

These don't go in either of the above (they're about the workstation
running the automation, not the lab) but they're worth a one-time
verification per workstation.

| Check | Command | Expected |
|---|---|---|
| Python version | `python3 --version` | >= 3.12 |
| venv created | `ls -d .venv` | exists |
| Required Python deps | `.venv/bin/pip check` | `No broken requirements found.` |
| `dig` available (for DNS check) | `which dig` | non-empty path; `bind-utils` / `dnsutils` installed if not |
| `ssh` available (for SOL phase) | `which ssh` | non-empty |
| macOS Keychain entries exist | `security find-generic-password -s "nd-lab-cimc" -a "$USER" -g 2>&1 \| grep "password:"` | line shown (does NOT print value to disk) |
| Workstation can reach all CIMC IPs | `nc -zv <cimc-ip> 443` for each | `succeeded` |
| Workstation can reach the ISO HTTP server | `curl -fsI <iso-url>` | `200 OK`, `Content-Length` ~ 11 GiB |
| Workstation has stable network (the SOL flow runs minutes-to-hours) | `ping -c 5 <ND-1-cimc>` | <1% loss, <50 ms |

### C.1. Don't let the workstation sleep mid-install

Procedure 3 (Phase 3 install + cluster bringup) keeps a paramiko SOL session
open against the CIMC for hours. If the workstation sleeps or the lab VPN
drops, the session goes half-open and the orchestrator can sit silently
against a dead socket without raising — observed live during the 4.2.1.10
build when the operator stepped away and returned to find ~5 hours of
"progress" that wasn't real (the lab VPN had dropped overnight). Two
mitigations, applied together:

```bash
# 1. Pin the OS awake for the lifetime of the orchestrator process
nohup .venv/bin/python -u scripts/main.py all > "logs/all-${TS}.out" 2>&1 &
PID=$!
caffeinate -dimsu -w "$PID" &        # exits when $PID exits
echo "orchestrator pid=$PID  caffeinate guarding it"
```

`caffeinate -dimsu -w <pid>` keeps display, idle, sleep, and system-sleep
suppressed only while `<pid>` lives, then exits cleanly — no manual cleanup,
no surprise battery drain after the install completes. (`-d` display, `-i`
idle, `-m` disk, `-s` system, `-u` declares user activity for the
power-management heuristic, `-w` ties lifetime to the watched pid.)

```text
2. Use a server, a stable wired link, or a VPN client configured with
   auto-reconnect. Lab VPNs that drop on Mac suspend (Cisco Secure Client,
   GlobalProtect, etc. depending on policy) WILL drop overnight. If your
   workstation can't run for 6+ hours uninterrupted, run the orchestrator
   from a jump host inside the lab instead.
```

This pairs with the agent-side
`notify-when-blocked-or-stalled`
rule, which asks the agent to flag silence as itself a signal — but the
operator-side mitigation is the cheaper preventative.

### C.2. Keep CIMC vKVM consoles open to every node throughout the install

Even when the install is being driven over SOL (manual MOP) or by the
orchestrator (`python scripts/main.py all`), pin a browser tab with the
**CIMC vKVM console open for every node you are installing or re-imaging**
and keep that browser window visible. vKVM is the authoritative visual
record of host state; SOL is a buffered serial proxy that can drop, hang,
or stall silently while still appearing connected. Three concrete failure
modes vKVM catches that SOL alone misses or delays:

1. **Installer hangs at the BIOS boot screen** because the one-time UEFI
   boot to `Cisco CIMC-Mapped vDVD` did not register (Redfish accepted the
   request but the next POST cycle came up with `BIOS Setup` instead). SOL
   shows nothing for 5-10 minutes; vKVM shows the BIOS menu in 30 s.
2. **Installer hits a kernel panic** mid-install. SOL may show truncated or
   reordered output; vKVM shows the full panic trace in real time.
3. **First-boot dialog hangs at a strict-validation prompt** (e.g., a
   bad-IP retry loop on the IP/Mask line — see [troubleshooting §13](troubleshooting.md#13-do-not-nudge-at-strictly-validating-prompts)).
   SOL output may scroll past the prompt visually if the buffer flushed
   late; vKVM always shows the live console state.

Cost: three pinned browser tabs (one per CIMC). Value: catching a stuck
install in seconds rather than the hours it takes to notice via
"orchestrator hasn't logged anything in a while". This is the visual
analogue of the SOL-side mitigation in §C.1 (`caffeinate` + stable VPN);
they reinforce each other and you want both.

For the automation orchestrator specifically: the SOL transcript is also
captured to `logs/sol/<node>.log` and the orchestrator emits structured
status JSON, so the vKVM tab is a redundancy layer — but a cheap one that
has paid for itself multiple times during the 4.2.1.10 build.

---

## §D. After the install — re-run a subset

After Procedure 3 completes, re-run a subset of these as a "still healthy?"
gate before you hand the cluster off to the next section (NDFC service
install). This is captured in `automation/scripts/validate.py`.

- Cluster status reports all 3 nodes Active
- `acs health` clean on each node
- NTP synced on each node
- Persistent IPs assigned to services as services come online
- DNS resolution still works from each node

---

## See also

- [`troubleshooting.md`](troubleshooting.md) — what to do if a check fails
  in unexpected ways, or if a check passes but the install still fails
- [`../RESUME.md`](../RESUME.md) — how to resume after a pause or recover
  via `acs reboot factory-reset`
- [`../../CHANGELOG.md`](../../CHANGELOG.md) — running list of changes
  to this section's docs and scripts (with the "why" for each)
