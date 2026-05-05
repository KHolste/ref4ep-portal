"""Aktivitäts-Feed-Endpunkt (Block 0018).

``GET /api/activity/recent?since=…`` liest Audit-Einträge ab einem
Zeitpunkt (oder default 14 Tage) und liefert sie als kompakten
Stream. Auth-only; keine sensiblen Felder.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ref4ep.api.deps import get_current_person, get_session
from ref4ep.api.schemas import ActivityEntryOut
from ref4ep.domain.models import Person
from ref4ep.services.activity_service import DEFAULT_LIMIT, ActivityService

router = APIRouter(prefix="/api")

SessionDep = Annotated[Session, Depends(get_session)]
ActorDep = Annotated[Person, Depends(get_current_person)]


@router.get("/activity/recent", response_model=list[ActivityEntryOut])
def get_recent_activity(
    _: ActorDep,
    session: SessionDep,
    since: datetime | None = None,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=200),
) -> list[ActivityEntryOut]:
    entries = ActivityService(session).recent(since=since, limit=limit)
    return [
        ActivityEntryOut(
            timestamp=e.timestamp,
            actor=e.actor,
            type=e.type,
            title=e.title,
            description=e.description,
            link=e.link,
        )
        for e in entries
    ]
