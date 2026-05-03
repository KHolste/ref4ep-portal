"""Audit-Log-API (Sprint 3).

Nur für Plattformrolle ``admin``. Lesepfad mit Filtern; schreibend
ist hier nichts vorgesehen — Einträge entstehen ausschließlich aus
den schreibenden Service-Methoden.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ref4ep.api.deps import get_auth_context, get_session
from ref4ep.api.schemas.documents import AuditActorOut, AuditLogOut
from ref4ep.domain.models import AuditLog, Person
from ref4ep.services.permissions import AuthContext, can_view_audit_log

router = APIRouter(prefix="/api/admin")

SessionDep = Annotated[Session, Depends(get_session)]
AuthDep = Annotated[AuthContext, Depends(get_auth_context)]


def _audit_to_out(entry: AuditLog) -> AuditLogOut:
    actor = entry.actor
    actor_out = AuditActorOut(
        person_id=entry.actor_person_id,
        email=actor.email if actor else None,
        display_name=actor.display_name if actor else None,
        label=entry.actor_label,
    )
    details = None
    if entry.details:
        try:
            details = json.loads(entry.details)
        except json.JSONDecodeError:
            details = {"raw": entry.details}
    return AuditLogOut(
        id=entry.id,
        created_at=entry.created_at,
        actor=actor_out,
        action=entry.action,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        details=details,
        client_ip=entry.client_ip,
        request_id=entry.request_id,
    )


@router.get("/audit", response_model=list[AuditLogOut])
def list_audit_log(
    session: SessionDep,
    auth: AuthDep,
    actor_email: Annotated[str | None, Query()] = None,
    entity_type: Annotated[str | None, Query()] = None,
    entity_id: Annotated[str | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AuditLogOut]:
    if not can_view_audit_log(auth):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "Nur Admin."}},
        )

    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if since:
        stmt = stmt.where(AuditLog.created_at >= since)
    if until:
        stmt = stmt.where(AuditLog.created_at <= until)
    if actor_email:
        person_id = session.scalar(select(Person.id).where(Person.email == actor_email.lower()))
        if person_id is None:
            return []
        stmt = stmt.where(AuditLog.actor_person_id == person_id)

    stmt = stmt.limit(limit).offset(offset)
    return [_audit_to_out(entry) for entry in session.scalars(stmt)]
