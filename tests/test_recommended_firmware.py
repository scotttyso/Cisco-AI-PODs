import json
from pathlib import Path
import sys
from unittest.mock import MagicMock, Mock

import pytest
import requests


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "05-mgmt-nodes-ucs/automation/scripts"))
import get_recommended_firmware as firmware


def image(version, *models):
    return {"Version": version, "SupportedModels": list(models)}


def test_catalog_queries_separate_platforms_and_paginate():
    client = Mock()
    client.get.side_effect = [
        Mock(json=lambda: {"Results": [image("4.3(5a)", "UCSX-210C-M7")] * 1000}),
        Mock(json=lambda: {"Results": [image("6.0(1a)", "UCSX-210C-M7")]}),
        Mock(json=lambda: {"Results": [image("4.3(4a)", "UCSC-C240-M7S")]}),
    ]
    rows = firmware.recommendations(client, "https://intersight.com", [
        ("FIAttached", "UCSX-210C-M7"), ("Standalone", "UCSC-C240-M7")])
    assert rows == [
        {"model": "UCSX-210C-M7", "platform": "FIAttached", "versions": ["4.3(5a)", "6.0(1a)"]},
        {"model": "UCSC-C240-M7", "platform": "Standalone", "versions": ["4.3(4a)"]},
    ]
    calls = client.get.call_args_list
    assert all(call.args == ("https://intersight.com/api/v1/firmware/Distributables",) for call in calls)
    assert calls[0].kwargs["params"]["$filter"] == (
        "RecommendedBuild eq 'Y' and ImageType eq 'Intersight Managed Mode Server'")
    assert calls[1].kwargs["params"]["$skip"] == 1000
    assert calls[2].kwargs["params"]["$filter"] == (
        "RecommendedBuild eq 'Y' and ImageType eq 'Standalone Server'")
    client.post.assert_not_called()
    client.patch.assert_not_called()


def test_exact_pid_precedes_variant_fallback_and_unmatched_is_explicit():
    client = Mock()
    client.get.return_value.json.return_value = {"Results": [
        image("4.3(5a)", "UCSC-C240-M7S"), image("6.0(1a)", "UCSC-C240-M7L"),
        image("6.0(1a)", "UCSC-C240-M7L"), {"Version": "4.3(5a)", "SupportedModels": None},
    ]}
    models = firmware.parse_models(["Standalone=ucsc-c240-m7s", "Standalone=UCSC-C240-M7",
                                    "Standalone=UCSC-C240-M8", "Standalone=UCSC-C240-M7S"])
    rows = {row["model"]: row["versions"] for row in firmware.recommendations(
        client, "https://intersight.com", models)}
    assert rows == {"UCSC-C240-M7": ["4.3(5a)", "6.0(1a)"],
                    "UCSC-C240-M7S": ["4.3(5a)"], "UCSC-C240-M8": []}


@pytest.mark.parametrize("suffix", ["L", "D", "X", "N", "S", "M", "SNEB", "S2"])
def test_catalog_hardware_variant_suffixes(suffix):
    assert firmware.model_family(f"UCSC-C240-M7{suffix}") == "UCSC-C240-M7"


@pytest.mark.parametrize("values", [[], ["Standalone="], ["Unknown=PID"], ["PID"]])
def test_invalid_model_input(values):
    with pytest.raises(ValueError):
        firmware.parse_models(values)


@pytest.mark.parametrize("entry", ["not-an-image", {}, {"Version": "6.0", "SupportedModels": "PID"},
                                  {"Version": "6.0", "SupportedModels": [None]}])
def test_invalid_catalog_fails(entry):
    client = Mock()
    client.get.return_value.json.return_value = {"Results": [entry]}
    with pytest.raises(ValueError, match="Firmware catalog"):
        firmware.recommendations(client, "https://intersight.com", [("Standalone", "UCSC-C240-M7")])


def test_cli_persists_report_and_failure_preserves_previous_result(tmp_path, monkeypatch, capsys):
    output = tmp_path / "firmware/intersight.json"
    monkeypatch.setattr(sys, "argv", ["firmware", "--model", "Standalone=UCSC-C240-M7",
                                    "--output", str(output), "--url", "intersight.com/"])
    client = Mock()
    client.get.return_value.json.return_value = {"Results": []}
    context = MagicMock()
    context.__enter__.return_value = client
    monkeypatch.setattr(firmware, "session", lambda: context)
    assert firmware.main() == 0
    saved = output.read_text()
    report = json.loads(saved)
    assert report["source"] == "https://intersight.com"
    assert report["collected"].endswith("+00:00")
    assert report["models"] == [{"model": "UCSC-C240-M7", "platform": "Standalone", "versions": []}]
    assert "WARNING: no recommended build found" in capsys.readouterr().out
    client.get.return_value.raise_for_status.side_effect = requests.HTTPError("403 Forbidden")
    assert firmware.main() == 1
    assert "lookup failed: 403 Forbidden" in capsys.readouterr().err
    assert output.read_text() == saved


def test_report_write_failure_is_atomic(tmp_path, monkeypatch):
    output = tmp_path / "firmware.json"
    output.write_text("previous result")

    def fail(_source, _destination):
        raise OSError("disk full")

    monkeypatch.setattr(firmware.os, "replace", fail)
    with pytest.raises(OSError, match="disk full"):
        firmware.write_report(output, {"models": []})
    assert output.read_text() == "previous result"
    assert list(tmp_path.iterdir()) == [output]
