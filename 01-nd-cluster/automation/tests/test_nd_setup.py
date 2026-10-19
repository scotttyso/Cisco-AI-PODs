"""Exact canonical-inventory to cisco.nd.nd_setup mapping tests."""
from __future__ import annotations

from dataclasses import replace
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.lib.inventory import InventoryError, load_ansible  # noqa: E402
from shared.lib.nd_setup import build_nd_setup_args  # noqa: E402


def _inventory():
    root = Path(__file__).resolve().parents[3]
    return load_ansible(
        root / "inventories" / "example" / "inventory.yml",
        inventory_bin=Path("/usr/bin/ansible-inventory"),
    )


def _serials():
    # Lowercase keys model a pre-uppercase-migration runtime artifact. Mapping
    # must remain compatible while the outgoing ND hostnames use canonical case.
    return {
        "schema_version": 1,
        "nodes": {
            "example-nd-1": {"cimc_ip": "198.51.100.87", "serial_number": "FDO00000001"},
            "example-nd-2": {"cimc_ip": "198.51.100.88", "serial_number": "FDO00000002"},
            "example-nd-3": {"cimc_ip": "198.51.100.89", "serial_number": "FDO00000003"},
        },
    }


def test_exact_nd_setup_mapping():
    args = build_nd_setup_args(
        _inventory(),
        _serials(),
        admin_password="ADMIN-SECRET",
        resolve_cimc_password=lambda ref: f"SECRET:{ref}",
    )
    assert args["host"] == "192.0.2.7"
    assert args["username"] == "admin"
    assert args["timeout"] == 3600
    assert args["cluster_name"] == "Example-ND-Cluster"
    assert args["persona"] == "lan"
    assert args["app_network"] == "198.18.0.1/16"
    assert args["service_network"] == "198.19.0.0/16"
    assert args["dns_search_domain"] == ["example.com"]
    assert args["dns_server"] == ["192.0.2.53", "192.0.2.54"]
    assert args["ntp_config"]["servers"] == [
        {"ntp_host": "198.51.100.124", "preferred": True},
        {"ntp_host": "198.51.100.125", "preferred": False},
    ]
    assert "timezone" not in args
    assert args["external_services"] == {
        "data_service_ips": [
            "203.0.113.20",
            "203.0.113.21",
            "203.0.113.22",
            "203.0.113.23",
            "203.0.113.24",
        ],
    }
    assert [node["serial_number"] for node in args["nodes"]] == [
        "FDO00000001",
        "FDO00000002",
        "FDO00000003",
    ]
    assert [node["hostname"] for node in args["nodes"]] == [
        "EXAMPLE-ND-1",
        "EXAMPLE-ND-2",
        "EXAMPLE-ND-3",
    ]
    assert args["nodes"][1]["management_ip_address"] == "198.51.100.88"
    assert args["nodes"][1]["management_network"] == {
        "ipv4_address": "192.0.2.8/24",
        "ipv4_gateway": "192.0.2.254",
    }
    assert args["nodes"][1]["data_network"] == {
        "ipv4_address": "203.0.113.18/24",
        "ipv4_gateway": "203.0.113.254",
    }


def test_serial_artifact_must_match_cimc():
    serials = _serials()
    serials["nodes"]["example-nd-2"]["cimc_ip"] = "192.0.2.1"
    with pytest.raises(InventoryError, match="CIMC mismatch"):
        build_nd_setup_args(
            _inventory(),
            serials,
            admin_password="ADMIN-SECRET",
            resolve_cimc_password=lambda ref: f"SECRET:{ref}",
        )


def test_nd_setup_includes_configured_dns_search_domains():
    inv = _inventory()
    inv = replace(
        inv,
        cluster=replace(
            inv.cluster,
            dns=replace(inv.cluster.dns, search_domains=["example.com"]),
        ),
    )
    args = build_nd_setup_args(
        inv,
        _serials(),
        admin_password="ADMIN-SECRET",
        resolve_cimc_password=lambda ref: f"SECRET:{ref}",
    )
    assert args["dns_search_domain"] == ["example.com"]


def test_form_cluster_waits_for_authenticated_https_before_nd_setup():
    root = Path(__file__).resolve().parents[3]
    tasks = yaml.safe_load(
        (
            root
            / "01-nd-cluster/automation/roles/nd_cluster/tasks/form_cluster.yml"
        ).read_text()
    )
    names = [task["name"] for task in tasks]
    socket_name = "ND/form_cluster: wait for ND-1 HTTPS socket"
    login_name = "ND/form_cluster: wait for ND-1 login service"
    create_name = "ND/form_cluster: create the 3-node cluster with cisco.nd.nd_setup"

    assert names.index(socket_name) < names.index(login_name) < names.index(create_name)
    login = next(task for task in tasks if task["name"] == login_name)
    assert login["no_log"] is True
    assert login["ansible.builtin.uri"]["status_code"] == 200
    assert login["ansible.builtin.uri"]["body"]["domain"] == "DefaultAuth"
    assert login["until"] == "nd_login_ready.status | default(0) == 200"


def test_form_cluster_uses_reconnecting_setup_wait_after_native_create():
    root = Path(__file__).resolve().parents[3]
    tasks = yaml.safe_load(
        (
            root
            / "01-nd-cluster/automation/roles/nd_cluster/tasks/form_cluster.yml"
        ).read_text()
    )
    names = [task["name"] for task in tasks]
    create_name = "ND/form_cluster: create the 3-node cluster with cisco.nd.nd_setup"
    wait_name = "ND/form_cluster: wait for setup completion across service restarts"

    assert names.index(create_name) < names.index(wait_name)
    wait_task = next(task for task in tasks if task["name"] == wait_name)
    assert "scripts/wait_setup_completion.py" in wait_task["ansible.builtin.command"]["cmd"]
    assert wait_task["no_log"] is True


def test_form_cluster_does_not_resubmit_active_or_completed_setup():
    root = Path(__file__).resolve().parents[3]
    tasks = yaml.safe_load(
        (
            root
            / "01-nd-cluster/automation/roles/nd_cluster/tasks/form_cluster.yml"
        ).read_text()
    )
    names = [task["name"] for task in tasks]
    inspect_name = "ND/form_cluster: inspect existing setup state before create"
    reject_name = "ND/form_cluster: reject a failed prior setup"
    create_name = "ND/form_cluster: create the 3-node cluster with cisco.nd.nd_setup"
    create = next(task for task in tasks if task["name"] == create_name)

    assert names.index(inspect_name) < names.index(reject_name) < names.index(create_name)
    assert create["when"] == (
        "(nd_existing_setup_state | lower) not in ['inprogress', 'completed']"
    )
    assert next(task for task in tasks if task["name"] == inspect_name)["no_log"] is True
