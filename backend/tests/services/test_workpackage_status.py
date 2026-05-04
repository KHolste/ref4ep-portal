"""WorkpackageService.update_status — Berechtigungen & Validierung (Block 0009)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from ref4ep.services.workpackage_service import WorkpackageService


def _make_lead(seeded_session: Session, wp_code: str = "WP3.1") -> tuple[str, str]:
    """Legt eine Person als wp_lead in ``wp_code`` an. Liefert (person_id, wp_id)."""
    from ref4ep.services.partner_service import PartnerService
    from ref4ep.services.person_service import PersonService

    jlu = PartnerService(seeded_session, role="admin").get_by_short_name("JLU")
    assert jlu is not None
    person = PersonService(seeded_session, role="admin", person_id="fixture").create(
        email="wplead@test.example",
        display_name="WP Lead",
        partner_id=jlu.id,
        password="LeadP4ssword!",
        platform_role="member",
    )
    wp_service = WorkpackageService(seeded_session, role="admin", person_id="fixture")
    wp = wp_service.get_by_code(wp_code)
    assert wp is not None
    wp_service.add_membership(person.id, wp.id, "wp_lead")
    seeded_session.commit()
    return person.id, wp.id


def test_admin_can_update_status_and_cockpit_fields(seeded_session: Session) -> None:
    wp_service = WorkpackageService(seeded_session, role="admin", person_id="admin-id")
    wp = wp_service.get_by_code("WP3.1")
    assert wp is not None
    updated = wp_service.update_status(
        wp.id,
        status="in_progress",
        summary="Konstruktion läuft.",
        next_steps="CAD-Review nächste Woche.",
        open_issues="Lieferzeit Spulenkern noch offen.",
    )
    assert updated.status == "in_progress"
    assert updated.summary == "Konstruktion läuft."
    assert updated.next_steps == "CAD-Review nächste Woche."
    assert updated.open_issues == "Lieferzeit Spulenkern noch offen."


def test_wp_lead_can_update_own_wp_status(seeded_session: Session) -> None:
    person_id, wp_id = _make_lead(seeded_session, "WP3.1")
    wp_service = WorkpackageService(seeded_session, role="member", person_id=person_id)
    updated = wp_service.update_status(wp_id, status="critical", summary="kritisch")
    assert updated.status == "critical"
    assert updated.summary == "kritisch"


def test_wp_lead_cannot_update_foreign_wp_status(seeded_session: Session) -> None:
    person_id, _ = _make_lead(seeded_session, "WP3.1")
    other = WorkpackageService(seeded_session).get_by_code("WP4.1")
    assert other is not None
    wp_service = WorkpackageService(seeded_session, role="member", person_id=person_id)
    with pytest.raises(PermissionError):
        wp_service.update_status(other.id, status="completed")


def test_member_without_lead_cannot_update_status(
    seeded_session: Session, member_in_wp3, member_person_id: str
) -> None:
    """``member_in_wp3`` macht ``member_person_id`` zum wp_member (nicht lead) in WP3."""
    wp_service = WorkpackageService(seeded_session, role="member", person_id=member_person_id)
    wp = wp_service.get_by_code("WP3")
    assert wp is not None
    with pytest.raises(PermissionError):
        wp_service.update_status(wp.id, status="completed")


def test_anonymous_cannot_update_status(seeded_session: Session) -> None:
    """Kein person_id, keine Rolle → PermissionError."""
    wp_service = WorkpackageService(seeded_session)
    wp = wp_service.get_by_code("WP3.1")
    assert wp is not None
    with pytest.raises(PermissionError):
        wp_service.update_status(wp.id, status="completed")


def test_invalid_status_raises(seeded_session: Session) -> None:
    wp_service = WorkpackageService(seeded_session, role="admin", person_id="admin-id")
    wp = wp_service.get_by_code("WP3.1")
    assert wp is not None
    with pytest.raises(ValueError):
        wp_service.update_status(wp.id, status="foo")


def test_unknown_field_silently_ignored(seeded_session: Session) -> None:
    wp_service = WorkpackageService(seeded_session, role="admin", person_id="admin-id")
    wp = wp_service.get_by_code("WP3.1")
    assert wp is not None
    # Z. B. ``code`` darf so nicht geändert werden — Service ignoriert es still.
    updated = wp_service.update_status(wp.id, code="HACK", summary="ok")
    assert updated.code != "HACK"
    assert updated.summary == "ok"
