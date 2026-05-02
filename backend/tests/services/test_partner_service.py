"""PartnerService."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ref4ep.services.partner_service import PartnerService


def test_member_cannot_create_partner(session: Session) -> None:
    svc = PartnerService(session, role="member")
    with pytest.raises(PermissionError):
        svc.create(name="X", short_name="X", country="DE")


def test_admin_creates_and_lists_partner(session: Session) -> None:
    svc = PartnerService(session, role="admin")
    p = svc.create(name="Acme", short_name="ACM", country="DE", website="https://acme.example")
    listed = svc.list_partners()
    assert any(x.short_name == "ACM" for x in listed)
    assert p.website == "https://acme.example"


def test_short_name_unique(session: Session) -> None:
    svc = PartnerService(session, role="admin")
    svc.create(name="A", short_name="DUP", country="DE")
    with pytest.raises(IntegrityError):
        svc.create(name="B", short_name="DUP", country="DE")
        session.flush()


def test_soft_delete_hides_from_list(session: Session) -> None:
    svc = PartnerService(session, role="admin")
    p = svc.create(name="Doomed", short_name="DOOM", country="DE")
    svc.soft_delete(p.id)
    assert all(x.short_name != "DOOM" for x in svc.list_partners())
    assert any(x.short_name == "DOOM" for x in svc.list_partners(include_deleted=True))
