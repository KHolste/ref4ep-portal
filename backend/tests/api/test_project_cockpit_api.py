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


# ---- Block 0025 — Ampel-Dashboard ----------------------------------------


def test_dashboard_carries_workpackage_health(
    member_client: TestClient, seeded_session: Session
) -> None:
    r = member_client.get("/api/cockpit/project")
    body = r.json()
    assert "workpackage_health" in body
    health = body["workpackage_health"]
    assert isinstance(health, list)
    if health:
        entry = health[0]
        for key in (
            "code",
            "title",
            "status",
            "traffic_light",
            "milestone_counts",
            "document_counts",
            "next_milestone",
        ):
            assert key in entry, f"Feld {key!r} fehlt"
        assert entry["traffic_light"] in {"green", "yellow", "red", "gray"}
        # milestone_counts mit allen vier Keys
        assert set(entry["milestone_counts"].keys()) == {"green", "yellow", "red", "gray"}
        # document_counts mit allen drei Statuswerten
        assert set(entry["document_counts"].keys()) == {"draft", "in_review", "released"}


def test_dashboard_carries_milestone_progress(
    member_client: TestClient, seeded_session: Session
) -> None:
    r = member_client.get("/api/cockpit/project")
    body = r.json()
    assert "milestone_progress" in body
    progress = body["milestone_progress"]
    assert {"achieved", "total"} == set(progress.keys())
    assert progress["achieved"] >= 0
    assert progress["total"] >= progress["achieved"]


def test_dashboard_carries_open_meeting_actions(
    member_client: TestClient, seeded_session: Session
) -> None:
    r = member_client.get("/api/cockpit/project")
    body = r.json()
    assert "open_meeting_actions" in body
    assert isinstance(body["open_meeting_actions"], int)
    assert body["open_meeting_actions"] >= 0


def test_dashboard_carries_campaign_status_counts(
    member_client: TestClient, seeded_session: Session
) -> None:
    r = member_client.get("/api/cockpit/project")
    body = r.json()
    assert "campaign_status_counts" in body
    # Alle 7 erlaubten Status-Werte vorhanden, mit 0 default.
    expected = {
        "planned",
        "preparing",
        "running",
        "completed",
        "evaluated",
        "cancelled",
        "postponed",
    }
    assert expected == set(body["campaign_status_counts"].keys())


def test_dashboard_carries_60_day_timeline(
    member_client: TestClient, seeded_session: Session
) -> None:
    r = member_client.get("/api/cockpit/project")
    body = r.json()
    assert "timeline_next_60_days" in body
    timeline = body["timeline_next_60_days"]
    assert isinstance(timeline, list)
    for ev in timeline:
        assert ev["kind"] in {"milestone", "meeting", "campaign"}
        assert "date" in ev
        assert "title" in ev
        assert "id" in ev


def test_dashboard_health_aggregates_at_risk_to_red(
    admin_client: TestClient, seeded_session: Session
) -> None:
    """Setzt einen Meilenstein auf at_risk; das zugehörige WP muss
    in workpackage_health auf 'red' aggregieren."""
    from ref4ep.domain.models import Milestone

    ms = seeded_session.query(Milestone).filter(Milestone.workpackage_id.isnot(None)).first()
    assert ms is not None
    ms.status = "at_risk"
    seeded_session.commit()
    r = admin_client.get("/api/cockpit/project")
    body = r.json()
    matching = [h for h in body["workpackage_health"] if h["code"] == ms.workpackage.code]
    assert matching, f"WP {ms.workpackage.code!r} fehlt in workpackage_health"
    assert matching[0]["traffic_light"] == "red"
