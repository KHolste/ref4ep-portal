"""PublicDocumentService — Filter und Releases."""

from __future__ import annotations

import io
from pathlib import Path

from sqlalchemy.orm import Session

from ref4ep.services.document_lifecycle_service import DocumentLifecycleService
from ref4ep.services.document_service import DocumentService
from ref4ep.services.document_version_service import DocumentVersionService
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.permissions import AuthContext, MembershipInfo
from ref4ep.services.person_service import PersonService
from ref4ep.services.public_document_service import PublicDocumentService
from ref4ep.services.workpackage_service import WorkpackageService
from ref4ep.storage.local import LocalFileStorage


def _make_lead(seeded_session: Session) -> AuthContext:
    partner = PartnerService(seeded_session).get_by_short_name("JLU")
    person = PersonService(seeded_session, role="admin").create(
        email="public-lead@test.example",
        display_name="Public Lead",
        partner_id=partner.id,
        password="StrongPw1!",
    )
    seeded_session.commit()
    wp = WorkpackageService(seeded_session).get_by_code("WP3")
    return AuthContext(
        person_id=person.id,
        email=person.email,
        platform_role="member",
        memberships=[
            MembershipInfo(workpackage_id=wp.id, workpackage_code=wp.code, wp_role="wp_lead")
        ],
    )


def _admin() -> AuthContext:
    return AuthContext(
        person_id="admin-fixture", email="admin@x", platform_role="admin", memberships=[]
    )


def _create_document_with_version(
    seeded_session: Session, auth: AuthContext, storage: LocalFileStorage, *, title: str
) -> str:
    doc = DocumentService(seeded_session, auth=auth).create(
        workpackage_code="WP3", title=title, document_type="deliverable"
    )
    seeded_session.commit()
    DocumentVersionService(seeded_session, auth=auth, storage=storage).upload_new_version(
        doc.id,
        file_stream=io.BytesIO(b"%PDF-1.4 inhalt"),
        original_filename="v1.pdf",
        mime_type="application/pdf",
        change_note="Erste Version",
    )
    seeded_session.commit()
    return doc.id


def _release_and_publish(
    seeded_session: Session, auth: AuthContext, doc_id: str, *, version_number: int = 1
) -> None:
    lifecycle = DocumentLifecycleService(seeded_session, auth=auth)
    lifecycle.set_status(doc_id, to="in_review")
    lifecycle.release(doc_id, version_number=version_number)
    lifecycle.set_visibility(doc_id, to="public")
    seeded_session.commit()


def test_draft_is_not_public(seeded_session: Session, tmp_storage_dir: Path) -> None:
    auth = _make_lead(seeded_session)
    storage = LocalFileStorage(tmp_storage_dir)
    _create_document_with_version(seeded_session, auth, storage, title="Bleibt Draft")
    listed = PublicDocumentService(seeded_session).list_public()
    assert listed == []


def test_workpackage_visibility_is_not_public(
    seeded_session: Session, tmp_storage_dir: Path
) -> None:
    auth = _make_lead(seeded_session)
    storage = LocalFileStorage(tmp_storage_dir)
    doc_id = _create_document_with_version(seeded_session, auth, storage, title="WP-only")
    lifecycle = DocumentLifecycleService(seeded_session, auth=auth)
    lifecycle.set_status(doc_id, to="in_review")
    lifecycle.release(doc_id, version_number=1)
    seeded_session.commit()
    # visibility bleibt workpackage → nicht im Public-Filter.
    listed = PublicDocumentService(seeded_session).list_public()
    assert listed == []


def test_internal_visibility_is_not_public(seeded_session: Session, tmp_storage_dir: Path) -> None:
    auth = _make_lead(seeded_session)
    storage = LocalFileStorage(tmp_storage_dir)
    doc_id = _create_document_with_version(seeded_session, auth, storage, title="Konsortium")
    lifecycle = DocumentLifecycleService(seeded_session, auth=auth)
    lifecycle.set_status(doc_id, to="in_review")
    lifecycle.release(doc_id, version_number=1)
    lifecycle.set_visibility(doc_id, to="internal")
    seeded_session.commit()
    listed = PublicDocumentService(seeded_session).list_public()
    assert listed == []


def test_released_and_public_is_listed(seeded_session: Session, tmp_storage_dir: Path) -> None:
    auth = _make_lead(seeded_session)
    storage = LocalFileStorage(tmp_storage_dir)
    doc_id = _create_document_with_version(seeded_session, auth, storage, title="Öffentlich")
    _release_and_publish(seeded_session, auth, doc_id)
    listed = PublicDocumentService(seeded_session).list_public()
    assert [d.id for d in listed] == [doc_id]
    pair = PublicDocumentService(seeded_session).get_for_public_download(
        wp_code="WP3", slug=listed[0].slug
    )
    assert pair is not None


def test_soft_deleted_is_not_public(seeded_session: Session, tmp_storage_dir: Path) -> None:
    auth = _make_lead(seeded_session)
    storage = LocalFileStorage(tmp_storage_dir)
    doc_id = _create_document_with_version(seeded_session, auth, storage, title="Gelöscht")
    _release_and_publish(seeded_session, auth, doc_id)
    DocumentService(seeded_session, auth=_admin()).soft_delete(doc_id)
    seeded_session.commit()
    assert PublicDocumentService(seeded_session).list_public() == []


def test_new_unreleased_version_does_not_change_public_version(
    seeded_session: Session, tmp_storage_dir: Path
) -> None:
    auth = _make_lead(seeded_session)
    storage = LocalFileStorage(tmp_storage_dir)
    doc_id = _create_document_with_version(seeded_session, auth, storage, title="Versionen")
    _release_and_publish(seeded_session, auth, doc_id)
    # Neuer Upload — soll released_version_id NICHT verändern.
    DocumentVersionService(seeded_session, auth=auth, storage=storage).upload_new_version(
        doc_id,
        file_stream=io.BytesIO(b"%PDF-1.4 v2 inhalt anders"),
        original_filename="v2.pdf",
        mime_type="application/pdf",
        change_note="zweite Version",
    )
    seeded_session.commit()

    pair = PublicDocumentService(seeded_session).get_for_public_download(
        wp_code="WP3", slug="versionen"
    )
    assert pair is not None
    document, version = pair
    assert document.released_version_id is not None
    assert version.version_number == 1
    assert version.original_filename == "v1.pdf"


def test_get_for_public_download_returns_none_for_internal(
    seeded_session: Session, tmp_storage_dir: Path
) -> None:
    auth = _make_lead(seeded_session)
    storage = LocalFileStorage(tmp_storage_dir)
    doc_id = _create_document_with_version(seeded_session, auth, storage, title="Konsortium2")
    lifecycle = DocumentLifecycleService(seeded_session, auth=auth)
    lifecycle.set_status(doc_id, to="in_review")
    lifecycle.release(doc_id, version_number=1)
    lifecycle.set_visibility(doc_id, to="internal")
    seeded_session.commit()
    pair = PublicDocumentService(seeded_session).get_for_public_download(
        wp_code="WP3", slug="konsortium2"
    )
    assert pair is None
