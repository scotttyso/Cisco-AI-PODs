"""Secret-free ND parity-baseline normalization tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.lib.nd_baseline import normalize_nd_baseline  # noqa: E402


def _cluster():
    return {
        "name": "Example-ND-Cluster",
        "implementation_type": "LAN",
        "dns": {"servers": ["192.0.2.53", "192.0.2.54"], "search_domains": []},
        "ntp": {
            "servers": [
                {"host": "198.51.100.124", "preferred": True},
                {"host": "198.51.100.125"},
            ]
        },
        "internal_networks": {
            "app_network": "198.18.0.1/16",
            "service_network": "198.19.0.0/16",
        },
        "external_services": {
            "management_service_ips": [],
            "data_service_ips": ["203.0.113.20", "203.0.113.21"],
        },
    }


def _nodes():
    return [
        {
            "hostname": f"ND-{index}",
            "type": "Primary",
            "role": "bootstrap" if index == 1 else "secondary",
            "cimc": {"ip": f"198.51.100.{86 + index}"},
            "mgmt": {"ip": f"192.0.2.{6 + index}", "mask": 24, "gateway": "192.0.2.254"},
            "data": {"ip": f"203.0.113.{16 + index}", "mask": 24, "gateway": "203.0.113.254"},
        }
        for index in (1, 2, 3)
    ]


def _current():
    return {
        "state": "Completed",
        "clusterConfig": {
            "name": "Example-ND-Cluster",
            "persona": "LAN",
            "nameServers": ["192.0.2.53", "192.0.2.54"],
            "searchDomains": [],
            "ntpConfig": {
                "servers": [
                    {"host": "198.51.100.124", "prefer": True},
                    {"host": "198.51.100.125", "prefer": False},
                ]
            },
            "appNetwork": "198.18.0.1/16",
            "serviceNetwork": "198.19.0.0/16",
            "externalServices": [{"target": "Data", "pool": ["203.0.113.20", "203.0.113.21"]}],
        },
        "nodes": [
            {
                "hostName": f"ND-{index}",
                "serialNumber": f"FDO0000000{index}",
                "role": "master",
                "managementNetwork": {
                    "ipSubnet": f"192.0.2.{6 + index}/24",
                    "gateway": "192.0.2.254",
                },
                "dataNetwork": {
                    "ipSubnet": f"203.0.113.{16 + index}/24",
                    "gateway": "203.0.113.254",
                },
                "nodeController": {
                    "id": "physical",
                    "ipAddress": f"198.51.100.{86 + index}",
                    "loginUser": "admin",
                    "loginPassword": "MUST-NOT-LEAK",
                },
            }
            for index in (1, 2, 3)
        ],
    }


def test_normalized_baseline_is_complete_and_secret_free():
    artifact = normalize_nd_baseline(
        _current(),
        {"platformVersion": "4.3.1"},
        _cluster(),
        _nodes(),
        baseline_kind="manual",
        captured_at="20260923T200000Z",
        serial_artifact={
            "nodes": {
                f"ND-{index}": {
                    "serial_number": f"FDO0000000{index}",
                    "cimc_ip": f"198.51.100.{86 + index}",
                    "power_state": "On",
                }
                for index in (1, 2, 3)
            }
        },
    )

    assert artifact["setup_state"] == "Completed"
    assert artifact["software_version"] == "4.3.1"
    assert artifact["observed_from_nd"]["cluster"]["search_domains"] == []
    assert len(artifact["observed_from_nd"]["nodes"]) == 3
    assert artifact["observed_from_nd"]["nodes"][0]["cimc_ip"] == "198.51.100.87"
    serialized = json.dumps(artifact).lower()
    assert "must-not-leak" not in serialized
    assert "loginpassword" not in serialized
    assert "password" not in serialized


def test_full_bootstrap_document_takes_precedence_over_collapsed_setup_query():
    collapsed = _current()
    collapsed["nodes"][0]["managementNetwork"] = {
        "ipSubnet": "192.0.2.7/0",
        "gateway": None,
    }
    full = _current()
    artifact = normalize_nd_baseline(
        collapsed,
        {"platformVersion": "4.3.1"},
        _cluster(),
        _nodes(),
        baseline_kind="manual",
        captured_at="20260923T200000Z",
        bootstrap=full,
        cluster_status={"state": "active"},
    )

    assert artifact["runtime_state"] == "active"
    assert artifact["observed_from_nd"]["nodes"][0]["management_network"] == {
        "ipv4_address": "192.0.2.7/24",
        "ipv4_gateway": "192.0.2.254",
        "vlan": None,
    }


def test_ntp_preference_is_unknown_when_api_only_returns_addresses():
    current = _current()
    current["clusterConfig"]["ntpConfig"] = {}
    current["clusterConfig"]["ntpServers"] = [
        "198.51.100.124",
        "198.51.100.125",
    ]
    artifact = normalize_nd_baseline(
        current,
        {"platformVersion": "4.3.1"},
        _cluster(),
        _nodes(),
        baseline_kind="manual",
        captured_at="20260923T200000Z",
    )

    assert artifact["observed_from_nd"]["cluster"]["ntp_servers"][0][
        "preferred"
    ] is None
    assert artifact["api_unverifiable_fields"] == [
        "cluster.ntp_servers[].preferred"
    ]
