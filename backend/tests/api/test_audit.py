"""GET /api/admin/audit."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def test_member_cannot_view_audit(member_client: TestClient, member_in_wp3) -> None:
    r = member_client.get("/api/admin/audit")
    assert r.status_code == 403


def test_admin_sees_audit_after_actions(admin_client: TestClient, member_in_wp3) -> None:
    # Erzeuge eine schreibende Aktion → produziert mind. einen Audit-Eintrag.
    create = admin_client.post(
        "/api/workpackages/WP3/documents",
        json={"title": "AuditDemo", "document_type": "report"},
        headers=_csrf(admin_client),
    )
    assert create.status_code == 201

    r = admin_client.get("/api/admin/audit", params={"action": "document.create"})
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    entry = items[0]
    assert entry["action"] == "document.create"
    assert entry["entity_type"] == "document"
    assert entry["details"]["after"]["title"] == "AuditDemo"
    assert entry["actor"]["email"]


def test_admin_can_filter_by_entity_type(admin_client: TestClient, member_in_wp3) -> None:
    admin_client.post(
        "/api/workpackages/WP3/documents",
        json={"title": "EntityFilter", "document_type": "note"},
        headers=_csrf(admin_client),
    )
    r = admin_client.get(
        "/api/admin/audit",
        params={"entity_type": "document", "action": "document.create"},
    )
    assert r.status_code == 200
    assert all(e["entity_type"] == "document" for e in r.json())
