"""Static safety contract for the ND-owned Cisco Intersight claim capability."""
from __future__ import annotations

from pathlib import Path

import yaml


AUTOMATION = Path(__file__).resolve().parents[1]
TASKS = AUTOMATION / "roles" / "nd_cluster" / "tasks"
PLAYBOOKS = AUTOMATION / "playbooks"


def _tasks(name: str):
    return yaml.safe_load((TASKS / name).read_text(encoding="utf-8"))


def test_normal_claim_never_unclaims_a_target():
    tasks = _tasks("intersight_claim.yml")
    claim = next(task for task in tasks if "submit an unclaimed Nexus Dashboard Device Claim" in task["name"])
    assert claim["cisco.intersight.intersight_rest_api"]["state"] == "present"
    assert all(
        task.get("cisco.intersight.intersight_target_claim", {}).get("state") != "absent"
        for task in tasks
    )


def test_normal_claim_discovers_never_inventories_device_credentials():
    text = (TASKS / "intersight_claim.yml").read_text(encoding="utf-8")
    assert "/api/v1/infra/intersight/status" in text
    assert "/api/v1/infra/intersight/about" in text
    assert "/api/v1/infra/intersight/securityToken" in text
    assert "resource_path: /asset/DeviceClaims" in text
    assert "SerialNumber: \"{{ nd_intersight_device_id }}\"" in text
    assert "SecurityToken: \"{{ nd_intersight_security_token.json.token }}\"" in text
    assert "no_log: true" in text


def test_connector_status_waits_through_post_install_service_startup():
    tasks = _tasks("intersight_claim.yml")
    status = next(
        task
        for task in tasks
        if task["name"] == "ND/Intersight: read current connector ownership state"
    )

    assert status["ansible.builtin.uri"]["status_code"] == [200, 500, 502, 503, 504]
    assert status["until"] == "nd_intersight_status_before.status == 200"
    assert status["retries"] == 30
    assert status["delay"] == 10


def test_resource_group_update_preserves_existing_selectors():
    text = (TASKS / "intersight_claim.yml").read_text(encoding="utf-8")
    assert "nd_intersight_existing_selectors" in text
    assert "nd_intersight_current_registration_selectors" in text
    assert "selectattr('Selector', 'search', nd_intersight_registration_moid)" in text
    assert "nd_intersight_existing_selectors\n          +" in text
    assert "resource_path: /resource/Groups" in text
    assert "DeviceRegistrations?$filter=(Moid eq '{{ nd_intersight_registration_moid }}')" in text


def test_reclaim_requires_one_run_confirmation_before_absent_state():
    tasks = _tasks("intersight_reclaim.yml")
    assert "nd_intersight_allow_reclaim" in str(tasks[0])
    unclaim = next(task for task in tasks if "intersight_target_claim" in str(task))
    assert unclaim["cisco.intersight.intersight_target_claim"]["state"] == "absent"


def test_normal_and_destructive_entrypoints_are_separate():
    normal = yaml.safe_load((PLAYBOOKS / "01_nd_cluster.yml").read_text(encoding="utf-8"))
    assert any(
        play["name"] == "Subsystem 01 - Claim the Nexus Dashboard cluster in Cisco Intersight"
        for play in normal
    )
    reclaim = yaml.safe_load((PLAYBOOKS / "reclaim_nd_intersight.yml").read_text(encoding="utf-8"))
    assert reclaim[0]["name"] == "Subsystem 01 - Explicitly unclaim and reclaim Nexus Dashboard"


def test_stale_target_cleanup_is_opt_in_and_protects_current_registration():
    defaults = yaml.safe_load(
        (AUTOMATION / "roles" / "nd_cluster" / "defaults" / "main.yml").read_text(
            encoding="utf-8"
        )
    )
    cleanup = (TASKS / "intersight_prune_stale_targets.yml").read_text(encoding="utf-8")
    claim = (TASKS / "intersight_claim.yml").read_text(encoding="utf-8")

    assert defaults["nd_intersight_prune_stale_targets"] is False
    assert "when: nd_intersight_prune_stale_targets | bool" in claim
    assert "selectattr('Status', 'equalto', 'Connected')" in cleanup
    assert "selectattr('Status', 'equalto', 'NotConnected')" in cleanup
    assert "rejectattr('RegisteredDevice.Moid', 'equalto', nd_intersight_registration_moid)" in cleanup
    assert "$filter: \"Moid eq '{{ item.Moid }}'\"" in cleanup
    assert "state: absent" in cleanup
    assert "nd_intersight_preserved_selectors + [item]" in cleanup
    assert "api_response | default([]) | length == 1" in cleanup
