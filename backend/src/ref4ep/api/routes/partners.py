"""Partner-Detail und WP-Lead-Edit für eingeloggte Personen.

Trennung gegenüber ``admin_partners``: dort wirken nur Admins
mit voller Whitelist. Hier liest jeder eingeloggte Account und
WP-Leads dürfen den von ihnen geführten Partner über die
schmale ``WP_LEAD_FIELDS``-Whitelist patchen.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ref4ep.api.deps import get_audit_logger, get_auth_context, get_session, require_csrf
from ref4ep.api.schemas.identity import (
    PartnerContactCreateRequest,
    PartnerContactOut,
    PartnerContactPatchRequest,
    PartnerDetailOut,
    PartnerPatchRequest,
)
from ref4ep.domain.models import (
    PARTNER_CONTACT_FUNCTIONS,
    Partner,
    PartnerContact,
)
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.partner_contact_service import PartnerContactService
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


# --------------------------------------------------------------------------- #
# Block 0007 — Partnerkontakte                                                #
# --------------------------------------------------------------------------- #


def _contact_out(contact: PartnerContact, *, include_internal: bool) -> PartnerContactOut:
    return PartnerContactOut(
        id=contact.id,
        partner_id=contact.partner_id,
        name=contact.name,
        title_or_degree=contact.title_or_degree,
        email=contact.email,
        phone=contact.phone,
        function=contact.function,
        organization_unit=contact.organization_unit,
        workpackage_notes=contact.workpackage_notes,
        is_primary_contact=contact.is_primary_contact,
        is_project_lead=contact.is_project_lead,
        visibility=contact.visibility,
        is_active=contact.is_active,
        internal_note=contact.internal_note if include_internal else None,
    )


def _contact_service(
    session: Session, auth: AuthContext, *, audit: AuditLogger | None = None
) -> PartnerContactService:
    return PartnerContactService(
        session,
        role=auth.platform_role,
        person_id=auth.person_id,
        audit=audit,
    )


def _ensure_partner_visible(session: Session, partner_id: str) -> None:
    partner = session.get(Partner, partner_id)
    if partner is None or partner.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Partner nicht gefunden."}},
        )


@router.get("/partner-contacts/functions", response_model=list[str])
def list_contact_functions(_: AuthDep) -> list[str]:
    """Vorgegebene Funktions-Auswahlliste für die UI (gendergerecht)."""
    return list(PARTNER_CONTACT_FUNCTIONS)


@router.get(
    "/partners/{partner_id}/contacts",
    response_model=list[PartnerContactOut],
)
def list_partner_contacts(
    partner_id: str,
    session: SessionDep,
    auth: AuthDep,
    include_inactive: bool = False,
) -> list[PartnerContactOut]:
    _ensure_partner_visible(session, partner_id)
    service = _contact_service(session, auth)
    is_admin = can_admin(auth.platform_role)
    can_manage = service.can_manage(partner_id)
    # ``include_inactive`` ist nur sinnvoll, wenn die Person verwalten darf;
    # sonst silently auf False zurückfallen.
    contacts = service.list_for_partner(
        partner_id,
        include_inactive=include_inactive and can_manage,
    )
    return [_contact_out(c, include_internal=is_admin) for c in contacts]


@router.post(
    "/partners/{partner_id}/contacts",
    response_model=PartnerContactOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_partner_contact(
    partner_id: str,
    payload: PartnerContactCreateRequest,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> PartnerContactOut:
    service = _contact_service(session, auth, audit=audit)
    fields = payload.model_dump(exclude_unset=True)
    try:
        contact = service.create(partner_id=partner_id, **fields)
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
    return _contact_out(contact, include_internal=can_admin(auth.platform_role))


def _load_contact_or_404(session: Session, contact_id: str) -> PartnerContact:
    contact = session.get(PartnerContact, contact_id)
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Kontakt nicht gefunden."}},
        )
    return contact


@router.patch(
    "/partner-contacts/{contact_id}",
    response_model=PartnerContactOut,
    dependencies=[Depends(require_csrf)],
)
def patch_partner_contact(
    contact_id: str,
    payload: PartnerContactPatchRequest,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> PartnerContactOut:
    _load_contact_or_404(session, contact_id)
    service = _contact_service(session, auth, audit=audit)
    fields = payload.model_dump(exclude_unset=True)
    try:
        contact = service.update(contact_id, **fields)
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
    return _contact_out(contact, include_internal=can_admin(auth.platform_role))


@router.delete(
    "/partner-contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def deactivate_partner_contact(
    contact_id: str,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> Response:
    """Soft-Delete: setzt ``is_active = False``. Es gibt keinen Hard-Delete."""
    _load_contact_or_404(session, contact_id)
    service = _contact_service(session, auth, audit=audit)
    try:
        service.deactivate(contact_id)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": str(exc)}},
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/partner-contacts/{contact_id}/reactivate",
    response_model=PartnerContactOut,
    dependencies=[Depends(require_csrf)],
)
def reactivate_partner_contact(
    contact_id: str,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> PartnerContactOut:
    _load_contact_or_404(session, contact_id)
    service = _contact_service(session, auth, audit=audit)
    try:
        contact = service.reactivate(contact_id)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": str(exc)}},
        ) from exc
    return _contact_out(contact, include_internal=can_admin(auth.platform_role))
