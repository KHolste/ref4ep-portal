"""Öffentlich erreichbare, serverseitig gerenderte Pages (Jinja2).

Sprint 0: Steckbrief, Impressum, Datenschutz (Platzhalter).
Sprint 1: zusätzlich öffentliche Partnerliste.
Sprint 4: zusätzlich öffentliche Download-Bibliothek.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ref4ep.api.deps import get_session
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.public_document_service import PublicDocumentService

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


def _humanize_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KiB"
    return f"{n / (1024 * 1024):.2f} MiB"


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


@router.get("/downloads", response_class=HTMLResponse)
def downloads(request: Request, session: SessionDep) -> HTMLResponse:
    templates = request.app.state.templates
    docs = PublicDocumentService(session).list_public()
    entries = []
    for doc in docs:
        version = next((v for v in doc.versions if v.id == doc.released_version_id), None)
        if version is None:
            continue
        entries.append(
            {
                "document": doc,
                "version": version,
                "size_human": _humanize_bytes(version.file_size_bytes),
            }
        )
    return templates.TemplateResponse(
        request=request,
        name="public/downloads.html",
        context={"title": "Downloads", "documents": entries},
    )


@router.get("/downloads/{wp_code}/{slug}", response_class=HTMLResponse)
def download_detail(wp_code: str, slug: str, request: Request, session: SessionDep) -> HTMLResponse:
    templates = request.app.state.templates
    pair = PublicDocumentService(session).get_for_public_download(wp_code=wp_code, slug=slug)
    if pair is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Dokument nicht gefunden."}},
        )
    document, version = pair
    return templates.TemplateResponse(
        request=request,
        name="public/downloads_detail.html",
        context={
            "title": document.title,
            "document": document,
            "version": version,
            "size_human": _humanize_bytes(version.file_size_bytes),
        },
    )
