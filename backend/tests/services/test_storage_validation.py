"""storage_validation: MIME-Whitelist, Size-Limit, Storage-Key-Helfer."""

from __future__ import annotations

import pytest

from ref4ep.services.storage_validation import (
    MIME_WHITELIST,
    compute_storage_key,
    validate_change_note,
    validate_mime,
    validate_size,
    validate_storage_key,
)

UUID_A = "11111111-1111-1111-1111-111111111111"
UUID_B = "22222222-2222-2222-2222-222222222222"


def test_mime_whitelist_accepts_pdf_and_office_zip_image() -> None:
    for mime in {
        "application/pdf",
        "application/zip",
        "image/png",
        "image/jpeg",
    }:
        assert mime in MIME_WHITELIST
        validate_mime(mime)  # no raise


def test_mime_whitelist_rejects_executable() -> None:
    with pytest.raises(ValueError):
        validate_mime("application/x-msdownload")


def test_validate_size_rejects_zero_and_too_large() -> None:
    with pytest.raises(ValueError):
        validate_size(0, 100)
    with pytest.raises(ValueError):
        validate_size(101, 100)
    validate_size(100, 100)  # genau am Limit ist erlaubt


def test_validate_change_note_min_length_after_strip() -> None:
    with pytest.raises(ValueError):
        validate_change_note("    ")
    with pytest.raises(ValueError):
        validate_change_note("abc")
    assert validate_change_note("  ändert das Format  ") == "ändert das Format"


def test_compute_and_validate_storage_key_roundtrip() -> None:
    key = compute_storage_key(UUID_A, UUID_B)
    assert key == f"documents/{UUID_A}/{UUID_B}.bin"
    validate_storage_key(key)


def test_validate_storage_key_rejects_traversal_and_extensions() -> None:
    with pytest.raises(ValueError):
        validate_storage_key("documents/../escape.bin")
    with pytest.raises(ValueError):
        validate_storage_key(f"documents/{UUID_A}/{UUID_B}.exe")
