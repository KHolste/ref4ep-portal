"""API: GET /api/cockpit/project (Block 0010)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.services.workpackage_service import WorkpackageService


def test_anonymous_cannot_get_project_cockpit(client: TestClient, seeded_session: Session) -> None:
    client.cookies.clear()
    r = client.get("/api/cockpit/project")
    assert r.status_code == 401


def test_member_can_get_project_cockpit(member_client: TestClient, seeded_session: Session) -> None:
    r = member_client.get("/api/cockpit/project")
    assert r.status_code == 200
    body = r.json()
    # Pflichtfelder
    assert "today" in body
    assert isinstance(body["upcoming_milestones"], list)
    assert isinstance(body["overdue_milestones"], list)
    assert isinstance(body["workpackages_with_open_issues"], list)
    assert isinstance(body["status_counts"], dict)
    assert isinstance(body["workpackage_status_overview"], list)


def test_status_counts_returns_all_five_keys(
    member_client: TestClient, seeded_session: Session
) -> None:
    r = member_client.get("/api/cockpit/project")
    body = r.json()
    assert set(body["status_counts"].keys()) == {
        "planned",
        "in_progress",
        "waiting_for_input",
        "critical",
        "completed",
    }


def test_overview_lists_all_workpackages(
    member_client: TestClient, seeded_session: Session
) -> None:
    r = member_client.get("/api/cockpit/project")
    body = r.json()
    codes = {entry["code"] for entry in body["workpackage_status_overview"]}
    assert {"WP1", "WP3.1", "WP4.1"}.issubset(codes)


def test_open_issues_appear_after_status_update(
    admin_client: TestClient, seeded_session: Session
) -> None:
    """Nach PATCH eines WP mit open_issues taucht es im Cockpit auf."""
    wp_service = WorkpackageService(seeded_session, role="admin", person_id="fixture")
    wp = wp_service.get_by_code("WP3.1")
    assert wp is not None
    # Direkt im Modell setzen — der Test soll nicht auf den PATCH-Endpoint angewiesen sein.
    wp.status = "critical"
    wp.open_issues = "Lieferzeit Spulen"
    wp.next_steps = "Alternativen prüfen"
    seeded_session.commit()
    r = admin_client.get("/api/cockpit/project")
    body = r.json()
    issues = body["workpackages_with_open_issues"]
    matching = [i for i in issues if i["code"] == "WP3.1"]
    assert matching, f"WP3.1 fehlt in Cockpit-Open-Issues: {issues}"
    entry = matching[0]
    assert entry["status"] == "critical"
    assert entry["open_issues"] == "Lieferzeit Spulen"
    assert entry["next_steps"] == "Alternativen prüfen"


def test_upcoming_limit_query_param(member_client: TestClient, seeded_session: Session) -> None:
    r = member_client.get("/api/cockpit/project?upcoming_limit=2")
    assert r.status_code == 200
    body = r.json()
    assert len(body["upcoming_milestones"]) <= 2


def test_upcoming_limit_validation(member_client: TestClient) -> None:
    r = member_client.get("/api/cockpit/project?upcoming_limit=0")
    assert r.status_code == 422
    r = member_client.get("/api/cockpit/project?upcoming_limit=999")
    assert r.status_code == 422


def test_no_deliverable_terms_in_payload(
    member_client: TestClient, seeded_session: Session
) -> None:
    """Keine Deliverable-Felder in der Cockpit-API-Antwort."""
    r = member_client.get("/api/cockpit/project")
    body_text = r.text.lower()
    assert "deliverable" not in body_text


def test_milestones_carry_workpackage_link_or_overall_marker(
    member_client: TestClient, seeded_session: Session
) -> None:
    r = member_client.get("/api/cockpit/project")
    body = r.json()
    # Sammle alle MS aus upcoming + overdue
    items = body["upcoming_milestones"] + body["overdue_milestones"]
    by_code = {ms["code"]: ms for ms in items}
    # MS3 hängt an WP3.1
    if "MS3" in by_code:
        assert by_code["MS3"]["workpackage_code"] == "WP3.1"
    # MS4 ist Gesamtprojekt → workpackage_code None
    if "MS4" in by_code:
        assert by_code["MS4"]["workpackage_code"] is None


def test_no_deliverables_endpoint_remains(member_client: TestClient) -> None:
    """Sicherheit: in diesem Block kommt KEIN Deliverable-Endpoint hinzu."""
    r = member_client.get("/api/deliverables")
    assert r.status_code == 404
