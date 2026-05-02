"""CSRF-Pflicht für schreibende Endpunkte."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import ADMIN_PASSWORD


def test_password_change_without_csrf_header_blocked(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/auth/password",
        json={"old_password": ADMIN_PASSWORD, "new_password": "AnotherStrong-Pw1!"},
    )
    assert response.status_code == 403


def test_password_change_with_wrong_csrf_blocked(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/auth/password",
        json={"old_password": ADMIN_PASSWORD, "new_password": "AnotherStrong-Pw1!"},
        headers={"X-CSRF-Token": "wrong"},
    )
    assert response.status_code == 403


def test_password_change_with_correct_csrf_passes(admin_client: TestClient) -> None:
    csrf = admin_client.cookies.get("ref4ep_csrf")
    response = admin_client.post(
        "/api/auth/password",
        json={"old_password": ADMIN_PASSWORD, "new_password": "AnotherStrong-Pw1!"},
        headers={"X-CSRF-Token": csrf or ""},
    )
    assert response.status_code == 200
