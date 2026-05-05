"""API: Aktivitäts-Feed (Block 0018).

``GET /api/activity/recent`` mappt Audit-Einträge in eine kompakte
Stream-Sicht. Die Tests prüfen Auth, Filter, Limit und vor allem
Sicherheit (keine Klartext-Beschluss-/Aufgabentexte, keine Passwörter
oder Notes im Stream).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.domain.models import Person
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.meeting_service import MeetingService


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def _admin_meeting(session: Session, *, with_decision_text: str = "Geheimer Beschluss") -> str:
    """Legt Meeting + Beschluss + Aufgabe direkt über den Service an —
    inklusive Audit-Logger, damit Audit-Einträge entstehen."""
    admin = session.query(Person).filter_by(email="admin@test.example").one()
    audit = AuditLogger(session, actor_person_id=admin.id)
    service = MeetingService(session, role=admin.platform_role, person_id=admin.id, audit=audit)
    meeting = service.create_meeting(
        title="Audit-Quelle",
        starts_at=datetime.now(tz=UTC),
        workpackage_ids=[],
    )
    service.create_decision(meeting_id=meeting.id, text=with_decision_text, status="open")
    service.create_action(meeting_id=meeting.id, text="Vertrauliche Aufgabe", status="open")
    session.commit()
    return meeting.id


# ---- Auth + Defaults --------------------------------------------------


def test_anonymous_cannot_get_activity(client: TestClient) -> None:
    client.cookies.clear()
    r = client.get("/api/activity/recent")
    assert r.status_code == 401


def test_member_can_get_activity_returns_list(member_client: TestClient) -> None:
    r = member_client.get("/api/activity/recent")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_recent_returns_meeting_create_audit(
    admin_client: TestClient, seeded_session: Session
) -> None:
    _admin_meeting(seeded_session)
    r = admin_client.get("/api/activity/recent")
    body = r.json()
    titles = [e["title"] for e in body]
    assert any("Meeting: Audit-Quelle" in t for t in titles)


def test_meeting_create_entry_has_link_to_meeting(
    admin_client: TestClient, seeded_session: Session
) -> None:
    meeting_id = _admin_meeting(seeded_session)
    r = admin_client.get("/api/activity/recent")
    matching = [e for e in r.json() if e.get("link") == f"/portal/meetings/{meeting_id}"]
    assert matching


def test_recent_omits_decision_plaintext(admin_client: TestClient, seeded_session: Session) -> None:
    """Sicherheit: Klartext der Beschlüsse darf nicht im Stream stehen."""
    _admin_meeting(seeded_session, with_decision_text="STRENG GEHEIM 12345")
    r = admin_client.get("/api/activity/recent")
    body_text = r.text
    assert "STRENG GEHEIM 12345" not in body_text


def test_recent_omits_action_plaintext(admin_client: TestClient, seeded_session: Session) -> None:
    _admin_meeting(seeded_session)
    r = admin_client.get("/api/activity/recent")
    assert "Vertrauliche Aufgabe" not in r.text


def test_recent_does_not_leak_passwords_or_hashes(
    admin_client: TestClient, seeded_session: Session
) -> None:
    _admin_meeting(seeded_session)
    r = admin_client.get("/api/activity/recent")
    body_text = r.text.lower()
    assert "password_hash" not in body_text
    assert "argon2" not in body_text


# ---- since-Filter -----------------------------------------------------


def test_since_filter_excludes_older_entries(
    admin_client: TestClient, seeded_session: Session
) -> None:
    _admin_meeting(seeded_session)
    # Setze ``since`` in die Zukunft → Stream muss leer sein.
    future = (datetime.now(tz=UTC) + timedelta(days=1)).isoformat()
    r = admin_client.get("/api/activity/recent", params={"since": future})
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_since_default_is_14_day_lookback(
    admin_client: TestClient, seeded_session: Session
) -> None:
    """Ohne ``since`` greift der 14-Tage-Default — frische Einträge sind drin."""
    _admin_meeting(seeded_session)
    r = admin_client.get("/api/activity/recent")
    assert r.status_code == 200
    assert any("Audit-Quelle" in e["title"] for e in r.json())


# ---- limit-Validierung -----------------------------------------------


def test_limit_validation_rejects_zero(member_client: TestClient) -> None:
    r = member_client.get("/api/activity/recent?limit=0")
    assert r.status_code == 422


def test_limit_validation_rejects_too_high(member_client: TestClient) -> None:
    r = member_client.get("/api/activity/recent?limit=999")
    assert r.status_code == 422


def test_limit_one_returns_at_most_one(admin_client: TestClient, seeded_session: Session) -> None:
    _admin_meeting(seeded_session)
    r = admin_client.get("/api/activity/recent?limit=1")
    assert r.status_code == 200
    assert len(r.json()) <= 1


# ---- Mapping ----------------------------------------------------------


def test_entry_has_required_fields(admin_client: TestClient, seeded_session: Session) -> None:
    _admin_meeting(seeded_session)
    r = admin_client.get("/api/activity/recent?limit=5")
    for entry in r.json():
        assert "timestamp" in entry
        assert "type" in entry
        assert "title" in entry
        assert entry["type"] in {
            "document",
            "meeting",
            "action",
            "decision",
            "workpackage",
            "team",
            "milestone",
            "partner",
            "other",
        }


def test_entry_actor_is_display_name_for_known_actor(
    admin_client: TestClient, seeded_session: Session
) -> None:
    _admin_meeting(seeded_session)
    r = admin_client.get("/api/activity/recent")
    actors = {e.get("actor") for e in r.json()}
    assert any(a == "Test admin" for a in actors)


def test_entries_sorted_descending_by_timestamp(
    admin_client: TestClient, seeded_session: Session
) -> None:
    _admin_meeting(seeded_session)
    r = admin_client.get("/api/activity/recent")
    timestamps = [e["timestamp"] for e in r.json()]
    assert timestamps == sorted(timestamps, reverse=True)


def test_password_change_self_action_is_suppressed(
    admin_client: TestClient, seeded_session: Session
) -> None:
    """``person.change_password`` ist explizit unterdrückt."""
    admin = seeded_session.query(Person).filter_by(email="admin@test.example").one()
    audit = AuditLogger(seeded_session, actor_person_id=admin.id)
    audit.log(
        "person.change_password",
        entity_type="person",
        entity_id=admin.id,
        after={"changed": True},
    )
    seeded_session.commit()
    r = admin_client.get("/api/activity/recent")
    assert all(e["title"] != "person.change_password" for e in r.json())
