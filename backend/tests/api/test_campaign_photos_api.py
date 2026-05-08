"""API: Foto-Upload für Testkampagnen (Block 0028).

Auth-Boundary, Permission-Matrix, MIME-Whitelist, Caption-Edit,
Soft-Delete, Streaming-Download.
"""

from __future__ import annotations

import io
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.domain.models import Person
from ref4ep.services.permissions import AuthContext
from ref4ep.services.test_campaign_photo_service import TestCampaignPhotoService
from ref4ep.services.test_campaign_service import TestCampaignService
from ref4ep.services.workpackage_service import WorkpackageService
from ref4ep.storage.local import LocalFileStorage

# 1×1 PNG.
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00"
    b"\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc"
    b"\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
JPEG_BYTES = b"\xff\xd8\xff\xe0jpeg-stub"


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def _wp_id(session: Session, code: str) -> str:
    wp = WorkpackageService(session).get_by_code(code)
    assert wp is not None
    return wp.id


def _create_campaign(session: Session, *, code: str, wp_codes: list[str]) -> str:
    admin = session.query(Person).filter_by(email="admin@test.example").one()
    wp_ids = [_wp_id(session, c) for c in wp_codes]
    campaign = TestCampaignService(
        session, role=admin.platform_role, person_id=admin.id
    ).create_campaign(
        code=code,
        title="Photo-Kampagne",
        starts_on=date.today(),
        workpackage_ids=wp_ids,
    )
    session.commit()
    return campaign.id


def _add_participant(session: Session, campaign_id: str, person_id: str) -> None:
    admin = session.query(Person).filter_by(email="admin@test.example").one()
    TestCampaignService(session, role=admin.platform_role, person_id=admin.id).add_participant(
        campaign_id, person_id=person_id, role="diagnostics"
    )
    session.commit()


def _upload_via_service(
    session: Session,
    storage_dir,
    *,
    campaign_id: str,
    uploader: Person,
    caption: str | None = None,
) -> str:
    """Lade ein Foto über den Service hoch — umgeht die TestClient-Cookie-
    Kollision zwischen ``admin_client`` und ``member_client``."""
    auth = AuthContext(
        person_id=uploader.id,
        email=uploader.email,
        platform_role=uploader.platform_role,
        memberships=[],
    )
    photo = TestCampaignPhotoService(
        session,
        auth=auth,
        storage=LocalFileStorage(storage_dir),
    ).upload(
        campaign_id,
        file_stream=io.BytesIO(PNG_BYTES),
        original_filename="x.png",
        mime_type="image/png",
        caption=caption,
    )
    session.commit()
    return photo.id


def _upload(
    client: TestClient,
    campaign_id: str,
    *,
    content: bytes = PNG_BYTES,
    filename: str = "x.png",
    mime: str = "image/png",
    caption: str | None = None,
) -> dict:
    files = {"file": (filename, content, mime)}
    data = {}
    if caption is not None:
        data["caption"] = caption
    r = client.post(
        f"/api/campaigns/{campaign_id}/photos",
        files=files,
        data=data,
        headers=_csrf(client),
    )
    return {"status": r.status_code, "json": r.json() if r.content else None, "raw": r}


# ---- Auth-Boundary -----------------------------------------------------


def test_anonymous_cannot_list_photos(client: TestClient) -> None:
    client.cookies.clear()
    r = client.get("/api/campaigns/00000000-0000-0000-0000-000000000000/photos")
    assert r.status_code == 401


def test_anonymous_cannot_upload(admin_client: TestClient) -> None:
    """Anonyme Aufrufer dürfen nicht hochladen — 401 oder 403, je nach
    Reihenfolge der Auth/CSRF-Middleware."""
    admin_client.cookies.clear()
    r = admin_client.post(
        "/api/campaigns/00000000-0000-0000-0000-000000000000/photos",
        files={"file": ("x.png", PNG_BYTES, "image/png")},
    )
    assert r.status_code in (401, 403)


def test_csrf_required_for_upload(admin_client: TestClient, seeded_session: Session) -> None:
    cid = _create_campaign(seeded_session, code="TC-PHOTO-CSRF", wp_codes=["WP3"])
    r = admin_client.post(
        f"/api/campaigns/{cid}/photos",
        files={"file": ("x.png", PNG_BYTES, "image/png")},
        # KEIN CSRF-Header
    )
    assert r.status_code == 403


# ---- Permission-Matrix --------------------------------------------------


def test_admin_can_upload_and_list(admin_client: TestClient, seeded_session: Session) -> None:
    cid = _create_campaign(seeded_session, code="TC-PHOTO-A1", wp_codes=["WP3"])
    out = _upload(admin_client, cid, caption="Aufbau A")
    assert out["status"] == 201, out["raw"].text
    body = out["json"]
    assert body["mime_type"] == "image/png"
    assert body["caption"] == "Aufbau A"
    assert body["can_edit"] is True

    r = admin_client.get(f"/api/campaigns/{cid}/photos")
    assert r.status_code == 200
    photos = r.json()
    assert len(photos) == 1
    assert photos[0]["id"] == body["id"]


