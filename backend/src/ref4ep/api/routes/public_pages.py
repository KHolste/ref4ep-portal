"""Öffentlich erreichbare, serverseitig gerenderte Pages (Jinja2).

Sprint 0: Steckbrief, Impressum, Datenschutz (Platzhalter).
Sprint 1: zusätzlich öffentliche Partnerliste.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ref4ep.api.deps import get_session
from ref4ep.services.partner_service import PartnerService

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="public/home.html",
        context={"title": "Projekt"},
    )


@router.get("/legal/imprint", response_class=HTMLResponse)
def imprint(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="legal/imprint.html",
        context={"title": "Impressum"},
    )


@router.get("/legal/privacy", response_class=HTMLResponse)
def privacy(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="legal/privacy.html",
        context={"title": "Datenschutz"},
    )


@router.get("/partners", response_class=HTMLResponse)
def partners(request: Request, session: SessionDep) -> HTMLResponse:
    templates = request.app.state.templates
    partners_list = PartnerService(session).list_partners()
    return templates.TemplateResponse(
        request=request,
        name="public/partners.html",
        context={"title": "Partner", "partners": partners_list},
    )
