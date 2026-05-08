"""API: Dokumentkommentare auf Versionsebene (Block 0024).

Prüft Permission-Matrix (anonym/Member-WP/Member-fremd/Admin),
Lebenszyklus open→submitted, Soft-Delete (Admin), Audit-Einträge,
Existenz-Leak-Schutz (404 vs. 403), CSRF.
"""

from __future__ import annotations

import hashlib
import io
import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.domain.models import AuditLog, Person
from ref4ep.services.document_service import DocumentService
from ref4ep.services.permissions import AuthContext


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


# ---- Fixtures-Helper ---------------------------------------------------


def _create_doc(client: TestClient, *, wp_code: str = "WP3", title: str = "Doc") -> str:
    r = client.post(
        f"/api/workpackages/{wp_code}/documents",
        json={"title": title, "document_type": "report"},
        headers=_csrf(client),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _upload_version(client: TestClient, doc_id: str, *, body: bytes = b"%PDF-1.4 x") -> str:
    r = client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": ("v.pdf", io.BytesIO(body), "application/pdf")},
        data={"change_note": "Initial"},
        headers=_csrf(client),
    )
    assert r.status_code == 201, r.text
    # Versionsnummer im Response, aber wir brauchen die UUID.
    # Hole sie über das Document-Detail.
    detail = client.get(f"/api/documents/{doc_id}").json()
    versions = detail["versions"]
    assert len(versions) >= 1
    # Hash matcht?
    expected = hashlib.sha256(body).hexdigest()
    assert any(v["sha256"] == expected for v in versions)
    return next(v for v in versions if v["sha256"] == expected)["id"]


def _create_doc_via_service(
    session: Session, *, wp_code: str = "WP4", title: str = "Fremd", visibility: str | None = None
) -> str:
    """Erstellt Doc + dummy Version direkt am Service (Cookie-Jar-frei)."""
    admin = session.query(Person).filter_by(email="admin@test.example").one()
    auth = AuthContext(
        person_id=admin.id,
        email=admin.email,
        platform_role=admin.platform_role,
        memberships=[],
    )
    doc = DocumentService(session, auth=auth).create(
        workpackage_code=wp_code, title=title, document_type="report"
    )
    if visibility is not None:
        doc.visibility = visibility
    session.commit()
    return doc.id


# ---- Liste pro Version: Sichtbarkeit + Auth-Boundary --------------------


def test_anonymous_cannot_list(
    client: TestClient, member_in_wp3, member_client: TestClient
) -> None:
    doc_id = _create_doc(member_client)
    version_id = _upload_version(member_client, doc_id)
    client.cookies.clear()
    r = client.get(f"/api/document-versions/{version_id}/comments")
    assert r.status_code == 401


def test_member_can_list_empty(member_client: TestClient, member_in_wp3) -> None:
    doc_id = _create_doc(member_client)
    version_id = _upload_version(member_client, doc_id)
    r = member_client.get(f"/api/document-versions/{version_id}/comments")
    assert r.status_code == 200
    assert r.json() == []


def test_unknown_version_returns_404(member_client: TestClient, member_in_wp3) -> None:
    r = member_client.get("/api/document-versions/00000000-0000-0000-0000-000000000000/comments")
    assert r.status_code == 404


def test_invisible_document_returns_404(
    member_client: TestClient, member_in_wp3, admin_person_id: str, seeded_session: Session
) -> None:
    """Doc liegt in WP4 (member ist nur in WP3) → unsichtbar → 404."""
    doc_id = _create_doc_via_service(seeded_session, wp_code="WP4")
    # Hole via Admin-Service eine Version. Vereinfacht: wir pflanzen direkt eine.
    from ref4ep.domain.models import Document, DocumentVersion

    doc = seeded_session.get(Document, doc_id)
    admin = seeded_session.query(Person).filter_by(email="admin@test.example").one()
    v = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        change_note="dummy",
        storage_key="x",
        original_filename="x.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        sha256="0" * 64,
        uploaded_by_person_id=admin.id,
    )
    seeded_session.add(v)
    seeded_session.commit()
    r = member_client.get(f"/api/document-versions/{v.id}/comments")
    assert r.status_code == 404


# ---- POST: Anlegen, Berechtigungen ------------------------------------


