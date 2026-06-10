"""API: Wiederkehrende Termine/Meetings — V1 (Block 0052).

Deckt ab:
- Anlegen einmaliger Termine bleibt unverändert,
- Anlegen mit Wiederholung (weekly/biweekly/monthly) + Enddatum,
- Validierung (Enddatum Pflicht + muss nach Start liegen),
- Kalender-Expansion in konkrete Vorkommen,
- Begrenzung durch ``recurrence_until``,
- Expansion NUR innerhalb des abgefragten Fensters.

Die Expansion ist read-only im ``CalendarService``; es werden keine
Vorkommen materialisiert (eine Serie = ein Meeting-Datensatz).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.domain.models import Person
from ref4ep.services.meeting_service import MeetingService


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def _admin_meeting_service(session: Session) -> MeetingService:
    admin = session.query(Person).filter_by(email="admin@test.example").one()
    return MeetingService(session, role=admin.platform_role, person_id=admin.id)


def _dt(y: int, m: int, d: int, hour: int = 10) -> datetime:
    return datetime(y, m, d, hour, 0, tzinfo=UTC)


def _occurrence_dates(body: list[dict], title: str) -> list[str]:
    """Datumsanteile (YYYY-MM-DD) aller Kalender-Vorkommen mit ``title``."""
    return sorted(e["starts_at"][:10] for e in body if e["title"] == title)


# ---- Anlegen / Validierung (API) --------------------------------------


def test_create_single_meeting_defaults_to_no_recurrence(admin_client: TestClient) -> None:
    r = admin_client.post(
        "/api/meetings",
        json={
            "title": "Einmal-Termin",
            "starts_at": "2026-06-15T10:00:00",
            "workpackage_ids": [],
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["recurrence_rule"] == "none"
    assert body["recurrence_until"] is None


def test_create_weekly_meeting_with_until(admin_client: TestClient) -> None:
    r = admin_client.post(
        "/api/meetings",
        json={
            "title": "Wöchentlich",
            "starts_at": "2026-06-01T10:00:00",
            "recurrence_rule": "weekly",
            "recurrence_until": "2026-08-31",
            "workpackage_ids": [],
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["recurrence_rule"] == "weekly"
    assert body["recurrence_until"] == "2026-08-31"


def test_create_rejects_recurrence_without_until(admin_client: TestClient) -> None:
    r = admin_client.post(
        "/api/meetings",
        json={
            "title": "Ohne Ende",
            "starts_at": "2026-06-01T10:00:00",
            "recurrence_rule": "weekly",
            "workpackage_ids": [],
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 422, r.text


def test_create_rejects_until_before_start(admin_client: TestClient) -> None:
    r = admin_client.post(
        "/api/meetings",
        json={
            "title": "Ende vor Start",
            "starts_at": "2026-06-15T10:00:00",
            "recurrence_rule": "weekly",
            "recurrence_until": "2026-06-10",
            "workpackage_ids": [],
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 422, r.text


# ---- Kalender-Expansion ------------------------------------------------


def test_single_meeting_appears_once(admin_client: TestClient, seeded_session: Session) -> None:
    _admin_meeting_service(seeded_session).create_meeting(
        title="Solo",
        starts_at=_dt(2026, 6, 10, 10),
        workpackage_ids=[],
    )
    seeded_session.commit()
    r = admin_client.get("/api/calendar/events?from=2026-06-01&to=2026-06-30&type=meeting")
    assert _occurrence_dates(r.json(), "Solo") == ["2026-06-10"]


def test_weekly_recurrence_expands_in_window(
    admin_client: TestClient, seeded_session: Session
) -> None:
    _admin_meeting_service(seeded_session).create_meeting(
        title="W-Serie",
        starts_at=_dt(2026, 6, 1, 10),
        recurrence_rule="weekly",
        recurrence_until=date(2026, 8, 31),
        workpackage_ids=[],
    )
    seeded_session.commit()
    r = admin_client.get("/api/calendar/events?from=2026-06-01&to=2026-06-30&type=meeting")
    assert _occurrence_dates(r.json(), "W-Serie") == [
        "2026-06-01",
        "2026-06-08",
        "2026-06-15",
        "2026-06-22",
        "2026-06-29",
    ]


def test_biweekly_recurrence_every_14_days(
    admin_client: TestClient, seeded_session: Session
) -> None:
    _admin_meeting_service(seeded_session).create_meeting(
        title="14-Serie",
        starts_at=_dt(2026, 6, 2, 9),
        recurrence_rule="biweekly",
        recurrence_until=date(2026, 9, 30),
        workpackage_ids=[],
    )
    seeded_session.commit()
    r = admin_client.get("/api/calendar/events?from=2026-06-01&to=2026-06-30&type=meeting")
    # 02.06., +14 = 16.06., +14 = 30.06.
    assert _occurrence_dates(r.json(), "14-Serie") == [
        "2026-06-02",
        "2026-06-16",
        "2026-06-30",
    ]


def test_monthly_recurrence_same_day(admin_client: TestClient, seeded_session: Session) -> None:
    _admin_meeting_service(seeded_session).create_meeting(
        title="M-Serie",
        starts_at=_dt(2026, 6, 10, 14),
        recurrence_rule="monthly",
        recurrence_until=date(2026, 12, 31),
        workpackage_ids=[],
    )
    seeded_session.commit()
    r = admin_client.get("/api/calendar/events?from=2026-06-01&to=2026-09-30&type=meeting")
    assert _occurrence_dates(r.json(), "M-Serie") == [
        "2026-06-10",
        "2026-07-10",
        "2026-08-10",
        "2026-09-10",
    ]


def test_recurrence_bounded_by_until(admin_client: TestClient, seeded_session: Session) -> None:
    _admin_meeting_service(seeded_session).create_meeting(
        title="Kurz-Serie",
        starts_at=_dt(2026, 6, 1, 10),
        recurrence_rule="weekly",
        recurrence_until=date(2026, 6, 15),
        workpackage_ids=[],
    )
    seeded_session.commit()
    r = admin_client.get("/api/calendar/events?from=2026-06-01&to=2026-06-30&type=meeting")
    # Endet am 15.06. — kein 22./29.06.
    assert _occurrence_dates(r.json(), "Kurz-Serie") == [
        "2026-06-01",
        "2026-06-08",
        "2026-06-15",
    ]


def test_expansion_only_within_queried_window(
    admin_client: TestClient, seeded_session: Session
) -> None:
    """Eine Serie, die VOR dem Fenster beginnt und weit danach endet,
    liefert nur die Vorkommen INNERHALB des abgefragten Fensters."""
    _admin_meeting_service(seeded_session).create_meeting(
        title="Lange-Serie",
        starts_at=_dt(2026, 5, 4, 10),  # Start vor dem Fenster
        recurrence_rule="weekly",
        recurrence_until=date(2026, 12, 31),
        workpackage_ids=[],
    )
    seeded_session.commit()
    # Fenster 08.06.–21.06.: Serie ist 04.05.+7k -> 08.06. und 15.06.
    r = admin_client.get("/api/calendar/events?from=2026-06-08&to=2026-06-21&type=meeting")
    assert _occurrence_dates(r.json(), "Lange-Serie") == [
        "2026-06-08",
        "2026-06-15",
    ]
