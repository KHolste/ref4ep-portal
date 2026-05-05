"""API: Meeting-/Protokollregister (Block 0015).

Deckt Permission-Matrix (anonym, Member, WP-Lead, Admin), Cancel,
Beschluss/Aufgabe-CRUD, Document-Link, Teilnehmende und Audit ab.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.domain.models import AuditLog, Meeting, MeetingAction, MeetingDecision
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.workpackage_service import WorkpackageService


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


@pytest.fixture
def jlu_partner_id(seeded_session: Session) -> str:
    p = PartnerService(seeded_session, role="admin").get_by_short_name("JLU")
    assert p is not None
    return p.id


def _wp_id(seeded_session: Session, code: str) -> str:
    wp = WorkpackageService(seeded_session).get_by_code(code)
    assert wp is not None
    return wp.id


def _starts_at() -> str:
    return (datetime.now(tz=UTC) + timedelta(days=7)).isoformat()


# ---- LIST + GET --------------------------------------------------------


def test_anonymous_cannot_list(client: TestClient) -> None:
    client.cookies.clear()
    r = client.get("/api/meetings")
    assert r.status_code == 401


def test_member_can_list_meetings(member_client: TestClient) -> None:
    r = member_client.get("/api/meetings")
    assert r.status_code == 200
    assert r.json() == []


def test_admin_can_create_meeting_without_workpackage(
    admin_client: TestClient, seeded_session: Session
) -> None:
    r = admin_client.post(
        "/api/meetings",
        json={
            "title": "Konsortialtreffen Mai",
            "starts_at": _starts_at(),
            "format": "online",
            "category": "consortium",
            "workpackage_ids": [],
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Konsortialtreffen Mai"
    assert body["category"] == "consortium"
    assert body["workpackages"] == []
    assert body["can_edit"] is True


def test_admin_can_create_meeting_with_workpackage(
    admin_client: TestClient, seeded_session: Session
) -> None:
    wp = _wp_id(seeded_session, "WP3.1")
    r = admin_client.post(
        "/api/meetings",
        json={
            "title": "WP3.1 Kickoff",
            "starts_at": _starts_at(),
            "category": "workpackage",
            "workpackage_ids": [wp],
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    codes = [w["code"] for w in body["workpackages"]]
    assert codes == ["WP3.1"]


# ---- WP-Lead-Berechtigungen --------------------------------------------


def test_member_without_lead_cannot_create_meeting(
    member_client: TestClient, seeded_session: Session, member_in_wp3
) -> None:
    """member_in_wp3 → Member ist wp_member in WP3 (nicht lead)."""
    wp = _wp_id(seeded_session, "WP3")
    r = member_client.post(
        "/api/meetings",
        json={
            "title": "Versuch",
            "starts_at": _starts_at(),
            "workpackage_ids": [wp],
        },
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_wp_lead_can_create_meeting_with_own_wp(
    member_client: TestClient, seeded_session: Session, lead_in_wp3
) -> None:
    wp = _wp_id(seeded_session, "WP3")
    r = member_client.post(
        "/api/meetings",
        json={
            "title": "WP3-Jour-Fixe",
            "starts_at": _starts_at(),
            "category": "jour_fixe",
            "workpackage_ids": [wp],
        },
        headers=_csrf(member_client),
    )
    assert r.status_code == 201, r.text


def test_wp_lead_cannot_create_meeting_without_workpackage(
    member_client: TestClient, seeded_session: Session, lead_in_wp3
) -> None:
    """Konsortialtreffen ohne WP-Bezug bleiben Admin-only."""
    r = member_client.post(
        "/api/meetings",
        json={
            "title": "Lead möchte Konsortialtreffen",
            "starts_at": _starts_at(),
            "category": "consortium",
            "workpackage_ids": [],
        },
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_wp_lead_cannot_create_meeting_with_foreign_workpackage(
    member_client: TestClient, seeded_session: Session, lead_in_wp3
) -> None:
    """Lead in WP3 darf kein Meeting für WP4.1 (CAU-geleitet) anlegen."""
    foreign = _wp_id(seeded_session, "WP4.1")
    r = member_client.post(
        "/api/meetings",
        json={
            "title": "Übergriff",
            "starts_at": _starts_at(),
            "workpackage_ids": [foreign],
        },
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_wp_lead_cannot_create_meeting_with_mixed_workpackages(
    member_client: TestClient, seeded_session: Session, lead_in_wp3
) -> None:
    """Vereinfachte Regel: Lead darf nur reine eigene-WP-Meetings anlegen."""
    own = _wp_id(seeded_session, "WP3")
    foreign = _wp_id(seeded_session, "WP4.1")
    r = member_client.post(
        "/api/meetings",
        json={
            "title": "Gemischt",
            "starts_at": _starts_at(),
            "workpackage_ids": [own, foreign],
        },
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def _create_meeting_via_service(
    session: Session, *, wp_codes: list[str], title: str = "Initial"
) -> str:
    """Hilfsroutine: legt ein Meeting direkt über den Service an,
    ohne dass ``admin_client``+``member_client`` parallel im Test
    laufen müssen (sie teilen sich den Cookie-Speicher)."""
    from datetime import datetime

    from ref4ep.domain.models import Person
    from ref4ep.services.meeting_service import MeetingService

    admin = session.query(Person).filter_by(email="admin@test.example").one()
    wp_ids = [_wp_id(session, code) for code in wp_codes]
    meeting = MeetingService(session, role=admin.platform_role, person_id=admin.id).create_meeting(
        title=title,
        starts_at=datetime.now(tz=UTC),
        workpackage_ids=wp_ids,
    )
    session.commit()
    return meeting.id


def test_wp_lead_can_edit_own_meeting(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
    admin_person_id: str,
) -> None:
    meeting_id = _create_meeting_via_service(seeded_session, wp_codes=["WP3"])
    r = member_client.patch(
        f"/api/meetings/{meeting_id}",
        json={"title": "Lead-Edit", "status": "minutes_draft"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Lead-Edit"
    assert body["status"] == "minutes_draft"


def test_wp_lead_cannot_edit_foreign_meeting(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
    admin_person_id: str,
) -> None:
    meeting_id = _create_meeting_via_service(seeded_session, wp_codes=["WP4.1"], title="WP4.1")
    r = member_client.patch(
        f"/api/meetings/{meeting_id}",
        json={"title": "Hack"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


# ---- Cancel ------------------------------------------------------------


def test_admin_can_cancel_meeting(admin_client: TestClient, seeded_session: Session) -> None:
    created = admin_client.post(
        "/api/meetings",
        json={"title": "Absagen", "starts_at": _starts_at(), "workpackage_ids": []},
        headers=_csrf(admin_client),
    ).json()
    r = admin_client.post(
        f"/api/meetings/{created['id']}/cancel",
        headers=_csrf(admin_client),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_delete_meeting_route_is_admin_only_route_exists() -> None:
    """Block 0016: ``DELETE /api/meetings/{id}`` existiert jetzt
    (Admin-only, CSRF-geschützt). Vorher gab es keinen Hard-Delete.
    """
    from ref4ep.api.app import create_app
    from ref4ep.api.config import Settings

    app = create_app(
        settings=Settings(
            database_url="sqlite:///:memory:",
            session_secret="x" * 48,
            storage_dir="/tmp/x",
        )
    )
    delete_meeting = [
        r
        for r in app.routes
        if getattr(r, "path", "") == "/api/meetings/{meeting_id}"
        and "DELETE" in getattr(r, "methods", set())
    ]
    assert len(delete_meeting) == 1


# ---- Hard-Delete (Block 0016) -----------------------------------------


def test_anonymous_cannot_delete_meeting(
    client: TestClient, seeded_session: Session, admin_person_id: str
) -> None:
    meeting_id = _create_meeting_via_service(seeded_session, wp_codes=[])
    client.cookies.clear()
    r = client.delete(f"/api/meetings/{meeting_id}")
    assert r.status_code in (401, 403)


def test_member_cannot_delete_meeting(
    member_client: TestClient,
    seeded_session: Session,
    member_in_wp3,
    admin_person_id: str,
) -> None:
    meeting_id = _create_meeting_via_service(seeded_session, wp_codes=[])
    r = member_client.delete(f"/api/meetings/{meeting_id}", headers=_csrf(member_client))
    assert r.status_code == 403


def test_wp_lead_cannot_delete_meeting_even_if_own_wp(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
    admin_person_id: str,
) -> None:
    """WP-Lead darf Meetings *seines* WPs absagen, aber nicht hart löschen."""
    meeting_id = _create_meeting_via_service(seeded_session, wp_codes=["WP3"])
    r = member_client.delete(f"/api/meetings/{meeting_id}", headers=_csrf(member_client))
    assert r.status_code == 403


def test_admin_can_delete_meeting(admin_client: TestClient, seeded_session: Session) -> None:
    created = admin_client.post(
        "/api/meetings",
        json={"title": "Zum Löschen", "starts_at": _starts_at(), "workpackage_ids": []},
        headers=_csrf(admin_client),
    ).json()
    r = admin_client.delete(f"/api/meetings/{created['id']}", headers=_csrf(admin_client))
    assert r.status_code == 204
    # Nachfolgender GET liefert 404.
    r2 = admin_client.get(f"/api/meetings/{created['id']}")
    assert r2.status_code == 404


def test_delete_requires_csrf(admin_client: TestClient, seeded_session: Session) -> None:
    meeting_id = _create_meeting_via_service(seeded_session, wp_codes=[])
    r = admin_client.delete(f"/api/meetings/{meeting_id}")
    assert r.status_code == 403


def test_delete_unknown_meeting_returns_404(admin_client: TestClient) -> None:
    r = admin_client.delete(
        "/api/meetings/00000000-0000-0000-0000-000000000000",
        headers=_csrf(admin_client),
    )
    assert r.status_code == 404


def test_delete_cascades_links_but_keeps_documents_persons_workpackages(
    admin_client: TestClient, seeded_session: Session, member_person_id: str
) -> None:
    """Hard-Delete entfernt MeetingDocumentLink, MeetingAction etc. —
    aber nicht das verknüpfte Dokument, nicht Personen, nicht WPs."""
    from ref4ep.domain.models import (
        Document,
        MeetingAction,
        MeetingDecision,
        MeetingDocumentLink,
        MeetingParticipant,
        MeetingWorkpackage,
        Person,
        Workpackage,
    )
    from ref4ep.services.document_service import DocumentService
    from ref4ep.services.permissions import AuthContext

    # Dokument anlegen.
    admin = seeded_session.query(Person).filter_by(email="admin@test.example").one()
    auth = AuthContext(person_id=admin.id, email=admin.email, platform_role="admin", memberships=[])
    doc = DocumentService(seeded_session, auth=auth).create(
        workpackage_code="WP1.1",
        title="Test-Protokoll",
        document_type="report",
    )
    seeded_session.commit()

    # Meeting via API anlegen, mit WP3.1 + Beschluss + Aufgabe + Doc-Link + Teilnehmender.
    wp = WorkpackageService(seeded_session).get_by_code("WP3.1")
    assert wp is not None
    created = admin_client.post(
        "/api/meetings",
        json={
            "title": "Vollkomplex",
            "starts_at": _starts_at(),
            "workpackage_ids": [wp.id],
        },
        headers=_csrf(admin_client),
    ).json()
    mid = created["id"]
    admin_client.post(
        f"/api/meetings/{mid}/decisions",
        json={"text": "B"},
        headers=_csrf(admin_client),
    )
    admin_client.post(
        f"/api/meetings/{mid}/actions",
        json={"text": "A"},
        headers=_csrf(admin_client),
    )
    admin_client.post(
        f"/api/meetings/{mid}/participants",
        json={"person_id": member_person_id},
        headers=_csrf(admin_client),
    )
    admin_client.post(
        f"/api/meetings/{mid}/documents",
        json={"document_id": doc.id, "label": "minutes"},
        headers=_csrf(admin_client),
    )

    # Hard-Delete.
    r = admin_client.delete(f"/api/meetings/{mid}", headers=_csrf(admin_client))
    assert r.status_code == 204

    seeded_session.expire_all()
    # Alle abhängigen Datensätze sind weg …
    assert seeded_session.query(MeetingWorkpackage).filter_by(meeting_id=mid).count() == 0
    assert seeded_session.query(MeetingParticipant).filter_by(meeting_id=mid).count() == 0
    assert seeded_session.query(MeetingDecision).filter_by(meeting_id=mid).count() == 0
    assert seeded_session.query(MeetingAction).filter_by(meeting_id=mid).count() == 0
    assert seeded_session.query(MeetingDocumentLink).filter_by(meeting_id=mid).count() == 0
    # … aber Dokument, Personen, Workpackage bleiben erhalten.
    assert seeded_session.get(Document, doc.id) is not None
    assert seeded_session.get(Person, member_person_id) is not None
    assert seeded_session.get(Workpackage, wp.id) is not None


def test_audit_records_meeting_delete(admin_client: TestClient, seeded_session: Session) -> None:
    created = admin_client.post(
        "/api/meetings",
        json={"title": "Mit Audit", "starts_at": _starts_at(), "workpackage_ids": []},
        headers=_csrf(admin_client),
    ).json()
    admin_client.delete(f"/api/meetings/{created['id']}", headers=_csrf(admin_client))
    seeded_session.expire_all()
    entries = seeded_session.query(AuditLog).filter_by(action="meeting.delete").all()
    assert entries, "Audit-Eintrag meeting.delete fehlt"
    last = entries[-1]
    details = last.details or ""
    assert "Mit Audit" in details
    assert "meeting_id" in details


# ---- Decisions ---------------------------------------------------------


def test_admin_can_add_and_update_decision(
    admin_client: TestClient, seeded_session: Session
) -> None:
    wp = _wp_id(seeded_session, "WP3.1")
    meeting = admin_client.post(
        "/api/meetings",
        json={"title": "M", "starts_at": _starts_at(), "workpackage_ids": [wp]},
        headers=_csrf(admin_client),
    ).json()
    add = admin_client.post(
        f"/api/meetings/{meeting['id']}/decisions",
        json={
            "text": "Beschluss A",
            "workpackage_id": wp,
            "status": "open",
        },
        headers=_csrf(admin_client),
    )
    assert add.status_code == 201, add.text
    decision_id = add.json()["id"]
    upd = admin_client.patch(
        f"/api/meeting-decisions/{decision_id}",
        json={"status": "valid"},
        headers=_csrf(admin_client),
    )
    assert upd.status_code == 200
    assert upd.json()["status"] == "valid"


def test_invalid_decision_status_returns_422(
    admin_client: TestClient, seeded_session: Session
) -> None:
    meeting = admin_client.post(
        "/api/meetings",
        json={"title": "M", "starts_at": _starts_at(), "workpackage_ids": []},
        headers=_csrf(admin_client),
    ).json()
    r = admin_client.post(
        f"/api/meetings/{meeting['id']}/decisions",
        json={"text": "X", "status": "erledigt"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 422


# ---- Actions -----------------------------------------------------------


def test_admin_can_add_and_update_action(admin_client: TestClient, seeded_session: Session) -> None:
    meeting = admin_client.post(
        "/api/meetings",
        json={"title": "M", "starts_at": _starts_at(), "workpackage_ids": []},
        headers=_csrf(admin_client),
    ).json()
    add = admin_client.post(
        f"/api/meetings/{meeting['id']}/actions",
        json={"text": "Aufgabe X", "status": "open"},
        headers=_csrf(admin_client),
    )
    assert add.status_code == 201, add.text
    action_id = add.json()["id"]
    upd = admin_client.patch(
        f"/api/meeting-actions/{action_id}",
        json={"status": "in_progress", "due_date": "2026-12-01"},
        headers=_csrf(admin_client),
    )
    assert upd.status_code == 200
    body = upd.json()
    assert body["status"] == "in_progress"
    assert body["due_date"] == "2026-12-01"


# ---- Document-Link ------------------------------------------------------


def test_admin_can_link_and_unlink_document(
    admin_client: TestClient, seeded_session: Session
) -> None:
    # Test braucht ein vorhandenes Document.
    from ref4ep.services.document_service import DocumentService

    wp = _wp_id(seeded_session, "WP1.1")
    from ref4ep.domain.models import Person
    from ref4ep.services.permissions import AuthContext

    admin = seeded_session.query(Person).filter_by(email="admin@test.example").one()
    auth = AuthContext(person_id=admin.id, email=admin.email, platform_role="admin", memberships=[])
    doc_service = DocumentService(seeded_session, auth=auth)
    doc = doc_service.create(
        workpackage_code="WP1.1",
        title="Test-Protokoll",
        document_type="report",
    )
    seeded_session.commit()
    _ = wp
    meeting = admin_client.post(
        "/api/meetings",
        json={"title": "M", "starts_at": _starts_at(), "workpackage_ids": [wp]},
        headers=_csrf(admin_client),
    ).json()
    link = admin_client.post(
        f"/api/meetings/{meeting['id']}/documents",
        json={"document_id": doc.id, "label": "minutes"},
        headers=_csrf(admin_client),
    )
    assert link.status_code == 201, link.text
    docs = link.json()["documents"]
    assert len(docs) == 1
    assert docs[0]["label"] == "minutes"
    # Entknüpfen
    unlink = admin_client.delete(
        f"/api/meetings/{meeting['id']}/documents/{doc.id}",
        headers=_csrf(admin_client),
    )
    assert unlink.status_code == 204
    # Dokument selbst bleibt erhalten.
    from ref4ep.domain.models import Document

    persisted = seeded_session.get(Document, doc.id)
    assert persisted is not None and persisted.is_deleted is False


# ---- Participants ------------------------------------------------------


def test_admin_can_add_and_remove_participant(
    admin_client: TestClient, seeded_session: Session, member_person_id: str
) -> None:
    meeting = admin_client.post(
        "/api/meetings",
        json={"title": "M", "starts_at": _starts_at(), "workpackage_ids": []},
        headers=_csrf(admin_client),
    ).json()
    r = admin_client.post(
        f"/api/meetings/{meeting['id']}/participants",
        json={"person_id": member_person_id},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 201
    ids = [p["id"] for p in r.json()["participants"]]
    assert member_person_id in ids
    r2 = admin_client.delete(
        f"/api/meetings/{meeting['id']}/participants/{member_person_id}",
        headers=_csrf(admin_client),
    )
    assert r2.status_code == 204
    detail = admin_client.get(f"/api/meetings/{meeting['id']}").json()
    assert all(p["id"] != member_person_id for p in detail["participants"])


# ---- Audit -------------------------------------------------------------


def test_audit_writes_meeting_create(admin_client: TestClient, seeded_session: Session) -> None:
    admin_client.post(
        "/api/meetings",
        json={"title": "A", "starts_at": _starts_at(), "workpackage_ids": []},
        headers=_csrf(admin_client),
    )
    seeded_session.expire_all()
    entries = seeded_session.query(AuditLog).filter_by(action="meeting.create").all()
    assert entries, "Audit-Eintrag meeting.create fehlt"


def test_audit_writes_decision_and_action(
    admin_client: TestClient, seeded_session: Session
) -> None:
    meeting = admin_client.post(
        "/api/meetings",
        json={"title": "B", "starts_at": _starts_at(), "workpackage_ids": []},
        headers=_csrf(admin_client),
    ).json()
    admin_client.post(
        f"/api/meetings/{meeting['id']}/decisions",
        json={"text": "B1"},
        headers=_csrf(admin_client),
    )
    admin_client.post(
        f"/api/meetings/{meeting['id']}/actions",
        json={"text": "A1"},
        headers=_csrf(admin_client),
    )
    seeded_session.expire_all()
    actions = {e.action for e in seeded_session.query(AuditLog).all()}
    assert "meeting.decision.create" in actions
    assert "meeting.action.create" in actions


# ---- Validierung -------------------------------------------------------


def test_meeting_invalid_status_returns_422(admin_client: TestClient) -> None:
    r = admin_client.post(
        "/api/meetings",
        json={
            "title": "X",
            "starts_at": _starts_at(),
            "status": "ungueltig",
            "workpackage_ids": [],
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 422


def test_meeting_unknown_workpackage_returns_404(admin_client: TestClient) -> None:
    r = admin_client.post(
        "/api/meetings",
        json={
            "title": "X",
            "starts_at": _starts_at(),
            "workpackage_ids": ["00000000-0000-0000-0000-000000000000"],
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 404


def test_csrf_required_on_create(admin_client: TestClient) -> None:
    r = admin_client.post(
        "/api/meetings",
        json={"title": "Ohne CSRF", "starts_at": _starts_at(), "workpackage_ids": []},
    )
    assert r.status_code == 403


# ---- Sicherheits-Smoke -------------------------------------------------


def test_seeded_meeting_count_consistent(admin_client: TestClient, seeded_session: Session) -> None:
    """Nichts in der Seed-Datenbank sollte Meetings/Decisions/Actions enthalten."""
    assert seeded_session.query(Meeting).count() == 0
    assert seeded_session.query(MeetingDecision).count() == 0
    assert seeded_session.query(MeetingAction).count() == 0


# ---- Block 0015 / Bugfix: WP-Round-Trip --------------------------------


def test_meeting_create_uses_id_from_workpackage_listing(
    admin_client: TestClient, seeded_session: Session
) -> None:
    """Reproduziert den Praxistest-Bug: Anlegen eines Meetings mit
    WP1.1, indem die ID aus dem Listen-Response wirklich akzeptiert
    wird. Vorher fehlte ``id`` im Schema, das Frontend übermittelte
    den Anzeigetext, und der Server lehnte mit ``LookupError`` ab."""
    listing = admin_client.get("/api/workpackages").json()
    wp11 = next(w for w in listing if w["code"] == "WP1.1")
    r = admin_client.post(
        "/api/meetings",
        json={
            "title": "WP1.1-Treffen",
            "starts_at": _starts_at(),
            "category": "workpackage",
            "workpackage_ids": [wp11["id"]],
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert [w["code"] for w in body["workpackages"]] == ["WP1.1"]


def test_meeting_create_rejects_composite_label_as_workpackage_id(
    admin_client: TestClient, seeded_session: Session
) -> None:
    """Symptom des Bugs: das Frontend hatte den Anzeigetext geschickt.
    Der Server muss das mit 404 ablehnen — keine schleichende Akzeptanz."""
    r = admin_client.post(
        "/api/meetings",
        json={
            "title": "Falscher Wert",
            "starts_at": _starts_at(),
            "workpackage_ids": ["WP1.1 — Projektmanagement"],
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 404
    assert "WP1.1" in r.json()["detail"]["error"]["message"]
