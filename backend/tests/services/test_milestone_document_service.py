"""MilestoneDocumentService — Verknüpfen / Entfernen von Dokumenten an
Meilensteine (Block 0039)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from ref4ep.domain.models import AuditLog, MilestoneDocumentLink, Person
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.document_service import DocumentService
from ref4ep.services.milestone_document_service import (
    MilestoneDocumentLinkConflictError,
    MilestoneDocumentLinkNotFoundError,
    MilestoneDocumentService,
    MilestoneNotFoundError,
)
from ref4ep.services.milestone_service import MilestoneService
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.permissions import AuthContext, MembershipInfo
from ref4ep.services.person_service import PersonService
from ref4ep.services.workpackage_service import WorkpackageService


def _ensure_admin(session: Session) -> Person:
    admin = session.query(Person).filter_by(email="admin@test.example").first()
    if admin is None:
        partner = PartnerService(session).get_by_short_name("JLU")
        if partner is None:
            partner = PartnerService(session).create(
                name="Test-JLU", short_name="JLU", country="DE"
            )
        admin = PersonService(session, role="admin").create(
            email="admin@test.example",
            display_name="Admin",
            partner_id=partner.id,
            password="StrongPw1!",
            platform_role="admin",
        )
        session.commit()
    return admin


def _admin_auth(session: Session) -> AuthContext:
    admin = _ensure_admin(session)
    return AuthContext(
        person_id=admin.id,
        email=admin.email,
        platform_role="admin",
        memberships=[],
    )


def _make_member(session: Session, email: str, memberships: list[MembershipInfo]) -> AuthContext:
    partner = PartnerService(session).get_by_short_name("JLU")
    person = PersonService(session, role="admin").create(
        email=email,
        display_name=email,
        partner_id=partner.id,
        password="StrongPw1!",
        platform_role="member",
    )
    session.commit()
    return AuthContext(
        person_id=person.id, email=email, platform_role="member", memberships=memberships
    )


def _wp_lead_auth(session: Session, wp_code: str) -> AuthContext:
    wp = WorkpackageService(session, role="admin", person_id="test-fixture").get_by_code(wp_code)
    assert wp is not None
    auth = _make_member(
        session,
        f"lead-{wp_code}@test.example",
        [MembershipInfo(workpackage_id=wp.id, workpackage_code=wp.code, wp_role="wp_lead")],
    )
    # ``MilestoneService.can_edit`` fragt den WP-Lead über die DB ab,
    # nicht aus ``AuthContext`` — wir müssen die Mitgliedschaft also
    # auch persistieren.
    WorkpackageService(session, role="admin", person_id="test-fixture").add_membership(
        auth.person_id, wp.id, "wp_lead"
    )
    session.commit()
    return auth


def _make_doc(session: Session, auth: AuthContext, title: str = "Doc") -> str:
    doc = DocumentService(session, auth=auth).create(
        workpackage_code=None,
        title=title,
        document_type="other",
        library_section="project",
        visibility="internal",
    )
    session.commit()
    return doc.id


def _service(
    session: Session,
    auth: AuthContext,
    *,
    audit: AuditLogger | None = None,
) -> MilestoneDocumentService:
    return MilestoneDocumentService(
        session,
        role=auth.platform_role,
        person_id=auth.person_id,
        auth=auth,
        audit=audit,
    )


# ---- Permission tests ------------------------------------------------------


def test_admin_can_link_document_to_wp_milestone(seeded_session: Session) -> None:
    auth = _admin_auth(seeded_session)
    doc_id = _make_doc(seeded_session, auth)
    ms = MilestoneService(seeded_session, role="admin", person_id=auth.person_id).get_by_code("MS3")
    assert ms is not None
    link = _service(seeded_session, auth).add_link(ms.id, document_id=doc_id)
    assert link.milestone_id == ms.id
    assert link.document_id == doc_id


def test_wp_lead_can_link_own_wp_milestone(seeded_session: Session) -> None:
    admin_auth = _admin_auth(seeded_session)
    doc_id = _make_doc(seeded_session, admin_auth)
    ms = MilestoneService(seeded_session, role="admin", person_id=admin_auth.person_id).get_by_code(
        "MS3"
    )
    assert ms is not None
    lead_auth = _wp_lead_auth(seeded_session, ms.workpackage.code)
    link = _service(seeded_session, lead_auth).add_link(ms.id, document_id=doc_id)
    assert link is not None


def test_member_cannot_link(seeded_session: Session) -> None:
    admin_auth = _admin_auth(seeded_session)
    doc_id = _make_doc(seeded_session, admin_auth)
    ms = MilestoneService(seeded_session, role="admin", person_id=admin_auth.person_id).get_by_code(
        "MS3"
    )
    assert ms is not None
    member_auth = _make_member(seeded_session, "ms-doc-member@test.example", [])
    with pytest.raises(PermissionError):
        _service(seeded_session, member_auth).add_link(ms.id, document_id=doc_id)


def test_overall_milestone_only_admin_can_link(seeded_session: Session) -> None:
    admin_auth = _admin_auth(seeded_session)
    doc_id = _make_doc(seeded_session, admin_auth)
    ms = MilestoneService(seeded_session, role="admin", person_id=admin_auth.person_id).get_by_code(
        "MS4"
    )
    assert ms is not None
    assert ms.workpackage_id is None
    lead_auth = _wp_lead_auth(seeded_session, "WP3")
    with pytest.raises(PermissionError):
        _service(seeded_session, lead_auth).add_link(ms.id, document_id=doc_id)
    # Admin selbst kann es:
    link = _service(seeded_session, admin_auth).add_link(ms.id, document_id=doc_id)
    assert link.milestone_id == ms.id


def test_unknown_milestone_raises(seeded_session: Session) -> None:
    auth = _admin_auth(seeded_session)
    doc_id = _make_doc(seeded_session, auth)
    with pytest.raises(MilestoneNotFoundError):
        _service(seeded_session, auth).add_link(
            "00000000-0000-0000-0000-000000000000", document_id=doc_id
        )


def test_unknown_document_raises(seeded_session: Session) -> None:
    auth = _admin_auth(seeded_session)
    ms = MilestoneService(seeded_session, role="admin", person_id=auth.person_id).get_by_code("MS3")
    assert ms is not None
    with pytest.raises(MilestoneNotFoundError):
        _service(seeded_session, auth).add_link(
            ms.id, document_id="00000000-0000-0000-0000-000000000000"
        )


# ---- Duplicate + remove ----------------------------------------------------


def test_duplicate_link_raises_conflict(seeded_session: Session) -> None:
    auth = _admin_auth(seeded_session)
    doc_id = _make_doc(seeded_session, auth)
    ms = MilestoneService(seeded_session, role="admin", person_id=auth.person_id).get_by_code("MS3")
    svc = _service(seeded_session, auth)
    svc.add_link(ms.id, document_id=doc_id)
    seeded_session.commit()
    with pytest.raises(MilestoneDocumentLinkConflictError):
        svc.add_link(ms.id, document_id=doc_id)


def test_remove_link_deletes_link_only(seeded_session: Session) -> None:
    auth = _admin_auth(seeded_session)
    doc_id = _make_doc(seeded_session, auth, title="ToDelete")
    ms = MilestoneService(seeded_session, role="admin", person_id=auth.person_id).get_by_code("MS3")
    svc = _service(seeded_session, auth)
    svc.add_link(ms.id, document_id=doc_id)
    seeded_session.commit()
    svc.remove_link(ms.id, document_id=doc_id)
    seeded_session.commit()
    remaining = (
        seeded_session.query(MilestoneDocumentLink)
        .filter_by(milestone_id=ms.id, document_id=doc_id)
        .all()
    )
    assert remaining == []
    # Dokument selbst existiert weiter:
    assert DocumentService(seeded_session, auth=auth).get_by_id(doc_id).title == "ToDelete"


def test_remove_unknown_link_raises(seeded_session: Session) -> None:
    auth = _admin_auth(seeded_session)
    doc_id = _make_doc(seeded_session, auth)
    ms = MilestoneService(seeded_session, role="admin", person_id=auth.person_id).get_by_code("MS3")
    with pytest.raises(MilestoneDocumentLinkNotFoundError):
        _service(seeded_session, auth).remove_link(ms.id, document_id=doc_id)


# ---- Visibility filter -----------------------------------------------------


def test_list_documents_filters_by_visibility(seeded_session: Session) -> None:
    admin_auth = _admin_auth(seeded_session)
    # Internal-Dokument — sichtbar für eingeloggte Members.
    doc_visible = _make_doc(seeded_session, admin_auth, title="Visible")
    # Verstecktes Dokument: visibility=workpackage UND workpackage_id=None
    # ⇒ Members können es laut Defense-in-Depth NICHT lesen.
    doc_hidden = _make_doc(seeded_session, admin_auth, title="Hidden")
    from ref4ep.domain.models import Document

    doc_hidden_obj = seeded_session.get(Document, doc_hidden)
    doc_hidden_obj.visibility = "workpackage"
    seeded_session.commit()

    ms = MilestoneService(seeded_session, role="admin", person_id=admin_auth.person_id).get_by_code(
        "MS3"
    )
    svc_admin = _service(seeded_session, admin_auth)
    svc_admin.add_link(ms.id, document_id=doc_visible)
    svc_admin.add_link(ms.id, document_id=doc_hidden)
    seeded_session.commit()

    member_auth = _make_member(seeded_session, "viz-member@test.example", [])
    member_svc = _service(seeded_session, member_auth)
    titles = {link.document.title for link in member_svc.list_documents(ms.id)}
    assert "Visible" in titles
    assert "Hidden" not in titles


# ---- Audit -----------------------------------------------------------------


def test_audit_writes_add_and_remove(seeded_session: Session) -> None:
    auth = _admin_auth(seeded_session)
    doc_id = _make_doc(seeded_session, auth, title="Audited")
    ms = MilestoneService(seeded_session, role="admin", person_id=auth.person_id).get_by_code("MS3")
    audit = AuditLogger(seeded_session, actor_person_id=auth.person_id, actor_label=auth.email)
    svc = _service(seeded_session, auth, audit=audit)
    svc.add_link(ms.id, document_id=doc_id)
    seeded_session.commit()
    svc.remove_link(ms.id, document_id=doc_id)
    seeded_session.commit()

    actions = [
        a.action
        for a in seeded_session.query(AuditLog)
        .filter(AuditLog.entity_type == "milestone_document_link")
        .all()
    ]
    assert "milestone.document_link.add" in actions
    assert "milestone.document_link.remove" in actions
