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


def test_member_can_create_library_document(member_client: TestClient) -> None:
    """Eingeloggte Konsortiumsmitglieder dürfen Bibliotheksdokumente
    anlegen — Admin-only ist aufgehoben."""
    r = member_client.post(
        "/api/library/documents",
        json={"title": "Member-Lib", "document_type": "other"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["workpackage"] is None
    assert body["title"] == "Member-Lib"


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


def test_admin_can_create_library_document_with_new_science_types(
    admin_client: TestClient, seeded_session: Session
) -> None:
    """Block 0035-Folgepatch 2: alle neuen wissenschaftlichen Typen
    werden über die Admin-Library-Route akzeptiert."""
    new_types = ["thesis", "presentation", "protocol", "specification", "template", "dataset"]
    for idx, doc_type in enumerate(new_types):
        r = admin_client.post(
            "/api/library/documents",
            json={
                "title": f"{doc_type.title()}-Test {idx}",
                "document_type": doc_type,
                "visibility": "internal",
            },
            headers=_csrf(admin_client),
        )
        assert r.status_code == 201, (doc_type, r.text)
        assert r.json()["document_type"] == doc_type


# ---- Bibliotheks-Schreibrechte für eingeloggte Nutzer -----------------
#
# Bibliotheksdokumente (``workpackage_id IS NULL``) sind für alle
# eingeloggten Konsortiumsmitglieder anlegbar und beschreibbar. WP-
# Dokumente bleiben unverändert an Membership/Admin gebunden. Release/
# Freigabe sowie Soft-Delete bleiben restriktiv (Admin bzw. WP-Lead).


def test_member_can_upload_version_to_library_document(
    member_client: TestClient,
    seeded_session: Session,
    admin_person_id: str,
) -> None:
    """Eingeloggte Member dürfen eine neue Version zu einem
    Bibliotheksdokument hochladen — Admin-only ist aufgehoben."""
    import hashlib
    import io

    doc_id = _create_library_doc_via_service(
        seeded_session, title="Lib-Member-Upload", library_section="project"
    )
    payload = b"%PDF-1.4 member content"
    r = member_client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": ("v1.pdf", io.BytesIO(payload), "application/pdf")},
        data={"change_note": "Erstversion durch Member"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"]["version_number"] == 1
    assert body["version"]["sha256"] == hashlib.sha256(payload).hexdigest()


def test_anonymous_cannot_upload_version_to_library_document(
    client: TestClient,
    seeded_session: Session,
    admin_person_id: str,
) -> None:
    """Anonyme Aufrufer dürfen weiterhin keine neue Version zu einem
    Bibliotheksdokument hochladen — die Schwelle bleibt ‚eingeloggt'."""
    import io

    doc_id = _create_library_doc_via_service(
        seeded_session, title="Lib-Anon-Block", library_section="project"
    )
    client.cookies.clear()
    r = client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4 anon"), "application/pdf")},
        data={"change_note": "darf nicht durchgehen"},
    )
    assert r.status_code in (401, 403)


def test_member_cannot_upload_version_to_wp_document_without_membership(
    member_client: TestClient,
    seeded_session: Session,
    admin_person_id: str,
) -> None:
    """Bibliotheks-Öffnung gilt NICHT für WP-Dokumente: Ein Member ohne
    Membership auf dem zugehörigen WP bleibt mit 403 ausgesperrt."""
    import io

    auth = _admin_auth(seeded_session)
    wp_doc = DocumentService(seeded_session, auth=auth).create(
        workpackage_code="WP3",
        title="WP3-Restricted",
        document_type="report",
    )
    seeded_session.commit()
    r = member_client.post(
        f"/api/documents/{wp_doc.id}/versions",
        files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4 nope"), "application/pdf")},
        data={"change_note": "ohne Membership"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_wp_member_can_still_upload_version_to_wp_document(
    member_client: TestClient, seeded_session: Session, member_in_wp3
) -> None:
    """WP-Membership-Pfad bleibt unverändert: WP-Mitglied darf hochladen."""
    import io

    create = member_client.post(
        "/api/workpackages/WP3/documents",
        json={"title": "WP3-Member-Upload", "document_type": "report"},
        headers=_csrf(member_client),
    )
    assert create.status_code == 201, create.text
    doc_id = create.json()["id"]
    r = member_client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": ("v1.pdf", io.BytesIO(b"%PDF-1.4 wp"), "application/pdf")},
        data={"change_note": "WP-Member-Upload"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 201, r.text


def test_member_cannot_release_library_document(
    member_client: TestClient,
    seeded_session: Session,
    admin_person_id: str,
) -> None:
    """Release-/Freigaberechte bleiben restriktiv: ein Member darf ein
    Bibliotheksdokument NICHT freigeben, obwohl er es jetzt beschreiben
    und in Review schicken darf. Ohne WP-Bezug ist die Freigabe Admin-
    only (``can_release``-Pfad fällt bei ``workpackage_id IS NULL`` auf
    Admin zurück, der WP-Lead-Zweig greift nicht)."""
    import io

    doc_id = _create_library_doc_via_service(
        seeded_session, title="Lib-Release-Block", library_section="project"
    )
    upload = member_client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": ("v1.pdf", io.BytesIO(b"%PDF-1.4 v1"), "application/pdf")},
        data={"change_note": "Member-Upload"},
        headers=_csrf(member_client),
    )
    assert upload.status_code == 201, upload.text
    version_number = upload.json()["version"]["version_number"]
    # Status auf in_review setzen (darf Member auch bei Lib-Docs).
    review = member_client.post(
        f"/api/documents/{doc_id}/status",
        json={"to": "in_review"},
        headers=_csrf(member_client),
    )
    assert review.status_code == 200, review.text
    # Release ist trotz in_review für Member verboten.
    r = member_client.post(
        f"/api/documents/{doc_id}/release",
        json={"version_number": version_number},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_member_cannot_soft_delete_library_document(
    member_client: TestClient,
    seeded_session: Session,
    admin_person_id: str,
) -> None:
    """Soft-Delete bleibt Admin-only — auch bei Bibliotheksdokumenten."""
    doc_id = _create_library_doc_via_service(
        seeded_session, title="Lib-Soft-Delete-Block", library_section="project"
    )
    r = member_client.delete(
        f"/api/documents/{doc_id}",
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


# ---- Block 0050 — fachliche Themenfelder der Projektbibliothek -------

_NEW_THEME_SECTIONS = (
    "technical_documentation",
    "measurement_test_campaigns",
    "round_robin",
    "meetings_minutes",
    "standards_procedures",
    "templates_forms",
    "software_data_formats",
)


@pytest.mark.parametrize("section", _NEW_THEME_SECTIONS)
def test_admin_can_create_library_document_with_new_theme_section(
    admin_client: TestClient, section: str
) -> None:
    """Block 0050 — jeder der sieben neuen ``library_section``-Slugs wird
    vom POST /api/library/documents akzeptiert. Bestehende Slugs sind
    durch eigene Tests bereits abgedeckt."""
    r = admin_client.post(
        "/api/library/documents",
        json={
            "title": f"Theme-Test {section}",
            "document_type": "other",
            "library_section": section,
            "visibility": "internal",
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 201, r.text
    assert r.json()["library_section"] == section


@pytest.mark.parametrize("section", _NEW_THEME_SECTIONS)
def test_library_section_filter_returns_only_new_theme_section(
    admin_client: TestClient,
    seeded_session: Session,
    admin_person_id: str,
    section: str,
) -> None:
    """Listing-Filter ``?library_section=<neuer Slug>`` funktioniert
    weiterhin und liefert nur Dokumente dieses Themenfeldes."""
    _create_library_doc_via_service(
        seeded_session, title=f"Theme-Filter {section}", library_section=section
    )
    r = admin_client.get(f"/api/documents?library_section={section}")
    assert r.status_code == 200, r.text
    sections = {d["library_section"] for d in r.json()}
    assert sections == {section}


def test_unknown_library_section_is_still_rejected(admin_client: TestClient) -> None:
    """Regression: unbekannter ``library_section``-Slug wird weiterhin
    mit 422 abgelehnt, auch nach Aufnahme der neuen Themenfelder."""
    r = admin_client.post(
        "/api/library/documents",
        json={"title": "x", "document_type": "other", "library_section": "no_such_section"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 422


def test_member_can_create_library_document_with_new_theme_section(
    member_client: TestClient,
) -> None:
    """Block 0050 verträgt sich mit Block 0049: eingeloggter Member
    legt ein Bibliotheksdokument mit einem der neuen Themenfelder an
    — kein Admin-only-Rückschritt."""
    r = member_client.post(
        "/api/library/documents",
        json={
            "title": "Member-Theme",
            "document_type": "other",
            "library_section": "round_robin",
            "visibility": "internal",
        },
        headers=_csrf(member_client),
    )
    assert r.status_code == 201, r.text
    assert r.json()["library_section"] == "round_robin"