def test_member_can_create_on_own_wp_doc(member_client: TestClient, member_in_wp3) -> None:
    doc_id = _create_doc(member_client)
    version_id = _upload_version(member_client, doc_id)
    r = member_client.post(
        f"/api/document-versions/{version_id}/comments",
        json={"text": "Bitte Kapitel 3 prüfen."},
        headers=_csrf(member_client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "open"
    assert body["text"] == "Bitte Kapitel 3 prüfen."
    assert body["submitted_at"] is None
    assert body["document_version"]["id"] == version_id


def test_create_strips_text(member_client: TestClient, member_in_wp3) -> None:
    doc_id = _create_doc(member_client)
    version_id = _upload_version(member_client, doc_id)
    r = member_client.post(
        f"/api/document-versions/{version_id}/comments",
        json={"text": "  Padding rundherum  "},
        headers=_csrf(member_client),
    )
    assert r.status_code == 201
    assert r.json()["text"] == "Padding rundherum"


def test_create_empty_returns_422(member_client: TestClient, member_in_wp3) -> None:
    doc_id = _create_doc(member_client)
    version_id = _upload_version(member_client, doc_id)
    r = member_client.post(
        f"/api/document-versions/{version_id}/comments",
        json={"text": "   "},
        headers=_csrf(member_client),
    )
    assert r.status_code == 422


def test_create_without_csrf_returns_403(member_client: TestClient, member_in_wp3) -> None:
    doc_id = _create_doc(member_client)
    version_id = _upload_version(member_client, doc_id)
    r = member_client.post(f"/api/document-versions/{version_id}/comments", json={"text": "x"})
    assert r.status_code == 403


def test_member_cannot_comment_on_foreign_wp_draft(
    member_client: TestClient,
    member_in_wp3,
    admin_person_id: str,
    seeded_session: Session,
) -> None:
    """WP4-Draft + visibility=internal → Member kann lesen, aber nicht
    kommentieren (kein WP-Mitglied, Doc nicht released → 403)."""
    doc_id = _create_doc_via_service(seeded_session, wp_code="WP4", visibility="internal")
    from ref4ep.domain.models import Document, DocumentVersion

    doc = seeded_session.get(Document, doc_id)
    admin = seeded_session.query(Person).filter_by(email="admin@test.example").one()
    v = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        change_note="dummy",
        storage_key="x",
        original_filename="x.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        sha256="1" * 64,
        uploaded_by_person_id=admin.id,
    )
    seeded_session.add(v)
    seeded_session.commit()
    # Sanity: Member darf lesen
    assert member_client.get(f"/api/documents/{doc_id}").status_code == 200
    # Aber nicht kommentieren
    r = member_client.post(
        f"/api/document-versions/{v.id}/comments",
        json={"text": "fremder Comment"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_member_can_comment_on_released_foreign_doc(
    member_client: TestClient,
    member_in_wp3,
    admin_person_id: str,
    seeded_session: Session,
) -> None:
    """WP4-Doc auf released + internal → jeder Konsortium-Member darf
    kommentieren."""
    doc_id = _create_doc_via_service(seeded_session, wp_code="WP4", visibility="internal")
    from ref4ep.domain.models import Document, DocumentVersion

    doc = seeded_session.get(Document, doc_id)
    doc.status = "released"
    admin = seeded_session.query(Person).filter_by(email="admin@test.example").one()
    v = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        change_note="dummy",
        storage_key="x",
        original_filename="x.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        sha256="2" * 64,
        uploaded_by_person_id=admin.id,
    )
    seeded_session.add(v)
    seeded_session.commit()
    r = member_client.post(
        f"/api/document-versions/{v.id}/comments",
        json={"text": "Reviewer-Kommentar"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 201, r.text


# ---- Visibility ``open`` only for author -------------------------------


def test_open_comment_invisible_to_other_member(
    admin_client: TestClient,
    admin_person_id: str,
    member_in_wp3,
    seeded_session: Session,
    app,
) -> None:
    """Admin legt Comment an. Member sieht ihn NICHT in der Versionsliste,
    weil Status open + nicht-Autor + nicht-Admin."""
    # Doc + Version als Admin anlegen + Comment als Admin
    doc_id = _create_doc(admin_client, wp_code="WP3")
    version_id = _upload_version(admin_client, doc_id)
    cr = admin_client.post(
        f"/api/document-versions/{version_id}/comments",
        json={"text": "Admin-Notiz"},
        headers=_csrf(admin_client),
    )
    assert cr.status_code == 201

    # Member-Sicht via separater Client
    member = TestClient(app)
    login = member.post(
        "/api/auth/login",
        json={"email": "member@test.example", "password": "M3mberP4ssword!"},
    )
    assert login.status_code == 200
    r = member.get(f"/api/document-versions/{version_id}/comments")
    assert r.status_code == 200
    assert r.json() == []
    member.close()


# ---- Lebenszyklus: submit, update --------------------------------------


def test_submit_freezes_comment(member_client: TestClient, member_in_wp3) -> None:
    doc_id = _create_doc(member_client)
    version_id = _upload_version(member_client, doc_id)
    cr = member_client.post(
        f"/api/document-versions/{version_id}/comments",
        json={"text": "Erste Version"},
        headers=_csrf(member_client),
    )
    cid = cr.json()["id"]

    # Submit
    sr = member_client.post(f"/api/document-comments/{cid}/submit", headers=_csrf(member_client))
    assert sr.status_code == 200, sr.text
    body = sr.json()
    assert body["status"] == "submitted"
    assert body["submitted_at"] is not None

    # Zweiter Submit → 422 (bereits eingereicht)
    sr2 = member_client.post(f"/api/document-comments/{cid}/submit", headers=_csrf(member_client))
    assert sr2.status_code == 422

    # Update nach Submit → 422
    ur = member_client.patch(
        f"/api/document-comments/{cid}",
        json={"text": "Geändert"},
        headers=_csrf(member_client),
    )
    assert ur.status_code == 422


def test_update_open_comment(member_client: TestClient, member_in_wp3) -> None:
    doc_id = _create_doc(member_client)
    version_id = _upload_version(member_client, doc_id)
    cr = member_client.post(
        f"/api/document-versions/{version_id}/comments",
        json={"text": "Erstfassung"},
        headers=_csrf(member_client),
    )
    cid = cr.json()["id"]
    ur = member_client.patch(
        f"/api/document-comments/{cid}",
        json={"text": "Korrigiert"},
        headers=_csrf(member_client),
    )
    assert ur.status_code == 200
    assert ur.json()["text"] == "Korrigiert"


def test_other_member_cannot_update_or_submit(
    admin_client: TestClient,
    admin_person_id: str,
    member_in_wp3,
    seeded_session: Session,
    app,
) -> None:
    # Admin legt einen open-Comment an
    doc_id = _create_doc(admin_client, wp_code="WP3")
    version_id = _upload_version(admin_client, doc_id)
    cr = admin_client.post(
        f"/api/document-versions/{version_id}/comments",
        json={"text": "Admin-only"},
        headers=_csrf(admin_client),
    )
    cid = cr.json()["id"]

    # Submit dann, damit Member ihn sehen darf — aber Update/Submit/Delete dürfen nicht.
    admin_client.post(f"/api/document-comments/{cid}/submit", headers=_csrf(admin_client))

    member = TestClient(app)
    member.post(
        "/api/auth/login",
        json={"email": "member@test.example", "password": "M3mberP4ssword!"},
    )
    # Member sieht den submitted Comment.
    assert member.get(f"/api/document-comments/{cid}").status_code == 200
    # Update versucht → 422 (submitted unveränderlich) — aber 403 wäre auch akzeptabel
    # je nach Reihenfolge der Checks. Tatsächlich: PermissionError zuerst (nicht Autor) → 403.
    ur = member.patch(
        f"/api/document-comments/{cid}",
        json={"text": "Hack"},
        headers={"X-CSRF-Token": member.cookies.get("ref4ep_csrf") or ""},
    )
    assert ur.status_code == 403
    member.close()


# ---- Admin Soft-Delete --------------------------------------------------


def test_admin_can_soft_delete(
    member_client: TestClient,
    member_in_wp3,
    admin_person_id: str,
    seeded_session: Session,
    app,
) -> None:
    doc_id = _create_doc(member_client)
    version_id = _upload_version(member_client, doc_id)
    cr = member_client.post(
        f"/api/document-versions/{version_id}/comments",
        json={"text": "Member-Comment"},
        headers=_csrf(member_client),
    )
    cid = cr.json()["id"]
    member_client.post(f"/api/document-comments/{cid}/submit", headers=_csrf(member_client))

    admin = TestClient(app)
    admin.post(
        "/api/auth/login",
        json={"email": "admin@test.example", "password": "Adm1nP4ssword!"},
    )
    dr = admin.delete(
        f"/api/document-comments/{cid}",
        headers={"X-CSRF-Token": admin.cookies.get("ref4ep_csrf") or ""},
    )
    assert dr.status_code == 204

    # Comment ist nach Soft-Delete in der Liste verschwunden.
    lst = member_client.get(f"/api/document-versions/{version_id}/comments")
    assert lst.status_code == 200
    assert lst.json() == []

    # Direkter GET → 404
    g = admin.get(f"/api/document-comments/{cid}")
    assert g.status_code == 404
    admin.close()


def test_member_cannot_delete(member_client: TestClient, member_in_wp3) -> None:
    doc_id = _create_doc(member_client)
    version_id = _upload_version(member_client, doc_id)
    cr = member_client.post(
        f"/api/document-versions/{version_id}/comments",
        json={"text": "Mein eigener"},
        headers=_csrf(member_client),
    )
    cid = cr.json()["id"]
    dr = member_client.delete(f"/api/document-comments/{cid}", headers=_csrf(member_client))
    assert dr.status_code == 403


# ---- Audit-Einträge -----------------------------------------------------


def test_audit_create_submit_delete(
    member_client: TestClient,
    member_in_wp3,
    admin_person_id: str,
    seeded_session: Session,
    app,
) -> None:
    doc_id = _create_doc(member_client)
    version_id = _upload_version(member_client, doc_id)
    cid = member_client.post(
        f"/api/document-versions/{version_id}/comments",
        json={"text": "Erst"},
        headers=_csrf(member_client),
    ).json()["id"]
    member_client.patch(
        f"/api/document-comments/{cid}",
        json={"text": "Zweit"},
        headers=_csrf(member_client),
    )
    member_client.post(f"/api/document-comments/{cid}/submit", headers=_csrf(member_client))

    admin = TestClient(app)
    admin.post(
        "/api/auth/login", json={"email": "admin@test.example", "password": "Adm1nP4ssword!"}
    )
    admin.delete(
        f"/api/document-comments/{cid}",
        headers={"X-CSRF-Token": admin.cookies.get("ref4ep_csrf") or ""},
    )
    admin.close()

    actions = (
        seeded_session.query(AuditLog)
        .filter(AuditLog.entity_id == cid)
        .order_by(AuditLog.created_at)
        .all()
    )
    actions_seen = [a.action for a in actions]
    assert actions_seen == [
        "document_comment.create",
        "document_comment.update",
        "document_comment.submit",
        "document_comment.delete",
    ]
    update_payload = json.loads(actions[1].details)
    assert update_payload["before"]["text"] == "Erst"
    assert update_payload["after"]["text"] == "Zweit"
    submit_payload = json.loads(actions[2].details)
    assert submit_payload["after"]["status"] == "submitted"
    assert submit_payload["after"]["submitted_at"] is not None


# ---- Globale Liste ------------------------------------------------------


def test_global_list_filters(member_client: TestClient, member_in_wp3) -> None:
    doc_id = _create_doc(member_client)
    version_id = _upload_version(member_client, doc_id)
    member_client.post(
        f"/api/document-versions/{version_id}/comments",
        json={"text": "A"},
        headers=_csrf(member_client),
    )
    cid = member_client.post(
        f"/api/document-versions/{version_id}/comments",
        json={"text": "B"},
        headers=_csrf(member_client),
    ).json()["id"]
    member_client.post(f"/api/document-comments/{cid}/submit", headers=_csrf(member_client))

    all_for_v = member_client.get(f"/api/document-comments?document_version_id={version_id}").json()
    assert len(all_for_v) == 2
    submitted_only = member_client.get(
        f"/api/document-comments?document_version_id={version_id}&status=submitted"
    ).json()
    assert len(submitted_only) == 1
    assert submitted_only[0]["text"] == "B"


def test_global_list_invalid_status_returns_422(member_client: TestClient, member_in_wp3) -> None:
    r = member_client.get("/api/document-comments?status=garbage")
    # Pydantic Literal-Validation greift bereits auf Routenebene → 422
    assert r.status_code == 422
