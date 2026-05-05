"""Zentrale Aufgaben-API (Block 0018).

Liefert ``MeetingAction``-Einträge gefiltert über den
``MeetingService.list_all_actions``-Helfer und erlaubt einen
schmalen PATCH-Pfad mit drei Berechtigungs-Routen
(Admin / WP-Lead / responsible_person == self).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ref4ep.api.deps import (
    get_audit_logger,
    get_current_person,
    get_session,
    require_csrf,
)
from ref4ep.api.schemas import (
    ActionListItemOut,
    ActionPatchRequest,
    MeetingPersonOut,
)
from ref4ep.domain.models import MeetingAction, Person
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.meeting_service import MeetingService

router = APIRouter(prefix="/api")

SessionDep = Annotated[Session, Depends(get_session)]
ActorDep = Annotated[Person, Depends(get_current_person)]
AuditDep = Annotated[AuditLogger, Depends(get_audit_logger)]


def _service(
    session: Session, actor: Person, *, audit: AuditLogger | None = None
) -> MeetingService:
    return MeetingService(
        session,
        role=actor.platform_role,
        person_id=actor.id,
        audit=audit,
    )


def _person_out(person: Person | None) -> MeetingPersonOut | None:
    if person is None:
        return None
    return MeetingPersonOut(id=person.id, display_name=person.display_name, email=person.email)


def _action_out(action: MeetingAction, *, can_edit: bool) -> ActionListItemOut:
    return ActionListItemOut(
        id=action.id,
        text=action.text,
        status=action.status,
        due_date=action.due_date,
        note=action.note,
        meeting_id=action.meeting_id,
        meeting_title=action.meeting.title,
        workpackage_code=action.workpackage.code if action.workpackage else None,
        workpackage_title=action.workpackage.title if action.workpackage else None,
        responsible_person=_person_out(action.responsible),
        can_edit=can_edit,
        created_at=action.created_at,
        updated_at=action.updated_at,
    )


@router.get("/actions", response_model=list[ActionListItemOut])
def list_actions(
    actor: ActorDep,
    session: SessionDep,
    mine: bool = False,
    status_filter: str | None = Query(default=None, alias="status"),
    overdue: bool = False,
    workpackage: str | None = None,
    responsible_person_id: str | None = None,
) -> list[ActionListItemOut]:
    service = _service(session, actor)
    try:
        actions = service.list_all_actions(
            mine=mine,
            status=status_filter,
            overdue=overdue,
            workpackage_code=workpackage,
            responsible_person_id=responsible_person_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "invalid", "message": str(exc)}},
        ) from exc
    return [_action_out(a, can_edit=service.can_edit_action(a)) for a in actions]


@router.patch(
    "/actions/{action_id}",
    response_model=ActionListItemOut,
    dependencies=[Depends(require_csrf)],
)
def patch_action(
    action_id: str,
    payload: ActionPatchRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> ActionListItemOut:
    service = _service(session, actor, audit=audit)
    fields = payload.model_dump(exclude_unset=True)
    try:
        action = service.update_action_compact(action_id, fields=fields)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": str(exc)}},
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "invalid", "message": str(exc)}},
        ) from exc
    return _action_out(action, can_edit=service.can_edit_action(action))
