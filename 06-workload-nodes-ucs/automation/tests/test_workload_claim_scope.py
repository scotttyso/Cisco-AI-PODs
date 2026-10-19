"""Inventory/claim scope contract; all connector and Intersight work is stubbed."""
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from validate_inventory import load_schema_tree

TASKS = ROOT / "06-workload-nodes-ucs/automation/roles/workload_nodes_ucs/tasks"


def _validator():
    path = ROOT / "schemas/workload-nodes-ucs.schema.json"
    schema, registry = load_schema_tree(path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator({"$ref": path.as_uri()}, registry=registry)


@pytest.mark.parametrize("platform,supported,has_target,valid", [
    ("standalone", False, False, True),
    ("standalone", False, True, False),
    ("domain", False, False, False),
    ("standalone", True, True, True),
    ("standalone", True, False, False),
    ("standalone", None, True, True),
    ("standalone", None, False, False),
    ("domain", None, True, True),
    ("domain", None, False, False),
])
def test_workload_schema_requires_claim_target_only_for_supported_nodes(
    platform, supported, has_target, valid,
):
    system = {
        "inventory_host": "fixture-server", "platform": platform, "role": "gpu",
        "cimc": {"ip": "192.0.2.1", "user": "admin", "pass_ref": "FIXTURE_PASSWORD"},
    }
    if supported is not None:
        system["intersight_claim_supported"] = supported
    if has_target:
        system["claim_target"] = "fixture-server"
    assert _validator().is_valid({"systems": [system]}) is valid


def test_canonical_workload_inventory_matches_the_coordinated_schema():
    inventory_root = ROOT / "inventories/example"
    inventory = yaml.safe_load((inventory_root / "inventory.yml").read_text())
    hosts = inventory["all"]["children"]["ucs_workload_nodes"]["hosts"]
    systems = []
    excluded = []
    for host in hosts:
        ucs = yaml.safe_load((inventory_root / "host_vars" / f"{host}.yml").read_text())["ucs"]
        system = {"inventory_host": host, "platform": ucs["platform"], "role": ucs["role"],
                  "cimc": {key: ucs["cimc"][key] for key in ("ip", "user", "pass_ref")}}
        for key in ("claim_target", "intersight_claim_supported"):
            if key in ucs:
                system[key] = ucs[key]
        systems.append(system)
        if host.startswith("ucs-c880-"):
            assert ucs["intersight_claim_supported"] is False
            assert "claim_target" not in ucs
            excluded.append(host)
        else:
            assert ucs.get("intersight_claim_supported", True) is True
            assert ucs["claim_target"]
    assert len(excluded) == 4
    _validator().validate({"systems": systems})


@pytest.mark.parametrize("entrypoint", ["main", "reclaim"])
@pytest.mark.parametrize("selection", ["all", "excluded_only", "supported_only"])
def test_real_role_selection_excludes_unclaimable_nodes_before_credentials(
    tmp_path, entrypoint, selection,
):
    executable = Path("/usr/bin/ansible-playbook")
    assert executable.is_file(), "This scope regression requires ansible-core."
    # Retain the actual normal/reclaim entrypoints, eligibility expressions and
    # target builder. Replace only the target processing with an offline stub.
    role_tasks = tmp_path / "tasks"
    role_tasks.mkdir()
    for filename in ("main.yml", "reclaim.yml", "intersight_claim.yml", "build_target.yml"):
        (role_tasks / filename).write_text((TASKS / filename).read_text())
    (role_tasks / "process_target_safe.yml").write_text(yaml.safe_dump([
        {"ansible.builtin.set_fact": {
            "processed_targets": "{{ processed_targets + [ucs_claim_target_item.key] }}"
        }}
    ]))
    domain = {"platform": "domain", "role": "gpu", "claim_target": "fixture-domain",
              "cimc": {"ip": "192.0.2.2", "user": "admin", "pass_ref": "FIXTURE_PASSWORD"}}
    rack = {"platform": "standalone", "role": "gpu", "claim_target": "fixture-rack",
            "cimc": {"ip": "192.0.2.3", "user": "admin", "pass_ref": "FIXTURE_PASSWORD"}}
    # Deliberately omit CIMC and claim metadata for the excluded node. Any
    # credential lookup or connector discovery for it would fail this run.
    hosts = {
        "fixture-excluded": {"ucs": {"platform": "standalone", "role": "gpu",
                                      "intersight_claim_supported": False}},
        "fixture-domain-a": {"ucs": deepcopy(domain)},
        "fixture-domain-b": {"ucs": deepcopy(domain)},
        "fixture-rack": {"ucs": rack},
    }
    inventory = tmp_path / "inventory.yml"
    inventory.write_text(yaml.safe_dump({"all": {"children": {"ucs_workload_nodes": {"hosts": hosts}}}}))
    filters = {"all": [], "excluded_only": ["fixture-excluded"],
               "supported_only": ["fixture-domain", "fixture-rack"]}
    variables = {
        "ucs_claim_inventory_group": "ucs_workload_nodes",
        "ucs_intersight_target_filter": filters[selection],
        "ucs_intersight_allow_reclaim": True, "processed_targets": [],
    }
    if selection != "excluded_only":
        variables.update({
            "intersight_api_uri": "https://intersight.com", "intersight_account_name": "fixture-account",
            "intersight_resource_group_name": "fixture-group", "vault_intersight_api_key_id": "CHANGE_ME",
            "vault_intersight_api_private_key": "CHANGE_ME", "vault_fixture_password": "CHANGE_ME",
        })
    expected_processed = [] if selection == "excluded_only" else ["fixture-domain", "fixture-rack"]
    expected_skipped = [] if selection == "supported_only" else [{
        "inventory_host": "fixture-excluded", "outcome": "not_supported",
        "message": "Not supported on UCS C880.",
    }]
    playbook = tmp_path / "playbook.yml"
    playbook.write_text(yaml.safe_dump([{
        "hosts": "localhost", "connection": "local", "gather_facts": False, "vars": variables,
        "tasks": [
            {"ansible.builtin.include_tasks": str(role_tasks / f"{entrypoint}.yml")},
            {"ansible.builtin.assert": {"that": [
                "processed_targets == expected_processed", "ucs_intersight_skipped_targets == expected_skipped",
                "ucs_claim_failures == []",
                "ucs_intersight_reclaim_mode == expected_reclaim",
                "ucs_claim_targets.get('fixture-domain', {}).get('endpoints', []) | length == expected_domain_endpoints",
            ]}, "vars": {"expected_processed": expected_processed, "expected_skipped": expected_skipped,
                         "expected_reclaim": entrypoint == "reclaim",
                         "expected_domain_endpoints": 0 if selection == "excluded_only" else 2}},
        ],
    }]))
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nretry_files_enabled = False\n")
    env = dict(os.environ, ANSIBLE_CONFIG=str(config), ANSIBLE_LOCAL_TEMP=str(tmp_path / "local"),
               ANSIBLE_REMOTE_TEMP=str(tmp_path / "remote"), ANSIBLE_NOCOLOR="1")
    result = subprocess.run([str(executable), "-i", str(inventory), str(playbook)],
                            env=env, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    if expected_skipped:
        assert "Not supported on UCS C880." in result.stdout
