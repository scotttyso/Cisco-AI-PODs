#!/usr/bin/env python3
"""Stage NX-OS upgrade images on switches, optionally through the Nexus Dashboard rescue-user shell.

For every switch in the YAML file the script:
  1. SSHes to the switch, either via Nexus Dashboard (rescue-user) when nexus_dashboard.host is set,
     or directly from this host when nexus_dashboard is omitted or --direct is used.
  2. Reads the model (show module), running version/image (show version) and boot variables.
  3. Works out which images in the model's upgrade path are newer than the running release.
  4. Deletes nxos*/n7000*/n7700* .bin files that are not running, not in the boot variable and not in
     the image catalog, plus all n9000-epld* files.
    5. Copies missing required images using management when mgmt0 is IP-configured, otherwise the TACACS VRF.

Passwords come from the environment:
  NEXUS_DASHBOARD_PASSWORD  rescue-user password on Nexus Dashboard (only when using Nexus Dashboard)
  NEXUS_PASSWORD            switch password
  SCP_SERVER_PASSWORD       SCP server password

Up to 16 switches run in parallel. Progress for each switch is printed to the console with a
[hostname] prefix, and the full session is logged to <log-dir>/<hostname>_<ip>.log.
"""

import argparse
import concurrent.futures
import json
import os
import re
import shlex
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pexpect
import yaml

ENV_ND = "NEXUS_DASHBOARD_PASSWORD"
ENV_SWITCH = "NEXUS_PASSWORD"
ENV_SCP = "SCP_SERVER_PASSWORD"
MAX_WORKERS = 16

HOSTKEY_RE = r"(?i)are you sure you want to continue connecting[^\n]*\?"
PASSWORD_RE = r"(?i)password:\s*"
FAIL_RE = (
    r"(?i)(permission denied[^\n]*|host key verification failed[^\n]*|bad server host key[^\n]*|"
    r"no matching \S+ (?:method|type|cipher) found[^\n]*|connection (?:refused|timed out)[^\n]*|"
    r"no route to host[^\n]*|could not resolve hostname[^\n]*|authentication failed[^\n]*)"
)
LEGACY_ERR_RE = re.compile(r"(?i)bad server host key|invalid key length|no matching \S+ (?:method|type|cipher) found")
# Older NX-OS has 1024-bit RSA host keys and SHA1 KEX that current OpenSSH crypto policies reject.
LEGACY_SSH_OPTIONS = [
    "-o", "RequiredRSASize=512",
    "-o", "HostKeyAlgorithms=+ssh-rsa",
    "-o", "KexAlgorithms=+diffie-hellman-group14-sha1,diffie-hellman-group1-sha1",
    "-o", "Ciphers=+aes128-cbc,aes256-cbc",
]
ND_GENERIC_PROMPT = r"[\$#>]\s*$"
SWITCH_GENERIC_PROMPT = r"[A-Za-z0-9][\w.\-]*# ?$"
IMAGE_FILE_RE = re.compile(r"^(?:nxos|n7000|n7700)\S*\.bin$")
STAGED_FILE_RE = re.compile(r"^(?:(?:nxos|n7000|n7700)\S*\.bin|(?:n7000|n7700)-s2-epld\S*\.img)$")
EPLD_FILE_RE = re.compile(r"^n9000-epld\S*$")
MODEL_LIKE_RE = re.compile(r"^N\d+K?-")
INVALID_RE = re.compile(r"(?i)% *invalid (command|input)|syntax error")

_print_lock = threading.Lock()


class StageError(Exception):
    pass


def version_key(version: str) -> Tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", str(version)))


