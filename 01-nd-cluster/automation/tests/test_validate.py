"""Regression coverage for ND 4.3 cluster-status validation."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from nd_api import cluster_nodes, node_operational_state  # noqa: E402


def test_nd43_nested_node_status_is_active():
    response = {
        "state": "active",
        "nodeDetailsList": [
            {
                "name": "EXAMPLE-ND-1",
                "status": {
                    "operationalState": "active",
                    "bootstrapStatus": "BootstrapCompleted",
                },
            },
            {"name": "EXAMPLE-ND-2", "status": {"operationalState": "active"}},
            {"name": "EXAMPLE-ND-3", "status": {"operationalState": "active"}},
        ],
    }

    nodes = cluster_nodes(response)
    assert len(nodes) == 3
    assert [node_operational_state(node) for node in nodes] == [
        "active",
        "active",
        "active",
    ]


def test_legacy_flat_node_status_remains_supported():
    assert node_operational_state({"operationalState": "ready"}) == "ready"
    assert node_operational_state({"status": "operational"}) == "operational"
