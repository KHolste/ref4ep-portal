"""Audit-Log-Service.

Schreibt einen ``audit_log``-Eintrag pro schreibender Aktion.
Wird über die Service-Konstruktoren als optionaler Parameter
hineingereicht; Services rufen ``self.audit.log(...)`` defensiv
nur auf, wenn ``self.audit`` gesetzt ist (Tests/CLI ohne
Audit-Bedarf bleiben so möglich).

Akteur-Quellen:
- API: ``actor_person_id`` aus dem aktuell eingeloggten Account.
- CLI: ``actor_label = "cli-admin"``.
- System (Migration, Seed, sonstige): Default-Label ``"system"``.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ref4ep.domain.models import AuditLog


def _serialize(payload: dict[str, Any] | None) -> Any:
    if payload is None:
        return None
    return payload


def _dumps(details: dict[str, Any] | None) -> str | None:
    if details is None:
        return None
    return json.dumps(details, default=str, ensure_ascii=False, sort_keys=True)


class AuditLogger:
    def __init__(
        self,
        session: Session,
        *,
        actor_person_id: str | None = None,
        actor_label: str | None = None,
        client_ip: str | None = None,
        request_id: str | None = None,
    ) -> None:
        self.session = session
        self.actor_person_id = actor_person_id
        if actor_person_id is None and actor_label is None:
            actor_label = "system"
        self.actor_label = actor_label
        self.client_ip = client_ip
        self.request_id = request_id

    def log(
        self,
        action: str,
        *,
        entity_type: str,
        entity_id: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> AuditLog:
        details = {"before": _serialize(before), "after": _serialize(after)}
        entry = AuditLog(
            actor_person_id=self.actor_person_id,
            actor_label=self.actor_label,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=_dumps(details),
            client_ip=self.client_ip,
            request_id=self.request_id,
        )
        self.session.add(entry)
        self.session.flush()
        return entry
