"""Power-state gate for runtime ND hardware discovery."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import yaml
import pytest

AUTOMATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AUTOMATION / "scripts"))

import discover_serials  # noqa: E402
import cimc_redfish  # noqa: E402


def _node(hostname: str = "EXAMPLE-ND-3"):
    return SimpleNamespace(
        hostname=hostname,
        cimc=SimpleNamespace(
            ip="198.51.100.89",
            user="admin",
            pass_ref="ND3_CIMC_PASSWORD",
        ),
    )


class _Session:
    def __init__(self, client):
        self.client = client

    def __enter__(self):
        return self.client

    def __exit__(self, *_args):
        return False


def _client(power_state: str):
    class FakeCimcRedfish:
        def __init__(self, *_args, **_kwargs):
            pass

        def session(self):
            return _Session(self)

        def power_state(self):
            return power_state

        def serial_number(self):
            return "FDO00000003"

    return FakeCimcRedfish


def test_discovery_records_power_state(monkeypatch):
    monkeypatch.setattr(discover_serials, "resolve", lambda _ref: "secret")
    monkeypatch.setattr(discover_serials, "CimcRedfish", _client("On"))

    hostname, record = discover_serials._discover(_node(), verify=False)

    assert hostname == "EXAMPLE-ND-3"
    assert record == {
        "cimc_ip": "198.51.100.89",
        "power_state": "On",
        "serial_number": "FDO00000003",
    }


def test_discovery_records_off_state_for_visible_ansible_gate(monkeypatch):
    monkeypatch.setattr(discover_serials, "resolve", lambda _ref: "secret")
    monkeypatch.setattr(discover_serials, "CimcRedfish", _client("Off"))

    _, record = discover_serials._discover(_node(), verify=False)

    assert record["power_state"] == "Off"


def test_discovery_falls_back_to_basic_auth_for_gets(monkeypatch):
    class TokenSessionUnavailable:
        def __enter__(self):
            raise cimc_redfish.RedfishTransient("session service recovering")

        def __exit__(self, *_args):
            return False

    class FakeCimcRedfish:
        used_basic = False

        def __init__(self, *_args, **_kwargs):
            pass

        def session(self):
            return TokenSessionUnavailable()

        def basic_session(self):
            FakeCimcRedfish.used_basic = True
            return _Session(self)

        def power_state(self):
            return "On"

        def serial_number(self):
            return "WZP00000001"

    monkeypatch.setattr(discover_serials, "resolve", lambda _ref: "secret")
    monkeypatch.setattr(discover_serials, "CimcRedfish", FakeCimcRedfish)

    _, record = discover_serials._discover(_node(), verify=False)

    assert FakeCimcRedfish.used_basic is True
    assert record["serial_number"] == "WZP00000001"


def test_redfish_login_classifies_recovering_cimc_as_transient(monkeypatch):
    client = cimc_redfish.CimcRedfish(
        "198.51.100.87", "admin", "secret", verify=False
    )
    response = SimpleNamespace(status_code=400, text="service recovering", headers={})
    monkeypatch.setattr(client._session, "post", lambda *_a, **_k: response)

    with pytest.raises(cimc_redfish.RedfishTransient):
        cimc_redfish.CimcRedfish.login.__wrapped__(client)


def test_redfish_login_does_not_retry_bad_credentials(monkeypatch):
    client = cimc_redfish.CimcRedfish(
        "198.51.100.87", "admin", "secret", verify=False
    )
    response = SimpleNamespace(status_code=401, text="unauthorized", headers={})
    monkeypatch.setattr(client._session, "post", lambda *_a, **_k: response)

    with pytest.raises(cimc_redfish.RedfishError) as exc:
        cimc_redfish.CimcRedfish.login.__wrapped__(client)
    assert not isinstance(exc.value, cimc_redfish.RedfishTransient)


def test_form_cluster_gates_each_node_before_nd_setup():
    tasks = yaml.safe_load(
        (
            AUTOMATION
            / "roles"
            / "nd_cluster"
            / "tasks"
            / "form_cluster.yml"
        ).read_text()
    )
    power_gate_index = next(
        index
        for index, task in enumerate(tasks)
        if task["name"] == "ND/form_cluster: require every node to be powered on"
    )
    setup_index = next(
        index
        for index, task in enumerate(tasks)
        if "cisco.nd.nd_setup" in task
    )
    gate = tasks[power_gate_index]

    assert power_gate_index < setup_index
    assert gate["loop"] == "{{ nodes }}"
    assert gate["ansible.builtin.assert"]["that"] == [
        "nd_serials.nodes[node.hostname].power_state == 'On'"
    ]
