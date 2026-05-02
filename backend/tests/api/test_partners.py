"""GET /api/partners + GET /partners (öffentlich)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_api_partners_requires_login(client: TestClient, migrated_db) -> None:
    response = client.get("/api/partners")
    assert response.status_code == 401


def test_api_partners_returns_seed(admin_client: TestClient) -> None:
    response = admin_client.get("/api/partners")
    assert response.status_code == 200
    short_names = {p["short_name"] for p in response.json()}
    assert short_names == {"JLU", "IOM", "CAU", "THM", "TUD"}


def test_public_partners_page_lists_all(client: TestClient, seeded_session) -> None:
    response = client.get("/partners")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    for short in ("JLU", "IOM", "CAU", "THM", "TUD"):
        assert short in body
