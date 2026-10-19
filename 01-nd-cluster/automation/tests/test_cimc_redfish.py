from __future__ import annotations

from pathlib import Path
import sys


AUTOMATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AUTOMATION / "scripts"))

from cimc_redfish import CimcRedfish  # noqa: E402


def test_refresh_session_replaces_expired_token() -> None:
    client = object.__new__(CimcRedfish)
    client.host = "192.0.2.10"
    events: list[str] = []
    client.logout = lambda: events.append("logout")
    client.login = lambda: events.append("login")

    client.refresh_session()

    assert events == ["logout", "login"]


def test_installers_refresh_before_post_install_redfish_actions() -> None:
    primary = (AUTOMATION / "scripts" / "install_node1.py").read_text()
    secondary = (AUTOMATION / "scripts" / "install_secondaries.py").read_text()

    primary_phase = primary.index(
        'if not is_complete(state_dir, STATE_NAME, "post_install_poweron")'
    )
    secondary_phase = secondary.index(
        'if not is_complete(state_dir, state_name, "post_install_poweron")'
    )

    assert primary.index("cimc.refresh_session()", primary_phase) < primary.index(
        "cimc.eject_iso()", primary_phase
    )
    assert secondary.index("cimc.refresh_session()", secondary_phase) < secondary.index(
        "cimc.eject_iso()", secondary_phase
    )