def _as_list(value) -> List[str]:
    return [str(v) for v in value] if isinstance(value, list) else [str(value)]


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    for key in ("switches", "scp", "images", "upgrade_paths"):
        if key not in cfg:
            raise SystemExit(f"{path}: missing required key '{key}'")
    if not cfg["switches"].get("username") or not cfg["switches"].get("hosts"):
        raise SystemExit(f"{path}: switches.username and switches.hosts are required")
    for key in ("server", "username"):
        if not cfg["scp"].get(key):
            raise SystemExit(f"{path}: scp.{key} is required")
    cfg["nexus_dashboard"] = cfg.get("nexus_dashboard") or {}
    cfg["nexus_dashboard"].setdefault("username", "rescue-user")
    cfg["images"] = {str(k): _as_list(v) for k, v in (cfg["images"] or {}).items()}
    for entry in cfg["upgrade_paths"]:
        entry["images"] = {str(k): _as_list(v) for k, v in (entry.get("images") or {}).items()}
    return cfg


def catalog_files(cfg: dict) -> set:
    files = {f for v in cfg["images"].values() for f in v}
    for entry in cfg["upgrade_paths"]:
        files.update(f for v in entry["images"].values() for f in v)
    return files


def plan_hops(cfg: dict, model: str, current: str) -> Tuple[dict, List[str], List[str]]:
    for entry in cfg["upgrade_paths"]:
        if re.fullmatch(entry["model"], model):
            break
    else:
        patterns = ", ".join(f"'{e['model']}'" for e in cfg["upgrade_paths"])
        raise StageError(f"no upgrade_paths entry matches model '{model}' (patterns: {patterns})")
    minimum = entry.get("minimum_version")
    if minimum and version_key(current) < version_key(minimum):
        raise StageError(f"running {current} is below minimum_version {minimum} for {entry['model']}")
    hops = [str(v) for v in entry["path"] if version_key(v) > version_key(current)]
    missing = [v for v in hops if v not in entry["images"] and v not in cfg["images"]]
    if missing:
        raise StageError(f"no image file defined in 'images' for: {', '.join(missing)}")
    files = [f for h in hops for f in entry["images"].get(h) or cfg["images"][h]]
    return entry, hops, files


def parse_model(output: str) -> str:
    seen_rows = False
    for line in output.splitlines():
        if not re.match(r"^\s*\d+\s+\d+\s+", line):
            if seen_rows and line.strip().startswith("Mod"):
                break
            continue
        seen_rows = True
        # Module-Type may be truncated against the Model column, so read Model as the token before Status.
        tokens = [t for t in line.split() if t != "*"]
        if len(tokens) >= 4:
            return tokens[-2]
    raise StageError("could not parse model from 'show module'")


def parse_bootflash(output: str, pattern: re.Pattern = IMAGE_FILE_RE) -> List[str]:
    files = []
    for line in output.splitlines():
        tokens = line.split()
        if tokens and pattern.match(tokens[-1]):
            files.append(tokens[-1])
    return files


def basename(path: str) -> str:
    return re.split(r"[:/]", path)[-1]


