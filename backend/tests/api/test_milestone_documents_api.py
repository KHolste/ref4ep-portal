"""API: /api/milestones/{id}/documents (Block 0039)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.domain.models import Person
from ref4ep.services.document_service import DocumentService
from ref4ep.services.milestone_document_service import MilestoneDocumentService
from ref4ep.services.milestone_service import MilestoneService
from ref4ep.services.permissions import AuthContext
from ref4ep.services.workpackage_service import WorkpackageService


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def _create_library_doc(session: Session, title: str = "Lib") -> str:
    admin = session.query(Person).filter_by(email="admin@test.example").first()
    if admin is None:
        # Falls der admin-Client noch nicht angelegt hat, nehmen wir den
        # ersten Admin aus dem Seed.
        admin = session.query(Person).filter_by(platform_role="admin").first()
        assert admin is not None
    auth = AuthContext(person_id=admin.id, email=admin.email, platform_role="admin", memberships=[])
    doc = DocumentService(session, auth=auth).create(
        workpackage_code=None,
        title=title,
        document_type="other",
        library_section="project",
        visibility="internal",
    )
    session.commit()
    return doc.id


# ---- GET --------------------------------------------------------------------


def test_anonymous_cannot_list(client: TestClient, seeded_session: Session) -> None:
    client.cookies.clear()
    ms = MilestoneService(seeded_session).get_by_code("MS3")
    r = client.get(f"/api/milestones/{ms.id}/documents")
    assert r.status_code == 401


def _admin_auth(session: Session) -> AuthContext:
    admin = session.query(Person).filter_by(email="admin@test.example").first()
    assert admin is not None
    return AuthContext(person_id=admin.id, email=admin.email, platform_role="admin", memberships=[])


def _link_via_service(session: Session, milestone_id: str, document_id: str) -> None:
    auth = _admin_auth(session)
    MilestoneDocumentService(session, role="admin", person_id=auth.person_id, auth=auth).add_link(
        milestone_id, document_id=document_id
    )
    session.commit()


def test_member_lists_visible_only(
    member_client: TestClient,
    admin_person_id: str,
    seeded_session: Session,
) -> None:
    ms = MilestoneService(seeded_session).get_by_code("MS3")
    doc_id = _create_library_doc(seeded_session, title="ApiViz")
    _link_via_service(seeded_session, ms.id, doc_id)

    r = member_client.get(f"/api/milestones/{ms.id}/documents")
    assert r.status_code == 200
    titles = {item["title"] for item in r.json()}
    assert "ApiViz" in titles


def test_list_unknown_milestone_404(admin_client: TestClient) -> None:
    r = admin_client.get("/api/milestones/00000000-0000-0000-0000-000000000000/documents")
    assert r.status_code == 404


# ---- POST -------------------------------------------------------------------


def test_member_cannot_link(
    admin_client: TestClient,
    member_client: TestClient,
    seeded_session: Session,
) -> None:
    ms = MilestoneService(seeded_session).get_by_code("MS3")
    doc_id = _create_library_doc(seeded_session, title="MemberFail")
    r = member_client.post(
        f"/api/milestones/{ms.id}/documents",
        json={"document_id": doc_id},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_wp_lead_can_link_own_wp(
    admin_client: TestClient,
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
) -> None:
    wp = WorkpackageService(seeded_session, role="admin", person_id="fixture").get_by_code("WP3.1")
    assert wp is not None
    WorkpackageService(seeded_session, role="admin", person_id="fixture").add_membership(
        member_person_id, wp.id, "wp_lead"
    )
    seeded_session.commit()
    ms = MilestoneService(seeded_session).get_by_code("MS3")
    doc_id = _create_library_doc(seeded_session, title="LeadOK")
    r = member_client.post(
        f"/api/milestones/{ms.id}/documents",
        json={"document_id": doc_id},
        headers=_csrf(member_client),
    )
    assert r.status_code == 201, r.text


def test_wp_lead_cannot_link_overall_project_milestone(
    admin_client: TestClient,
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
) -> None:
    wp = WorkpackageService(seeded_session, role="admin", person_id="fixture").get_by_code("WP3.1")
    WorkpackageService(seeded_session, role="admin", person_id="fixture").add_membership(
        member_person_id, wp.id, "wp_lead"
    )
    seeded_session.commit()
    ms4 = MilestoneService(seeded_session).get_by_code("MS4")
    assert ms4.workpackage_id is None
    doc_id = _create_library_doc(seeded_session, title="OverallFail")
    r = member_client.post(
        f"/api/milestones/{ms4.id}/documents",
        json={"document_id": doc_id},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_csrf_required_for_post(admin_client: TestClient, seeded_session: Session) -> None:
    ms = MilestoneService(seeded_session).get_by_code("MS3")
    doc_id = _create_library_doc(seeded_session, title="CsrfTest")
    r = admin_client.post(
        f"/api/milestones/{ms.id}/documents",
        json={"document_id": doc_id},
    )
    assert r.status_code == 403


def test_duplicate_link_returns_409(admin_client: TestClient, seeded_session: Session) -> None:
    ms = MilestoneService(seeded_session).get_by_code("MS3")
    doc_id = _create_library_doc(seeded_session, title="DupTest")
    r1 = admin_client.post(
        f"/api/milestones/{ms.id}/documents",
        json={"document_id": doc_id},
        headers=_csrf(admin_client),
    )
    assert r1.status_code == 201, r1.text
    r2 = admin_client.post(
        f"/api/milestones/{ms.id}/documents",
        json={"document_id": doc_id},
        headers=_csrf(admin_client),
    )
    assert r2.status_code == 409


# ---- DELETE -----------------------------------------------------------------


def test_admin_can_delete_link(admin_client: TestClient, seeded_session: Session) -> None:
    ms = MilestoneService(seeded_session).get_by_code("MS3")
    doc_id = _create_library_doc(seeded_session, title="DelTest")
    admin_client.post(
        f"/api/milestones/{ms.id}/documents",
        json={"document_id": doc_id},
        headers=_csrf(admin_client),
    )
    r = admin_client.delete(
        f"/api/milestones/{ms.id}/documents/{doc_id}",
        headers=_csrf(admin_client),
    )
    assert r.status_code == 204


def test_delete_unknown_link_404(admin_client: TestClient, seeded_session: Session) -> None:
    ms = MilestoneService(seeded_session).get_by_code("MS3")
    r = admin_client.delete(
        f"/api/milestones/{ms.id}/documents/00000000-0000-0000-0000-000000000000",
        headers=_csrf(admin_client),
    )
    assert r.status_code == 404


# ---- Dokument-Detail enthält linked_milestones -----------------------------


def test_document_detail_shows_linked_milestones(
    admin_client: TestClient, seeded_session: Session
) -> None:
    ms = MilestoneService(seeded_session).get_by_code("MS3")
    doc_id = _create_library_doc(seeded_session, title="LinkedToMs3")
    admin_client.post(
        f"/api/milestones/{ms.id}/documents",
        json={"document_id": doc_id},
        headers=_csrf(admin_client),
    )
    r = admin_client.get(f"/api/documents/{doc_id}")
    assert r.status_code == 200
    body = r.json()
    codes = [m["code"] for m in body["linked_milestones"]]
    assert codes == ["MS3"]
