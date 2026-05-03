"""DocumentService: Audit-Hooks und Soft-Delete."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from ref4ep.domain.models import AuditLog
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.document_service import DocumentService
from ref4ep.services.document_version_service import DocumentVersionService
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.permissions import AuthContext, MembershipInfo
from ref4ep.services.person_service import PersonService
from ref4ep.services.workpackage_service import WorkpackageService
from ref4ep.storage.local import LocalFileStorage


def _setup(seeded_session: Session) -> AuthContext:
    partner = PartnerService(seeded_session).get_by_short_name("JLU")
    person = PersonService(seeded_session, role="admin").create(
        email="member-audit@test.example",
        display_name="Member Audit",
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
            MembershipInfo(workpackage_id=wp.id, workpackage_code=wp.code, wp_role="wp_member")
        ],
    )


def test_create_writes_audit(seeded_session: Session) -> None:
    auth = _setup(seeded_session)
    audit = AuditLogger(seeded_session, actor_person_id=auth.person_id)
    DocumentService(seeded_session, auth=auth, audit=audit).create(
        workpackage_code="WP3", title="Auditing", document_type="report"
    )
    seeded_session.commit()
    assert seeded_session.query(AuditLog).filter_by(action="document.create").count() == 1


def test_update_metadata_writes_audit(seeded_session: Session) -> None:
    auth = _setup(seeded_session)
    audit = AuditLogger(seeded_session, actor_person_id=auth.person_id)
    svc = DocumentService(seeded_session, auth=auth, audit=audit)
    doc = svc.create(workpackage_code="WP3", title="Original", document_type="note")
    seeded_session.commit()
    svc.update_metadata(doc.id, title="Korrigiert")
    seeded_session.commit()
    assert seeded_session.query(AuditLog).filter_by(action="document.update").count() == 1


def test_soft_delete_admin_only(seeded_session: Session) -> None:
    auth = _setup(seeded_session)  # member
    doc = DocumentService(seeded_session, auth=auth).create(
        workpackage_code="WP3", title="Doomed", document_type="other"
    )
    seeded_session.commit()
    with pytest.raises(PermissionError):
        DocumentService(seeded_session, auth=auth).soft_delete(doc.id)


def test_soft_delete_keeps_row_and_storage(seeded_session: Session, tmp_storage_dir: Path) -> None:
    auth = _setup(seeded_session)
    storage = LocalFileStorage(tmp_storage_dir)
    doc = DocumentService(seeded_session, auth=auth).create(
        workpackage_code="WP3", title="Mit Datei", document_type="other"
    )
    seeded_session.commit()
    DocumentVersionService(seeded_session, auth=auth, storage=storage).upload_new_version(
        doc.id,
        file_stream=io.BytesIO(b"%PDF-1.4 hi"),
        original_filename="v1.pdf",
        mime_type="application/pdf",
        change_note="erste Version",
    )
    seeded_session.commit()
    doc_id = doc.id

    admin_auth = AuthContext(
        person_id="admin-fixture", email="admin@x", platform_role="admin", memberships=[]
    )
    audit = AuditLogger(seeded_session, actor_person_id="admin-fixture")
    DocumentService(seeded_session, auth=admin_auth, audit=audit).soft_delete(doc_id)
    seeded_session.commit()

    # Zeile bleibt physisch in der Tabelle.
    raw = seeded_session.execute(
        text("SELECT is_deleted FROM document WHERE id = :id"), {"id": doc_id}
    ).scalar()
    assert raw == 1  # SQLite repräsentiert Boolean als Integer
    # Versionsdatei bleibt physisch erhalten.
    version_files = list((tmp_storage_dir / "documents" / doc_id).glob("*.bin"))
    assert version_files, "Version-Datei wurde gelöscht — sollte erhalten bleiben"
    # Dokument verschwindet aus der Liste.
    listed = DocumentService(seeded_session, auth=auth).list_for_workpackage("WP3")
    assert all(d.id != doc_id for d in listed)
    # Audit-Eintrag existiert.
    assert seeded_session.query(AuditLog).filter_by(action="document.delete").count() == 1
