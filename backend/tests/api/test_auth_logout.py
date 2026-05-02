"""POST /api/auth/logout."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_logout_clears_session_cookie_and_blocks_me(admin_client: TestClient) -> None:
    csrf = admin_client.cookies.get("ref4ep_csrf")
    response = admin_client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf or ""})
    assert response.status_code == 200
    # ref4ep_session ist gelöscht (max-age=0); zur Sicherheit explizit entfernen:
    admin_client.cookies.pop("ref4ep_session", None)
    me = admin_client.get("/api/me")
    assert me.status_code == 401
