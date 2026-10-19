from __future__ import annotations

from copy import deepcopy

from shared.lib.nd_parity import compare_nd_baselines


def _baseline(kind: str) -> dict:
    expected = {
        "cluster": {
            "name": "Example-ND-Cluster",
            "ntp_servers": [
                {"host": "192.0.2.10", "preferred": True},
                {"host": "192.0.2.11", "preferred": False},
            ],
        },
        "nodes": [
            {
                "hostname": "EXAMPLE-ND-1",
                "role": "primary",
                "cimc_ip": "192.0.2.20",
            }
        ],
    }
    return {
        "baseline_kind": kind,
        "software_version": "4.3.1",
        "setup_state": "Completed",
        "runtime_state": "active",
        "api_unverifiable_fields": ["cluster.ntp_servers[].preferred"],
        "expected_from_inventory": expected,
        "observed_from_nd": {
            "cluster": {
                "name": "Example-ND-Cluster",
                "ntp_servers": [
                    {"host": "192.0.2.10", "preferred": None},
                    {"host": "192.0.2.11", "preferred": None},
                ],
            },
            "nodes": [
                {
                    "hostname": "EXAMPLE-ND-1",
                    "role": "primary",
                    "cimc_ip": "192.0.2.20",
                    "serial_number": "FDO00000001",
                    "power_state": "On",
                }
            ],
        },
    }


def test_matching_baselines_pass():
    assert compare_nd_baselines(_baseline("manual"), _baseline("automated")) == []


def test_inventory_drift_fails():
    manual = _baseline("manual")
    automated = _baseline("automated")
    automated["expected_from_inventory"]["cluster"]["name"] = "OTHER"

    assert "canonical inventory projection changed between runs" in compare_nd_baselines(
        manual, automated
    )


def test_automated_node_drift_fails():
    manual = _baseline("manual")
    automated = deepcopy(_baseline("automated"))
    automated["observed_from_nd"]["nodes"][0]["cimc_ip"] = "192.0.2.99"

    errors = compare_nd_baselines(manual, automated)

    assert "automated node configuration differs from inventory" in errors
    assert "observed nodes differ between manual and automated runs" in errors
