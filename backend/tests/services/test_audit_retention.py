"""Block 0079: IP-Adressen im Änderungsprotokoll werden nach der Frist
entfernt; der Protokolleintrag selbst bleibt."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ref4ep.api.app import create_app
from ref4ep.api.config import Settings
from ref4ep.domain.models import AuditLog
from ref4ep.services.audit_retention import purge_old_client_ips, run_ip_retention

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


def _entry(session: Session, *, age_days: int, ip: str | None = "203.0.113.7") -> str:
    entry = AuditLog(
        actor_label="test",
        action="person.create",
        entity_type="person",
        entity_id="00000000-0000-0000-0000-000000000000",
        client_ip=ip,
        created_at=NOW - timedelta(days=age_days),
    )
    session.add(entry)
    session.flush()
    return entry.id


def test_old_ips_are_removed_and_recent_ones_kept(session: Session) -> None:
    old = _entry(session, age_days=120)
    recent = _entry(session, age_days=10)
    assert purge_old_client_ips(session, days=90, now=NOW) == 1
    session.expire_all()
    rows = {e.id: e for e in session.scalars(select(AuditLog))}
    assert rows[old].client_ip is None
    # Der Eintrag selbst bleibt vollständig erhalten.
    assert rows[old].action == "person.create"
    assert rows[recent].client_ip == "203.0.113.7"


def test_zero_days_disables_purge(session: Session) -> None:
    old = _entry(session, age_days=400)
    assert purge_old_client_ips(session, days=0, now=NOW) == 0
    session.expire_all()
    assert session.get(AuditLog, old).client_ip == "203.0.113.7"


def test_entries_without_ip_are_not_counted(session: Session) -> None:
    _entry(session, age_days=200, ip=None)
    assert purge_old_client_ips(session, days=90, now=NOW) == 0


def test_run_ip_retention_commits(migrated_db: Settings) -> None:
    engine = create_engine(migrated_db.database_url, future=True)
    with Session(engine) as s, s.begin():
        old_id = _entry(s, age_days=365 * 5)
    assert run_ip_retention(engine, 90) == 1
    with Session(engine) as s:
        assert s.get(AuditLog, old_id).client_ip is None


def test_app_startup_runs_retention(migrated_db: Settings) -> None:
    """Beim Start des Portals läuft die Löschung einmal."""
    engine = create_engine(migrated_db.database_url, future=True)
    with Session(engine) as s, s.begin():
        old_id = _entry(s, age_days=365 * 5)
    with TestClient(create_app(settings=migrated_db)) as client:
        client.get("/api/health")
    with Session(engine) as s:
        assert s.get(AuditLog, old_id).client_ip is None
