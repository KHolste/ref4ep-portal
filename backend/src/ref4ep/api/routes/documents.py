"""Dokumentenregister-Endpunkte (Sprint 2).

Internes Register: Anlegen, Listen, Detail, Metadaten-Patch,
Version-Upload (multipart) und kontrollierter Download (Streaming).
Öffentliche Bibliothek folgt erst Sprint 4.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ref4ep.api.config import Settings
from ref4ep.api.deps import get_auth_context, get_session, get_settings, require_csrf
from ref4ep.api.schemas.documents import (
    DocumentCreateRequest,
    DocumentDetailOut,
    DocumentOut,
    DocumentPatchRequest,
    DocumentVersionOut,
    DocumentVersionUploadResponse,
    PersonRef,
    WorkpackageRef,
)
from ref4ep.domain.models import Document, DocumentVersion
from ref4ep.services.document_service import DocumentNotFoundError, DocumentService
from ref4ep.services.document_version_service import DocumentVersionService
from ref4ep.services.permissions import AuthContext
from ref4ep.services.storage_validation import validate_change_note, validate_mime
from ref4ep.services.workpackage_service import WorkpackageService
from ref4ep.storage import Storage

router = APIRouter(prefix="/api")

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
AuthDep = Annotated[AuthContext, Depends(get_auth_context)]
CHUNK_SIZE = 1024 * 1024


def _get_storage(request: Request) -> Storage:
    return request.app.state.storage


StorageDep = Annotated[Storage, Depends(_get_storage)]


# --------------------------------------------------------------------------- #
# Mapping ORM → Out                                                           #
# --------------------------------------------------------------------------- #


def _version_out(version: DocumentVersion) -> DocumentVersionOut:
    return DocumentVersionOut(
        id=version.id,
        version_number=version.version_number,
        version_label=version.version_label,
        change_note=version.change_note,
        original_filename=version.original_filename,
        mime_type=version.mime_type,
        file_size_bytes=version.file_size_bytes,
        sha256=version.sha256,
        uploaded_by=PersonRef(
            email=version.uploaded_by.email,
            display_name=version.uploaded_by.display_name,
        ),
        uploaded_at=version.uploaded_at,
    )


def _document_out(document: Document, *, with_versions: bool = False) -> DocumentOut:
    versions_sorted = sorted(document.versions, key=lambda v: v.version_number)
    latest = versions_sorted[-1] if versions_sorted else None
    base = DocumentOut(
        id=document.id,
        slug=document.slug,
        title=document.title,
        document_type=document.document_type,
        deliverable_code=document.deliverable_code,
        status=document.status,
        visibility=document.visibility,
        workpackage=WorkpackageRef(
            code=document.workpackage.code, title=document.workpackage.title
        ),
        created_by=PersonRef(
            email=document.created_by.email, display_name=document.created_by.display_name
        ),
        latest_version=_version_out(latest) if latest else None,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )
    if with_versions:
        return DocumentDetailOut(
            **base.model_dump(),
            versions=[_version_out(v) for v in versions_sorted],
        )
    return base


# --------------------------------------------------------------------------- #
# Endpunkte                                                                   #
# --------------------------------------------------------------------------- #


@router.get(
    "/workpackages/{code}/documents",
    response_model=list[DocumentOut],
)
def list_documents(code: str, session: SessionDep, auth: AuthDep) -> list[DocumentOut]:
    if WorkpackageService(session).get_by_code(code) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Workpackage nicht gefunden."}},
        )
    docs = DocumentService(session, auth=auth).list_for_workpackage(code)
    return [_document_out(d) for d in docs]


@router.post(
    "/workpackages/{code}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_document(
    code: str,
    payload: DocumentCreateRequest,
    session: SessionDep,
    auth: AuthDep,
) -> DocumentOut:
    try:
        document = DocumentService(session, auth=auth).create(
            workpackage_code=code,
            title=payload.title,
            document_type=payload.document_type,
            deliverable_code=payload.deliverable_code,
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
        # Slug-Kollision vom Service als ValueError signalisiert
        message = str(exc)
        if "existiert" in message and "bereits" in message:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": {"code": "slug_conflict", "message": message}},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "invalid", "message": message}},
        ) from exc
    return _document_out(document)


@router.get("/documents/{document_id}", response_model=DocumentDetailOut)
def get_document(document_id: str, session: SessionDep, auth: AuthDep) -> DocumentDetailOut:
    try:
        document = DocumentService(session, auth=auth).get_by_id(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Dokument nicht gefunden."}},
        ) from exc
    return _document_out(document, with_versions=True)


@router.patch(
    "/documents/{document_id}",
    response_model=DocumentOut,
    dependencies=[Depends(require_csrf)],
)
def patch_document(
    document_id: str,
    payload: DocumentPatchRequest,
    session: SessionDep,
    auth: AuthDep,
) -> DocumentOut:
    try:
        document = DocumentService(session, auth=auth).update_metadata(
            document_id,
            title=payload.title,
            document_type=payload.document_type,
            deliverable_code=payload.deliverable_code,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Dokument nicht gefunden."}},
        ) from exc
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
    return _document_out(document)


@router.get("/documents/{document_id}/versions", response_model=list[DocumentVersionOut])
def list_versions(document_id: str, session: SessionDep, auth: AuthDep) -> list[DocumentVersionOut]:
    try:
        versions = DocumentVersionService(session, auth=auth).list_for_document(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Dokument nicht gefunden."}},
        ) from exc
    return [_version_out(v) for v in versions]


@router.post(
    "/documents/{document_id}/versions",
    response_model=DocumentVersionUploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def upload_version(
    document_id: str,
    session: SessionDep,
    auth: AuthDep,
    settings: SettingsDep,
    storage: StorageDep,
    file: Annotated[UploadFile, File(...)],
    change_note: Annotated[str, Form()],
    version_label: Annotated[str | None, Form()] = None,
) -> DocumentVersionUploadResponse:
    # Eingangsvalidierung VOR dem Storage-Aufruf — verhindert vergebliches Schreiben.
    mime_type = (file.content_type or "").lower()
    try:
        validate_mime(mime_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"error": {"code": "unsupported_media_type", "message": str(exc)}},
        ) from exc
    try:
        validate_change_note(change_note)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "invalid_change_note", "message": str(exc)}},
        ) from exc

    max_bytes = settings.max_upload_mb * 1024 * 1024

    # Größenprüfung vorab über Content-Length (best effort) — dann hart über
    # einen wrapping-Stream während des eigentlichen Uploads.
    file_stream = _SizeLimitingStream(file.file, max_bytes)

    service = DocumentVersionService(session, auth=auth, storage=storage)
    try:
        version, warnings = service.upload_new_version(
            document_id,
            file_stream=file_stream,
            original_filename=file.filename or "unbenannt",
            mime_type=mime_type,
            change_note=change_note,
            version_label=version_label,
        )
    except _PayloadTooLarge as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={"error": {"code": "payload_too_large", "message": str(exc)}},
        ) from exc
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Dokument nicht gefunden."}},
        ) from exc
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

    return DocumentVersionUploadResponse(version=_version_out(version), warnings=warnings)


@router.get("/documents/{document_id}/versions/{version_number}/download")
def download_version(
    document_id: str,
    version_number: int,
    session: SessionDep,
    auth: AuthDep,
    storage: StorageDep,
) -> StreamingResponse:
    try:
        version = DocumentVersionService(session, auth=auth).get_for_download(
            document_id, version_number
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Version nicht gefunden."}},
        ) from exc

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
    }
    return StreamingResponse(iterator(), media_type=version.mime_type, headers=headers)


# --------------------------------------------------------------------------- #
# Hilfsklassen                                                                #
# --------------------------------------------------------------------------- #


class _PayloadTooLarge(Exception):
    pass


class _SizeLimitingStream:
    """File-like-Wrapper, der nach ``max_bytes`` einen Fehler wirft."""

    def __init__(self, inner, max_bytes: int) -> None:
        self._inner = inner
        self._max = max_bytes
        self._read = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self._inner.read(size)
        if not chunk:
            return chunk
        self._read += len(chunk)
        if self._read > self._max:
            raise _PayloadTooLarge(f"Upload überschreitet Limit von {self._max} Bytes.")
        return chunk
