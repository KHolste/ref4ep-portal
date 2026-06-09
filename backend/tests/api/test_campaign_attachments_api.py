"""API: Datei-Anhänge für Testkampagnen (Block 0044).

Auth-Boundary, Permission-Matrix, MIME-Whitelist (PDF/CSV/Office/Bild),
Beschreibung-Edit, Soft-Delete, Streaming-Download, Thumbnail.
"""

from __future__ import annotations

import io
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.domain.models import Person
from ref4ep.services.permissions import AuthContext
from ref4ep.services.test_campaign_attachment_service import TestCampaignAttachmentService
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
        title="Anhang-Kampagne",
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
    description: str | None = None,
) -> str:
    auth = AuthContext(
        person_id=uploader.id,
        email=uploader.email,
        platform_role=uploader.platform_role,
        memberships=[],
    )
    att = TestCampaignAttachmentService(
        session, auth=auth, storage=LocalFileStorage(storage_dir)
    ).upload(
        campaign_id,
        file_stream=io.BytesIO(PDF_BYTES),
        original_filename="x.pdf",
        mime_type="application/pdf",
        description=description,
    )
    session.commit()
    return att.id


def _upload(
    client: TestClient,
    campaign_id: str,
    *,
    content: bytes = PDF_BYTES,
    filename: str = "x.pdf",
    mime: str = "application/pdf",
    description: str | None = None,
) -> dict:
    files = {"file": (filename, content, mime)}
    data = {}
    if description is not None:
        data["description"] = description
    r = client.post(
        f"/api/campaigns/{campaign_id}/attachments",
        files=files,
        data=data,
        headers=_csrf(client),
    )
    return {"status": r.status_code, "json": r.json() if r.content else None, "raw": r}


# ---- Auth-Boundary -----------------------------------------------------


def test_anonymous_cannot_list_attachments(client: TestClient) -> None:
    client.cookies.clear()
    r = client.get("/api/campaigns/00000000-0000-0000-0000-000000000000/attachments")
    assert r.status_code == 401


def test_csrf_required_for_upload(admin_client: TestClient, seeded_session: Session) -> None:
    cid = _create_campaign(seeded_session, code="TC-ATT-CSRF", wp_codes=["WP3"])
    r = admin_client.post(
        f"/api/campaigns/{cid}/attachments",
        files={"file": ("x.pdf", PDF_BYTES, "application/pdf")},
    )
    assert r.status_code == 403


# ---- Permission-Matrix + Whitelist -------------------------------------


def test_admin_can_upload_pdf_and_list(
    admin_client: TestClient, seeded_session: Session
) -> None:
    cid = _create_campaign(seeded_session, code="TC-ATT-A1", wp_codes=["WP3"])
    out = _upload(admin_client, cid, description="Rohprotokoll")
    assert out["status"] == 201, out["raw"].text
    body = out["json"]
    assert body["mime_type"] == "application/pdf"
    assert body["description"] == "Rohprotokoll"
    assert body["can_edit"] is True
    assert body["has_thumbnail"] is False

    r = admin_client.get(f"/api/campaigns/{cid}/attachments")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_csv_accepted(admin_client: TestClient, seeded_session: Session) -> None:
    cid = _create_campaign(seeded_session, code="TC-ATT-CSV", wp_codes=["WP3"])
    out = _upload(admin_client, cid, content=CSV_BYTES, filename="messwerte.csv", mime="text/csv")
    assert out["status"] == 201, out["raw"].text
    assert out["json"]["mime_type"] == "text/csv"


def test_image_upload_reports_thumbnail(
    admin_client: TestClient, seeded_session: Session
) -> None:
    cid = _create_campaign(seeded_session, code="TC-ATT-IMG", wp_codes=["WP3"])
    out = _upload(
        admin_client, cid, content=_real_jpeg_bytes(), filename="kammer.jpg", mime="image/jpeg"
    )
    assert out["status"] == 201, out["raw"].text
    assert out["json"]["has_thumbnail"] is True
    assert out["json"]["thumbnail_mime_type"] == "image/jpeg"


def test_unsupported_mime_returns_415(
    admin_client: TestClient, seeded_session: Session
) -> None:
    cid = _create_campaign(seeded_session, code="TC-ATT-MIME", wp_codes=["WP3"])
    out = _upload(
        admin_client, cid, content=b"<html></html>", filename="x.html", mime="text/html"
    )
    assert out["status"] == 415


