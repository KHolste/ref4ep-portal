"""PartnerService — Organisations- und Einheitsfelder + WP-Lead-Edit (Block 0008)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from ref4ep.services.partner_service import PartnerService
from ref4ep.services.workpackage_service import WorkpackageService


def _make_partner(session: Session, *, short_name: str = "ACM", **kwargs) -> str:
    svc = PartnerService(session, role="admin")
    p = svc.create(name="Acme", short_name=short_name, country="DE", **kwargs)
    return p.id


# ---- Admin-Update: Organisations- und Einheitsfelder --------------------


def test_admin_update_writes_all_extended_fields(session: Session) -> None:
    pid = _make_partner(session)
    svc = PartnerService(session, role="admin")
    p = svc.update(
        pid,
        unit_name="I. Physikalisches Institut",
        organization_address_line="Hauptstr. 1",
        organization_postal_code="35392",
        organization_city="Gießen",
        organization_country="DE",
        unit_address_same_as_organization=False,
        unit_address_line="Heinrich-Buff-Ring 16",
        unit_postal_code="35392",
        unit_city="Gießen",
        unit_country="DE",
        is_active=False,
        internal_note="Achtung: Verwaltung hängt nach.",
    )
    assert p.unit_name == "I. Physikalisches Institut"
    assert p.organization_address_line == "Hauptstr. 1"
    assert p.organization_postal_code == "35392"
    assert p.organization_city == "Gießen"
    assert p.organization_country == "DE"
    assert p.unit_address_same_as_organization is False
    assert p.unit_address_line == "Heinrich-Buff-Ring 16"
    assert p.unit_postal_code == "35392"
    assert p.unit_city == "Gießen"
    assert p.unit_country == "DE"
    assert p.is_active is False
    assert p.internal_note == "Achtung: Verwaltung hängt nach."


def test_admin_update_invalid_organization_country_raises(session: Session) -> None:
    pid = _make_partner(session)
    svc = PartnerService(session, role="admin")
    with pytest.raises(ValueError):
        svc.update(pid, organization_country="DEU")


def test_admin_update_invalid_unit_country_raises(session: Session) -> None:
    pid = _make_partner(session)
    svc = PartnerService(session, role="admin")
    with pytest.raises(ValueError):
        svc.update(pid, unit_address_same_as_organization=False, unit_country="123")


def test_admin_update_blank_text_clears_to_none(session: Session) -> None:
    pid = _make_partner(session, organization_address_line="Main 1")
    svc = PartnerService(session, role="admin")
    p = svc.update(pid, organization_address_line="   ")
    assert p.organization_address_line is None


def test_unit_address_same_as_org_clears_unit_fields(session: Session) -> None:
    """Wenn der Toggle gesetzt wird, fliegen Einheitsadressfelder auf NULL."""
    pid = _make_partner(
        session,
        unit_address_same_as_organization=False,
        unit_address_line="Alt 1",
        unit_postal_code="9999",
        unit_city="Altstadt",
        unit_country="DE",
    )
    svc = PartnerService(session, role="admin")
    p = svc.update(pid, unit_address_same_as_organization=True)
    assert p.unit_address_same_as_organization is True
    assert p.unit_address_line is None
    assert p.unit_postal_code is None
    assert p.unit_city is None
    assert p.unit_country is None


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
        name="JLU — neu",
        unit_name="II. Physikalisches Institut",
        organization_address_line="Heinrich-Buff-Ring 16",
        organization_postal_code="35392",
        organization_city="Gießen",
        organization_country="DE",
        unit_address_same_as_organization=False,
        unit_address_line="Leihgesterner Weg 217",
        unit_postal_code="35392",
        unit_city="Gießen",
        unit_country="DE",
    )
    assert p.name == "JLU — neu"
    assert p.unit_name == "II. Physikalisches Institut"
    assert p.organization_city == "Gießen"
    assert p.unit_address_same_as_organization is False
    assert p.unit_address_line == "Leihgesterner Weg 217"


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


def test_wp_lead_country_validation(seeded_session: Session) -> None:
    person_id, partner_id, _ = _setup_lead(seeded_session)
    svc = PartnerService(seeded_session, role="member", person_id=person_id)
    with pytest.raises(ValueError):
        svc.update_by_wp_lead(partner_id, organization_country="XYZ")


def test_wp_lead_cannot_edit_soft_deleted_partner(seeded_session: Session) -> None:
    person_id, partner_id, _ = _setup_lead(seeded_session)
    PartnerService(seeded_session, role="admin").soft_delete(partner_id)
    seeded_session.commit()
    svc = PartnerService(seeded_session, role="member", person_id=person_id)
    with pytest.raises(LookupError):
        svc.update_by_wp_lead(partner_id, name="X")


def test_wp_lead_can_toggle_unit_address_same_as_org(seeded_session: Session) -> None:
    person_id, partner_id, _ = _setup_lead(seeded_session)
    svc = PartnerService(seeded_session, role="member", person_id=person_id)
    # Erst eigene Einheitsadresse setzen.
    svc.update_by_wp_lead(
        partner_id,
        unit_address_same_as_organization=False,
        unit_address_line="Test 1",
    )
    # Dann zurück auf "identisch" toggeln — Einheitsadresse muss leer werden.
    p = svc.update_by_wp_lead(partner_id, unit_address_same_as_organization=True)
    assert p.unit_address_same_as_organization is True
    assert p.unit_address_line is None


# ---- Whitelist-Garantie auf Konstantenebene -----------------------------


def test_wp_lead_whitelist_excludes_admin_only_fields() -> None:
    from ref4ep.services.partner_service import WP_LEAD_FIELDS

    forbidden = {"short_name", "country", "is_active", "internal_note", "is_deleted"}
    assert forbidden.isdisjoint(set(WP_LEAD_FIELDS))


def test_wp_lead_whitelist_excludes_legacy_person_fields() -> None:
    """Block 0008: personenbezogene Felder dürfen nicht mehr in der Whitelist liegen."""
    from ref4ep.services.partner_service import ADMIN_FIELDS, WP_LEAD_FIELDS

    legacy = {"primary_contact_name", "contact_email", "contact_phone", "project_role_note"}
    assert legacy.isdisjoint(set(WP_LEAD_FIELDS))
    assert legacy.isdisjoint(set(ADMIN_FIELDS))
