"""API: Aggregierter Projektkalender (Block 0023).

Aggregation aus Meetings / Testkampagnen / Meilensteinen / Aufgaben;
Filter (type / workpackage / mine / from / to); Sortierung; overdue-
Flag; Behandlung abgesagter/abgebrochener Events; Datenleckschutz.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.domain.models import Milestone, Person
from ref4ep.services.meeting_service import MeetingService
from ref4ep.services.test_campaign_service import TestCampaignService
from ref4ep.services.workpackage_service import WorkpackageService


def _wp_id(seeded_session: Session, code: str) -> str:
    wp = WorkpackageService(seeded_session).get_by_code(code)
    assert wp is not None
    return wp.id


def _admin_meeting_service(session: Session) -> MeetingService:
    admin = session.query(Person).filter_by(email="admin@test.example").one()
    return MeetingService(session, role=admin.platform_role, person_id=admin.id)


def _admin_campaign_service(session: Session) -> TestCampaignService:
    admin = session.query(Person).filter_by(email="admin@test.example").one()
    return TestCampaignService(session, role=admin.platform_role, person_id=admin.id)


def _date(y: int, m: int, d: int) -> date:
    return date(y, m, d)


def _dt(y: int, m: int, d: int, hour: int = 10) -> datetime:
    return datetime(y, m, d, hour, 0, tzinfo=UTC)


# ---- Permission-Matrix -------------------------------------------------


def test_anonymous_cannot_read_calendar(client: TestClient) -> None:
    client.cookies.clear()
    r = client.get("/api/calendar/events")
    assert r.status_code == 401


def test_member_can_read_calendar_default_month(member_client: TestClient) -> None:
    r = member_client.get("/api/calendar/events")
    assert r.status_code == 200
    assert r.json() == []


def test_admin_can_read_calendar(admin_client: TestClient) -> None:
    r = admin_client.get("/api/calendar/events")
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


# ---- Quellen sind sichtbar --------------------------------------------


def test_meetings_appear_in_range(admin_client: TestClient, seeded_session: Session) -> None:
    service = _admin_meeting_service(seeded_session)
    service.create_meeting(
        title="Kalender-Meeting",
        starts_at=_dt(2026, 6, 15, 10),
        ends_at=_dt(2026, 6, 15, 12),
        workpackage_ids=[],
    )
    seeded_session.commit()
    r = admin_client.get("/api/calendar/events?from=2026-06-01&to=2026-06-30")
    body = r.json()
    titles = [e["title"] for e in body]
    assert "Kalender-Meeting" in titles
    found = next(e for e in body if e["title"] == "Kalender-Meeting")
    assert found["type"] == "meeting"
    assert found["all_day"] is False
    assert found["link"].startswith("/portal/meetings/")


def test_campaigns_appear_in_range(admin_client: TestClient, seeded_session: Session) -> None:
    service = _admin_campaign_service(seeded_session)
    service.create_campaign(
        code="TC-CAL-01",
        title="Kalender-Kampagne",
        starts_on=_date(2026, 6, 10),
        ends_on=_date(2026, 6, 20),
        workpackage_ids=[],
    )
    seeded_session.commit()
    r = admin_client.get("/api/calendar/events?from=2026-06-01&to=2026-06-30")
    body = r.json()
    found = [e for e in body if "Kalender-Kampagne" in e["title"]]
    assert found
    e = found[0]
    assert e["type"] == "campaign"
    assert e["all_day"] is True
    assert e["link"].startswith("/portal/campaigns/")
    # Zeitraum erscheint in der Description.
    assert e["description"] and "Zeitraum" in e["description"]


def test_milestones_appear_in_range_via_planned_date(
    admin_client: TestClient, seeded_session: Session
) -> None:
    wp = _wp_id(seeded_session, "WP3.1")
    ms = Milestone(
        code="MS-CAL-01",
        title="Kalender-Meilenstein",
        workpackage_id=wp,
        planned_date=_date(2026, 6, 18),
        status="planned",
    )
    seeded_session.add(ms)
    seeded_session.commit()
    r = admin_client.get("/api/calendar/events?from=2026-06-01&to=2026-06-30")
    body = r.json()
    matching = [e for e in body if e["source_id"] == ms.id]
    assert matching
    e = matching[0]
    assert e["type"] == "milestone"
    assert e["all_day"] is True
    assert e["workpackage_codes"] == ["WP3.1"]


def test_actions_with_due_date_appear(
    admin_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
) -> None:
    service = _admin_meeting_service(seeded_session)
    meeting = service.create_meeting(
        title="Quelle für Action",
        starts_at=_dt(2026, 5, 20),
        workpackage_ids=[],
    )
    service.create_action(
        meeting_id=meeting.id,
        text="Aufgabe mit Frist",
        due_date=_date(2026, 6, 12),
        responsible_person_id=member_person_id,
        status="open",
    )
    seeded_session.commit()
    r = admin_client.get("/api/calendar/events?from=2026-06-01&to=2026-06-30&type=action")
    body = r.json()
    assert any(e["title"] == "Aufgabe mit Frist" for e in body)
    e = next(e for e in body if e["title"] == "Aufgabe mit Frist")
    assert e["type"] == "action"
    assert e["all_day"] is True
    # Link zeigt zur Meeting-Detail-Seite.
    assert e["link"].startswith("/portal/meetings/")


# ---- overdue-Flag -----------------------------------------------------


def test_actions_overdue_flag_set_for_past_open_due_date(
    admin_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
) -> None:
    service = _admin_meeting_service(seeded_session)
    meeting = service.create_meeting(
        title="OldM",
        starts_at=_dt(2020, 1, 1),
        workpackage_ids=[],
    )
    yesterday = date.today() - timedelta(days=1)
    service.create_action(
        meeting_id=meeting.id,
        text="alt und offen",
        due_date=yesterday,
        responsible_person_id=member_person_id,
        status="open",
    )
    service.create_action(
        meeting_id=meeting.id,
        text="alt aber done",
        due_date=yesterday,
        responsible_person_id=member_person_id,
        status="done",
    )
    seeded_session.commit()
    # Zeitraum, der den gestrigen Tag enthält:
    from_date = (yesterday - timedelta(days=2)).isoformat()
    to_date = (yesterday + timedelta(days=2)).isoformat()
    r = admin_client.get(f"/api/calendar/events?from={from_date}&to={to_date}&type=action")
    by_text = {e["title"]: e for e in r.json()}
    assert by_text["alt und offen"]["is_overdue"] is True
    # done → nicht overdue.
    assert by_text["alt aber done"]["is_overdue"] is False


# ---- Type-Filter ------------------------------------------------------


def test_type_filter_limits_to_one_source(
    admin_client: TestClient, seeded_session: Session
) -> None:
    _admin_meeting_service(seeded_session).create_meeting(
        title="M1", starts_at=_dt(2026, 6, 5), workpackage_ids=[]
    )
    _admin_campaign_service(seeded_session).create_campaign(
        code="TC-FILT-1",
        title="C1",
        starts_on=_date(2026, 6, 6),
        workpackage_ids=[],
    )
    seeded_session.commit()
    r = admin_client.get("/api/calendar/events?from=2026-06-01&to=2026-06-30&type=meeting")
    body = r.json()
    assert all(e["type"] == "meeting" for e in body)
    assert any(e["title"] == "M1" for e in body)
    assert not any(e["type"] == "campaign" for e in body)


def test_type_filter_accepts_comma_list(admin_client: TestClient, seeded_session: Session) -> None:
    _admin_meeting_service(seeded_session).create_meeting(
        title="M_combo", starts_at=_dt(2026, 6, 5), workpackage_ids=[]
    )
    _admin_campaign_service(seeded_session).create_campaign(
        code="TC-FILT-COMBO",
        title="C_combo",
        starts_on=_date(2026, 6, 6),
        workpackage_ids=[],
    )
    seeded_session.commit()
    r = admin_client.get("/api/calendar/events?from=2026-06-01&to=2026-06-30&type=meeting,campaign")
    types = {e["type"] for e in r.json()}
    assert types == {"meeting", "campaign"}


def test_type_filter_invalid_value_returns_422(admin_client: TestClient) -> None:
    r = admin_client.get("/api/calendar/events?type=ungueltig")
    assert r.status_code == 422


# ---- WP-Filter --------------------------------------------------------


def test_workpackage_filter_returns_only_related_events(
    admin_client: TestClient, seeded_session: Session
) -> None:
    wp_a = _wp_id(seeded_session, "WP3.1")
    wp_b = _wp_id(seeded_session, "WP4.1")
    s = _admin_meeting_service(seeded_session)
    s.create_meeting(
        title="WP3.1-Meeting",
        starts_at=_dt(2026, 7, 5),
        workpackage_ids=[wp_a],
    )
    s.create_meeting(
        title="WP4.1-Meeting",
        starts_at=_dt(2026, 7, 6),
        workpackage_ids=[wp_b],
    )
    seeded_session.commit()
    r = admin_client.get("/api/calendar/events?from=2026-07-01&to=2026-07-31&workpackage=WP3.1")
    titles = {e["title"] for e in r.json()}
    assert "WP3.1-Meeting" in titles
    assert "WP4.1-Meeting" not in titles


def test_workpackage_filter_unknown_code_returns_empty(
    admin_client: TestClient,
) -> None:
    r = admin_client.get("/api/calendar/events?workpackage=WP-DOES-NOT-EXIST")
    assert r.status_code == 200
    assert r.json() == []


# ---- mine=true --------------------------------------------------------


def test_mine_filter_meeting_via_participant(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    service = _admin_meeting_service(seeded_session)
    m1 = service.create_meeting(
        title="Mit Member als Teilnehmer",
        starts_at=_dt(2026, 6, 4),
        workpackage_ids=[],
    )
    service.add_participant(m1.id, member_person_id)
    service.create_meeting(
        title="Ohne Member",
        starts_at=_dt(2026, 6, 5),
        workpackage_ids=[],
    )
    seeded_session.commit()
    r = member_client.get("/api/calendar/events?from=2026-06-01&to=2026-06-30&mine=true")
    titles = {e["title"] for e in r.json()}
    assert "Mit Member als Teilnehmer" in titles
    assert "Ohne Member" not in titles


def test_mine_filter_meeting_via_workpackage_membership(
    member_client: TestClient,
    seeded_session: Session,
    member_in_wp3,
    admin_person_id: str,
) -> None:
    wp = _wp_id(seeded_session, "WP3")
    service = _admin_meeting_service(seeded_session)
    service.create_meeting(
        title="WP3-Meeting via Membership",
        starts_at=_dt(2026, 6, 4),
        workpackage_ids=[wp],
    )
    seeded_session.commit()
    r = member_client.get("/api/calendar/events?from=2026-06-01&to=2026-06-30&mine=true")
    titles = {e["title"] for e in r.json()}
    assert "WP3-Meeting via Membership" in titles


def test_mine_filter_action_via_responsible(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    service = _admin_meeting_service(seeded_session)
    meeting = service.create_meeting(title="X", starts_at=_dt(2026, 6, 1), workpackage_ids=[])
    service.create_action(
        meeting_id=meeting.id,
        text="Aufgabe für Member",
        due_date=_date(2026, 6, 7),
        responsible_person_id=member_person_id,
    )
    service.create_action(
        meeting_id=meeting.id,
        text="Aufgabe für Admin",
        due_date=_date(2026, 6, 8),
        responsible_person_id=admin_person_id,
    )
    seeded_session.commit()
    r = member_client.get(
        "/api/calendar/events?from=2026-06-01&to=2026-06-30&type=action&mine=true"
    )
    titles = {e["title"] for e in r.json()}
    assert "Aufgabe für Member" in titles
    assert "Aufgabe für Admin" not in titles


def test_mine_filter_milestone_includes_project_wide_ms4(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    """MS4 (workpackage_id=NULL) ist für alle relevant — bei mine=true
    wird er trotzdem mitgeliefert."""
    seeded_session.add(
        Milestone(
            code="MS-PROJ",
            title="Gesamtprojekt-MS",
            workpackage_id=None,
            planned_date=_date(2026, 6, 15),
            status="planned",
        )
    )
    seeded_session.commit()
    r = member_client.get(
        "/api/calendar/events?from=2026-06-01&to=2026-06-30&type=milestone&mine=true"
    )
    titles = {e["title"] for e in r.json()}
    assert any("Gesamtprojekt-MS" in t for t in titles)


# ---- Range-Schnitt ----------------------------------------------------


def test_event_outside_range_is_not_returned(
    admin_client: TestClient, seeded_session: Session
) -> None:
    _admin_meeting_service(seeded_session).create_meeting(
        title="Lange vorher",
        starts_at=_dt(2025, 1, 1),
        workpackage_ids=[],
    )
    seeded_session.commit()
    r = admin_client.get("/api/calendar/events?from=2026-06-01&to=2026-06-30")
    assert not any(e["title"] == "Lange vorher" for e in r.json())


def test_multiday_campaign_intersecting_window_is_returned(
    admin_client: TestClient, seeded_session: Session
) -> None:
    """Kampagne läuft 25.05.–05.06., Fenster 01.06.–30.06. → enthalten."""
    _admin_campaign_service(seeded_session).create_campaign(
        code="TC-OVR-01",
        title="Schneidende Kampagne",
        starts_on=_date(2026, 5, 25),
        ends_on=_date(2026, 6, 5),
        workpackage_ids=[],
    )
    seeded_session.commit()
    r = admin_client.get("/api/calendar/events?from=2026-06-01&to=2026-06-30")
    titles = {e["title"] for e in r.json()}
    assert any("Schneidende Kampagne" in t for t in titles)


def test_invalid_range_returns_422(admin_client: TestClient) -> None:
    r = admin_client.get("/api/calendar/events?from=2026-06-30&to=2026-06-01")
    assert r.status_code == 422


# ---- Sortierung --------------------------------------------------------


def test_events_are_sorted_by_starts_at_ascending(
    admin_client: TestClient, seeded_session: Session
) -> None:
    s = _admin_meeting_service(seeded_session)
    s.create_meeting(title="Spät", starts_at=_dt(2026, 6, 25, 10), workpackage_ids=[])
    s.create_meeting(title="Früh", starts_at=_dt(2026, 6, 5, 10), workpackage_ids=[])
    s.create_meeting(title="Mitte", starts_at=_dt(2026, 6, 15, 10), workpackage_ids=[])
    seeded_session.commit()
    r = admin_client.get("/api/calendar/events?from=2026-06-01&to=2026-06-30&type=meeting")
    titles = [e["title"] for e in r.json()]
    assert titles == ["Früh", "Mitte", "Spät"]


# ---- Abgesagte / abgebrochene Events -----------------------------------


def test_cancelled_meeting_remains_visible_with_status(
    admin_client: TestClient, seeded_session: Session
) -> None:
    service = _admin_meeting_service(seeded_session)
    meeting = service.create_meeting(
        title="Bald abgesagt",
        starts_at=_dt(2026, 6, 9),
        workpackage_ids=[],
    )
    service.cancel_meeting(meeting.id)
    seeded_session.commit()
    r = admin_client.get("/api/calendar/events?from=2026-06-01&to=2026-06-30&type=meeting")
    body = r.json()
    matching = [e for e in body if e["title"] == "Bald abgesagt"]
    assert matching
    assert matching[0]["status"] == "cancelled"


def test_cancelled_campaign_remains_visible_with_status(
    admin_client: TestClient, seeded_session: Session
) -> None:
    service = _admin_campaign_service(seeded_session)
    campaign = service.create_campaign(
        code="TC-CANCEL-01",
        title="Abgebrochene Kampagne",
        starts_on=_date(2026, 6, 11),
        workpackage_ids=[],
    )
    service.cancel_campaign(campaign.id)
    seeded_session.commit()
    r = admin_client.get("/api/calendar/events?from=2026-06-01&to=2026-06-30&type=campaign")
    matching = [e for e in r.json() if e["source_id"] == campaign.id]
    assert matching
    assert matching[0]["status"] == "cancelled"


# ---- Datenleckschutz ---------------------------------------------------


def test_calendar_response_does_not_leak_session_or_passwords(
    admin_client: TestClient, seeded_session: Session
) -> None:
    _admin_meeting_service(seeded_session).create_meeting(
        title="Smoke", starts_at=_dt(2026, 6, 1), workpackage_ids=[]
    )
    seeded_session.commit()
    body_text = admin_client.get("/api/calendar/events?from=2026-06-01&to=2026-06-30").text.lower()
    assert "session_secret" not in body_text
    assert "password" not in body_text


def test_default_range_is_current_month(admin_client: TestClient) -> None:
    """Ohne ``from``/``to`` antwortet die API mit 200 und einer Liste."""
    r = admin_client.get("/api/calendar/events")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ---- Bystander: Smoke ist UTC-konform ----------------------------------


def test_smoke_utc_now_is_aware() -> None:
    assert datetime.now(tz=UTC).tzinfo is not None
    assert time.min.hour == 0


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-06-01", "to": "2026-06-30"},
        {"from": "2026-06-01", "to": "2026-06-30", "type": "meeting"},
        {"from": "2026-06-01", "to": "2026-06-30", "type": "meeting,campaign"},
        {"from": "2026-06-01", "to": "2026-06-30", "mine": "true"},
    ],
)
def test_filter_combinations_respond_200(admin_client: TestClient, params: dict[str, str]) -> None:
    r = admin_client.get("/api/calendar/events", params=params)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
