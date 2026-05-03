"""PartnerService — erweiterte Felder + WP-Lead-Edit (Migration 0006)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from ref4ep.services.partner_service import PartnerService
from ref4ep.services.workpackage_service import WorkpackageService


def _make_partner(session: Session, *, short_name: str = "ACM", **kwargs) -> str:
    svc = PartnerService(session, role="admin")
    p = svc.create(name="Acme", short_name=short_name, country="DE", **kwargs)
    return p.id


# ---- Admin-Update: erweiterte Felder werden übernommen ------------------


def test_admin_update_writes_all_extended_fields(session: Session) -> None:
    pid = _make_partner(session)
    svc = PartnerService(session, role="admin")
    p = svc.update(
        pid,
        general_email="info@acme.example",
        address_line="Main 1",
        postal_code="12345",
        city="Hauptstadt",
        address_country="DE",
        primary_contact_name="Carola Test",
        contact_email="c.test@acme.example",
        contact_phone="+49 30 1234",
        project_role_note="Diagnostik-Prototyp.",
        is_active=False,
        internal_note="Achtung: Verwaltung hängt nach.",
    )
    assert p.general_email == "info@acme.example"
    assert p.address_line == "Main 1"
    assert p.postal_code == "12345"
    assert p.city == "Hauptstadt"
    assert p.address_country == "DE"
    assert p.primary_contact_name == "Carola Test"
    assert p.contact_email == "c.test@acme.example"
    assert p.contact_phone == "+49 30 1234"
    assert p.project_role_note == "Diagnostik-Prototyp."
    assert p.is_active is False
    assert p.internal_note == "Achtung: Verwaltung hängt nach."


def test_admin_update_invalid_email_raises(session: Session) -> None:
    pid = _make_partner(session)
    svc = PartnerService(session, role="admin")
    with pytest.raises(ValueError):
        svc.update(pid, general_email="ohne_at_zeichen")


def test_admin_update_blank_email_clears_to_none(session: Session) -> None:
    pid = _make_partner(session, general_email="info@acme.example")
    svc = PartnerService(session, role="admin")
    p = svc.update(pid, general_email="")
    assert p.general_email is None


def test_admin_update_invalid_address_country_raises(session: Session) -> None:
    pid = _make_partner(session)
    svc = PartnerService(session, role="admin")
    with pytest.raises(ValueError):
        svc.update(pid, address_country="DEU")


# ---- WP-Lead-Update -----------------------------------------------------


def _setup_lead(seeded_session: Session) -> tuple[str, str, str]:
    """Legt Person + WP an und macht die Person zum WP-Lead.

    Liefert ``(person_id, partner_id, wp_id)``.
    """
    from ref4ep.services.person_service import PersonService

    partners = PartnerService(seeded_session, role="admin")
    jlu = partners.get_by_short_name("JLU")
    assert jlu is not None
    persons = PersonService(seeded_session, role="admin", person_id="fixture")
    person = persons.create(
        email="lead@test.example",
        display_name="Lead",
        partner_id=jlu.id,
        password="LeadP4ssword!",
        platform_role="member",
    )
    wp_service = WorkpackageService(seeded_session, role="admin", person_id="fixture")
    # Suche ein WP, das von JLU geführt wird.
    leading = next(
        (wp for wp in wp_service.list_workpackages() if wp.lead_partner_id == jlu.id),
        None,
    )
    assert leading is not None, "Test-Seed sollte ein JLU-geführtes WP enthalten"
    wp_service.add_membership(person.id, leading.id, "wp_lead")
    seeded_session.commit()
    return person.id, jlu.id, leading.id


def test_wp_lead_can_update_whitelisted_fields(seeded_session: Session) -> None:
    person_id, partner_id, _ = _setup_lead(seeded_session)
    svc = PartnerService(seeded_session, role="member", person_id=person_id)
    p = svc.update_by_wp_lead(
        partner_id,
        name="Acme — neu",
        general_email="info@neu.example",
        primary_contact_name="Doris Test",
    )
    assert p.name == "Acme — neu"
    assert p.general_email == "info@neu.example"
    assert p.primary_contact_name == "Doris Test"


def test_wp_lead_cannot_change_short_name_or_country(seeded_session: Session) -> None:
    person_id, partner_id, _ = _setup_lead(seeded_session)
    svc = PartnerService(seeded_session, role="member", person_id=person_id)
    p_before = svc.get_by_id(partner_id)
    assert p_before is not None
    short_before, country_before = p_before.short_name, p_before.country
    svc.update_by_wp_lead(
        partner_id,
        short_name="HACK",
        country="ZZ",
        name="Akzeptiert",
    )
    p_after = svc.get_by_id(partner_id)
    assert p_after is not None
    assert p_after.short_name == short_before
    assert p_after.country == country_before
    assert p_after.name == "Akzeptiert"


def test_wp_lead_cannot_change_is_active_or_internal_note(seeded_session: Session) -> None:
    person_id, partner_id, _ = _setup_lead(seeded_session)
    svc = PartnerService(seeded_session, role="member", person_id=person_id)
    p_before = svc.get_by_id(partner_id)
    assert p_before is not None and p_before.is_active is True
    svc.update_by_wp_lead(
        partner_id,
        is_active=False,
        internal_note="injiziert",
    )
    p_after = svc.get_by_id(partner_id)
    assert p_after is not None
    assert p_after.is_active is True
    assert p_after.internal_note is None


def test_wp_lead_of_other_partner_is_rejected(seeded_session: Session) -> None:
    person_id, jlu_id, _ = _setup_lead(seeded_session)
    svc = PartnerService(seeded_session, role="member", person_id=person_id)
    # Ein anderer Partner aus dem Seed.
    other = next(p for p in svc.list_partners() if p.id != jlu_id)
    with pytest.raises(PermissionError):
        svc.update_by_wp_lead(other.id, name="Übergriff")


def test_wp_member_without_lead_cannot_edit(seeded_session: Session) -> None:
    from ref4ep.services.person_service import PersonService

    partners = PartnerService(seeded_session, role="admin")
    jlu = partners.get_by_short_name("JLU")
    assert jlu is not None
    persons = PersonService(seeded_session, role="admin", person_id="fixture")
    person = persons.create(
        email="member-only@test.example",
        display_name="Member only",
        partner_id=jlu.id,
        password="M3mberP4ssword!",
        platform_role="member",
    )
    wp_service = WorkpackageService(seeded_session, role="admin", person_id="fixture")
    leading = next(wp for wp in wp_service.list_workpackages() if wp.lead_partner_id == jlu.id)
    wp_service.add_membership(person.id, leading.id, "wp_member")
    seeded_session.commit()
    svc = PartnerService(seeded_session, role="member", person_id=person.id)
    with pytest.raises(PermissionError):
        svc.update_by_wp_lead(jlu.id, name="hack")


def test_wp_lead_email_validation(seeded_session: Session) -> None:
    person_id, partner_id, _ = _setup_lead(seeded_session)
    svc = PartnerService(seeded_session, role="member", person_id=person_id)
    with pytest.raises(ValueError):
        svc.update_by_wp_lead(partner_id, contact_email="kein_at")


def test_wp_lead_cannot_edit_soft_deleted_partner(seeded_session: Session) -> None:
    person_id, partner_id, _ = _setup_lead(seeded_session)
    PartnerService(seeded_session, role="admin").soft_delete(partner_id)
    seeded_session.commit()
    svc = PartnerService(seeded_session, role="member", person_id=person_id)
    with pytest.raises(LookupError):
        svc.update_by_wp_lead(partner_id, name="X")


# ---- Whitelist-Garantie auf Konstantenebene -----------------------------


def test_wp_lead_whitelist_excludes_admin_only_fields() -> None:
    from ref4ep.services.partner_service import WP_LEAD_FIELDS

    forbidden = {"short_name", "country", "is_active", "internal_note", "is_deleted"}
    assert forbidden.isdisjoint(set(WP_LEAD_FIELDS))
