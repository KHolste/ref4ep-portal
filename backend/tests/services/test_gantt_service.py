"""GanttService — Aggregation der Timeline-Daten (Block 0026)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from ref4ep.domain.models import (
    Meeting,
    MeetingWorkpackage,
    Milestone,
    Person,
    TestCampaign,
    Workpackage,
)
from ref4ep.services.gantt_service import (
    CONSORTIUM_TRACK_CODE,
    PROJECT_DURATION_MONTHS,
    GanttService,
)


def _admin_id(session: Session) -> str:
    return session.query(Person).filter_by(email="admin@test.example").one().id


# ---- Projektzeitfenster ------------------------------------------------


def test_empty_db_falls_back_to_today_window(session: Session) -> None:
    """Ohne Daten: Window um heute, Dauer = 36 Monate."""
    today = date(2026, 5, 8)
    board = GanttService(session, today=today).build()
    assert board.today == today
    assert board.project_start == date(2026, 5, 1)
    assert board.project_end.year == 2029
    assert board.project_end.month == 5


def test_project_window_uses_earliest_actual_data(seeded_session: Session) -> None:
    today = date(2026, 5, 8)
    board = GanttService(seeded_session, today=today).build()
    earliest = min(ms.planned_date for ms in seeded_session.query(Milestone).all())
    assert board.project_start == date(earliest.year, earliest.month, 1)
    assert board.project_end >= board.project_start


def test_project_duration_constant() -> None:
    """Sanity: 36 Monate entsprechen der Spec."""
    assert PROJECT_DURATION_MONTHS == 36


# ---- Tracks / Sortierung ----------------------------------------------


def test_tracks_contain_workpackages_in_order(seeded_session: Session) -> None:
    today = date(2026, 5, 8)
    board = GanttService(seeded_session, today=today).build()
    codes = [t.code for t in board.tracks]
    assert len(codes) == len(set(codes))
    sort_orders = [t.sort_order for t in board.tracks]
    assert sort_orders == sorted(sort_orders)


def test_milestone_without_wp_lands_on_consortium_track(seeded_session: Session) -> None:
    today = date(2026, 5, 8)
    ms = Milestone(
        code="MS-CONS",
        title="Konsortial-MS",
        workpackage_id=None,
        planned_date=date(2026, 9, 1),
        status="planned",
    )
    seeded_session.add(ms)
    seeded_session.commit()

    board = GanttService(seeded_session, today=today).build()
    consortium = next((t for t in board.tracks if t.code == CONSORTIUM_TRACK_CODE), None)
    assert consortium is not None
    assert "MS-CONS" in [m.code for m in consortium.milestones]


# ---- Ampel-Propagation -------------------------------------------------


def test_milestone_traffic_light_propagates(seeded_session: Session) -> None:
    today = date(2026, 5, 8)
    ms = seeded_session.query(Milestone).filter(Milestone.workpackage_id.isnot(None)).first()
    assert ms is not None
    ms.status = "at_risk"
    seeded_session.commit()

    board = GanttService(seeded_session, today=today).build()
    matching = [m for t in board.tracks for m in t.milestones if m.id == ms.id]
    assert matching, "Meilenstein nicht in den Tracks"
    assert matching[0].traffic_light == "red"


# ---- Kampagnen ---------------------------------------------------------


def test_open_campaign_keeps_ends_on_none(seeded_session: Session, admin_person_id: str) -> None:
    """Eine Kampagne ohne ``ends_on`` bleibt mit ``None`` — das Frontend
    rendert sie gestrichelt bis zum Achsenende."""
    today = date(2026, 5, 8)
    open_camp = TestCampaign(
        code="TC-OPEN",
        title="Offen",
        starts_on=date(2026, 7, 1),
        ends_on=None,
        category="other",
        status="running",
        created_by_id=_admin_id(seeded_session),
    )
    seeded_session.add(open_camp)
    seeded_session.commit()

    board = GanttService(seeded_session, today=today).build()
    found = [c for t in board.tracks for c in t.campaigns if c.code == "TC-OPEN"]
    assert found
    assert found[0].ends_on is None


# ---- Meetings ----------------------------------------------------------


def test_meeting_appears_in_track_via_workpackage_link(
    seeded_session: Session, admin_person_id: str
) -> None:
    today = date(2026, 5, 8)
    wp3 = seeded_session.query(Workpackage).filter_by(code="WP3").one()
    mtg = Meeting(
        title="WP3 Jour Fixe",
        starts_at=datetime(2026, 6, 15, 9, 0, tzinfo=UTC),
        ends_at=None,
        format="online",
        category="jour_fixe",
        status="planned",
        created_by_id=_admin_id(seeded_session),
    )
    seeded_session.add(mtg)
    seeded_session.flush()
    seeded_session.add(MeetingWorkpackage(meeting_id=mtg.id, workpackage_id=wp3.id))
    seeded_session.commit()

    board = GanttService(seeded_session, today=today).build()
    wp3_track = next(t for t in board.tracks if t.code == "WP3")
    assert "WP3 Jour Fixe" in [m.title for m in wp3_track.meetings]


def test_cancelled_meeting_is_skipped(seeded_session: Session, admin_person_id: str) -> None:
    today = date(2026, 5, 8)
    mtg = Meeting(
        title="Abgesagt",
        starts_at=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
        format="online",
        category="other",
        status="cancelled",
        created_by_id=_admin_id(seeded_session),
    )
    seeded_session.add(mtg)
    seeded_session.commit()

    board = GanttService(seeded_session, today=today).build()
    titles = {m.title for t in board.tracks for m in t.meetings}
    assert "Abgesagt" not in titles
