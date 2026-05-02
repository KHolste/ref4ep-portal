"""Öffentlich erreichbare, serverseitig gerenderte Pages (Jinja2).

In Sprint 0 nur Platzhalter-Inhalte. Echte Texte (Steckbrief,
Impressum, Datenschutz) werden in Sprint 4 vor Go-Live ergänzt.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


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
