"""Python capabilities used by the ND 4.3.x Ansible deployment.

Phases:
  precheck  Pre-validation checklist (DNS->NTP, CIMC reachability, IP plan,
            ISO URL, secrets present, plaintext-credential leak scan, ...).
            Read-only. See scripts/precheck.py and docs/precheck-checklist.md.
  node1     ISO install + bootstrap of node 1 (Redfish + SOL)
  bootstrap Bootstrap node 1 over SOL without reinstalling its verified image
  secondary ISO install of one secondary node; cluster formation drives its
            first-boot dialog
  validate  Post-install report and assertions

The complete workflow is ``playbooks/01_nd_cluster.yml``. Cluster formation
is owned by ``cisco.nd.nd_setup`` there; this CLI intentionally has no second
cluster-formation path.

Diagnostic subcommands (read-only, no state writes):
  tail-sol  Peek at the SOL console of any node by inventory hostname.
            One-liner replacement for "ask a human to KVM in" - see
            docs/troubleshooting.md \u00a711.

State files under inventory.runtime.state_dir make every phase idempotent and
the orchestrator resumable.

By default `all` aborts if precheck reports any FAIL. Pass
`--skip-precheck-on-all` to run anyway (e.g. you've intentionally accepted
a WARN that's misclassified as FAIL in your environment).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import signal
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))                                  # for sibling modules
sys.path.insert(0, str(THIS_DIR.resolve().parents[2]))             # for shared/lib

from shared.lib.inventory import InventoryError, load_ansible  # noqa: E402
from shared.lib.logging import configure, get_logger               # noqa: E402
from shared.lib.orchestrator_telemetry import (  # noqa: E402
    RunLog,
    RunStatusHeartbeat,
    _atomic_json_write,
    capture_run_output,
    make_run_dir,
    prune_completed_runs,
    run_state_for_exit,
    write_run_status,
)

REPO_ROOT = THIS_DIR.parents[2]
DEFAULT_INVENTORY = REPO_ROOT / "inventories" / "example" / "inventory.yml"
DEFAULT_RUN_LOG_ROOT = THIS_DIR.parent / "run-logs"
TELEMETRY_SCHEMA = "nd_cluster_deploy_telemetry"


def _emit_changed(phase: str, changed: bool) -> None:
    """Print a stable, machine-readable change marker to stdout.

    The Ansible wedge (roles/nd_cluster/tasks/{image_node,form_cluster}.yml)
    keys ``changed_when`` on ``'changed=true' in <result>.stdout``. Phases that
    performed real work print ``changed=true``; a fully idempotent re-run (all
    steps state-skipped) or a dry run prints ``changed=false`` so Ansible can
    report ``ok`` vs ``changed`` honestly.
    """
    marker = "true" if changed else "false"
    print(f"changed={marker}")
    get_logger("main").info(
        "phase change marker",
        extra={"event": "phase.changed", "phase": phase, "changed": changed},
    )


def _run_precheck(args) -> int:
    """Invoke precheck and translate exit codes for the orchestrator."""
    import precheck

    sub_argv = ["--ansible-inventory", args.ansible_inventory]
    sub_argv.append("--json")
    if args.iso_file:
        sub_argv += ["--iso-file", args.iso_file]
    for check_id in args.skip:
        sub_argv += ["--skip", check_id]
    return precheck.main(sub_argv)


def _badge(state: str) -> dict[str, str]:
    return {
        "PASS": {"label": "Passed", "variant": "success"},
        "WARN": {"label": "Warning", "variant": "warning"},
        "FAIL": {"label": "Failed", "variant": "danger"},
        "SKIP": {"label": "Skipped", "variant": "secondary"},
        "running": {"label": "In progress", "variant": "info"},
        "succeeded": {"label": "Complete", "variant": "success"},
        "failed": {"label": "Needs attention", "variant": "danger"},
    }.get(state, {"label": state.replace("_", " ").title(), "variant": "info"})


def build_telemetry(phase: str, exit_code: int, run_log: RunLog, *,
                    stdout: str = "", node: str | None = None,
                    cluster_state: str | None = None, node_states=None,
                    offline: bool = False, run_dir=None) -> dict:
    checks = []
    try:
        parsed = json.loads(stdout)
    except (TypeError, ValueError):
        parsed = None
    if isinstance(parsed, list) and all(isinstance(row, dict) for row in parsed):
        for row in parsed:
            status = str(row.get("status", "UNKNOWN")).upper()
            checks.append({"kind": "verification", "name": str(row.get("id", "check")),
                           "state": status.lower(), "detail": str(row.get("detail", "")),
                           "badge": _badge(status)})
    parsed_cluster = parsed if isinstance(parsed, dict) else {}
    cluster_state = cluster_state or parsed_cluster.get("cluster_state")
    node_states = node_states or [
        (row.get("name", "node"), row.get("state", "unknown"))
        for row in parsed_cluster.get("nodes", []) if isinstance(row, dict)
    ]
    if node_states:
        checks.append({
            "kind": "phase", "name": phase,
            "state": "succeeded" if exit_code == 0 else "failed",
            "detail": ("Sanitized offline deployment example."
                       if offline else f"Subsystem 01 {phase} phase exit code {exit_code}."),
            "badge": _badge("succeeded" if exit_code == 0 else "failed"),
        })
    if node_states:
        for name, state in node_states:
            normalized = str(state).lower()
            healthy = normalized in {"active", "ready", "operational"}
            passed_node = healthy or normalized == "phase completed"
            node_badge = "PASS" if passed_node else ("UNKNOWN" if normalized == "not queried" else "FAIL")
            checks.append({"kind": "node", "name": name, "state": str(state),
                           "detail": ("Synthetic node state for offline example; no ND query performed."
                                      if offline else
                                      "Node operational state from ND validation."
                                      if normalized in {"active", "ready", "operational"}
                                      else "Node-specific phase result; health is not inferred."),
                           "badge": _badge(node_badge)})
    if not checks:
        checks.append({
            "kind": "phase", "name": phase,
            "state": "succeeded" if exit_code == 0 else "failed",
            "detail": ("Sanitized offline example; no credentials or network access."
                      if offline else f"Subsystem 01 {phase} phase exit code {exit_code}."),
            "badge": _badge("succeeded" if exit_code == 0 else "failed"),
        })
    passed = sum(item["badge"]["variant"] == "success" for item in checks)
    failed = sum(item["badge"]["variant"] == "danger" for item in checks)
    decision = "offline_example" if offline else ("completed" if exit_code == 0 else "failed")
    badge = _badge("succeeded" if exit_code == 0 else "failed")
    if offline:
        badge = {"label": "Offline example", "variant": "info"}
    payload = {
        "schema_version": "1.0", "telemetry_type": TELEMETRY_SCHEMA,
        "phase": "offline_plan" if offline else phase,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "decision": decision, "badge": badge,
            "reason": ("Sanitized example generated without inventory, credentials, or ND access."
                       if offline else f"Subsystem 01 {phase} phase finished with exit code {exit_code}."),
            "phases_total": 1, "phases_succeeded": int(exit_code == 0),
            "checks_total": len(checks), "checks_passed": passed, "checks_failed": failed,
            "cluster_state": cluster_state,
            "nodes_total": len(node_states or []),
            "nodes_healthy": sum(str(state).lower() in {"active", "ready", "operational"}
                                 for _, state in (node_states or [])),
        },
        "checks_table": checks,
        "console_drawer": {
            "title": "Raw Orchestrator Logs", "total_lines": len(run_log.lines[-500:]),
            "lines": run_log.lines[-500:], "collapsible": True,
            "default_expanded": False,
        },
    }
    if run_dir:
        payload["artifacts"] = {
            "run_id": Path(run_dir).name, "run_dir": str(run_dir),
            "raw_log": str(Path(run_dir) / "raw.log"),
            "telemetry_file": str(Path(run_dir) / "telemetry.json"),
            "status_file": str(Path(run_dir) / "status.json"),
        }
    return payload


def _find_node(inv, hostname: str):
    """Resolve an inventory hostname case-insensitively."""
    target_key = hostname.strip().casefold()
    for node in inv.nodes:
        if node.hostname.casefold() == target_key:
            return node
    raise InventoryError(f"node not in inventory: {hostname}")


def _run_tail_sol(args, inv) -> int:
    """Resolve --node to a CIMC IP via inventory and call tail_sol.main.

    Read-only diagnostic. Does NOT write state. Sources $CIMC_PASSWORD from
    the environment (Keychain-backed in our docs).
    """
    import tail_sol

    log = get_logger("main.tail_sol")
    target_hostname = args.node.strip()
    try:
        match = _find_node(inv, target_hostname)
    except InventoryError:
        log.error("node not in inventory",
                  extra={"event": "tail-sol.node-missing", "node": target_hostname})
        return 2
    cimc_ip = match.cimc.ip
    cimc_user = match.cimc.user
    if not cimc_ip:
        log.error("node has no CIMC ip in inventory",
                  extra={"event": "tail-sol.cimc-missing", "node": target_hostname})
        return 2
    log.info("tail-sol begin",
             extra={"event": "tail-sol.begin", "node": target_hostname,
                    "cimc": cimc_ip, "seconds": args.seconds, "nudge": args.nudge})
    sub_argv = [
        "--cimc", cimc_ip,
        "--user", cimc_user,
        "--seconds", str(args.seconds),
    ]
    if args.out:
        sub_argv += ["--out", args.out]
    sub_argv += ["--nudge"] if args.nudge else ["--no-nudge"]
    return tail_sol.main(sub_argv)


def _dispatch(args) -> int:
    # Keep offline telemetry generation independent of automation-only packages.
    import install_node1
    import install_secondaries
    import validate as validator

    run_id = configure(level=args.log_level)
    log = get_logger("main")
    log.info("start", extra={"event": "run.start", "phase": args.phase, "runId": run_id})

    if args.phase == "precheck":
        return _run_precheck(args)

    try:
        inv = load_ansible(args.ansible_inventory)
    except InventoryError as e:
        log.error("inventory error", extra={"event": "inventory.error", "err": str(e)})
        return 2

    if args.phase == "tail-sol":
        if not args.node:
            log.error("tail-sol requires --node", extra={"event": "tail-sol.missing-arg"})
            return 2
        return _run_tail_sol(args, inv)

    ph = args.phase
    log.info("phase begin", extra={"event": "phase.begin", "phase": ph})
    try:
        if ph == "node1":
            changed = install_node1.run(inv, dry_run=args.dry_run)
            _emit_changed(ph, changed)
            print(json.dumps({"nodes": [{"name": inv.bootstrap_node.hostname,
                                          "state": "phase completed"}]}))
        elif ph == "bootstrap":
            changed = install_node1.bootstrap_only(inv, dry_run=args.dry_run)
            _emit_changed(ph, changed)
            print(json.dumps({"nodes": [{"name": inv.bootstrap_node.hostname,
                                          "state": "phase completed"}]}))
        elif ph == "secondary":
            if not args.node:
                raise InventoryError("secondary requires --node")
            node = _find_node(inv, args.node)
            changed = install_secondaries.run_one(inv, node)
            _emit_changed(ph, changed)
            print(json.dumps({"nodes": [{"name": node.hostname,
                                          "state": "phase completed"}]}))
        elif ph == "validate":
            validation = validator.run(inv, dry_run=args.dry_run)
            if isinstance(validation, dict):
                print(json.dumps(validation))
                return 0 if validation.get("healthy", True) else 1
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        import traceback
        tb = traceback.format_exc()
        log.error("phase failed", extra={"event": "phase.fail", "phase": ph,
                                         "errType": type(e).__name__, "err": str(e)})
        print(tb, file=sys.stderr)
        return 2
    log.info("phase end", extra={"event": "phase.end", "phase": ph})
    log.info("done", extra={"event": "run.done"})
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Cisco AI POD - Subsystem 01 ND install orchestrator")
    p.add_argument("phase",
                   choices=("precheck", "node1", "bootstrap", "secondary", "validate", "tail-sol"))
    p.add_argument("--ansible-inventory", default=str(DEFAULT_INVENTORY),
                   help="canonical Ansible inventory (default: example inventory.yml)")
    p.add_argument("--iso-file", default=None,
                   help="local ISO to hash during precheck and compare with the "
                        "inventory SHA-512")
    p.add_argument("--skip", action="append", default=[],
                   help="precheck id to skip; may be repeated and applies only "
                        "to the precheck phase")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--log-level", default="INFO")
    # Node-specific phases: secondary imaging and tail-sol diagnostics.
    p.add_argument("--node", default=None,
                   help="ND hostname for secondary or tail-sol (case-insensitive)")
    p.add_argument("--seconds", type=int, default=12,
                   help="(tail-sol) drain window in seconds (default: 12)")
    p.add_argument("--out", default=None,
                   help="(tail-sol) optional file to also write the captured stream to")
    nudge_grp = p.add_mutually_exclusive_group()
    nudge_grp.add_argument("--nudge", dest="nudge", action="store_true", default=True,
                           help="(tail-sol) send one CR after attach (default).")
    nudge_grp.add_argument("--no-nudge", dest="nudge", action="store_false",
                           help="(tail-sol) do NOT send a CR; safer at strictly-validating "
                                "prompts. See docs/troubleshooting.md \u00a713.")
    p.add_argument("--telemetry-only", action="store_true",
                   help="Print sanitized offline telemetry; no inventory, credentials, or network")
    p.add_argument("--run-log-root", type=Path, default=DEFAULT_RUN_LOG_ROOT)
    p.add_argument("--no-run-logs", action="store_true")
    args = p.parse_args(argv)
    if args.telemetry_only:
        with RunLog() as log:
            print(json.dumps(build_telemetry(
                "offline_plan", 0, log, cluster_state="active",
                node_states=[("nd-node-1", "active"), ("nd-node-2", "active")],
                offline=True,
            ),
                              indent=2, sort_keys=True))
        return 0

    action = f"{args.phase}-{args.node}" if args.node and args.phase in {"secondary", "tail-sol"} else args.phase
    host = args.node or "nd-cluster"
    run_dir = None if args.no_run_logs else make_run_dir(args.run_log_root, host, action)
    started_utc = datetime.now(timezone.utc).isoformat()
    run_log = RunLog(run_dir=run_dir)
    heartbeat = RunStatusHeartbeat(run_dir, started_utc, scrubber=run_log)
    write_run_status(run_dir, "running", started_utc=started_utc, scrubber=run_log)
    heartbeat.start()
    result = {"exit_code": 2, "raised": False, "error": None}
    previous_handlers = {}

    def on_signal(signum, _frame):
        raise SystemExit(128 + signum)

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, on_signal)
        run_log(f"Starting ND cluster {args.phase} run")
        # Secret references are targeted from the supported ND environment.
        for ref in ("ND_ADMIN_PASSWORD", "ND1_CIMC_PASSWORD", "ND2_CIMC_PASSWORD",
                    "ND3_CIMC_PASSWORD", "CIMC_PASSWORD"):
            run_log.add_secret(os.environ.get(ref))
        with capture_run_output(run_log) as (stdout_stream, stderr_stream):
            try:
                result["exit_code"] = _dispatch(args)
            except SystemExit as exc:
                result["exit_code"] = int(exc.code or 0)
                result["raised"] = result["exit_code"] != 0
                result["error"] = f"phase exited with code {result['exit_code']}" if result["raised"] else None
            except Exception as exc:  # operational errors become exit 2
                result["exit_code"] = 2
                result["raised"] = True
                result["error"] = f"{type(exc).__name__}: {exc}"
                run_log(result["error"])
            stdout = stdout_stream.getvalue()
            stderr = stderr_stream.getvalue()
        safe_stdout = run_log.scrub(stdout)
        safe_stderr = run_log.scrub(stderr)
        if safe_stdout:
            displayed_stdout = safe_stdout
            if args.phase == "precheck":
                try:
                    import precheck
                    rows = json.loads(stdout)
                    displayed_stdout = precheck.render_text(
                        [precheck.Result(**row) for row in rows], use_color=False
                    )
                except (ImportError, TypeError, ValueError):
                    pass
            print(displayed_stdout, end="")
        if safe_stderr:
            print(safe_stderr, end="", file=sys.stderr)
        telemetry = build_telemetry(args.phase, result["exit_code"], run_log,
                                    stdout=stdout, node=args.node, run_dir=run_dir)
        if run_dir:
            _atomic_json_write(run_dir / "telemetry.json", telemetry)
    finally:
        heartbeat.stop()
        write_run_status(run_dir, run_state_for_exit(result["exit_code"], result["raised"]),
                         exit_code=result["exit_code"], error=result["error"],
                         started_utc=started_utc, scrubber=run_log)
        run_log.close()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        if not args.no_run_logs:
            prune_completed_runs(args.run_log_root, host)
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
