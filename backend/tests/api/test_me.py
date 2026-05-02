"""GET /api/me."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_me_requires_login(client: TestClient, migrated_db) -> None:
    response = client.get("/api/me")
    assert response.status_code == 401


def test_me_returns_profile(admin_client: TestClient) -> None:
    response = admin_client.get("/api/me")
    assert response.status_code == 200
    body = response.json()
    assert body["person"]["email"]
    assert body["person"]["partner"]["short_name"] == "JLU"
    assert isinstance(body["memberships"], list)
