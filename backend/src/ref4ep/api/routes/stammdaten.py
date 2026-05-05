"""Lese-Endpunkte für Stammdaten: Partner, Personen, Workpackages."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ref4ep.api.deps import (
    get_audit_logger,
    get_auth_context,
    get_current_person,
    get_session,
    require_csrf,
)
from ref4ep.api.schemas import (
    PartnerOut,
    PartnerRefOut,
    PersonOut,
    WorkpackageContactOut,
    WorkpackageDetailOut,
    WorkpackageMilestoneOut,
    WorkpackageOut,
    WorkpackageRefOut,
    WorkpackageStatusPatchRequest,
)
from ref4ep.api.schemas.identity import WPMembershipOut
from ref4ep.domain.models import PartnerContact, Person, Workpackage
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.permissions import AuthContext, can_admin
from ref4ep.services.person_service import PersonService
from ref4ep.services.workpackage_service import WorkpackageService

router = APIRouter(prefix="/api")

SessionDep = Annotated[Session, Depends(get_session)]
PersonDep = Annotated[Person, Depends(get_current_person)]
AuthDep = Annotated[AuthContext, Depends(get_auth_context)]
AuditDep = Annotated[AuditLogger, Depends(get_audit_logger)]


@router.get("/partners", response_model=list[PartnerOut])
def list_partners(_: PersonDep, session: SessionDep) -> list[PartnerOut]:
    return [
        PartnerOut(
            id=p.id,
            short_name=p.short_name,
            name=p.name,
            country=p.country,
            website=p.website,
        )
        for p in PartnerService(session).list_partners()
    ]


@router.get("/persons", response_model=list[PersonOut])
def list_persons(_: PersonDep, session: SessionDep) -> list[PersonOut]:
    return [
        PersonOut(
            id=p.id,
            email=p.email,
            display_name=p.display_name,
            partner=PartnerRefOut(
                id=p.partner.id, short_name=p.partner.short_name, name=p.partner.name
            ),
            platform_role=p.platform_role,
            is_active=p.is_active,
            must_change_password=p.must_change_password,
        )
        for p in PersonService(session).list_persons()
    ]


@router.get("/workpackages", response_model=list[WorkpackageOut])
def list_workpackages(
    _: PersonDep,
    session: SessionDep,
    parent_only: bool = False,
) -> list[WorkpackageOut]:
    service = WorkpackageService(session)
    out: list[WorkpackageOut] = []
    for wp in service.list_workpackages(parents_only=parent_only):
        parent_code: str | None = None
        if wp.parent_workpackage_id:
            parent = service.get_by_id(wp.parent_workpackage_id)
            parent_code = parent.code if parent else None
        out.append(
            WorkpackageOut(
                id=wp.id,
                code=wp.code,
                title=wp.title,
                parent_code=parent_code,
                lead_partner=PartnerRefOut(
                    id=wp.lead_partner.id,
                    short_name=wp.lead_partner.short_name,
                    name=wp.lead_partner.name,
                ),
                sort_order=wp.sort_order,
            )
        )
    return out


def _wp_detail_out(
    wp: Workpackage,
    *,
    children: list[Workpackage],
    can_edit_status: bool,
) -> WorkpackageDetailOut:
    parent_ref: WorkpackageRefOut | None = None
    if wp.parent:
        parent_ref = WorkpackageRefOut(
            code=wp.parent.code,
            title=wp.parent.title,
            lead_partner=PartnerRefOut(
                id=wp.parent.lead_partner.id,
                short_name=wp.parent.lead_partner.short_name,
                name=wp.parent.lead_partner.name,
            ),
        )
    memberships = [
        WPMembershipOut(
            person_email=m.person.email,
            person_display_name=m.person.display_name,
            wp_role=m.wp_role,
        )
        for m in wp.memberships
    ]
    # Kontaktpersonen des Lead-Partners (nur aktive, intern oder öffentlich).
    lead_contacts = [
        c
        for c in wp.lead_partner.contacts
        if c.is_active and c.visibility in ("internal", "public")
    ]
    lead_contacts_out = [
        WorkpackageContactOut(
            id=c.id,
            name=c.name,
            title_or_degree=c.title_or_degree,
            email=c.email,
            phone=c.phone,
            function=c.function,
            is_primary_contact=c.is_primary_contact,
            is_project_lead=c.is_project_lead,
        )
        for c in _sorted_contacts(lead_contacts)
    ]
    milestones_out = [
        WorkpackageMilestoneOut(
            id=ms.id,
            code=ms.code,
            title=ms.title,
            planned_date=ms.planned_date,
            actual_date=ms.actual_date,
            status=ms.status,
            note=ms.note,
        )
        for ms in wp.milestones
    ]
    return WorkpackageDetailOut(
        code=wp.code,
        title=wp.title,
        description=wp.description,
        parent=parent_ref,
        lead_partner=PartnerRefOut(
            id=wp.lead_partner.id,
            short_name=wp.lead_partner.short_name,
            name=wp.lead_partner.name,
        ),
        children=[
            WorkpackageRefOut(
                code=c.code,
                title=c.title,
                lead_partner=PartnerRefOut(
                    id=c.lead_partner.id,
                    short_name=c.lead_partner.short_name,
                    name=c.lead_partner.name,
                ),
            )
            for c in children
        ],
        memberships=memberships,
        status=wp.status,
        summary=wp.summary,
        next_steps=wp.next_steps,
        open_issues=wp.open_issues,
        can_edit_status=can_edit_status,
        lead_partner_contacts=lead_contacts_out,
        milestones=milestones_out,
    )


def _sorted_contacts(contacts: list[PartnerContact]) -> list[PartnerContact]:
    """Hauptkontakt + Projektleitung zuerst, dann alphabetisch."""
    return sorted(
        contacts,
        key=lambda c: (
            not c.is_primary_contact,
            not c.is_project_lead,
            (c.name or "").lower(),
        ),
    )


@router.get("/workpackages/{code}", response_model=WorkpackageDetailOut)
def get_workpackage(
    code: str,
    session: SessionDep,
    auth: AuthDep,
) -> WorkpackageDetailOut:
    service = WorkpackageService(session)
    wp = service.get_by_code(code)
    if wp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Workpackage nicht gefunden."}},
        )
    children = service.get_children(wp.id)
    is_admin = can_admin(auth.platform_role)
    is_lead = bool(auth.person_id) and service.is_wp_lead(auth.person_id, wp.id)
    return _wp_detail_out(
        wp,
        children=children,
        can_edit_status=is_admin or is_lead,
    )


@router.patch(
    "/workpackages/{code}",
    response_model=WorkpackageDetailOut,
    dependencies=[Depends(require_csrf)],
)
def patch_workpackage_status(
    code: str,
    payload: WorkpackageStatusPatchRequest,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> WorkpackageDetailOut:
    service = WorkpackageService(
        session,
        role=auth.platform_role,
        person_id=auth.person_id,
        audit=audit,
    )
    wp = service.get_by_code(code)
    if wp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Workpackage nicht gefunden."}},
        )
    fields = payload.model_dump(exclude_unset=True)
    try:
        wp = service.update_status(wp.id, **fields)
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
    children = service.get_children(wp.id)
    return _wp_detail_out(
        wp,
        children=children,
        can_edit_status=True,
    )
