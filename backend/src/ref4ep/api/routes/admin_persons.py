"""Admin-API für Personen und WP-Mitgliedschaften.

Plattformrolle ``admin`` zwingend; CSRF für alle nicht-GETs.
Initial- und Reset-Passwörter werden vom Server generiert (oder
optional vom Admin im Body übergeben) und einmalig im Response
zurückgegeben — danach nicht erneut abrufbar.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ref4ep.api.deps import get_audit_logger, get_auth_context, get_session, require_csrf
from ref4ep.api.schemas.admin import (
    AdminMembershipAddRequest,
    AdminMembershipOut,
    AdminMembershipPatchRequest,
    AdminPartnerRefOut,
    AdminPasswordResetResponse,
    AdminPersonCreatedOut,
    AdminPersonCreateRequest,
    AdminPersonDetailOut,
    AdminPersonOut,
    AdminPersonPatchRequest,
    AdminResetPasswordRequest,
    AdminSetRoleRequest,
)
from ref4ep.domain.models import Person
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.auth import generate_initial_password
from ref4ep.services.permissions import AuthContext, can_admin
from ref4ep.services.person_service import EmailAlreadyExists, PersonService
from ref4ep.services.workpackage_service import WorkpackageService

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


def _person_out(person: Person) -> AdminPersonOut:
    return AdminPersonOut(
        id=person.id,
        email=person.email,
        display_name=person.display_name,
        partner=AdminPartnerRefOut(
            id=person.partner.id,
            short_name=person.partner.short_name,
            name=person.partner.name,
        ),
        platform_role=person.platform_role,
        is_active=person.is_active,
        must_change_password=person.must_change_password,
    )


def _membership_out(membership) -> AdminMembershipOut:
    wp = membership.workpackage
    return AdminMembershipOut(
        workpackage_id=wp.id,
        workpackage_code=wp.code,
        workpackage_title=wp.title,
        wp_role=membership.wp_role,
    )


def _detail_out(person: Person) -> AdminPersonDetailOut:
    base = _person_out(person)
    memberships = sorted(person.memberships, key=lambda m: m.workpackage.sort_order)
    return AdminPersonDetailOut(
        **base.model_dump(),
        memberships=[_membership_out(m) for m in memberships],
    )


def _person_service(session: Session, *, audit: AuditLogger) -> PersonService:
    return PersonService(session, role="admin", audit=audit)


def _wp_service(session: Session, *, audit: AuditLogger) -> WorkpackageService:
    return WorkpackageService(session, role="admin", audit=audit)


# --------------------------------------------------------------------------- #
# Personen                                                                    #
# --------------------------------------------------------------------------- #


@router.get("/persons", response_model=list[AdminPersonOut])
def list_persons(session: SessionDep, auth: AuthDep) -> list[AdminPersonOut]:
    _require_admin_or_403(auth)
    persons = PersonService(session).list_persons()
    return [_person_out(p) for p in persons]


@router.get("/persons/{person_id}", response_model=AdminPersonDetailOut)
def get_person(person_id: str, session: SessionDep, auth: AuthDep) -> AdminPersonDetailOut:
    _require_admin_or_403(auth)
    person = PersonService(session).get_by_id(person_id)
    if person is None or person.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Person nicht gefunden."}},
        )
    return _detail_out(person)


@router.post(
    "/persons",
    response_model=AdminPersonCreatedOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_person(
    payload: AdminPersonCreateRequest,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> AdminPersonCreatedOut:
    _require_admin_or_403(auth)
    initial_password = payload.initial_password or generate_initial_password()
    try:
        person = _person_service(session, audit=audit).create(
            email=payload.email,
            display_name=payload.display_name,
            partner_id=payload.partner_id,
            password=initial_password,
            platform_role=payload.platform_role,
        )
    except (LookupError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "invalid", "message": str(exc)}},
        ) from exc
    return AdminPersonCreatedOut(person=_person_out(person), initial_password=initial_password)


@router.patch(
    "/persons/{person_id}",
    response_model=AdminPersonOut,
    dependencies=[Depends(require_csrf)],
)
def patch_person(
    person_id: str,
    payload: AdminPersonPatchRequest,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> AdminPersonOut:
    _require_admin_or_403(auth)
    try:
        person = _person_service(session, audit=audit).update(
            person_id,
            display_name=payload.display_name,
            partner_id=payload.partner_id,
            email=payload.email,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
        ) from exc
    except EmailAlreadyExists as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "email_taken", "message": str(exc)}},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "invalid", "message": str(exc)}},
        ) from exc
    return _person_out(person)


@router.post(
    "/persons/{person_id}/reset-password",
    response_model=AdminPasswordResetResponse,
    dependencies=[Depends(require_csrf)],
)
def reset_password_endpoint(
    person_id: str,
    payload: AdminResetPasswordRequest,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> AdminPasswordResetResponse:
    _require_admin_or_403(auth)
    initial_password = payload.initial_password or generate_initial_password()
    try:
        _person_service(session, audit=audit).reset_password(person_id, initial_password)
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
    return AdminPasswordResetResponse(initial_password=initial_password)


@router.post(
    "/persons/{person_id}/set-role",
    response_model=AdminPersonOut,
    dependencies=[Depends(require_csrf)],
)
def set_role_endpoint(
    person_id: str,
    payload: AdminSetRoleRequest,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> AdminPersonOut:
    _require_admin_or_403(auth)
    try:
        _person_service(session, audit=audit).set_role(person_id, payload.role)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
        ) from exc
    person = PersonService(session).get_by_id(person_id)
    return _person_out(person)


@router.post(
    "/persons/{person_id}/enable",
    response_model=AdminPersonOut,
    dependencies=[Depends(require_csrf)],
)
def enable_endpoint(
    person_id: str, session: SessionDep, auth: AuthDep, audit: AuditDep
) -> AdminPersonOut:
    _require_admin_or_403(auth)
    try:
        _person_service(session, audit=audit).enable(person_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
        ) from exc
    person = PersonService(session).get_by_id(person_id)
    return _person_out(person)


@router.post(
    "/persons/{person_id}/disable",
    response_model=AdminPersonOut,
    dependencies=[Depends(require_csrf)],
)
def disable_endpoint(
    person_id: str, session: SessionDep, auth: AuthDep, audit: AuditDep
) -> AdminPersonOut:
    _require_admin_or_403(auth)
    try:
        _person_service(session, audit=audit).disable(person_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
        ) from exc
    person = PersonService(session).get_by_id(person_id)
    return _person_out(person)


# --------------------------------------------------------------------------- #
# Mitgliedschaften                                                            #
# --------------------------------------------------------------------------- #


def _resolve_membership(session: Session, person_id: str, wp_code: str):
    person = PersonService(session).get_by_id(person_id)
    if person is None or person.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Person nicht gefunden."}},
        )
    wp = WorkpackageService(session).get_by_code(wp_code)
    if wp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Workpackage nicht gefunden."}},
        )
    return person, wp


@router.post(
    "/persons/{person_id}/memberships",
    response_model=AdminMembershipOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def add_membership_endpoint(
    person_id: str,
    payload: AdminMembershipAddRequest,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> AdminMembershipOut:
    _require_admin_or_403(auth)
    person, wp = _resolve_membership(session, person_id, payload.workpackage_code)
    try:
        membership = _wp_service(session, audit=audit).add_membership(
            person.id, wp.id, payload.wp_role
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "membership_exists", "message": str(exc)}},
        ) from exc
    return _membership_out(membership)


@router.patch(
    "/persons/{person_id}/memberships/{wp_code}",
    response_model=AdminMembershipOut,
    dependencies=[Depends(require_csrf)],
)
def patch_membership_endpoint(
    person_id: str,
    wp_code: str,
    payload: AdminMembershipPatchRequest,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> AdminMembershipOut:
    _require_admin_or_403(auth)
    person, wp = _resolve_membership(session, person_id, wp_code)
    try:
        membership = _wp_service(session, audit=audit).set_membership_role(
            person.id, wp.id, payload.wp_role
        )
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
    return _membership_out(membership)


@router.delete(
    "/persons/{person_id}/memberships/{wp_code}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def delete_membership_endpoint(
    person_id: str,
    wp_code: str,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> Response:
    _require_admin_or_403(auth)
    person, wp = _resolve_membership(session, person_id, wp_code)
    _wp_service(session, audit=audit).remove_membership(person.id, wp.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
