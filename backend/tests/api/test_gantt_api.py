"""API: GET /api/gantt (Block 0026)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_anonymous_cannot_get_gantt(client: TestClient, seeded_session) -> None:
    client.cookies.clear()
    r = client.get("/api/gantt")
    assert r.status_code == 401


def test_member_can_get_gantt(member_client: TestClient, seeded_session) -> None:
    r = member_client.get("/api/gantt")
    assert r.status_code == 200
    body = r.json()
    for key in ("today", "project_start", "project_end", "tracks"):
        assert key in body, f"Feld {key!r} fehlt"
    assert isinstance(body["tracks"], list)


def test_track_shape(member_client: TestClient, seeded_session) -> None:
    r = member_client.get("/api/gantt")
    body = r.json()
    if not body["tracks"]:
        return
    track = body["tracks"][0]
    for key in ("code", "title", "sort_order", "milestones", "campaigns", "meetings"):
        assert key in track


def test_milestone_carries_traffic_light(member_client: TestClient, seeded_session) -> None:
    r = member_client.get("/api/gantt")
    body = r.json()
    all_ms = [m for t in body["tracks"] for m in t["milestones"]]
    if not all_ms:
        return
    for m in all_ms:
        assert m["traffic_light"] in {"green", "yellow", "red", "gray"}
        for key in ("id", "code", "title", "planned_date", "status"):
            assert key in m


def test_project_window_is_at_least_36_months(member_client: TestClient, seeded_session) -> None:
    """end - start ≥ 36 Monate (Auto-Fit-Spec)."""
    from datetime import date

    r = member_client.get("/api/gantt")
    body = r.json()
    start = date.fromisoformat(body["project_start"])
    end = date.fromisoformat(body["project_end"])
    months = (end.year - start.year) * 12 + (end.month - start.month)
    assert months >= 36, f"Window nur {months} Monate"
