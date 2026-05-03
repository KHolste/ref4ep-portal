"""AuditLogger."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ref4ep.domain.models import AuditLog
from ref4ep.services.audit_logger import AuditLogger


def test_log_creates_entry_with_actor_and_request_context(seeded_session: Session) -> None:
    audit = AuditLogger(
        seeded_session,
        actor_person_id="abc-123",
        client_ip="127.0.0.1",
        request_id="req-1",
    )
    entry = audit.log(
        "document.create",
        entity_type="document",
        entity_id="doc-uuid-1",
        after={"title": "T"},
    )
    assert entry.actor_person_id == "abc-123"
    assert entry.actor_label is None
    assert entry.action == "document.create"
    assert entry.entity_type == "document"
    assert entry.entity_id == "doc-uuid-1"
    assert entry.client_ip == "127.0.0.1"
    assert entry.request_id == "req-1"
    payload = json.loads(entry.details)
    assert payload == {"before": None, "after": {"title": "T"}}


def test_log_without_actor_uses_system_label(seeded_session: Session) -> None:
    audit = AuditLogger(seeded_session)
    entry = audit.log(
        "system.event", entity_type="system", entity_id="00000000-0000-0000-0000-000000000000"
    )
    assert entry.actor_person_id is None
    assert entry.actor_label == "system"


def test_log_serializes_datetime_via_default_str(seeded_session: Session) -> None:
    audit = AuditLogger(seeded_session, actor_label="cli-admin")
    when = datetime(2026, 5, 3, 12, 0, 0, tzinfo=UTC)
    audit.log(
        "document.update",
        entity_type="document",
        entity_id="doc-uuid-2",
        before={"updated_at": when},
        after={"updated_at": when},
    )
    seeded_session.commit()
    entry = seeded_session.query(AuditLog).filter_by(action="document.update").one()
    payload = json.loads(entry.details)
    assert "2026-05-03" in payload["before"]["updated_at"]
