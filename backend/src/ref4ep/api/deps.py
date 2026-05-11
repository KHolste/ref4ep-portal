"""FastAPI-Dependencies (Injection-Helfer).

Sprint 1: Settings, Engine/Session, Auth-Resolver (Cookie → Person),
CSRF-Prüfung, AuthContext-Bau.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ref4ep.api.config import Settings
from ref4ep.domain.models import Person
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.auth import read_session_token, verify_csrf
from ref4ep.services.permissions import AuthContext, MembershipInfo, PartnerRoleInfo

SESSION_COOKIE = "ref4ep_session"
CSRF_COOKIE = "ref4ep_csrf"
CSRF_HEADER = "X-CSRF-Token"


def get_settings(request: Request) -> Settings:
    """Settings aus ``app.state`` (von ``create_app`` injiziert)."""
    return request.app.state.settings


def get_engine(request: Request) -> Engine:
    return request.app.state.engine


def get_session(request: Request) -> Iterator[Session]:
    engine: Engine = request.app.state.engine
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
        expire_on_commit=False,
    )
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_session)]


def get_optional_person(
    request: Request,
    settings: SettingsDep,
    session: SessionDep,
) -> Person | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    person_id = read_session_token(token, settings.session_secret, settings.session_max_age)
    if person_id is None:
        return None
    person = session.get(Person, person_id)
    if person is None or not person.is_active or person.is_deleted:
        return None
    return person


OptionalPersonDep = Annotated[Person | None, Depends(get_optional_person)]


def get_current_person(person: OptionalPersonDep) -> Person:
    if person is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "not_authenticated", "message": "Nicht angemeldet."}},
        )
    return person


CsrfCookieDep = Annotated[str | None, Cookie(alias=CSRF_COOKIE)]
CsrfHeaderDep = Annotated[str | None, Header(alias=CSRF_HEADER)]


def require_csrf(
    request: Request,
    csrf_cookie: CsrfCookieDep = None,
    csrf_header: CsrfHeaderDep = None,
) -> None:
    if not verify_csrf(csrf_cookie, csrf_header):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "csrf_failed", "message": "CSRF-Token ungültig."}},
        )


CurrentPersonDep = Annotated[Person, Depends(get_current_person)]


def get_audit_logger(
    request: Request,
    person: CurrentPersonDep,
    session: SessionDep,
) -> AuditLogger:
    request_id = request.headers.get("X-Request-ID")
    client_host = request.client.host if request.client else None
    return AuditLogger(
        session,
        actor_person_id=person.id,
        client_ip=client_host,
        request_id=request_id,
    )


def get_auth_context(person: CurrentPersonDep) -> AuthContext:
    memberships = [
        MembershipInfo(
            workpackage_id=m.workpackage_id,
            workpackage_code=m.workpackage.code,
            wp_role=m.wp_role,
        )
        for m in person.memberships
    ]
    # Block 0045 — Partnerrollen passiv mitführen. Auswertung erfolgt
    # gezielt in den Service-Pfaden, die Partnerleitung berücksichtigen.
    partner_roles = [
        PartnerRoleInfo(partner_id=pr.partner_id, role=pr.role) for pr in person.partner_roles
    ]
    return AuthContext(
        person_id=person.id,
        email=person.email,
        platform_role=person.platform_role,
        memberships=memberships,
        partner_roles=partner_roles,
    )
