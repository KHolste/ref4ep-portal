"""TestCampaignPhotoService — Upload, Permission, Caption-Edit, Soft-Delete (Block 0028)."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from ref4ep.domain.models import AuditLog, Person, TestCampaignPhoto
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.permissions import AuthContext
from ref4ep.services.person_service import PersonService
from ref4ep.services.test_campaign_photo_service import (
    CampaignNotFoundError,
    CampaignPhotoNotFoundError,
    TestCampaignPhotoService,
)
from ref4ep.services.test_campaign_service import TestCampaignService
from ref4ep.services.workpackage_service import WorkpackageService
from ref4ep.storage.local import LocalFileStorage

# 1×1 PNG (Header + minimaler Inhalt — reicht für die MIME-/Size-Pfade).
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00"
    b"\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc"
    b"\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


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


def _create_campaign(session: Session, *, code: str = "TC-PHOTO") -> str:
    admin = session.query(Person).filter_by(email="admin@test.example").one()
    wp = WorkpackageService(session).get_by_code("WP3")
    assert wp is not None
    campaign = TestCampaignService(
        session, role=admin.platform_role, person_id=admin.id
    ).create_campaign(
        code=code,
        title="Foto-Kampagne",
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
    """Stellt sicher, dass ein Admin-Account vorhanden ist (entspricht
    dem Pattern aus den Kampagnen-API-Tests)."""
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
    storage = LocalFileStorage(tmp_storage_dir)
    service = TestCampaignPhotoService(admin_seeded, auth=auth, storage=storage)
    with pytest.raises(CampaignNotFoundError):
        service.list_for_campaign("00000000-0000-0000-0000-000000000000")


def test_list_for_empty_campaign_returns_empty(
    admin_seeded: Session, tmp_storage_dir: Path
) -> None:
    cid = _create_campaign(admin_seeded)
    _, auth = _admin_auth(admin_seeded)
    service = TestCampaignPhotoService(
        admin_seeded, auth=auth, storage=LocalFileStorage(tmp_storage_dir)
    )
    assert service.list_for_campaign(cid) == []


# ---- Upload + permissions ----------------------------------------------


def test_admin_can_upload_png(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded)
    _, auth = _admin_auth(admin_seeded)
    storage = LocalFileStorage(tmp_storage_dir)
    service = TestCampaignPhotoService(admin_seeded, auth=auth, storage=storage)
    photo = service.upload(
        cid,
        file_stream=io.BytesIO(PNG_BYTES),
        original_filename="kammer.png",
        mime_type="image/png",
        caption="Innenansicht",
    )
    assert photo.id is not None
    assert photo.mime_type == "image/png"
    assert photo.file_size_bytes == len(PNG_BYTES)
    assert photo.caption == "Innenansicht"
    assert photo.is_deleted is False
    assert photo.uploaded_by_person_id == auth.person_id


def test_participant_can_upload(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-PHOTO-PART")
    member = _create_member(admin_seeded, email="part@test.example")
    _add_participant(admin_seeded, cid, member.id)
    auth = _make_participant_auth(member)
    storage = LocalFileStorage(tmp_storage_dir)
    photo = TestCampaignPhotoService(admin_seeded, auth=auth, storage=storage).upload(
        cid,
        file_stream=io.BytesIO(PNG_BYTES),
        original_filename="set.png",
        mime_type="image/png",
    )
    assert photo.uploaded_by_person_id == member.id


def test_non_participant_cannot_upload(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-PHOTO-NOPART")
    outsider = _create_member(admin_seeded, email="out@test.example")
    auth = _make_participant_auth(outsider)
    storage = LocalFileStorage(tmp_storage_dir)
    with pytest.raises(PermissionError):
        TestCampaignPhotoService(admin_seeded, auth=auth, storage=storage).upload(
            cid,
            file_stream=io.BytesIO(PNG_BYTES),
            original_filename="x.png",
            mime_type="image/png",
        )


def test_unsupported_mime_rejected(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-PHOTO-PDF")
    _, auth = _admin_auth(admin_seeded)
    storage = LocalFileStorage(tmp_storage_dir)
    with pytest.raises(ValueError, match="MIME"):
        TestCampaignPhotoService(admin_seeded, auth=auth, storage=storage).upload(
            cid,
            file_stream=io.BytesIO(b"%PDF-1.4 ..."),
            original_filename="x.pdf",
            mime_type="application/pdf",
        )


def test_empty_file_rejected(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-PHOTO-EMPTY")
    _, auth = _admin_auth(admin_seeded)
    storage = LocalFileStorage(tmp_storage_dir)
    with pytest.raises(ValueError, match="leer"):
        TestCampaignPhotoService(admin_seeded, auth=auth, storage=storage).upload(
            cid,
            file_stream=io.BytesIO(b""),
            original_filename="x.png",
            mime_type="image/png",
        )


def test_jpeg_accepted(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-PHOTO-JPEG")
    _, auth = _admin_auth(admin_seeded)
    storage = LocalFileStorage(tmp_storage_dir)
    photo = TestCampaignPhotoService(admin_seeded, auth=auth, storage=storage).upload(
        cid,
        file_stream=io.BytesIO(b"\xff\xd8\xff\xe0jpeg-stub"),
        original_filename="kammer.jpg",
        mime_type="image/jpeg",
    )
    assert photo.mime_type == "image/jpeg"


# ---- Caption edit ------------------------------------------------------


def test_uploader_can_edit_caption(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-PHOTO-EDIT")
    member = _create_member(admin_seeded, email="cap@test.example")
    _add_participant(admin_seeded, cid, member.id)
    auth = _make_participant_auth(member)
    storage = LocalFileStorage(tmp_storage_dir)
    photo = TestCampaignPhotoService(admin_seeded, auth=auth, storage=storage).upload(
        cid,
        file_stream=io.BytesIO(PNG_BYTES),
        original_filename="x.png",
        mime_type="image/png",
        caption="alt",
    )
    updated = TestCampaignPhotoService(admin_seeded, auth=auth).update_caption(
        photo.id, caption="neu"
    )
    assert updated.caption == "neu"


def test_admin_can_edit_foreign_caption(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-PHOTO-ADMIN-EDIT")
    member = _create_member(admin_seeded, email="someone@test.example")
    _add_participant(admin_seeded, cid, member.id)
    member_auth = _make_participant_auth(member)
    storage = LocalFileStorage(tmp_storage_dir)
    photo = TestCampaignPhotoService(admin_seeded, auth=member_auth, storage=storage).upload(
        cid,
        file_stream=io.BytesIO(PNG_BYTES),
        original_filename="x.png",
        mime_type="image/png",
    )
    _, admin_auth = _admin_auth(admin_seeded)
    updated = TestCampaignPhotoService(admin_seeded, auth=admin_auth).update_caption(
        photo.id, caption="vom Admin gesetzt"
    )
    assert updated.caption == "vom Admin gesetzt"


def test_other_member_cannot_edit_caption(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-PHOTO-FOREIGN-EDIT")
    uploader = _create_member(admin_seeded, email="u@test.example")
    intruder = _create_member(admin_seeded, email="i@test.example")
    _add_participant(admin_seeded, cid, uploader.id)
    _add_participant(admin_seeded, cid, intruder.id)
    storage = LocalFileStorage(tmp_storage_dir)
    photo = TestCampaignPhotoService(
        admin_seeded, auth=_make_participant_auth(uploader), storage=storage
    ).upload(
        cid,
        file_stream=io.BytesIO(PNG_BYTES),
        original_filename="x.png",
        mime_type="image/png",
    )
    with pytest.raises(PermissionError):
        TestCampaignPhotoService(
            admin_seeded, auth=_make_participant_auth(intruder)
        ).update_caption(photo.id, caption="übergriffig")


# ---- Soft-Delete -------------------------------------------------------


def test_uploader_can_soft_delete(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-PHOTO-DEL")
    member = _create_member(admin_seeded, email="d@test.example")
    _add_participant(admin_seeded, cid, member.id)
    auth = _make_participant_auth(member)
    storage = LocalFileStorage(tmp_storage_dir)
    photo = TestCampaignPhotoService(admin_seeded, auth=auth, storage=storage).upload(
        cid,
        file_stream=io.BytesIO(PNG_BYTES),
        original_filename="x.png",
        mime_type="image/png",
    )
    TestCampaignPhotoService(admin_seeded, auth=auth).soft_delete(photo.id)
    # Reload — Photo selbst ist soft-gelöscht.
    refreshed = admin_seeded.get(TestCampaignPhoto, photo.id)
    assert refreshed is not None
    assert refreshed.is_deleted is True
    # Liste filtert es heraus.
    assert (
        TestCampaignPhotoService(admin_seeded, auth=auth, storage=storage).list_for_campaign(cid)
        == []
    )


def test_listing_sorts_newest_first(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-PHOTO-SORT")
    _, auth = _admin_auth(admin_seeded)
    storage = LocalFileStorage(tmp_storage_dir)
    older = TestCampaignPhotoService(admin_seeded, auth=auth, storage=storage).upload(
        cid,
        file_stream=io.BytesIO(PNG_BYTES),
        original_filename="alt.png",
        mime_type="image/png",
        taken_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    newer = TestCampaignPhotoService(admin_seeded, auth=auth, storage=storage).upload(
        cid,
        file_stream=io.BytesIO(PNG_BYTES),
        original_filename="neu.png",
        mime_type="image/png",
        taken_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    photos = TestCampaignPhotoService(admin_seeded, auth=auth, storage=storage).list_for_campaign(
        cid
    )
    assert [p.id for p in photos] == [newer.id, older.id]


def test_get_visible_raises_for_deleted(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-PHOTO-VIS")
    _, auth = _admin_auth(admin_seeded)
    storage = LocalFileStorage(tmp_storage_dir)
    photo = TestCampaignPhotoService(admin_seeded, auth=auth, storage=storage).upload(
        cid,
        file_stream=io.BytesIO(PNG_BYTES),
        original_filename="x.png",
        mime_type="image/png",
    )
    TestCampaignPhotoService(admin_seeded, auth=auth).soft_delete(photo.id)
    with pytest.raises(CampaignPhotoNotFoundError):
        TestCampaignPhotoService(admin_seeded, auth=auth).get_visible(photo.id)


# ---- Audit -------------------------------------------------------------


def test_upload_emits_audit_entry(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    from ref4ep.services.audit_logger import AuditLogger

    cid = _create_campaign(admin_seeded, code="TC-PHOTO-AUDIT")
    _, auth = _admin_auth(admin_seeded)
    audit = AuditLogger(admin_seeded, actor_person_id=auth.person_id)
    storage = LocalFileStorage(tmp_storage_dir)
    TestCampaignPhotoService(admin_seeded, auth=auth, audit=audit, storage=storage).upload(
        cid,
        file_stream=io.BytesIO(PNG_BYTES),
        original_filename="x.png",
        mime_type="image/png",
    )
    admin_seeded.commit()
    actions = {row.action for row in admin_seeded.query(AuditLog).all()}
    assert "campaign.photo.upload" in actions


# ---- Block 0032 — Thumbnail-Pipeline ---------------------------------


def _real_jpeg_bytes(width: int = 800, height: int = 600) -> bytes:
    """Echtes JPEG (groß genug für sinnvolles Thumbnail)."""
    from io import BytesIO as _BytesIO

    from PIL import Image as _Image

    buf = _BytesIO()
    _Image.new("RGB", (width, height), (180, 60, 120)).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _real_png_alpha_bytes(width: int = 600, height: int = 400) -> bytes:
    from io import BytesIO as _BytesIO

    from PIL import Image as _Image

    buf = _BytesIO()
    _Image.new("RGBA", (width, height), (0, 200, 255, 128)).save(buf, format="PNG")
    return buf.getvalue()


def test_upload_jpeg_creates_jpeg_thumbnail(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    cid = _create_campaign(admin_seeded, code="TC-PHOTO-THUMB-JPG")
    _, auth = _admin_auth(admin_seeded)
    storage = LocalFileStorage(tmp_storage_dir)
    photo = TestCampaignPhotoService(admin_seeded, auth=auth, storage=storage).upload(
        cid,
        file_stream=io.BytesIO(_real_jpeg_bytes()),
        original_filename="kammer.jpg",
        mime_type="image/jpeg",
    )
    assert photo.thumbnail_storage_key is not None
    assert photo.thumbnail_mime_type == "image/jpeg"
    assert photo.thumbnail_size_bytes is not None
    assert photo.thumbnail_size_bytes > 0
    # Thumbnail kleiner als Original.
    assert photo.thumbnail_size_bytes < photo.file_size_bytes
    # Thumbnail liegt im Storage und beginnt mit JPEG-Magic.
    with storage.open_read(photo.thumbnail_storage_key) as fh:
        head = fh.read(3)
    assert head == b"\xff\xd8\xff"


def test_upload_png_with_alpha_creates_png_thumbnail(
    admin_seeded: Session, tmp_storage_dir: Path
) -> None:
    cid = _create_campaign(admin_seeded, code="TC-PHOTO-THUMB-PNG")
    _, auth = _admin_auth(admin_seeded)
    storage = LocalFileStorage(tmp_storage_dir)
    photo = TestCampaignPhotoService(admin_seeded, auth=auth, storage=storage).upload(
        cid,
        file_stream=io.BytesIO(_real_png_alpha_bytes()),
        original_filename="overlay.png",
        mime_type="image/png",
    )
    assert photo.thumbnail_mime_type == "image/png"
    with storage.open_read(photo.thumbnail_storage_key) as fh:
        head = fh.read(8)
    assert head[:8] == b"\x89PNG\r\n\x1a\n"


def test_upload_corrupted_image_succeeds_without_thumbnail(
    admin_seeded: Session, tmp_storage_dir: Path
) -> None:
    """MIME ist erlaubt, Inhalt ist Müll: Upload bleibt erfolgreich,
    Thumbnail-Felder bleiben NULL."""
    cid = _create_campaign(admin_seeded, code="TC-PHOTO-THUMB-CORRUPT")
    _, auth = _admin_auth(admin_seeded)
    storage = LocalFileStorage(tmp_storage_dir)
    photo = TestCampaignPhotoService(admin_seeded, auth=auth, storage=storage).upload(
        cid,
        file_stream=io.BytesIO(b"not a real image"),
        original_filename="x.jpg",
        mime_type="image/jpeg",
    )
    assert photo.id is not None
    assert photo.thumbnail_storage_key is None
    assert photo.thumbnail_mime_type is None
    assert photo.thumbnail_size_bytes is None


def test_thumbnail_error_is_recorded_in_audit(admin_seeded: Session, tmp_storage_dir: Path) -> None:
    from ref4ep.services.audit_logger import AuditLogger

    cid = _create_campaign(admin_seeded, code="TC-PHOTO-THUMB-AUDIT")
    _, auth = _admin_auth(admin_seeded)
    audit = AuditLogger(admin_seeded, actor_person_id=auth.person_id)
    storage = LocalFileStorage(tmp_storage_dir)
    TestCampaignPhotoService(admin_seeded, auth=auth, audit=audit, storage=storage).upload(
        cid,
        file_stream=io.BytesIO(b"corrupt"),
        original_filename="x.jpg",
        mime_type="image/jpeg",
    )
    admin_seeded.commit()
    log = (
        admin_seeded.query(AuditLog)
        .filter_by(action="campaign.photo.upload")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert log is not None
    # ``details`` ist ein JSON-Blob mit ``after``-Sektion.
    assert "thumbnail_error" in str(log.details)
