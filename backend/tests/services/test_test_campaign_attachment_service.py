"""TestCampaignAttachmentService — Upload (PDF/CSV/Office/Bild), Permission,
Beschreibung-Edit, Soft-Delete, Thumbnail nur für Bilder (Block 0044)."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from ref4ep.domain.models import AuditLog, Person, TestCampaignAttachment
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.permissions import AuthContext
from ref4ep.services.person_service import PersonService
from ref4ep.services.test_campaign_attachment_service import (
    CampaignAttachmentNotFoundError,
    CampaignNotFoundError,
    TestCampaignAttachmentService,
)
from ref4ep.services.test_campaign_service import TestCampaignService
from ref4ep.services.workpackage_service import WorkpackageService
from ref4ep.storage.local import LocalFileStorage

PDF_BYTES = b"%PDF-1.4\n%stub\n"
CSV_BYTES = b"a,b,c\n1,2,3\n"


def _real_jpeg_bytes(width: int = 800, height: int = 600) -> bytes:
    from io import BytesIO as _BytesIO

    from PIL import Image as _Image

    buf = _BytesIO()
    _Image.new("RGB", (width, height), (180, 60, 120)).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _admin_auth(session: Session) -> tuple[Person, AuthContext]:
    admin = session.query(Person).filter_by(email="admin@test.example").one()
    auth = AuthContext(
        person_id=admin.id,
        email=admin.email,
        platform_role="admin",
        memberships=[],
    )
    return admin, auth


def _create_member(session: Session, *, email: str, role: str = "member") -> Person:
    partner = PartnerService(session).get_by_short_name("JLU")
    assert partner is not None
    person = PersonService(session, role="admin").create(
        email=email,
        display_name=email.split("@")[0],
        partner_id=partner.id,
        password="StrongPw1!",
        platform_role=role,
    )
    session.commit()
    return person


def _create_campaign(session: Session, *, code: str = "TC-ATT") -> str:
    admin = session.query(Person).filter_by(email="admin@test.example").one()
    wp = WorkpackageService(session).get_by_code("WP3")
    assert wp is not None
    campaign = TestCampaignService(
        session, role=admin.platform_role, person_id=admin.id
    ).create_campaign(
        code=code,
        title="Anhang-Kampagne",
        starts_on=datetime(2026, 5, 1).date(),
        workpackage_ids=[wp.id],
    )
    session.commit()
    return campaign.id


def _make_participant_auth(person: Person) -> AuthContext:
    return AuthContext(
        person_id=person.id,
        email=person.email,
        platform_role=person.platform_role,
        memberships=[],
    )


def _add_participant(session: Session, campaign_id: str, person_id: str) -> None:
    admin = session.query(Person).filter_by(email="admin@test.example").one()
    TestCampaignService(session, role=admin.platform_role, person_id=admin.id).add_participant(
        campaign_id, person_id=person_id, role="diagnostics"
    )
    session.commit()


@pytest.fixture
def admin_seeded(seeded_session: Session) -> Session:
    if not seeded_session.query(Person).filter_by(email="admin@test.example").first():
        partner = PartnerService(seeded_session).get_by_short_name("JLU")
        assert partner is not None
        PersonService(seeded_session, role="admin").create(
            email="admin@test.example",
            display_name="Admin",
            partner_id=partner.id,
            password="StrongPw1!",
            platform_role="admin",
        )
        seeded_session.commit()
    return seeded_session


# ---- Read --------------------------------------------------------------


def test_list_for_unknown_campaign_raises(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    _, auth = _admin_auth(admin_seeded)
    service = TestCampaignAttachmentService(
        admin_seeded, auth=auth, storage=LocalFileStorage(tmp_storage_dir)
    )
    with pytest.raises(CampaignNotFoundError):
        service.list_for_campaign("00000000-0000-0000-0000-000000000000")


def test_list_for_empty_campaign_returns_empty(
    admin_seeded: Session, tmp_storage_dir: Path
) -> None:
    cid = _create_campaign(admin_seeded)
    _, auth = _admin_auth(admin_seeded)
    service = TestCampaignAttachmentService(
        admin_seeded, auth=auth, storage=LocalFileStorage(tmp_storage_dir)
    )
    assert service.list_for_campaign(cid) == []


# ---- Upload + Whitelist -------------------------------------------------


def test_admin_can_upload_pdf(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-ATT-PDF")
    _, auth = _admin_auth(admin_seeded)
    storage = LocalFileStorage(tmp_storage_dir)
    att = TestCampaignAttachmentService(admin_seeded, auth=auth, storage=storage).upload(
        cid,
        file_stream=io.BytesIO(PDF_BYTES),
        original_filename="messprotokoll.pdf",
        mime_type="application/pdf",
        description="Rohprotokoll",
    )
    assert att.mime_type == "application/pdf"
    assert att.file_size_bytes == len(PDF_BYTES)
    assert att.description == "Rohprotokoll"
    assert att.is_deleted is False
    # PDF bekommt kein Thumbnail.
    assert att.thumbnail_storage_key is None


def test_admin_can_upload_csv(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-ATT-CSV")
    _, auth = _admin_auth(admin_seeded)
    storage = LocalFileStorage(tmp_storage_dir)
    att = TestCampaignAttachmentService(admin_seeded, auth=auth, storage=storage).upload(
        cid,
        file_stream=io.BytesIO(CSV_BYTES),
        original_filename="messwerte.csv",
        mime_type="text/csv",
    )
    assert att.mime_type == "text/csv"
    assert att.thumbnail_storage_key is None


def test_image_upload_creates_thumbnail(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-ATT-IMG")
    _, auth = _admin_auth(admin_seeded)
    storage = LocalFileStorage(tmp_storage_dir)
    att = TestCampaignAttachmentService(admin_seeded, auth=auth, storage=storage).upload(
        cid,
        file_stream=io.BytesIO(_real_jpeg_bytes()),
        original_filename="kammer.jpg",
        mime_type="image/jpeg",
    )
    assert att.thumbnail_storage_key is not None
    assert att.thumbnail_mime_type == "image/jpeg"
    assert att.thumbnail_size_bytes is not None
    assert att.thumbnail_size_bytes < att.file_size_bytes


def test_unsupported_mime_rejected(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-ATT-EXE")
    _, auth = _admin_auth(admin_seeded)
    storage = LocalFileStorage(tmp_storage_dir)
    with pytest.raises(ValueError, match="MIME"):
        TestCampaignAttachmentService(admin_seeded, auth=auth, storage=storage).upload(
            cid,
            file_stream=io.BytesIO(b"<html></html>"),
            original_filename="x.html",
            mime_type="text/html",
        )


def test_empty_file_rejected(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-ATT-EMPTY")
    _, auth = _admin_auth(admin_seeded)
    storage = LocalFileStorage(tmp_storage_dir)
    with pytest.raises(ValueError, match="leer"):
        TestCampaignAttachmentService(admin_seeded, auth=auth, storage=storage).upload(
            cid,
            file_stream=io.BytesIO(b""),
            original_filename="x.pdf",
            mime_type="application/pdf",
        )


# ---- Permissions --------------------------------------------------------


def test_participant_can_upload(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-ATT-PART")
    member = _create_member(admin_seeded, email="attpart@test.example")
    _add_participant(admin_seeded, cid, member.id)
    auth = _make_participant_auth(member)
    storage = LocalFileStorage(tmp_storage_dir)
    att = TestCampaignAttachmentService(admin_seeded, auth=auth, storage=storage).upload(
        cid,
        file_stream=io.BytesIO(PDF_BYTES),
        original_filename="x.pdf",
        mime_type="application/pdf",
    )
    assert att.uploaded_by_person_id == member.id


def test_non_participant_cannot_upload(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-ATT-NOPART")
    outsider = _create_member(admin_seeded, email="attout@test.example")
    auth = _make_participant_auth(outsider)
    storage = LocalFileStorage(tmp_storage_dir)
    with pytest.raises(PermissionError):
        TestCampaignAttachmentService(admin_seeded, auth=auth, storage=storage).upload(
            cid,
            file_stream=io.BytesIO(PDF_BYTES),
            original_filename="x.pdf",
            mime_type="application/pdf",
        )


# ---- Beschreibung-Edit --------------------------------------------------


def test_uploader_can_edit_description(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-ATT-EDIT")
    member = _create_member(admin_seeded, email="attcap@test.example")
    _add_participant(admin_seeded, cid, member.id)
    auth = _make_participant_auth(member)
    storage = LocalFileStorage(tmp_storage_dir)
    att = TestCampaignAttachmentService(admin_seeded, auth=auth, storage=storage).upload(
        cid,
        file_stream=io.BytesIO(PDF_BYTES),
        original_filename="x.pdf",
        mime_type="application/pdf",
        description="alt",
    )
    updated = TestCampaignAttachmentService(admin_seeded, auth=auth).update_description(
        att.id, description="neu"
    )
    assert updated.description == "neu"


def test_other_member_cannot_edit_description(
    admin_seeded: Session, tmp_storage_dir: Path
) -> None:
    cid = _create_campaign(admin_seeded, code="TC-ATT-FOREIGN")
    uploader = _create_member(admin_seeded, email="attu@test.example")
    intruder = _create_member(admin_seeded, email="atti@test.example")
    _add_participant(admin_seeded, cid, uploader.id)
    _add_participant(admin_seeded, cid, intruder.id)
    storage = LocalFileStorage(tmp_storage_dir)
    att = TestCampaignAttachmentService(
        admin_seeded, auth=_make_participant_auth(uploader), storage=storage
    ).upload(
        cid,
        file_stream=io.BytesIO(PDF_BYTES),
        original_filename="x.pdf",
        mime_type="application/pdf",
    )
    with pytest.raises(PermissionError):
        TestCampaignAttachmentService(
            admin_seeded, auth=_make_participant_auth(intruder)
        ).update_description(att.id, description="übergriffig")


def test_admin_can_edit_foreign_description(
    admin_seeded: Session, tmp_storage_dir: Path
) -> None:
    cid = _create_campaign(admin_seeded, code="TC-ATT-ADMINEDIT")
    member = _create_member(admin_seeded, email="attsomeone@test.example")
    _add_participant(admin_seeded, cid, member.id)
    storage = LocalFileStorage(tmp_storage_dir)
    att = TestCampaignAttachmentService(
        admin_seeded, auth=_make_participant_auth(member), storage=storage
    ).upload(
        cid,
        file_stream=io.BytesIO(PDF_BYTES),
        original_filename="x.pdf",
        mime_type="application/pdf",
    )
    _, admin_auth = _admin_auth(admin_seeded)
    updated = TestCampaignAttachmentService(admin_seeded, auth=admin_auth).update_description(
        att.id, description="vom Admin gesetzt"
    )
    assert updated.description == "vom Admin gesetzt"


# ---- Soft-Delete + Listing ---------------------------------------------


def test_uploader_can_soft_delete(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-ATT-DEL")
    _, auth = _admin_auth(admin_seeded)
    storage = LocalFileStorage(tmp_storage_dir)
    att = TestCampaignAttachmentService(admin_seeded, auth=auth, storage=storage).upload(
        cid,
        file_stream=io.BytesIO(PDF_BYTES),
        original_filename="x.pdf",
        mime_type="application/pdf",
    )
    TestCampaignAttachmentService(admin_seeded, auth=auth).soft_delete(att.id)
    refreshed = admin_seeded.get(TestCampaignAttachment, att.id)
    assert refreshed is not None and refreshed.is_deleted is True
    assert (
        TestCampaignAttachmentService(
            admin_seeded, auth=auth, storage=storage
        ).list_for_campaign(cid)
        == []
    )


def test_get_visible_raises_for_deleted(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-ATT-VIS")
    _, auth = _admin_auth(admin_seeded)
    storage = LocalFileStorage(tmp_storage_dir)
    att = TestCampaignAttachmentService(admin_seeded, auth=auth, storage=storage).upload(
        cid,
        file_stream=io.BytesIO(PDF_BYTES),
        original_filename="x.pdf",
        mime_type="application/pdf",
    )
    TestCampaignAttachmentService(admin_seeded, auth=auth).soft_delete(att.id)
    with pytest.raises(CampaignAttachmentNotFoundError):
        TestCampaignAttachmentService(admin_seeded, auth=auth).get_visible(att.id)


# ---- Audit -------------------------------------------------------------


def test_upload_emits_audit_entry(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-ATT-AUDIT")
    _, auth = _admin_auth(admin_seeded)
    audit = AuditLogger(admin_seeded, actor_person_id=auth.person_id)
    storage = LocalFileStorage(tmp_storage_dir)
    TestCampaignAttachmentService(
        admin_seeded, auth=auth, audit=audit, storage=storage
    ).upload(
        cid,
        file_stream=io.BytesIO(PDF_BYTES),
        original_filename="x.pdf",
        mime_type="application/pdf",
    )
    admin_seeded.commit()
    actions = {row.action for row in admin_seeded.query(AuditLog).all()}
    assert "campaign.attachment.upload" in actions