class SwitchStager:
    def __init__(self, cfg: dict, host: str, log_dir: Path, dry_run: bool, via_nd: bool):
        self.cfg = cfg
        self.host = host
        self.log_dir = log_dir
        self.dry_run = dry_run
        self.via_nd = via_nd
        self.log_path = log_dir / f"{host}.log"
        self.log_fh = None
        self.child: Optional[pexpect.spawn] = None
        self.nd_prompt_re = ""
        self.sw_prompt_re = ""
        self.result: Dict = {"host": host, "status": "failed", "dry_run": dry_run}

    def note(self, message: str):
        line = f"### [{datetime.now():%H:%M:%S}] {message}\n"
        if self.log_fh:
            self.log_fh.write(line)
            self.log_fh.flush()
        with _print_lock:
            print(f"[{self.result.get('hostname', self.host)}] {message}", flush=True)

    def dump(self, command: str, output: str):
        name = self.result.get("hostname", self.host)
        body = "\n".join(line.rstrip() for line in output.strip("\n").splitlines())
        with _print_lock:
            print(f"----- [{name}] {command} -----\n{body}\n----- [{name}] end {command} -----", flush=True)

    def _authenticate(self, password: str, done_re: str, label: str, extra=None):
        patterns = [HOSTKEY_RE, PASSWORD_RE, FAIL_RE, pexpect.EOF, pexpect.TIMEOUT, done_re] + (extra or [])
        sent = False
        while True:
            idx = self.child.expect(patterns, timeout=self.cfg.get("login_timeout", 60))
            if idx == 0:
                self.note(f"{label}: accepting SSH host key")
                self.child.sendline("yes")
            elif idx == 1:
                if sent:
                    raise StageError(f"{label}: password rejected")
                self.child.sendline(password)
                sent = True
            elif idx == 2:
                raise StageError(f"{label}: {self.child.after.strip()}")
            elif idx == 3:
                raise StageError(f"{label}: connection closed")
            elif idx == 4:
                raise StageError(f"{label}: timed out waiting for login")
            elif idx == 5:
                return
            else:
                raise StageError(f"{label}: ssh failed, returned to Nexus Dashboard shell")

    def _capture_prompt(self, generic: str) -> str:
        self.child.sendline("")
        self.child.expect(generic, timeout=30)
        text = (self.child.before + self.child.after).replace("\r", "").strip()
        return text.split("\n")[-1].strip()

    def cmd(self, command: str, timeout: int = 120) -> str:
        self.child.sendline(command)
        self.child.expect(self.sw_prompt_re, timeout=timeout)
        lines = self.child.before.replace("\r", "").split("\n")
        if lines and command[:20] in lines[0]:
            lines = lines[1:]
        return "\n".join(lines)

    def _spawn(self, args: List[str]):
        self.child = pexpect.spawn(
            "ssh", args, encoding="utf-8", codec_errors="replace", timeout=60, dimensions=(200, 512)
        )
        self.child.logfile_read = self.log_fh

    def connect(self):
        nd = self.cfg["nexus_dashboard"]
        sw = self.cfg["switches"]
        ssh_opts = ["-o", "PreferredAuthentications=keyboard-interactive,password", "-o", "PubkeyAuthentication=no"]
        if self.via_nd:
            self.note(f"connecting to Nexus Dashboard {nd['host']} as {nd['username']}")
            self._spawn(ssh_opts + nd.get("ssh_options", []) + [f"{nd['username']}@{nd['host']}"])
            self._authenticate(os.environ[ENV_ND], ND_GENERIC_PROMPT, "Nexus Dashboard")
            nd_prompt = self._capture_prompt(ND_GENERIC_PROMPT)
            self.nd_prompt_re = re.escape(nd_prompt) + r"\s*$"

        self.note(f"connecting to switch {self.host} as {sw['username']}{'' if self.via_nd else ' (direct)'}")
        base = ssh_opts + sw.get("ssh_options", [])
        try:
            self._ssh_switch(base)
        except StageError as exc:
            if not LEGACY_ERR_RE.search(str(exc)):
                raise
            self.note(f"{exc}; retrying with legacy SSH options")
            if self.via_nd:
                self.child.expect(self.nd_prompt_re, timeout=30)
            else:
                self.child.close(force=True)
            self._ssh_switch(base + sw.get("legacy_ssh_options", LEGACY_SSH_OPTIONS))
        sw_prompt = self._capture_prompt(SWITCH_GENERIC_PROMPT)
        self.sw_prompt_re = re.escape(sw_prompt) + r"\s*$"
        self.set_hostname(sw_prompt.rstrip("# "))

    def _ssh_switch(self, options: List[str]):
        sw = self.cfg["switches"]
        label = f"switch {self.host}"
        if not self.via_nd:
            self._spawn(options + [f"{sw['username']}@{self.host}"])
            self._authenticate(os.environ[ENV_SWITCH], SWITCH_GENERIC_PROMPT, label)
            return
        inner = " ".join(shlex.quote(o) for o in options)
        self.child.sendline(f"ssh {inner} {shlex.quote(sw['username'])}@{self.host}")
        self._authenticate(os.environ[ENV_SWITCH], SWITCH_GENERIC_PROMPT, label, [self.nd_prompt_re])

    def set_hostname(self, hostname: str):
        self.result["hostname"] = hostname
        new_path = self.log_dir / f"{hostname}_{self.host}.log"
        os.replace(self.log_path, new_path)
        self.log_path = new_path
        self.result["log"] = str(new_path)

    def list_bootflash(self) -> str:
        command = self.cfg.get("bootflash_command", "show bootflash")
        output = self.cmd(command)
        if INVALID_RE.search(output):
            output = self.cmd("dir bootflash:")
        return output

    def get_vrf(self) -> str:
        management = self.cmd("show running-config interface mgmt0")
        if re.search(r"^\s*(?:ip|ipv6) address\s+\S+", management, re.M):
            self.note("mgmt0 has an IP configured, using vrf 'management'")
            return "management"
        self.note("mgmt0 has no configured IP, checking TACACS VRF")
        vrfs = re.findall(r"^\s*use-vrf\s+(\S+)", self.cmd("show running-config tacacs"), re.M)
        source = "show running-config tacacs"
        if not vrfs:
            vrfs = re.findall(r"(?i)\bvrf(?:\s+is\b)?\s*[:=]?\s+(\S+)", self.cmd("show tacacs-server groups"))
            source = "show tacacs-server groups"
        vrfs = list(dict.fromkeys(vrfs))
        if vrfs:
            if len(vrfs) > 1:
                self.note(f"multiple tacacs VRFs {vrfs}, using '{vrfs[0]}'")
            self.note(f"using vrf '{vrfs[0]}' from '{source}'")
            return vrfs[0]
        vrf = self.cfg["scp"].get("vrf", "management")
        self.note(f"no tacacs VRF found on switch, using scp.vrf '{vrf}'")
        return vrf

    def copy_image(self, filename: str, vrf: str, options: str):
        scp = self.cfg["scp"]
        path = str(scp.get("file_path", "")).strip("/")
        remote = f"{path}/{filename}" if path else filename
        command = f"copy scp://{scp['username']}@{scp['server']}/{remote} bootflash: vrf {vrf} {options}".rstrip()
        self.note(f"copying {filename}: {command}")
        self.child.sendline(command)
        sent = False
        transcript = ""
        while True:
            idx = self.child.expect(
                [HOSTKEY_RE, PASSWORD_RE, r"(?i)do you want to overwrite[^\n]*", self.sw_prompt_re, pexpect.EOF, pexpect.TIMEOUT],
                timeout=int(scp.get("timeout", 3600)),
            )
            transcript += self.child.before
            if idx == 0:
                self.child.sendline("yes")
            elif idx == 1:
                if sent:
                    self.child.sendcontrol("c")
                    self.child.expect(self.sw_prompt_re, timeout=30)
                    raise StageError(f"SCP password rejected copying {filename}")
                self.child.sendline(os.environ[ENV_SCP])
                sent = True
            elif idx == 2:
                self.child.sendline("n")
            elif idx == 3:
                break
            elif idx == 4:
                raise StageError(f"switch session closed while copying {filename}")
            else:
                raise StageError(f"timed out copying {filename}")
        if not re.search(r"(?i)copy complete", transcript):
            if options and INVALID_RE.search(transcript):
                self.note(f"switch rejected '{options}', retrying copy without it")
                return self.copy_image(filename, vrf, "")
            tail = " | ".join(line.strip() for line in transcript.strip().splitlines()[-3:])
            raise StageError(f"copy of {filename} failed: {tail} [command: {command}]")

    def delete_file(self, filename: str):
        self.note(f"deleting bootflash:{filename}")
        output = self.cmd(f"delete bootflash:{filename} no-prompt")
        if INVALID_RE.search(output):
            self.child.sendline(f"delete bootflash:{filename}")
            if self.child.expect([r"(?i)\(yes/no[^)]*\)", self.sw_prompt_re], timeout=60) == 0:
                self.child.sendline("y")
                self.child.expect(self.sw_prompt_re, timeout=120)
            output = self.child.before
        if INVALID_RE.search(output) or re.search(r"(?i)error|no such file", output):
            raise StageError(f"delete of {filename} failed: {output.strip()}")

    def stage(self):
        self.cmd("terminal length 0")
        self.cmd("terminal width 511")

        module_out = self.cmd("show module")
        try:
            model = parse_model(module_out)
        except StageError:
            self.dump("show module", module_out)
            raise
        if not MODEL_LIKE_RE.match(model):
            self.dump("show module", module_out)
        version_out = self.cmd("show version")
        ver = re.search(r"(?:NXOS|system):\s+version\s+(\S+)", version_out)
        running = [basename(p) for p in re.findall(r"(?:NXOS|system|kickstart) image file is:\s+(\S+)", version_out)]
        if not ver or not running:
            raise StageError("could not parse version/image from 'show version'")
        version = ver.group(1)
        boot_out = self.cmd("show boot")
        boot_images = {basename(p) for p in re.findall(r"(?:NXOS|system|kickstart) variable\s*=\s*(\S+)", boot_out)}
        self.result.update(model=model, version=version, running_image=", ".join(running))
        self.note(f"model {model}, running {version} ({', '.join(running)}), boot variable {sorted(boot_images) or '-'}")

        try:
            entry, hops, required = plan_hops(self.cfg, model, version)
        except StageError:
            if MODEL_LIKE_RE.match(model):
                self.dump("show module", module_out)
            raise
        self.result.update(upgrade_path=hops, required=required)
        self.note(f"matched '{entry['model']}', upgrade hops {hops or 'none (already at target)'}, images {required or '-'}")

        listing = self.list_bootflash()
        present = parse_bootflash(listing)
        staged_present = parse_bootflash(listing, STAGED_FILE_RE)
        epld = parse_bootflash(listing, EPLD_FILE_RE)
        keep = {*running, *boot_images, *catalog_files(self.cfg)}
        to_delete = [f for f in present if f not in keep] + epld
        to_copy = [f for f in required if f not in staged_present]
        self.result.update(delete=to_delete, copy=to_copy)
        self.note(f"bootflash nxos images {present or '-'}; epld images {epld or '-'}")
        self.note(f"delete {to_delete or '-'}; copy {to_copy or '-'}")

        vrf = self.get_vrf()
        self.result["vrf"] = vrf

        if self.dry_run:
            self.note("dry run, no changes made")
            self.result["status"] = "dry-run"
            return

        for filename in to_delete:
            self.delete_file(filename)

        copy_options = str(entry.get("copy_options", self.cfg["scp"].get("copy_options", "use-kstack")))
        for filename in to_copy:
            self.copy_image(filename, vrf, copy_options)

        verification_listing = self.list_bootflash()
        verified_files = parse_bootflash(verification_listing, STAGED_FILE_RE)
        missing = [f for f in required if f not in verified_files]
        if missing:
            self.dump("bootflash verification", verification_listing)
            raise StageError(f"images still missing after copy: {missing}")
        self.result["status"] = "ok"
        self.note("all required images present")

    def disconnect(self):
        if not self.child or not self.child.isalive():
            return
        try:
            if self.sw_prompt_re and self.via_nd:
                self.child.sendline("exit")
                self.child.expect([self.nd_prompt_re, pexpect.EOF, pexpect.TIMEOUT], timeout=15)
            self.child.sendline("exit")
            self.child.expect([pexpect.EOF, pexpect.TIMEOUT], timeout=15)
        finally:
            self.child.close(force=True)

    def run(self) -> Dict:
        self.log_fh = open(self.log_path, "a", encoding="utf-8")
        self.result["log"] = str(self.log_path)
        try:
            self.connect()
            self.stage()
        except (StageError, pexpect.ExceptionPexpect) as exc:
            self.result["error"] = str(exc).splitlines()[0]
            self.note(f"ERROR: {self.result['error']}")
        finally:
            try:
                self.disconnect()
            except pexpect.ExceptionPexpect:
                pass
            self.log_fh.close()
        (self.log_dir / f"{self.host}.result.json").write_text(json.dumps(self.result, indent=2))
        return self.result


