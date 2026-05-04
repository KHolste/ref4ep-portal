"""MilestoneService — CRUD, Berechtigungen, Achievement-Regel (Block 0009)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from ref4ep.services.milestone_service import MilestoneService
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.workpackage_service import WorkpackageService


def _make_lead(seeded_session: Session, wp_code: str) -> str:
    from ref4ep.services.person_service import PersonService

    jlu = PartnerService(seeded_session, role="admin").get_by_short_name("JLU")
    assert jlu is not None
    person = PersonService(seeded_session, role="admin", person_id="fixture").create(
        email=f"lead-{wp_code}@test.example",
        display_name=f"Lead {wp_code}",
        partner_id=jlu.id,
        password="LeadP4ssword!",
        platform_role="member",
    )
    wp_service = WorkpackageService(seeded_session, role="admin", person_id="fixture")
    wp = wp_service.get_by_code(wp_code)
    assert wp is not None
    wp_service.add_membership(person.id, wp.id, "wp_lead")
    seeded_session.commit()
    return person.id


def test_seed_milestones_are_listed(seeded_session: Session) -> None:
    svc = MilestoneService(seeded_session, role="admin", person_id="admin-id")
    items = svc.list_all()
    codes = [ms.code for ms in items]
    assert codes == ["MS1", "MS2", "MS3", "MS4"]


def test_admin_can_edit_any_milestone(seeded_session: Session) -> None:
    svc = MilestoneService(seeded_session, role="admin", person_id="admin-id")
    ms4 = svc.get_by_code("MS4")
    assert ms4 is not None
    updated = svc.update(ms4.id, note="Admin-Notiz")
    assert updated.note == "Admin-Notiz"


def test_wp_lead_can_edit_own_wp_milestone(seeded_session: Session) -> None:
    person_id = _make_lead(seeded_session, "WP3.1")
    svc = MilestoneService(seeded_session, role="member", person_id=person_id)
    ms3 = svc.get_by_code("MS3")
    assert ms3 is not None
    updated = svc.update(ms3.id, status="at_risk")
    assert updated.status == "at_risk"


def test_wp_lead_cannot_edit_foreign_milestone(seeded_session: Session) -> None:
    person_id = _make_lead(seeded_session, "WP3.1")
    svc = MilestoneService(seeded_session, role="member", person_id=person_id)
    ms2 = svc.get_by_code("MS2")  # WP4.1
    assert ms2 is not None
    with pytest.raises(PermissionError):
        svc.update(ms2.id, status="at_risk")


def test_wp_lead_cannot_edit_overall_project_milestone(seeded_session: Session) -> None:
    """MS4 (Gesamtprojekt, kein workpackage_id) ist Admin-only."""
    person_id = _make_lead(seeded_session, "WP3.1")
    svc = MilestoneService(seeded_session, role="member", person_id=person_id)
    ms4 = svc.get_by_code("MS4")
    assert ms4 is not None
    assert ms4.workpackage_id is None
    with pytest.raises(PermissionError):
        svc.update(ms4.id, status="postponed")


def test_member_cannot_edit_any_milestone(seeded_session: Session, member_person_id: str) -> None:
    svc = MilestoneService(seeded_session, role="member", person_id=member_person_id)
    ms = svc.get_by_code("MS1")
    assert ms is not None
    with pytest.raises(PermissionError):
        svc.update(ms.id, note="hack")


def test_invalid_status_raises(seeded_session: Session) -> None:
    svc = MilestoneService(seeded_session, role="admin", person_id="admin-id")
    ms = svc.get_by_code("MS2")
    assert ms is not None
    with pytest.raises(ValueError):
        svc.update(ms.id, status="erledigt")


def test_achieved_without_actual_date_sets_today(seeded_session: Session) -> None:
    """Service entscheidet sich für Auto-Heute statt 422 — siehe Bericht."""
    svc = MilestoneService(seeded_session, role="admin", person_id="admin-id")
    ms = svc.get_by_code("MS2")
    assert ms is not None
    assert ms.actual_date is None
    updated = svc.update(ms.id, status="achieved")
    assert updated.status == "achieved"
    assert updated.actual_date == date.today()


def test_achieved_with_explicit_actual_date_keeps_it(seeded_session: Session) -> None:
    svc = MilestoneService(seeded_session, role="admin", person_id="admin-id")
    ms = svc.get_by_code("MS2")
    assert ms is not None
    explicit = date(2027, 2, 20)
    updated = svc.update(ms.id, status="achieved", actual_date=explicit)
    assert updated.status == "achieved"
    assert updated.actual_date == explicit


def test_create_overall_project_milestone(seeded_session: Session) -> None:
    """Service.create akzeptiert ``workpackage_id=None`` für Gesamtprojekt-MS."""
    svc = MilestoneService(seeded_session, role="admin", person_id="admin-id")
    ms = svc.create(
        code="MS-X",
        title="Test-Gesamt",
        planned_date=date(2030, 1, 1),
    )
    assert ms.workpackage_id is None


def test_create_unknown_workpackage_raises(seeded_session: Session) -> None:
    svc = MilestoneService(seeded_session, role="admin", person_id="admin-id")
    with pytest.raises(LookupError):
        svc.create(
            code="MS-Y",
            title="Test",
            planned_date=date(2030, 1, 1),
            workpackage_id="00000000-0000-0000-0000-000000000000",
        )
