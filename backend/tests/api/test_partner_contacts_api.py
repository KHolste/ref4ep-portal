"""API: /api/partners/{id}/contacts + /api/partner-contacts/{id} (Block 0007)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.services.partner_contact_service import PartnerContactService
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.workpackage_service import WorkpackageService


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def _jlu(session: Session) -> str:
    p = PartnerService(session, role="admin").get_by_short_name("JLU")
    assert p is not None
    return p.id


def _other(session: Session, jlu_id: str) -> str:
    return next(
        p for p in PartnerService(session, role="admin").list_partners() if p.id != jlu_id
    ).id


def _make_lead(session: Session, person_id: str, partner_id: str) -> None:
    wps = WorkpackageService(session, role="admin", person_id="fixture")
    leading = next(wp for wp in wps.list_workpackages() if wp.lead_partner_id == partner_id)
    wps.add_membership(person_id, leading.id, "wp_lead")
    session.commit()


# ---- Funktions-Auswahlliste -------------------------------------------


def test_function_list_returns_inclusive_terms(member_client: TestClient) -> None:
    r = member_client.get("/api/partner-contacts/functions")
    assert r.status_code == 200
    items = r.json()
    assert "Projektleitung" in items
    assert "Professorin/Professor" in items
    assert "Doktorandin/Doktorand" in items


# ---- LIST ---------------------------------------------------------------


def test_anonymous_cannot_list(client: TestClient, seeded_session: Session) -> None:
    pid = _jlu(seeded_session)
    client.cookies.clear()
    r = client.get(f"/api/partners/{pid}/contacts")
    assert r.status_code == 401


def test_member_sees_only_active_visible_no_internal_note(
    member_client: TestClient, seeded_session: Session
) -> None:
    pid = _jlu(seeded_session)
    svc = PartnerContactService(seeded_session, role="admin", person_id="admin-id")
    svc.create(partner_id=pid, name="aktiv-intern", internal_note="geheim")
    deact = svc.create(partner_id=pid, name="deaktiviert")
    svc.deactivate(deact.id)
    seeded_session.commit()
    r = member_client.get(f"/api/partners/{pid}/contacts")
    assert r.status_code == 200
    body = r.json()
    names = {c["name"] for c in body}
    assert "aktiv-intern" in names
    assert "deaktiviert" not in names
    for c in body:
        assert c["internal_note"] is None  # Member darf interne Notiz nicht sehen


def test_admin_sees_internal_note(admin_client: TestClient, seeded_session: Session) -> None:
    pid = _jlu(seeded_session)
    PartnerContactService(seeded_session, role="admin", person_id="admin-id").create(
        partner_id=pid, name="A", internal_note="nur Admin"
    )
    seeded_session.commit()
    r = admin_client.get(f"/api/partners/{pid}/contacts")
    assert r.status_code == 200
    a = next(c for c in r.json() if c["name"] == "A")
    assert a["internal_note"] == "nur Admin"


def test_admin_can_request_inactive_via_query(
    admin_client: TestClient, seeded_session: Session
) -> None:
    pid = _jlu(seeded_session)
    svc = PartnerContactService(seeded_session, role="admin", person_id="admin-id")
    deact = svc.create(partner_id=pid, name="archiviert")
    svc.deactivate(deact.id)
    seeded_session.commit()
    r = admin_client.get(f"/api/partners/{pid}/contacts?include_inactive=true")
    assert r.status_code == 200
    assert any(c["name"] == "archiviert" for c in r.json())


# ---- CREATE -------------------------------------------------------------


def test_admin_can_create(admin_client: TestClient, seeded_session: Session) -> None:
    pid = _jlu(seeded_session)
    r = admin_client.post(
        f"/api/partners/{pid}/contacts",
        json={
            "name": "Dr. Test",
            "title_or_degree": "Dr.",
            "email": "test@jlu.example",
            "function": "Projektleitung",
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Dr. Test"
    assert body["function"] == "Projektleitung"
    assert body["is_active"] is True
    assert body["visibility"] == "internal"


def test_wp_lead_can_create_for_own_partner(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
) -> None:
    pid = _jlu(seeded_session)
    _make_lead(seeded_session, member_person_id, pid)
    r = member_client.post(
        f"/api/partners/{pid}/contacts",
        json={"name": "Lead-erstellt"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 201, r.text


def test_wp_lead_cannot_create_for_foreign_partner(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
) -> None:
    pid = _jlu(seeded_session)
    _make_lead(seeded_session, member_person_id, pid)
    other = _other(seeded_session, pid)
    r = member_client.post(
        f"/api/partners/{other}/contacts",
        json={"name": "X"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_member_without_lead_cannot_create(
    member_client: TestClient, seeded_session: Session, member_in_wp3
) -> None:
    pid = _jlu(seeded_session)
    r = member_client.post(
        f"/api/partners/{pid}/contacts",
        json={"name": "X"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_invalid_email_returns_422(admin_client: TestClient, seeded_session: Session) -> None:
    pid = _jlu(seeded_session)
    r = admin_client.post(
        f"/api/partners/{pid}/contacts",
        json={"name": "X", "email": "kein_at"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 422


def test_invalid_function_returns_422(admin_client: TestClient, seeded_session: Session) -> None:
    pid = _jlu(seeded_session)
    r = admin_client.post(
        f"/api/partners/{pid}/contacts",
        json={"name": "X", "function": "freie_eingabe"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 422


def test_unknown_partner_returns_404(admin_client: TestClient) -> None:
    r = admin_client.post(
        "/api/partners/00000000-0000-0000-0000-000000000000/contacts",
        json={"name": "X"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 404


# ---- PATCH --------------------------------------------------------------


def test_admin_can_patch(admin_client: TestClient, seeded_session: Session) -> None:
    pid = _jlu(seeded_session)
    c = PartnerContactService(seeded_session, role="admin", person_id="admin-id").create(
        partner_id=pid, name="X"
    )
    seeded_session.commit()
    r = admin_client.patch(
        f"/api/partner-contacts/{c.id}",
        json={"phone": "+49 30 7", "function": "Postdoc"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["phone"] == "+49 30 7"
    assert body["function"] == "Postdoc"


def test_wp_lead_cannot_patch_foreign_contact(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
) -> None:
    jlu = _jlu(seeded_session)
    other = _other(seeded_session, jlu)
    foreign = PartnerContactService(seeded_session, role="admin", person_id="admin-id").create(
        partner_id=other, name="Fremd"
    )
    seeded_session.commit()
    _make_lead(seeded_session, member_person_id, jlu)
    r = member_client.patch(
        f"/api/partner-contacts/{foreign.id}",
        json={"name": "übergriff"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_wp_lead_internal_note_silently_ignored_via_api(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
) -> None:
    pid = _jlu(seeded_session)
    _make_lead(seeded_session, member_person_id, pid)
    create_r = member_client.post(
        f"/api/partners/{pid}/contacts",
        json={"name": "X"},
        headers=_csrf(member_client),
    )
    assert create_r.status_code == 201
    cid = create_r.json()["id"]
    r = member_client.patch(
        f"/api/partner-contacts/{cid}",
        json={"name": "X-neu", "internal_note": "versucht"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 200
    seeded_session.expire_all()
    contact = PartnerContactService(seeded_session, role="admin", person_id="admin-id").get(cid)
    assert contact is not None
    assert contact.name == "X-neu"
    assert contact.internal_note is None


# ---- DELETE / REACTIVATE -----------------------------------------------


def test_delete_deactivates(admin_client: TestClient, seeded_session: Session) -> None:
    pid = _jlu(seeded_session)
    c = PartnerContactService(seeded_session, role="admin", person_id="admin-id").create(
        partner_id=pid, name="X"
    )
    seeded_session.commit()
    r = admin_client.delete(f"/api/partner-contacts/{c.id}", headers=_csrf(admin_client))
    assert r.status_code == 204
    seeded_session.expire_all()
    again = PartnerContactService(seeded_session, role="admin", person_id="admin-id").get(c.id)
    assert again is not None
    assert again.is_active is False


def test_reactivate(admin_client: TestClient, seeded_session: Session) -> None:
    pid = _jlu(seeded_session)
    svc = PartnerContactService(seeded_session, role="admin", person_id="admin-id")
    c = svc.create(partner_id=pid, name="X")
    svc.deactivate(c.id)
    seeded_session.commit()
    r = admin_client.post(
        f"/api/partner-contacts/{c.id}/reactivate",
        json={},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is True


def test_member_without_lead_cannot_delete(
    member_client: TestClient,
    seeded_session: Session,
    member_in_wp3,
) -> None:
    pid = _jlu(seeded_session)
    c = PartnerContactService(seeded_session, role="admin", person_id="admin-id").create(
        partner_id=pid, name="X"
    )
    seeded_session.commit()
    r = member_client.delete(f"/api/partner-contacts/{c.id}", headers=_csrf(member_client))
    assert r.status_code == 403
