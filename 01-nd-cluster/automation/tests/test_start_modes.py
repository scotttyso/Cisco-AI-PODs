"""Start-mode gates for ND imaging and preinstalled-release verification."""
from __future__ import annotations

import secrets
import sys
import json
from pathlib import Path
from types import SimpleNamespace

import yaml

AUTOMATION = Path(__file__).resolve().parents[1]
REPO = AUTOMATION.parents[1]
sys.path.insert(0, str(AUTOMATION / "scripts"))

import precheck  # noqa: E402
import install_node1  # noqa: E402


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _inventory(start_mode: str):
    nodes = [
        SimpleNamespace(
            hostname=f"ND-{index}",
            mgmt=SimpleNamespace(ip=f"192.0.2.{index + 6}"),
            cimc=SimpleNamespace(
                ip=f"198.51.100.{index + 86}",
                pass_ref=f"ND{index}_CIMC_PASSWORD",
            ),
        )
        for index in (1, 2, 3)
    ]
    return SimpleNamespace(
        cluster=SimpleNamespace(
            start_mode=start_mode,
            iso=SimpleNamespace(
                url="http://192.0.2.150/software/nd-dk9.4.3.1.175.iso"
            ),
        ),
        admin_pass_ref="ND_ADMIN_PASSWORD",
        nodes=nodes,
        runtime=SimpleNamespace(
            state_dir="state/",
            ca_bundle=None,
            verify_tls=False,
        ),
    )


def _result(results, result_id: str):
    return next(result for result in results if result.id == result_id)


def test_factory_preinstalled_requires_all_nodes_at_selected_release(monkeypatch):
    inv = _inventory("factory_preinstalled")
    monkeypatch.setenv(inv.admin_pass_ref, secrets.token_urlsafe(16))
    monkeypatch.setattr(precheck.socket, "create_connection", lambda *_a, **_k: _Connection())
    monkeypatch.setattr(
        precheck,
        "_ssh_acs_version",
        lambda *_a, **_k: ("4.3.1.175", "verified"),
    )

    results = precheck.check_node_os_version_match(inv)

    assert _result(results, "version.cluster_match").status == precheck.PASS
    assert all(
        _result(results, f"version.node.ND-{index}").status == precheck.PASS
        for index in (1, 2, 3)
    )


def test_factory_preinstalled_fails_without_positive_verification(monkeypatch):
    inv = _inventory("factory_preinstalled")
    monkeypatch.setenv(inv.admin_pass_ref, secrets.token_urlsafe(16))

    def connect(address, **_kwargs):
        if address[0] == "192.0.2.9":
            raise OSError("unreachable")
        return _Connection()

    monkeypatch.setattr(precheck.socket, "create_connection", connect)
    monkeypatch.setattr(
        precheck,
        "_ssh_acs_version",
        lambda *_a, **_k: ("4.3.1.175", "verified"),
    )

    results = precheck.check_node_os_version_match(inv)

    assert _result(results, "version.node.ND-3").status == precheck.FAIL
    assert _result(results, "version.cluster_match").status == precheck.FAIL


def test_factory_preinstalled_accepts_serial_bound_pre_reset_evidence(
    monkeypatch, tmp_path
):
    inv = _inventory("factory_preinstalled")
    monkeypatch.setenv(inv.admin_pass_ref, secrets.token_urlsafe(16))
    monkeypatch.setattr(
        precheck.socket,
        "create_connection",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("factory reset")),
    )
    import discover_serials

    serials = {
        node.hostname: f"FDO0000000{index}"
        for index, node in enumerate(inv.nodes, 1)
    }
    monkeypatch.setattr(
        discover_serials,
        "_discover",
        lambda node, _verify: (
            node.hostname,
            {
                "cimc_ip": node.cimc.ip,
                "serial_number": serials[node.hostname],
                "power_state": "On",
            },
        ),
    )
    evidence = {
        "schema_version": 1,
        "selected_release": "4.3.1.175",
        "nodes": {
            node.hostname: {
                "cimc_ip": node.cimc.ip,
                "serial_number": f"FDO0000000{index}",
                "installed_release": "4.3.1.175",
            }
            for index, node in enumerate(inv.nodes, 1)
        },
    }
    evidence_path = tmp_path / "nd-release-evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    results = precheck.check_node_os_version_match(
        inv, release_evidence_path=evidence_path
    )

    assert _result(results, "version.cluster_match").status == precheck.PASS
    assert all(
        _result(results, f"version.node.ND-{index}").status == precheck.PASS
        for index in (1, 2, 3)
    )


def test_iso_reimage_allows_current_release_probe_to_skip(monkeypatch):
    inv = _inventory("iso_reimage")
    monkeypatch.setenv(inv.admin_pass_ref, secrets.token_urlsafe(16))
    monkeypatch.setattr(
        precheck.socket,
        "create_connection",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("unreachable")),
    )

    results = precheck.check_node_os_version_match(inv)

    assert all(
        _result(results, f"version.node.ND-{index}").status == precheck.SKIP
        for index in (1, 2, 3)
    )
    assert _result(results, "version.cluster_match").status == precheck.SKIP


