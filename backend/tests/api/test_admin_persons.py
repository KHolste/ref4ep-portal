"""Admin-API für Personen — CRUD, Aktivieren/Deaktivieren, Rolle, Reset-Passwort."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def _admin(client: TestClient, person_id: str) -> None:
    """Hilfsfunktion: Admin-Login auf demselben Client."""
    client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})


# ---- Auth-Boundary ------------------------------------------------------


def test_anonymous_cannot_list(client: TestClient, member_in_wp3) -> None:
    client.cookies.clear()
    r = client.get("/api/admin/persons")
    assert r.status_code == 401


def test_member_cannot_list(member_client: TestClient, member_in_wp3) -> None:
    r = member_client.get("/api/admin/persons")
    assert r.status_code == 403


def test_admin_can_list(admin_client: TestClient, member_in_wp3) -> None:
    r = admin_client.get("/api/admin/persons")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert any(p["email"] == ADMIN_EMAIL for p in body)
    # Sicherheitsfall: kein Hash, kein Passwort in der Antwort.
    for p in body:
        assert "password_hash" not in p
        assert "password" not in p


# ---- Anlegen ------------------------------------------------------------


def test_create_person_returns_initial_password_and_no_hash(
    admin_client: TestClient, seeded_session
) -> None:
    partners = admin_client.get("/api/admin/partners").json()
    jlu = next(p for p in partners if p["short_name"] == "JLU")
    r = admin_client.post(
        "/api/admin/persons",
        json={
            "email": "neu@test.example",
            "display_name": "Neu Test",
            "partner_id": jlu["id"],
            "platform_role": "member",
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["person"]["email"] == "neu@test.example"
    assert body["person"]["must_change_password"] is True
    pw = body["initial_password"]
    assert isinstance(pw, str) and len(pw) >= 10
    # Person-Antwort enthält keine Passwort-Felder
    assert "password_hash" not in body["person"]
    assert "password" not in body["person"]
    # Login mit dem ausgegebenen Passwort funktioniert.
    fresh = TestClient(admin_client.app)
    login = fresh.post("/api/auth/login", json={"email": "neu@test.example", "password": pw})
    assert login.status_code == 200
    fresh.close()


def test_create_person_rejects_member(member_client: TestClient, member_in_wp3) -> None:
    partners = member_client.get("/api/partners").json()
    jlu = next(p for p in partners if p["short_name"] == "JLU")
    r = member_client.post(
        "/api/admin/persons",
        json={
            "email": "x@y",
            "display_name": "X",
            "partner_id": jlu["id"],
        },
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_create_with_explicit_password_uses_it(admin_client: TestClient, seeded_session) -> None:
    jlu = next(
        p for p in admin_client.get("/api/admin/partners").json() if p["short_name"] == "JLU"
    )
    own_password = "MeinAdminGenerated1!"
    r = admin_client.post(
        "/api/admin/persons",
        json={
            "email": "explizit@test.example",
            "display_name": "Explizit",
            "partner_id": jlu["id"],
            "initial_password": own_password,
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 201
    assert r.json()["initial_password"] == own_password


# ---- Detail / Patch -----------------------------------------------------


def test_detail_includes_memberships(admin_client: TestClient, member_in_wp3) -> None:
    members = admin_client.get("/api/admin/persons").json()
    member = next(m for m in members if m["email"] == "member@test.example")
    r = admin_client.get(f"/api/admin/persons/{member['id']}")
    assert r.status_code == 200
    body = r.json()
    assert "memberships" in body
    codes = [m["workpackage_code"] for m in body["memberships"]]
    assert "WP3" in codes


def test_patch_updates_display_name_and_partner(admin_client: TestClient, seeded_session) -> None:
    members = admin_client.get("/api/admin/persons").json()
    target = members[0]
    partners = admin_client.get("/api/admin/partners").json()
    other = next(p for p in partners if p["short_name"] != target["partner"]["short_name"])
    r = admin_client.patch(
        f"/api/admin/persons/{target['id']}",
        json={"display_name": "Geändert", "partner_id": other["id"]},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["display_name"] == "Geändert"
    assert body["partner"]["short_name"] == other["short_name"]


def test_patch_updates_email(
    admin_client: TestClient, member_person_id: str, app
) -> None:
    r = admin_client.patch(
        f"/api/admin/persons/{member_person_id}",
        json={"email": "  Renamed@Test.example  "},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "renamed@test.example"
    # Login mit alter Email schlägt fehl, neue Email funktioniert.
    fresh = TestClient(app)
    old = fresh.post(
        "/api/auth/login",
        json={"email": "member@test.example", "password": "M3mberP4ssword!"},
    )
    assert old.status_code == 401
    new = fresh.post(
        "/api/auth/login",
        json={"email": "renamed@test.example", "password": "M3mberP4ssword!"},
    )
    assert new.status_code == 200
    fresh.close()


def test_patch_email_session_survives_for_existing_user(
    member_client: TestClient,
    member_person_id: str,
    admin_person_id: str,
    app,
) -> None:
    # member_client besitzt eine aktive Session vor der Email-Änderung.
    me_before = member_client.get("/api/me").json()
    assert me_before["person"]["email"] == "member@test.example"

    # Email-Änderung über separaten Admin-Client, damit der Cookie-Jar
    # des member_client unverändert bleibt.
    admin_only = TestClient(app)
    admin_only.post(
        "/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    r = admin_only.patch(
        f"/api/admin/persons/{member_person_id}",
        json={"email": "rotated@test.example"},
        headers={"X-CSRF-Token": admin_only.cookies.get("ref4ep_csrf") or ""},
    )
    assert r.status_code == 200, r.text
    admin_only.close()

    # Cookie/Token bleibt gültig (person_id-basiert), /api/me liefert neue Email.
    me_after = member_client.get("/api/me")
    assert me_after.status_code == 200
    assert me_after.json()["person"]["email"] == "rotated@test.example"


def test_patch_email_conflict_returns_409(
    admin_client: TestClient, member_person_id: str, admin_person_id: str
) -> None:
    # Versuch, Member auf Admin-Email zu setzen -> 409.
    r = admin_client.patch(
        f"/api/admin/persons/{member_person_id}",
        json={"email": ADMIN_EMAIL},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"]["error"]["code"] == "email_taken"


def test_patch_email_invalid_returns_422(
    admin_client: TestClient, member_person_id: str
) -> None:
    r = admin_client.patch(
        f"/api/admin/persons/{member_person_id}",
        json={"email": "not-an-email"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 422, r.text


def test_patch_email_member_forbidden(
    member_client: TestClient, admin_person_id: str
) -> None:
    r = member_client.patch(
        f"/api/admin/persons/{admin_person_id}",
        json={"email": "hijack@test.example"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_patch_email_unknown_person_returns_404(admin_client: TestClient) -> None:
    r = admin_client.patch(
        "/api/admin/persons/00000000-0000-0000-0000-000000000000",
        json={"email": "ghost@test.example"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 404


# ---- Rolle / Aktivieren / Deaktivieren ---------------------------------


def test_set_role_changes_platform_role(admin_client: TestClient, member_person_id: str) -> None:
    r = admin_client.post(
        f"/api/admin/persons/{member_person_id}/set-role",
        json={"role": "admin"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 200
    assert r.json()["platform_role"] == "admin"


def test_disable_blocks_login(admin_client: TestClient, member_person_id: str, app) -> None:
    r = admin_client.post(
        f"/api/admin/persons/{member_person_id}/disable",
        headers=_csrf(admin_client),
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is False
    fresh = TestClient(app)
    login = fresh.post(
        "/api/auth/login",
        json={"email": "member@test.example", "password": "M3mberP4ssword!"},
    )
    assert login.status_code == 401
    fresh.close()


def test_enable_unblocks_login(admin_client: TestClient, member_person_id: str, app) -> None:
    admin_client.post(
        f"/api/admin/persons/{member_person_id}/disable",
        headers=_csrf(admin_client),
    )
    r = admin_client.post(
        f"/api/admin/persons/{member_person_id}/enable",
        headers=_csrf(admin_client),
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is True


# ---- Passwort-Reset -----------------------------------------------------


def test_reset_password_returns_new_initial_password(
    admin_client: TestClient, member_person_id: str, app
) -> None:
    r = admin_client.post(
        f"/api/admin/persons/{member_person_id}/reset-password",
        json={},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 200
    body = r.json()
    assert "initial_password" in body and len(body["initial_password"]) >= 10
    # Alter Login schlägt fehl, neuer geht.
    fresh = TestClient(app)
    old = fresh.post(
        "/api/auth/login",
        json={"email": "member@test.example", "password": "M3mberP4ssword!"},
    )
    assert old.status_code == 401
    new = fresh.post(
        "/api/auth/login",
        json={"email": "member@test.example", "password": body["initial_password"]},
    )
    assert new.status_code == 200
    assert new.json()["must_change_password"] is True
    fresh.close()


def test_reset_password_requires_admin(member_client: TestClient, member_person_id: str) -> None:
    r = member_client.post(
        f"/api/admin/persons/{member_person_id}/reset-password",
        json={},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403
