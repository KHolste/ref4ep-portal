"""Admin-API für WP-Mitgliedschaften — add/set_role/remove."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ref4ep.domain.models import AuditLog


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def test_member_cannot_use_membership_endpoints(
    member_client: TestClient, member_person_id: str
) -> None:
    r = member_client.post(
        f"/api/admin/persons/{member_person_id}/memberships",
        json={"workpackage_code": "WP3", "wp_role": "wp_member"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_add_membership_appears_in_detail(admin_client: TestClient, member_person_id: str) -> None:
    r = admin_client.post(
        f"/api/admin/persons/{member_person_id}/memberships",
        json={"workpackage_code": "WP3", "wp_role": "wp_member"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 201
    detail = admin_client.get(f"/api/admin/persons/{member_person_id}").json()
    codes = [m["workpackage_code"] for m in detail["memberships"]]
    assert "WP3" in codes


def test_set_role_writes_membership_set_role_audit(
    admin_client: TestClient, member_person_id: str, seeded_session
) -> None:
    admin_client.post(
        f"/api/admin/persons/{member_person_id}/memberships",
        json={"workpackage_code": "WP3", "wp_role": "wp_member"},
        headers=_csrf(admin_client),
    )
    # Vorher: kein set_role-Eintrag
    before_count = seeded_session.query(AuditLog).filter_by(action="membership.set_role").count()
    r = admin_client.patch(
        f"/api/admin/persons/{member_person_id}/memberships/WP3",
        json={"wp_role": "wp_lead"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 200
    assert r.json()["wp_role"] == "wp_lead"
    seeded_session.expire_all()
    after_count = seeded_session.query(AuditLog).filter_by(action="membership.set_role").count()
    assert after_count == before_count + 1
    # Sicherheitsfall: weder remove noch add wurden hier erzeugt.
    last_remove = (
        seeded_session.query(AuditLog)
        .filter_by(action="membership.remove", entity_type="membership")
        .count()
    )
    assert last_remove == 0  # nur set_role lief, keine doppelten Audit-Einträge


def test_set_role_unknown_membership_returns_404(
    admin_client: TestClient, member_person_id: str
) -> None:
    r = admin_client.patch(
        f"/api/admin/persons/{member_person_id}/memberships/WP4",
        json={"wp_role": "wp_lead"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 404


def test_delete_membership(admin_client: TestClient, member_person_id: str, member_in_wp3) -> None:
    r = admin_client.delete(
        f"/api/admin/persons/{member_person_id}/memberships/WP3",
        headers=_csrf(admin_client),
    )
    assert r.status_code == 204
    detail = admin_client.get(f"/api/admin/persons/{member_person_id}").json()
    codes = [m["workpackage_code"] for m in detail["memberships"]]
    assert "WP3" not in codes
