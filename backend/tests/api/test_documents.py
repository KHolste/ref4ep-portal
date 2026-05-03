"""API: Dokument-CRUD (ohne Versions-Upload)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def test_anonymous_cannot_list_documents(client: TestClient, seeded_session) -> None:
    r = client.get("/api/workpackages/WP3/documents")
    assert r.status_code == 401


def test_member_can_create_and_list(member_client: TestClient, member_in_wp3) -> None:
    create = member_client.post(
        "/api/workpackages/WP3/documents",
        json={"title": "Konstruktion", "document_type": "deliverable", "deliverable_code": "D3.1"},
        headers=_csrf(member_client),
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["status"] == "draft"
    assert body["visibility"] == "workpackage"
    assert body["slug"]

    listed = member_client.get("/api/workpackages/WP3/documents")
    assert listed.status_code == 200
    assert any(d["title"] == "Konstruktion" for d in listed.json())


def test_non_member_gets_empty_list_not_403(member_client: TestClient, member_in_wp3) -> None:
    # Member ist in WP3; WP4 sieht er nicht.
    r = member_client.get("/api/workpackages/WP4/documents")
    assert r.status_code == 200
    assert r.json() == []


def test_non_member_cannot_create_in_other_wp(member_client: TestClient, member_in_wp3) -> None:
    r = member_client.post(
        "/api/workpackages/WP4/documents",
        json={"title": "Fremd", "document_type": "note"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_create_without_csrf_blocked(member_client: TestClient, member_in_wp3) -> None:
    r = member_client.post(
        "/api/workpackages/WP3/documents",
        json={"title": "Ohne CSRF", "document_type": "note"},
    )
    assert r.status_code == 403


def test_get_unknown_document_returns_404(admin_client: TestClient) -> None:
    r = admin_client.get("/api/documents/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_patch_metadata(member_client: TestClient, member_in_wp3) -> None:
    create = member_client.post(
        "/api/workpackages/WP3/documents",
        json={"title": "Erst", "document_type": "report"},
        headers=_csrf(member_client),
    )
    doc_id = create.json()["id"]
    r = member_client.patch(
        f"/api/documents/{doc_id}",
        json={"title": "Korrigiert", "deliverable_code": "D3.2"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Korrigiert"
    assert r.json()["deliverable_code"] == "D3.2"


def test_slug_conflict_returns_409(member_client: TestClient, member_in_wp3) -> None:
    member_client.post(
        "/api/workpackages/WP3/documents",
        json={"title": "Selber Titel", "document_type": "note"},
        headers=_csrf(member_client),
    )
    r = member_client.post(
        "/api/workpackages/WP3/documents",
        json={"title": "Selber Titel", "document_type": "note"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 409