def test_iso_reimage_does_not_block_on_current_release_drift(monkeypatch):
    inv = _inventory("iso_reimage")
    monkeypatch.setenv(inv.admin_pass_ref, secrets.token_urlsafe(16))
    monkeypatch.setattr(precheck.socket, "create_connection", lambda *_a, **_k: _Connection())
    versions = {
        "192.0.2.7": "4.3.1.175",
        "192.0.2.8": "4.2.1.10",
        "192.0.2.9": "4.1.1g",
    }
    monkeypatch.setattr(
        precheck,
        "_ssh_acs_version",
        lambda host, *_a, **_k: (versions[host], "verified"),
    )

    results = precheck.check_node_os_version_match(inv)

    assert _result(results, "version.cluster_match").status == precheck.WARN
    assert not any(result.status == precheck.FAIL for result in results)


def test_playbook_images_every_node_only_for_iso_reimage():
    playbook = yaml.safe_load(
        (AUTOMATION / "playbooks" / "01_nd_cluster.yml").read_text()
    )
    image_play = next(play for play in playbook if play["hosts"] == "nd_cluster")
    task = next(
        task
        for task in image_play["tasks"]
        if task["name"] == "Image this ND node from the selected ISO"
    )

    assert task["vars"]["node"] == "{{ nd_node }}"
    assert task["when"] == "nd_cluster_spec.start_mode == 'iso_reimage'"
    assert "loop" not in task
    assert "requires_imaging" not in (
        AUTOMATION / "playbooks" / "01_nd_cluster.yml"
    ).read_text()


def test_playbook_bootstraps_nd1_without_imaging_for_preinstalled_mode():
    playbook = yaml.safe_load(
        (AUTOMATION / "playbooks" / "01_nd_cluster.yml").read_text()
    )
    task = next(
        task
        for task in playbook[0]["tasks"]
        if task["name"] == "Bootstrap ND-1 from the verified installed release"
    )

    assert task["ansible.builtin.import_role"]["tasks_from"] == "bootstrap_node"
    assert task["when"] == "nd_cluster_spec.start_mode == 'factory_preinstalled'"
    assert "selectattr('role', 'equalto', 'bootstrap')" in task["vars"]["node"]


def test_bootstrap_role_uses_bootstrap_only_python_phase():
    tasks = yaml.safe_load(
        (
            AUTOMATION
            / "roles"
            / "nd_cluster"
            / "tasks"
            / "bootstrap_node.yml"
        ).read_text()
    )
    command = next(task for task in tasks if "ansible.builtin.command" in task)

    assert "scripts/main.py bootstrap" in command["ansible.builtin.command"]["cmd"]
    assert "scripts/main.py node1" not in command["ansible.builtin.command"]["cmd"]
    assert isinstance(command["environment"], str)
    assert "combine" in command["environment"]
    assert "admin_pass_ref" in command["environment"]
    assert "node.cimc.pass_ref" in command["environment"]


def test_bootstrap_only_skips_cimc_when_state_is_complete(monkeypatch, tmp_path):
    node = SimpleNamespace(hostname="ND-1")
    inv = SimpleNamespace(
        bootstrap_node=node,
        runtime=SimpleNamespace(state_dir=tmp_path),
    )
    monkeypatch.setattr(install_node1, "is_complete", lambda *_a, **_k: True)

    def unexpected_cimc(*_args, **_kwargs):
        raise AssertionError("completed bootstrap must not contact CIMC")

    monkeypatch.setattr(install_node1, "CimcRedfish", unexpected_cimc)

    assert install_node1.bootstrap_only(inv) is False


def test_image_role_dispatches_bootstrap_and_secondary_installers():
    tasks = yaml.safe_load(
        (
            AUTOMATION
            / "roles"
            / "nd_cluster"
            / "tasks"
            / "image_node.yml"
        ).read_text()
    )
    image = next(task for task in tasks if task["name"] == "ND/image_node: image {{ node.hostname }}")
    command = image["ansible.builtin.command"]["cmd"]

    assert "'node1' if node.role == 'bootstrap' else 'secondary'" in command
    assert "--node" in command
    assert image["when"] == "cluster.start_mode == 'iso_reimage'"
    assert isinstance(image["environment"], str)
    assert "combine" in image["environment"]
    assert "node.cimc.pass_ref" in image["environment"]
    assert "admin_pass_ref" in image["environment"]


def test_primary_and_secondary_allow_for_delayed_vmedia_skip_prompt():
    primary = (AUTOMATION / "scripts" / "install_node1.py").read_text()
    secondary = (AUTOMATION / "scripts" / "install_secondaries.py").read_text()

    assert "wait_and_send_skip(timeout_s=900)" in primary
    assert "wait_and_send_skip(timeout_s=900)" in secondary
