"""PersonService inkl. Authentifizierung."""

from __future__ import annotations

import json

import pytest
from sqlalchemy.orm import Session

from ref4ep.domain.models import AuditLog
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.person_service import EmailAlreadyExists, PersonService


def _make_partner(session: Session) -> str:
    p = PartnerService(session, role="admin").create(name="JLU", short_name="JLU", country="DE")
    return p.id


def test_member_cannot_create_person(session: Session) -> None:
    pid = _make_partner(session)
    svc = PersonService(session, role="member")
    with pytest.raises(PermissionError):
        svc.create(
            email="x@y",
            display_name="X",
            partner_id=pid,
            password="StrongPw1!",
            platform_role="member",
        )


def test_create_and_authenticate(session: Session) -> None:
    pid = _make_partner(session)
    PersonService(session, role="admin").create(
        email="alice@example.com",
        display_name="Alice",
        partner_id=pid,
        password="StrongPw1!",
    )
    auth = PersonService(session)
    assert auth.authenticate("alice@example.com", "StrongPw1!") is not None
    assert auth.authenticate("ALICE@EXAMPLE.COM", "StrongPw1!") is not None  # case-insens.
    assert auth.authenticate("alice@example.com", "wrong-password!!") is None


def test_disabled_person_cannot_authenticate(session: Session) -> None:
    pid = _make_partner(session)
    admin = PersonService(session, role="admin")
    person = admin.create(
        email="bob@example.com", display_name="Bob", partner_id=pid, password="StrongPw1!"
    )
    admin.disable(person.id)
    assert PersonService(session).authenticate("bob@example.com", "StrongPw1!") is None


def test_change_password_requires_old(session: Session) -> None:
    pid = _make_partner(session)
    person = PersonService(session, role="admin").create(
        email="c@e", display_name="C", partner_id=pid, password="OriginalPw1!"
    )
    svc = PersonService(session, role="member", person_id=person.id)
    with pytest.raises(PermissionError):
        svc.change_password(person.id, "wrong", "NewPassword2!")
    svc.change_password(person.id, "OriginalPw1!", "NewPassword2!")
    assert person.must_change_password is False


def test_change_password_min_length(session: Session) -> None:
    pid = _make_partner(session)
    person = PersonService(session, role="admin").create(
        email="d@e", display_name="D", partner_id=pid, password="OriginalPw1!"
    )
    with pytest.raises(ValueError):
        PersonService(session).change_password(person.id, "OriginalPw1!", "shortpw")


def test_update_changes_email(session: Session) -> None:
    pid = _make_partner(session)
    admin = PersonService(session, role="admin")
    person = admin.create(
        email="old@example.com",
        display_name="Old",
        partner_id=pid,
        password="StrongPw1!",
    )
    updated = admin.update(person.id, email="new@example.com")
    assert updated.email == "new@example.com"
    assert admin.get_by_email("old@example.com") is None
    assert admin.get_by_email("new@example.com") is not None


def test_update_normalizes_email(session: Session) -> None:
    pid = _make_partner(session)
    admin = PersonService(session, role="admin")
    person = admin.create(
        email="norm@example.com",
        display_name="Norm",
        partner_id=pid,
        password="StrongPw1!",
    )
    updated = admin.update(person.id, email="  Mixed@Example.DE  ")
    assert updated.email == "mixed@example.de"


def test_update_rejects_duplicate_email(session: Session) -> None:
    pid = _make_partner(session)
    admin = PersonService(session, role="admin")
    admin.create(
        email="taken@example.com",
        display_name="Taken",
        partner_id=pid,
        password="StrongPw1!",
    )
    other = admin.create(
        email="free@example.com",
        display_name="Free",
        partner_id=pid,
        password="StrongPw1!",
    )
    with pytest.raises(EmailAlreadyExists):
        admin.update(other.id, email="taken@example.com")
    # Case-Variante kollidiert ebenfalls.
    with pytest.raises(EmailAlreadyExists):
        admin.update(other.id, email="TAKEN@example.com")
    assert other.email == "free@example.com"


def test_update_rejects_invalid_email(session: Session) -> None:
    pid = _make_partner(session)
    admin = PersonService(session, role="admin")
    person = admin.create(
        email="valid@example.com",
        display_name="V",
        partner_id=pid,
        password="StrongPw1!",
    )
    with pytest.raises(ValueError):
        admin.update(person.id, email="not-an-email")
    with pytest.raises(ValueError):
        admin.update(person.id, email="   ")


def test_update_email_writes_audit_before_after(session: Session) -> None:
    pid = _make_partner(session)
    audit = AuditLogger(session, actor_person_id="actor-test")
    admin = PersonService(session, role="admin", audit=audit)
    person = admin.create(
        email="before@example.com",
        display_name="Before",
        partner_id=pid,
        password="StrongPw1!",
    )
    admin.update(person.id, email="After@Example.com")
    session.flush()

    entry = (
        session.query(AuditLog)
        .filter_by(action="person.update", entity_id=person.id)
        .one()
    )
    payload = json.loads(entry.details)
    assert payload["before"]["email"] == "before@example.com"
    assert payload["after"]["email"] == "after@example.com"
    # Passwortdaten dürfen nie ins Audit geraten.
    assert "password" not in payload["before"]
    assert "password_hash" not in payload["before"]
    assert "password" not in payload["after"]
    assert "password_hash" not in payload["after"]


def test_update_email_keeps_password_and_must_change_flag(session: Session) -> None:
    pid = _make_partner(session)
    admin = PersonService(session, role="admin")
    person = admin.create(
        email="stay@example.com",
        display_name="Stay",
        partner_id=pid,
        password="StrongPw1!",
    )
    person.must_change_password = False
    session.flush()
    pwhash_before = person.password_hash

    admin.update(person.id, email="moved@example.com")
    assert person.password_hash == pwhash_before
    assert person.must_change_password is False


def test_update_same_email_no_audit_entry(session: Session) -> None:
    pid = _make_partner(session)
    audit = AuditLogger(session, actor_person_id="actor-test")
    admin = PersonService(session, role="admin", audit=audit)
    person = admin.create(
        email="noop@example.com",
        display_name="NoOp",
        partner_id=pid,
        password="StrongPw1!",
    )
    admin.update(person.id, email="NoOp@example.com")  # nach Normalisierung gleich
    session.flush()
    count = (
        session.query(AuditLog)
        .filter_by(action="person.update", entity_id=person.id)
        .count()
    )
    assert count == 0


def test_set_role_admin_only(session: Session) -> None:
    pid = _make_partner(session)
    person = PersonService(session, role="admin").create(
        email="e@e", display_name="E", partner_id=pid, password="OriginalPw1!"
    )
    with pytest.raises(PermissionError):
        PersonService(session, role="member").set_role(person.id, "admin")
    PersonService(session, role="admin").set_role(person.id, "admin")
    assert person.platform_role == "admin"
