"""API: Zentrale Aufgaben-Übersicht (Block 0018).

Deckt Permission-Matrix für GET ``/api/actions`` und PATCH
``/api/actions/{id}`` ab — insbesondere den
„responsible_person == self"-Pfad und die Selbst-Service-Felder
``status``/``note``/``due_date``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.domain.models import AuditLog, MeetingAction, Person
from ref4ep.services.meeting_service import MeetingService
from ref4ep.services.workpackage_service import WorkpackageService


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def _wp_id(session: Session, code: str) -> str:
    wp = WorkpackageService(session).get_by_code(code)
    assert wp is not None
    return wp.id


def _admin_meeting_with_action(
    session: Session,
    *,
    wp_codes: list[str],
    responsible_id: str | None = None,
    due: date | None = None,
    status: str = "open",
    text: str = "Aufgabe X",
) -> tuple[str, str]:
    """Legt direkt über den Service ein Meeting + Aufgabe an. Liefert
    ``(meeting_id, action_id)``. Damit umgehen wir die Cookie-Kollision
    zwischen ``admin_client`` und ``member_client``."""
    admin = session.query(Person).filter_by(email="admin@test.example").one()
    wp_ids = [_wp_id(session, c) for c in wp_codes]
    service = MeetingService(session, role=admin.platform_role, person_id=admin.id)
    meeting = service.create_meeting(
        title="Aufgaben-Quelle",
        starts_at=datetime.now(tz=UTC),
        workpackage_ids=wp_ids,
    )
    action = service.create_action(
        meeting_id=meeting.id,
        text=text,
        responsible_person_id=responsible_id,
        due_date=due,
        status=status,
        workpackage_id=wp_ids[0] if wp_ids else None,
    )
    session.commit()
    return meeting.id, action.id


# ---- Auth + Listings ---------------------------------------------------


def test_anonymous_cannot_list_actions(client: TestClient) -> None:
    client.cookies.clear()
    r = client.get("/api/actions")
    assert r.status_code == 401


def test_member_sees_empty_list_initially(member_client: TestClient) -> None:
    r = member_client.get("/api/actions")
    assert r.status_code == 200
    assert r.json() == []


def test_member_can_list_actions_assigned_to_them(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    _admin_meeting_with_action(seeded_session, wp_codes=[], responsible_id=member_person_id)
    r = member_client.get("/api/actions")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["responsible_person"]["id"] == member_person_id
    assert body[0]["meeting_title"] == "Aufgaben-Quelle"


def test_mine_filter_excludes_other_actions(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    _admin_meeting_with_action(
        seeded_session, wp_codes=[], responsible_id=member_person_id, text="Mein"
    )
    _admin_meeting_with_action(
        seeded_session, wp_codes=[], responsible_id=admin_person_id, text="Anderer"
    )
    r = member_client.get("/api/actions?mine=true")
    body = r.json()
    assert len(body) == 1
    assert body[0]["text"] == "Mein"


def test_overdue_filter_returns_only_past_open_actions(
    admin_client: TestClient, seeded_session: Session, admin_person_id: str
) -> None:
    yesterday = date.today() - timedelta(days=1)
    tomorrow = date.today() + timedelta(days=1)
    _admin_meeting_with_action(
        seeded_session,
        wp_codes=[],
        responsible_id=admin_person_id,
        due=yesterday,
        text="Überfällig",
    )
    _admin_meeting_with_action(
        seeded_session,
        wp_codes=[],
        responsible_id=admin_person_id,
        due=tomorrow,
        text="Zukunft",
    )
    _admin_meeting_with_action(
        seeded_session,
        wp_codes=[],
        responsible_id=admin_person_id,
        due=yesterday,
        status="done",
        text="Done",
    )
    r = admin_client.get("/api/actions?overdue=true")
    body = r.json()
    texts = {a["text"] for a in body}
    assert texts == {"Überfällig"}


def test_status_filter_validates(admin_client: TestClient) -> None:
    r = admin_client.get("/api/actions?status=ungueltig")
    assert r.status_code == 422


def test_status_filter_returns_only_matching(
    admin_client: TestClient, seeded_session: Session, admin_person_id: str
) -> None:
    _admin_meeting_with_action(
        seeded_session,
        wp_codes=[],
        responsible_id=admin_person_id,
        status="in_progress",
        text="Läuft",
    )
    _admin_meeting_with_action(
        seeded_session, wp_codes=[], responsible_id=admin_person_id, status="open", text="Offen"
    )
    r = admin_client.get("/api/actions?status=in_progress")
    body = r.json()
    assert {a["text"] for a in body} == {"Läuft"}


def test_workpackage_filter_returns_only_that_wp(
    admin_client: TestClient, seeded_session: Session, admin_person_id: str
) -> None:
    _admin_meeting_with_action(
        seeded_session,
        wp_codes=["WP3"],
        responsible_id=admin_person_id,
        text="WP3-Task",
    )
    _admin_meeting_with_action(
        seeded_session,
        wp_codes=["WP4.1"],
        responsible_id=admin_person_id,
        text="WP4.1-Task",
    )
    r = admin_client.get("/api/actions?workpackage=WP3")
    body = r.json()
    assert {a["text"] for a in body} == {"WP3-Task"}


def test_unknown_workpackage_returns_empty_list(admin_client: TestClient) -> None:
    r = admin_client.get("/api/actions?workpackage=WPXX")
    assert r.status_code == 200
    assert r.json() == []


def test_response_does_not_leak_password_hash_or_internal_note(
    admin_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    _admin_meeting_with_action(seeded_session, wp_codes=[], responsible_id=member_person_id)
    r = admin_client.get("/api/actions")
    body_text = r.text.lower()
    assert "password" not in body_text
    assert "hash" not in body_text


# ---- can_edit-Flag ----------------------------------------------------


def test_can_edit_true_for_admin_on_any_action(
    admin_client: TestClient, seeded_session: Session, admin_person_id: str
) -> None:
    _admin_meeting_with_action(seeded_session, wp_codes=[], responsible_id=admin_person_id)
    r = admin_client.get("/api/actions")
    assert all(a["can_edit"] is True for a in r.json())


def test_can_edit_true_for_responsible_self(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    _admin_meeting_with_action(seeded_session, wp_codes=[], responsible_id=member_person_id)
    r = member_client.get("/api/actions")
    body = r.json()
    assert body[0]["can_edit"] is True


def test_can_edit_false_for_unrelated_member(
    member_client: TestClient, seeded_session: Session, admin_person_id: str
) -> None:
    """Member ohne Verantwortung und ohne WP-Lead-Rolle: kein Edit."""
    _admin_meeting_with_action(
        seeded_session,
        wp_codes=[],
        responsible_id=admin_person_id,
        text="Nicht meine Aufgabe",
    )
    r = member_client.get("/api/actions")
    body = r.json()
    assert len(body) == 1
    assert body[0]["can_edit"] is False


def test_can_edit_true_for_wp_lead_of_meeting_wp(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
    admin_person_id: str,
) -> None:
    """Lead in WP3 sieht Aufgaben aus WP3-Meetings als bearbeitbar."""
    _admin_meeting_with_action(
        seeded_session,
        wp_codes=["WP3"],
        responsible_id=admin_person_id,
        text="WP3-Task",
    )
    r = member_client.get("/api/actions")
    body = [a for a in r.json() if a["text"] == "WP3-Task"]
    assert body
    assert body[0]["can_edit"] is True


# ---- PATCH /api/actions/{id} ------------------------------------------


def test_patch_requires_csrf(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    _, action_id = _admin_meeting_with_action(
        seeded_session, wp_codes=[], responsible_id=member_person_id
    )
    r = member_client.patch(f"/api/actions/{action_id}", json={"status": "in_progress"})
    assert r.status_code == 403


def test_responsible_can_patch_status_note_and_due(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    _, action_id = _admin_meeting_with_action(
        seeded_session, wp_codes=[], responsible_id=member_person_id
    )
    r = member_client.patch(
        f"/api/actions/{action_id}",
        json={
            "status": "in_progress",
            "note": "läuft im Labor",
            "due_date": "2026-12-15",
        },
        headers=_csrf(member_client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "in_progress"
    assert body["note"] == "läuft im Labor"
    assert body["due_date"] == "2026-12-15"


def test_responsible_cannot_change_text_or_responsible(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    """Der Responsible-Self-Pfad ignoriert text/responsible/wp und
    ändert nichts daran — die Felder sind nicht erlaubt, nicht
    fehlerhaft."""
    _, action_id = _admin_meeting_with_action(
        seeded_session, wp_codes=[], responsible_id=member_person_id, text="Original"
    )
    r = member_client.patch(
        f"/api/actions/{action_id}",
        json={
            "text": "Manipuliert",
            "responsible_person_id": admin_person_id,
            "status": "in_progress",
        },
        headers=_csrf(member_client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # status wurde übernommen, text und responsible nicht.
    assert body["status"] == "in_progress"
    assert body["text"] == "Original"
    assert body["responsible_person"]["id"] == member_person_id


def test_unrelated_member_cannot_patch(
    member_client: TestClient,
    seeded_session: Session,
    admin_person_id: str,
) -> None:
    _, action_id = _admin_meeting_with_action(
        seeded_session, wp_codes=[], responsible_id=admin_person_id
    )
    r = member_client.patch(
        f"/api/actions/{action_id}",
        json={"status": "done"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_admin_can_patch_any_field(
    admin_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    _, action_id = _admin_meeting_with_action(
        seeded_session, wp_codes=[], responsible_id=member_person_id, text="Alt"
    )
    r = admin_client.patch(
        f"/api/actions/{action_id}",
        json={
            "text": "Neu durch Admin",
            "responsible_person_id": admin_person_id,
            "status": "in_progress",
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["text"] == "Neu durch Admin"
    assert body["responsible_person"]["id"] == admin_person_id


def test_wp_lead_can_patch_action_in_own_wp(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
    admin_person_id: str,
) -> None:
    _, action_id = _admin_meeting_with_action(
        seeded_session, wp_codes=["WP3"], responsible_id=admin_person_id, text="X"
    )
    r = member_client.patch(
        f"/api/actions/{action_id}",
        json={"text": "Lead-Edit", "status": "in_progress"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["text"] == "Lead-Edit"
    assert body["status"] == "in_progress"


def test_invalid_status_returns_422(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    _, action_id = _admin_meeting_with_action(
        seeded_session, wp_codes=[], responsible_id=member_person_id
    )
    r = member_client.patch(
        f"/api/actions/{action_id}",
        json={"status": "ungueltig"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 422


def test_unknown_action_returns_404(admin_client: TestClient) -> None:
    r = admin_client.patch(
        "/api/actions/00000000-0000-0000-0000-000000000000",
        json={"status": "in_progress"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 404


def test_audit_records_action_update(
    member_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
    admin_person_id: str,
) -> None:
    _, action_id = _admin_meeting_with_action(
        seeded_session, wp_codes=[], responsible_id=member_person_id
    )
    member_client.patch(
        f"/api/actions/{action_id}",
        json={"status": "in_progress"},
        headers=_csrf(member_client),
    )
    seeded_session.expire_all()
    entries = seeded_session.query(AuditLog).filter_by(action="meeting.action.update").all()
    assert entries, "Audit-Eintrag meeting.action.update fehlt"


@pytest.mark.parametrize(
    "params",
    [
        {"mine": "true"},
        {"overdue": "true"},
        {"status": "open"},
        {"workpackage": "WP3"},
    ],
)
def test_filter_combinations_return_200(admin_client: TestClient, params: dict[str, str]) -> None:
    r = admin_client.get("/api/actions", params=params)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ---- Sorting ----------------------------------------------------------


def test_sorting_puts_due_dates_first_then_null(
    admin_client: TestClient, seeded_session: Session, admin_person_id: str
) -> None:
    """NULL-due_date wandert nach hinten (CASE-Sortierung)."""
    later = date.today() + timedelta(days=10)
    earlier = date.today() + timedelta(days=2)
    _admin_meeting_with_action(
        seeded_session, wp_codes=[], responsible_id=admin_person_id, text="Spät", due=later
    )
    _admin_meeting_with_action(
        seeded_session, wp_codes=[], responsible_id=admin_person_id, text="Früh", due=earlier
    )
    _admin_meeting_with_action(
        seeded_session, wp_codes=[], responsible_id=admin_person_id, text="Ohne Datum", due=None
    )
    r = admin_client.get("/api/actions")
    body = r.json()
    assert [a["text"] for a in body] == ["Früh", "Spät", "Ohne Datum"]


def test_action_seeded_db_is_clean(seeded_session: Session) -> None:
    assert seeded_session.query(MeetingAction).count() == 0
