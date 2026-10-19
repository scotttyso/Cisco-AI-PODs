"""Phase: post-install validation + Markdown report.

Hits node 1 ND API (read-only) and writes a report under runbook/.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.lib.inventory import Inventory  # noqa: E402
from shared.lib.logging import get_logger  # noqa: E402
from shared.lib.secrets import resolve  # noqa: E402

from nd_api import NdApi, cluster_nodes, node_operational_state  # noqa: E402

log = get_logger(__name__)


def run(inv: Inventory, *, dry_run: bool = False) -> None:
    nd1 = inv.bootstrap_node
    verify = inv.runtime.ca_bundle if inv.runtime.ca_bundle else inv.runtime.verify_tls

    if dry_run:
        print(f"DRY RUN: would query https://{nd1.mgmt.ip}/ for cluster + system status")
        return {"cluster_state": "not queried", "healthy": True,
                "nodes": [{"name": node.hostname, "state": "not queried"}
                          for node in inv.nodes]}

    admin_pass = resolve(inv.admin_pass_ref)
    nd = NdApi(
        nd1.mgmt.ip,
        admin_pass,
        username=inv.admin_username,
        verify=verify,
    )
    nd.login()
    try:
        cluster = nd.wait_for_cluster_active(
            expected_nodes=len(inv.nodes),
            timeout_s=inv.runtime.cluster_bringup_timeout_s,
            poll_s=30,
        )
    finally:
        nd.logout()

    nodes = cluster_nodes(cluster)
    state = cluster.get("state") or cluster.get("status") or "Unknown"
    nodes_active = sum(
        1 for node in nodes
        if node_operational_state(node).lower()
        in {"active", "ready", "operational"}
    )
    inventory_mgmt = {node.hostname.lower(): node.mgmt.ip for node in inv.nodes}

    report_path = Path(__file__).resolve().parents[2] / "manual" / "post-install-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append(f"# Post-install report - {inv.cluster.name}")
    lines.append("")
    lines.append(f"Generated: {datetime.now(tz=timezone.utc).isoformat()}")
    lines.append("")
    lines.append("## Cluster")
    lines.append("")
    lines.append(f"- State: **{state}**")
    lines.append(f"- Nodes active: **{nodes_active} / {len(nodes) or 3}**")
    lines.append("")
    lines.append("## Nodes")
    lines.append("")
    lines.append("| Hostname | State | Mgmt IP |")
    lines.append("|---|---|---|")
    if nodes:
        for n in nodes:
            hostname = str(
                n.get("name") or n.get("hostname") or n.get("hostName") or "?"
            )
            mgmt_ip = (
                n.get("mgmtIp")
                or n.get("managementIp")
                or inventory_mgmt.get(hostname.lower())
                or "?"
            )
            lines.append(
                f"| {hostname} | {node_operational_state(n)} | {mgmt_ip} |"
            )
    else:
        for n in inv.nodes:
            lines.append(f"| {n.hostname} | (not reported) | {n.mgmt.ip} |")
    lines.append("")
    lines.append("## Persistent IPs (configured)")
    lines.append("")
    for ip in inv.cluster.persistent_ips:
        lines.append(f"- {ip}")
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("validation report written",
             extra={"event": "validate.report", "path": str(report_path),
                    "state": state, "nodesActive": nodes_active})

    healthy = (str(state).lower() in {"active", "ready", "operational"}
               and nodes_active >= len(inv.nodes))
    node_rows = []
    if nodes:
        for item in nodes:
            name = str(item.get("name") or item.get("hostname") or item.get("hostName") or "?")
            node_rows.append({"name": name, "state": node_operational_state(item)})
    else:
        node_rows = [{"name": node.hostname, "state": "not reported"} for node in inv.nodes]
    return {"cluster_state": str(state), "healthy": healthy, "nodes": node_rows}
