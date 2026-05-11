"""JSON-Auth-Endpunkte: Login, Logout, Passwortänderung, /api/me."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ref4ep.api.config import Settings
from ref4ep.api.deps import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    get_current_person,
    get_session,
    get_settings,
    require_csrf,
)
from ref4ep.api.schemas import (
    LoginRequest,
    LoginResponse,
    MembershipOut,
    MeOut,
    MePartnerRoleOut,
    PartnerRefOut,
    PasswordChangeRequest,
    PersonOut,
)
from ref4ep.domain.models import Person
from ref4ep.services.auth import create_csrf_token, create_session_token
from ref4ep.services.person_service import PersonService

router = APIRouter(prefix="/api")

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_session)]
PersonDep = Annotated[Person, Depends(get_current_person)]


def _person_to_out(person: Person) -> PersonOut:
    return PersonOut(
        id=person.id,
        email=person.email,
        display_name=person.display_name,
        partner=PartnerRefOut(
            id=person.partner.id,
            short_name=person.partner.short_name,
            name=person.partner.name,
        ),
        platform_role=person.platform_role,
        is_active=person.is_active,
        must_change_password=person.must_change_password,
    )


def _set_auth_cookies(response: Response, settings: Settings, session_token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        max_age=settings.session_max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        create_csrf_token(),
        max_age=settings.session_max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_auth_cookies(response: Response, settings: Settings) -> None:
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.set_cookie(
            name,
            "",
            max_age=0,
            httponly=(name == SESSION_COOKIE),
            secure=settings.cookie_secure,
            samesite="lax",
            path="/",
        )


@router.post("/auth/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    response: Response,
    settings: SettingsDep,
    session: SessionDep,
) -> LoginResponse:
    service = PersonService(session)
    person = service.authenticate(payload.email, payload.password)
    if person is None:
        # Bewusst generisch — keine Existenz-Leakage.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "invalid_credentials", "message": "Login fehlgeschlagen."}},
        )
    token = create_session_token(person.id, settings.session_secret)
    _set_auth_cookies(response, settings, token)
    return LoginResponse(
        person=_person_to_out(person),
        must_change_password=person.must_change_password,
    )


@router.post("/auth/logout", dependencies=[Depends(require_csrf)])
def logout(response: Response, settings: SettingsDep, _: PersonDep) -> dict[str, str]:
    _clear_auth_cookies(response, settings)
    return {"status": "ok"}


@router.post("/auth/password", dependencies=[Depends(require_csrf)])
def change_password(
    payload: PasswordChangeRequest,
    person: PersonDep,
    session: SessionDep,
) -> dict[str, str]:
    service = PersonService(session, role=person.platform_role, person_id=person.id)
    try:
        service.change_password(person.id, payload.old_password, payload.new_password)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "wrong_password", "message": str(exc)}},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_password", "message": str(exc)}},
        ) from exc
    return {"status": "ok"}


@router.get("/me", response_model=MeOut)
def me(person: PersonDep) -> MeOut:
    memberships = [
        MembershipOut(
            workpackage_code=m.workpackage.code,
            workpackage_title=m.workpackage.title,
            wp_role=m.wp_role,
            lead_partner=PartnerRefOut(
                id=m.workpackage.lead_partner.id,
                short_name=m.workpackage.lead_partner.short_name,
                name=m.workpackage.lead_partner.name,
            ),
        )
        for m in person.memberships
    ]
    partner_roles = [
        MePartnerRoleOut(
            partner_id=pr.partner_id,
            partner_short_name=pr.partner.short_name,
            role=pr.role,
        )
        for pr in person.partner_roles
    ]
    return MeOut(
        person=_person_to_out(person),
        memberships=memberships,
        partner_roles=partner_roles,
    )
