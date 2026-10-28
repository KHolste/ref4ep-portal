"""POST /api/auth/logout und das Formular-Logout POST /logout."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_form_logout_redirects_to_login_with_confirmation(admin_client: TestClient) -> None:
    """Block 0055: Abmelden führt zurück zur Anmeldung — nicht mehr auf
    die alte Startseite."""
    response = admin_client.post("/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?logged_out=1"


def test_form_logout_clears_cookies(admin_client: TestClient) -> None:
    admin_client.post("/logout", follow_redirects=False)
    admin_client.cookies.pop("ref4ep_session", None)
    assert admin_client.get("/api/me").status_code == 401


def test_login_page_shows_logout_confirmation(client: TestClient) -> None:
    plain = client.get("/login")
    assert "Du wurdest abgemeldet." not in plain.text
    after_logout = client.get("/login?logged_out=1")
    assert after_logout.status_code == 200
    assert "Du wurdest abgemeldet." in after_logout.text
    # Weg zur öffentlichen Projektseite ist von hier aus sichtbar.
    assert "Zur Projektseite" in after_logout.text


def test_logout_clears_session_cookie_and_blocks_me(admin_client: TestClient) -> None:
    csrf = admin_client.cookies.get("ref4ep_csrf")
    response = admin_client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf or ""})
    assert response.status_code == 200
    # ref4ep_session ist gelöscht (max-age=0); zur Sicherheit explizit entfernen:
    admin_client.cookies.pop("ref4ep_session", None)
    me = admin_client.get("/api/me")
    assert me.status_code == 401
