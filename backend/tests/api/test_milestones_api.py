"""API: /api/milestones (Block 0009)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.services.milestone_service import MilestoneService
from ref4ep.services.workpackage_service import WorkpackageService


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


# ---- LIST / GET --------------------------------------------------------


def test_anonymous_cannot_list(client: TestClient, seeded_session: Session) -> None:
    client.cookies.clear()
    r = client.get("/api/milestones")
    assert r.status_code == 401


def test_member_lists_four_milestones(member_client: TestClient, seeded_session: Session) -> None:
    r = member_client.get("/api/milestones")
    assert r.status_code == 200
    body = r.json()
    codes = [ms["code"] for ms in body]
    assert codes == ["MS1", "MS2", "MS3", "MS4"]
    # Member darf nicht editieren.
    assert all(ms["can_edit"] is False for ms in body)


def test_admin_can_edit_flags_true(admin_client: TestClient, seeded_session: Session) -> None:
    r = admin_client.get("/api/milestones")
    body = r.json()
    assert all(ms["can_edit"] is True for ms in body)


def test_get_single_milestone(member_client: TestClient, seeded_session: Session) -> None:
    ms3 = MilestoneService(seeded_session).get_by_code("MS3")
    assert ms3 is not None
    r = member_client.get(f"/api/milestones/{ms3.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == "MS3"
    assert body["workpackage_code"] == "WP3.1"


def test_get_unknown_milestone_returns_404(admin_client: TestClient) -> None:
    r = admin_client.get("/api/milestones/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


# ---- PATCH -------------------------------------------------------------


def test_admin_can_patch_milestone(admin_client: TestClient, seeded_session: Session) -> None:
    ms2 = MilestoneService(seeded_session).get_by_code("MS2")
    assert ms2 is not None
    r = admin_client.patch(
        f"/api/milestones/{ms2.id}",
        json={"status": "at_risk", "note": "Lieferverzug"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "at_risk"
    assert body["note"] == "Lieferverzug"


def test_wp_lead_can_patch_own_milestone(
    member_client: TestClient, seeded_session: Session, member_person_id: str
) -> None:
    wp = WorkpackageService(seeded_session, role="admin", person_id="fixture")
    target = wp.get_by_code("WP3.1")
    assert target is not None
    wp.add_membership(member_person_id, target.id, "wp_lead")
    seeded_session.commit()
    ms3 = MilestoneService(seeded_session).get_by_code("MS3")
    assert ms3 is not None
    r = member_client.patch(
        f"/api/milestones/{ms3.id}",
        json={"status": "postponed"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "postponed"


def test_wp_lead_cannot_patch_foreign_milestone(
    member_client: TestClient, seeded_session: Session, member_person_id: str
) -> None:
    wp = WorkpackageService(seeded_session, role="admin", person_id="fixture")
    target = wp.get_by_code("WP3.1")
    assert target is not None
    wp.add_membership(member_person_id, target.id, "wp_lead")
    seeded_session.commit()
    ms2 = MilestoneService(seeded_session).get_by_code("MS2")  # WP4.1 → fremd
    assert ms2 is not None
    r = member_client.patch(
        f"/api/milestones/{ms2.id}",
        json={"status": "postponed"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_wp_lead_cannot_patch_overall_project_milestone(
    member_client: TestClient, seeded_session: Session, member_person_id: str
) -> None:
    wp = WorkpackageService(seeded_session, role="admin", person_id="fixture")
    target = wp.get_by_code("WP3.1")
    assert target is not None
    wp.add_membership(member_person_id, target.id, "wp_lead")
    seeded_session.commit()
    ms4 = MilestoneService(seeded_session).get_by_code("MS4")
    assert ms4 is not None
    assert ms4.workpackage_id is None
    r = member_client.patch(
        f"/api/milestones/{ms4.id}",
        json={"status": "postponed"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_member_cannot_patch_milestone(member_client: TestClient, seeded_session: Session) -> None:
    ms = MilestoneService(seeded_session).get_by_code("MS1")
    assert ms is not None
    r = member_client.patch(
        f"/api/milestones/{ms.id}",
        json={"note": "hack"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_invalid_status_returns_422(admin_client: TestClient, seeded_session: Session) -> None:
    ms = MilestoneService(seeded_session).get_by_code("MS2")
    assert ms is not None
    r = admin_client.patch(
        f"/api/milestones/{ms.id}",
        json={"status": "erledigt"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 422


def test_no_deliverable_endpoint_exists(member_client: TestClient) -> None:
    """Ref4EP führt keine Deliverables — entsprechender Endpoint fehlt."""
    r = member_client.get("/api/deliverables")
    assert r.status_code == 404
