"""Tests for precheck ISO content verification."""
from __future__ import annotations

import hashlib
import io
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from precheck import (  # noqa: E402
    FAIL,
    PASS,
    SKIP,
    check_iso_sha512_file,
    check_iso_sha512_url,
)


def _inventory(
    expected: str,
    url: str = "https://example.invalid/nd.iso",
    start_mode: str = "iso_reimage",
):
    return SimpleNamespace(
        cluster=SimpleNamespace(
            iso=SimpleNamespace(sha512=expected, url=url),
            start_mode=start_mode,
        ),
        runtime=SimpleNamespace(verify_tls=True),
    )


def test_iso_sha512_file_matches(tmp_path):
    payload = b"verified ND ISO fixture\n"
    iso = tmp_path / "nd.iso"
    iso.write_bytes(payload)
    expected = hashlib.sha512(payload).hexdigest()

    result = check_iso_sha512_file(_inventory(expected), iso)

    assert result.status == PASS
    assert "matches inventory SHA-512" in result.detail


def test_iso_sha512_file_mismatch(tmp_path):
    iso = tmp_path / "nd.iso"
    iso.write_bytes(b"different bytes")
    expected = hashlib.sha512(b"expected bytes").hexdigest()

    result = check_iso_sha512_file(_inventory(expected), iso)

    assert result.status == FAIL
    assert "SHA-512 mismatch" in result.detail


def test_iso_sha512_file_missing(tmp_path):
    expected = hashlib.sha512(b"expected bytes").hexdigest()

    result = check_iso_sha512_file(_inventory(expected), tmp_path / "missing.iso")

    assert result.status == FAIL
    assert "ISO file not found" in result.detail


def test_iso_sha512_url_matches(tmp_path):
    payload = b"verified hosted ND ISO fixture\n"
    iso = tmp_path / "nd.iso"
    iso.write_bytes(payload)
    expected = hashlib.sha512(payload).hexdigest()

    result = check_iso_sha512_url(_inventory(expected, iso.as_uri()))

    assert result.status == PASS
    assert "hosted ISO matches inventory SHA-512" in result.detail


def test_iso_sha512_url_mismatch(tmp_path):
    iso = tmp_path / "nd.iso"
    iso.write_bytes(b"wrong hosted bytes")
    expected = hashlib.sha512(b"expected bytes").hexdigest()

    result = check_iso_sha512_url(_inventory(expected, iso.as_uri()))

    assert result.status == FAIL
    assert "hosted ISO SHA-512 mismatch" in result.detail


def test_iso_sha512_url_skipped_when_image_is_not_consumed():
    expected = hashlib.sha512(b"expected bytes").hexdigest()

    result = check_iso_sha512_url(
        _inventory(expected, start_mode="factory_preinstalled")
    )

    assert result.status == SKIP
    assert "not consumed" in result.detail


def test_iso_sha512_url_rejects_incomplete_transfer_before_digest(monkeypatch):
    payload = b"partial bytes"
    expected = hashlib.sha512(payload).hexdigest()

    class _Response(io.BytesIO):
        headers = {"Content-Length": str(len(payload) + 100)}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    monkeypatch.setattr(
        "precheck.urllib.request.urlopen",
        lambda *_args, **_kwargs: _Response(payload),
    )

    result = check_iso_sha512_url(_inventory(expected))

    assert result.status == FAIL
    assert "transfer incomplete" in result.detail
    assert "no content-integrity conclusion" in result.detail