def run_threads(args, cfg: dict, hosts: List[str], log_dir: Path, via_nd: bool) -> None:
    def work(host: str):
        return SwitchStager(cfg, host, log_dir, dry_run=args.dry_run, via_nd=via_nd).run()

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = []
        for host in hosts:
            print(f"[{host}] log: {log_dir / (host + '.log')} (renamed to <hostname>_{host}.log after login)", flush=True)
            futures.append(pool.submit(work, host))
            time.sleep(args.stagger)
        for future in futures:
            future.result()


def print_summary(hosts: List[str], log_dir: Path) -> int:
    failures = 0
    print("\n{:<16} {:<20} {:<18} {:<14} {:<9} {}".format("HOST", "HOSTNAME", "MODEL", "VERSION", "STATUS", "DETAIL"))
    for host in hosts:
        path = log_dir / f"{host}.result.json"
        res = json.loads(path.read_text()) if path.exists() else {"status": "failed", "error": "no result file"}
        if res["status"] == "failed":
            failures += 1
            detail = res.get("error", "")
        else:
            detail = f"vrf {res.get('vrf')}; path {res.get('upgrade_path')}; deleted {res.get('delete')}; copied {res.get('copy')}"
        print(
            "{:<16} {:<20} {:<18} {:<14} {:<9} {}".format(
                host, res.get("hostname", "-"), res.get("model", "-"), res.get("version", "-"), res["status"], detail
            )
        )
    print(f"\nLogs: {log_dir}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True, help="YAML input file")
    parser.add_argument("--only", action="append", default=[], help="limit to these switch IPs (repeatable)")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help=f"parallel sessions (1-{MAX_WORKERS})")
    parser.add_argument("--stagger", type=float, default=2.0, help="seconds between session starts")
    parser.add_argument("--log-dir", help="log directory (default: ~/LOGS/nxos_stage_logs/<timestamp>)")
    parser.add_argument("--dry-run", action="store_true", help="report the plan without deleting or copying")
    parser.add_argument("--direct", action="store_true", help="SSH to switches directly, skipping Nexus Dashboard")
    args = parser.parse_args()
    args.workers = max(1, min(MAX_WORKERS, args.workers))

    cfg = load_config(args.config)
    via_nd = bool(cfg["nexus_dashboard"].get("host")) and not args.direct
    required_env = [ENV_SWITCH, ENV_SCP] + ([ENV_ND] if via_nd else [])
    missing = [v for v in required_env if not os.environ.get(v)]
    if missing:
        raise SystemExit(f"missing environment variables: {', '.join(missing)}")
    print(f"Connecting {'via Nexus Dashboard ' + cfg['nexus_dashboard']['host'] if via_nd else 'directly'}", flush=True)

    default_dir = Path.home() / "LOGS" / "nxos_stage_logs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    log_dir = Path(args.log_dir).expanduser() if args.log_dir else default_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    hosts = [str(h) for h in cfg["switches"]["hosts"]]
    if args.only:
        hosts = [h for h in hosts if h in args.only]
    if not hosts:
        raise SystemExit("no switches selected")

    run_threads(args, cfg, hosts, log_dir, via_nd)
    return print_summary(hosts, log_dir)


if __name__ == "__main__":
    sys.exit(main())
