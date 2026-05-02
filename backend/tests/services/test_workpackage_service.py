"""WorkpackageService und Memberships."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from ref4ep.services.workpackage_service import WorkpackageService, _sort_key_from_code


def test_sort_key_from_code() -> None:
    assert _sort_key_from_code("WP1") < _sort_key_from_code("WP1.1")
    assert _sort_key_from_code("WP1.1") < _sort_key_from_code("WP1.2")
    assert _sort_key_from_code("WP1.2") < _sort_key_from_code("WP2")
    assert _sort_key_from_code("WP9") < _sort_key_from_code("WP10")


def test_list_workpackages_sorted_by_code(seeded_session: Session) -> None:
    wps = WorkpackageService(seeded_session).list_workpackages()
    codes = [w.code for w in wps]
    # Reihenfolge: WP1, WP1.1, WP1.2, WP2, WP2.1, ...
    assert codes[0] == "WP1"
    assert codes[1] == "WP1.1"
    assert codes[2] == "WP1.2"
    assert codes[3] == "WP2"


def test_list_parents_only(seeded_session: Session) -> None:
    parents = WorkpackageService(seeded_session).list_workpackages(parents_only=True)
    assert [w.code for w in parents] == [
        "WP1",
        "WP2",
        "WP3",
        "WP4",
        "WP5",
        "WP6",
        "WP7",
        "WP8",
    ]


def test_get_children(seeded_session: Session) -> None:
    svc = WorkpackageService(seeded_session)
    wp4 = svc.get_by_code("WP4")
    assert wp4 is not None
    children = svc.get_children(wp4.id)
    assert [c.code for c in children] == [
        "WP4.1",
        "WP4.2",
        "WP4.3",
        "WP4.4",
        "WP4.5",
        "WP4.6",
    ]


def test_add_membership_unique(seeded_session: Session) -> None:
    from ref4ep.services.partner_service import PartnerService
    from ref4ep.services.person_service import PersonService

    partner = PartnerService(seeded_session).get_by_short_name("JLU")
    assert partner is not None
    person = PersonService(seeded_session, role="admin").create(
        email="m@e", display_name="M", partner_id=partner.id, password="StrongPw1!"
    )
    wp = WorkpackageService(seeded_session).get_by_code("WP1")
    assert wp is not None

    svc = WorkpackageService(seeded_session, role="admin")
    svc.add_membership(person.id, wp.id, "wp_member")
    with pytest.raises(ValueError):
        svc.add_membership(person.id, wp.id, "wp_member")  # Doppel-Mitgliedschaft


def test_add_membership_member_forbidden(seeded_session: Session) -> None:
    wp = WorkpackageService(seeded_session).get_by_code("WP1")
    assert wp is not None
    with pytest.raises(PermissionError):
        WorkpackageService(seeded_session, role="member").add_membership(
            "fake-person", wp.id, "wp_member"
        )
