"""API: Partner-Detail + WP-Lead-Edit (Migration 0006)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.services.partner_service import PartnerService
from ref4ep.services.workpackage_service import WorkpackageService
from tests.conftest import MEMBER_EMAIL


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def _jlu_id(session: Session) -> str:
    p = PartnerService(session).get_by_short_name("JLU")
    assert p is not None
    return p.id


# ---- GET /api/partners/{id} --------------------------------------------


def test_anonymous_cannot_get_partner(client: TestClient, seeded_session: Session) -> None:
    pid = _jlu_id(seeded_session)
    client.cookies.clear()
    r = client.get(f"/api/partners/{pid}")
    assert r.status_code == 401


def test_member_can_view_but_internal_note_hidden(
    member_client: TestClient, seeded_session: Session
) -> None:
    pid = _jlu_id(seeded_session)
    PartnerService(seeded_session, role="admin").update(pid, internal_note="geheim")
    seeded_session.commit()
    r = member_client.get(f"/api/partners/{pid}")
    assert r.status_code == 200
    body = r.json()
    assert body["short_name"] == "JLU"
    assert body["internal_note"] is None
    assert body["can_edit"] is False


def test_admin_sees_internal_note(admin_client: TestClient, seeded_session: Session) -> None:
    pid = _jlu_id(seeded_session)
    PartnerService(seeded_session, role="admin").update(pid, internal_note="nur Admin")
    seeded_session.commit()
    r = admin_client.get(f"/api/partners/{pid}")
    assert r.status_code == 200
    body = r.json()
    assert body["internal_note"] == "nur Admin"
    assert body["can_edit"] is True


def test_get_unknown_partner_returns_404(admin_client: TestClient) -> None:
    r = admin_client.get("/api/partners/99999999-9999-9999-9999-999999999999")
    assert r.status_code == 404


# ---- PATCH /api/partners/{id} ------------------------------------------


def test_anonymous_cannot_patch(client: TestClient, seeded_session: Session) -> None:
    pid = _jlu_id(seeded_session)
    client.cookies.clear()
    r = client.patch(f"/api/partners/{pid}", json={"name": "Hack"})
    # 401 (kein Login) oder 403 (CSRF-Dep läuft als Erste) — beides ist
    # eine ordnungsgemäße Ablehnung. Wichtig ist: kein 200.
    assert r.status_code in (401, 403)


def test_member_without_lead_role_gets_403(
    member_client: TestClient, member_in_wp3, seeded_session: Session
) -> None:
    # WP3 wird im Seed nicht von JLU geführt — also fehlt der lead-Bezug.
    # Wir patchen JLU; Membership ist nur "wp_member" → erwartet 403.
    pid = _jlu_id(seeded_session)
    r = member_client.patch(
        f"/api/partners/{pid}",
        json={"name": "Hack"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_wp_lead_can_patch_own_partner_via_api(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
) -> None:
    # member als wp_lead in einem JLU-geführten WP eintragen.
    pid = _jlu_id(seeded_session)
    wp_service = WorkpackageService(seeded_session, role="admin", person_id="fixture")
    leading = next(wp for wp in wp_service.list_workpackages() if wp.lead_partner_id == pid)
    wp_service.add_membership(member_person_id, leading.id, "wp_lead")
    seeded_session.commit()
    r = member_client.patch(
        f"/api/partners/{pid}",
        json={
            "name": "JLU Gießen — neu",
            "general_email": "info@jlu.example",
            "primary_contact_name": "C. Lead",
        },
        headers=_csrf(member_client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "JLU Gießen — neu"
    assert body["general_email"] == "info@jlu.example"
    assert body["primary_contact_name"] == "C. Lead"
    assert body["can_edit"] is True
    # internal_note bleibt für non-admin verborgen.
    assert body["internal_note"] is None


def test_wp_lead_patch_ignores_admin_only_fields(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
) -> None:
    pid = _jlu_id(seeded_session)
    wp_service = WorkpackageService(seeded_session, role="admin", person_id="fixture")
    leading = next(wp for wp in wp_service.list_workpackages() if wp.lead_partner_id == pid)
    wp_service.add_membership(member_person_id, leading.id, "wp_lead")
    seeded_session.commit()
    # short_name/country sind im PartnerPatchRequest gar nicht vorhanden →
    # Pydantic ignoriert unbekannte Felder *nicht* — sondern fehlertolerant
    # via model_dump(exclude_unset=True). Der Service-Whitelist filtert
    # Restfelder zusätzlich. Wir prüfen also ein erlaubtes + ein ignoriertes.
    r = member_client.patch(
        f"/api/partners/{pid}",
        json={"name": "ok", "is_active": False, "internal_note": "x"},
        headers=_csrf(member_client),
    )
    # is_active/internal_note sind nicht in PartnerPatchRequest → Pydantic
    # akzeptiert das Body weiter; falls Pydantic bei Extra fehlschlägt, ist
    # das auch ein Schutz. Wir akzeptieren beide gültigen Antworten:
    assert r.status_code in (200, 422), r.text
    # Egal, ob 200 oder 422: die Verwaltungsfelder dürfen nicht gesetzt sein.
    seeded_session.expire_all()
    p = PartnerService(seeded_session).get_by_id(pid)
    assert p is not None
    assert p.is_active is True
    assert p.internal_note is None


def test_admin_patch_via_partners_route_writes_all_fields(
    admin_client: TestClient,
    seeded_session: Session,
) -> None:
    pid = _jlu_id(seeded_session)
    r = admin_client.patch(
        f"/api/partners/{pid}",
        json={
            "name": "JLU neu",
            "general_email": "admin@jlu.example",
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "JLU neu"
    assert body["general_email"] == "admin@jlu.example"


def test_patch_invalid_email_returns_422(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
) -> None:
    pid = _jlu_id(seeded_session)
    wp_service = WorkpackageService(seeded_session, role="admin", person_id="fixture")
    leading = next(wp for wp in wp_service.list_workpackages() if wp.lead_partner_id == pid)
    wp_service.add_membership(member_person_id, leading.id, "wp_lead")
    seeded_session.commit()
    r = member_client.patch(
        f"/api/partners/{pid}",
        json={"general_email": "kein_at_zeichen"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 422


def test_patch_requires_csrf(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
) -> None:
    pid = _jlu_id(seeded_session)
    wp_service = WorkpackageService(seeded_session, role="admin", person_id="fixture")
    leading = next(wp for wp in wp_service.list_workpackages() if wp.lead_partner_id == pid)
    wp_service.add_membership(member_person_id, leading.id, "wp_lead")
    seeded_session.commit()
    r = member_client.patch(f"/api/partners/{pid}", json={"name": "ohne CSRF"})
    assert r.status_code == 403


# ---- Admin-Liste enthält neue Felder -----------------------------------


def test_admin_list_partners_returns_extended_fields(
    admin_client: TestClient, seeded_session: Session
) -> None:
    pid = _jlu_id(seeded_session)
    PartnerService(seeded_session, role="admin").update(
        pid,
        general_email="info@jlu.example",
        is_active=True,
        internal_note="Hinweis",
    )
    seeded_session.commit()
    r = admin_client.get("/api/admin/partners")
    assert r.status_code == 200
    jlu = next(p for p in r.json() if p["short_name"] == "JLU")
    assert jlu["general_email"] == "info@jlu.example"
    assert jlu["is_active"] is True
    assert jlu["internal_note"] == "Hinweis"


def test_me_response_now_includes_partner_id(member_client: TestClient) -> None:
    r = member_client.get("/api/me")
    assert r.status_code == 200
    body = r.json()
    assert body["person"]["email"] == MEMBER_EMAIL
    assert "id" in body["person"]["partner"]
    assert body["person"]["partner"]["id"]
