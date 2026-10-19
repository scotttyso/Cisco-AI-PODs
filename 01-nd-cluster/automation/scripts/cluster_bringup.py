"""Phase: cluster bring-up via Node 1 ND REST API.

Sequence (per ND 4.2.x docs + DevNet OpenAPI):

  1. Wait for nd-1 mgmt IP to answer HTTPS.
  2. Login (cookie auth, AuthCookie).
  3. GET /api/v1/infra/cluster/status — log current state for the run record.
  4. Push cluster spec (DNS / NTP / proxy / timezone) via Platform v1
     PUT /nexus/infra/api/platform/v1/clusters/{specName}.
     (First-boot SOL only sets admin password + mgmt IP/gw on Node 1.)
  5. POST persistent IP pool via Platform v1 /externalips.
  6. For each secondary node (nd-2, then nd-3):
       a. If already present and active in /cluster/nodes -> skip (idempotent).
       b. Else POST /api/v1/infra/cluster/nodes (one node per call).
       c. Poll /cluster/nodes?nodeName=... until operationalState == active.
  7. Final wait for cluster_status.state == active with N >= 3 active nodes.
  8. Logout.

Each step is gated by a state marker so a re-run resumes from where the
previous run stopped (no duplicate POSTs, no duplicate pool creation).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.lib.inventory import Inventory  # noqa: E402
from shared.lib.logging import get_logger  # noqa: E402
from shared.lib.secrets import resolve  # noqa: E402
from shared.lib.state import is_complete, mark  # noqa: E402

from nd_api import (  # noqa: E402
    ClusterSpec,
    NdApi,
    NdApiError,
    NodePayload,
    build_node_payload,
    build_platform_cluster_patch,
)

log = get_logger(__name__)

STATE_NAME = "cluster"

# All inventory nodes currently use type=Primary in the GUI sense; per the
# 4.2.x deployment guide the first three nodes of an HA cluster are Primary.
# The API enum is lower-case. If a future inventory adds standby, map here.
_TYPE_TO_API_ROLE = {
    "primary": "primary",
    "secondary": "secondary",
    "standby": "standby",
}


def _api_role(node_type: str) -> str:
    role = _TYPE_TO_API_ROLE.get(node_type.lower())
    if role is None:
        raise ValueError(
            f"unsupported node type {node_type!r}; "
            f"expected one of {sorted(_TYPE_TO_API_ROLE)}"
        )
    return role


def _node_payload(inv_node, *, cimc_pass: str | None) -> NodePayload:
    return NodePayload(
        hostname=inv_node.hostname,
        role=_api_role(inv_node.type),
        cimc_ip=inv_node.cimc.ip,
        cimc_user=inv_node.cimc.user,
        cimc_pass=cimc_pass,
        mgmt_ip=inv_node.mgmt.ip,
        mgmt_mask=inv_node.mgmt.mask,
        mgmt_gw=inv_node.mgmt.gateway,
        data_ip=inv_node.data.ip,
        data_mask=inv_node.data.mask,
        data_gw=inv_node.data.gateway,
        data_vlan=inv_node.data.vlan,
    )


def _cluster_spec(inv: Inventory) -> ClusterSpec:
    return ClusterSpec(
        name=inv.cluster.name,
        timezone=inv.cluster.timezone,
        dns_servers=list(inv.cluster.dns.servers),
        dns_search=list(inv.cluster.dns.search_domains),
        ntp_servers=[s.host for s in inv.cluster.ntp],
        proxy_skip=inv.cluster.proxy.skip,
        proxy_url=inv.cluster.proxy.url,
        proxy_ignore_hosts=list(inv.cluster.proxy.ignore_hosts),
    )


def _scrub(obj):
    """Replace any password-like values with a placeholder for safe printing."""
    if isinstance(obj, dict):
        return {
            k: ("***REDACTED***"
                if str(k).lower() in {"password", "passwd", "pass", "secret", "token"}
                else _scrub(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj


def run(inv: Inventory, *, dry_run: bool = False) -> bool:
    """Bring up the 3-node cluster via the nd-1 REST API.

    Returns True if any mutating step actually executed, False if every step
    was skipped via its state marker (fully idempotent no-op) or this was a
    dry run. Surfaced by the orchestrator as a ``changed=`` marker so the
    Ansible wedge reports ``changed`` honestly (see main.py / form_cluster.yml).
    """
    state_dir = inv.runtime.state_dir
    nd1 = inv.bootstrap_node
    secondaries = inv.secondary_nodes
    verify = inv.runtime.ca_bundle if inv.runtime.ca_bundle else inv.runtime.verify_tls
    spec_name = inv.cluster.name  # TODO ASSUMED: cluster spec name == cluster name

    log.info(
        "cluster bringup begin",
        extra={
            "event": "cluster.begin",
            "ndHost": nd1.mgmt.ip,
            "secondaryCount": len(secondaries),
            "dryRun": dry_run,
            "specName": spec_name,
        },
    )

    if dry_run:
        cfg = _cluster_spec(inv)
        print("DRY RUN: would talk to nd-1 at", nd1.mgmt.ip)
        print(f"  Cluster spec name        : {spec_name}")
        print(f"  Timezone                 : {cfg.timezone}")
        print(f"  DNS servers              : {cfg.dns_servers}")
        print(f"  NTP servers              : {cfg.ntp_servers}")
        print(f"  Proxy skip               : {cfg.proxy_skip}")
        print(f"  Persistent IP pool ('data-persistent-pool'):")
        for ip in inv.cluster.persistent_ips:
            print(f"    - {ip}")
        for n in secondaries:
            payload = build_node_payload(_node_payload(n, cimc_pass="<RESOLVED-AT-RUN>"))
            import json
            print(f"\n  Would POST createNode for {n.hostname}:")
            print(json.dumps(_scrub(payload), indent=2, sort_keys=True))
        return False

    admin_pass = resolve(inv.admin_pass_ref)
    nd = NdApi(
        nd1.mgmt.ip,
        admin_pass,
        username=inv.admin_username,
        verify=verify,
    )

    # ----- 1. wait for nd-1 reachable + 2. login ------------------------------
    nd.wait_for_reachable(timeout_s=1800, poll_s=15)
    nd.login()

    try:
        changed = _run_authed(nd, inv, secondaries, spec_name, state_dir)
    finally:
        nd.logout()

    log.info("cluster bringup done", extra={"event": "cluster.done", "changed": changed})
    return changed


def _run_authed(
    nd: NdApi,
    inv: Inventory,
    secondaries: list,
    spec_name: str,
    state_dir: str,
) -> bool:
    """Run the authenticated bring-up steps. Returns True if any mutating step
    executed (cluster spec, IP pool, or node add), False if all were skipped."""
    changed = False

    # ----- 3. snapshot cluster status (informational) -------------------------
    if not is_complete(state_dir, STATE_NAME, "status_snapshot"):
        try:
            cs = nd.cluster_status()
            log.info(
                "nd cluster status snapshot",
                extra={
                    "event": "nd.cluster.status",
                    "state": cs.get("state"),
                    "nodesPresent": len(
                        cs.get("nodeDetailsList") or cs.get("nodes") or []
                    ),
                },
            )
        except NdApiError as e:
            log.warning(
                "cluster status snapshot failed (non-fatal)",
                extra={"event": "nd.cluster.status.err", "err": str(e)},
            )
        mark(state_dir, STATE_NAME, "status_snapshot", status="recorded")

    # ----- 4. cluster spec (DNS / NTP / proxy / timezone) ---------------------
    if not is_complete(state_dir, STATE_NAME, "cluster_spec"):
        cfg = _cluster_spec(inv)
        try:
            current = nd.platform_get_cluster(spec_name)
        except NdApiError as e:
            # If the spec name doesn't match, log a clear hint -- this is the
            # most likely misalignment between docs and live system.
            log.error(
                "platform GET /clusters/{spec_name} failed",
                extra={
                    "event": "nd.platform.cluster.get.err",
                    "specName": spec_name,
                    "err": str(e),
                    "hint": (
                        "Run scripts/verify_endpoints.py to discover the live "
                        "cluster spec name; common candidates are the cluster "
                        "name (lowercased) or 'default'."
                    ),
                },
            )
            raise
        body = build_platform_cluster_patch(current_spec=current, cfg=cfg)
        nd.platform_put_cluster(spec_name, body)
        mark(
            state_dir,
            STATE_NAME,
            "cluster_spec",
            status="applied",
            dns=cfg.dns_servers,
            ntp=cfg.ntp_servers,
            timezone=cfg.timezone,
        )
        changed = True
    else:
        log.info("skip cluster_spec (state)", extra={"event": "phase.skip"})

    # ----- 5. persistent IP pool ----------------------------------------------
    if not is_complete(state_dir, STATE_NAME, "persistent_ips"):
        try:
            nd.platform_create_external_ip_pool(
                name="data-persistent-pool",
                ips=list(inv.cluster.persistent_ips),
                target_network="Data",
            )
            mark(
                state_dir,
                STATE_NAME,
                "persistent_ips",
                status="created",
                count=len(inv.cluster.persistent_ips),
            )
            changed = True
        except NdApiError as e:
            # Pool may already exist from a partial prior run; log and proceed.
            # TODO ASSUMED: ND returns 409/400 with a recognizable "already exists"
            # message; until verified, we re-raise on hard failures and only
            # downgrade specifically on 409.
            if " 409 " in str(e) or "already exists" in str(e).lower():
                log.warning(
                    "persistent IP pool already exists; proceeding",
                    extra={"event": "nd.externalip.exists", "err": str(e)},
                )
                mark(state_dir, STATE_NAME, "persistent_ips", status="exists")
            else:
                raise
    else:
        log.info("skip persistent_ips (state)", extra={"event": "phase.skip"})

    # ----- 6. add secondary nodes (one per call) ------------------------------
    for sec in secondaries:
        sub = f"node_{sec.hostname}"
        if is_complete(state_dir, STATE_NAME, sub):
            log.info(
                f"skip {sub} (state)",
                extra={"event": "phase.skip", "newNodeName": sec.hostname},
            )
            continue

        existing = nd.get_node(sec.hostname)
        if existing and str(existing.get("operationalState") or "").lower() in {
            "active", "ready", "operational",
        }:
            log.info(
                "node already active in cluster; skipping createNode",
                extra={
                    "event": "nd.node.skip.exists",
                    "newNodeName": sec.hostname,
                    "operationalState": existing.get("operationalState"),
                },
            )
            mark(state_dir, STATE_NAME, sub, status="exists",
                 operationalState=existing.get("operationalState"))
            continue

        cimc_pass = resolve(sec.cimc.pass_ref)
        payload = build_node_payload(_node_payload(sec, cimc_pass=cimc_pass))
        nd.create_node(payload)
        # The image-staging + bring-up of a secondary takes a long time
        # (CIMC vMedia transfer of the same ~12 GiB ISO). Empirical estimate
        # from Node 1 install: ~3 hours per node. Allow 5 hours for safety.
        # TODO ASSUMED: confirm wall time on lab and tighten.
        final = nd.wait_for_node_active(
            sec.hostname, timeout_s=18000, poll_s=60,
        )
        mark(
            state_dir,
            STATE_NAME,
            sub,
            status="active",
            operationalState=final.get("operationalState"),
            serial=final.get("serialNumber"),
            uuid=final.get("uuid"),
        )
        changed = True

    # ----- 7. final cluster wait ----------------------------------------------
    if not is_complete(state_dir, STATE_NAME, "active"):
        last = nd.wait_for_cluster_active(
            expected_nodes=len(inv.nodes),
            timeout_s=inv.runtime.cluster_bringup_timeout_s,
            poll_s=30,
        )
        mark(
            state_dir,
            STATE_NAME,
            "active",
            state=last.get("state"),
            nodesActive=len(last.get("nodeDetailsList") or last.get("nodes") or []),
        )
    else:
        log.info("skip active wait (state)", extra={"event": "phase.skip"})

    return changed
