"""„Mein Team“-Endpoints für WP-Leads (Block 0013).

Eigener Router unter ``/api/lead/...`` — bewusst getrennt von den
Admin-Routen, damit die Admin-Berechtigungen nicht aufgeweicht werden.

Berechtigungs-Eingangskriterium: die eingeloggte Person muss
**mindestens eine** ``wp_lead``-Mitgliedschaft haben **oder** Admin
sein. Admins dürfen die Lead-Sicht mitnutzen (sie sehen ihren
eigenen Partner und ihre eigenen Lead-WPs — meist null Lead-WPs).

Alle schreibenden Endpunkte:
- CSRF-geschützt
- Audit-Eintrag mit ``actor_person_id`` und Entity-Feldern, **ohne
  Klartextpasswort**.

Existenz-Leakage: Lead-Routen verwenden ``403`` für fremde Objekte
(„nein, nicht deins") statt ``404`` („existiert nicht"). Das ist die
fachliche Antwort, die ein Lead an dieser Stelle bekommt.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ref4ep.api.deps import (
    get_audit_logger,
    get_current_person,
    get_session,
    require_csrf,
)
from ref4ep.api.schemas import (
    LeadAddMembershipRequest,
    LeadPersonCreatedOut,
    LeadPersonCreateRequest,
    LeadPersonOut,
    LeadSetMembershipRoleRequest,
    LeadWorkpackageMemberOut,
    LeadWorkpackageOut,
)
from ref4ep.domain.models import Membership, PartnerRole, Person, Workpackage
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.auth import generate_initial_password
from ref4ep.services.permissions import can_admin
from ref4ep.services.person_service import PersonService
from ref4ep.services.workpackage_service import WorkpackageService

router = APIRouter(prefix="/api/lead")

SessionDep = Annotated[Session, Depends(get_session)]
ActorDep = Annotated[Person, Depends(get_current_person)]
AuditDep = Annotated[AuditLogger, Depends(get_audit_logger)]


# ---- Berechtigungs-Eingang ---------------------------------------------


def _require_lead_or_admin(actor: Person, session: Session) -> None:
    """403, wenn der Aufrufer weder Admin noch WP-Lead noch
    Projektleitung (``partner_lead``) ist.

    Block 0045 — Eingang zur Lead-Sicht öffnet sich zusätzlich für
    Partnerleitungen. Die Lead-Routen wirken weiterhin auf
    ``actor.partner_id`` — Partnerleitung kann also nur den eigenen
    Login-Partner verwalten. Wer Partnerleitung für **einen anderen**
    Partner ist, sieht hier seinen eigenen Partner, nicht den fremden
    (das wäre eine eigene Route — Folgepunkt).
    """
    if can_admin(actor.platform_role):
        return
    has_lead = session.scalars(
        select(Membership.id)
        .where(
            Membership.person_id == actor.id,
            Membership.wp_role == "wp_lead",
        )
        .limit(1)
    ).first()
    if has_lead is not None:
        return
    has_partner_lead = session.scalars(
        select(PartnerRole.id)
        .where(
            PartnerRole.person_id == actor.id,
            PartnerRole.role == "partner_lead",
        )
        .limit(1)
    ).first()
    if has_partner_lead is not None:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": {
                "code": "forbidden",
                "message": "„Mein Team“ ist nur für WP-Leads und Projektleitungen zugänglich.",
            }
        },
    )


def _person_out(person: Person) -> LeadPersonOut:
    return LeadPersonOut(
        id=person.id,
        email=person.email,
        display_name=person.display_name,
        is_active=person.is_active,
        must_change_password=person.must_change_password,
    )


# ---- Personen meines Partners ------------------------------------------


@router.get("/persons", response_model=list[LeadPersonOut])
def list_my_partner_persons(actor: ActorDep, session: SessionDep) -> list[LeadPersonOut]:
    """Personen, die zum gleichen Partner gehören wie der Aufrufer.

    Soft-deleted werden ausgeblendet — entspricht dem Verhalten des
    Admin-`/api/admin/persons`-Endpoints.
    """
    _require_lead_or_admin(actor, session)
    stmt = (
        select(Person)
        .where(
            Person.partner_id == actor.partner_id,
            Person.is_deleted.is_(False),
        )
        .order_by(Person.email)
    )
    return [_person_out(p) for p in session.scalars(stmt)]


@router.post(
    "/persons",
    response_model=LeadPersonCreatedOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_my_partner_person(
    payload: LeadPersonCreateRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> LeadPersonCreatedOut:
    _require_lead_or_admin(actor, session)
    initial_password = payload.initial_password or generate_initial_password()
    service = PersonService(session, role=actor.platform_role, person_id=actor.id, audit=audit)
    try:
        person = service.create_by_wp_lead(
            actor_partner_id=actor.partner_id,
            email=payload.email,
            display_name=payload.display_name,
            password=initial_password,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "invalid", "message": str(exc)}},
        ) from exc
    return LeadPersonCreatedOut(person=_person_out(person), initial_password=initial_password)


# ---- Meine WPs (mit Mitgliedern) ---------------------------------------


def _wp_out_for_lead(wp: Workpackage, actor_person_id: str) -> LeadWorkpackageOut:
    my_membership = next(
        (m for m in wp.memberships if m.person_id == actor_person_id),
        None,
    )
    members = [
        LeadWorkpackageMemberOut(
            person_id=m.person_id,
            email=m.person.email,
            display_name=m.person.display_name,
            wp_role=m.wp_role,
        )
        for m in sorted(
            wp.memberships,
            key=lambda m: (m.wp_role != "wp_lead", (m.person.display_name or "").lower()),
        )
    ]
    return LeadWorkpackageOut(
        code=wp.code,
        title=wp.title,
        my_role=my_membership.wp_role if my_membership else "wp_lead",
        members=members,
    )


@router.get("/workpackages", response_model=list[LeadWorkpackageOut])
def list_my_lead_workpackages(actor: ActorDep, session: SessionDep) -> list[LeadWorkpackageOut]:
    """Workpackages, in denen der Aufrufer wp_lead ist (mit Mitgliederliste).

    Admins sehen hier nur ihre eigenen Lead-WPs (meist keine).
    Begründung: dieser Endpoint hat in seiner Semantik „**meine**
    Lead-WPs"; eine Sonderbehandlung für Admin (alle WPs) wäre
    inkonsistent zur Personen-Liste, die ebenfalls nur den eigenen
    Partner-Kreis liefert. Wer alle WPs sehen will, nutzt
    ``/api/workpackages``.
    """
    _require_lead_or_admin(actor, session)
    wps = WorkpackageService(session).list_lead_workpackages(actor.id)
    return [_wp_out_for_lead(wp, actor.id) for wp in wps]


def _resolve_wp_or_403(session: Session, code: str, actor: Person) -> Workpackage:
    """Holt ein WP per Code; 403 wenn der Aufrufer dort nicht wp_lead ist.

    Bewusst 403 (nicht 404), damit Lead-Routen ein konsistentes
    „nein, nicht deins" liefern — egal ob das WP existiert oder nicht.
    Admins werden nicht durchgewunken: die Lead-Routen sind für die
    eigene Lead-Sicht da; Admin-Funktionen liegen in ``/api/admin/...``.
    """
    wp = session.scalars(
        select(Workpackage).where(Workpackage.code == code, Workpackage.is_deleted.is_(False))
    ).first()
    if wp is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "Kein Zugriff auf dieses WP."}},
        )
    if not WorkpackageService(session).is_wp_lead(actor.id, wp.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "Kein Zugriff auf dieses WP."}},
        )
    return wp


@router.post(
    "/workpackages/{code}/memberships",
    response_model=LeadWorkpackageOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def add_membership_in_my_wp(
    code: str,
    payload: LeadAddMembershipRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> LeadWorkpackageOut:
    _require_lead_or_admin(actor, session)
    wp = _resolve_wp_or_403(session, code, actor)
    service = WorkpackageService(session, role=actor.platform_role, person_id=actor.id, audit=audit)
    try:
        service.add_membership_by_wp_lead(
            actor_person_id=actor.id,
            actor_partner_id=actor.partner_id,
            workpackage_id=wp.id,
            target_person_id=payload.person_id,
            wp_role=payload.wp_role,
        )
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
    session.refresh(wp)
    return _wp_out_for_lead(wp, actor.id)


@router.patch(
    "/workpackages/{code}/memberships/{person_id}",
    response_model=LeadWorkpackageOut,
    dependencies=[Depends(require_csrf)],
)
def set_membership_role_in_my_wp(
    code: str,
    person_id: str,
    payload: LeadSetMembershipRoleRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> LeadWorkpackageOut:
    _require_lead_or_admin(actor, session)
    wp = _resolve_wp_or_403(session, code, actor)
    service = WorkpackageService(session, role=actor.platform_role, person_id=actor.id, audit=audit)
    try:
        service.set_membership_role_by_wp_lead(
            actor_person_id=actor.id,
            workpackage_id=wp.id,
            target_person_id=person_id,
            wp_role=payload.wp_role,
        )
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
    session.refresh(wp)
    return _wp_out_for_lead(wp, actor.id)


@router.delete(
    "/workpackages/{code}/memberships/{person_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def remove_membership_from_my_wp(
    code: str,
    person_id: str,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> Response:
    _require_lead_or_admin(actor, session)
    wp = _resolve_wp_or_403(session, code, actor)
    service = WorkpackageService(session, role=actor.platform_role, person_id=actor.id, audit=audit)
    try:
        service.remove_membership_by_wp_lead(
            actor_person_id=actor.id,
            workpackage_id=wp.id,
            target_person_id=person_id,
        )
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
    return Response(status_code=status.HTTP_204_NO_CONTENT)
