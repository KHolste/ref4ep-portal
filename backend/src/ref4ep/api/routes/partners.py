"""Partner-Detail und WP-Lead-Edit für eingeloggte Personen.

Trennung gegenüber ``admin_partners``: dort wirken nur Admins
mit voller Whitelist. Hier liest jeder eingeloggte Account und
WP-Leads dürfen den von ihnen geführten Partner über die
schmale ``WP_LEAD_FIELDS``-Whitelist patchen.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ref4ep.api.deps import get_audit_logger, get_auth_context, get_session, require_csrf
from ref4ep.api.schemas.identity import PartnerDetailOut, PartnerPatchRequest
from ref4ep.domain.models import Partner
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.permissions import AuthContext, can_admin

router = APIRouter(prefix="/api")

SessionDep = Annotated[Session, Depends(get_session)]
AuthDep = Annotated[AuthContext, Depends(get_auth_context)]
AuditDep = Annotated[AuditLogger, Depends(get_audit_logger)]


def _detail_out(partner: Partner, *, can_edit: bool, include_internal: bool) -> PartnerDetailOut:
    return PartnerDetailOut(
        id=partner.id,
        short_name=partner.short_name,
        name=partner.name,
        country=partner.country,
        website=partner.website,
        general_email=partner.general_email,
        address_line=partner.address_line,
        postal_code=partner.postal_code,
        city=partner.city,
        address_country=partner.address_country,
        primary_contact_name=partner.primary_contact_name,
        contact_email=partner.contact_email,
        contact_phone=partner.contact_phone,
        project_role_note=partner.project_role_note,
        is_active=partner.is_active,
        internal_note=partner.internal_note if include_internal else None,
        can_edit=can_edit,
    )


def _service(
    session: Session, auth: AuthContext, *, audit: AuditLogger | None = None
) -> PartnerService:
    return PartnerService(
        session,
        role=auth.platform_role,
        person_id=auth.person_id,
        audit=audit,
    )


@router.get("/partners/{partner_id}", response_model=PartnerDetailOut)
def get_partner(partner_id: str, session: SessionDep, auth: AuthDep) -> PartnerDetailOut:
    service = _service(session, auth)
    partner = service.get_by_id(partner_id)
    if partner is None or partner.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Partner nicht gefunden."}},
        )
    is_admin = can_admin(auth.platform_role)
    is_lead = service.is_wp_lead_for_partner(auth.person_id, partner_id)
    return _detail_out(
        partner,
        can_edit=is_admin or is_lead,
        include_internal=is_admin,
    )


@router.patch(
    "/partners/{partner_id}",
    response_model=PartnerDetailOut,
    dependencies=[Depends(require_csrf)],
)
def patch_partner(
    partner_id: str,
    payload: PartnerPatchRequest,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> PartnerDetailOut:
    """WP-Lead-Edit (oder Admin via Whitelist).

    Admins können diesen Endpoint mitnutzen — sie sehen ihn aber
    primär in ``/api/admin/partners`` mit voller Feldmenge.
    """
    fields = payload.model_dump(exclude_unset=True)
    service = _service(session, auth, audit=audit)
    is_admin = can_admin(auth.platform_role)
    try:
        if is_admin:
            partner = service.update(partner_id, **fields)
        else:
            partner = service.update_by_wp_lead(partner_id, **fields)
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
    return _detail_out(
        partner,
        can_edit=True,
        include_internal=is_admin,
    )
