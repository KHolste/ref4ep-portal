"""Speicherfrist für IP-Adressen im Änderungsprotokoll (Block 0079).

Das Protokoll selbst bleibt erhalten (Nachvollziehbarkeit der
Projektarbeit); nur die IP-Adresse wird nach Ablauf der Frist entfernt.
Die Frist steht in der Datenschutzerklärung (www.ref4ep.de, Abschnitt 8.3)
und ist über ``REF4EP_AUDIT_IP_RETENTION_DAYS`` einstellbar.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ref4ep.domain.models import AuditLog

log = logging.getLogger(__name__)


def purge_old_client_ips(session: Session, *, days: int, now: datetime | None = None) -> int:
    """Entfernt IP-Adressen aus Protokolleinträgen, die älter als ``days``
    Tage sind. Gibt die Zahl der geänderten Einträge zurück; ``days <= 0``
    schaltet die Löschung ab."""
    if days <= 0:
        return 0
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    result = session.execute(
        update(AuditLog)
        .where(AuditLog.created_at < cutoff, AuditLog.client_ip.is_not(None))
        .values(client_ip=None)
    )
    return result.rowcount or 0


def run_ip_retention(engine: Engine, days: int) -> int:
    """Eigenständiger Lauf mit eigener Session (Start und täglicher Lauf)."""
    with Session(engine) as session, session.begin():
        count = purge_old_client_ips(session, days=days)
    if count:
        log.info("Änderungsprotokoll: %d IP-Adressen älter als %d Tage entfernt", count, days)
    return count
