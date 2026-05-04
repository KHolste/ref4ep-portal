"""API: Workpackage-Cockpit (Block 0009).

GET /api/workpackages/{code} liefert Status + Lead-Kontakte +
Meilensteine. PATCH /api/workpackages/{code} ändert die Cockpit-Felder.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.services.partner_contact_service import PartnerContactService
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.workpackage_service import WorkpackageService


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


# ---- GET ---------------------------------------------------------------


def test_workpackage_detail_returns_cockpit_fields(
    member_client: TestClient, seeded_session: Session
) -> None:
    r = member_client.get("/api/workpackages/WP3.1")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == "WP3.1"
    assert body["status"] == "planned"
    assert body["summary"] is None
    assert body["next_steps"] is None
    assert body["open_issues"] is None
    assert body["can_edit_status"] is False
    assert isinstance(body["lead_partner_contacts"], list)
    assert isinstance(body["milestones"], list)


def test_workpackage_detail_includes_lead_contacts(
    member_client: TestClient, seeded_session: Session
) -> None:
    # WP3.1 wird von TUD geführt → wir legen einen Kontakt am TUD an.
    tud = PartnerService(seeded_session, role="admin").get_by_short_name("TUD")
    assert tud is not None
    PartnerContactService(seeded_session, role="admin", person_id="admin-id").create(
        partner_id=tud.id,
        name="Dr. T. Lead",
        email="t.lead@tud.example",
        function="Projektleitung",
        is_project_lead=True,
    )
    seeded_session.commit()
    r = member_client.get("/api/workpackages/WP3.1")
    body = r.json()
    names = [c["name"] for c in body["lead_partner_contacts"]]
    assert "Dr. T. Lead" in names


def test_workpackage_detail_includes_milestones(
    member_client: TestClient, seeded_session: Session
) -> None:
    """WP3.1 hat MS3 (Referenz-HT fertiggestellt)."""
    r = member_client.get("/api/workpackages/WP3.1")
    body = r.json()
    codes = [ms["code"] for ms in body["milestones"]]
    assert "MS3" in codes


def test_admin_sees_can_edit_true(admin_client: TestClient, seeded_session: Session) -> None:
    r = admin_client.get("/api/workpackages/WP3.1")
    body = r.json()
    assert body["can_edit_status"] is True


def test_wp_lead_sees_can_edit_true(
    member_client: TestClient, seeded_session: Session, member_person_id: str
) -> None:
    wp = WorkpackageService(seeded_session, role="admin", person_id="fixture")
    target = wp.get_by_code("WP3.1")
    assert target is not None
    wp.add_membership(member_person_id, target.id, "wp_lead")
    seeded_session.commit()
    r = member_client.get("/api/workpackages/WP3.1")
    body = r.json()
    assert body["can_edit_status"] is True


# ---- PATCH -------------------------------------------------------------


def test_anonymous_cannot_patch_status(client: TestClient, seeded_session: Session) -> None:
    client.cookies.clear()
    r = client.patch("/api/workpackages/WP3.1", json={"status": "in_progress"})
    assert r.status_code in (401, 403)


def test_member_without_lead_cannot_patch(
    member_client: TestClient, seeded_session: Session, member_in_wp3
) -> None:
    # member_in_wp3 → Member ist wp_member in WP3, nicht lead.
    r = member_client.patch(
        "/api/workpackages/WP3", json={"status": "in_progress"}, headers=_csrf(member_client)
    )
    assert r.status_code == 403


def test_admin_can_patch_status(admin_client: TestClient, seeded_session: Session) -> None:
    r = admin_client.patch(
        "/api/workpackages/WP3.1",
        json={
            "status": "in_progress",
            "summary": "CAD im Gange.",
            "next_steps": "Review nächste Woche.",
            "open_issues": "Lieferzeit Spulen.",
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "in_progress"
    assert body["summary"] == "CAD im Gange."
    assert body["next_steps"] == "Review nächste Woche."
    assert body["open_issues"] == "Lieferzeit Spulen."


def test_wp_lead_can_patch_own_wp(
    member_client: TestClient, seeded_session: Session, member_person_id: str
) -> None:
    wp = WorkpackageService(seeded_session, role="admin", person_id="fixture")
    target = wp.get_by_code("WP4.1")
    assert target is not None
    wp.add_membership(member_person_id, target.id, "wp_lead")
    seeded_session.commit()
    r = member_client.patch(
        "/api/workpackages/WP4.1",
        json={"status": "critical"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "critical"


def test_wp_lead_cannot_patch_foreign_wp(
    member_client: TestClient, seeded_session: Session, member_person_id: str
) -> None:
    wp = WorkpackageService(seeded_session, role="admin", person_id="fixture")
    target = wp.get_by_code("WP4.1")
    assert target is not None
    wp.add_membership(member_person_id, target.id, "wp_lead")
    seeded_session.commit()
    # WP3.1 ist ein anderer WP
    r = member_client.patch(
        "/api/workpackages/WP3.1",
        json={"status": "critical"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_invalid_status_returns_422(admin_client: TestClient) -> None:
    r = admin_client.patch(
        "/api/workpackages/WP3.1",
        json={"status": "doing"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 422
