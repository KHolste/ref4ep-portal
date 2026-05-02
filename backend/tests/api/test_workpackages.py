"""GET /api/workpackages und GET /api/workpackages/{code}."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_list_returns_35_entries(admin_client: TestClient) -> None:
    response = admin_client.get("/api/workpackages")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 35
    parents = [w for w in items if w["parent_code"] is None]
    assert len(parents) == 8


def test_parent_only_filter(admin_client: TestClient) -> None:
    response = admin_client.get("/api/workpackages", params={"parent_only": "true"})
    assert response.status_code == 200
    items = response.json()
    assert [w["code"] for w in items] == [
        "WP1",
        "WP2",
        "WP3",
        "WP4",
        "WP5",
        "WP6",
        "WP7",
        "WP8",
    ]


def test_detail_with_children_and_lead(admin_client: TestClient) -> None:
    response = admin_client.get("/api/workpackages/WP3")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "WP3"
    assert body["lead_partner"]["short_name"] == "TUD"
    assert [c["code"] for c in body["children"]] == ["WP3.1", "WP3.2", "WP3.3"]


def test_detail_unknown_code_404(admin_client: TestClient) -> None:
    response = admin_client.get("/api/workpackages/WPnotexist")
    assert response.status_code == 404
