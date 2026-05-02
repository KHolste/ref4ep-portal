"""POST /api/auth/login + Cookie-Verhalten."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD


def test_login_success_sets_cookies(client: TestClient, admin_person_id: str) -> None:
    response = client.post(
        "/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["person"]["email"] == ADMIN_EMAIL
    assert body["must_change_password"] is False
    cookies = response.cookies
    assert "ref4ep_session" in cookies
    assert "ref4ep_csrf" in cookies


def test_login_wrong_password_returns_401(client: TestClient, admin_person_id: str) -> None:
    response = client.post(
        "/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-password!!"}
    )
    assert response.status_code == 401
    detail = response.json()["detail"]["error"]
    assert detail["code"] == "invalid_credentials"


def test_login_unknown_email_returns_generic_401(client: TestClient, admin_person_id: str) -> None:
    response = client.post(
        "/api/auth/login", json={"email": "ghost@test.example", "password": "Whatever1234"}
    )
    assert response.status_code == 401


def test_login_disabled_user_returns_401(
    client: TestClient, admin_person_id: str, seeded_session
) -> None:
    from ref4ep.services.person_service import PersonService

    PersonService(seeded_session, role="admin").disable(admin_person_id)
    seeded_session.commit()
    response = client.post(
        "/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 401


def test_login_must_change_password_flag(
    client: TestClient, seeded_session, admin_person_id: str
) -> None:
    # admin_person_id-Fixture setzt must_change_password=False; wir aktivieren es manuell.
    from ref4ep.domain.models import Person

    p = seeded_session.get(Person, admin_person_id)
    p.must_change_password = True
    seeded_session.commit()

    response = client.post(
        "/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200
    assert response.json()["must_change_password"] is True
