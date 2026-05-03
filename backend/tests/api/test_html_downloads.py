"""HTML-View /downloads — Sichtbarkeit der freigegebenen public-Dokumente."""

from __future__ import annotations

import io

from fastapi.testclient import TestClient


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def _publish(client: TestClient, title: str) -> str:
    create = client.post(
        "/api/workpackages/WP3/documents",
        json={"title": title, "document_type": "deliverable", "deliverable_code": "D3.X"},
        headers=_csrf(client),
    )
    assert create.status_code == 201
    doc_id = create.json()["id"]
    upload = client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": ("v1.pdf", io.BytesIO(b"%PDF-1.4 inhalt"), "application/pdf")},
        data={"change_note": "erste Version"},
        headers=_csrf(client),
    )
    assert upload.status_code == 201
    n = upload.json()["version"]["version_number"]
    client.post(
        f"/api/documents/{doc_id}/status",
        json={"to": "in_review"},
        headers=_csrf(client),
    )
    client.post(
        f"/api/documents/{doc_id}/release",
        json={"version_number": n},
        headers=_csrf(client),
    )
    client.post(
        f"/api/documents/{doc_id}/visibility",
        json={"to": "public"},
        headers=_csrf(client),
    )
    return doc_id


def test_downloads_page_lists_only_public_released(
    client: TestClient, member_client: TestClient, lead_in_wp3
) -> None:
    _publish(member_client, "ÖffentlichesDokument")
    # Ein nicht veröffentlichtes Dokument darf NICHT erscheinen.
    member_client.post(
        "/api/workpackages/WP3/documents",
        json={"title": "NurDraft", "document_type": "note"},
        headers=_csrf(member_client),
    )

    client.cookies.clear()
    r = client.get("/downloads")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    assert "ÖffentlichesDokument" in body
    assert "NurDraft" not in body
    assert "v1.pdf" in body
    assert "/api/public/documents/WP3/offentlichesdokument/download" in body


def test_downloads_page_shows_empty_message_when_no_public_docs(
    client: TestClient, seeded_session
) -> None:
    client.cookies.clear()
    r = client.get("/downloads")
    assert r.status_code == 200
    assert "Aktuell sind keine öffentlich freigegebenen Dokumente" in r.text


def test_download_detail_page_shows_metadata(
    client: TestClient, member_client: TestClient, lead_in_wp3
) -> None:
    _publish(member_client, "DetailTest")
    client.cookies.clear()
    r = client.get("/downloads/WP3/detailtest")
    assert r.status_code == 200
    body = r.text
    assert "DetailTest" in body
    assert "WP3" in body
    assert "D3.X" in body
    assert "v1.pdf" in body
    assert "/api/public/documents/WP3/detailtest/download" in body


def test_download_detail_page_404_for_unknown(client: TestClient, seeded_session) -> None:
    client.cookies.clear()
    r = client.get("/downloads/WP3/gibt-es-nicht")
    assert r.status_code == 404


def test_download_detail_page_404_for_internal(
    client: TestClient, member_client: TestClient, lead_in_wp3
) -> None:
    create = member_client.post(
        "/api/workpackages/WP3/documents",
        json={"title": "InternalDoc", "document_type": "note"},
        headers=_csrf(member_client),
    )
    doc_id = create.json()["id"]
    upload = member_client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": ("v.pdf", io.BytesIO(b"%PDF-1.4 i"), "application/pdf")},
        data={"change_note": "Initial-Entwurf"},
        headers=_csrf(member_client),
    )
    n = upload.json()["version"]["version_number"]
    member_client.post(
        f"/api/documents/{doc_id}/status",
        json={"to": "in_review"},
        headers=_csrf(member_client),
    )
    member_client.post(
        f"/api/documents/{doc_id}/release",
        json={"version_number": n},
        headers=_csrf(member_client),
    )
    member_client.post(
        f"/api/documents/{doc_id}/visibility",
        json={"to": "internal"},
        headers=_csrf(member_client),
    )
    client.cookies.clear()
    r = client.get("/downloads/WP3/internaldoc")
    assert r.status_code == 404