def test_member_without_participation_gets_403_on_upload(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    cid = _create_campaign(seeded_session, code="TC-PHOTO-A2", wp_codes=["WP3"])
    out = _upload(member_client, cid)
    assert out["status"] == 403


def test_member_participant_can_upload(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    cid = _create_campaign(seeded_session, code="TC-PHOTO-A3", wp_codes=["WP3"])
    _add_participant(seeded_session, cid, member_person_id)
    out = _upload(member_client, cid, caption="Innenansicht")
    assert out["status"] == 201, out["raw"].text
    assert out["json"]["uploaded_by"]["id"] == member_person_id
    assert out["json"]["can_edit"] is True


def test_unsupported_mime_returns_415(admin_client: TestClient, seeded_session: Session) -> None:
    cid = _create_campaign(seeded_session, code="TC-PHOTO-MIME", wp_codes=["WP3"])
    out = _upload(
        admin_client, cid, content=b"%PDF-1.4 ...", filename="x.pdf", mime="application/pdf"
    )
    assert out["status"] == 415


def test_jpeg_accepted(admin_client: TestClient, seeded_session: Session) -> None:
    cid = _create_campaign(seeded_session, code="TC-PHOTO-JPG", wp_codes=["WP3"])
    out = _upload(admin_client, cid, content=JPEG_BYTES, filename="kammer.jpg", mime="image/jpeg")
    assert out["status"] == 201, out["raw"].text
    assert out["json"]["mime_type"] == "image/jpeg"


def test_unknown_campaign_returns_404(admin_client: TestClient) -> None:
    out = _upload(admin_client, "00000000-0000-0000-0000-000000000000", caption="x")
    assert out["status"] == 404


# ---- Caption + Delete + can_edit ---------------------------------------


def test_uploader_can_patch_caption_and_delete(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    cid = _create_campaign(seeded_session, code="TC-PHOTO-CAP", wp_codes=["WP3"])
    _add_participant(seeded_session, cid, member_person_id)
    out = _upload(member_client, cid, caption="alt")
    pid = out["json"]["id"]

    r = member_client.patch(
        f"/api/campaigns/{cid}/photos/{pid}",
        json={"caption": "neue Bildunterschrift"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 200
    assert r.json()["caption"] == "neue Bildunterschrift"

    rd = member_client.delete(
        f"/api/campaigns/{cid}/photos/{pid}",
        headers=_csrf(member_client),
    )
    assert rd.status_code == 204
    rl = member_client.get(f"/api/campaigns/{cid}/photos")
    assert rl.status_code == 200
    assert rl.json() == []


def test_other_participant_cannot_patch_caption(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
    tmp_storage_dir,
) -> None:
    """Admin lädt hoch — Member ist Teilnehmer, darf aber als Nicht-
    Uploader die Caption nicht ändern."""
    cid = _create_campaign(seeded_session, code="TC-PHOTO-FORE", wp_codes=["WP3"])
    _add_participant(seeded_session, cid, member_person_id)
    admin = seeded_session.query(Person).filter_by(email="admin@test.example").one()
    pid = _upload_via_service(
        seeded_session, tmp_storage_dir, campaign_id=cid, uploader=admin, caption="vom Admin"
    )
    r = member_client.patch(
        f"/api/campaigns/{cid}/photos/{pid}",
        json={"caption": "Übergriff"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_listing_marks_can_edit_per_photo(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
    tmp_storage_dir,
) -> None:
    cid = _create_campaign(seeded_session, code="TC-PHOTO-FLAGS", wp_codes=["WP3"])
    _add_participant(seeded_session, cid, member_person_id)
    admin = seeded_session.query(Person).filter_by(email="admin@test.example").one()
    member = seeded_session.get(Person, member_person_id)
    pid_admin = _upload_via_service(
        seeded_session, tmp_storage_dir, campaign_id=cid, uploader=admin, caption="Admin-Foto"
    )
    pid_member = _upload_via_service(
        seeded_session, tmp_storage_dir, campaign_id=cid, uploader=member, caption="Member-Foto"
    )
    # Member sieht beide; can_edit nur auf eigenem Upload.
    body = {p["id"]: p for p in member_client.get(f"/api/campaigns/{cid}/photos").json()}
    assert body[pid_member]["can_edit"] is True
    assert body[pid_admin]["can_edit"] is False


def test_campaign_detail_exposes_can_upload_photo_for_participant(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    cid = _create_campaign(seeded_session, code="TC-PHOTO-DETAIL", wp_codes=["WP3"])
    _add_participant(seeded_session, cid, member_person_id)
    body = member_client.get(f"/api/campaigns/{cid}").json()
    assert body["can_upload_photo"] is True


def test_campaign_detail_can_upload_photo_false_for_non_participant(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    cid = _create_campaign(seeded_session, code="TC-PHOTO-DETAIL2", wp_codes=["WP3"])
    body = member_client.get(f"/api/campaigns/{cid}").json()
    assert body["can_upload_photo"] is False


# ---- Download ----------------------------------------------------------


def test_download_streams_inline_with_correct_headers(
    admin_client: TestClient, seeded_session: Session
) -> None:
    cid = _create_campaign(seeded_session, code="TC-PHOTO-DL", wp_codes=["WP3"])
    pid = _upload(admin_client, cid)["json"]["id"]
    r = admin_client.get(f"/api/campaigns/{cid}/photos/{pid}/download")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")
    assert "inline" in r.headers["content-disposition"].lower()
    assert r.headers.get("cache-control") == "private"
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.content == PNG_BYTES


def test_download_returns_404_for_soft_deleted_photo(
    admin_client: TestClient, seeded_session: Session
) -> None:
    cid = _create_campaign(seeded_session, code="TC-PHOTO-DLDEL", wp_codes=["WP3"])
    pid = _upload(admin_client, cid)["json"]["id"]
    admin_client.delete(f"/api/campaigns/{cid}/photos/{pid}", headers=_csrf(admin_client))
    r = admin_client.get(f"/api/campaigns/{cid}/photos/{pid}/download")
    assert r.status_code == 404
