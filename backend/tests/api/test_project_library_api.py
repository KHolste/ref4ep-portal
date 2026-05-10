"""API-Tests: Projektbibliothek (Block 0035).

Schwerpunkt: Sichtbarkeit über ``enforce_visibility``,
Bibliotheks-Filter, Anlage von Dokumenten ohne WP-Bezug.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.domain.models import Document, Person
from ref4ep.services.document_service import DocumentService
from ref4ep.services.permissions import AuthContext


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def _admin_auth(session: Session) -> AuthContext:
    admin = session.query(Person).filter_by(email="admin@test.example").one()
    return AuthContext(person_id=admin.id, email=admin.email, platform_role="admin", memberships=[])


def _create_library_doc_via_service(
    session: Session, *, title: str, library_section: str | None, visibility: str = "internal"
) -> str:
    auth = _admin_auth(session)
    doc = DocumentService(session, auth=auth).create(
        workpackage_code=None,
        title=title,
        document_type="other",
        library_section=library_section,
        visibility=visibility,
    )
    session.commit()
    return doc.id


# ---- Auth + Permission -----------------------------------------------


def test_anonymous_cannot_create_library_document(client: TestClient) -> None:
    client.cookies.clear()
    r = client.post("/api/library/documents", json={"title": "x"})
    assert r.status_code in (401, 403)


def test_member_cannot_create_library_document(member_client: TestClient) -> None:
    r = member_client.post(
        "/api/library/documents",
        json={"title": "Privat", "document_type": "other"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_admin_can_create_library_document_without_workpackage(
    admin_client: TestClient, seeded_session: Session
) -> None:
    r = admin_client.post(
        "/api/library/documents",
        json={
            "title": "Konsortialvereinbarung",
            "document_type": "other",
            "library_section": "project",
            "visibility": "internal",
            "description": "Stand bei Antragstellung.",
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["workpackage"] is None
    assert body["library_section"] == "project"
    assert body["visibility"] == "internal"


def test_admin_cannot_create_library_document_with_invalid_section(
    admin_client: TestClient,
) -> None:
    r = admin_client.post(
        "/api/library/documents",
        json={"title": "x", "document_type": "other", "library_section": "bogus"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 422


def test_admin_cannot_create_library_document_with_workpackage_visibility(
    admin_client: TestClient,
) -> None:
    """Sichtbarkeit ``workpackage`` ist ohne WP-Bezug nicht erlaubt;
    Schema akzeptiert sie nicht und liefert 422."""
    r = admin_client.post(
        "/api/library/documents",
        json={"title": "x", "document_type": "other", "visibility": "workpackage"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 422


# ---- Listen + Filter -------------------------------------------------


@pytest.fixture
def library_docs(seeded_session: Session, admin_person_id: str) -> dict[str, str]:
    """Setup: drei Bibliotheksdokumente mit verschiedenen Bereichen."""
    return {
        "project": _create_library_doc_via_service(
            seeded_session, title="Projektantrag", library_section="project"
        ),
        "literature": _create_library_doc_via_service(
            seeded_session, title="Standard XYZ", library_section="literature"
        ),
        "thesis": _create_library_doc_via_service(
            seeded_session, title="MA Müller", library_section="thesis"
        ),
    }


def test_library_section_filter_returns_only_that_section(
    admin_client: TestClient, library_docs: dict[str, str]
) -> None:
    r = admin_client.get("/api/documents?library_section=literature")
    assert r.status_code == 200
    sections = {d["library_section"] for d in r.json()}
    assert sections == {"literature"}


def test_without_workpackage_filter_returns_only_library_documents(
    admin_client: TestClient, library_docs: dict[str, str]
) -> None:
    r = admin_client.get("/api/documents?without_workpackage=true")
    assert r.status_code == 200
    body = r.json()
    assert body
    for d in body:
        assert d["workpackage_code"] is None


def test_invalid_library_section_filter_is_422(admin_client: TestClient) -> None:
    r = admin_client.get("/api/documents?library_section=bogus")
    assert r.status_code == 422


def test_enforce_visibility_drops_documents_user_cannot_read(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    """Ein Dokument mit ``visibility=public`` und ``status=draft`` ist
    nur für Admins sichtbar — `released` fehlt für anonymen Pfad,
    `internal` greift nicht bei `public`-Visibility, und ohne WP-Bezug
    auch keine WP-Mitgliedschaftspfade. Mit ``enforce_visibility=true``
    darf der Member es deshalb nicht in der Liste sehen."""
    admin_only_id = _create_library_doc_via_service(
        seeded_session,
        title="Public-Draft",
        library_section="project",
        visibility="public",
    )
    doc = seeded_session.get(Document, admin_only_id)
    assert doc.status == "draft"
    assert doc.visibility == "public"

    # Ohne enforce: Liste filtert NICHT auf Sichtbarkeit (Auswahllisten-
    # Modus) — Member sieht es trotzdem.
    r_loose = member_client.get("/api/documents?library_section=project")
    assert any(d["id"] == admin_only_id for d in r_loose.json())
    # Mit enforce: Member sieht es nicht mehr.
    r_strict = member_client.get("/api/documents?library_section=project&enforce_visibility=true")
    assert all(d["id"] != admin_only_id for d in r_strict.json())


def test_status_filter_works(admin_client: TestClient, library_docs: dict[str, str]) -> None:
    r = admin_client.get("/api/documents?status_filter=draft&without_workpackage=true")
    assert r.status_code == 200
    statuses = {d["status"] for d in r.json()}
    assert statuses <= {"draft"}


def test_admin_can_create_library_document_with_paper_type(
    admin_client: TestClient, seeded_session: Session
) -> None:
    """Block 0035-Folgepatch: ``document_type='paper'`` wird vom
    erweiterten CHECK-Constraint und vom Service akzeptiert."""
    r = admin_client.post(
        "/api/library/documents",
        json={
            "title": "Recommended Practices Paper",
            "document_type": "paper",
            "library_section": "literature",
            "visibility": "internal",
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["document_type"] == "paper"
    assert body["library_section"] == "literature"
