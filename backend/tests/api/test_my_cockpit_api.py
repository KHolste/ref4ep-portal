"""API: Personalisierte Cockpit-Sicht (Block 0018).

``GET /api/cockpit/me`` aggregiert pro eingeloggter Person:
eigene Workpackages, eigene Aufgaben (offen + überfällig) und
nächste Meetings.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.domain.models import Person
from ref4ep.services.meeting_service import MeetingService
from ref4ep.services.workpackage_service import WorkpackageService


def _wp_id(session: Session, code: str) -> str:
    wp = WorkpackageService(session).get_by_code(code)
    assert wp is not None
    return wp.id


def _admin_meeting(
    session: Session,
    *,
    wp_codes: list[str],
    starts_at: datetime | None = None,
    title: str = "M",
) -> str:
    admin = session.query(Person).filter_by(email="admin@test.example").one()
    service = MeetingService(session, role=admin.platform_role, person_id=admin.id)
    meeting = service.create_meeting(
        title=title,
        starts_at=starts_at or datetime.now(tz=UTC),
        workpackage_ids=[_wp_id(session, c) for c in wp_codes],
    )
    session.commit()
    return meeting.id


def _admin_action(
    session: Session,
    meeting_id: str,
    *,
    responsible_id: str | None = None,
    due: date | None = None,
    status: str = "open",
    text: str = "Aufgabe",
) -> str:
    admin = session.query(Person).filter_by(email="admin@test.example").one()
    service = MeetingService(session, role=admin.platform_role, person_id=admin.id)
    action = service.create_action(
        meeting_id=meeting_id,
        text=text,
        responsible_person_id=responsible_id,
        due_date=due,
        status=status,
    )
    session.commit()
    return action.id


def _add_participant(session: Session, meeting_id: str, person_id: str) -> None:
    admin = session.query(Person).filter_by(email="admin@test.example").one()
    service = MeetingService(session, role=admin.platform_role, person_id=admin.id)
    service.add_participant(meeting_id, person_id=person_id)
    session.commit()


# ---- Auth + Schema ----------------------------------------------------


def test_anonymous_cannot_get_my_cockpit(client: TestClient) -> None:
    client.cookies.clear()
    r = client.get("/api/cockpit/me")
    assert r.status_code == 401


def test_member_gets_empty_cockpit_initially(member_client: TestClient) -> None:
    r = member_client.get("/api/cockpit/me")
    assert r.status_code == 200
    body = r.json()
    assert "today" in body
    assert body["my_workpackages"] == []
    assert body["my_lead_workpackages"] == []
    assert body["my_open_actions"] == []
    assert body["my_overdue_actions"] == []
    assert body["my_next_meetings"] == []


# ---- my_workpackages / my_lead_workpackages --------------------------


def test_member_sees_their_workpackage(
    member_client: TestClient,
    seeded_session: Session,
    member_in_wp3,
) -> None:
    r = member_client.get("/api/cockpit/me")
    body = r.json()
    codes = [w["code"] for w in body["my_workpackages"]]
    assert "WP3" in codes
    # Member-Rolle, also nicht in Lead-Liste.
    assert all(w["code"] != "WP3" for w in body["my_lead_workpackages"])


def test_lead_sees_workpackage_in_both_lists(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
) -> None:
    r = member_client.get("/api/cockpit/me")
    body = r.json()
    assert any(w["code"] == "WP3" and w["wp_role"] == "wp_lead" for w in body["my_workpackages"])
    assert any(w["code"] == "WP3" for w in body["my_lead_workpackages"])


# ---- my_open_actions / my_overdue_actions ----------------------------


def test_open_action_shows_in_open_list(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    meeting_id = _admin_meeting(seeded_session, wp_codes=[])
    _admin_action(
        seeded_session,
        meeting_id,
        responsible_id=member_person_id,
        due=date.today() + timedelta(days=5),
        text="Künftige Aufgabe",
    )
    r = member_client.get("/api/cockpit/me")
    body = r.json()
    assert len(body["my_open_actions"]) == 1
    assert body["my_open_actions"][0]["text"] == "Künftige Aufgabe"
    assert body["my_overdue_actions"] == []


def test_overdue_action_lands_in_overdue_list_only(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    meeting_id = _admin_meeting(seeded_session, wp_codes=[])
    _admin_action(
        seeded_session,
        meeting_id,
        responsible_id=member_person_id,
        due=date.today() - timedelta(days=2),
        text="Verspätet",
    )
    r = member_client.get("/api/cockpit/me")
    body = r.json()
    assert len(body["my_overdue_actions"]) == 1
    assert body["my_overdue_actions"][0]["text"] == "Verspätet"
    assert body["my_overdue_actions"][0]["overdue"] is True
    assert body["my_open_actions"] == []


def test_done_action_is_neither_open_nor_overdue(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    meeting_id = _admin_meeting(seeded_session, wp_codes=[])
    _admin_action(
        seeded_session,
        meeting_id,
        responsible_id=member_person_id,
        due=date.today() - timedelta(days=2),
        status="done",
        text="Fertig",
    )
    r = member_client.get("/api/cockpit/me")
    body = r.json()
    assert body["my_open_actions"] == []
    assert body["my_overdue_actions"] == []


def test_action_assigned_to_other_person_is_not_listed(
    member_client: TestClient,
    seeded_session: Session,
    admin_person_id: str,
) -> None:
    meeting_id = _admin_meeting(seeded_session, wp_codes=[])
    _admin_action(
        seeded_session,
        meeting_id,
        responsible_id=admin_person_id,
        text="Nicht meine",
    )
    r = member_client.get("/api/cockpit/me")
    body = r.json()
    assert body["my_open_actions"] == []
    assert body["my_overdue_actions"] == []


# ---- my_next_meetings -------------------------------------------------


def test_next_meeting_appears_when_member_is_participant(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    starts = datetime.now(tz=UTC) + timedelta(days=3)
    meeting_id = _admin_meeting(seeded_session, wp_codes=[], starts_at=starts, title="Mit Member")
    _add_participant(seeded_session, meeting_id, member_person_id)
    r = member_client.get("/api/cockpit/me")
    titles = [m["title"] for m in r.json()["my_next_meetings"]]
    assert "Mit Member" in titles


def test_next_meeting_appears_via_workpackage_membership(
    member_client: TestClient,
    seeded_session: Session,
    member_in_wp3,
    admin_person_id: str,
) -> None:
    starts = datetime.now(tz=UTC) + timedelta(days=2)
    _admin_meeting(seeded_session, wp_codes=["WP3"], starts_at=starts, title="WP3-Meeting")
    r = member_client.get("/api/cockpit/me")
    titles = [m["title"] for m in r.json()["my_next_meetings"]]
    assert "WP3-Meeting" in titles


def test_next_meeting_excludes_past_meetings(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    past = datetime.now(tz=UTC) - timedelta(days=2)
    meeting_id = _admin_meeting(seeded_session, wp_codes=[], starts_at=past, title="Vorbei")
    _add_participant(seeded_session, meeting_id, member_person_id)
    r = member_client.get("/api/cockpit/me")
    assert all(m["title"] != "Vorbei" for m in r.json()["my_next_meetings"])


def test_next_meeting_excludes_cancelled(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    starts = datetime.now(tz=UTC) + timedelta(days=3)
    meeting_id = _admin_meeting(seeded_session, wp_codes=[], starts_at=starts, title="Abgesagt")
    _add_participant(seeded_session, meeting_id, member_person_id)
    # Direkt im Modell auf cancelled setzen — vermeidet API-Round-Trip.
    from ref4ep.domain.models import Meeting

    meeting = seeded_session.get(Meeting, meeting_id)
    assert meeting is not None
    meeting.status = "cancelled"
    seeded_session.commit()
    r = member_client.get("/api/cockpit/me")
    assert all(m["title"] != "Abgesagt" for m in r.json()["my_next_meetings"])


def test_next_meeting_carries_workpackage_codes(
    member_client: TestClient,
    seeded_session: Session,
    member_in_wp3,
    admin_person_id: str,
) -> None:
    starts = datetime.now(tz=UTC) + timedelta(days=1)
    _admin_meeting(seeded_session, wp_codes=["WP3"], starts_at=starts, title="X")
    r = member_client.get("/api/cockpit/me")
    matches = [m for m in r.json()["my_next_meetings"] if m["title"] == "X"]
    assert matches
    assert "WP3" in matches[0]["workpackage_codes"]


# ---- Datenleckschutz --------------------------------------------------


def test_response_does_not_leak_password_hash(
    member_client: TestClient,
    seeded_session: Session,
    member_in_wp3,
) -> None:
    r = member_client.get("/api/cockpit/me")
    body_text = r.text.lower()
    assert "password" not in body_text
    assert "hash" not in body_text
