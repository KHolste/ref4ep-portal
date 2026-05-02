"""POST /api/auth/password — eigenes Passwort ändern."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import ADMIN_PASSWORD


def test_change_password_success(admin_client: TestClient) -> None:
    csrf = admin_client.cookies.get("ref4ep_csrf")
    response = admin_client.post(
        "/api/auth/password",
        json={"old_password": ADMIN_PASSWORD, "new_password": "NewStrong-PW-1!"},
        headers={"X-CSRF-Token": csrf or ""},
    )
    assert response.status_code == 200


def test_change_password_wrong_old_returns_400(admin_client: TestClient) -> None:
    csrf = admin_client.cookies.get("ref4ep_csrf")
    response = admin_client.post(
        "/api/auth/password",
        json={"old_password": "wrong-old-pw", "new_password": "NewStrong-PW-1!"},
        headers={"X-CSRF-Token": csrf or ""},
    )
    assert response.status_code == 400


def test_change_password_too_short_returns_422_or_400(admin_client: TestClient) -> None:
    csrf = admin_client.cookies.get("ref4ep_csrf")
    response = admin_client.post(
        "/api/auth/password",
        json={"old_password": ADMIN_PASSWORD, "new_password": "short"},
        headers={"X-CSRF-Token": csrf or ""},
    )
    # Pydantic-Validation fängt das vor dem Service ab → 422.
    assert response.status_code in (400, 422)


def test_change_password_without_csrf_403(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/auth/password",
        json={"old_password": ADMIN_PASSWORD, "new_password": "NewStrong-PW-1!"},
    )
    assert response.status_code == 403
