"""API: /api/admin/partners/{id}/roles (Block 0043)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.domain.models import Person
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.person_service import PersonService


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def _make_target_person(seeded_session: Session, suffix: str = "lead") -> Person:
    partner = PartnerService(seeded_session).get_by_short_name("JLU")
    assert partner is not None
    person = PersonService(seeded_session, role="admin").create(
        email=f"target-{suffix}@test.example",
        display_name=f"Target {suffix}",
        partner_id=partner.id,
        password="StrongPw1!",
        platform_role="member",
    )
    seeded_session.commit()
    return person


def _partner_id(seeded_session: Session, short: str = "JLU") -> str:
    p = PartnerService(seeded_session).get_by_short_name(short)
    assert p is not None
    return p.id


# ---- GET --------------------------------------------------------------------


def test_anonymous_cannot_list(client: TestClient, seeded_session: Session) -> None:
    client.cookies.clear()
    partner_id = _partner_id(seeded_session)
    r = client.get(f"/api/admin/partners/{partner_id}/roles")
    assert r.status_code == 401


def test_member_cannot_list(member_client: TestClient, seeded_session: Session) -> None:
    partner_id = _partner_id(seeded_session)
    r = member_client.get(f"/api/admin/partners/{partner_id}/roles")
    assert r.status_code == 403


def test_admin_can_list_empty(admin_client: TestClient, seeded_session: Session) -> None:
    partner_id = _partner_id(seeded_session)
    r = admin_client.get(f"/api/admin/partners/{partner_id}/roles")
    assert r.status_code == 200
    assert r.json() == []


def test_list_unknown_partner_returns_404(admin_client: TestClient) -> None:
    r = admin_client.get("/api/admin/partners/00000000-0000-0000-0000-000000000000/roles")
    assert r.status_code == 404


# ---- POST -------------------------------------------------------------------


def test_admin_can_add_partner_lead(admin_client: TestClient, seeded_session: Session) -> None:
    partner_id = _partner_id(seeded_session)
    target = _make_target_person(seeded_session)
    r = admin_client.post(
        f"/api/admin/partners/{partner_id}/roles",
        json={"person_id": target.id, "role": "partner_lead"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["partner_id"] == partner_id
    assert body["role"] == "partner_lead"
    assert body["person"]["id"] == target.id


def test_post_csrf_required(admin_client: TestClient, seeded_session: Session) -> None:
    partner_id = _partner_id(seeded_session)
    target = _make_target_person(seeded_session, suffix="csrf")
    r = admin_client.post(
        f"/api/admin/partners/{partner_id}/roles",
        json={"person_id": target.id, "role": "partner_lead"},
    )
    assert r.status_code == 403


def test_post_duplicate_is_idempotent_201(
    admin_client: TestClient, seeded_session: Session
) -> None:
    """Doppelte Vergabe gibt 201 mit dem bestehenden Eintrag zurück
    (idempotent — Service-Entscheidung)."""
    partner_id = _partner_id(seeded_session)
    target = _make_target_person(seeded_session, suffix="dup")
    body = {"person_id": target.id, "role": "partner_lead"}
    headers = _csrf(admin_client)
    r1 = admin_client.post(f"/api/admin/partners/{partner_id}/roles", json=body, headers=headers)
    assert r1.status_code == 201
    r2 = admin_client.post(f"/api/admin/partners/{partner_id}/roles", json=body, headers=headers)
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]


def test_post_invalid_role_returns_422(admin_client: TestClient, seeded_session: Session) -> None:
    partner_id = _partner_id(seeded_session)
    target = _make_target_person(seeded_session, suffix="badrole")
    r = admin_client.post(
        f"/api/admin/partners/{partner_id}/roles",
        json={"person_id": target.id, "role": "admin"},
        headers=_csrf(admin_client),
    )
    # Literal-Validation greift im Schema → 422.
    assert r.status_code == 422


def test_post_unknown_person_returns_404(admin_client: TestClient, seeded_session: Session) -> None:
    partner_id = _partner_id(seeded_session)
    r = admin_client.post(
        f"/api/admin/partners/{partner_id}/roles",
        json={
            "person_id": "00000000-0000-0000-0000-000000000000",
            "role": "partner_lead",
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 404


def test_member_cannot_post(
    admin_client: TestClient, member_client: TestClient, seeded_session: Session
) -> None:
    """`admin_client` ist hier nur Fixture-Vehikel, damit der
    admin-User existiert. ``member_client`` loggt zuletzt ein und macht
    den POST-Versuch."""
    partner_id = _partner_id(seeded_session)
    target = _make_target_person(seeded_session, suffix="m-deny")
    r = member_client.post(
        f"/api/admin/partners/{partner_id}/roles",
        json={"person_id": target.id, "role": "partner_lead"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


# ---- DELETE -----------------------------------------------------------------


def test_admin_can_delete_partner_lead(admin_client: TestClient, seeded_session: Session) -> None:
    partner_id = _partner_id(seeded_session)
    target = _make_target_person(seeded_session, suffix="del")
    admin_client.post(
        f"/api/admin/partners/{partner_id}/roles",
        json={"person_id": target.id, "role": "partner_lead"},
        headers=_csrf(admin_client),
    )
    r = admin_client.delete(
        f"/api/admin/partners/{partner_id}/roles/{target.id}",
        headers=_csrf(admin_client),
    )
    assert r.status_code == 204


def test_delete_missing_role_returns_404(admin_client: TestClient, seeded_session: Session) -> None:
    partner_id = _partner_id(seeded_session)
    target = _make_target_person(seeded_session, suffix="ghost")
    r = admin_client.delete(
        f"/api/admin/partners/{partner_id}/roles/{target.id}",
        headers=_csrf(admin_client),
    )
    assert r.status_code == 404


def test_delete_csrf_required(admin_client: TestClient, seeded_session: Session) -> None:
    partner_id = _partner_id(seeded_session)
    target = _make_target_person(seeded_session, suffix="csrf-del")
    admin_client.post(
        f"/api/admin/partners/{partner_id}/roles",
        json={"person_id": target.id, "role": "partner_lead"},
        headers=_csrf(admin_client),
    )
    r = admin_client.delete(
        f"/api/admin/partners/{partner_id}/roles/{target.id}",
    )
    assert r.status_code == 403
