from __future__ import annotations

from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from shared.lib.state import clear_phases, is_complete, mark  # noqa: E402


def test_new_image_clears_only_selected_downstream_markers(tmp_path: Path) -> None:
    mark(tmp_path, "node1", "bootstrap", mgmtIp="192.0.2.10")
    mark(tmp_path, "node1", "installer_complete")
    mark(tmp_path, "node1", "evidence", source="prior-run")

    clear_phases(tmp_path, "node1", "bootstrap", "installer_complete")

    assert not is_complete(tmp_path, "node1", "bootstrap")
    assert not is_complete(tmp_path, "node1", "installer_complete")
    assert is_complete(tmp_path, "node1", "evidence")


def test_installers_clear_stale_markers_before_mounting_new_image() -> None:
    automation = REPO / "01-nd-cluster" / "automation" / "scripts"
    primary = (automation / "install_node1.py").read_text()
    secondary = (automation / "install_secondaries.py").read_text()

    primary_mount = primary.index(
        'if not is_complete(state_dir, STATE_NAME, "mount_and_boot")'
    )
    secondary_mount = secondary.index(
        'if not is_complete(state_dir, state_name, "mount_and_boot")'
    )

    assert primary.index("clear_phases(", primary_mount) < primary.index(
        "cimc.insert_iso", primary_mount
    )
    assert secondary.index("clear_phases(", secondary_mount) < secondary.index(
        "cimc.insert_iso", secondary_mount
    )
