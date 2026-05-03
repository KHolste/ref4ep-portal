"""DocumentService."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from ref4ep.services.document_service import (
    DocumentNotFoundError,
    DocumentService,
    slugify,
)
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.permissions import AuthContext, MembershipInfo
from ref4ep.services.person_service import PersonService
from ref4ep.services.workpackage_service import WorkpackageService


def _auth_member_in(seeded_session: Session, person_id: str, wp_code: str) -> AuthContext:
    wp = WorkpackageService(seeded_session).get_by_code(wp_code)
    assert wp is not None
    return AuthContext(
        person_id=person_id,
        email="member@test.example",
        platform_role="member",
        memberships=[
            MembershipInfo(workpackage_id=wp.id, workpackage_code=wp.code, wp_role="wp_member")
        ],
    )


def _make_person(seeded_session: Session) -> str:
    partner = PartnerService(seeded_session).get_by_short_name("JLU")
    assert partner is not None
    person = PersonService(seeded_session, role="admin").create(
        email="doc-author@test.example",
        display_name="Doc Author",
        partner_id=partner.id,
        password="StrongPw1!",
    )
    seeded_session.commit()
    return person.id


def test_slugify_handles_umlauts_and_spaces() -> None:
    assert slugify("Über das Triebwerk!") == "uber-das-triebwerk"
    assert slugify("D3.1 — Konstruktion") == "d3-1-konstruktion"
    assert slugify("   ") == "dokument"


def test_create_requires_membership(seeded_session: Session) -> None:
    pid = _make_person(seeded_session)
    auth = AuthContext(person_id=pid, email="x@y", platform_role="member", memberships=[])
    svc = DocumentService(seeded_session, auth=auth)
    with pytest.raises(PermissionError):
        svc.create(
            workpackage_code="WP3", title="Konstruktionszeichnung", document_type="deliverable"
        )


def test_member_can_create_document(seeded_session: Session) -> None:
    pid = _make_person(seeded_session)
    auth = _auth_member_in(seeded_session, pid, "WP3")
    svc = DocumentService(seeded_session, auth=auth)
    doc = svc.create(
        workpackage_code="WP3",
        title="Konstruktionszeichnung Ref-HT",
        document_type="deliverable",
        deliverable_code="D3.1",
    )
    assert doc.slug == "konstruktionszeichnung-ref-ht"
    assert doc.status == "draft"
    assert doc.visibility == "workpackage"
    assert doc.deliverable_code == "D3.1"


def test_admin_can_create_without_membership(seeded_session: Session) -> None:
    pid = _make_person(seeded_session)
    auth = AuthContext(person_id=pid, email="x@y", platform_role="admin", memberships=[])
    doc = DocumentService(seeded_session, auth=auth).create(
        workpackage_code="WP3", title="Adminliste", document_type="report"
    )
    assert doc.status == "draft"


def test_create_unknown_document_type_raises(seeded_session: Session) -> None:
    pid = _make_person(seeded_session)
    auth = _auth_member_in(seeded_session, pid, "WP3")
    with pytest.raises(ValueError):
        DocumentService(seeded_session, auth=auth).create(
            workpackage_code="WP3", title="X", document_type="unbekannt"
        )


def test_slug_collision_in_same_wp_raises(seeded_session: Session) -> None:
    pid = _make_person(seeded_session)
    auth = _auth_member_in(seeded_session, pid, "WP3")
    svc = DocumentService(seeded_session, auth=auth)
    svc.create(workpackage_code="WP3", title="Doppel", document_type="other")
    seeded_session.commit()
    with pytest.raises(ValueError):
        svc.create(workpackage_code="WP3", title="Doppel", document_type="other")


def test_get_by_id_hides_documents_for_non_members(seeded_session: Session) -> None:
    pid = _make_person(seeded_session)
    member_auth = _auth_member_in(seeded_session, pid, "WP3")
    doc = DocumentService(seeded_session, auth=member_auth).create(
        workpackage_code="WP3", title="Geheimes Dokument", document_type="note"
    )
    seeded_session.commit()
    foreign_auth = AuthContext(
        person_id="foreign", email="x", platform_role="member", memberships=[]
    )
    with pytest.raises(DocumentNotFoundError):
        DocumentService(seeded_session, auth=foreign_auth).get_by_id(doc.id)


def test_update_metadata_requires_write(seeded_session: Session) -> None:
    pid = _make_person(seeded_session)
    member_auth = _auth_member_in(seeded_session, pid, "WP3")
    doc = DocumentService(seeded_session, auth=member_auth).create(
        workpackage_code="WP3", title="Original", document_type="note"
    )
    seeded_session.commit()
    foreign_auth = AuthContext(
        person_id="foreign", email="x", platform_role="member", memberships=[]
    )
    with pytest.raises(PermissionError):
        DocumentService(seeded_session, auth=foreign_auth).update_metadata(
            doc.id, title="Übernommen"
        )
    DocumentService(seeded_session, auth=member_auth).update_metadata(doc.id, title="Korrigiert")
    seeded_session.commit()
    refreshed = DocumentService(seeded_session, auth=member_auth).get_by_id(doc.id)
    assert refreshed.title == "Korrigiert"


def test_list_for_workpackage_excludes_non_members(seeded_session: Session) -> None:
    pid = _make_person(seeded_session)
    member_auth = _auth_member_in(seeded_session, pid, "WP3")
    DocumentService(seeded_session, auth=member_auth).create(
        workpackage_code="WP3", title="Sichtbar für WP3", document_type="report"
    )
    seeded_session.commit()
    other_auth = AuthContext(person_id="other", email="x", platform_role="member", memberships=[])
    listed = DocumentService(seeded_session, auth=other_auth).list_for_workpackage("WP3")
    assert listed == []
