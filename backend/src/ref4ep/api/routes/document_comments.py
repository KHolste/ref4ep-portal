"""Routen für Dokumentkommentare auf Versionsebene (Block 0024).

Endpunkte:
- ``GET    /api/document-versions/{version_id}/comments``  — Liste pro Version
- ``POST   /api/document-versions/{version_id}/comments``  — neuer Kommentar
- ``GET    /api/document-comments``                        — globale Übersicht (filterbar)
- ``GET    /api/document-comments/{comment_id}``           — Single-Read
- ``PATCH  /api/document-comments/{comment_id}``           — Text editieren (open + Autor)
- ``POST   /api/document-comments/{comment_id}/submit``    — open → submitted
- ``DELETE /api/document-comments/{comment_id}``           — Soft-Delete (Admin)

Existenz-Leak-Schutz: nicht sichtbare Kommentare oder Versionen
liefern 404, nicht 403. Schreibrecht-Verstöße liefern 403.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ref4ep.api.deps import (
    get_audit_logger,
    get_auth_context,
    get_session,
    require_csrf,
)
from ref4ep.api.schemas.document_comments import (
    DocumentCommentCreateRequest,
    DocumentCommentOut,
    DocumentCommentUpdateRequest,
    DocumentCommentVersionRef,
)
from ref4ep.api.schemas.documents import PersonRef
from ref4ep.domain.models import DocumentComment
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.document_comment_service import (
    DocumentCommentNotFoundError,
    DocumentCommentService,
    DocumentVersionNotFoundError,
)
from ref4ep.services.permissions import AuthContext

router = APIRouter(prefix="/api")

SessionDep = Annotated[Session, Depends(get_session)]
AuthDep = Annotated[AuthContext, Depends(get_auth_context)]
AuditDep = Annotated[AuditLogger, Depends(get_audit_logger)]


def _comment_out(comment: DocumentComment) -> DocumentCommentOut:
    version = comment.document_version
    return DocumentCommentOut(
        id=comment.id,
        document_version=DocumentCommentVersionRef(
            id=version.id,
            version_number=version.version_number,
            document_id=version.document_id,
        ),
        author=PersonRef(
            email=comment.author.email,
            display_name=comment.author.display_name,
        ),
        text=comment.text,
        status=comment.status,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        submitted_at=comment.submitted_at,
    )


def _service(session: Session, auth: AuthContext, audit: AuditLogger | None = None):
    return DocumentCommentService(session, auth=auth, audit=audit)


# --------------------------------------------------------------------------- #
# Pro Version: Liste + Anlegen                                                #
# --------------------------------------------------------------------------- #


@router.get(
    "/document-versions/{version_id}/comments",
    response_model=list[DocumentCommentOut],
)
def list_comments_for_version(
    version_id: str, session: SessionDep, auth: AuthDep
) -> list[DocumentCommentOut]:
    try:
        comments = _service(session, auth).list_for_version(version_id)
    except DocumentVersionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
        ) from exc
    return [_comment_out(c) for c in comments]


@router.post(
    "/document-versions/{version_id}/comments",
    response_model=DocumentCommentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_comment(
    version_id: str,
    payload: DocumentCommentCreateRequest,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> DocumentCommentOut:
    try:
        comment = _service(session, auth, audit).create(version_id, text=payload.text)
    except DocumentVersionNotFoundError as exc:
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
    return _comment_out(comment)


# --------------------------------------------------------------------------- #
# Globale Übersicht                                                           #
# --------------------------------------------------------------------------- #


@router.get("/document-comments", response_model=list[DocumentCommentOut])
def list_comments_global(
    session: SessionDep,
    auth: AuthDep,
    document_version_id: str | None = Query(default=None),
    author_person_id: str | None = Query(default=None),
    status_filter: Literal["open", "submitted"] | None = Query(default=None, alias="status"),
) -> list[DocumentCommentOut]:
    try:
        comments = _service(session, auth).list_global(
            document_version_id=document_version_id,
            author_person_id=author_person_id,
            status=status_filter,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "invalid", "message": str(exc)}},
        ) from exc
    return [_comment_out(c) for c in comments]


# --------------------------------------------------------------------------- #
# Single-Comment: Read / Patch / Submit / Delete                              #
# --------------------------------------------------------------------------- #


@router.get("/document-comments/{comment_id}", response_model=DocumentCommentOut)
def get_comment(comment_id: str, session: SessionDep, auth: AuthDep) -> DocumentCommentOut:
    try:
        comment = _service(session, auth).get_visible(comment_id)
    except DocumentCommentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
        ) from exc
    return _comment_out(comment)


@router.patch(
    "/document-comments/{comment_id}",
    response_model=DocumentCommentOut,
    dependencies=[Depends(require_csrf)],
)
def update_comment(
    comment_id: str,
    payload: DocumentCommentUpdateRequest,
    session: SessionDep,
    auth: AuthDep,
    audit: AuditDep,
) -> DocumentCommentOut:
    try:
        comment = _service(session, auth, audit).update(comment_id, text=payload.text)
    except DocumentCommentNotFoundError as exc:
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
    return _comment_out(comment)


@router.post(
    "/document-comments/{comment_id}/submit",
    response_model=DocumentCommentOut,
    dependencies=[Depends(require_csrf)],
)
def submit_comment(
    comment_id: str, session: SessionDep, auth: AuthDep, audit: AuditDep
) -> DocumentCommentOut:
    try:
        comment = _service(session, auth, audit).submit(comment_id)
    except DocumentCommentNotFoundError as exc:
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
    return _comment_out(comment)


@router.delete(
    "/document-comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def delete_comment(
    comment_id: str, session: SessionDep, auth: AuthDep, audit: AuditDep
) -> Response:
    try:
        _service(session, auth, audit).soft_delete(comment_id)
    except DocumentCommentNotFoundError as exc:
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
