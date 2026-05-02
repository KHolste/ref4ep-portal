"""PersonService inkl. Authentifizierung."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from ref4ep.services.partner_service import PartnerService
from ref4ep.services.person_service import PersonService


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


def test_set_role_admin_only(session: Session) -> None:
    pid = _make_partner(session)
    person = PersonService(session, role="admin").create(
        email="e@e", display_name="E", partner_id=pid, password="OriginalPw1!"
    )
    with pytest.raises(PermissionError):
        PersonService(session, role="member").set_role(person.id, "admin")
    PersonService(session, role="admin").set_role(person.id, "admin")
    assert person.platform_role == "admin"
