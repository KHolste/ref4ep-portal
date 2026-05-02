"""Health-Endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_200_with_expected_payload(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {"status", "db", "version"}
    assert payload["status"] == "ok"


def test_health_db_ping_against_test_db(client: TestClient) -> None:
    payload = client.get("/api/health").json()
    assert payload["db"] == "ok"


def test_health_does_not_require_auth(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
