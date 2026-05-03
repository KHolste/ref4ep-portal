"""DocumentLifecycleService — Status, Release, Visibility, Audit."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from ref4ep.domain.models import AuditLog
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.document_lifecycle_service import (
    DocumentLifecycleService,
    InvalidStatusTransitionError,
)
from ref4ep.services.document_service import DocumentNotFoundError, DocumentService
from ref4ep.services.document_version_service import DocumentVersionService
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.permissions import AuthContext, MembershipInfo
from ref4ep.services.person_service import PersonService
from ref4ep.services.workpackage_service import WorkpackageService
from ref4ep.storage.local import LocalFileStorage


def _make_auth(seeded_session: Session, *, wp_role: str | None) -> tuple[str, AuthContext]:
    partner = PartnerService(seeded_session).get_by_short_name("JLU")
    person = PersonService(seeded_session, role="admin").create(
        email=f"life-{wp_role or 'none'}@test.example",
        display_name=f"Life {wp_role or 'none'}",
        partner_id=partner.id,
        password="StrongPw1!",
    )
    seeded_session.commit()
    wp = WorkpackageService(seeded_session).get_by_code("WP3")
    memberships = (
        [MembershipInfo(workpackage_id=wp.id, workpackage_code=wp.code, wp_role=wp_role)]
        if wp_role
        else []
    )
    auth = AuthContext(
        person_id=person.id,
        email=person.email,
        platform_role="member",
        memberships=memberships,
    )
    return wp.id, auth


def _create_doc_with_version(
    seeded_session: Session,
    auth: AuthContext,
    storage: LocalFileStorage,
    *,
    body: bytes = b"%PDF-1.4 inhalt",
) -> str:
    doc = DocumentService(seeded_session, auth=auth).create(
        workpackage_code="WP3", title="Konstruktion", document_type="deliverable"
    )
    seeded_session.commit()
    DocumentVersionService(seeded_session, auth=auth, storage=storage).upload_new_version(
        doc.id,
        file_stream=io.BytesIO(body),
        original_filename="v1.pdf",
        mime_type="application/pdf",
        change_note="Initial-Entwurf",
    )
    seeded_session.commit()
    return doc.id


def test_set_status_requires_at_least_one_version(
    seeded_session: Session, tmp_storage_dir: Path
) -> None:
    _, auth = _make_auth(seeded_session, wp_role="wp_member")
    doc = DocumentService(seeded_session, auth=auth).create(
        workpackage_code="WP3", title="Leerdoc", document_type="note"
    )
    seeded_session.commit()
    svc = DocumentLifecycleService(seeded_session, auth=auth)
    with pytest.raises(ValueError):
        svc.set_status(doc.id, to="in_review")


def test_set_status_writes_audit(seeded_session: Session, tmp_storage_dir: Path) -> None:
    _, auth = _make_auth(seeded_session, wp_role="wp_member")
    storage = LocalFileStorage(tmp_storage_dir)
    doc_id = _create_doc_with_version(seeded_session, auth, storage)
    audit = AuditLogger(seeded_session, actor_person_id=auth.person_id)
    svc = DocumentLifecycleService(seeded_session, auth=auth, audit=audit)
    svc.set_status(doc_id, to="in_review")
    seeded_session.commit()
    entry = seeded_session.query(AuditLog).filter_by(action="document.set_status").one()
    assert entry.entity_id == doc_id


def test_release_requires_wp_lead(seeded_session: Session, tmp_storage_dir: Path) -> None:
    _, member_auth = _make_auth(seeded_session, wp_role="wp_member")
    storage = LocalFileStorage(tmp_storage_dir)
    doc_id = _create_doc_with_version(seeded_session, member_auth, storage)
    DocumentLifecycleService(seeded_session, auth=member_auth).set_status(doc_id, to="in_review")
    seeded_session.commit()
    with pytest.raises(PermissionError):
        DocumentLifecycleService(seeded_session, auth=member_auth).release(doc_id, version_number=1)


def test_release_as_wp_lead_sets_status_and_id(
    seeded_session: Session, tmp_storage_dir: Path
) -> None:
    _, member_auth = _make_auth(seeded_session, wp_role="wp_member")
    storage = LocalFileStorage(tmp_storage_dir)
    doc_id = _create_doc_with_version(seeded_session, member_auth, storage)
    DocumentLifecycleService(seeded_session, auth=member_auth).set_status(doc_id, to="in_review")
    seeded_session.commit()

    _, lead_auth = _make_auth(seeded_session, wp_role="wp_lead")
    audit = AuditLogger(seeded_session, actor_person_id=lead_auth.person_id)
    svc = DocumentLifecycleService(seeded_session, auth=lead_auth, audit=audit)
    document = svc.release(doc_id, version_number=1)
    seeded_session.commit()
    assert document.status == "released"
    assert document.released_version_id is not None
    entry = seeded_session.query(AuditLog).filter_by(action="document.release").one()
    assert entry.entity_id == doc_id


def test_release_with_unknown_version_raises_not_found(
    seeded_session: Session, tmp_storage_dir: Path
) -> None:
    _, lead_auth = _make_auth(seeded_session, wp_role="wp_lead")
    storage = LocalFileStorage(tmp_storage_dir)
    doc_id = _create_doc_with_version(seeded_session, lead_auth, storage)
    DocumentLifecycleService(seeded_session, auth=lead_auth).set_status(doc_id, to="in_review")
    seeded_session.commit()
    with pytest.raises(DocumentNotFoundError):
        DocumentLifecycleService(seeded_session, auth=lead_auth).release(doc_id, version_number=99)


def test_release_only_from_in_review_or_released(
    seeded_session: Session, tmp_storage_dir: Path
) -> None:
    _, lead_auth = _make_auth(seeded_session, wp_role="wp_lead")
    storage = LocalFileStorage(tmp_storage_dir)
    doc_id = _create_doc_with_version(seeded_session, lead_auth, storage)
    # Status ist draft → kein direktes Release
    with pytest.raises(InvalidStatusTransitionError):
        DocumentLifecycleService(seeded_session, auth=lead_auth).release(doc_id, version_number=1)


def test_unrelease_only_admin(seeded_session: Session, tmp_storage_dir: Path) -> None:
    _, lead_auth = _make_auth(seeded_session, wp_role="wp_lead")
    storage = LocalFileStorage(tmp_storage_dir)
    doc_id = _create_doc_with_version(seeded_session, lead_auth, storage)
    DocumentLifecycleService(seeded_session, auth=lead_auth).set_status(doc_id, to="in_review")
    DocumentLifecycleService(seeded_session, auth=lead_auth).release(doc_id, version_number=1)
    seeded_session.commit()
    with pytest.raises(PermissionError):
        DocumentLifecycleService(seeded_session, auth=lead_auth).unrelease(doc_id)
    admin_auth = AuthContext(
        person_id="admin-fixture", email="admin@x", platform_role="admin", memberships=[]
    )
    document = DocumentLifecycleService(seeded_session, auth=admin_auth).unrelease(doc_id)
    assert document.status == "draft"
    assert document.released_version_id is None


def test_set_visibility_public_requires_wp_lead(
    seeded_session: Session, tmp_storage_dir: Path
) -> None:
    _, member_auth = _make_auth(seeded_session, wp_role="wp_member")
    storage = LocalFileStorage(tmp_storage_dir)
    doc_id = _create_doc_with_version(seeded_session, member_auth, storage)
    with pytest.raises(PermissionError):
        DocumentLifecycleService(seeded_session, auth=member_auth).set_visibility(
            doc_id, to="public"
        )

    _, lead_auth = _make_auth(seeded_session, wp_role="wp_lead")
    document = DocumentLifecycleService(seeded_session, auth=lead_auth).set_visibility(
        doc_id, to="public"
    )
    assert document.visibility == "public"


def test_set_visibility_internal_allowed_for_member(
    seeded_session: Session, tmp_storage_dir: Path
) -> None:
    _, member_auth = _make_auth(seeded_session, wp_role="wp_member")
    storage = LocalFileStorage(tmp_storage_dir)
    doc_id = _create_doc_with_version(seeded_session, member_auth, storage)
    document = DocumentLifecycleService(seeded_session, auth=member_auth).set_visibility(
        doc_id, to="internal"
    )
    assert document.visibility == "internal"
