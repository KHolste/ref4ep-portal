"""Schemas für das Dokumentenregister (Sprint 2 + Sprint 3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from ref4ep.api.schemas.identity import PartnerRefOut


class WorkpackageRef(BaseModel):
    code: str
    title: str


class PersonRef(BaseModel):
    email: str
    display_name: str


class DocumentVersionOut(BaseModel):
    id: str
    version_number: int
    version_label: str | None
    change_note: str
    original_filename: str
    mime_type: str
    file_size_bytes: int
    sha256: str
    uploaded_by: PersonRef
    uploaded_at: datetime


class DocumentOut(BaseModel):
    id: str
    slug: str
    title: str
    document_type: str
    deliverable_code: str | None
    description: str | None = None
    status: str
    visibility: str
    workpackage: WorkpackageRef
    created_by: PersonRef
    latest_version: DocumentVersionOut | None
    released_version_id: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentDetailOut(DocumentOut):
    versions: list[DocumentVersionOut]
    released_version: DocumentVersionOut | None = None


class DocumentCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    document_type: str
    deliverable_code: str | None = None
    description: str | None = None


class DocumentPatchRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    document_type: str | None = None
    deliverable_code: str | None = None
    description: str | None = None


class DocumentVersionUploadResponse(BaseModel):
    version: DocumentVersionOut
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Sprint-3-Lifecycle-Requests                                                  #
# --------------------------------------------------------------------------- #


class DocumentStatusRequest(BaseModel):
    to: Literal["draft", "in_review"]


class DocumentReleaseRequest(BaseModel):
    version_number: int = Field(gt=0)


class DocumentVisibilityRequest(BaseModel):
    to: Literal["workpackage", "internal", "public"]


# --------------------------------------------------------------------------- #
# Audit-Schema                                                                 #
# --------------------------------------------------------------------------- #


class AuditActorOut(BaseModel):
    person_id: str | None
    email: str | None
    display_name: str | None
    label: str | None


class AuditLogOut(BaseModel):
    id: str
    created_at: datetime
    actor: AuditActorOut
    action: str
    entity_type: str
    entity_id: str
    details: dict[str, Any] | None
    client_ip: str | None
    request_id: str | None


# --------------------------------------------------------------------------- #
# Sprint-4-Schema: öffentliche Sicht (anonym)                                  #
# --------------------------------------------------------------------------- #


class PublicDocumentVersionOut(BaseModel):
    version_number: int
    version_label: str | None
    original_filename: str
    mime_type: str
    file_size_bytes: int
    sha256: str
    uploaded_at: datetime


class PublicDocumentOut(BaseModel):
    slug: str
    title: str
    document_type: str
    deliverable_code: str | None
    workpackage: WorkpackageRef
    released_version: PublicDocumentVersionOut
    released_at: datetime
    download_url: str


__all__ = [
    "AuditActorOut",
    "AuditLogOut",
    "DocumentCreateRequest",
    "DocumentDetailOut",
    "DocumentOut",
    "DocumentPatchRequest",
    "DocumentReleaseRequest",
    "DocumentStatusRequest",
    "DocumentVersionOut",
    "DocumentVersionUploadResponse",
    "DocumentVisibilityRequest",
    "PartnerRefOut",
    "PersonRef",
    "PublicDocumentOut",
    "PublicDocumentVersionOut",
    "WorkpackageRef",
]
