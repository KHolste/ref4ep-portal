"""API: Kampagnennotizen für Testkampagnen (Block 0029).

Auth-Boundary, CSRF, Permission-Matrix, can_edit, Soft-Delete.
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.domain.models import Person
from ref4ep.services.permissions import AuthContext
from ref4ep.services.test_campaign_note_service import TestCampaignNoteService
from ref4ep.services.test_campaign_service import TestCampaignService
from ref4ep.services.workpackage_service import WorkpackageService


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
        title="Notiz-Kampagne",
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


def _create_note_via_service(
    session: Session, *, campaign_id: str, author: Person, body: str
) -> str:
    auth = AuthContext(
        person_id=author.id,
        email=author.email,
        platform_role=author.platform_role,
        memberships=[],
    )
    note = TestCampaignNoteService(session, auth=auth).create(campaign_id, body_md=body)
    session.commit()
    return note.id


# ---- Auth-Boundary -----------------------------------------------------


def test_anonymous_cannot_list_notes(client: TestClient) -> None:
    client.cookies.clear()
    r = client.get("/api/campaigns/00000000-0000-0000-0000-000000000000/notes")
    assert r.status_code == 401


def test_anonymous_cannot_create_note(admin_client: TestClient) -> None:
    admin_client.cookies.clear()
    r = admin_client.post(
        "/api/campaigns/00000000-0000-0000-0000-000000000000/notes",
        json={"body_md": "x"},
    )
    assert r.status_code in (401, 403)


def test_csrf_required_for_create(admin_client: TestClient, seeded_session: Session) -> None:
    cid = _create_campaign(seeded_session, code="TC-NOTE-CSRF", wp_codes=["WP3"])
    r = admin_client.post(
        f"/api/campaigns/{cid}/notes",
        json={"body_md": "ohne CSRF"},
    )
    assert r.status_code == 403


# ---- Permission-Matrix --------------------------------------------------


def test_admin_can_create_and_list(admin_client: TestClient, seeded_session: Session) -> None:
    cid = _create_campaign(seeded_session, code="TC-NOTE-A1", wp_codes=["WP3"])
    r = admin_client.post(
        f"/api/campaigns/{cid}/notes",
        json={"body_md": "**Idee:** Sensor erweitern"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["body_md"].startswith("**Idee:**")
    assert body["can_edit"] is True
    assert body["campaign_id"] == cid

    rl = admin_client.get(f"/api/campaigns/{cid}/notes")
    assert rl.status_code == 200
    notes = rl.json()
    assert len(notes) == 1
    assert notes[0]["id"] == body["id"]


def test_member_without_participation_cannot_create(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    cid = _create_campaign(seeded_session, code="TC-NOTE-A2", wp_codes=["WP3"])
    r = member_client.post(
        f"/api/campaigns/{cid}/notes",
        json={"body_md": "darf nicht"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_member_participant_can_create(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    cid = _create_campaign(seeded_session, code="TC-NOTE-A3", wp_codes=["WP3"])
    _add_participant(seeded_session, cid, member_person_id)
    r = member_client.post(
        f"/api/campaigns/{cid}/notes",
        json={"body_md": "Beobachtung"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 201, r.text
    assert r.json()["can_edit"] is True
    assert r.json()["author"]["id"] == member_person_id


def test_unknown_campaign_returns_404(admin_client: TestClient) -> None:
    r = admin_client.post(
        "/api/campaigns/00000000-0000-0000-0000-000000000000/notes",
        json={"body_md": "x"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 404


def test_empty_body_returns_422(admin_client: TestClient, seeded_session: Session) -> None:
    cid = _create_campaign(seeded_session, code="TC-NOTE-EMPTY", wp_codes=["WP3"])
    r = admin_client.post(
        f"/api/campaigns/{cid}/notes",
        json={"body_md": ""},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 422


# ---- Update + Delete + can_edit ----------------------------------------


def test_author_can_update_and_delete(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    cid = _create_campaign(seeded_session, code="TC-NOTE-UPD", wp_codes=["WP3"])
    _add_participant(seeded_session, cid, member_person_id)
    create = member_client.post(
        f"/api/campaigns/{cid}/notes",
        json={"body_md": "alt"},
        headers=_csrf(member_client),
    )
    nid = create.json()["id"]

    r = member_client.patch(
        f"/api/campaign-notes/{nid}",
        json={"body_md": "neu"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 200
    assert r.json()["body_md"] == "neu"

    rd = member_client.delete(
        f"/api/campaign-notes/{nid}",
        headers=_csrf(member_client),
    )
    assert rd.status_code == 204
    rl = member_client.get(f"/api/campaigns/{cid}/notes")
    assert rl.status_code == 200
    assert rl.json() == []


def test_other_participant_cannot_update(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    """Admin legt eine Notiz an — Member ist Teilnehmer, darf aber als
    Nicht-Autor nicht bearbeiten."""
    cid = _create_campaign(seeded_session, code="TC-NOTE-FORE", wp_codes=["WP3"])
    _add_participant(seeded_session, cid, member_person_id)
    admin = seeded_session.query(Person).filter_by(email="admin@test.example").one()
    nid = _create_note_via_service(seeded_session, campaign_id=cid, author=admin, body="vom Admin")

    r = member_client.patch(
        f"/api/campaign-notes/{nid}",
        json={"body_md": "übergriffig"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_listing_marks_can_edit_per_note(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    cid = _create_campaign(seeded_session, code="TC-NOTE-FLAGS", wp_codes=["WP3"])
    _add_participant(seeded_session, cid, member_person_id)
    admin = seeded_session.query(Person).filter_by(email="admin@test.example").one()
    member = seeded_session.get(Person, member_person_id)
    nid_admin = _create_note_via_service(
        seeded_session, campaign_id=cid, author=admin, body="admin"
    )
    nid_member = _create_note_via_service(
        seeded_session, campaign_id=cid, author=member, body="member"
    )
    body = {n["id"]: n for n in member_client.get(f"/api/campaigns/{cid}/notes").json()}
    assert body[nid_member]["can_edit"] is True
    assert body[nid_admin]["can_edit"] is False


def test_campaign_detail_exposes_can_create_note(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    cid = _create_campaign(seeded_session, code="TC-NOTE-DETAIL", wp_codes=["WP3"])
    _add_participant(seeded_session, cid, member_person_id)
    body = member_client.get(f"/api/campaigns/{cid}").json()
    assert body["can_create_note"] is True


def test_campaign_detail_can_create_note_false_for_non_participant(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    cid = _create_campaign(seeded_session, code="TC-NOTE-DETAIL2", wp_codes=["WP3"])
    body = member_client.get(f"/api/campaigns/{cid}").json()
    assert body["can_create_note"] is False


def test_delete_returns_404_for_already_deleted(
    admin_client: TestClient, seeded_session: Session
) -> None:
    cid = _create_campaign(seeded_session, code="TC-NOTE-DELDEL", wp_codes=["WP3"])
    r = admin_client.post(
        f"/api/campaigns/{cid}/notes",
        json={"body_md": "weg"},
        headers=_csrf(admin_client),
    )
    nid = r.json()["id"]
    admin_client.delete(f"/api/campaign-notes/{nid}", headers=_csrf(admin_client))
    again = admin_client.delete(f"/api/campaign-notes/{nid}", headers=_csrf(admin_client))
    assert again.status_code == 404
