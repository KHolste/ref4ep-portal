"""API: Partnerleitungs-Rechte für Lead-/Partner-/Kontakt-Routen
(Block 0045).

Geprüft wird:
- Lead-Routen-Eingang öffnet sich für Partnerleitung.
- Partnerleitung darf Personen des eigenen Partners listen und anlegen.
- Neue Person hat hart ``platform_role=member`` und ``partner_id`` =
  Partner der Partnerleitung.
- PATCH /api/partners/{id} (WP-Lead-Schiene) erlaubt jetzt auch
  Partnerleitung, aber nur für den eigenen Partner.
- Partnerleitung kann Kontakte des eigenen Partners pflegen, fremde
  nicht.
- WP-Lead-Verhalten bleibt unverändert (Regression).
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.domain.models import Person
from ref4ep.services.partner_role_service import PartnerRoleService
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.person_service import PersonService

MEMBER_EMAIL = "member@test.example"
MEMBER_PASSWORD = "M3mberP4ssword!"


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def _login(client: TestClient, email: str, password: str) -> None:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text


def _ensure_admin(session: Session) -> Person:
    admin = session.query(Person).filter_by(email="admin@test.example").first()
    if admin is None:
        partner = PartnerService(session).get_by_short_name("JLU")
        admin = PersonService(session, role="admin").create(
            email="admin@test.example",
            display_name="Admin",
            partner_id=partner.id,
            password="StrongPw1!",
            platform_role="admin",
        )
        admin.must_change_password = False
        session.commit()
    return admin


def _make_partner_lead_person(session: Session, partner_short: str) -> Person:
    """Legt eine Person an, die zu ``partner_short`` gehört und für
    ``partner_short`` als Projektleitung markiert ist. Loggt sich als
    Admin-Service ein."""
    admin = _ensure_admin(session)
    partner = PartnerService(session).get_by_short_name(partner_short)
    assert partner is not None
    person = session.query(Person).filter_by(email=MEMBER_EMAIL).first()
    if person is None:
        person = PersonService(session, role="admin").create(
            email=MEMBER_EMAIL,
            display_name="Projektleitung Test",
            partner_id=partner.id,
            password=MEMBER_PASSWORD,
            platform_role="member",
        )
        person.must_change_password = False
        session.commit()
    PartnerRoleService(session, role="admin").add_partner_role(
        person_id=person.id,
        partner_id=partner.id,
        actor_person_id=admin.id,
    )
    session.commit()
    return person


# ---- Lead-Routen-Eingang ---------------------------------------------------


def test_partner_lead_can_enter_lead_persons(client: TestClient, seeded_session: Session) -> None:
    _make_partner_lead_person(seeded_session, "JLU")
    _login(client, MEMBER_EMAIL, MEMBER_PASSWORD)
    r = client.get("/api/lead/persons")
    assert r.status_code == 200
    # Mindestens die Projektleitung selbst muss in der Liste auftauchen.
    emails = {p["email"] for p in r.json()}
    assert MEMBER_EMAIL in emails


def test_partner_lead_can_create_person_for_own_partner(
    client: TestClient, seeded_session: Session
) -> None:
    _make_partner_lead_person(seeded_session, "JLU")
    _login(client, MEMBER_EMAIL, MEMBER_PASSWORD)
    r = client.post(
        "/api/lead/persons",
        json={"email": "neu@test.example", "display_name": "Neue Person"},
        headers=_csrf(client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    created = seeded_session.query(Person).filter_by(email="neu@test.example").one()
    # Plattformrolle ist hart member; Partner ist der eigene.
    assert created.platform_role == "member"
    jlu = PartnerService(seeded_session).get_by_short_name("JLU")
    assert created.partner_id == jlu.id
    # Initialpasswort wird zurückgegeben, nicht ins Audit:
    assert body["initial_password"]


def test_partner_lead_cannot_set_admin_role(client: TestClient, seeded_session: Session) -> None:
    """Auch bei manipuliertem Payload bleibt Plattformrolle ``member``
    (das Schema kennt kein Rollen-Feld; Service erzwingt zusätzlich)."""
    _make_partner_lead_person(seeded_session, "JLU")
    _login(client, MEMBER_EMAIL, MEMBER_PASSWORD)
    r = client.post(
        "/api/lead/persons",
        json={
            "email": "hack@test.example",
            "display_name": "Hack",
            "platform_role": "admin",
        },
        headers=_csrf(client),
    )
    assert r.status_code == 201, r.text
    created = seeded_session.query(Person).filter_by(email="hack@test.example").one()
    assert created.platform_role == "member"


def test_partner_lead_lead_persons_only_own_partner(
    client: TestClient, seeded_session: Session
) -> None:
    """Personen anderer Partner dürfen nicht in der Lead-Personenliste
    auftauchen — Filter ist ``Person.partner_id == actor.partner_id``."""
    _make_partner_lead_person(seeded_session, "JLU")
    # Eine Person eines fremden Partners anlegen:
    other_partner = (
        PartnerService(seeded_session).get_by_short_name("INFLPR")
        # INFLPR ist im Seed; falls nicht, nimm den ersten anderen Partner.
    )
    if other_partner is None:
        partners = PartnerService(seeded_session).list_partners()
        other_partner = next(p for p in partners if p.short_name != "JLU")
    foreign = PersonService(seeded_session, role="admin").create(
        email="foreign@test.example",
        display_name="Foreign",
        partner_id=other_partner.id,
        password="StrongPw1!",
        platform_role="member",
    )
    foreign.must_change_password = False
    seeded_session.commit()

    _login(client, MEMBER_EMAIL, MEMBER_PASSWORD)
    r = client.get("/api/lead/persons")
    emails = {p["email"] for p in r.json()}
    assert "foreign@test.example" not in emails


def test_member_without_role_cannot_enter_lead(client: TestClient, seeded_session: Session) -> None:
    _ensure_admin(seeded_session)
    partner = PartnerService(seeded_session).get_by_short_name("JLU")
    p = PersonService(seeded_session, role="admin").create(
        email="plain@test.example",
        display_name="Plain",
        partner_id=partner.id,
        password=MEMBER_PASSWORD,
        platform_role="member",
    )
    p.must_change_password = False
    seeded_session.commit()
    _login(client, "plain@test.example", MEMBER_PASSWORD)
    r = client.get("/api/lead/persons")
    assert r.status_code == 403


# ---- PATCH /api/partners/{id} ----------------------------------------------


def test_partner_lead_can_patch_own_partner_via_wp_lead_route(
    client: TestClient, seeded_session: Session
) -> None:
    _make_partner_lead_person(seeded_session, "JLU")
    jlu = PartnerService(seeded_session).get_by_short_name("JLU")
    _login(client, MEMBER_EMAIL, MEMBER_PASSWORD)
    r = client.patch(
        f"/api/partners/{jlu.id}",
        json={"website": "https://jlu.example/new"},
        headers=_csrf(client),
    )
    assert r.status_code == 200, r.text
    assert r.json()["website"] == "https://jlu.example/new"


def test_partner_lead_cannot_patch_foreign_partner(
    client: TestClient, seeded_session: Session
) -> None:
    _make_partner_lead_person(seeded_session, "JLU")
    partners = PartnerService(seeded_session).list_partners()
    other = next(p for p in partners if p.short_name != "JLU")
    _login(client, MEMBER_EMAIL, MEMBER_PASSWORD)
    r = client.patch(
        f"/api/partners/{other.id}",
        json={"website": "https://hack.example"},
        headers=_csrf(client),
    )
    assert r.status_code == 403


# ---- Partnerkontakte --------------------------------------------------------


def test_partner_lead_can_manage_own_partner_contacts(
    client: TestClient, seeded_session: Session
) -> None:
    _make_partner_lead_person(seeded_session, "JLU")
    jlu = PartnerService(seeded_session).get_by_short_name("JLU")
    _login(client, MEMBER_EMAIL, MEMBER_PASSWORD)
    r = client.post(
        f"/api/partners/{jlu.id}/contacts",
        json={"name": "Neuer Kontakt"},
        headers=_csrf(client),
    )
    assert r.status_code == 201, r.text


def test_partner_lead_cannot_manage_foreign_partner_contacts(
    client: TestClient, seeded_session: Session
) -> None:
    _make_partner_lead_person(seeded_session, "JLU")
    partners = PartnerService(seeded_session).list_partners()
    other = next(p for p in partners if p.short_name != "JLU")
    _login(client, MEMBER_EMAIL, MEMBER_PASSWORD)
    r = client.post(
        f"/api/partners/{other.id}/contacts",
        json={"name": "Hack"},
        headers=_csrf(client),
    )
    assert r.status_code == 403
