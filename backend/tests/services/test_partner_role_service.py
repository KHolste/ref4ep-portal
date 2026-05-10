"""PartnerRoleService — Verwaltung der Projektleitungs-Rolle pro
Partner (Block 0043)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from ref4ep.domain.models import AuditLog, PartnerRole, Person
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.partner_role_service import (
    PartnerRoleNotFoundError,
    PartnerRoleService,
)
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.person_service import PersonService


def _admin(session: Session) -> Person:
    admin = session.query(Person).filter_by(email="admin@test.example").first()
    if admin is None:
        partner = PartnerService(session).get_by_short_name("JLU")
        if partner is None:
            partner = PartnerService(session).create(
                name="Test-JLU", short_name="JLU", country="DE"
            )
        admin = PersonService(session, role="admin").create(
            email="admin@test.example",
            display_name="Admin",
            partner_id=partner.id,
            password="StrongPw1!",
            platform_role="admin",
        )
        session.commit()
    return admin


def _service_for(
    actor: Person, session: Session, *, audit: AuditLogger | None = None
) -> PartnerRoleService:
    return PartnerRoleService(session, role=actor.platform_role, person_id=actor.id, audit=audit)


def _other_person(session: Session, *, partner_short: str = "JLU") -> Person:
    partner = PartnerService(session).get_by_short_name(partner_short)
    assert partner is not None
    person = PersonService(session, role="admin").create(
        email=f"member-{partner_short.lower()}@test.example",
        display_name=f"Member {partner_short}",
        partner_id=partner.id,
        password="StrongPw1!",
        platform_role="member",
    )
    session.commit()
    return person


# ---- add ------------------------------------------------------------------


def test_admin_can_add_partner_lead(seeded_session: Session) -> None:
    admin = _admin(seeded_session)
    target = _other_person(seeded_session)
    partner = PartnerService(seeded_session).get_by_short_name("JLU")
    link = _service_for(admin, seeded_session).add_partner_role(
        person_id=target.id, partner_id=partner.id, actor_person_id=admin.id
    )
    assert link.role == "partner_lead"
    assert link.person_id == target.id
    assert link.partner_id == partner.id


def test_add_is_idempotent(seeded_session: Session) -> None:
    """Doppelte Vergabe liefert den bestehenden Eintrag zurück, ohne
    Fehler und ohne zweiten Audit-Eintrag."""
    admin = _admin(seeded_session)
    target = _other_person(seeded_session)
    partner = PartnerService(seeded_session).get_by_short_name("JLU")
    audit = AuditLogger(seeded_session, actor_person_id=admin.id, actor_label=admin.email)
    svc = _service_for(admin, seeded_session, audit=audit)

    first = svc.add_partner_role(
        person_id=target.id, partner_id=partner.id, actor_person_id=admin.id
    )
    seeded_session.commit()
    second = svc.add_partner_role(
        person_id=target.id, partner_id=partner.id, actor_person_id=admin.id
    )
    assert first.id == second.id

    add_events = seeded_session.query(AuditLog).filter(AuditLog.action == "partner.role.add").all()
    assert len(add_events) == 1, "Idempotenter Aufruf soll keinen zweiten Audit erzeugen."


def test_add_rejects_unknown_role(seeded_session: Session) -> None:
    admin = _admin(seeded_session)
    target = _other_person(seeded_session)
    partner = PartnerService(seeded_session).get_by_short_name("JLU")
    with pytest.raises(ValueError):
        _service_for(admin, seeded_session).add_partner_role(
            person_id=target.id,
            partner_id=partner.id,
            role="something_else",
            actor_person_id=admin.id,
        )


def test_add_unknown_person_raises(seeded_session: Session) -> None:
    admin = _admin(seeded_session)
    partner = PartnerService(seeded_session).get_by_short_name("JLU")
    with pytest.raises(LookupError):
        _service_for(admin, seeded_session).add_partner_role(
            person_id="00000000-0000-0000-0000-000000000000",
            partner_id=partner.id,
            actor_person_id=admin.id,
        )


def test_add_unknown_partner_raises(seeded_session: Session) -> None:
    admin = _admin(seeded_session)
    target = _other_person(seeded_session)
    with pytest.raises(LookupError):
        _service_for(admin, seeded_session).add_partner_role(
            person_id=target.id,
            partner_id="00000000-0000-0000-0000-000000000000",
            actor_person_id=admin.id,
        )


def test_member_cannot_add(seeded_session: Session) -> None:
    member = _other_person(seeded_session)
    partner = PartnerService(seeded_session).get_by_short_name("JLU")
    with pytest.raises(PermissionError):
        PartnerRoleService(seeded_session, role="member", person_id=member.id).add_partner_role(
            person_id=member.id, partner_id=partner.id, actor_person_id=member.id
        )


# ---- remove ----------------------------------------------------------------


def test_admin_can_remove_partner_lead(seeded_session: Session) -> None:
    admin = _admin(seeded_session)
    target = _other_person(seeded_session)
    partner = PartnerService(seeded_session).get_by_short_name("JLU")
    svc = _service_for(admin, seeded_session)
    svc.add_partner_role(person_id=target.id, partner_id=partner.id, actor_person_id=admin.id)
    seeded_session.commit()
    svc.remove_partner_role(person_id=target.id, partner_id=partner.id)
    seeded_session.commit()
    remaining = (
        seeded_session.query(PartnerRole)
        .filter_by(person_id=target.id, partner_id=partner.id)
        .all()
    )
    assert remaining == []


def test_remove_missing_role_raises_not_found(seeded_session: Session) -> None:
    admin = _admin(seeded_session)
    target = _other_person(seeded_session)
    partner = PartnerService(seeded_session).get_by_short_name("JLU")
    with pytest.raises(PartnerRoleNotFoundError):
        _service_for(admin, seeded_session).remove_partner_role(
            person_id=target.id, partner_id=partner.id
        )


def test_member_cannot_remove(seeded_session: Session) -> None:
    admin = _admin(seeded_session)
    target = _other_person(seeded_session)
    partner = PartnerService(seeded_session).get_by_short_name("JLU")
    _service_for(admin, seeded_session).add_partner_role(
        person_id=target.id, partner_id=partner.id, actor_person_id=admin.id
    )
    seeded_session.commit()
    with pytest.raises(PermissionError):
        PartnerRoleService(seeded_session, role="member", person_id=target.id).remove_partner_role(
            person_id=target.id, partner_id=partner.id
        )


# ---- read ------------------------------------------------------------------


def test_list_for_partner_and_person(seeded_session: Session) -> None:
    admin = _admin(seeded_session)
    target = _other_person(seeded_session)
    partner = PartnerService(seeded_session).get_by_short_name("JLU")
    svc = _service_for(admin, seeded_session)
    svc.add_partner_role(person_id=target.id, partner_id=partner.id, actor_person_id=admin.id)
    seeded_session.commit()
    by_partner = svc.list_for_partner(partner.id)
    by_person = svc.list_for_person(target.id)
    assert len(by_partner) == 1
    assert len(by_person) == 1
    assert by_partner[0].id == by_person[0].id


def test_is_partner_lead_for(seeded_session: Session) -> None:
    admin = _admin(seeded_session)
    target = _other_person(seeded_session)
    partner = PartnerService(seeded_session).get_by_short_name("JLU")
    svc = _service_for(admin, seeded_session)
    assert svc.is_partner_lead_for(target.id, partner.id) is False
    svc.add_partner_role(person_id=target.id, partner_id=partner.id, actor_person_id=admin.id)
    seeded_session.commit()
    assert svc.is_partner_lead_for(target.id, partner.id) is True


# ---- audit -----------------------------------------------------------------


def test_audit_writes_add_and_remove(seeded_session: Session) -> None:
    admin = _admin(seeded_session)
    target = _other_person(seeded_session)
    partner = PartnerService(seeded_session).get_by_short_name("JLU")
    audit = AuditLogger(seeded_session, actor_person_id=admin.id, actor_label=admin.email)
    svc = _service_for(admin, seeded_session, audit=audit)
    svc.add_partner_role(person_id=target.id, partner_id=partner.id, actor_person_id=admin.id)
    seeded_session.commit()
    svc.remove_partner_role(person_id=target.id, partner_id=partner.id)
    seeded_session.commit()
    actions = [
        a.action
        for a in seeded_session.query(AuditLog).filter(AuditLog.entity_type == "partner_role").all()
    ]
    assert "partner.role.add" in actions
    assert "partner.role.remove" in actions