def test_member_without_participation_gets_403(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    cid = _create_campaign(seeded_session, code="TC-ATT-A2", wp_codes=["WP3"])
    out = _upload(member_client, cid)
    assert out["status"] == 403


def test_member_participant_can_upload(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    cid = _create_campaign(seeded_session, code="TC-ATT-A3", wp_codes=["WP3"])
    _add_participant(seeded_session, cid, member_person_id)
    out = _upload(member_client, cid, description="Messreihe")
    assert out["status"] == 201, out["raw"].text
    assert out["json"]["uploaded_by"]["id"] == member_person_id


def test_unknown_campaign_returns_404(admin_client: TestClient) -> None:
    out = _upload(admin_client, "00000000-0000-0000-0000-000000000000")
    assert out["status"] == 404


# ---- Beschreibung + Delete + can_edit ----------------------------------


def test_uploader_can_patch_description_and_delete(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    cid = _create_campaign(seeded_session, code="TC-ATT-CAP", wp_codes=["WP3"])
    _add_participant(seeded_session, cid, member_person_id)
    aid = _upload(member_client, cid, description="alt")["json"]["id"]

    r = member_client.patch(
        f"/api/campaigns/{cid}/attachments/{aid}",
        json={"description": "neue Beschreibung"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 200
    assert r.json()["description"] == "neue Beschreibung"

    rd = member_client.delete(
        f"/api/campaigns/{cid}/attachments/{aid}",
        headers=_csrf(member_client),
    )
    assert rd.status_code == 204
    assert member_client.get(f"/api/campaigns/{cid}/attachments").json() == []


def test_other_participant_cannot_patch_description(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
    tmp_storage_dir,
) -> None:
    cid = _create_campaign(seeded_session, code="TC-ATT-FORE", wp_codes=["WP3"])
    _add_participant(seeded_session, cid, member_person_id)
    admin = seeded_session.query(Person).filter_by(email="admin@test.example").one()
    aid = _upload_via_service(
        seeded_session, tmp_storage_dir, campaign_id=cid, uploader=admin, description="vom Admin"
    )
    r = member_client.patch(
        f"/api/campaigns/{cid}/attachments/{aid}",
        json={"description": "Übergriff"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_detail_exposes_can_upload_attachment(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    cid = _create_campaign(seeded_session, code="TC-ATT-DETAIL", wp_codes=["WP3"])
    _add_participant(seeded_session, cid, member_person_id)
    body = member_client.get(f"/api/campaigns/{cid}").json()
    assert body["can_upload_attachment"] is True


def test_detail_can_upload_attachment_false_for_non_participant(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    cid = _create_campaign(seeded_session, code="TC-ATT-DETAIL2", wp_codes=["WP3"])
    body = member_client.get(f"/api/campaigns/{cid}").json()
    assert body["can_upload_attachment"] is False


# ---- Download + Thumbnail ----------------------------------------------


def test_download_streams_as_attachment(
    admin_client: TestClient, seeded_session: Session
) -> None:
    cid = _create_campaign(seeded_session, code="TC-ATT-DL", wp_codes=["WP3"])
    aid = _upload(admin_client, cid)["json"]["id"]
    r = admin_client.get(f"/api/campaigns/{cid}/attachments/{aid}/download")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    # Beliebige Dateitypen → Download statt Inline-Rendering.
    assert "attachment" in r.headers["content-disposition"].lower()
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.content == PDF_BYTES


def test_download_returns_404_for_soft_deleted(
    admin_client: TestClient, seeded_session: Session
) -> None:
    cid = _create_campaign(seeded_session, code="TC-ATT-DLDEL", wp_codes=["WP3"])
    aid = _upload(admin_client, cid)["json"]["id"]
    admin_client.delete(
        f"/api/campaigns/{cid}/attachments/{aid}", headers=_csrf(admin_client)
    )
    r = admin_client.get(f"/api/campaigns/{cid}/attachments/{aid}/download")
    assert r.status_code == 404


def test_thumbnail_endpoint_for_image(
    admin_client: TestClient, seeded_session: Session
) -> None:
    cid = _create_campaign(seeded_session, code="TC-ATT-THUMB", wp_codes=["WP3"])
    aid = _upload(
        admin_client, cid, content=_real_jpeg_bytes(), filename="kammer.jpg", mime="image/jpeg"
    )["json"]["id"]
    r = admin_client.get(f"/api/campaigns/{cid}/attachments/{aid}/thumbnail")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/jpeg")
    assert r.content[:3] == b"\xff\xd8\xff"
