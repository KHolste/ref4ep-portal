"""DocumentVersionService — Upload, Listing, Download-Lookup."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from ref4ep.services.document_service import DocumentService
from ref4ep.services.document_version_service import DocumentVersionService
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.permissions import AuthContext, MembershipInfo
from ref4ep.services.person_service import PersonService
from ref4ep.services.workpackage_service import WorkpackageService
from ref4ep.storage.local import LocalFileStorage


def _setup(
    seeded_session: Session, tmp_storage_dir: Path
) -> tuple[str, AuthContext, LocalFileStorage]:
    partner = PartnerService(seeded_session).get_by_short_name("JLU")
    assert partner is not None
    person = PersonService(seeded_session, role="admin").create(
        email="uploader@test.example",
        display_name="Uploader",
        partner_id=partner.id,
        password="StrongPw1!",
    )
    seeded_session.commit()
    wp = WorkpackageService(seeded_session).get_by_code("WP3")
    assert wp is not None
    auth = AuthContext(
        person_id=person.id,
        email=person.email,
        platform_role="member",
        memberships=[
            MembershipInfo(workpackage_id=wp.id, workpackage_code=wp.code, wp_role="wp_member")
        ],
    )
    doc = DocumentService(seeded_session, auth=auth).create(
        workpackage_code="WP3", title="Konstruktion", document_type="deliverable"
    )
    seeded_session.commit()
    storage = LocalFileStorage(tmp_storage_dir)
    return doc.id, auth, storage


def test_first_upload_assigns_version_number_one(
    seeded_session: Session, tmp_storage_dir: Path
) -> None:
    doc_id, auth, storage = _setup(seeded_session, tmp_storage_dir)
    service = DocumentVersionService(seeded_session, auth=auth, storage=storage)
    version, warnings = service.upload_new_version(
        doc_id,
        file_stream=io.BytesIO(b"%PDF-1.4 content"),
        original_filename="entwurf.pdf",
        mime_type="application/pdf",
        change_note="Initial-Entwurf v0.1",
    )
    assert version.version_number == 1
    assert version.original_filename == "entwurf.pdf"
    assert version.file_size_bytes == len(b"%PDF-1.4 content")
    assert warnings == []


def test_second_upload_assigns_version_number_two(
    seeded_session: Session, tmp_storage_dir: Path
) -> None:
    doc_id, auth, storage = _setup(seeded_session, tmp_storage_dir)
    service = DocumentVersionService(seeded_session, auth=auth, storage=storage)
    service.upload_new_version(
        doc_id,
        file_stream=io.BytesIO(b"%PDF-1.4 first"),
        original_filename="v1.pdf",
        mime_type="application/pdf",
        change_note="Initial-Entwurf",
    )
    seeded_session.commit()
    v2, _ = service.upload_new_version(
        doc_id,
        file_stream=io.BytesIO(b"%PDF-1.4 second"),
        original_filename="v2.pdf",
        mime_type="application/pdf",
        change_note="Korrektur Maßangaben",
    )
    assert v2.version_number == 2


def test_missing_change_note_uses_default_first_upload(
    seeded_session: Session, tmp_storage_dir: Path
) -> None:
    """Block 0036: Beim ersten Upload ohne explizite Notiz wird
    automatisch ``Initialer Upload`` gespeichert."""
    doc_id, auth, storage = _setup(seeded_session, tmp_storage_dir)
    service = DocumentVersionService(seeded_session, auth=auth, storage=storage)
    version, _warnings = service.upload_new_version(
        doc_id,
        file_stream=io.BytesIO(b"%PDF-1.4 first"),
        original_filename="x.pdf",
        mime_type="application/pdf",
        # change_note bewusst weggelassen
    )
    assert version.change_note == "Initialer Upload"


def test_blank_change_note_uses_default(seeded_session: Session, tmp_storage_dir: Path) -> None:
    """Block 0036: Whitespace-Notiz wird wie Leereingabe behandelt."""
    doc_id, auth, storage = _setup(seeded_session, tmp_storage_dir)
    service = DocumentVersionService(seeded_session, auth=auth, storage=storage)
    version, _warnings = service.upload_new_version(
        doc_id,
        file_stream=io.BytesIO(b"%PDF-1.4 dat"),
        original_filename="x.pdf",
        mime_type="application/pdf",
        change_note="   ",
    )
    assert version.change_note == "Initialer Upload"


def test_missing_change_note_for_next_version_uses_other_default(
    seeded_session: Session, tmp_storage_dir: Path
) -> None:
    doc_id, auth, storage = _setup(seeded_session, tmp_storage_dir)
    service = DocumentVersionService(seeded_session, auth=auth, storage=storage)
    service.upload_new_version(
        doc_id,
        file_stream=io.BytesIO(b"%PDF-1.4 v1"),
        original_filename="v1.pdf",
        mime_type="application/pdf",
        change_note="Erstfassung",
    )
    seeded_session.commit()
    v2, _ = service.upload_new_version(
        doc_id,
        file_stream=io.BytesIO(b"%PDF-1.4 v2"),
        original_filename="v2.pdf",
        mime_type="application/pdf",
        # ohne explizite Notiz
    )
    assert v2.change_note == "Neue Version hochgeladen"


def test_short_change_note_is_accepted(seeded_session: Session, tmp_storage_dir: Path) -> None:
    """Block 0036: Kurze Notizen sind keine Validierungsfehler mehr."""
    doc_id, auth, storage = _setup(seeded_session, tmp_storage_dir)
    service = DocumentVersionService(seeded_session, auth=auth, storage=storage)
    version, _warnings = service.upload_new_version(
        doc_id,
        file_stream=io.BytesIO(b"%PDF-1.4 dat"),
        original_filename="x.pdf",
        mime_type="application/pdf",
        change_note="ab",
    )
    assert version.change_note == "ab"


def test_unsupported_mime_rejected(seeded_session: Session, tmp_storage_dir: Path) -> None:
    doc_id, auth, storage = _setup(seeded_session, tmp_storage_dir)
    service = DocumentVersionService(seeded_session, auth=auth, storage=storage)
    with pytest.raises(ValueError):
        service.upload_new_version(
            doc_id,
            file_stream=io.BytesIO(b"MZ..."),
            original_filename="virus.exe",
            mime_type="application/x-msdownload",
            change_note="Versuch",
        )


def test_duplicate_content_returns_warning(seeded_session: Session, tmp_storage_dir: Path) -> None:
    doc_id, auth, storage = _setup(seeded_session, tmp_storage_dir)
    service = DocumentVersionService(seeded_session, auth=auth, storage=storage)
    payload = b"identical bytes for both uploads"
    service.upload_new_version(
        doc_id,
        file_stream=io.BytesIO(payload),
        original_filename="v1.pdf",
        mime_type="application/pdf",
        change_note="erste Version",
    )
    seeded_session.commit()
    v2, warnings = service.upload_new_version(
        doc_id,
        file_stream=io.BytesIO(payload),
        original_filename="v1-renamed.pdf",
        mime_type="application/pdf",
        change_note="nur Metadaten korrigiert",
    )
    assert v2.version_number == 2
    assert warnings == ["duplicate_content_of_v1"]


def test_non_member_cannot_upload(seeded_session: Session, tmp_storage_dir: Path) -> None:
    doc_id, _, storage = _setup(seeded_session, tmp_storage_dir)
    foreign = AuthContext(person_id="foreign", email="x", platform_role="member", memberships=[])
    service = DocumentVersionService(seeded_session, auth=foreign, storage=storage)
    with pytest.raises(PermissionError):
        service.upload_new_version(
            doc_id,
            file_stream=io.BytesIO(b"abc"),
            original_filename="x.pdf",
            mime_type="application/pdf",
            change_note="versuche fremd",
        )
