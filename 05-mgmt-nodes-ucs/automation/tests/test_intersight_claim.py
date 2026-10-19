"""Static safety contract for subsystem 05 Intersight claim automation."""
from pathlib import Path

import yaml


AUTOMATION = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]
ROLE = AUTOMATION / "roles" / "mgmt_nodes_ucs"
PLAYBOOKS = AUTOMATION / "playbooks"
RECONCILE = ROLE / "tasks" / "reconcile_domain_connector_prerequisites.yml"


def _tasks(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_domain_reconciliation_uses_csrf_and_requires_canonical_inclusion():
    discover = (ROLE / "tasks" / "discover_endpoint.yml").read_text(encoding="utf-8")
    reconcile = RECONCILE.read_text(encoding="utf-8")
    assert "X-Csrf-Token" in discover
    assert "union(aipod.dns_servers)" in reconcile
    assert "union(aipod.ntp_servers)" in reconcile
    assert "re-authenticate after UCS-X connector restart" in reconcile
    assert "ucs_domain_relogin.x_csrf_token" in reconcile


def test_standalone_prerequisites_remain_read_only():
    tasks = _tasks(ROLE / "tasks" / "validate_standalone_connector_prerequisites.yml")
    assert all(task.get("ansible.builtin.uri", {}).get("method", "GET") == "GET" for task in tasks)


def test_reclaim_is_a_separate_explicit_entrypoint():
    reclaim = _tasks(PLAYBOOKS / "reclaim_mgmt_nodes_intersight.yml")
    text = (PLAYBOOKS / "reclaim_mgmt_nodes_intersight.yml").read_text(encoding="utf-8")
    assert reclaim[0]["name"].lower().startswith("subsystem 05 - explicitly")
    assert "tasks_from: reclaim" in text
    assert "ucs_intersight_allow_reclaim" in (
        ROLE / "tasks" / "reclaim.yml"
    ).read_text(encoding="utf-8")


def test_domain_endpoints_are_deduplicated_by_claim_target():
    text = (ROLE / "tasks" / "build_target.yml").read_text(encoding="utf-8")
    assert "hostvars[ucs_inventory_host].ucs.claim_target" in text
    assert "ucs_claim_targets.get(hostvars[ucs_inventory_host].ucs.claim_target" in text
    assert "'endpoints':" in text


def test_normal_path_rejects_account_mismatch_and_never_unclaims():
    text = (ROLE / "tasks" / "process_target.yml").read_text(encoding="utf-8")
    assert "ownership_account == intersight_account_name" in text
    normal_text = (ROLE / "tasks" / "intersight_claim.yml").read_text(encoding="utf-8")
    assert "state: absent" not in normal_text


def test_connector_readiness_is_required_before_claim():
    text = (ROLE / "tasks" / "process_target.yml").read_text(encoding="utf-8")
    assert "map(attribute='admin_state')" in text
    assert "map(attribute='connection_state') | map('lower')" in text
    assert "unique | list == ['connected']" in text


def test_claim_code_is_runtime_only_and_has_minimum_lifetime():
    discover = (ROLE / "tasks" / "discover_endpoint.yml").read_text(encoding="utf-8")
    process = (ROLE / "tasks" / "process_target.yml").read_text(encoding="utf-8")
    defaults = yaml.safe_load((ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
    assert "ucs_connector_token.Duration" in discover
    assert "claim_code_duration" in process
    assert defaults["ucs_claim_code_minimum_duration_seconds"] == 60
    for path in (REPO / "inventories").glob("**/host_vars/*.yml"):
        inventory_text = path.read_text(encoding="utf-8").lower()
        assert "claim_code" not in inventory_text
        assert "device_id" not in inventory_text


def test_connector_poll_accepts_platform_unclaimed_alias():
    defaults = yaml.safe_load((ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
    poll = (ROLE / "tasks" / "poll_connector.yml").read_text(encoding="utf-8")
    assert (
        defaults["ucs_connector_poll_retries"]
        * defaults["ucs_connector_poll_delay_seconds"]
        >= 600
    )
    assert "not claimed" in poll
    assert "ucs_poll_expected_state == 'unclaimed'" in poll


def test_standalone_discovery_uses_temporary_redfish_session():
    discover = (ROLE / "tasks" / "discover_endpoint.yml").read_text(encoding="utf-8")
    assert "/redfish/v1/SessionService/Sessions" in discover
    assert "method: DELETE" in discover
    assert "when: ucs_claim_target.platform == 'standalone'" in discover
