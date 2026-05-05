"""API: GET /api/documents — interne Dokumentliste (Block 0017).

Zweck: Auswahllisten interner UI-Module (z. B. Meeting-Doc-Verknüpfung)
sollen einen einzigen Request statt vieler WP-spezifischer machen.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def _create_doc(
    client: TestClient,
    *,
    wp_code: str,
    title: str,
    deliverable_code: str | None = None,
    document_type: str = "report",
) -> str:
    r = client.post(
        f"/api/workpackages/{wp_code}/documents",
        json={
            "title": title,
            "document_type": document_type,
            "deliverable_code": deliverable_code,
        },
        headers=_csrf(client),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---- Permissions ------------------------------------------------------


def test_anonymous_cannot_list_internal_documents(
    client: TestClient, seeded_session: Session
) -> None:
    client.cookies.clear()
    r = client.get("/api/documents")
    assert r.status_code == 401


def test_logged_in_member_can_list(member_client: TestClient) -> None:
    r = member_client.get("/api/documents")
    assert r.status_code == 200
    # Antwort ist eine Liste (auch wenn leer).
    assert isinstance(r.json(), list)


# ---- Filterverhalten --------------------------------------------------


def test_response_carries_compact_fields(admin_client: TestClient, seeded_session: Session) -> None:
    _create_doc(
        admin_client,
        wp_code="WP3.1",
        title="Test-Bericht 1",
        deliverable_code="D3.1",
    )
    r = admin_client.get("/api/documents")
    assert r.status_code == 200
    items = r.json()
    target = next(d for d in items if d["title"] == "Test-Bericht 1")
    # Pflichtfelder gemäß Schema InternalDocumentOut.
    for key in (
        "id",
        "code",
        "title",
        "workpackage_code",
        "workpackage_title",
        "status",
        "visibility",
        "is_public",
        "is_archived",
        "updated_at",
    ):
        assert key in target, f"Feld {key!r} fehlt: {target}"
    assert target["code"] == "D3.1"
    assert target["workpackage_code"] == "WP3.1"
    assert target["is_archived"] is False
    assert target["is_public"] is False


def test_default_excludes_archived(admin_client: TestClient, seeded_session: Session) -> None:
    """``is_deleted=True`` zählt aktuell als archiviert (kein eigenes Flag)."""
    doc_id = _create_doc(admin_client, wp_code="WP3.1", title="Archiviert")
    # Soft-Delete via API (Admin) — der Endpoint liefert das gepatchte
    # DocumentOut zurück (Status 200, nicht 204).
    r_del = admin_client.delete(f"/api/documents/{doc_id}", headers=_csrf(admin_client))
    assert r_del.status_code == 200
    items = admin_client.get("/api/documents").json()
    assert all(d["title"] != "Archiviert" for d in items)


def test_include_archived_returns_archived_too(
    admin_client: TestClient, seeded_session: Session
) -> None:
    doc_id = _create_doc(admin_client, wp_code="WP3.1", title="Archiv-Sicht")
    r_del = admin_client.delete(f"/api/documents/{doc_id}", headers=_csrf(admin_client))
    assert r_del.status_code == 200
    items = admin_client.get("/api/documents?include_archived=true").json()
    target = next(d for d in items if d["title"] == "Archiv-Sicht")
    assert target["is_archived"] is True


def test_workpackage_filter(admin_client: TestClient) -> None:
    _create_doc(admin_client, wp_code="WP1.1", title="WP1.1-Doc")
    _create_doc(admin_client, wp_code="WP3.1", title="WP3.1-Doc")
    items = admin_client.get("/api/documents?workpackage=WP1.1").json()
    titles = [d["title"] for d in items]
    assert "WP1.1-Doc" in titles
    assert "WP3.1-Doc" not in titles


def test_workpackage_unknown_returns_empty_list(admin_client: TestClient) -> None:
    """Konsistent mit ``list_for_workpackage``: unbekannter WP → []."""
    r = admin_client.get("/api/documents?workpackage=WPNotExist")
    assert r.status_code == 200
    assert r.json() == []


def test_q_searches_code_and_title_case_insensitive(admin_client: TestClient) -> None:
    _create_doc(admin_client, wp_code="WP1.1", title="Spec Alpha", deliverable_code="D1.7")
    _create_doc(admin_client, wp_code="WP3.1", title="Bericht Beta")
    # Suche im Titel.
    items = admin_client.get("/api/documents?q=alpha").json()
    titles = [d["title"] for d in items]
    assert "Spec Alpha" in titles
    assert "Bericht Beta" not in titles
    # Suche im Code.
    items2 = admin_client.get("/api/documents?q=d1.7").json()
    assert any(d["title"] == "Spec Alpha" for d in items2)


# ---- Sortierung -------------------------------------------------------


def test_sorted_by_workpackage_then_title(admin_client: TestClient) -> None:
    _create_doc(admin_client, wp_code="WP3.1", title="Z-Bericht")
    _create_doc(admin_client, wp_code="WP1.1", title="A-Bericht")
    _create_doc(admin_client, wp_code="WP1.1", title="M-Bericht")
    items = admin_client.get("/api/documents").json()
    # Nur unsere Test-Dokumente herausfiltern, dann WP-Reihenfolge prüfen.
    labels = [(d["workpackage_code"], d["title"]) for d in items]
    indices_a = labels.index(("WP1.1", "A-Bericht"))
    indices_m = labels.index(("WP1.1", "M-Bericht"))
    indices_z = labels.index(("WP3.1", "Z-Bericht"))
    assert indices_a < indices_m < indices_z


# ---- Bestehende Endpunkte unverändert --------------------------------


def test_workpackage_specific_endpoint_still_works(
    member_client: TestClient, member_in_wp3, seeded_session: Session
) -> None:
    """``/api/workpackages/{code}/documents`` bleibt unverändert
    (mit eigener WP-Mitgliedschafts-Filterung)."""
    r = member_client.get("/api/workpackages/WP3/documents")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
