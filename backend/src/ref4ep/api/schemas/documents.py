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
    # Block 0035: Bibliotheks-Dokumente haben keinen WP-Bezug.
    workpackage: WorkpackageRef | None = None
    library_section: str | None = None
    created_by: PersonRef
    latest_version: DocumentVersionOut | None
    released_version_id: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentCampaignLinkOut(BaseModel):
    """Kompakte Sicht einer Testkampagne, die einem Dokument zugeordnet ist."""

    id: str
    code: str
    title: str
    status: str
    label: str


class DocumentDetailOut(DocumentOut):
    versions: list[DocumentVersionOut]
    released_version: DocumentVersionOut | None = None
    test_campaigns: list[DocumentCampaignLinkOut] = Field(default_factory=list)


class DocumentTestCampaignLinkRequest(BaseModel):
    campaign_id: str = Field(min_length=36, max_length=36)
    label: str = Field(default="other", min_length=1)


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
    "DocumentCampaignLinkOut",
    "DocumentCreateRequest",
    "DocumentDetailOut",
    "DocumentOut",
    "DocumentPatchRequest",
    "DocumentReleaseRequest",
    "DocumentStatusRequest",
    "DocumentTestCampaignLinkRequest",
    "DocumentVersionOut",
    "DocumentVersionUploadResponse",
    "DocumentVisibilityRequest",
    "InternalDocumentOut",
    "PartnerRefOut",
    "PersonRef",
    "PublicDocumentOut",
    "PublicDocumentVersionOut",
    "WorkpackageRef",
]


# --------------------------------------------------------------------------- #
# Block 0017 — Interne Dokumentliste                                          #
# --------------------------------------------------------------------------- #


class InternalDocumentOut(BaseModel):
    """Kompaktes Dokument-Item für interne Auswahllisten (z. B. Meeting-
    Doc-Verknüpfung). Bewusst flach — kein Audit, keine Versions-Liste,
    nur die letzte Version als Label.

    Block 0035: ``workpackage_code`` und ``workpackage_title`` sind
    optional, weil Bibliotheks-Dokumente ohne WP-Bezug existieren
    können. ``library_section`` markiert die Bibliotheks-Kachel."""

    id: str
    code: str | None = None  # = deliverable_code
    title: str
    workpackage_code: str | None = None
    workpackage_title: str | None = None
    document_type: str | None = None
    library_section: str | None = None
    status: str
    visibility: str
    is_public: bool = False
    is_archived: bool = False
    latest_version_label: str | None = None
    updated_at: datetime


class LibraryDocumentCreateRequest(BaseModel):
    """Block 0035 — Anlage eines Bibliotheks-Dokuments ohne WP-Bezug."""

    title: str = Field(min_length=1)
    document_type: str = "other"
    description: str | None = None
    library_section: str | None = None
    visibility: Literal["internal", "public"] = "internal"
