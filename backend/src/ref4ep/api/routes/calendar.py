"""Aggregierter Projektkalender (Block 0023).

``GET /api/calendar/events`` — auth-only Lese-Endpoint, der Termine
aus mehreren Quellen normalisiert. Keine Schreibpfade, kein Audit.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ref4ep.api.deps import get_current_person, get_session
from ref4ep.api.schemas.calendar import CalendarEventOut
from ref4ep.domain.models import Person
from ref4ep.services.calendar_service import (
    CALENDAR_EVENT_TYPES,
    CalendarEvent,
    CalendarService,
)

router = APIRouter(prefix="/api")

SessionDep = Annotated[Session, Depends(get_session)]
ActorDep = Annotated[Person, Depends(get_current_person)]


def _default_month_range(today: date) -> tuple[date, date]:
    """Default-Zeitraum: aktueller Kalendermonat."""
    first = today.replace(day=1)
    if first.month == 12:
        next_first = first.replace(year=first.year + 1, month=1)
    else:
        next_first = first.replace(month=first.month + 1)
    last = next_first.replace(day=1)
    # last ist exklusiv → einen Tag zurück.
    from datetime import timedelta

    return first, last - timedelta(days=1)


def _parse_types(raw: list[str] | None) -> list[str] | None:
    """Akzeptiert ``?type=meeting&type=campaign`` ODER kommagetrennt
    (``?type=meeting,campaign``)."""
    if not raw:
        return None
    out: list[str] = []
    for chunk in raw:
        for t in str(chunk).split(","):
            t_clean = t.strip()
            if not t_clean:
                continue
            if t_clean not in CALENDAR_EVENT_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "error": {
                            "code": "invalid",
                            "message": f"type: ungültiger Wert {t_clean!r}",
                        }
                    },
                )
            out.append(t_clean)
    # Reihenfolge ohne Duplikate.
    seen: set[str] = set()
    deduped: list[str] = []
    for t in out:
        if t in seen:
            continue
        seen.add(t)
        deduped.append(t)
    return deduped or None


def _to_out(event: CalendarEvent) -> CalendarEventOut:
    return CalendarEventOut(
        id=event.id,
        source_id=event.source_id,
        type=event.type,
        title=event.title,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        all_day=event.all_day,
        status=event.status,
        workpackage_codes=list(event.workpackage_codes),
        link=event.link,
        description=event.description,
        is_overdue=event.is_overdue,
    )


@router.get("/calendar/events", response_model=list[CalendarEventOut])
def list_calendar_events(
    actor: ActorDep,
    session: SessionDep,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: Annotated[date | None, Query()] = None,
    type: Annotated[list[str] | None, Query()] = None,
    workpackage: Annotated[str | None, Query()] = None,
    mine: Annotated[bool, Query()] = False,
) -> list[CalendarEventOut]:
    today = date.today()
    if from_ is None or to is None:
        default_from, default_to = _default_month_range(today)
        if from_ is None:
            from_ = default_from
        if to is None:
            to = default_to
    types = _parse_types(type)
    service = CalendarService(session, person_id=actor.id)
    try:
        events = service.list_events(
            from_=from_,
            to=to,
            types=types,
            workpackage_code=workpackage,
            mine=mine,
            today=today,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "invalid", "message": str(exc)}},
        ) from exc
    return [_to_out(e) for e in events]
