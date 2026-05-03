"""Lese-Endpunkte für Stammdaten: Partner, Personen, Workpackages."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ref4ep.api.deps import get_current_person, get_session
from ref4ep.api.schemas import (
    PartnerOut,
    PartnerRefOut,
    PersonOut,
    WorkpackageDetailOut,
    WorkpackageOut,
    WorkpackageRefOut,
)
from ref4ep.api.schemas.identity import WPMembershipOut
from ref4ep.domain.models import Person
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.person_service import PersonService
from ref4ep.services.workpackage_service import WorkpackageService

router = APIRouter(prefix="/api")

SessionDep = Annotated[Session, Depends(get_session)]
PersonDep = Annotated[Person, Depends(get_current_person)]


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


@router.get("/workpackages/{code}", response_model=WorkpackageDetailOut)
def get_workpackage(code: str, _: PersonDep, session: SessionDep) -> WorkpackageDetailOut:
    service = WorkpackageService(session)
    wp = service.get_by_code(code)
    if wp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Workpackage nicht gefunden."}},
        )
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
    children = [
        WorkpackageRefOut(
            code=c.code,
            title=c.title,
            lead_partner=PartnerRefOut(
                id=c.lead_partner.id,
                short_name=c.lead_partner.short_name,
                name=c.lead_partner.name,
            ),
        )
        for c in service.get_children(wp.id)
    ]
    memberships = [
        WPMembershipOut(
            person_email=m.person.email,
            person_display_name=m.person.display_name,
            wp_role=m.wp_role,
        )
        for m in wp.memberships
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
        children=children,
        memberships=memberships,
    )
