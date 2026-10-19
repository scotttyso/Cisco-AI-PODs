"""Safety checks for the SG2-only Nexus Dashboard software upgrade."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import requests
import yaml


ROOT = Path(__file__).resolve().parents[1]


def _upload_module():
    path = ROOT / "scripts" / "sg2_nd_upload.py"
    spec = importlib.util.spec_from_file_location("sg2_nd_upload", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _paired_module():
    path = ROOT / "scripts" / "sg2_nd_paired_upgrade.py"
    spec = importlib.util.spec_from_file_location("sg2_nd_paired_upgrade", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upload_is_exact_pinned_sg2_image() -> None:
    upload = _upload_module()
    assert upload.IMAGE_NAME == "nxos64-s1.10.6.4.M.bin"
    assert upload.IMAGE_SIZE == 3_430_233_088
    assert len(upload.IMAGE_SHA512) == 128


def test_upload_cloud_scale_image_has_independent_cisco_pin() -> None:
    upload = _upload_module()
    upload.select_profile("cs")
    assert upload.IMAGE_NAME == "nxos64-cs.10.6.4.M.bin"
    assert upload.IMAGE_SIZE == 2_962_740_224
    assert upload.IMAGE_SHA512 == (
        "4ae1475c454918798679016c25e65fdca9205d310888efb80ddde9bf2cf94c98"
        "0822f49f44c9d3c85c50eb9ca1b475695689cd41fa54e0cde0c826d6bb707223"
    )


def test_multipart_upload_has_known_length_and_no_chunked_framing(
    tmp_path: Path, monkeypatch,
) -> None:
    upload = _upload_module()
    monkeypatch.setattr(upload, "IMAGE_SIZE", 3)
    image = tmp_path / upload.IMAGE_NAME
    image.write_bytes(b"abc")
    body = upload.MultipartStream(image)
    try:
        prepared = requests.Request(
            "POST", "https://example.invalid/images", data=body,
            headers={"Content-Type": body.content_type},
        ).prepare()
        assert prepared.headers["Content-Length"] == str(len(body))
        assert "Transfer-Encoding" not in prepared.headers
        raw = b"".join(iter(lambda: body.read(2), b""))
        assert raw.count(b"abc") == 1
        assert raw.endswith(b"--\r\n")
        assert len(raw) == len(body)
    finally:
        body.close()


def test_upgrade_playbook_is_sg2_scoped_and_pause_on_failure() -> None:
    document = yaml.safe_load((ROOT / "playbooks" / "03_sg2_software_upgrade.yml").read_text())
    assert len(document) == 1
    play = document[0]
    assert play["force_handlers"] is True
    assert play["vars"]["nd_upgrade_fabric"] == "AIPOD-BE-SG2-Fabric"
    assert play["vars"]["nd_upgrade_phase"] == "plan"
    create = next(task for task in play["tasks"] if task["name"].startswith("Create a serial"))
    group = create["ansible.builtin.uri"]["body"]["updateGroups"][0]
    assert group["execution"] == "serial"
    assert group["contingency"] == "pause"
    assert group["isDisruptiveUpdate"] is True
    assert group["installImageData"]["nosImageName"] == "{{ nd_upgrade_image_name }}"
    assert all(
        task.get("no_log") is True
        for task in play["tasks"]
        if task.get("ansible.builtin.uri", {}).get("method") == "POST"
    )


def test_future_pair_waves_have_one_spine_and_one_leaf_each() -> None:
    paired = _paired_module()
    assert paired.WAVES == (
        ("BE-SG2-SP1", "BE-SG2-LF1"),
        ("BE-SG2-SP2", "BE-SG2-LF2"),
    )
    assert {name for wave in paired.WAVES for name in wave} == set(paired.ROLES)
    assert all({paired.ROLES[name] for name in wave} == {"spine", "leaf"}
               for wave in paired.WAVES)


def test_cloud_scale_profile_is_separate_and_exactly_paired() -> None:
    paired = _paired_module()
    paired.select_profile("cs")
    assert paired.FABRIC == "AIPOD-BE-Fabric"
    assert paired.IMAGE == "nxos64-cs.10.6.4.M.bin"
    assert paired.IMAGE_SIZE == 2_962_740_224
    assert paired.WAVES == (("BE-SP1", "BE-LF1"), ("BE-SP2", "BE-LF2"))
    assert paired.GROUPS == ("Update-Pair-Left", "Update-Pair-Right")
    assert paired.PAIR_LABELS == ("Update-Pair-Left", "Update-Pair-Right")
    assert all({paired.ROLES[name] for name in wave} == {"spine", "leaf"}
               for wave in paired.WAVES)
    assert set(paired.MODELS.values()) == {"N9K-C9364D-GX2A", "N9K-C9332D-GX2B"}
    assert all("SG2" not in group for group in paired.GROUPS)


def test_primary_underlay_gate_requires_both_remotes_and_established_peers() -> None:
    import pytest

    paired = _paired_module()
    lldp = "\n".join(["Eth1/1 BE-LF1 Eth1/1"] * 2 +
                     ["Eth1/2 BE-LF2 Eth1/2"] * 2)
    bgp = "\n".join(f"20.0.0.{i} 4 6510{i} 0 0 0 0 00:01:00 12"
                    for i in range(1, 5))
    assert paired.primary_underlay_counts("BE-SP1", lldp, bgp) == (4, 4)
    with pytest.raises(RuntimeError, match="BE-SP1"):
        paired.primary_underlay_counts("BE-SP1", lldp.replace("BE-LF2", "BE-LF1"), bgp)
    with pytest.raises(RuntimeError, match="BE-SP1"):
        paired.primary_underlay_counts("BE-SP1", lldp, bgp.replace(" 12", " Idle", 1))


def test_future_pair_groups_are_parallel_pause_and_exactly_two() -> None:
    paired = _paired_module()
    inventory = {
        name: {"serialNumber": f"test-id-{i}"}
        for i, name in enumerate(paired.ROLES)
    }

    class FakeNd:
        created = []

        def groups(self):
            return self.created

        def request(self, method, path, *, payload, accepted):
            assert method == "POST" and path.endswith("/updateGroups")
            self.created = payload["updateGroups"]
            return {}

    fake = FakeNd()
    paired.ensure_groups(fake, inventory)
    assert len(fake.created) == 2
    assert all(len(group["updateGroupSwitches"]) == 2 and
               group["execution"] == "parallel" and
               group["contingency"] == "pause" and
               group["isDisruptiveUpdate"] is True
               for group in fake.created)


def test_groups_phase_creates_only_missing_records_without_staging() -> None:
    paired = _paired_module()
    inventory = {
        name: {"serialNumber": f"test-id-{i}", "status": "ok"}
        for i, name in enumerate(paired.ROLES)
    }

    class FakeNd:
        created = []
        writes = []

        def request(self, method, path, *, payload=None, accepted=(200,)):
            if method == "GET" and path.endswith("/images"):
                return {"uploadedImages": [{"imageName": paired.IMAGE,
                                            "imagePresent": "present",
                                            "imageSize": paired.IMAGE_SIZE}]}
            assert method == "POST" and path.endswith("/updateGroups")
            self.writes.append(path)
            self.created = payload["updateGroups"]
            return {}

        def inventory(self, *, healthy):
            return inventory

        def groups(self):
            return self.created

        def plan(self):
            return [
                {"updateGroupName": group["updateGroupName"],
                 "updateGroupStatus": "ready",
                 "updateGroupSwitches": [
                     {"switchName": name, "switchUpdateStatus": "none"}
                     for name in paired.WAVES[index]
                 ]}
                for index, group in enumerate(self.created)
            ]

    fake = FakeNd()
    paired.run(fake, "groups", {})
    paired.run(fake, "groups", {})
    assert len(fake.created) == 2
    assert fake.writes == [f"/api/v1/manage/fabrics/{paired.FABRIC}/updateGroups"]


def test_future_pair_refuses_partial_or_failed_install() -> None:
    import pytest

    paired = _paired_module()
    status = lambda value: {"switchUpdateStatus": value}
    assert paired.wave_action([status("none"), status("none")]) == "start"
    assert paired.wave_action([status("inProgress"), status("none")]) == "observe"
    assert paired.wave_action([status("success"), status("success")]) == "done"
    with pytest.raises(RuntimeError, match="Partial"):
        paired.wave_action([status("success"), status("none")])
    with pytest.raises(RuntimeError, match="failed"):
        paired.wave_action([status("failed"), status("none")])


def test_future_pair_requires_all_four_image_validations_before_install() -> None:
    import pytest

    paired = _paired_module()
    groups = [
        {"updateGroupSwitches": [{"imageValidatedStatus": "success"},
                                 {"imageValidatedStatus": "success"}]},
        {"updateGroupSwitches": [{"imageValidatedStatus": "success"},
                                 {"imageValidatedStatus": "none"}]},
    ]
    with pytest.raises(RuntimeError, match="All four"):
        paired.require_all_validated(groups)
    groups[1]["updateGroupSwitches"][1]["imageValidatedStatus"] = "success"
    paired.require_all_validated(groups)


def test_cloud_scale_rehearsal_is_no_install_when_target_is_already_present(
    monkeypatch, capsys,
) -> None:
    paired = _paired_module()
    paired.select_profile("cs")
    monkeypatch.setattr(paired, "require_image", lambda _nd: None)
    names = paired.GROUPS
    plan = [
        {"updateGroupName": group_name, "updateGroupStatus": "ready",
         "updateGroupSwitches": [
             {"switchName": switch, "switchUpdateStatus": "none",
              "imageValidatedStatus": "success", "switchVersion": paired.TARGET_VERSION}
             for switch in wave
         ]}
        for group_name, wave in zip(names, paired.WAVES)
    ]

    class FakeNd:
        install_actions = []

        def inventory(self, *, healthy):
            assert healthy is False or healthy is True
            return {}

        def plan(self):
            return plan

        def action(self, action, group_names):
            self.install_actions.append((action, group_names))

    fake = FakeNd()
    paired.run(fake, "rehearsal", {})
    assert fake.install_actions == []
    assert "no install requested" in capsys.readouterr().out


def test_cloud_scale_install_phase_skips_nd_action_if_target_is_already_present(
    monkeypatch, capsys,
) -> None:
    paired = _paired_module()
    paired.select_profile("cs")
    monkeypatch.setattr(paired, "require_image", lambda _nd: None)
    snapshots = {
        name: {"version": paired.TARGET_VERSION,
               "uptime": "3 day(s), 4 hour(s), 5 minute(s)",
               "lastReset": "2026-09-20 10:11:12"}
        for wave in paired.WAVES for name in wave
    }
    monkeypatch.setattr(
        paired, "read_switch_snapshots",
        lambda _vault, names: {name: snapshots[name] for name in names},
    )
    plan = [
        {"updateGroupName": group_name, "updateGroupStatus": "none",
         "updateGroupSwitches": [
             {"switchName": switch, "switchUpdateStatus": "none",
              "imageValidatedStatus": "none", "switchVersion": paired.TARGET_VERSION}
             for switch in wave
         ]}
        for group_name, wave in zip(paired.GROUPS, paired.WAVES)
    ]

    class FakeNd:
        def __init__(self):
            self.actions = []

        def inventory(self, *, healthy):
            assert healthy in (False, True)
            return {}

        def plan(self):
            return plan

        def action(self, action, group_names):
            self.actions.append((action, group_names))

    fake = FakeNd()
    paired.run(fake, "install", {})
    assert fake.actions == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["outcome"] == "already_at_target"
    assert payload["headline"] == (
        "All switches at target release: No upgrade or reboot required"
    )


def test_explicit_same_version_experiment_only_requests_left_group(monkeypatch, capsys) -> None:
    paired = _paired_module()
    paired.select_profile("cs")
    monkeypatch.setattr(paired, "require_image", lambda _nd: None)
    snapshots = {
        name: {"version": paired.TARGET_VERSION,
               "uptime": "3 day(s), 4 hour(s), 5 minute(s)",
               "lastReset": "2026-09-20 10:11:12"}
        for wave in paired.WAVES for name in wave
    }
    mock_snapshots = lambda _vault, names: {name: snapshots[name] for name in names}
    monkeypatch.setattr(paired, "read_switch_snapshots", mock_snapshots)
    monkeypatch.setattr(paired, "wait_for_switch_snapshots", mock_snapshots)
    monkeypatch.setattr(paired, "wait_for", lambda nd, index, field, **kwargs:
                        nd.plan()[index]["updateGroupSwitches"])
    monkeypatch.setattr(paired, "wait_inventory", lambda _nd, limit=900: None)
    plan = [
        {"updateGroupName": name, "updateGroupStatus": "none",
         "updateGroupSwitches": [
             {"switchName": switch, "switchUpdateStatus": "none",
              "imageValidatedStatus": "success", "switchVersion": paired.TARGET_VERSION}
             for switch in wave
         ]}
        for name, wave in zip(paired.GROUPS, paired.WAVES)
    ]

    class FakeNd:
        def __init__(self):
            self.actions = []

        def inventory(self, *, healthy):
            return {}

        def plan(self):
            return plan

        def action(self, action, group_names):
            self.actions.append((action, group_names))
            for group in plan:
                if group["updateGroupName"] in group_names:
                    group["updateGroupStatus"] = "success"
                    for switch in group["updateGroupSwitches"]:
                        switch["switchUpdateStatus"] = "success"

    fake = FakeNd()
    paired.run(fake, "install-left", {})
    assert fake.actions == [("updateSoftware", [paired.GROUPS[0]])]
    captured = capsys.readouterr().out
    payload = json.loads(captured.splitlines()[-1])
    assert payload["outcome"] == "already_at_target"
    assert payload["ndStatus"] == "success"


def test_explicit_left_stage_only_stages_left_group(monkeypatch, capsys) -> None:
    paired = _paired_module()
    paired.select_profile("cs")
    monkeypatch.setattr(paired, "require_image", lambda _nd: None)
    monkeypatch.setattr(paired, "ensure_groups", lambda _nd, _inventory: None)
    monkeypatch.setattr(paired, "wait_for", lambda nd, index, field, **kwargs:
                        nd.plan()[index]["updateGroupSwitches"])
    plan = [
        {"updateGroupName": name, "updateGroupStatus": "none",
         "updateGroupSwitches": [
             {"switchName": switch, "switchUpdateStatus": "none",
              "imageStagedStatus": "none", "imageValidatedStatus": "none"}
             for switch in wave
         ]}
        for name, wave in zip(paired.GROUPS, paired.WAVES)
    ]

    class FakeNd:
        def __init__(self):
            self.actions = []

        def inventory(self, *, healthy):
            return {}

        def plan(self):
            return plan

        def action(self, action, names):
            self.actions.append((action, names))

    fake = FakeNd()
    paired.run(fake, "stage-left", {})
    assert fake.actions == [("stage", [paired.GROUPS[0]])]
    assert "right pair untouched" in capsys.readouterr().out


def test_future_pair_refuses_to_overlap_active_serial_group() -> None:
    import pytest

    paired = _paired_module()

    class FakeNd:
        def plan(self):
            return [{"updateGroupName": "AIPOD-SG2-1064M",
                     "updateGroupSwitches": [{"switchUpdateStatus": "inProgress"}]}]

    with pytest.raises(RuntimeError, match="Another install in this fabric"):
        paired.check_plan(FakeNd())


def test_install_observation_retries_only_transient_controller_reads(monkeypatch) -> None:
    paired = _paired_module()
    calls = []

    class FakeNd:
        def plan(self):
            calls.append("read")
            if len(calls) == 1:
                raise RuntimeError("ND GET returned HTTP 503; response body suppressed")
            return [
                {"updateGroupName": name, "updateGroupStatus": "success",
                 "updateGroupSwitches": [
                     {"switchName": switch, "switchUpdateStatus": "success"}
                     for switch in paired.WAVES[index]
                 ]}
                for index, name in enumerate(paired.GROUPS)
            ]

    monkeypatch.setattr(paired.time, "sleep", lambda _: None)
    result = paired.wait_for(FakeNd(), 0, "switchUpdateStatus", interval=1, limit=60)
    assert len(result) == 2
    assert calls == ["read", "read"]
    assert not paired.transient_read_error(RuntimeError("ND POST outcome ambiguous"))
