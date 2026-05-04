"""Admin-API für Partner-Verwaltung."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ref4ep.api.deps import get_audit_logger, get_auth_context, get_session, require_csrf
from ref4ep.api.schemas.admin import (
    AdminPartnerCreateRequest,
    AdminPartnerOut,
    AdminPartnerPatchRequest,
)
from ref4ep.domain.models import Partner
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.permissions import AuthContext, can_admin

router = APIRouter(prefix="/api/admin")

SessionDep = Annotated[Session, Depends(get_session)]
AuthDep = Annotated[AuthContext, Depends(get_auth_context)]
AuditDep = Annotated[AuditLogger, Depends(get_audit_logger)]


def _require_admin_or_403(auth: AuthContext) -> None:
    if not can_admin(auth.platform_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "Nur Admin."}},
        )


def _partner_out(partner: Partner) -> AdminPartnerOut:
    return AdminPartnerOut(
        id=partner.id,
        short_name=partner.short_name,
        name=partner.name,
        country=partner.country,
        website=partner.website,
        unit_name=partner.unit_name,
        organization_address_line=partner.organization_address_line,
        organization_postal_code=partner.organization_postal_code,
        organization_city=partner.organization_city,
        organization_country=partner.organization_country,
        unit_address_same_as_organization=partner.unit_address_same_as_organization,
        unit_address_line=partner.unit_address_line,
        unit_postal_code=partner.unit_postal_code,
        unit_city=partner.unit_city,
        unit_country=partner.unit_country,
        is_active=partner.is_active,
        internal_note=partner.internal_note,
        is_deleted=partner.is_deleted,
        created_at=partner.created_at,
        updated_at=partner.updated_at,
    )


def _service(
    session: Session,
    *,
    audit: AuditLogger,
    person_id: str | None = None,
) -> PartnerService:
    return PartnerService(session, role="admin", person_id=person_id, audit=audit)


@router.get("/partners", response_model=list[AdminPartnerOut])
def list_partners(session: SessionDep, auth: AuthDep) -> list[AdminPartnerOut]:
    _require_admin_or_403(auth)
    partners = PartnerService(session).list_partners(include_deleted=True)
    return [_partner_out(p) for p in partners]


@router.post(
    "/partners",
    response_model=AdminPartnerOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_partner(
    payload: AdminPartnerCreateRequest,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> AdminPartnerOut:
    _require_admin_or_403(auth)
    try:
        partner = _service(session, audit=audit).create(
            name=payload.name,
            short_name=payload.short_name,
            country=payload.country,
            website=payload.website,
            unit_name=payload.unit_name,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "invalid", "message": str(exc)}},
        ) from exc
    return _partner_out(partner)


@router.patch(
    "/partners/{partner_id}",
    response_model=AdminPartnerOut,
    dependencies=[Depends(require_csrf)],
)
def patch_partner(
    partner_id: str,
    payload: AdminPartnerPatchRequest,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> AdminPartnerOut:
    _require_admin_or_403(auth)
    fields = payload.model_dump(exclude_unset=True)
    try:
        partner = _service(session, audit=audit).update(partner_id, **fields)
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
    return _partner_out(partner)


@router.delete(
    "/partners/{partner_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def delete_partner(
    partner_id: str,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> Response:
    _require_admin_or_403(auth)
    try:
        _service(session, audit=audit).soft_delete(partner_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
