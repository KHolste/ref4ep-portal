"""ProjectDashboardService — Aggregate fürs Cockpit (Block 0010)."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from ref4ep.services.milestone_service import MilestoneService
from ref4ep.services.project_dashboard_service import (
    OPEN_MILESTONE_STATUSES,
    ProjectDashboardService,
)
from ref4ep.services.workpackage_service import WorkpackageService

# Heute-Anker zum Zeitpunkt des Antrags. So sieht der Service:
#   MS1 (2026-03-02, achieved)         → ignoriert (achieved)
#   MS2 (2027-02-15, planned)          → upcoming
#   MS3 (2028-02-15, planned)          → upcoming
#   MS4 (2029-02-28, planned)          → upcoming
TODAY_BEFORE_PROJECT = date(2026, 5, 4)


# ---- upcoming_milestones -----------------------------------------------


def test_upcoming_returns_open_milestones_in_future_only(
    seeded_session: Session,
) -> None:
    svc = ProjectDashboardService(seeded_session, today=TODAY_BEFORE_PROJECT)
    upcoming = svc.upcoming_milestones()
    codes = [ms.code for ms in upcoming]
    # MS1 ist achieved → fehlt
    assert "MS1" not in codes
    # MS2/MS3/MS4 sind in der Zukunft und planned → enthalten
    assert codes == ["MS2", "MS3", "MS4"]
    # Sortierung aufsteigend nach Plandatum
    plans = [ms.planned_date for ms in upcoming]
    assert plans == sorted(plans)


def test_upcoming_respects_limit(seeded_session: Session) -> None:
    svc = ProjectDashboardService(seeded_session, today=TODAY_BEFORE_PROJECT)
    upcoming = svc.upcoming_milestones(limit=2)
    assert len(upcoming) == 2
    assert [ms.code for ms in upcoming] == ["MS2", "MS3"]


def test_upcoming_excludes_overdue(seeded_session: Session) -> None:
    """Wenn ‚heute' > Plandatum, taucht der MS in upcoming nicht mehr auf."""
    svc = ProjectDashboardService(seeded_session, today=date(2027, 6, 1))
    upcoming = [ms.code for ms in svc.upcoming_milestones()]
    # MS2 (2027-02-15) ist überfällig → nicht in upcoming
    assert "MS2" not in upcoming
    assert "MS3" in upcoming
    assert "MS4" in upcoming


def test_upcoming_excludes_cancelled_status(seeded_session: Session) -> None:
    """Sicherheit: nur ``planned/postponed/at_risk`` zählt als offen."""
    assert "achieved" not in OPEN_MILESTONE_STATUSES
    assert "cancelled" not in OPEN_MILESTONE_STATUSES
    # MS3 → cancelled setzen
    ms3 = MilestoneService(seeded_session).get_by_code("MS3")
    assert ms3 is not None
    ms3.status = "cancelled"
    seeded_session.flush()
    svc = ProjectDashboardService(seeded_session, today=TODAY_BEFORE_PROJECT)
    codes = [ms.code for ms in svc.upcoming_milestones()]
    assert "MS3" not in codes


# ---- overdue_milestones ------------------------------------------------


def test_overdue_returns_open_milestones_in_past(seeded_session: Session) -> None:
    """Wir verschieben ‚heute' nach MS2 → MS2 wird überfällig."""
    svc = ProjectDashboardService(seeded_session, today=date(2027, 6, 1))
    overdue = svc.overdue_milestones()
    codes = [ms.code for ms in overdue]
    assert codes == ["MS2"]  # Sortierung aufsteigend nach Plandatum
    assert overdue[0].days_to_planned < 0


def test_overdue_excludes_achieved(seeded_session: Session) -> None:
    """Auch wenn das Plandatum in der Vergangenheit liegt: achieved zählt nicht."""
    svc = ProjectDashboardService(seeded_session, today=date(2027, 6, 1))
    overdue_codes = [ms.code for ms in svc.overdue_milestones()]
    # MS1 (2026-03-02, achieved) ist nicht überfällig.
    assert "MS1" not in overdue_codes


