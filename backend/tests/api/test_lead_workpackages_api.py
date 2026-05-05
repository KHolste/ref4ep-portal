"""API: /api/lead/workpackages + /memberships (Block 0013)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.domain.models import Membership
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.person_service import PersonService
from ref4ep.services.workpackage_service import WorkpackageService


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


@pytest.fixture
def jlu_partner_id(seeded_session: Session) -> str:
    p = PartnerService(seeded_session, role="admin").get_by_short_name("JLU")
    assert p is not None
    return p.id


@pytest.fixture
def tud_partner_id(seeded_session: Session) -> str:
    p = PartnerService(seeded_session, role="admin").get_by_short_name("TUD")
    assert p is not None
    return p.id


@pytest.fixture
def jlu_extra_person_id(seeded_session: Session, jlu_partner_id: str) -> str:
    """Zweite JLU-Person als Anfügekandidat."""
    person = PersonService(seeded_session, role="admin", person_id="fixture").create(
        email="jlu-zwei@test.example",
        display_name="JLU Zwei",
        partner_id=jlu_partner_id,
        password="X" * 12,
    )
    seeded_session.commit()
    return person.id


@pytest.fixture
def tud_person_id(seeded_session: Session, tud_partner_id: str) -> str:
    person = PersonService(seeded_session, role="admin", person_id="fixture").create(
        email="tud-fremd@test.example",
        display_name="TUD Fremd",
        partner_id=tud_partner_id,
        password="X" * 12,
    )
    seeded_session.commit()
    return person.id


# ---- LIST -------------------------------------------------------------


def test_anonymous_cannot_list_lead_wps(client: TestClient, seeded_session: Session) -> None:
    client.cookies.clear()
    r = client.get("/api/lead/workpackages")
    assert r.status_code == 401


def test_member_without_lead_role_gets_403(
    member_client: TestClient, seeded_session: Session, member_in_wp3
) -> None:
    r = member_client.get("/api/lead/workpackages")
    assert r.status_code == 403


def test_wp_lead_lists_only_own_lead_wps(
    member_client: TestClient, seeded_session: Session, lead_in_wp3
) -> None:
    r = member_client.get("/api/lead/workpackages")
    assert r.status_code == 200
    body = r.json()
    codes = [w["code"] for w in body]
    assert codes == ["WP3"]
    # WP3 enthält den Lead selbst als Mitglied.
    assert body[0]["my_role"] == "wp_lead"
    member_emails = {m["email"] for m in body[0]["members"]}
    assert "member@test.example" in member_emails


def test_admin_without_lead_membership_sees_no_wps(
    admin_client: TestClient, seeded_session: Session
) -> None:
    """Admin ohne wp_lead-Mitgliedschaft sieht keine eigenen Lead-WPs.
    Begründung im Bericht: ``/api/lead/workpackages`` bedeutet
    ‚meine Lead-WPs', nicht ‚alle WPs'."""
    r = admin_client.get("/api/lead/workpackages")
    assert r.status_code == 200
    assert r.json() == []


# ---- ADD MEMBERSHIP ---------------------------------------------------


def test_anonymous_cannot_add_membership(
    client: TestClient, seeded_session: Session, jlu_extra_person_id: str
) -> None:
    client.cookies.clear()
    r = client.post(
        "/api/lead/workpackages/WP3/memberships",
        json={"person_id": jlu_extra_person_id},
    )
    assert r.status_code in (401, 403)


def test_lead_can_add_own_partner_person(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
    jlu_extra_person_id: str,
) -> None:
    r = member_client.post(
        "/api/lead/workpackages/WP3/memberships",
        json={"person_id": jlu_extra_person_id},
        headers=_csrf(member_client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    member_ids = {m["person_id"] for m in body["members"]}
    assert jlu_extra_person_id in member_ids


def test_lead_cannot_add_foreign_partner_person(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
    tud_person_id: str,
) -> None:
    r = member_client.post(
        "/api/lead/workpackages/WP3/memberships",
        json={"person_id": tud_person_id},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_lead_cannot_add_to_foreign_wp(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
    jlu_extra_person_id: str,
) -> None:
    """Lead von WP3 darf in WP4.1 (CAU-geleitet) nichts machen — 403."""
    r = member_client.post(
        "/api/lead/workpackages/WP4.1/memberships",
        json={"person_id": jlu_extra_person_id},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_lead_cannot_add_to_unknown_wp(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
    jlu_extra_person_id: str,
) -> None:
    """Existenz-Leakage: unbekannter WP-Code → 403, nicht 404."""
    r = member_client.post(
        "/api/lead/workpackages/WPXYZ/memberships",
        json={"person_id": jlu_extra_person_id},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_add_requires_csrf(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
    jlu_extra_person_id: str,
) -> None:
    r = member_client.post(
        "/api/lead/workpackages/WP3/memberships",
        json={"person_id": jlu_extra_person_id},
    )
    assert r.status_code == 403


def test_add_duplicate_membership_returns_422(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
    jlu_extra_person_id: str,
) -> None:
    member_client.post(
        "/api/lead/workpackages/WP3/memberships",
        json={"person_id": jlu_extra_person_id},
        headers=_csrf(member_client),
    )
    r = member_client.post(
        "/api/lead/workpackages/WP3/memberships",
        json={"person_id": jlu_extra_person_id},
        headers=_csrf(member_client),
    )
    assert r.status_code == 422


# ---- PATCH MEMBERSHIP ROLE --------------------------------------------


def test_lead_can_change_member_role_to_lead_and_back(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
    jlu_extra_person_id: str,
) -> None:
    member_client.post(
        "/api/lead/workpackages/WP3/memberships",
        json={"person_id": jlu_extra_person_id},
        headers=_csrf(member_client),
    )
    r = member_client.patch(
        f"/api/lead/workpackages/WP3/memberships/{jlu_extra_person_id}",
        json={"wp_role": "wp_lead"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    target = next(m for m in body["members"] if m["person_id"] == jlu_extra_person_id)
    assert target["wp_role"] == "wp_lead"
    # Zurück auf member geht auch (es gibt jetzt zwei Leads).
    r = member_client.patch(
        f"/api/lead/workpackages/WP3/memberships/{jlu_extra_person_id}",
        json={"wp_role": "wp_member"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 200


def test_last_lead_cannot_demote_self(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
    member_person_id: str,
) -> None:
    """Sicherheits-Constraint: ein WP muss mindestens einen wp_lead behalten."""
    r = member_client.patch(
        f"/api/lead/workpackages/WP3/memberships/{member_person_id}",
        json={"wp_role": "wp_member"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 422


def test_lead_cannot_change_role_in_foreign_wp(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
    tud_person_id: str,
) -> None:
    r = member_client.patch(
        f"/api/lead/workpackages/WP4.1/memberships/{tud_person_id}",
        json={"wp_role": "wp_lead"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_lead_cannot_set_invalid_role(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
    member_person_id: str,
) -> None:
    r = member_client.patch(
        f"/api/lead/workpackages/WP3/memberships/{member_person_id}",
        json={"wp_role": "admin"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 422


# ---- DELETE MEMBERSHIP ------------------------------------------------


def test_lead_can_remove_member(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
    jlu_extra_person_id: str,
) -> None:
    member_client.post(
        "/api/lead/workpackages/WP3/memberships",
        json={"person_id": jlu_extra_person_id},
        headers=_csrf(member_client),
    )
    r = member_client.delete(
        f"/api/lead/workpackages/WP3/memberships/{jlu_extra_person_id}",
        headers=_csrf(member_client),
    )
    assert r.status_code == 204
    # Mitgliedschaft weg.
    seeded_session.expire_all()
    remaining = seeded_session.query(Membership).filter_by(person_id=jlu_extra_person_id)
    assert remaining.count() == 0
    # Person bleibt erhalten.
    from ref4ep.domain.models import Person

    person = seeded_session.get(Person, jlu_extra_person_id)
    assert person is not None
    assert person.is_active is True
    assert person.is_deleted is False


def test_lead_cannot_remove_from_foreign_wp(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
    tud_person_id: str,
) -> None:
    # Wir setzen die TUD-Person als wp_member in WP4.1 (admin macht das).
    wp_service = WorkpackageService(seeded_session, role="admin", person_id="fixture")
    wp = wp_service.get_by_code("WP4.1")
    assert wp is not None
    wp_service.add_membership(tud_person_id, wp.id, "wp_member")
    seeded_session.commit()
    r = member_client.delete(
        f"/api/lead/workpackages/WP4.1/memberships/{tud_person_id}",
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_last_lead_cannot_remove_self(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
    member_person_id: str,
) -> None:
    r = member_client.delete(
        f"/api/lead/workpackages/WP3/memberships/{member_person_id}",
        headers=_csrf(member_client),
    )
    assert r.status_code == 422
