"""Server-gerenderte Auth-Seiten.

GET /login zeigt eine schlichte HTML-Form (kein JS notwendig).
POST /login akzeptiert ``application/x-www-form-urlencoded``,
ruft den Authentifizierungsservice und setzt bei Erfolg die
Session- und CSRF-Cookies. Anschließend Redirect:

- ``/portal/account``, falls ``must_change_password = True``
- ``/portal/`` sonst.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ref4ep.api.config import Settings
from ref4ep.api.deps import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    get_current_person,
    get_session,
    get_settings,
)
from ref4ep.domain.models import Person
from ref4ep.services.auth import create_csrf_token, create_session_token
from ref4ep.services.person_service import PersonService

router = APIRouter()

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_session)]


def _set_cookies(response: RedirectResponse, settings: Settings, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
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


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, error: str | None = None) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"title": "Login", "error": error},
    )


@router.post("/login", response_model=None)
def login_submit(
    request: Request,
    settings: SettingsDep,
    session: SessionDep,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> HTMLResponse | RedirectResponse:
    service = PersonService(session)
    person = service.authenticate(email, password)
    if person is None:
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"title": "Login", "error": "Login fehlgeschlagen.", "email": email},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    target = "/portal/account" if person.must_change_password else "/portal/"
    response = RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)
    token = create_session_token(person.id, settings.session_secret)
    _set_cookies(response, settings, token)
    return response


@router.post("/logout")
def logout_form(
    settings: SettingsDep,
    _: Annotated[Person, Depends(get_current_person)],
) -> RedirectResponse:
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
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
    return response
