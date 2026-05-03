"""Öffentliche Dokumenten-API (Sprint 4).

Anonym erreichbar; liefert ausschließlich Dokumente, die der
``PublicDocumentService``-Filter durchlässt
(``visibility=public ∧ status=released ∧ released_version_id IS NOT NULL
∧ is_deleted=false``). Schreibt **keine** Audit-Einträge — DSGVO-
freundlich, kein Mehrwert für interne Nachvollziehbarkeit (siehe
MVP-Spec §9 „Audit-Log erfasst den Download nicht").
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ref4ep.api.deps import get_session
from ref4ep.api.schemas.documents import (
    PublicDocumentOut,
    PublicDocumentVersionOut,
    WorkpackageRef,
)
from ref4ep.domain.models import Document, DocumentVersion
from ref4ep.services.public_document_service import PublicDocumentService
from ref4ep.storage import Storage

router = APIRouter(prefix="/api/public")

SessionDep = Annotated[Session, Depends(get_session)]
CHUNK_SIZE = 1024 * 1024


def _get_storage(request: Request) -> Storage:
    return request.app.state.storage


StorageDep = Annotated[Storage, Depends(_get_storage)]


def _public_version_out(version: DocumentVersion) -> PublicDocumentVersionOut:
    return PublicDocumentVersionOut(
        version_number=version.version_number,
        version_label=version.version_label,
        original_filename=version.original_filename,
        mime_type=version.mime_type,
        file_size_bytes=version.file_size_bytes,
        sha256=version.sha256,
        uploaded_at=version.uploaded_at,
    )


def _public_document_out(document: Document, version: DocumentVersion) -> PublicDocumentOut:
    return PublicDocumentOut(
        slug=document.slug,
        title=document.title,
        document_type=document.document_type,
        deliverable_code=document.deliverable_code,
        workpackage=WorkpackageRef(
            code=document.workpackage.code, title=document.workpackage.title
        ),
        released_version=_public_version_out(version),
        released_at=version.uploaded_at,
        download_url=(
            f"/api/public/documents/{document.workpackage.code}/{document.slug}/download"
        ),
    )


@router.get("/documents", response_model=list[PublicDocumentOut])
def list_public_documents(session: SessionDep) -> list[PublicDocumentOut]:
    docs = PublicDocumentService(session).list_public()
    out: list[PublicDocumentOut] = []
    for doc in docs:
        version = next((v for v in doc.versions if v.id == doc.released_version_id), None)
        if version is None:
            continue
        out.append(_public_document_out(doc, version))
    return out


@router.get("/documents/{wp_code}/{slug}", response_model=PublicDocumentOut)
def get_public_document(wp_code: str, slug: str, session: SessionDep) -> PublicDocumentOut:
    pair = PublicDocumentService(session).get_for_public_download(wp_code=wp_code, slug=slug)
    if pair is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Dokument nicht gefunden."}},
        )
    document, version = pair
    return _public_document_out(document, version)


@router.get("/documents/{wp_code}/{slug}/download")
def download_public_version(
    wp_code: str,
    slug: str,
    session: SessionDep,
    storage: StorageDep,
) -> StreamingResponse:
    pair = PublicDocumentService(session).get_for_public_download(wp_code=wp_code, slug=slug)
    if pair is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Datei nicht verfügbar."}},
        )
    _, version = pair

    fh = storage.open_read(version.storage_key)

    def iterator():
        try:
            while True:
                chunk = fh.read(CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
        finally:
            fh.close()

    safe_name = version.original_filename.replace('"', "")
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_name}"',
        "Content-Length": str(version.file_size_bytes),
        "X-Content-Type-Options": "nosniff",
        "ETag": f'"{version.sha256}"',
        "Cache-Control": "public, max-age=300",
    }
    return StreamingResponse(iterator(), media_type=version.mime_type, headers=headers)
