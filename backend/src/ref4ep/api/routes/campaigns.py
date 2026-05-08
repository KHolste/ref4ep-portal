"""Testkampagnen-API (Block 0022).

Lesen ist auth-only; Schreiben CSRF + Service-Permission.
``TestCampaignService`` kapselt die Berechtigungslogik (Admin oder
WP-Lead aller beteiligten WPs).

Es gibt **keinen** Hard-Delete und **keinen** Datei-Upload — Dokumente
werden ausschließlich über das bestehende Dokumentenregister verlinkt.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, BinaryIO

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ref4ep.api.config import Settings
from ref4ep.api.deps import (
    get_audit_logger,
    get_auth_context,
    get_current_person,
    get_session,
    get_settings,
    require_csrf,
)
from ref4ep.api.schemas.campaigns import (
    CampaignCreateRequest,
    CampaignDetailOut,
    CampaignDocumentLinkAddRequest,
    CampaignDocumentOut,
    CampaignListItemOut,
    CampaignNoteCreateRequest,
    CampaignNoteOut,
    CampaignNoteUpdateRequest,
    CampaignParticipantAddRequest,
    CampaignParticipantOut,
    CampaignParticipantPatchRequest,
    CampaignPatchRequest,
    CampaignPersonOut,
    CampaignPhotoCaptionRequest,
    CampaignPhotoOut,
    CampaignWorkpackageOut,
)
from ref4ep.domain.models import (
    Person,
    TestCampaign,
    TestCampaignNote,
    TestCampaignParticipant,
    TestCampaignPhoto,
)
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.permissions import AuthContext
from ref4ep.services.test_campaign_note_service import (
    CampaignNoteNotFoundError,
    TestCampaignNoteService,
)
from ref4ep.services.test_campaign_note_service import (
    CampaignNotFoundError as CampaignNotFoundForNoteError,
)
from ref4ep.services.test_campaign_photo_service import (
    CampaignNotFoundError,
    CampaignPhotoNotFoundError,
    TestCampaignPhotoService,
)
from ref4ep.services.test_campaign_service import TestCampaignService
from ref4ep.storage import Storage

router = APIRouter(prefix="/api")

SessionDep = Annotated[Session, Depends(get_session)]
ActorDep = Annotated[Person, Depends(get_current_person)]
AuditDep = Annotated[AuditLogger, Depends(get_audit_logger)]
AuthDep = Annotated[AuthContext, Depends(get_auth_context)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _get_storage(request: Request) -> Storage:
    return request.app.state.storage


StorageDep = Annotated[Storage, Depends(_get_storage)]
CHUNK_SIZE = 1024 * 1024


# ---- Block 0028 — Foto-Upload-Helfer ---------------------------------
# Lokale Duplikation der Upload-Wrapper aus ``api/routes/documents.py``,
# bewusst ohne Cross-Module-Import privater Symbole. Eine spätere
# Konsolidierung wäre ein eigener Refactor-Patch.


class _PayloadTooLarge(Exception):
    pass


class _SizeLimitingStream:
    """File-like-Wrapper, der nach ``max_bytes`` einen Fehler wirft."""

    def __init__(self, inner: BinaryIO, max_bytes: int) -> None:
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


def _service(
    session: Session, actor: Person, *, audit: AuditLogger | None = None
) -> TestCampaignService:
    return TestCampaignService(
        session,
        role=actor.platform_role,
        person_id=actor.id,
        audit=audit,
    )


def _person_out(person: Person) -> CampaignPersonOut:
    return CampaignPersonOut(id=person.id, display_name=person.display_name, email=person.email)


def _wps_out(campaign: TestCampaign) -> list[CampaignWorkpackageOut]:
    return [
        CampaignWorkpackageOut(code=link.workpackage.code, title=link.workpackage.title)
        for link in sorted(campaign.workpackage_links, key=lambda link: link.workpackage.sort_order)
    ]


def _participant_out(participant: TestCampaignParticipant) -> CampaignParticipantOut:
    return CampaignParticipantOut(
        id=participant.id,
        person=_person_out(participant.person),
        role=participant.role,
        note=participant.note,
    )


def _document_out(link) -> CampaignDocumentOut:
    return CampaignDocumentOut(
        document_id=link.document_id,
        title=link.document.title,
        deliverable_code=link.document.deliverable_code,
        workpackage_code=link.document.workpackage.code if link.document.workpackage else None,
        label=link.label,
    )


def _list_item(campaign: TestCampaign, *, can_edit: bool) -> CampaignListItemOut:
    return CampaignListItemOut(
        id=campaign.id,
        code=campaign.code,
        title=campaign.title,
        category=campaign.category,
        status=campaign.status,
        starts_on=campaign.starts_on,
        ends_on=campaign.ends_on,
        facility=campaign.facility,
        workpackages=_wps_out(campaign),
        participants_count=len(campaign.participant_links),
        documents_count=len(campaign.document_links),
        can_edit=can_edit,
    )


def _can_upload_photo(campaign: TestCampaign, actor: Person) -> bool:
    if actor.platform_role == "admin":
        return True
    return any(link.person_id == actor.id for link in campaign.participant_links)


def _can_create_note(campaign: TestCampaign, actor: Person) -> bool:
    """Block 0029 — Notiz anlegen darf wer Foto hochladen darf
    (Teilnehmer + Admin). Eigene Funktion für semantische Klarheit;
    aktuell deckungsgleich mit ``_can_upload_photo``."""
    return _can_upload_photo(campaign, actor)


def _detail(
    campaign: TestCampaign,
    *,
    can_edit: bool,
    can_upload_photo: bool = False,
    can_create_note: bool = False,
) -> CampaignDetailOut:
    return CampaignDetailOut(
        id=campaign.id,
        code=campaign.code,
        title=campaign.title,
        category=campaign.category,
        status=campaign.status,
        starts_on=campaign.starts_on,
        ends_on=campaign.ends_on,
        facility=campaign.facility,
        location=campaign.location,
        short_description=campaign.short_description,
        objective=campaign.objective,
        test_matrix=campaign.test_matrix,
        expected_measurements=campaign.expected_measurements,
        boundary_conditions=campaign.boundary_conditions,
        success_criteria=campaign.success_criteria,
        risks_or_open_points=campaign.risks_or_open_points,
        created_by=_person_out(campaign.created_by),
        workpackages=_wps_out(campaign),
        participants=[_participant_out(p) for p in campaign.participant_links],
        documents=[_document_out(d) for d in campaign.document_links],
        can_edit=can_edit,
        can_upload_photo=can_upload_photo,
        can_create_note=can_create_note,
    )


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": str(exc)}},
        )
    if isinstance(exc, LookupError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
        )
    if isinstance(exc, ValueError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "invalid", "message": str(exc)}},
        )
    raise exc


# ---- Kampagnen --------------------------------------------------------


@router.get("/campaigns", response_model=list[CampaignListItemOut])
def list_campaigns(
    actor: ActorDep,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status"),
    category: str | None = None,
    workpackage: str | None = None,
    q: str | None = None,
) -> list[CampaignListItemOut]:
    service = _service(session, actor)
    try:
        campaigns = service.list_campaigns(
            status=status_filter,
            category=category,
            workpackage_code=workpackage,
            q=q,
        )
    except ValueError as exc:
        raise _http_error(exc) from exc
    return [_list_item(c, can_edit=service.can_edit_campaign(c)) for c in campaigns]


@router.post(
    "/campaigns",
    response_model=CampaignDetailOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_campaign(
    payload: CampaignCreateRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> CampaignDetailOut:
    service = _service(session, actor, audit=audit)
    try:
        campaign = service.create_campaign(
            code=payload.code,
            title=payload.title,
            category=payload.category,
            status=payload.status,
            starts_on=payload.starts_on,
            ends_on=payload.ends_on,
            facility=payload.facility,
            location=payload.location,
            short_description=payload.short_description,
            objective=payload.objective,
            test_matrix=payload.test_matrix,
            expected_measurements=payload.expected_measurements,
            boundary_conditions=payload.boundary_conditions,
            success_criteria=payload.success_criteria,
            risks_or_open_points=payload.risks_or_open_points,
            workpackage_ids=payload.workpackage_ids,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return _detail(
        campaign,
        can_edit=True,
        can_upload_photo=_can_upload_photo(campaign, actor),
        can_create_note=_can_create_note(campaign, actor),
    )


@router.get("/campaigns/{campaign_id}", response_model=CampaignDetailOut)
def get_campaign(campaign_id: str, actor: ActorDep, session: SessionDep) -> CampaignDetailOut:
    service = _service(session, actor)
    campaign = service.get(campaign_id)
    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Testkampagne nicht gefunden."}},
        )
    return _detail(
        campaign,
        can_edit=service.can_edit_campaign(campaign),
        can_upload_photo=_can_upload_photo(campaign, actor),
        can_create_note=_can_create_note(campaign, actor),
    )


@router.patch(
    "/campaigns/{campaign_id}",
    response_model=CampaignDetailOut,
    dependencies=[Depends(require_csrf)],
)
def patch_campaign(
    campaign_id: str,
    payload: CampaignPatchRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> CampaignDetailOut:
    service = _service(session, actor, audit=audit)
    raw = payload.model_dump(exclude_unset=True)
    workpackage_ids = raw.pop("workpackage_ids", None)
    try:
        campaign = service.update_campaign(
            campaign_id,
            fields=raw,
            workpackage_ids=workpackage_ids,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return _detail(
        campaign,
        can_edit=True,
        can_upload_photo=_can_upload_photo(campaign, actor),
        can_create_note=_can_create_note(campaign, actor),
    )


@router.post(
    "/campaigns/{campaign_id}/cancel",
    response_model=CampaignDetailOut,
    dependencies=[Depends(require_csrf)],
)
def cancel_campaign(
    campaign_id: str,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> CampaignDetailOut:
    service = _service(session, actor, audit=audit)
    try:
        campaign = service.cancel_campaign(campaign_id)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return _detail(
        campaign,
        can_edit=True,
        can_upload_photo=_can_upload_photo(campaign, actor),
        can_create_note=_can_create_note(campaign, actor),
    )


# ---- Teilnehmende -----------------------------------------------------


@router.post(
    "/campaigns/{campaign_id}/participants",
    response_model=CampaignDetailOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def add_campaign_participant(
    campaign_id: str,
    payload: CampaignParticipantAddRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> CampaignDetailOut:
    service = _service(session, actor, audit=audit)
    try:
        service.add_participant(
            campaign_id,
            person_id=payload.person_id,
            role=payload.role,
            note=payload.note,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    campaign = service.get(campaign_id)
    return _detail(
        campaign,
        can_edit=True,
        can_upload_photo=_can_upload_photo(campaign, actor),
        can_create_note=_can_create_note(campaign, actor),
    )


@router.patch(
    "/campaign-participants/{participant_id}",
    response_model=CampaignParticipantOut,
    dependencies=[Depends(require_csrf)],
)
def patch_campaign_participant(
    participant_id: str,
    payload: CampaignParticipantPatchRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> CampaignParticipantOut:
    service = _service(session, actor, audit=audit)
    fields = payload.model_dump(exclude_unset=True)
    try:
        participant = service.update_participant(participant_id, fields=fields)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return _participant_out(participant)


@router.delete(
    "/campaign-participants/{participant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def remove_campaign_participant(
    participant_id: str,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> Response:
    service = _service(session, actor, audit=audit)
    try:
        service.remove_participant(participant_id)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- Dokumentverknüpfungen --------------------------------------------


@router.post(
    "/campaigns/{campaign_id}/documents",
    response_model=CampaignDetailOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def link_campaign_document(
    campaign_id: str,
    payload: CampaignDocumentLinkAddRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> CampaignDetailOut:
    service = _service(session, actor, audit=audit)
    try:
        service.add_document_link(campaign_id, document_id=payload.document_id, label=payload.label)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    campaign = service.get(campaign_id)
    return _detail(
        campaign,
        can_edit=True,
        can_upload_photo=_can_upload_photo(campaign, actor),
        can_create_note=_can_create_note(campaign, actor),
    )


@router.delete(
    "/campaigns/{campaign_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def unlink_campaign_document(
    campaign_id: str,
    document_id: str,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> Response:
    service = _service(session, actor, audit=audit)
    try:
        service.remove_document_link(campaign_id, document_id)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# Block 0028 — Foto-Upload für Testkampagnen                                  #
# --------------------------------------------------------------------------- #


def _photo_service(
    session: Session,
    auth: AuthContext,
    *,
    audit: AuditLogger | None = None,
    storage: Storage | None = None,
) -> TestCampaignPhotoService:
    return TestCampaignPhotoService(session, auth=auth, audit=audit, storage=storage)


def _photo_out(photo: TestCampaignPhoto, auth: AuthContext) -> CampaignPhotoOut:
    can_edit = auth.platform_role == "admin" or auth.person_id == photo.uploaded_by_person_id
    return CampaignPhotoOut(
        id=photo.id,
        original_filename=photo.original_filename,
        mime_type=photo.mime_type,
        file_size_bytes=photo.file_size_bytes,
        sha256=photo.sha256,
        caption=photo.caption,
        taken_at=photo.taken_at,
        uploaded_by=_person_out(photo.uploaded_by),
        created_at=photo.created_at,
        updated_at=photo.updated_at,
        can_edit=can_edit,
    )


@router.get(
    "/campaigns/{campaign_id}/photos",
    response_model=list[CampaignPhotoOut],
)
def list_campaign_photos(
    campaign_id: str,
    _: ActorDep,
    auth: AuthDep,
    session: SessionDep,
) -> list[CampaignPhotoOut]:
    try:
        photos = _photo_service(session, auth).list_for_campaign(campaign_id)
    except CampaignNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
        ) from exc
    return [_photo_out(p, auth) for p in photos]


@router.post(
    "/campaigns/{campaign_id}/photos",
    response_model=CampaignPhotoOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def upload_campaign_photo(
    campaign_id: str,
    auth: AuthDep,
    session: SessionDep,
    settings: SettingsDep,
    storage: StorageDep,
    audit: AuditDep,
    file: Annotated[UploadFile, File(...)],
    caption: Annotated[str | None, Form()] = None,
    taken_at: Annotated[str | None, Form()] = None,
) -> CampaignPhotoOut:
    mime_type = (file.content_type or "").lower()

    parsed_taken_at: datetime | None = None
    if taken_at:
        try:
            parsed_taken_at = datetime.fromisoformat(taken_at)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"error": {"code": "invalid_taken_at", "message": str(exc)}},
            ) from exc

    max_bytes = settings.max_upload_mb * 1024 * 1024
    file_stream = _SizeLimitingStream(file.file, max_bytes)

    try:
        photo = _photo_service(session, auth, audit=audit, storage=storage).upload(
            campaign_id,
            file_stream=file_stream,
            original_filename=file.filename or "unbenannt",
            mime_type=mime_type,
            caption=caption,
            taken_at=parsed_taken_at,
        )
    except _PayloadTooLarge as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={"error": {"code": "payload_too_large", "message": str(exc)}},
        ) from exc
    except CampaignNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": str(exc)}},
        ) from exc
    except ValueError as exc:
        # Falsche MIME-Whitelist → 415, leere Datei → 422.
        message = str(exc)
        if "MIME" in message or "mime" in message:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail={"error": {"code": "unsupported_media_type", "message": message}},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "invalid", "message": message}},
        ) from exc
    return _photo_out(photo, auth)


@router.patch(
    "/campaigns/{campaign_id}/photos/{photo_id}",
    response_model=CampaignPhotoOut,
    dependencies=[Depends(require_csrf)],
)
def patch_campaign_photo_caption(
    campaign_id: str,
    photo_id: str,
    payload: CampaignPhotoCaptionRequest,
    auth: AuthDep,
    session: SessionDep,
    audit: AuditDep,
) -> CampaignPhotoOut:
    try:
        photo = _photo_service(session, auth, audit=audit).update_caption(
            photo_id, caption=payload.caption
        )
    except CampaignPhotoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": str(exc)}},
        ) from exc
    return _photo_out(photo, auth)


@router.delete(
    "/campaigns/{campaign_id}/photos/{photo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def delete_campaign_photo(
    campaign_id: str,
    photo_id: str,
    auth: AuthDep,
    session: SessionDep,
    audit: AuditDep,
) -> Response:
    try:
        _photo_service(session, auth, audit=audit).soft_delete(photo_id)
    except CampaignPhotoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": str(exc)}},
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/campaigns/{campaign_id}/photos/{photo_id}/download")
def download_campaign_photo(
    campaign_id: str,
    photo_id: str,
    auth: AuthDep,
    session: SessionDep,
    storage: StorageDep,
) -> StreamingResponse:
    try:
        photo, fh = _photo_service(session, auth, storage=storage).open_read_stream(photo_id)
    except CampaignPhotoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
        ) from exc

    def iterator():
        try:
            while True:
                chunk = fh.read(CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
        finally:
            fh.close()

    safe_name = photo.original_filename.replace('"', "")
    headers = {
        "Content-Disposition": f'inline; filename="{safe_name}"',
        "Content-Length": str(photo.file_size_bytes),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private",
    }
    return StreamingResponse(iterator(), media_type=photo.mime_type, headers=headers)


# --------------------------------------------------------------------------- #
# Block 0029 — Kampagnennotizen                                               #
# --------------------------------------------------------------------------- #


def _note_service(
    session: Session,
    auth: AuthContext,
    *,
    audit: AuditLogger | None = None,
) -> TestCampaignNoteService:
    return TestCampaignNoteService(session, auth=auth, audit=audit)


def _note_out(note: TestCampaignNote, auth: AuthContext) -> CampaignNoteOut:
    can_edit = auth.platform_role == "admin" or auth.person_id == note.author_person_id
    return CampaignNoteOut(
        id=note.id,
        campaign_id=note.campaign_id,
        body_md=note.body_md,
        author=_person_out(note.author),
        created_at=note.created_at,
        updated_at=note.updated_at,
        can_edit=can_edit,
    )


@router.get(
    "/campaigns/{campaign_id}/notes",
    response_model=list[CampaignNoteOut],
)
def list_campaign_notes(
    campaign_id: str,
    _: ActorDep,
    auth: AuthDep,
    session: SessionDep,
) -> list[CampaignNoteOut]:
    try:
        notes = _note_service(session, auth).list_for_campaign(campaign_id)
    except CampaignNotFoundForNoteError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
        ) from exc
    return [_note_out(n, auth) for n in notes]


@router.post(
    "/campaigns/{campaign_id}/notes",
    response_model=CampaignNoteOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_campaign_note(
    campaign_id: str,
    payload: CampaignNoteCreateRequest,
    auth: AuthDep,
    session: SessionDep,
    audit: AuditDep,
) -> CampaignNoteOut:
    try:
        note = _note_service(session, auth, audit=audit).create(
            campaign_id, body_md=payload.body_md
        )
    except CampaignNotFoundForNoteError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
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
    return _note_out(note, auth)


@router.patch(
    "/campaign-notes/{note_id}",
    response_model=CampaignNoteOut,
    dependencies=[Depends(require_csrf)],
)
def patch_campaign_note(
    note_id: str,
    payload: CampaignNoteUpdateRequest,
    auth: AuthDep,
    session: SessionDep,
    audit: AuditDep,
) -> CampaignNoteOut:
    try:
        note = _note_service(session, auth, audit=audit).update(note_id, body_md=payload.body_md)
    except CampaignNoteNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
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
    return _note_out(note, auth)


@router.delete(
    "/campaign-notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def delete_campaign_note(
    note_id: str,
    auth: AuthDep,
    session: SessionDep,
    audit: AuditDep,
) -> Response:
    try:
        _note_service(session, auth, audit=audit).soft_delete(note_id)
    except CampaignNoteNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": str(exc)}},
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
