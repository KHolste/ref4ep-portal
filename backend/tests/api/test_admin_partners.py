"""Admin-API für Partner — CRUD + Soft-Delete."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def test_anonymous_cannot_list(client: TestClient, seeded_session) -> None:
    client.cookies.clear()
    r = client.get("/api/admin/partners")
    assert r.status_code == 401


def test_member_cannot_list(member_client: TestClient, member_in_wp3) -> None:
    r = member_client.get("/api/admin/partners")
    assert r.status_code == 403


def test_admin_can_list_includes_deleted(admin_client: TestClient, seeded_session) -> None:
    r = admin_client.get("/api/admin/partners")
    assert r.status_code == 200
    body = r.json()
    short_names = {p["short_name"] for p in body}
    assert {"JLU", "IOM", "CAU", "THM", "TUD"}.issubset(short_names)


def test_create_partner(admin_client: TestClient, seeded_session) -> None:
    r = admin_client.post(
        "/api/admin/partners",
        json={"short_name": "ACM", "name": "Acme AG", "country": "DE"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 201
    assert r.json()["short_name"] == "ACM"


def test_patch_partner(admin_client: TestClient, seeded_session) -> None:
    partners = admin_client.get("/api/admin/partners").json()
    target = next(p for p in partners if p["short_name"] == "JLU")
    r = admin_client.patch(
        f"/api/admin/partners/{target['id']}",
        json={"website": "https://www.uni-giessen.de"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 200
    assert r.json()["website"] == "https://www.uni-giessen.de"


def test_soft_delete_hides_from_public_list(
    admin_client: TestClient, client: TestClient, seeded_session
) -> None:
    partners = admin_client.get("/api/admin/partners").json()
    target = next(p for p in partners if p["short_name"] == "TUD")
    r = admin_client.delete(f"/api/admin/partners/{target['id']}", headers=_csrf(admin_client))
    assert r.status_code == 204
    # Internes /api/partners (Sprint 1) zeigt soft-deleted nicht mehr.
    listed = admin_client.get("/api/partners").json()
    assert all(p["short_name"] != "TUD" for p in listed)
    # Admin-Endpunkt zeigt ihn weiterhin (mit is_deleted=true).
    full = admin_client.get("/api/admin/partners").json()
    deleted_entry = next(p for p in full if p["short_name"] == "TUD")
    assert deleted_entry["is_deleted"] is True


def test_member_cannot_create(member_client: TestClient, seeded_session) -> None:
    r = member_client.post(
        "/api/admin/partners",
        json={"short_name": "X", "name": "X", "country": "DE"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403
