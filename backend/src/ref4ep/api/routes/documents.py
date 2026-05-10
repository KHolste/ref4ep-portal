"""Dokumentenregister-Endpunkte (Sprint 2 + Sprint 3).

Internes Register: Anlegen, Listen, Detail, Metadaten-Patch,
Version-Upload (multipart) und kontrollierter Download (Streaming).
Sprint-3-Erweiterungen: Status- und Sichtbarkeits-Übergänge,
explizite Freigabe einer Version, Soft-Delete; jede schreibende
Aktion ist auditierbar. Öffentliche Bibliothek folgt erst
Sprint 4.
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
from sqlalchemy import select
from sqlalchemy.orm import Session

from ref4ep.api.config import Settings
from ref4ep.api.deps import (
    get_audit_logger,
    get_auth_context,
    get_session,
    get_settings,
    require_csrf,
)
from ref4ep.api.schemas.documents import (
    DocumentCampaignLinkOut,
    DocumentCreateRequest,
    DocumentDetailOut,
    DocumentOut,
    DocumentPatchRequest,
    DocumentReleaseRequest,
    DocumentStatusRequest,
    DocumentTestCampaignLinkRequest,
    DocumentVersionOut,
    DocumentVersionUploadResponse,
    DocumentVisibilityRequest,
    InternalDocumentOut,
    LibraryDocumentCreateRequest,
    PersonRef,
    WorkpackageRef,
)
from ref4ep.domain.models import Document, DocumentVersion
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.document_lifecycle_service import (
    DocumentLifecycleService,
    InvalidStatusTransitionError,
)
from ref4ep.services.document_service import DocumentNotFoundError, DocumentService
from ref4ep.services.document_version_service import DocumentVersionService
from ref4ep.services.permissions import AuthContext, can_write_document
from ref4ep.services.storage_validation import validate_change_note, validate_mime
from ref4ep.services.test_campaign_service import TestCampaignService
from ref4ep.services.workpackage_service import WorkpackageService
from ref4ep.storage import Storage

router = APIRouter(prefix="/api")

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
AuthDep = Annotated[AuthContext, Depends(get_auth_context)]
AuditDep = Annotated[AuditLogger, Depends(get_audit_logger)]
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
    released_version = next(
        (v for v in versions_sorted if v.id == document.released_version_id), None
    )
    wp_ref: WorkpackageRef | None = None
    if document.workpackage is not None:
        wp_ref = WorkpackageRef(code=document.workpackage.code, title=document.workpackage.title)
    base = DocumentOut(
        id=document.id,
        slug=document.slug,
        title=document.title,
        document_type=document.document_type,
        deliverable_code=document.deliverable_code,
        description=document.description,
        status=document.status,
        visibility=document.visibility,
        workpackage=wp_ref,
        library_section=document.library_section,
        created_by=PersonRef(
            email=document.created_by.email, display_name=document.created_by.display_name
        ),
        latest_version=_version_out(latest) if latest else None,
        released_version_id=document.released_version_id,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )
    if with_versions:
        return DocumentDetailOut(
            **base.model_dump(),
            versions=[_version_out(v) for v in versions_sorted],
            released_version=_version_out(released_version) if released_version else None,
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


def _internal_document_out(document: Document) -> InternalDocumentOut:
    """Kompaktes Mapping für die interne Auswahlliste (Block 0017).

    Block 0035: ``workpackage`` ist optional — Bibliotheks-Dokumente
    haben keinen WP-Bezug."""
    latest = document.versions[-1] if document.versions else None
    is_public = document.visibility == "public" and document.status == "released"
    wp = document.workpackage
    return InternalDocumentOut(
        id=document.id,
        code=document.deliverable_code,
        title=document.title,
        workpackage_code=wp.code if wp is not None else None,
        workpackage_title=wp.title if wp is not None else None,
        document_type=document.document_type,
        library_section=document.library_section,
        status=document.status,
        visibility=document.visibility,
        is_public=is_public,
        is_archived=document.is_deleted,
        latest_version_label=latest.version_label if latest else None,
        updated_at=document.updated_at,
    )


@router.get("/documents", response_model=list[InternalDocumentOut])
def list_internal_documents(
    session: SessionDep,
    auth: AuthDep,
    include_archived: bool = False,
    workpackage: str | None = None,
    q: str | None = None,
    library_section: str | None = None,
    without_workpackage: bool = False,
    enforce_visibility: bool = False,
    status_filter: str | None = None,
) -> list[InternalDocumentOut]:
    """Interne Dokumentliste für Auswahlfelder (Block 0017).

    Auth-only — alle eingeloggten Personen dürfen lesen. Filter:
    ``include_archived`` (default false), ``workpackage`` (WP-Code),
    ``q`` (Substring über Code/Title). Sortierung nach
    WP-``sort_order``, dann WP-Code, dann Dokument-Title.

    Anmerkung: Im Gegensatz zu ``/api/workpackages/{code}/documents``
    filtert diese Liste per Default **nicht** auf WP-Mitgliedschaft.
    Auswahllisten interner Module brauchen einen konsistenten Blick.
    Inhalt holt sich der Client weiterhin über
    ``GET /api/documents/{id}``, das die Sichtbarkeit prüft.

    Block 0035 ergänzt für die Projektbibliothek:
    - ``library_section`` filtert auf eine Kachel.
    - ``without_workpackage`` filtert auf Dokumente ohne WP-Bezug.
    - ``enforce_visibility`` (Default false) wendet
      ``can_read_document`` pro Dokument an. Die Bibliotheks-UI ruft
      mit ``true`` auf — andere Aufrufer (Auswahllisten) bleiben beim
      bestehenden Verhalten, weil sie inhaltlich nur Titel/Code zeigen.
    - ``status_filter`` schränkt auf einen Status ein.
    """
    try:
        docs = DocumentService(session, auth=auth).list_internal(
            include_archived=include_archived,
            workpackage_code=workpackage,
            q=q,
            library_section=library_section,
            without_workpackage=without_workpackage,
            enforce_visibility=enforce_visibility,
            status=status_filter,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "invalid", "message": str(exc)}},
        ) from exc
    return [_internal_document_out(d) for d in docs]


@router.post(
    "/library/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_library_document(
    payload: LibraryDocumentCreateRequest,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> DocumentOut:
    """Block 0035 — Anlage eines Bibliotheks-Dokuments ohne WP-Bezug.

    Nur Admin (im Service erzwungen). Die anschließende Versions-
    Anlage läuft über die bestehenden Versions-Routen.
    """
    try:
        document = DocumentService(session, auth=auth, audit=audit).create(
            workpackage_code=None,
            title=payload.title,
            document_type=payload.document_type,
            description=payload.description,
            library_section=payload.library_section,
            visibility=payload.visibility,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": str(exc)}},
        ) from exc
    except ValueError as exc:
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
    audit: AuditDep,
) -> DocumentOut:
    try:
        document = DocumentService(session, auth=auth, audit=audit).create(
            workpackage_code=code,
            title=payload.title,
            document_type=payload.document_type,
            deliverable_code=payload.deliverable_code,
            description=payload.description,
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


def _campaign_links_out(session: Session, document_id: str) -> list[DocumentCampaignLinkOut]:
    links = TestCampaignService(session).list_links_for_document(document_id)
    return [
        DocumentCampaignLinkOut(
            id=link.campaign.id,
            code=link.campaign.code,
            title=link.campaign.title,
            status=link.campaign.status,
            label=link.label,
        )
        for link in links
    ]


def _milestone_links_out(session: Session, document_id: str) -> list:
    """Block 0039 — Meilensteine, mit denen das Dokument verknüpft ist.

    Bewusst lokal in der Document-Route gehalten, damit der
    MilestoneDocumentService unabhängig bleibt; Sichtbarkeit ist
    durch ``get_by_id`` davor bereits abgedeckt."""
    from ref4ep.api.schemas.documents import DocumentMilestoneLinkOut
    from ref4ep.domain.models import Milestone, MilestoneDocumentLink

    rows = list(
        session.scalars(
            select(Milestone)
            .join(
                MilestoneDocumentLink,
                MilestoneDocumentLink.milestone_id == Milestone.id,
            )
            .where(MilestoneDocumentLink.document_id == document_id)
            .order_by(Milestone.planned_date, Milestone.code)
        )
    )
    return [
        DocumentMilestoneLinkOut(
            id=ms.id,
            code=ms.code,
            title=ms.title,
            planned_date=ms.planned_date,
            status=ms.status,
        )
        for ms in rows
    ]


def _document_detail_out(document: Document, session: Session) -> DocumentDetailOut:
    base = _document_out(document, with_versions=True)
    return base.model_copy(
        update={
            "test_campaigns": _campaign_links_out(session, document.id),
            "linked_milestones": _milestone_links_out(session, document.id),
        }
    )


@router.get("/documents/{document_id}", response_model=DocumentDetailOut)
def get_document(document_id: str, session: SessionDep, auth: AuthDep) -> DocumentDetailOut:
    try:
        document = DocumentService(session, auth=auth).get_by_id(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Dokument nicht gefunden."}},
        ) from exc
    return _document_detail_out(document, session)


def _resolve_writable_document(session: Session, auth: AuthContext, document_id: str) -> Document:
    """Lädt ein Dokument, prüft Sichtbarkeit (404) und Schreibrecht (403).

    Identische Schwelle wie ``PATCH /api/documents/{id}``.
    """
    try:
        document = DocumentService(session, auth=auth).get_by_id(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Dokument nicht gefunden."}},
        ) from exc
    if not can_write_document(auth, document):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "forbidden",
                    "message": "Nicht berechtigt, dieses Dokument zu ändern.",
                }
            },
        )
    return document


@router.post(
    "/documents/{document_id}/test-campaigns",
    response_model=DocumentDetailOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def link_document_test_campaign(
    document_id: str,
    payload: DocumentTestCampaignLinkRequest,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> DocumentDetailOut:
    document = _resolve_writable_document(session, auth, document_id)
    try:
        TestCampaignService(session, audit=audit).link_document(
            document, campaign_id=payload.campaign_id, label=payload.label
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
    return _document_detail_out(document, session)


@router.delete(
    "/documents/{document_id}/test-campaigns/{campaign_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def unlink_document_test_campaign(
    document_id: str,
    campaign_id: str,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> None:
    document = _resolve_writable_document(session, auth, document_id)
    try:
        TestCampaignService(session, audit=audit).unlink_document(document, campaign_id=campaign_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
        ) from exc
    return None


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
    audit: AuditDep,
) -> DocumentOut:
    try:
        document = DocumentService(session, auth=auth, audit=audit).update_metadata(
            document_id,
            title=payload.title,
            document_type=payload.document_type,
            deliverable_code=payload.deliverable_code,
            description=payload.description,
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
    audit: AuditDep,
    file: Annotated[UploadFile, File(...)],
    change_note: Annotated[str | None, Form()] = None,
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
    # Block 0036: Versionsnotiz ist optional. ``validate_change_note``
    # trimmt nur noch — keine Mindestlänge mehr.
    change_note = validate_change_note(change_note)

    max_bytes = settings.max_upload_mb * 1024 * 1024

    # Größenprüfung vorab über Content-Length (best effort) — dann hart über
    # einen wrapping-Stream während des eigentlichen Uploads.
    file_stream = _SizeLimitingStream(file.file, max_bytes)

    service = DocumentVersionService(session, auth=auth, storage=storage, audit=audit)
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


# --------------------------------------------------------------------------- #
# Sprint 3 — Lifecycle-Endpunkte                                              #
# --------------------------------------------------------------------------- #


def _lifecycle(session: Session, auth: AuthContext, audit: AuditLogger) -> DocumentLifecycleService:
    return DocumentLifecycleService(session, auth=auth, audit=audit)


def _handle_lifecycle_call(call):
    """Mappt Service-Exceptions auf HTTP-Codes."""
    try:
        return call()
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Dokument nicht gefunden."}},
        ) from exc
    except InvalidStatusTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "invalid_status_transition", "message": str(exc)}},
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


@router.post(
    "/documents/{document_id}/status",
    response_model=DocumentDetailOut,
    dependencies=[Depends(require_csrf)],
)
def set_status_endpoint(
    document_id: str,
    payload: DocumentStatusRequest,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> DocumentDetailOut:
    document = _handle_lifecycle_call(
        lambda: _lifecycle(session, auth, audit).set_status(document_id, to=payload.to)
    )
    return _document_detail_out(document, session)


@router.post(
    "/documents/{document_id}/release",
    response_model=DocumentDetailOut,
    dependencies=[Depends(require_csrf)],
)
def release_endpoint(
    document_id: str,
    payload: DocumentReleaseRequest,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> DocumentDetailOut:
    document = _handle_lifecycle_call(
        lambda: _lifecycle(session, auth, audit).release(
            document_id, version_number=payload.version_number
        )
    )
    return _document_detail_out(document, session)


@router.post(
    "/documents/{document_id}/unrelease",
    response_model=DocumentDetailOut,
    dependencies=[Depends(require_csrf)],
)
def unrelease_endpoint(
    document_id: str,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> DocumentDetailOut:
    document = _handle_lifecycle_call(
        lambda: _lifecycle(session, auth, audit).unrelease(document_id)
    )
    return _document_detail_out(document, session)


@router.post(
    "/documents/{document_id}/visibility",
    response_model=DocumentDetailOut,
    dependencies=[Depends(require_csrf)],
)
def set_visibility_endpoint(
    document_id: str,
    payload: DocumentVisibilityRequest,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> DocumentDetailOut:
    document = _handle_lifecycle_call(
        lambda: _lifecycle(session, auth, audit).set_visibility(document_id, to=payload.to)
    )
    return _document_detail_out(document, session)


@router.delete(
    "/documents/{document_id}",
    response_model=DocumentOut,
    dependencies=[Depends(require_csrf)],
)
def soft_delete_document(
    document_id: str,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> DocumentOut:
    """Soft-Delete: setzt is_deleted=true. Versionen + Storage bleiben."""
    try:
        document = DocumentService(session, auth=auth, audit=audit).soft_delete(document_id)
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
    return _document_out(document)
