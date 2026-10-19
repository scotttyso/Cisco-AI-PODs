# Resume cheatsheet — ND-1 install

This page covers three scenarios:

- **A.** You paused mid-install on ND-1 and want to pick up where you left off.
- **B.** You factory-reset ND-1 (e.g. to clear a stuck bootstrap — see
  [`docs/troubleshooting.md`](docs/troubleshooting.md)) and want to re-drive
  only the first-boot dialog without re-installing the OS.
- **C.** Cluster commit failed at `Setup boot time configuration` because a
  secondary's installed ND release didn't match the leader's, and you need to
  re-image **ND-2/ND-3** mid-build then recover ND-1's failed-cluster record.
  See [decision D-012](../CHANGELOG.md#d-012--secondaries-must-match-cluster-leader-os-release-acs-reboot-factory-reset-preserves-the-os-image)
  and [troubleshooting §17](docs/troubleshooting.md#17-secondary-node-firmware-version-mismatch-blocks-cluster-commit).

All three scenarios use the same orchestrator and the same secrets-from-keychain
pattern. Only the state-file edit and the script invocation differ.

---

## Secrets — never inline

CIMC and ND admin passwords come from the macOS Keychain, never from shell
history or this file. Add the Keychain entries once:

```bash
# One-time setup. Replace <…> with your actual values, run once, then forget.
security add-generic-password -s "nd-lab-cimc"  -a "$USER" -w '<CIMC-PASSWORD>'
security add-generic-password -s "nd-lab-admin" -w '<ND-ADMIN-PASSWORD>'
```

Then on every shell where you run the orchestrator:

```bash
export CIMC_PASSWORD=$(security find-generic-password -s "nd-lab-cimc"  -a "$USER" -w)
export ND_ADMIN_PASSWORD=$(security find-generic-password -s "nd-lab-admin" -w)

# Confirm both are set (length only — never echo the value)
echo "CIMC=${CIMC_PASSWORD:+set/len=${#CIMC_PASSWORD}}  ADMIN=${ND_ADMIN_PASSWORD:+set/len=${#ND_ADMIN_PASSWORD}}"
```

When you're done:

```bash
unset CIMC_PASSWORD ND_ADMIN_PASSWORD
```

---

## Scenario A — resume a paused install

Typical pause point: mid-install, e.g. ISO at `~7 GiB / 11.6 GiB`. State at
that point looks like:

```
state/node1.json
  mount_and_boot       : complete
  installer_skip_sent  : complete
  installer_complete   : NOT YET   <-- this is what resume picks up
```

ND-1 is installing autonomously over CIMC vMedia ↔ apache@<iso-host>. Your
laptop is not in that data path; killing the orchestrator (SIGTERM) only
stops the SOL listener and the first-boot driver.

### Resume — three commands

```bash
cd "<repo>/cisco-aipod/01-nd-cluster/automation"

# 1. (re-)export secrets in the new shell — see "Secrets — never inline" above
export CIMC_PASSWORD=$(security find-generic-password -s "nd-lab-cimc"  -a "$USER" -w)
export ND_ADMIN_PASSWORD=$(security find-generic-password -s "nd-lab-admin" -w)

# 2. resume — idempotent; honors state/node1.json
TS=$(date -u +%Y%m%dT%H%M%SZ)
nohup .venv/bin/python -u scripts/main.py node1 \
    > "logs/node1-resume-${TS}.out" 2>&1 &
echo "pid=$!  log=logs/node1-resume-${TS}.out"

# 3. drop secrets from this shell once the background process owns them
unset CIMC_PASSWORD ND_ADMIN_PASSWORD
```

The orchestrator will:

1. Skip `mount_and_boot` and `installer_skip_sent` (state-marked complete).
2. Re-enter `wait_for_install_complete`. On reconnect, `Sol._nudge()` sends
   `\r` to repaint the current screen. The relaxed `PROMPT_INSTALL_COMPLETE`
   regex also matches first-boot indicators (`first-boot setup`,
   `Press Enter to manually bootstrap`, `Admin Password`), so:
   - if the install is still running → normal heartbeat-every-2-min wait
   - if the install finished while you were gone → returns within seconds
3. Mark `installer_complete`, then drive `bootstrap_first_primary` (admin pw
   + mgmt IP/mask + gateway) and `wait_for_bootstrap_complete`.
4. Exit cleanly when ND-1's GUI is reachable on its mgmt IP.

---

## Scenario B — re-drive only the first-boot dialog after factory-reset

You triggered `acs reboot factory-reset` (see
[`docs/troubleshooting.md` §10](docs/troubleshooting.md#10-recovery-without-os-reinstall-acs-reboot-factory-reset))
and the node has come back to the first-boot setup prompt. The OS is intact;
only the bootstrap config was wiped.

### Edit state — clear only the `bootstrap` phase

```bash
cd "<repo>/cisco-aipod/01-nd-cluster/automation"

python - <<'PY'
import json, pathlib, datetime
p = pathlib.Path("state/node1.json")
s = json.loads(p.read_text())
s.setdefault("phases", {}).pop("bootstrap", None)
s.setdefault("_history", []).append({
    "ts": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"),
    "note": "acs reboot factory-reset cleared bootstrap config; "
            "bootstrap phase removed so install_node1 re-drives only the "
            "SOL first-boot dialog",
})
p.write_text(json.dumps(s, indent=2))
print(json.dumps(s, indent=2))
PY
```

The retained phases (`mount_and_boot`, `installer_skip_sent`,
`installer_complete`, `post_install_poweron`) tell the orchestrator the OS
install is done; only the SOL first-boot dialog needs to run.

### Run

Same three commands as Scenario A. The orchestrator will skip phases 1–4
and execute only Phase 5 (`bootstrap` — drive the SOL dialog).

---

## Scenario C — mid-build secondary re-image

You ran cluster commit (`scripts/wizard_flow_retry.py --commit`), it was
accepted, and the bringup monitor (`logs/bringup-monitor/watch.py` or polling
`/api/v1/infra/cluster/status`) reported failure at stage `Setup boot time
configuration`. The underlying error string (sometimes truncated in monitor
output — read it directly via the API) reads:

```
Node CIMC error response: The installed firmware version is incompatible
with cluster's. [Node: <secondary-version>. Cluster: <leader-version>]
```

That means one or both secondaries were on a different ND release than ND-1
when commit ran. `acs reboot factory-reset` won't help — it preserves the OS
image. The fix is **re-image the stale secondary(ies), then drive the
ND-1-side recovery loop**.

### Step 1 — confirm version drift

```bash
# Reachable on mgmt? Then probe directly.
.venv/bin/python scripts/precheck.py --category version
```

Look for either `version.cluster_match: FAIL` or one or more
`version.node.<host>` rows reporting a different release than the others or
than the ISO. If the secondaries are unreachable on mgmt:22 (typical when
ND-1 cluster commit nuked their SOL dialog state), peek with:

```bash
# 12-second SOL peek per secondary; not destructive.
.venv/bin/python scripts/main.py tail-sol --node nd-2 --seconds 12
.venv/bin/python scripts/main.py tail-sol --node nd-3 --seconds 12
```

If a node is sitting at an old `localhost login:` or partial bootstrap, it
needs a re-image (or at least a factory-reset; in this scenario it's a
re-image).

### Step 2 — re-image affected secondaries (parallel)

```bash
cd "<repo>/cisco-aipod/01-nd-cluster/automation"

export CIMC_PASSWORD=$(security find-generic-password -s "nd-lab-cimc"  -a "$USER" -w)
export ND_ADMIN_PASSWORD=$(security find-generic-password -s "nd-lab-admin" -w)

TS=$(date -u +%Y%m%dT%H%M%SZ)
nohup .venv/bin/python -u scripts/install_secondaries.py \
    > "logs/secondaries-${TS}.out" 2>&1 &
echo "pid=$!  log=logs/secondaries-${TS}.out"

unset CIMC_PASSWORD ND_ADMIN_PASSWORD
```

The script runs ND-2 and ND-3 concurrently through phases 1–4 (Redfish
vMedia mount, UEFI vDVD one-time boot, SOL installer-skip, install-complete
wait, post-install power-on). It deliberately does **not** run Phase 5
(first-boot SOL dialog) — that step is owned by ND-1's cluster orchestrator
once you re-commit. Total elapsed: ~3 hours (parallel; the slow leg is
phase 3, install-complete).

Empirical timeline anchors (4.2.1.10 ISO, dual UCS C220 M5):

- T+0:00  : `install_secondaries.py` launches, both nodes begin Redfish boot
- T+0:05  : installer reaches `skip` prompt on each (4–7 min after restart)
- T+0:30  : install actively writing `/tmp/cdrom.iso`
- T+1:30  : install ~50% (`Logical Vol image1` resize)
- T+2:00  : install complete; node powers off
- T+2:01  : Phase 4 (eject vMedia + power on); node boots into fresh ND OS
- T+2:05  : SOL shows `Press <Enter> to manually bootstrap your first
            primary node` — this is the "fresh state" ND-1 needs

If the install appears to stall at >1 hour without progress in the install
log, **first** check whether the SOL session is healthy — paramiko half-open
sessions after a VPN drop look exactly like a stuck install. See
[`troubleshooting.md` §11](docs/troubleshooting.md#11-sol-peek-with-nudge-as-programmatic-state-source)
for the SOL-peek diagnostic.

### Step 3 — clear ND-1's failed-cluster record

The failed cluster commit left ND-1 in `BootstrapFailed`. Like any pending
record (see [§1](docs/troubleshooting.md#1-pending-cluster-bootstrap-exists)),
the only API-side fix is `acs reboot factory-reset` on ND-1:

```bash
ssh rescue-user@<ND-1-mgmt>
printf 'y\n' | acs reboot factory-reset
# wait ~5 min for the node to drop off ping then come back
```

Or via the orchestrator (uses paramiko `exec_command` with no TTY, which is
what actually works reliably; see
[§10](docs/troubleshooting.md#10-recovery-without-os-reinstall-acs-reboot-factory-reset)):

```bash
.venv/bin/python scripts/main.py factory-reset --node nd-1
```

### Step 4 — re-drive only Phase 5 on ND-1

Same Scenario B state-file edit (clear only the `bootstrap` phase):

```bash
python - <<'PY'
import json, pathlib, datetime
p = pathlib.Path("state/node1.json")
s = json.loads(p.read_text())
s.setdefault("phases", {}).pop("bootstrap", None)
s.setdefault("_history", []).append({
    "ts": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"),
    "note": "scenario C: cluster commit failed on version drift; re-imaged "
            "secondaries via install_secondaries.py and factory-reset ND-1; "
            "re-driving Phase 5 only",
})
p.write_text(json.dumps(s, indent=2))
PY

TS=$(date -u +%Y%m%dT%H%M%SZ)
nohup .venv/bin/python -u scripts/main.py node1 \
    > "logs/node1-resume-${TS}.out" 2>&1 &
```

### Step 5 — re-commit, monitor, verify

```bash
.venv/bin/python scripts/precheck.py --category version   # should now PASS
.venv/bin/python scripts/wizard_flow_retry.py --commit
.venv/bin/python logs/bringup-monitor/watch.py            # tail for stage progression
```

The cluster commit should now pass `Setup boot time configuration` and
proceed through all 8 K8s stages (~22 min from commit accept to active in
our lab). After active, re-run the version precheck plus the post-install
gate ([`§D` of precheck-checklist.md](docs/precheck-checklist.md#d-after-the-install--re-run-a-subset)).

### Why this scenario can't be reduced to "just run Scenario B"

Scenario B assumes only ND-1 needs work and the secondaries are already in
the correct state (fresh + correct OS release). Scenario C is the cross-cut:
secondaries also need work (re-image, not just factory-reset), AND ND-1's
failed-cluster state has to be cleared before re-commit will succeed. The
two parts are independent — you can run step 2 and step 3 concurrently —
but both must complete before step 4.

---

## How to peek without touching anything

```bash
# tail the live JSONL log
tail -f "$(ls -t logs/node1-*.jsonl | head -1)"

# see latest serial-line heartbeat in one line
tail -n 200 "$(ls -t logs/node1-*.jsonl | head -1)" \
  | grep heartbeat | tail -1 | python3 -c \
  "import json,sys; e=json.loads(sys.stdin.read()); \
   print(e['ts'], e['elapsedS'], 's ::', e['lastSerialLine'])"

# read-only SOL tail — does NOT compete with the orchestrator's session
# unless the orchestrator is in an _expect window (paramiko holds the
# channel). CIMC SOL is multi-reader-safe in 4.2.x.
.venv/bin/python scripts/tail_sol.py --host <cimc-ip> --user admin
# (Ctrl+C to detach.)
```

---

## Stale CIMC SOL session?

The orchestrator was killed via SIGTERM, which lets `Sol.__exit__` run
(`Ctrl+X q` to detach SOL, then close SSH). If for any reason a stale SOL
session lingers and your resume run sees `host SOL is already connected`,
clear it from the CIMC CLI:

```bash
ssh admin@<cimc-ip>
# at CIMC prompt:
scope sol
show detail
# if Active: yes from a different session, force-detach by closing your SSH
# (the lingering paramiko session times out after CIMC's idle timeout; or
# reload CIMC):
end
```

---

## Once Node 1 is up (mgmt IP answers HTTPS)

Before driving cluster bringup, validate the live API contract — read-only:

```bash
.venv/bin/python scripts/verify_endpoints.py \
    --host <nd-mgmt-ip> --insecure
```

Reconcile any `TODO ASSUMED` deltas in `scripts/nd_api.py`, then commit the
cluster:

```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)
nohup .venv/bin/python -u scripts/wizard_flow_retry.py --commit \
    > "logs/cluster-${TS}.out" 2>&1 &
echo "pid=$!  log=logs/cluster-${TS}.out"
```

If the commit returns `500 Pending cluster bootstrap exists`, see
[`docs/troubleshooting.md` §1](docs/troubleshooting.md#1-pending-cluster-bootstrap-exists).
