"""Regression tests for backend-fabric underlay pool rewriting."""
from __future__ import annotations

import re
from pathlib import Path

import pytest


ROLE_TASKS = Path(__file__).resolve().parents[1] / "roles/backend_fabric_nxos/tasks"
ROLE_DEFAULTS = Path(__file__).resolve().parents[1] / "roles/backend_fabric_nxos/defaults/main.yml"


@pytest.mark.parametrize(
    "task_file",
    [
        "build_fabric_config.yml",
        "collect_manage_pool_override.yml",
    ],
)
def test_default_10_pool_is_rewritten_to_fabric_octet(task_file: str) -> None:
    text = (ROLE_TASKS / task_file).read_text(encoding="utf-8")
    match = re.search(r"regex_replace\(\s*'([^']+)'", text)

    assert match is not None
    assert re.sub(match.group(1), "20.", "10.2.0.0/22") == "20.2.0.0/22"
    assert re.sub(match.group(1), "21.", "10.3.0.0/22") == "21.3.0.0/22"


def test_only_active_fabric_pools_are_managed() -> None:
    import yaml

    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text(encoding="utf-8"))

    assert defaults["be_ndfc_pool_keys"] == [
        "LOOPBACK0_IP_RANGE",
        "LOOPBACK1_IP_RANGE",
        "SUBNET_RANGE",
        "ANYCAST_RP_IP_RANGE",
        "DCI_SUBNET_RANGE",
    ]
    assert "PER_VRF_LOOPBACK_IP_RANGE" not in defaults["be_ndfc_pool_keys"]
    assert "perVrfUniqueLoopbackIpRange" not in defaults["be_ndfc_pool_keys"]
    assert "hypershieldHASourceSubnet" not in defaults["be_ndfc_pool_keys"]
    assert "hypershieldHAPeerLinkSubnet" not in defaults["be_ndfc_pool_keys"]

    assert defaults["be_manage_pool_keys"] == [
        "bgpLoopbackIpRange",
        "nveLoopbackIpRange",
        "intraFabricSubnetRange",
        "anycastRendezvousPointIpRange",
        "vrfLiteSubnetRange",
    ]


def test_ingress_replication_does_not_populate_multicast_anycast_rp_pool() -> None:
    text = (ROLE_TASKS / "build_fabric_config.yml").read_text(encoding="utf-8")

    assert "be_default_item.key != 'ANYCAST_RP_IP_RANGE'" in text
    assert "!= 'Ingress'" in text
