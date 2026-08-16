"""API: /api/contacts — projektweites Kontaktverzeichnis (Block 0053).

Kernzusage des Blocks: jede eingeloggte Person sieht die Kontaktdaten
**aller** Einrichtungen und Arbeitspakete — nicht nur die der eigenen
Zugehörigkeit. Die Tests prüfen genau das, plus die beiden Grenzen,
die weiterhin gelten (``internal_note`` und deaktivierte Einträge sind
Admin-Sache).
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.services.partner_contact_service import PartnerContactService
from ref4ep.services.partner_service import PartnerService
from tests.conftest import MEMBER_EMAIL


def _jlu(session: Session) -> str:
    p = PartnerService(session, role="admin").get_by_short_name("JLU")
    assert p is not None
    return p.id


def _other_partner(session: Session, jlu_id: str) -> str:
    """Ein Partner, mit dem die Member-Fixture nichts zu tun hat."""
    return next(
        p for p in PartnerService(session, role="admin").list_partners() if p.id != jlu_id
    ).id


def _contacts(session: Session) -> PartnerContactService:
    return PartnerContactService(session, role="admin", person_id="admin-id")


def _by_name(body: list[dict], name: str) -> dict:
    return next(entry for entry in body if entry["name"] == name)


# ---- Zugriff ------------------------------------------------------------


def test_anonymous_cannot_list_directory(client: TestClient) -> None:
    client.cookies.clear()
    r = client.get("/api/contacts")
    assert r.status_code == 401


def test_member_sees_contacts_of_foreign_partner(
    member_client: TestClient, seeded_session: Session
) -> None:
    """Kern des Blocks: fremde Einrichtung, keine WP-Verbindung — trotzdem sichtbar."""
    other = _other_partner(seeded_session, _jlu(seeded_session))
    _contacts(seeded_session).create(
        partner_id=other,
        name="Fremde Ansprechperson",
        email="fremd@example.org",
        phone="+49 641 99-0",
        function="Administration",
    )
    seeded_session.commit()

    r = member_client.get("/api/contacts")
    assert r.status_code == 200
    entry = _by_name(r.json(), "Fremde Ansprechperson")
    assert entry["partner"]["id"] == other
    assert entry["email"] == "fremd@example.org"
    assert entry["phone"] == "+49 641 99-0"
    assert entry["sources"] == ["contact"]


def test_directory_covers_every_partner(member_client: TestClient, seeded_session: Session) -> None:
    """Alle nicht gelöschten Partner mit Personen tauchen im Verzeichnis auf."""
    jlu = _jlu(seeded_session)
    other = _other_partner(seeded_session, jlu)
    svc = _contacts(seeded_session)
    svc.create(partner_id=jlu, name="JLU-Kontakt")
    svc.create(partner_id=other, name="Partner-Kontakt")
    seeded_session.commit()

    body = member_client.get("/api/contacts").json()
    partner_ids = {entry["partner"]["id"] for entry in body}
    assert {jlu, other} <= partner_ids


def test_entries_are_sorted_by_partner_then_name(
    member_client: TestClient, seeded_session: Session
) -> None:
    body = member_client.get("/api/contacts").json()
    keys = [(e["partner"]["short_name"].lower(), e["name"].lower()) for e in body]
    assert keys == sorted(keys)


# ---- Admin-Grenzen ------------------------------------------------------


def test_member_never_sees_internal_note(
    member_client: TestClient, seeded_session: Session
) -> None:
    _contacts(seeded_session).create(
        partner_id=_jlu(seeded_session), name="Mit Notiz", internal_note="geheim"
    )
    seeded_session.commit()

    body = member_client.get("/api/contacts").json()
    assert _by_name(body, "Mit Notiz")["internal_note"] is None


def test_admin_sees_internal_note(admin_client: TestClient, seeded_session: Session) -> None:
    _contacts(seeded_session).create(
        partner_id=_jlu(seeded_session), name="Mit Notiz", internal_note="nur Admin"
    )
    seeded_session.commit()

    body = admin_client.get("/api/contacts").json()
    assert _by_name(body, "Mit Notiz")["internal_note"] == "nur Admin"


def test_member_cannot_force_inactive_entries(
    member_client: TestClient, seeded_session: Session
) -> None:
    """``include_inactive`` wirkt für Member nicht — still ignoriert, keine 403."""
    svc = _contacts(seeded_session)
    deactivated = svc.create(partner_id=_jlu(seeded_session), name="Deaktivierter Kontakt")
    svc.deactivate(deactivated.id)
    seeded_session.commit()

    r = member_client.get("/api/contacts?include_inactive=true")
    assert r.status_code == 200
    assert "Deaktivierter Kontakt" not in {e["name"] for e in r.json()}


def test_admin_can_include_inactive_entries(
    admin_client: TestClient, seeded_session: Session
) -> None:
    svc = _contacts(seeded_session)
    deactivated = svc.create(partner_id=_jlu(seeded_session), name="Deaktivierter Kontakt")
    svc.deactivate(deactivated.id)
    seeded_session.commit()

    assert "Deaktivierter Kontakt" not in {
        e["name"] for e in admin_client.get("/api/contacts").json()
    }
    body = admin_client.get("/api/contacts?include_inactive=true").json()
    entry = _by_name(body, "Deaktivierter Kontakt")
    assert entry["is_active"] is False


# ---- Zusammenführung Kontakt × Portal-Account ---------------------------


def test_portal_accounts_appear_without_contact_record(
    member_client: TestClient, seeded_session: Session
) -> None:
    body = member_client.get("/api/contacts").json()
    entry = next(e for e in body if e["email"] == MEMBER_EMAIL)
    assert entry["sources"] == ["person"]
    assert entry["is_portal_user"] is True
    assert entry["person_id"]


def test_contact_and_account_are_merged_on_matching_email(
    member_client: TestClient, seeded_session: Session, member_in_wp3: str
) -> None:
    """Gleiche E-Mail + gleicher Partner → ein Eintrag mit beiden Quellen."""
    _contacts(seeded_session).create(
        partner_id=_jlu(seeded_session),
        name="Doppelte Person",
        email=MEMBER_EMAIL.upper(),  # Case-insensitiver Abgleich
        phone="+49 641 99-1",
    )
    seeded_session.commit()

    body = member_client.get("/api/contacts").json()
    merged = [e for e in body if (e["email"] or "").lower() == MEMBER_EMAIL]
    assert len(merged) == 1, "Kontakt und Portal-Konto dürfen nicht doppelt erscheinen"
    entry = merged[0]
    assert entry["sources"] == ["contact", "person"]
    # Gepflegte Kontaktdaten gewinnen, der Account steuert Konto + WPs bei.
    assert entry["phone"] == "+49 641 99-1"
    assert entry["is_portal_user"] is True
    assert entry["contact_id"] and entry["person_id"]
    assert "WP3" in {wp["code"] for wp in entry["workpackages"]}


def test_same_email_at_other_partner_is_not_merged(
    member_client: TestClient, seeded_session: Session
) -> None:
    """Gleiche E-Mail bei anderer Einrichtung deutet auf einen Datenfehler —
    beide Einträge bleiben sichtbar statt still verschmolzen zu werden."""
    other = _other_partner(seeded_session, _jlu(seeded_session))
    _contacts(seeded_session).create(partner_id=other, name="Namensgleich", email=MEMBER_EMAIL)
    seeded_session.commit()

    body = member_client.get("/api/contacts").json()
    same_email = [e for e in body if (e["email"] or "").lower() == MEMBER_EMAIL]
    assert len(same_email) == 2
    assert {tuple(e["sources"]) for e in same_email} == {("contact",), ("person",)}


def test_workpackage_memberships_are_exposed(
    member_client: TestClient, seeded_session: Session, member_in_wp3: str
) -> None:
    body = member_client.get("/api/contacts").json()
    entry = next(e for e in body if e["email"] == MEMBER_EMAIL)
    wp3 = next(wp for wp in entry["workpackages"] if wp["code"] == "WP3")
    assert wp3["wp_role"] == "wp_member"
    assert wp3["title"]
