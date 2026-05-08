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


# ---- Block 0027 — Workpackage-Zeitplan ---------------------------------


def test_workpackage_detail_carries_schedule_fields(
    member_client: TestClient, seeded_session: Session
) -> None:
    r = member_client.get("/api/workpackages/WP3.1")
    assert r.status_code == 200
    body = r.json()
    assert "start_date" in body
    assert "end_date" in body
    # Initial-Seed (Block 0027): WP3.1 ist Antrags-Monat 1–24 ab März 2026,
    # also 2026-03-01 bis 2028-02-29. Beide Werte sind Date-Strings.
    assert body["start_date"] == "2026-03-01"
    assert body["end_date"] == "2028-02-29"


def test_workpackage_top_level_has_no_schedule_from_seed(
    member_client: TestClient, seeded_session: Session
) -> None:
    """Hauptpakete (WP3) bekommen keine Datumsfelder aus dem Seed —
    der Gantt aggregiert sie aus den Sub-WPs."""
    r = member_client.get("/api/workpackages/WP3").json()
    assert r["start_date"] is None
    assert r["end_date"] is None


def test_admin_can_set_schedule(admin_client: TestClient, seeded_session: Session) -> None:
    r = admin_client.patch(
        "/api/workpackages/WP3.1",
        json={"start_date": "2026-06-01", "end_date": "2027-12-31"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 200, r.text
    follow = admin_client.get("/api/workpackages/WP3.1").json()
    assert follow["start_date"] == "2026-06-01"
    assert follow["end_date"] == "2027-12-31"


def test_only_one_endpoint_value_is_allowed(
    admin_client: TestClient, seeded_session: Session
) -> None:
    """Einzelne Werte (nur Start oder nur Ende) sind erlaubt — der
    jeweils andere Wert bleibt unangetastet."""
    # Vorher: nur start_date setzen, end_date weglassen.
    pre = admin_client.get("/api/workpackages/WP3.1").json()
    end_before = pre["end_date"]
    r = admin_client.patch(
        "/api/workpackages/WP3.1",
        json={"start_date": "2026-06-01"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 200, r.text
    body = admin_client.get("/api/workpackages/WP3.1").json()
    assert body["start_date"] == "2026-06-01"
    assert body["end_date"] == end_before


def test_can_clear_dates_explicitly(admin_client: TestClient, seeded_session: Session) -> None:
    """Explizit ``null`` im PATCH leert das Datumsfeld."""
    r = admin_client.patch(
        "/api/workpackages/WP3.1",
        json={"start_date": None, "end_date": None},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 200, r.text
    body = admin_client.get("/api/workpackages/WP3.1").json()
    assert body["start_date"] is None
    assert body["end_date"] is None


def test_end_before_start_returns_422(admin_client: TestClient, seeded_session: Session) -> None:
    r = admin_client.patch(
        "/api/workpackages/WP3.1",
        json={"start_date": "2026-12-01", "end_date": "2026-06-01"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 422


def test_member_cannot_set_schedule(member_client: TestClient, seeded_session: Session) -> None:
    r = member_client.patch(
        "/api/workpackages/WP3.1",
        json={"start_date": "2026-06-01"},
        headers=_csrf(member_client),
    )
    # Memberschaft genügt nicht — nur Admin oder WP-Lead.
    assert r.status_code == 403


def test_schedule_audit_records_before_after(
    admin_client: TestClient, seeded_session: Session
) -> None:
    """Audit für Datums-Updates nutzt dieselbe Action wie für andere
    Cockpit-Felder (workpackage.update_status) und enthält before/after."""
    import json

    from ref4ep.domain.models import AuditLog

    admin_client.patch(
        "/api/workpackages/WP3.1",
        json={"start_date": "2026-06-01", "end_date": "2027-06-01"},
        headers=_csrf(admin_client),
    )
    entries = (
        seeded_session.query(AuditLog)
        .filter_by(action="workpackage.update_status", entity_type="workpackage")
        .order_by(AuditLog.created_at.desc())
        .limit(1)
        .all()
    )
    assert entries, "Kein Audit-Eintrag für update_status"
    payload = json.loads(entries[0].details)
    assert "start_date" in payload["after"]
    assert "end_date" in payload["after"]
    assert payload["after"]["start_date"] == "2026-06-01"
    assert payload["after"]["end_date"] == "2027-06-01"
