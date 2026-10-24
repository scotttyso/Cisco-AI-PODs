from pathlib import Path
import sys
from unittest.mock import MagicMock, Mock

import pytest
import requests
import yaml


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "05-mgmt-nodes-ucs/automation/scripts"))
import check_intersight_domain_ports as ports


def test_targets_include_uploads_but_not_system_or_servers(tmp_path):
    model = {"intersight": {"configure": {"Org": {"profiles": {
        "domain": [{"name": "Domain", "serial_numbers": ["SERIAL-A", "SERIAL-B"]}],
        "server": [{"name": "Server", "serial_number": "SERVER"}],
    }}}}}
    domains = tmp_path / "domains"
    uploads = domains / "uploads"
    uploads.mkdir(parents=True)
    (uploads / "domain.ezai.yaml").write_text(yaml.safe_dump(model))
    (tmp_path / "system.ezai.yaml").write_text("invalid: [")
    assert ports.domain_targets(domains) == {"SERIAL-A": "Org/Domain", "SERIAL-B": "Org/Domain"}
    with pytest.raises(ValueError, match="No domain profile"):
        ports.domain_targets(tmp_path / "absent")


def test_query_paginates_and_rejects_invalid_response():
    client = Mock()
    client.get.side_effect = [
        Mock(json=lambda: {"Results": [{"Moid": "port"}] * 1000}),
        Mock(json=lambda: {"Results": [{"Moid": "last"}]}),
    ]
    assert len(ports.query(client, "https://intersight.com", "ether/PhysicalPorts", "test")) == 1001
    assert client.get.call_args.kwargs["params"]["$skip"] == 1000
    client.get.side_effect = None
    client.get.return_value = Mock(json=lambda: {})
    with pytest.raises(ValueError, match="Results list"):
        ports.query(client, "https://intersight.com", "ether/PhysicalPorts", "test")
    client.get.return_value.raise_for_status.side_effect = requests.HTTPError("403 forbidden")
    with pytest.raises(requests.HTTPError, match="403"):
        ports.query(client, "https://intersight.com", "ether/PhysicalPorts", "test")


def fake_inventory(state="up", missing=False, neighbors=True, assigned=True, roles=True):
    def query(_client, _base, endpoint, expression):
        if endpoint == "network/Elements":
            assert expression == "Serial eq 'SERIAL-A'"
            return [{"Moid": "switch-a", "SwitchId": "A"}]
        if endpoint == "fabric/SwitchProfiles":
            assert expression == "AssignedSwitch.Moid eq 'switch-a'"
            return [{"PolicyBucket": [{"ObjectType": "fabric.PortPolicy", "Moid": "policy-a"}]}] if assigned else []
        if endpoint.startswith("fabric/"):
            assert expression == "PortPolicy.Moid eq 'policy-a'"
            if roles and endpoint == "fabric/UplinkPcRoles":
                return [{"Ports": [{"SlotId": 1, "PortId": 1, "AggregatePortId": 2}]}]
            if roles and endpoint == "fabric/FcUplinkRoles":
                return [{"SlotId": 1, "PortId": 8}]
            return []
        if endpoint in ("ether/PhysicalPorts", "fc/PhysicalPorts"):
            assert expression == "Ancestors/any(t:t/Moid eq 'switch-a')"
            if missing:
                return []
            return [{"Moid": "eth-a", "SlotId": 1, "PortId": 1, "AggregatePortId": 2,
                     "OperState": state, "OperSpeed": "100Gbps"}] if endpoint.startswith("ether/") else [
                         {"Moid": "fc-a", "SlotId": 1, "PortId": 8, "OperState": "up"}]
        if endpoint == "network/DiscoveredNeighbors":
            assert expression == "PhysicalPort.Moid eq 'eth-a'"
            return [
                {"CdpNeighbor": {"Moid": "switch-a"}, "NeighborDeviceId": "Nexus-A",
                 "NeighborInterface": "Ethernet1/10", "ManagementAddress": "192.0.2.1"},
                {"LldpNeighbor": {"Moid": "switch-a"}, "NeighborDeviceId": "Nexus-A",
                 "NeighborPortId": "Ethernet1/10"},
            ] if neighbors else []
        raise AssertionError(endpoint)
    return query


@pytest.mark.parametrize("state,missing,healthy", [
    ("up", False, True), ("down", False, False), ("", False, False), ("up", True, False),
])
def test_link_states_and_breakout_members(monkeypatch, capsys, state, missing, healthy):
    monkeypatch.setattr(ports, "query", fake_inventory(state=state, missing=missing))
    assert ports.check_switch(Mock(), "https://intersight.com", "SERIAL-A", "Org/Domain") is healthy
    output = capsys.readouterr().out
    assert "ether 1/1/2" in output
    assert "fc 1/8" in output
    if not missing:
        assert "CDP: Nexus-A port Ethernet1/10" in output
        assert "LLDP: Nexus-A port Ethernet1/10" in output


@pytest.mark.parametrize("assigned,roles", [(False, True), (True, False)])
def test_missing_profile_or_uplinks_fails(monkeypatch, assigned, roles):
    monkeypatch.setattr(ports, "query", fake_inventory(assigned=assigned, roles=roles))
    with pytest.raises(ValueError):
        ports.check_switch(Mock(), "https://intersight.com", "SERIAL-A", "Org/Domain")


def test_absent_neighbors_are_explicit(monkeypatch, capsys):
    monkeypatch.setattr(ports, "query", fake_inventory(neighbors=False))
    assert ports.check_switch(Mock(), "https://intersight.com", "SERIAL-A", "Org/Domain")
    assert "link state alone cannot confirm the remote switch" in capsys.readouterr().out


def test_main_returns_failure_and_continues_other_switches(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["check", "--domains-dir", "domains"])
    monkeypatch.setattr(ports, "domain_targets", lambda _directory: {"A": "Domain", "B": "Domain"})
    monkeypatch.setattr(ports, "session", MagicMock())
    check = Mock(side_effect=[requests.HTTPError("403 forbidden"), True])
    monkeypatch.setattr(ports, "check_switch", check)
    assert ports.main() == 1
    assert check.call_count == 2
    assert "403 forbidden" in capsys.readouterr().err


def test_odata_literal_escaping():
    assert ports.quote("switch'name") == "'switch''name'"


@pytest.mark.parametrize("content", [
    "- unexpected\n",
    "intersight:\n  configure:\n    Org:\n      profiles:\n        domain:\n"
    "          - name: Domain\n            serial_numbers: SERIAL-A\n",
])
def test_invalid_domain_inputs_are_rejected(tmp_path, content):
    (tmp_path / "profiles.ezai.yaml").write_text(content)
    with pytest.raises(ValueError):
        ports.domain_targets(tmp_path)
