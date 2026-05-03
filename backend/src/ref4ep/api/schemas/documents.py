"""Schemas für das Dokumentenregister (Sprint 2)."""

from __future__ import annotations

from datetime import datetime

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
    status: str
    visibility: str
    workpackage: WorkpackageRef
    created_by: PersonRef
    latest_version: DocumentVersionOut | None
    created_at: datetime
    updated_at: datetime


class DocumentDetailOut(DocumentOut):
    versions: list[DocumentVersionOut]


class DocumentCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    document_type: str
    deliverable_code: str | None = None


class DocumentPatchRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    document_type: str | None = None
    deliverable_code: str | None = None


class DocumentVersionUploadResponse(BaseModel):
    version: DocumentVersionOut
    warnings: list[str] = Field(default_factory=list)


__all__ = [
    "DocumentCreateRequest",
    "DocumentDetailOut",
    "DocumentOut",
    "DocumentPatchRequest",
    "DocumentVersionOut",
    "DocumentVersionUploadResponse",
    "PartnerRefOut",
    "PersonRef",
    "WorkpackageRef",
]
