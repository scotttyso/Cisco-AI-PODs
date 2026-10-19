"""Offline real-Ansible tests: a failed gate cannot reach a later play.

The checker transport is a synthetic local JSON emitter, never a lab endpoint.
Parser/decision tests exercise the actual checker separately.
"""
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "roles/backend_fabric_nxos"
TASK = ROLE / "tasks/preflight_core_connectivity.yml"
ANSIBLE = Path("/usr/bin/ansible-playbook")


def result(ready=True, fabric="backend"):
    return {"deployment_ready": ready, "require_inventory_match": True,
            "mutations_performed": False, "read_failures": [], "inventory_warnings": [],
            "fabrics": [{"fabric": fabric, "physical_gate": "PASS" if ready else "FAIL",
                         "issues": [] if ready else [{"type": "port_down"}]}]}


def execute(tmp_path, payload, code=0, check=False, selected=None):
    # Exercise packaged checker discovery too; no override of production gate.
    fake_role = tmp_path / "role"
    script = fake_role / "files/automation/scripts/check_be_core_connectivity.py"
    script.parent.mkdir(parents=True)
    script.write_text("print(" + repr(payload) + ")\nraise SystemExit(" + str(code) + ")\n")
    values = {"role_path": str(fake_role), "be_core_inventory_dir": str(tmp_path),
              "be_core_sg2_plan": "", "be_core_cabling_plans": {}, "be_fabrics": [{"key": "backend", "name": "AIPOD-Backend"}, {"key": "backend_800g", "name": "AIPOD-Backend-800G"}], "be_target_fabric_keys": selected or ["backend"]}
    playbook = [
        {"hosts": "gate_hosts", "gather_facts": False, "connection": "local",
         "vars": values, "tasks": [{"ansible.builtin.include_tasks": str(TASK)}]},
        {"hosts": "controller", "gather_facts": False, "connection": "local",
         "tasks": [{"ansible.builtin.debug": {"msg": "OFFLINE_TEMPLATE_SENTINEL"}}]},
    ]
    path = tmp_path / "gate.yml"
    path.write_text(yaml.safe_dump(playbook, sort_keys=False))
    inventory = tmp_path / "inventory.yml"
    inventory.write_text(yaml.safe_dump({"all": {"vars": {"ansible_python_interpreter": sys.executable},
        "children": {"gate_hosts": {"hosts": {"fake-spine": {}, "fake-leaf": {}}},
                     "controller": {"hosts": {"localhost": {}}}}}}))
    argv = [str(ANSIBLE), "-i", str(inventory), str(path)] + (["--check"] if check else [])
    return subprocess.run(argv, cwd=ROOT.parents[1], capture_output=True, text=True, timeout=45)


@pytest.mark.parametrize("check", [False, True])
def test_passing_fresh_gate_allows_following_play_offline(tmp_path, check):
    run = execute(tmp_path, json.dumps(result()), check=check)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "OFFLINE_TEMPLATE_SENTINEL" in run.stdout


@pytest.mark.parametrize("scenario", ["down", "incomplete", "stale", "bad_json", "contradictory", "wrong_target"])
def test_failed_gate_blocks_following_play_even_on_other_hosts(tmp_path, scenario):
    body, code = result(), 0
    if scenario == "down":
        body, code = result(False), 1
    elif scenario == "incomplete":
        body, code = {"deployment_ready": False, "input_error": True}, 2
    elif scenario == "stale":
        body["inventory_warnings"] = [{"switch": "EXAMPLE-BE-800G-SPINE-1", "plan_ports_missing_from_inventory": ["Eth1/8/1"]}]
        body["deployment_ready"], code = False, 1
    elif scenario == "contradictory":
        body["deployment_ready"] = False
    elif scenario == "wrong_target":
        body["fabrics"][0]["fabric"] = "backend_800g"
    payload = "not-json" if scenario == "bad_json" else json.dumps(body)
    run = execute(tmp_path, payload, code)
    assert run.returncode != 0
    assert "require explicit physical preflight inputs" in run.stdout
    assert "Local RPC server did not start" not in run.stderr
    assert "OFFLINE_TEMPLATE_SENTINEL" not in run.stdout


def test_planless_inventory_defined_fabric_runs_the_gate(tmp_path):
    run = execute(tmp_path, json.dumps(result(fabric="backend_800g")), selected=["backend_800g"])
    assert run.returncode == 0, run.stdout + run.stderr
    assert "collect fresh serial paced physical evidence" in run.stdout
    assert "OFFLINE_TEMPLATE_SENTINEL" in run.stdout


def test_gate_precedes_preparation_and_nd_template_writes():
    playbook = yaml.safe_load((ROOT / "playbooks/02_backend_fabric.yml").read_text())
    assert playbook[0]["any_errors_fatal"] is True
    assert playbook[0]["pre_tasks"][0]["ansible.builtin.include_role"]["tasks_from"] == "preflight_core_connectivity.yml"
    assert "be_target_fabric_keys" in playbook[0]["tasks"][0]["when"]
    main = yaml.safe_load((ROLE / "tasks/main.yml").read_text())
    assert main[0]["ansible.builtin.include_tasks"] == "preflight_core_connectivity.yml"
    gate = yaml.safe_load(TASK.read_text())[0]
    assert gate["any_errors_fatal"] is True
    command = next(t for t in gate["block"] if "ansible.builtin.command" in t)
    assert command["check_mode"] is False
    assert command["changed_when"] is False
    assert command["no_log"] is True
    assert "until" not in command and "retries" not in command
    assert "--require-inventory-match" in command["ansible.builtin.command"]["argv"]
