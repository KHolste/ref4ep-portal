"""API: /api/lead/persons (Block 0013).

Lead-Funktion „Mein Team": eingeloggte WP-Leads sehen und legen
Personen ihres eigenen Partners an. Server erzwingt Partner und
Plattformrolle — Request darf hier nichts injizieren.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.domain.models import AuditLog, Person
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.person_service import PersonService


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


# ---- LIST -------------------------------------------------------------


def test_anonymous_cannot_list(client: TestClient, seeded_session: Session) -> None:
    client.cookies.clear()
    r = client.get("/api/lead/persons")
    assert r.status_code == 401


def test_member_without_lead_role_gets_403(
    member_client: TestClient, member_in_wp3, seeded_session: Session
) -> None:
    # member_in_wp3 macht den Member zum wp_member (nicht lead).
    r = member_client.get("/api/lead/persons")
    assert r.status_code == 403


def test_wp_lead_lists_only_own_partner_persons(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
) -> None:
    # ``lead_in_wp3`` macht den Member-Account zum wp_lead in WP3.
    # Außerdem legen wir eine Person beim TUD-Partner an, die in der
    # Liste NICHT auftauchen darf.
    tud = PartnerService(seeded_session, role="admin").get_by_short_name("TUD")
    assert tud is not None
    PersonService(seeded_session, role="admin", person_id="fixture").create(
        email="tud-fremder@test.example",
        display_name="TUD Fremder",
        partner_id=tud.id,
        password="X" * 12,
    )
    seeded_session.commit()

    r = member_client.get("/api/lead/persons")
    assert r.status_code == 200
    body = r.json()
    emails = {p["email"] for p in body}
    # Eigene JLU-Person ist da.
    assert "member@test.example" in emails
    # Fremder Partner taucht NICHT auf.
    assert "tud-fremder@test.example" not in emails
    # Kein password_hash in der Antwort.
    for p in body:
        assert "password_hash" not in p


def test_admin_can_list_via_lead_endpoint(
    admin_client: TestClient, seeded_session: Session
) -> None:
    """Admin darf die Lead-Sicht mitnutzen — sieht Personen des eigenen Partners."""
    r = admin_client.get("/api/lead/persons")
    assert r.status_code == 200


# ---- CREATE -----------------------------------------------------------


def test_anonymous_cannot_create(client: TestClient) -> None:
    client.cookies.clear()
    r = client.post(
        "/api/lead/persons",
        json={"email": "x@y", "display_name": "X"},
    )
    assert r.status_code in (401, 403)


def test_member_without_lead_role_cannot_create(
    member_client: TestClient, member_in_wp3, seeded_session: Session
) -> None:
    r = member_client.post(
        "/api/lead/persons",
        json={"email": "x@y", "display_name": "X"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_wp_lead_creates_person_for_own_partner(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
) -> None:
    r = member_client.post(
        "/api/lead/persons",
        json={"email": "neu-jlu@test.example", "display_name": "Neu JLU"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    # Server hat die Plattformrolle = member, Partner = JLU gesetzt.
    assert body["person"]["email"] == "neu-jlu@test.example"
    assert body["person"]["must_change_password"] is True
    assert body["person"]["is_active"] is True
    # password_hash darf NICHT im Antwortobjekt sein.
    assert "password_hash" not in body["person"]
    # Initialpasswort ist einmalig im Response, mind. 10 Zeichen.
    pw = body["initial_password"]
    assert isinstance(pw, str) and len(pw) >= 10
    # Login mit dem ausgegebenen Passwort funktioniert.
    fresh = TestClient(member_client.app)
    login = fresh.post(
        "/api/auth/login",
        json={"email": "neu-jlu@test.example", "password": pw},
    )
    assert login.status_code == 200
    fresh.close()
    # In der DB ist der Partner = JLU (gleicher wie der Lead).
    new_person = seeded_session.query(Person).filter_by(email="neu-jlu@test.example").one()
    jlu = PartnerService(seeded_session, role="admin").get_by_short_name("JLU")
    assert jlu is not None
    assert new_person.partner_id == jlu.id
    assert new_person.platform_role == "member"


def test_lead_create_request_cannot_inject_partner_or_role(
    member_client: TestClient, seeded_session: Session, lead_in_wp3
) -> None:
    """Felder ``partner_id`` und ``platform_role`` ignoriert der Server (Pydantic ignoriert Extras),
    Person landet trotzdem beim eigenen Partner und als ``member``."""
    tud = PartnerService(seeded_session, role="admin").get_by_short_name("TUD")
    assert tud is not None
    r = member_client.post(
        "/api/lead/persons",
        json={
            "email": "trick@test.example",
            "display_name": "Trick",
            "partner_id": tud.id,
            "platform_role": "admin",
        },
        headers=_csrf(member_client),
    )
    assert r.status_code == 201, r.text
    person = seeded_session.query(Person).filter_by(email="trick@test.example").one()
    jlu = PartnerService(seeded_session, role="admin").get_by_short_name("JLU")
    assert jlu is not None
    assert person.partner_id == jlu.id
    assert person.platform_role == "member"


def test_audit_records_create_by_wp_lead_without_password(
    member_client: TestClient, seeded_session: Session, lead_in_wp3
) -> None:
    r = member_client.post(
        "/api/lead/persons",
        json={"email": "audited@test.example", "display_name": "Audited"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 201
    initial_pw = r.json()["initial_password"]
    seeded_session.expire_all()
    entries = seeded_session.query(AuditLog).filter_by(action="person.create_by_wp_lead").all()
    assert entries, "Audit-Eintrag person.create_by_wp_lead fehlt"
    for entry in entries:
        details = entry.details or ""
        # Konkretes Klartextpasswort darf im Audit nicht erscheinen.
        assert initial_pw not in details
        # Auch kein password_hash.
        assert "password_hash" not in details


def test_create_requires_csrf(
    member_client: TestClient, seeded_session: Session, lead_in_wp3
) -> None:
    r = member_client.post(
        "/api/lead/persons",
        json={"email": "ohnecsrf@test.example", "display_name": "Ohne CSRF"},
    )
    assert r.status_code == 403


def test_create_short_password_returns_422(
    member_client: TestClient, seeded_session: Session, lead_in_wp3
) -> None:
    r = member_client.post(
        "/api/lead/persons",
        json={
            "email": "short@test.example",
            "display_name": "Short",
            "initial_password": "kurz",
        },
        headers=_csrf(member_client),
    )
    assert r.status_code == 422
