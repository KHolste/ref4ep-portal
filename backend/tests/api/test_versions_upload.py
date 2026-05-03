"""API: Version-Upload (multipart)."""

from __future__ import annotations

import hashlib
import io

from fastapi.testclient import TestClient


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def _create_doc(member_client: TestClient) -> str:
    r = member_client.post(
        "/api/workpackages/WP3/documents",
        json={"title": "Upload-Test", "document_type": "report"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_first_upload_returns_version_one_with_hash(
    member_client: TestClient, member_in_wp3
) -> None:
    doc_id = _create_doc(member_client)
    payload = b"%PDF-1.4 demo content"
    expected_hash = hashlib.sha256(payload).hexdigest()
    r = member_client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": ("entwurf.pdf", io.BytesIO(payload), "application/pdf")},
        data={"change_note": "Initial-Entwurf v0.1"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"]["version_number"] == 1
    assert body["version"]["sha256"] == expected_hash
    assert body["version"]["file_size_bytes"] == len(payload)
    assert body["warnings"] == []


def test_short_change_note_returns_422(member_client: TestClient, member_in_wp3) -> None:
    doc_id = _create_doc(member_client)
    r = member_client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": ("x.pdf", io.BytesIO(b"abc"), "application/pdf")},
        data={"change_note": "  "},
        headers=_csrf(member_client),
    )
    assert r.status_code == 422


def test_unsupported_mime_returns_415(member_client: TestClient, member_in_wp3) -> None:
    doc_id = _create_doc(member_client)
    r = member_client.post(
        f"/api/documents/{doc_id}/versions",
        files={
            "file": ("virus.exe", io.BytesIO(b"MZ"), "application/x-msdownload"),
        },
        data={"change_note": "soll abgelehnt werden"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 415


def test_csrf_missing_returns_403(member_client: TestClient, member_in_wp3) -> None:
    doc_id = _create_doc(member_client)
    r = member_client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        data={"change_note": "ohne csrf"},
    )
    assert r.status_code == 403


def test_payload_too_large_returns_413(member_client: TestClient, member_in_wp3, app) -> None:
    # Limit auf wenige Bytes setzen, damit der Test schnell ist.
    app.state.settings.max_upload_mb = 0  # 0 MiB = 0 Bytes
    doc_id = _create_doc(member_client)
    r = member_client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4 large"), "application/pdf")},
        data={"change_note": "zu groß"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 413


def test_duplicate_content_warning_in_response(member_client: TestClient, member_in_wp3) -> None:
    doc_id = _create_doc(member_client)
    payload = b"identical bytes"
    member_client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": ("v1.pdf", io.BytesIO(payload), "application/pdf")},
        data={"change_note": "erste Version"},
        headers=_csrf(member_client),
    )
    r = member_client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": ("v1-rename.pdf", io.BytesIO(payload), "application/pdf")},
        data={"change_note": "Metadaten korrigiert"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 201
    assert r.json()["warnings"] == ["duplicate_content_of_v1"]
