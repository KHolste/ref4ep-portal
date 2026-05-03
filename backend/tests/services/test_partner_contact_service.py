"""PartnerContactService — CRUD + Berechtigungsmatrix (Block 0007)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from ref4ep.services.partner_contact_service import PartnerContactService
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.workpackage_service import WorkpackageService


def _jlu(session: Session) -> str:
    p = PartnerService(session, role="admin").get_by_short_name("JLU")
    assert p is not None
    return p.id


def _other_partner(session: Session, jlu_id: str) -> str:
    other = next(p for p in PartnerService(session, role="admin").list_partners() if p.id != jlu_id)
    return other.id


def _make_lead(seeded_session: Session, partner_id: str) -> str:
    """Legt eine Person an und macht sie zum WP-Lead in einem WP, das ``partner_id`` führt."""
    from ref4ep.services.person_service import PersonService

    persons = PersonService(seeded_session, role="admin", person_id="fixture")
    person = persons.create(
        email=f"lead-{partner_id[:8]}@test.example",
        display_name="Lead",
        partner_id=partner_id,
        password="LeadP4ssword!",
        platform_role="member",
    )
    wps = WorkpackageService(seeded_session, role="admin", person_id="fixture")
    leading = next(wp for wp in wps.list_workpackages() if wp.lead_partner_id == partner_id)
    wps.add_membership(person.id, leading.id, "wp_lead")
    seeded_session.commit()
    return person.id


# ---- Admin -------------------------------------------------------------


def test_admin_can_create_and_list(seeded_session: Session) -> None:
    pid = _jlu(seeded_session)
    svc = PartnerContactService(seeded_session, role="admin", person_id="admin-id")
    c = svc.create(
        partner_id=pid,
        name="Dr. Carola Test",
        title_or_degree="Dr.",
        email="c.test@jlu.example",
        function="Postdoc",
    )
    assert c.id
    assert c.is_active is True
    assert c.visibility == "internal"
    contacts = svc.list_for_partner(pid)
    assert any(x.name == "Dr. Carola Test" for x in contacts)


def test_admin_can_update_and_deactivate(seeded_session: Session) -> None:
    pid = _jlu(seeded_session)
    svc = PartnerContactService(seeded_session, role="admin", person_id="admin-id")
    c = svc.create(partner_id=pid, name="Doris Test")
    svc.update(c.id, function="Projektleitung", phone="+49 30 1")
    seeded_session.refresh(c)
    assert c.function == "Projektleitung"
    assert c.phone == "+49 30 1"
    svc.deactivate(c.id)
    seeded_session.refresh(c)
    assert c.is_active is False


def test_admin_can_set_internal_note(seeded_session: Session) -> None:
    pid = _jlu(seeded_session)
    svc = PartnerContactService(seeded_session, role="admin", person_id="admin-id")
    c = svc.create(partner_id=pid, name="X", internal_note="nur Admin")
    assert c.internal_note == "nur Admin"


# ---- WP-Lead -----------------------------------------------------------


def test_wp_lead_can_manage_own_partner(seeded_session: Session) -> None:
    pid = _jlu(seeded_session)
    lead_id = _make_lead(seeded_session, pid)
    svc = PartnerContactService(seeded_session, role="member", person_id=lead_id)
    c = svc.create(partner_id=pid, name="Lead-erstellt")
    assert c.id
    svc.update(c.id, phone="123")
    svc.deactivate(c.id)
    seeded_session.refresh(c)
    assert c.is_active is False


def test_wp_lead_cannot_manage_foreign_partner(seeded_session: Session) -> None:
    pid = _jlu(seeded_session)
    lead_id = _make_lead(seeded_session, pid)
    other_id = _other_partner(seeded_session, pid)
    svc = PartnerContactService(seeded_session, role="member", person_id=lead_id)
    with pytest.raises(PermissionError):
        svc.create(partner_id=other_id, name="hack")


def test_wp_lead_internal_note_silently_ignored(seeded_session: Session) -> None:
    pid = _jlu(seeded_session)
    lead_id = _make_lead(seeded_session, pid)
    svc = PartnerContactService(seeded_session, role="member", person_id=lead_id)
    c = svc.create(partner_id=pid, name="Y", internal_note="versucht")
    # Lead darf keine internen Notizen schreiben → Service ignoriert das Feld.
    assert c.internal_note is None


# ---- Member ohne Lead --------------------------------------------------


def test_member_cannot_manage(seeded_session: Session) -> None:
    pid = _jlu(seeded_session)
    from ref4ep.services.person_service import PersonService

    person = PersonService(seeded_session, role="admin", person_id="fixture").create(
        email="member-only@test.example",
        display_name="M",
        partner_id=pid,
        password="M3mberP4ssword!",
        platform_role="member",
    )
    seeded_session.commit()
    svc = PartnerContactService(seeded_session, role="member", person_id=person.id)
    with pytest.raises(PermissionError):
        svc.create(partner_id=pid, name="hack")


def test_member_sees_only_active_visible(seeded_session: Session) -> None:
    pid = _jlu(seeded_session)
    admin_svc = PartnerContactService(seeded_session, role="admin", person_id="admin-id")
    admin_svc.create(partner_id=pid, name="sichtbar", visibility="internal")
    admin_svc.create(partner_id=pid, name="öffentlich", visibility="public")
    deact = admin_svc.create(partner_id=pid, name="deaktiviert")
    admin_svc.deactivate(deact.id)
    seeded_session.commit()

    from ref4ep.services.person_service import PersonService

    person = PersonService(seeded_session, role="admin", person_id="fixture").create(
        email="member-readonly@test.example",
        display_name="R",
        partner_id=pid,
        password="ReadP4ssword!",
        platform_role="member",
    )
    seeded_session.commit()

    member_svc = PartnerContactService(seeded_session, role="member", person_id=person.id)
    seen = {c.name for c in member_svc.list_for_partner(pid)}
    # Nur intern und öffentlich, nur aktiv.
    assert "sichtbar" in seen
    assert "öffentlich" in seen
    assert "deaktiviert" not in seen


def test_admin_sees_inactive_when_requested(seeded_session: Session) -> None:
    pid = _jlu(seeded_session)
    admin_svc = PartnerContactService(seeded_session, role="admin", person_id="admin-id")
    c = admin_svc.create(partner_id=pid, name="zur-deaktivierung")
    admin_svc.deactivate(c.id)
    seeded_session.commit()
    seen_active = {c.name for c in admin_svc.list_for_partner(pid)}
    assert "zur-deaktivierung" not in seen_active
    seen_all = {c.name for c in admin_svc.list_for_partner(pid, include_inactive=True)}
    assert "zur-deaktivierung" in seen_all


# ---- Validierung -------------------------------------------------------


def test_invalid_email_raises(seeded_session: Session) -> None:
    pid = _jlu(seeded_session)
    svc = PartnerContactService(seeded_session, role="admin", person_id="admin-id")
    with pytest.raises(ValueError):
        svc.create(partner_id=pid, name="Z", email="ohne_at")


def test_invalid_function_raises(seeded_session: Session) -> None:
    pid = _jlu(seeded_session)
    svc = PartnerContactService(seeded_session, role="admin", person_id="admin-id")
    with pytest.raises(ValueError):
        svc.create(partner_id=pid, name="Z", function="freie_eingabe")


def test_invalid_visibility_raises(seeded_session: Session) -> None:
    pid = _jlu(seeded_session)
    svc = PartnerContactService(seeded_session, role="admin", person_id="admin-id")
    with pytest.raises(ValueError):
        svc.create(partner_id=pid, name="Z", visibility="halböffentlich")


def test_create_requires_name(seeded_session: Session) -> None:
    pid = _jlu(seeded_session)
    svc = PartnerContactService(seeded_session, role="admin", person_id="admin-id")
    with pytest.raises(ValueError):
        svc.create(partner_id=pid, name="   ")


def test_create_unknown_partner_raises(seeded_session: Session) -> None:
    svc = PartnerContactService(seeded_session, role="admin", person_id="admin-id")
    with pytest.raises(LookupError):
        svc.create(partner_id="00000000-0000-0000-0000-000000000000", name="Z")


def test_function_whitelist_is_gender_inclusive() -> None:
    from ref4ep.domain.models import PARTNER_CONTACT_FUNCTIONS

    # Stichproben — keine generischen Maskulinformen ohne Doppelung.
    paired = {
        "Professorin/Professor",
        "Doktorandin/Doktorand",
        "Masterstudentin/Masterstudent",
        "Bachelorstudentin/Bachelorstudent",
        "Technikerin/Techniker",
    }
    for entry in paired:
        assert entry in PARTNER_CONTACT_FUNCTIONS
