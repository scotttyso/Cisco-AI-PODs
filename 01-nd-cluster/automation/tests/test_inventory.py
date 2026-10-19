"""Canonical Ansible inventory loading and semantic-validation tests."""
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.lib.inventory import (  # noqa: E402
    InventoryError,
    inventory_from_merged_vars,
    load_ansible,
)


CLUSTER = {
    "start_mode": "iso_reimage",
    "name": "TEST-ND",
    "implementation_type": "LAN",
    "timezone": "America/New_York",
    "iso": {"url": "http://192.0.2.1/nd.iso", "sha512": "a" * 128},
    "network": {
        "mgmt_subnet": "192.0.2.0/24",
        "mgmt_gateway": "192.0.2.1",
        "data_subnet": "203.0.113.0/24",
        "data_gateway": "203.0.113.1",
        "oob_subnet": "198.51.100.0/24",
    },
    "internal_networks": {
        "app_network": "198.18.0.1/16",
        "service_network": "198.19.0.0/16",
    },
    "dns": {"servers": ["192.0.2.53"], "search_domains": ["example.com"]},
    "ntp": {
        "servers": [
            {"host": "198.51.100.20", "preferred": True},
            {"host": "198.51.100.21"},
        ]
    },
    "proxy": {"skip": True},
    "external_services": {
        "management_service_ips": [],
        "data_service_ips": [
            "203.0.113.20",
            "203.0.113.21",
            "203.0.113.22",
            "203.0.113.23",
            "203.0.113.24",
        ],
    },
}

NODES = [
    {
        "hostname": f"ND-{index}",
        "type": "Primary",
        "role": "bootstrap" if index == 1 else "secondary",
        "cimc": {
            "ip": f"198.51.100.{index}",
            "user": "admin",
            "pass_ref": f"ND{index}_CIMC_PASSWORD",
        },
        "mgmt": {"ip": f"192.0.2.{index}", "mask": 24, "gateway": "192.0.2.1"},
        "data": {"ip": f"203.0.113.{index}", "mask": 24, "gateway": "203.0.113.1"},
    }
    for index in (1, 2, 3)
]


def build(cluster=None, nodes=None):
    return inventory_from_merged_vars(
        cluster or deepcopy(CLUSTER),
        {"state_dir": "state/", "verify_tls": False},
        "admin",
        "ND_ADMIN_PASSWORD",
        nodes or deepcopy(NODES),
    )


def test_merged_vars_build_inventory():
    inv = build()
    assert inv.bootstrap_node.hostname == "ND-1"
    assert inv.admin_username == "admin"
    assert inv.cluster.internal_networks.app_network == "198.18.0.1/16"
    assert inv.cluster.external_services.data_service_ips[-1] == "203.0.113.24"


def test_internal_networks_must_be_slash_16():
    cluster = deepcopy(CLUSTER)
    cluster["internal_networks"]["app_network"] = "198.18.0.0/24"
    with pytest.raises(InventoryError, match="requires an IPv4 /16"):
        build(cluster=cluster)


def test_internal_networks_cannot_overlap_each_other():
    cluster = deepcopy(CLUSTER)
    cluster["internal_networks"]["service_network"] = "198.18.0.0/16"
    with pytest.raises(InventoryError, match="internal ND networks overlap"):
        build(cluster=cluster)


def test_internal_network_cannot_overlap_external_plan():
    cluster = deepcopy(CLUSTER)
    cluster["internal_networks"]["app_network"] = "192.0.2.0/16"
    with pytest.raises(InventoryError, match="overlaps ND-MGMT"):
        build(cluster=cluster)


def test_start_mode_must_be_supported():
    cluster = deepcopy(CLUSTER)
    cluster["start_mode"] = "reuse_if_convenient"
    with pytest.raises(InventoryError, match="start_mode must be"):
        build(cluster=cluster)


def test_exactly_one_bootstrap():
    nodes = deepcopy(NODES)
    nodes[0]["role"] = "secondary"
    with pytest.raises(InventoryError, match="exactly one"):
        build(nodes=nodes)


def test_example_inventory():
    repo_root = Path(__file__).resolve().parents[3]
    inventory_bin = Path("/usr/bin/ansible-inventory")
    if not inventory_bin.exists():
        pytest.skip("ansible-inventory is not installed beside the test interpreter")
    inv = load_ansible(
        repo_root / "inventories" / "example" / "inventory.yml",
        inventory_bin=inventory_bin,
    )
    assert inv.cluster.start_mode in {"iso_reimage", "factory_preinstalled"}
    assert inv.cluster.name == "Example-ND-Cluster"
    assert inv.cluster.iso.sha512.startswith("5349fefdc4b601ea5")
    assert inv.cluster.internal_networks.app_network == "198.18.0.1/16"
    assert inv.cluster.internal_networks.service_network == "198.19.0.0/16"
    assert inv.cluster.external_services.management_service_ips == []
    assert inv.cluster.external_services.data_service_ips == [
        "203.0.113.20",
        "203.0.113.21",
        "203.0.113.22",
        "203.0.113.23",
        "203.0.113.24",
    ]
    assert inv.admin_username == "admin"
    assert [node.hostname for node in inv.nodes] == ["EXAMPLE-ND-1", "EXAMPLE-ND-2", "EXAMPLE-ND-3"]
    assert [node.cimc.pass_ref for node in inv.nodes] == [
        "ND1_CIMC_PASSWORD",
        "ND2_CIMC_PASSWORD",
        "ND3_CIMC_PASSWORD",
    ]
