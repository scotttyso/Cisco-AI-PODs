"""Canonical Ansible inventory tests for subsystem 02."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[3]
INVENTORY = REPO / "inventories/example/inventory.yml"
SCHEMA = REPO / "schemas/backend-fabric-nxos.schema.json"
ANSIBLE_INVENTORY = Path("/usr/bin/ansible-inventory")


def _payload() -> dict:
    completed = subprocess.run(
        [str(ANSIBLE_INVENTORY), "-i", str(INVENTORY), "--list"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _instance(payload: dict) -> dict:
    hostvars = payload["_meta"]["hostvars"]
    hosts: list[str] = []
    for child in payload["backend_fabric_switches"]["children"]:
        hosts.extend(payload[child]["hosts"])
    first = hostvars[hosts[0]]
    return {
        "fabrics": first["be_fabrics"],
        "features": first["be_fabric_features"],
        "switches": [
            {"inventory_host": host, **hostvars[host]["be_switch"]}
            for host in hosts
        ],
    }


def test_backend_inventory_matches_strict_schema() -> None:
    from shared.lib.inventory import _validate_schema_instance

    _validate_schema_instance(_instance(_payload()), SCHEMA)


def test_two_fabrics_have_unique_names_asns_and_complete_roles() -> None:
    instance = _instance(_payload())
    fabrics = instance["fabrics"]
    assert len(fabrics) == 2
    assert len({item["key"] for item in fabrics}) == 2
    assert len({item["name"] for item in fabrics}) == 2
    assert len({item["bgp_as"] for item in fabrics}) == 2

    for fabric in fabrics:
        switches = [
            item for item in instance["switches"]
            if item["fabric_key"] == fabric["key"]
        ]
        assert [item["role"] for item in switches].count("spine") == 2
        assert [item["role"] for item in switches].count("leaf") == 2


def test_backend_fabric_enables_telemetry_in_dedicated_vrf() -> None:
    instance = _instance(_payload())
    assert instance["features"]["enable_telemetry"] is True
    assert instance["features"]["telemetry_collection_mode"] == "in_band"
    assert instance["features"]["telemetry_streaming_protocol"] == "ipv4"
    assert instance["features"]["telemetry_vrf"] == "Telemetry_VRF"
    assert instance["features"]["telemetry_source_interface"] == "loopback0"

    task_file = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/tasks/build_fabric_config.yml"
    )
    text = task_file.read_text(encoding="utf-8")
    assert "ALLOW_NXC" not in text
    assert "OVERWRITE_GLOBAL_NXC" not in text
    assert "NXC_DEST_VRF" not in text

    manage_file = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/tasks/reconcile_license.yml"
    ).read_text(encoding="utf-8")
    assert "'telemetryCollection': be_fabric_features.enable_telemetry" in manage_file
    assert "'telemetryCollectionType':" in manage_file
    assert "'telemetrySourceVrf': be_fabric_features.telemetry_vrf" in manage_file
    assert (
        "'telemetrySourceInterface': be_fabric_features.telemetry_source_interface"
        in manage_file
    )
    assert (
        "'telemetryStreamingProtocol': be_fabric_features.telemetry_streaming_protocol"
        in manage_file
    )


def test_backend_fabric_supplies_core_ebgp_create_fields() -> None:
    features = _instance(_payload())["features"]
    assert features["bgp_as_mode"] == "Multi-AS"
    assert features["enable_evpn"] is True
    assert features["fabric_mtu"] == 9216
    assert features["link_state_routing"] == "ebgp"

    task_file = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/tasks/build_fabric_config.yml"
    )
    text = task_file.read_text(encoding="utf-8")
    assert "'BGP_AS_MODE': be_fabric_features.bgp_as_mode" in text
    assert "'ENABLE_EVPN': be_fabric_features.enable_evpn" in text
    assert "'FABRIC_MTU': be_fabric_features.fabric_mtu" in text
    assert "'LINK_STATE_ROUTING': be_fabric_features.link_state_routing" in text
    assert "be_fabric_create_configs" in text
    assert "'DEPLOY': false" in text


def test_backend_fabric_supplies_required_ptp_companion_fields() -> None:
    features = _instance(_payload())["features"]
    assert features["ptp"] is True
    assert features["ptp_source_loopback_id"] == 0
    assert features["ptp_domain_id"] == 0

    task_file = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/tasks/build_fabric_config.yml"
    )
    text = task_file.read_text(encoding="utf-8")
    assert "'FEATURE_PTP_INTERNAL': (" in text
    assert "be_fabric.ptp | default(be_fabric_features.ptp)" in text
    assert "'PTP_LB_ID': (" in text
    assert "be_fabric_features.ptp_source_loopback_id" in text
    assert "'PTP_DOMAIN_ID': (" in text
    assert "be_fabric_features.ptp_domain_id" in text
    assert "else ''" in text


def test_backend_fabric_stages_core_create_before_full_reconcile() -> None:
    main_file = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/tasks/main.yml"
    ).read_text(encoding="utf-8")
    core = main_file.index("create both fabrics with the proven core payload")
    topology = main_file.index("reconcile topology and fabric behavior selectively")
    secret = main_file.index("reconcile robot password in an isolated secret stage")
    assert core < topology < secret
    assert 'config: "{{ be_fabric_create_configs }}"' in main_file
    assert "be_fabric_topology_configs" in main_file
    assert "be_fabric_robot_password_configs" in main_file

    stage_file = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/tasks/reconcile_fabric_stage.yml"
    ).read_text(encoding="utf-8")
    assert 'config: "{{ be_reconcile_stage.configs }}"' in stage_file


def test_backend_fabrics_pass_through_optional_inventory_location() -> None:
    fabrics = _instance(_payload())["fabrics"]
    assert all(
        fabric["location"] == {
            "name": "Example City, US",
            "latitude": 0,
            "longitude": 0,
        }
        for fabric in fabrics
    )

    task_file = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/tasks/reconcile_license.yml"
    )
    text = task_file.read_text(encoding="utf-8")
    assert '"location": be_fabric.location' in text
    assert "be_fabric.location is defined" in text
    assert "be_fabric.location.latitude" in text and "be_fabric.location.longitude" in text


def test_backend_fabric_uses_vault_backed_robot_password() -> None:
    instance = _instance(_payload())
    features = instance["features"]
    assert features["use_robot_password"] is True
    assert features["switch_password_ref"] == "EXAMPLE_BE_FABRIC_SWITCH_PASSWORD"

    task_file = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/tasks/build_fabric_config.yml"
    )
    text = task_file.read_text(encoding="utf-8")
    assert "'designerUseRobotPassword': be_fabric_features.use_robot_password" in text
    assert "be_fabric_features.switch_password_ref | lower" in text
    assert "vault_nd_admin_password" not in text


def test_switch_addresses_and_vault_refs_are_unique() -> None:
    switches = _instance(_payload())["switches"]
    assert len({item["mgmt_ip"] for item in switches}) == len(switches)
    assert len({item["hostname"] for item in switches}) == len(switches)
    assert len({item["pass_ref"] for item in switches}) == len(switches)


def test_backend_800g_uses_supported_ingress_replication() -> None:
    fabrics = {item["key"]: item for item in _instance(_payload())["fabrics"]}
    assert fabrics["backend_800g"]["replication_mode"] == "Ingress"
    assert fabrics["backend_800g"]["ptp"] is False


def test_backend_800g_switches_define_idempotent_2x400g_breakout() -> None:
    switches = _instance(_payload())["switches"]
    backend_800g = [item for item in switches if item["fabric_key"] == "backend_800g"]
    assert len(backend_800g) == 4
    assert all(item["breakout_commands"] for item in backend_800g)
    assert all(
        command.endswith("map 400g-2x")
        for item in backend_800g
        for command in item["breakout_commands"]
    )

    access_tasks = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/tasks/configure_switch_access.yml"
    ).read_text(encoding="utf-8")
    assert "read configured port breakout mode" in access_tasks
    assert "apply missing 2x400G breakout ranges" in access_tasks
    assert "require every intended 2x400G breakout range" in access_tasks
    assert "administratively enable authoritative fabric lanes" in access_tasks
    assert "require every authoritative fabric lane to be admin-up" in access_tasks
    assert "save_when: modified" in access_tasks

    expected_lane_count = {
        "EXAMPLE-BE-800G-SPINE-1": 8,
        "EXAMPLE-BE-800G-SPINE-2": 8,
        "EXAMPLE-BE-800G-LEAF-1": 8,
        "EXAMPLE-BE-800G-LEAF-2": 8,
    }
    assert {
        item["hostname"]: len(item["fabric_link_interfaces"])
        for item in backend_800g
    } == expected_lane_count


@pytest.mark.parametrize("field", ["fabric_key", "hostname", "role", "mgmt_ip", "username", "pass_ref"])
def test_switch_required_fields_are_not_empty(field: str) -> None:
    switches = _instance(_payload())["switches"]
    assert all(item[field] not in (None, "") for item in switches)


def test_switch_onboarding_uses_sha_authentication() -> None:
    task_file = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/tasks/onboard_fabric.yml"
    )
    text = task_file.read_text(encoding="utf-8")
    assert "'auth_proto': 'SHA_AES'" in text
    assert "'auth_proto': 'MD5'" not in text


def test_backend_switches_prepare_sha_aes_before_ndfc_onboarding() -> None:
    playbook = (
        REPO
        / "02-backend-fabric-nxos/automation/playbooks/02_backend_fabric.yml"
    ).read_text()
    access_tasks = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/tasks/configure_switch_access.yml"
    ).read_text()

    assert "hosts: backend_fabric_switches" in playbook
    assert "tasks_from: configure_switch_access.yml" in playbook
    assert "cisco.nxos.nxos_config" in access_tasks
    assert "auth sha" in access_tasks
    assert "priv aes-128" in access_tasks
    assert "save_when: modified" in access_tasks
    assert "show snmp user | include ^{{ be_switch.username }}" in access_tasks
    assert "no_log: true" in access_tasks


def test_greenfield_cleanup_is_guarded_to_first_import() -> None:
    onboarding = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/tasks/onboard_fabric.yml"
    ).read_text()

    assert "'preserve_config': false" in onboarding
    assert "be_existing_switches_before" in onboarding
    assert "be_first_import_switch_configs" in onboarding
    assert "config: \"{{ be_first_import_switch_configs }}\"" in onboarding
    assert "when: be_first_import_switch_configs | length > 0" in onboarding
    assert "Existing members will not receive preserve_config=false again" in onboarding


def test_add_without_reload_transitions_only_after_initial_formation() -> None:
    role_root = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/tasks"
    )
    onboarding = (role_root / "onboard_fabric.yml").read_text()
    lifecycle = (role_root / "reconcile_add_without_reload.yml").read_text()
    build_config = (role_root / "build_fabric_config.yml").read_text()

    disable = onboarding.index("require reload cleanup during initial formation")
    onboard = onboarding.index("use the collection-native first-import path")
    verify = onboarding.index("wait for cleanup reload and complete intended membership")
    enable = onboarding.index("enable no-reload additions after successful formation")

    assert disable < onboard < verify < enable
    assert "be_add_without_reload_enabled: false" in onboarding
    assert "be_fabric_features.add_switches_without_reload" in onboarding
    assert "rejectattr('status', 'equalto', 'ok')" in onboarding
    assert "selectattr('managable', 'equalto', true)" in onboarding
    assert "difference(['normal'])" in onboarding
    assert "retries: 60" in onboarding
    assert "delay: 30" in onboarding
    assert "GRFIELD_DEBUG_FLAG" in lifecycle
    assert "method: PUT" in lifecycle
    assert "read back add-switch lifecycle state" in lifecycle
    assert "require requested add-switch lifecycle state" in lifecycle
    assert "GRFIELD_DEBUG_FLAG" not in build_config


def test_backend_onboarding_recovers_from_legacy_role_api_failure() -> None:
    role_root = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/tasks"
    )
    onboarding = (role_root / "onboard_fabric.yml").read_text()
    role_reconcile = (role_root / "reconcile_switch_roles.yml").read_text()
    save_deploy = (role_root / "save_deploy_fabric.yml").read_text()

    assert "rescue:" in onboarding
    assert "reconcile_switch_roles.yml" in onboarding
    assert "save and deploy after role reconciliation" in onboarding
    assert "save_deploy_fabric.yml" in onboarding
    assert "/api/v1/manage/inventory/switchActions/changeRoles" in role_reconcile
    assert "switchRoles:" in role_reconcile
    assert "refusing partial role reconciliation" in role_reconcile
    assert "status_code:" in role_reconcile
    assert "- 207" in role_reconcile
    assert "no_log: true" in role_reconcile
    assert "/config-save" in save_deploy
    assert "/config-deploy/" in save_deploy
    assert "forceShowRun=false" in save_deploy
    assert "be_imported_switches.json" in save_deploy
    assert "no_log: true" in save_deploy


def test_per_fabric_replication_mode_overrides_live_default() -> None:
    role_root = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/tasks"
    )
    build_config = (
        role_root / "build_fabric_config.yml"
    ).read_text()
    main = (role_root / "main.yml").read_text()
    reconcile = (role_root / "reconcile_fabric_topology.yml").read_text()
    assert "'REPLICATION_MODE'" in build_config
    assert "be_fabric.replication_mode" in build_config
    assert "default(be_template_defaults.REPLICATION_MODE)" in build_config
    assert "be_fabric.ptp | default(be_fabric_features.ptp)" in build_config
    assert "reconcile_fabric_topology.yml" in main
    assert "reconcile post-create settings in isolated stages" not in main
    assert "method: PUT" in reconcile
    assert "collect_topology_update.yml" in reconcile
    assert "collect_topology_mismatch.yml" in reconcile
    assert "be_topology_updates | length > 3" in reconcile
    assert "no_log: true" in reconcile


def test_backend_fabrics_can_be_targeted_independently() -> None:
    defaults_file = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/defaults/main.yml"
    )
    main_file = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/tasks/main.yml"
    )
    defaults = defaults_file.read_text(encoding="utf-8")
    main = main_file.read_text(encoding="utf-8")

    assert "be_target_fabric_keys:" in defaults
    assert "be_active_fabrics" in main
    assert "loop: \"{{ be_active_fabrics }}\"" in main
    assert (
        "hostvars[be_switch_host].be_switch.fabric_key "
        "in be_target_fabric_keys"
    ) in main


def test_backend_play_sets_dcnm_inventory_timeouts() -> None:
    playbook = (
        REPO
        / "02-backend-fabric-nxos/automation/playbooks/02_backend_fabric.yml"
    ).read_text(encoding="utf-8")
    assert "ansible_command_timeout: 1000" in playbook
    assert "ansible_connect_timeout: 1000" in playbook

    reconcile_license = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/tasks/reconcile_license.yml"
    ).read_text(encoding="utf-8")
    defaults = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/defaults/main.yml"
    ).read_text(encoding="utf-8")
    assert "be_fabric_ready_poll_interval: 30" in defaults
    assert "be_fabric_ready_poll_retries: 20" in defaults
    assert "be_manage_update_request_timeout: 120" in defaults
    assert "be_manage_update_observe_interval: 30" in defaults
    assert "be_manage_update_observe_retries: 20" in defaults
    assert "wait for preceding NDFC work" in reconcile_license
    assert "be_fabric_ready.json.operStatus" in reconcile_license
    assert "== 'HEALTHY'" in reconcile_license
    assert 'timeout: "{{ be_manage_update_request_timeout }}"' in reconcile_license
    assert "observe timed-out Manage update" in reconcile_license
    assert "method: GET" in reconcile_license
    assert "be_manage_observed.json | default({}) == be_desired_fabric_body" in reconcile_license
    assert reconcile_license.count("method: PUT") == 1


def test_backend_direct_rest_uses_ephemeral_nd_session() -> None:
    main_file = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/tasks/main.yml"
    ).read_text(encoding="utf-8")
    license_file = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/tasks/reconcile_license.yml"
    ).read_text(encoding="utf-8")

    assert "/api/v1/infra/login" in main_file
    assert "vault_nd_admin_password" in main_file
    assert "be_platform_login.cookies_string" in main_file
    assert "/api/v1/infra/systemSoftware/services" in main_file
    assert "deploymentState.deploymentStatus.status" in main_file
    assert "operState.state" in main_file
    assert 'headers: "{{ be_platform_headers }}"' in main_file
    assert 'headers: "{{ be_platform_headers }}"' in license_file
    assert "X-Nd-Apikey" not in main_file
    assert "X-Nd-Apikey" not in license_file


def test_backend_secret_bearing_include_loops_are_suppressed() -> None:
    main_file = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/tasks/main.yml"
    ).read_text(encoding="utf-8")
    license_file = (
        REPO
        / "02-backend-fabric-nxos/automation/roles/backend_fabric_nxos/tasks/reconcile_license.yml"
    ).read_text(encoding="utf-8")

    existing_block = main_file.split(
        '- name: "BE fabric: collect existing fabric identities"', 1
    )[1].split('- name: "BE fabric: preflight desired fabric identities"', 1)[0]
    reconcile_block = main_file.split(
        '- name: "BE fabric: reconcile robot password in an isolated secret stage"', 1
    )[1].split('- name: "BE fabric: reconcile and verify Premier license tier"', 1)[0]
    pools_block = license_file.split(
        '- name: "BE fabric: derive every live 10.* management pool', 1
    )[1].split('- name: "BE fabric: build complete desired Manage record', 1)[0]

    assert "no_log: true" in existing_block
    assert "no_log: true" in reconcile_block
    assert "no_log: true" in pools_block
