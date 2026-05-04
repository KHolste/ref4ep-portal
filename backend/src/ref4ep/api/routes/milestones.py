"""Meilenstein-API (Block 0009).

Lesen für jeden eingeloggten Account; Patchen für Admin oder den
``wp_lead`` des zugehörigen Arbeitspakets. Gesamtprojekt-Meilensteine
(``workpackage_id is None``) sind Admin-only — die Permission steckt
im Service (``MilestoneService.can_edit``).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ref4ep.api.deps import (
    get_audit_logger,
    get_auth_context,
    get_session,
    require_csrf,
)
from ref4ep.api.schemas import MilestoneOut, MilestonePatchRequest
from ref4ep.domain.models import Milestone
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.milestone_service import MilestoneService
from ref4ep.services.permissions import AuthContext

router = APIRouter(prefix="/api")

SessionDep = Annotated[Session, Depends(get_session)]
AuthDep = Annotated[AuthContext, Depends(get_auth_context)]
AuditDep = Annotated[AuditLogger, Depends(get_audit_logger)]


def _service(
    session: Session, auth: AuthContext, *, audit: AuditLogger | None = None
) -> MilestoneService:
    return MilestoneService(
        session,
        role=auth.platform_role,
        person_id=auth.person_id,
        audit=audit,
    )


def _milestone_out(milestone: Milestone, *, can_edit: bool) -> MilestoneOut:
    return MilestoneOut(
        id=milestone.id,
        code=milestone.code,
        title=milestone.title,
        workpackage_id=milestone.workpackage_id,
        workpackage_code=milestone.workpackage.code if milestone.workpackage else None,
        workpackage_title=milestone.workpackage.title if milestone.workpackage else None,
        planned_date=milestone.planned_date,
        actual_date=milestone.actual_date,
        status=milestone.status,
        note=milestone.note,
        can_edit=can_edit,
    )


@router.get("/milestones", response_model=list[MilestoneOut])
def list_milestones(session: SessionDep, auth: AuthDep) -> list[MilestoneOut]:
    service = _service(session, auth)
    return [_milestone_out(ms, can_edit=service.can_edit(ms)) for ms in service.list_all()]


@router.get("/milestones/{milestone_id}", response_model=MilestoneOut)
def get_milestone(milestone_id: str, session: SessionDep, auth: AuthDep) -> MilestoneOut:
    service = _service(session, auth)
    milestone = service.get(milestone_id)
    if milestone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Meilenstein nicht gefunden."}},
        )
    return _milestone_out(milestone, can_edit=service.can_edit(milestone))


@router.patch(
    "/milestones/{milestone_id}",
    response_model=MilestoneOut,
    dependencies=[Depends(require_csrf)],
)
def patch_milestone(
    milestone_id: str,
    payload: MilestonePatchRequest,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> MilestoneOut:
    service = _service(session, auth, audit=audit)
    fields = payload.model_dump(exclude_unset=True)
    try:
        milestone = service.update(milestone_id, **fields)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": str(exc)}},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "invalid", "message": str(exc)}},
        ) from exc
    return _milestone_out(milestone, can_edit=True)