def test_overdue_empty_before_project_start(seeded_session: Session) -> None:
    svc = ProjectDashboardService(seeded_session, today=TODAY_BEFORE_PROJECT)
    assert svc.overdue_milestones() == []


# ---- workpackages_with_open_issues -------------------------------------


def test_open_issues_lists_only_filled_workpackages(seeded_session: Session) -> None:
    wp_service = WorkpackageService(seeded_session, role="admin", person_id="admin-id")
    target = wp_service.get_by_code("WP3.1")
    other = wp_service.get_by_code("WP4.1")
    assert target is not None and other is not None
    wp_service.update_status(target.id, status="critical", open_issues="Lieferzeit Spulen")
    wp_service.update_status(
        other.id,
        status="waiting_for_input",
        open_issues="Spec-Freigabe steht aus",
    )
    seeded_session.commit()
    svc = ProjectDashboardService(seeded_session, today=TODAY_BEFORE_PROJECT)
    issues = svc.workpackages_with_open_issues()
    codes = [i.code for i in issues]
    # Nur die beiden mit open_issues; nicht alle WPs.
    assert codes == ["WP3.1", "WP4.1"]
    # Sortierung: kritisch zuerst (WP3.1), dann waiting_for_input (WP4.1).
    assert codes[0] == "WP3.1"


def test_open_issues_blank_string_is_ignored(seeded_session: Session) -> None:
    """Leerstring darf nicht als ‚offener Punkt' gelten."""
    wp_service = WorkpackageService(seeded_session, role="admin", person_id="admin-id")
    wp = wp_service.get_by_code("WP3.1")
    assert wp is not None
    # _normalise im Service wandelt "" → None — also expliziter Roh-Setter:
    wp.open_issues = ""
    seeded_session.flush()
    svc = ProjectDashboardService(seeded_session, today=TODAY_BEFORE_PROJECT)
    assert svc.workpackages_with_open_issues() == []


# ---- status_counts + overview ------------------------------------------


def test_status_counts_includes_all_status_keys(seeded_session: Session) -> None:
    svc = ProjectDashboardService(seeded_session, today=TODAY_BEFORE_PROJECT)
    counts = svc.status_counts()
    assert set(counts.keys()) == {
        "planned",
        "in_progress",
        "waiting_for_input",
        "critical",
        "completed",
    }
    # Frischer Seed → alle WPs default ‚planned'.
    total = sum(counts.values())
    assert total == 35
    assert counts["planned"] == 35
    for other in ("in_progress", "waiting_for_input", "critical", "completed"):
        assert counts[other] == 0


def test_status_counts_reacts_to_status_changes(seeded_session: Session) -> None:
    wp_service = WorkpackageService(seeded_session, role="admin", person_id="admin-id")
    wp = wp_service.get_by_code("WP3.1")
    assert wp is not None
    wp_service.update_status(wp.id, status="critical")
    seeded_session.commit()
    svc = ProjectDashboardService(seeded_session, today=TODAY_BEFORE_PROJECT)
    counts = svc.status_counts()
    assert counts["critical"] == 1
    assert counts["planned"] == 34


def test_status_overview_lists_all_active_workpackages(seeded_session: Session) -> None:
    svc = ProjectDashboardService(seeded_session, today=TODAY_BEFORE_PROJECT)
    overview = svc.workpackage_status_overview()
    codes = [e.code for e in overview]
    assert "WP1" in codes
    assert "WP3.1" in codes
    assert len(overview) == 35


# ---- build() ------------------------------------------------------------


def test_build_returns_complete_dashboard(seeded_session: Session) -> None:
    svc = ProjectDashboardService(seeded_session, today=TODAY_BEFORE_PROJECT)
    dashboard = svc.build()
    assert dashboard.today == TODAY_BEFORE_PROJECT
    assert len(dashboard.upcoming_milestones) == 3
    assert dashboard.overdue_milestones == []
    assert isinstance(dashboard.status_counts, dict)
    assert len(dashboard.workpackage_status_overview) == 35


def test_default_today_is_today(seeded_session: Session) -> None:
    """Ohne ``today``-Override wird ``date.today()`` genutzt."""
    svc = ProjectDashboardService(seeded_session)
    assert svc.today == date.today()
