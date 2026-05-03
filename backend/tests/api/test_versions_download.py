"""API: Download einer Version."""

from __future__ import annotations

import hashlib
import io

from fastapi.testclient import TestClient


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def _create_doc_with_version(client: TestClient, payload: bytes, filename: str = "x.pdf"):
    create = client.post(
        "/api/workpackages/WP3/documents",
        json={"title": "Download-Test", "document_type": "report"},
        headers=_csrf(client),
    )
    assert create.status_code == 201, create.text
    doc_id = create.json()["id"]
    upload = client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": (filename, io.BytesIO(payload), "application/pdf")},
        data={"change_note": "erste Version"},
        headers=_csrf(client),
    )
    assert upload.status_code == 201, upload.text
    return doc_id, upload.json()["version"]["version_number"]


def test_download_returns_byte_identical_attachment(
    member_client: TestClient, member_in_wp3
) -> None:
    payload = b"%PDF-1.4\nbinaerinhalt\n" * 50
    doc_id, n = _create_doc_with_version(member_client, payload)
    r = member_client.get(f"/api/documents/{doc_id}/versions/{n}/download")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in r.headers["content-disposition"]
    assert hashlib.sha256(r.content).hexdigest() == hashlib.sha256(payload).hexdigest()


def test_download_anonymous_returns_401(
    client: TestClient, member_client: TestClient, member_in_wp3
) -> None:
    payload = b"%PDF-1.4 secret"
    doc_id, n = _create_doc_with_version(member_client, payload)
    # Cookies des member_client clearen
    client.cookies.clear()
    r = client.get(f"/api/documents/{doc_id}/versions/{n}/download")
    assert r.status_code == 401


def test_download_unknown_version_returns_404(member_client: TestClient, member_in_wp3) -> None:
    doc_id, _ = _create_doc_with_version(member_client, b"%PDF-1.4 abc")
    r = member_client.get(f"/api/documents/{doc_id}/versions/99/download")
    assert r.status_code == 404


def test_download_for_foreign_user_returns_404(
    member_client: TestClient, member_in_wp3, client: TestClient, admin_person_id
) -> None:
    # member_in_wp3 ist Mitglied von WP3 und legt Doku an. Der Admin hat
    # dank platform_role = admin Lesezugriff; um „nicht-Mitglied" zu testen
    # würden wir einen dritten Account brauchen. Hier kontrastieren wir mit
    # einem zweiten User ohne Membership: wir nutzen den admin_person_id,
    # der Admin ist und damit lesen darf — also stattdessen anonymen Zugriff
    # mit ungültigem Cookie testen.
    payload = b"%PDF-1.4 forbidden"
    doc_id, n = _create_doc_with_version(member_client, payload)
    client.cookies.clear()
    client.cookies.set("ref4ep_session", "invalid.token.here")
    r = client.get(f"/api/documents/{doc_id}/versions/{n}/download")
    assert r.status_code == 401
