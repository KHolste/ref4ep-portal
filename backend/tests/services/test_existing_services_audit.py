"""Audit-Hooks in Sprint-1-Stammdatenservices."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ref4ep.domain.models import AuditLog
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.person_service import PersonService
from ref4ep.services.workpackage_service import WorkpackageService


def test_partner_create_logs(session: Session) -> None:
    audit = AuditLogger(session, actor_label="cli-admin")
    PartnerService(session, role="admin", audit=audit).create(
        name="X-AG", short_name="XAG", country="DE"
    )
    session.commit()
    assert session.query(AuditLog).filter_by(action="partner.create").count() == 1


def test_person_create_set_role_logs(session: Session) -> None:
    audit = AuditLogger(session, actor_label="cli-admin")
    partners = PartnerService(session, role="admin", audit=audit)
    persons = PersonService(session, role="admin", audit=audit)
    p = partners.create(name="JLU", short_name="JLU", country="DE")
    person = persons.create(
        email="audit-target@test.example",
        display_name="Audit Target",
        partner_id=p.id,
        password="StrongPw1!",
    )
    persons.set_role(person.id, "admin")
    session.commit()
    actions = [e.action for e in session.query(AuditLog).order_by(AuditLog.created_at).all()]
    assert "person.create" in actions
    assert "person.set_role" in actions


def test_workpackage_membership_logs(seeded_session: Session) -> None:
    audit = AuditLogger(seeded_session, actor_label="cli-admin")
    partners = PartnerService(seeded_session, role="admin", audit=audit)
    persons = PersonService(seeded_session, role="admin", audit=audit)
    wps = WorkpackageService(seeded_session, role="admin", audit=audit)
    partner = partners.get_by_short_name("JLU")
    person = persons.create(
        email="m-audit@test.example",
        display_name="M Audit",
        partner_id=partner.id,
        password="StrongPw1!",
    )
    seeded_session.commit()
    wp = wps.get_by_code("WP1")
    wps.add_membership(person.id, wp.id, "wp_member")
    seeded_session.commit()
    wps.remove_membership(person.id, wp.id)
    seeded_session.commit()
    actions = [e.action for e in seeded_session.query(AuditLog).order_by(AuditLog.created_at).all()]
    assert "membership.add" in actions
    assert "membership.remove" in actions
