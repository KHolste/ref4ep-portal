"""Meeting-/Protokollregister-Endpoints (Block 0015).

Lesen ist auth-only; Schreiben CSRF + Service-Permission.
``MeetingService`` kapselt die Berechtigungslogik (Admin oder
WP-Lead aller beteiligten WPs).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ref4ep.api.deps import (
    get_audit_logger,
    get_current_person,
    get_session,
    require_csrf,
)
from ref4ep.api.schemas import (
    MeetingActionCreateRequest,
    MeetingActionOut,
    MeetingActionPatchRequest,
    MeetingCreateRequest,
    MeetingDecisionCreateRequest,
    MeetingDecisionOut,
    MeetingDecisionPatchRequest,
    MeetingDetailOut,
    MeetingDocumentLinkAddRequest,
    MeetingDocumentOut,
    MeetingListItemOut,
    MeetingParticipantAddRequest,
    MeetingPatchRequest,
    MeetingPersonOut,
    MeetingWorkpackageOut,
)
from ref4ep.domain.models import (
    Meeting,
    MeetingAction,
    MeetingDecision,
    Person,
)
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
    return MeetingPersonOut(
        id=person.id,
        display_name=person.display_name,
        email=person.email,
    )


def _wps_out(meeting: Meeting) -> list[MeetingWorkpackageOut]:
    return [
        MeetingWorkpackageOut(code=link.workpackage.code, title=link.workpackage.title)
        for link in sorted(meeting.workpackage_links, key=lambda link: link.workpackage.sort_order)
    ]


def _decision_out(decision: MeetingDecision) -> MeetingDecisionOut:
    return MeetingDecisionOut(
        id=decision.id,
        text=decision.text,
        status=decision.status,
        workpackage_code=decision.workpackage.code if decision.workpackage else None,
        responsible_person=_person_out(decision.responsible),
    )


def _action_out(action: MeetingAction) -> MeetingActionOut:
    return MeetingActionOut(
        id=action.id,
        text=action.text,
        status=action.status,
        due_date=action.due_date,
        workpackage_code=action.workpackage.code if action.workpackage else None,
        responsible_person=_person_out(action.responsible),
        note=action.note,
    )


def _document_out(link) -> MeetingDocumentOut:
    return MeetingDocumentOut(
        document_id=link.document_id,
        title=link.document.title,
        deliverable_code=link.document.deliverable_code,
        label=link.label,
    )


def _list_item(meeting: Meeting, *, can_edit: bool) -> MeetingListItemOut:
    open_actions = sum(1 for a in meeting.actions if a.status in ("open", "in_progress"))
    return MeetingListItemOut(
        id=meeting.id,
        title=meeting.title,
        starts_at=meeting.starts_at,
        ends_at=meeting.ends_at,
        format=meeting.format,
        category=meeting.category,
        status=meeting.status,
        workpackages=_wps_out(meeting),
        open_actions=open_actions,
        decisions=len(meeting.decisions),
        can_edit=can_edit,
    )


def _detail(meeting: Meeting, *, can_edit: bool) -> MeetingDetailOut:
    return MeetingDetailOut(
        id=meeting.id,
        title=meeting.title,
        starts_at=meeting.starts_at,
        ends_at=meeting.ends_at,
        format=meeting.format,
        location=meeting.location,
        category=meeting.category,
        status=meeting.status,
        summary=meeting.summary,
        extra_participants=meeting.extra_participants,
        created_by=_person_out(meeting.created_by),
        workpackages=_wps_out(meeting),
        participants=[
            _person_out(link.person)
            for link in sorted(
                meeting.participant_links,
                key=lambda link: (link.person.display_name or "").lower(),
            )
        ],
        decisions=[_decision_out(d) for d in meeting.decisions],
        actions=[_action_out(a) for a in meeting.actions],
        documents=[_document_out(link) for link in meeting.document_links],
        can_edit=can_edit,
    )


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": str(exc)}},
        )
    if isinstance(exc, LookupError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
        )
    if isinstance(exc, ValueError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "invalid", "message": str(exc)}},
        )
    raise exc


# ---- Meetings ----------------------------------------------------------


@router.get("/meetings", response_model=list[MeetingListItemOut])
def list_meetings(
    actor: ActorDep,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status"),
    category: str | None = None,
    workpackage: str | None = None,
) -> list[MeetingListItemOut]:
    service = _service(session, actor)
    meetings = service.list_meetings(
        status=status_filter, category=category, workpackage_code=workpackage
    )
    return [_list_item(m, can_edit=service.can_edit_meeting(m)) for m in meetings]


@router.post(
    "/meetings",
    response_model=MeetingDetailOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_meeting(
    payload: MeetingCreateRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> MeetingDetailOut:
    service = _service(session, actor, audit=audit)
    try:
        meeting = service.create_meeting(
            title=payload.title,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            format_=payload.format,
            location=payload.location,
            category=payload.category,
            status=payload.status,
            summary=payload.summary,
            extra_participants=payload.extra_participants,
            workpackage_ids=payload.workpackage_ids,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return _detail(meeting, can_edit=True)


@router.get("/meetings/{meeting_id}", response_model=MeetingDetailOut)
def get_meeting(meeting_id: str, actor: ActorDep, session: SessionDep) -> MeetingDetailOut:
    service = _service(session, actor)
    meeting = service.get(meeting_id)
    if meeting is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Meeting nicht gefunden."}},
        )
    return _detail(meeting, can_edit=service.can_edit_meeting(meeting))


@router.patch(
    "/meetings/{meeting_id}",
    response_model=MeetingDetailOut,
    dependencies=[Depends(require_csrf)],
)
def patch_meeting(
    meeting_id: str,
    payload: MeetingPatchRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> MeetingDetailOut:
    service = _service(session, actor, audit=audit)
    raw = payload.model_dump(exclude_unset=True)
    workpackage_ids = raw.pop("workpackage_ids", None)
    try:
        meeting = service.update_meeting(
            meeting_id,
            fields=raw,
            workpackage_ids=workpackage_ids,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return _detail(meeting, can_edit=True)


@router.post(
    "/meetings/{meeting_id}/cancel",
    response_model=MeetingDetailOut,
    dependencies=[Depends(require_csrf)],
)
def cancel_meeting(
    meeting_id: str,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> MeetingDetailOut:
    service = _service(session, actor, audit=audit)
    try:
        meeting = service.cancel_meeting(meeting_id)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return _detail(meeting, can_edit=True)


@router.delete(
    "/meetings/{meeting_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def delete_meeting(
    meeting_id: str,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> Response:
    """Hard-Delete eines Meetings — ausschließlich Plattform-``admin``.

    Bewusst eng gefasst: WP-Leads können Meetings nur über
    ``POST /api/meetings/{id}/cancel`` zum Status ``cancelled`` bringen.
    """
    service = _service(session, actor, audit=audit)
    try:
        service.delete_meeting_admin(meeting_id)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- Teilnehmende ------------------------------------------------------


@router.post(
    "/meetings/{meeting_id}/participants",
    response_model=MeetingDetailOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def add_participant(
    meeting_id: str,
    payload: MeetingParticipantAddRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> MeetingDetailOut:
    service = _service(session, actor, audit=audit)
    try:
        service.add_participant(meeting_id, payload.person_id)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    meeting = service.get(meeting_id)
    return _detail(meeting, can_edit=True)


@router.delete(
    "/meetings/{meeting_id}/participants/{person_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def remove_participant(
    meeting_id: str,
    person_id: str,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> Response:
    service = _service(session, actor, audit=audit)
    try:
        service.remove_participant(meeting_id, person_id)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- Beschlüsse --------------------------------------------------------


@router.post(
    "/meetings/{meeting_id}/decisions",
    response_model=MeetingDecisionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_decision(
    meeting_id: str,
    payload: MeetingDecisionCreateRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> MeetingDecisionOut:
    service = _service(session, actor, audit=audit)
    try:
        decision = service.create_decision(
            meeting_id,
            text=payload.text,
            workpackage_id=payload.workpackage_id,
            responsible_person_id=payload.responsible_person_id,
            status=payload.status,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return _decision_out(decision)


@router.patch(
    "/meeting-decisions/{decision_id}",
    response_model=MeetingDecisionOut,
    dependencies=[Depends(require_csrf)],
)
def patch_decision(
    decision_id: str,
    payload: MeetingDecisionPatchRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> MeetingDecisionOut:
    service = _service(session, actor, audit=audit)
    fields = payload.model_dump(exclude_unset=True)
    try:
        decision = service.update_decision(decision_id, fields=fields)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return _decision_out(decision)


# ---- Aufgaben ----------------------------------------------------------


@router.post(
    "/meetings/{meeting_id}/actions",
    response_model=MeetingActionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_action(
    meeting_id: str,
    payload: MeetingActionCreateRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> MeetingActionOut:
    service = _service(session, actor, audit=audit)
    try:
        action = service.create_action(
            meeting_id,
            text=payload.text,
            workpackage_id=payload.workpackage_id,
            responsible_person_id=payload.responsible_person_id,
            due_date=payload.due_date,
            status=payload.status,
            note=payload.note,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return _action_out(action)


@router.patch(
    "/meeting-actions/{action_id}",
    response_model=MeetingActionOut,
    dependencies=[Depends(require_csrf)],
)
def patch_action(
    action_id: str,
    payload: MeetingActionPatchRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> MeetingActionOut:
    service = _service(session, actor, audit=audit)
    fields = payload.model_dump(exclude_unset=True)
    try:
        action = service.update_action(action_id, fields=fields)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return _action_out(action)


# ---- Dokumentverknüpfungen --------------------------------------------


@router.post(
    "/meetings/{meeting_id}/documents",
    response_model=MeetingDetailOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def link_document(
    meeting_id: str,
    payload: MeetingDocumentLinkAddRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> MeetingDetailOut:
    service = _service(session, actor, audit=audit)
    try:
        service.add_document_link(meeting_id, document_id=payload.document_id, label=payload.label)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    meeting = service.get(meeting_id)
    return _detail(meeting, can_edit=True)


@router.delete(
    "/meetings/{meeting_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def unlink_document(
    meeting_id: str,
    document_id: str,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> Response:
    service = _service(session, actor, audit=audit)
    try:
        service.remove_document_link(meeting_id, document_id)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
