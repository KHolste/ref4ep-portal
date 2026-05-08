"""Pydantic-Schemas für das Testkampagnenregister (Block 0022)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

# ---- gemeinsame Refs --------------------------------------------------


class CampaignWorkpackageOut(BaseModel):
    code: str
    title: str


class CampaignPersonOut(BaseModel):
    id: str
    display_name: str
    email: str


class CampaignParticipantOut(BaseModel):
    id: str
    person: CampaignPersonOut
    role: str
    note: str | None = None


class CampaignDocumentOut(BaseModel):
    document_id: str
    title: str
    deliverable_code: str | None = None
    workpackage_code: str | None = None
    label: str


# ---- Listen / Detail --------------------------------------------------


class CampaignListItemOut(BaseModel):
    id: str
    code: str
    title: str
    category: str
    status: str
    starts_on: date
    ends_on: date | None = None
    facility: str | None = None
    workpackages: list[CampaignWorkpackageOut] = Field(default_factory=list)
    participants_count: int = 0
    documents_count: int = 0
    can_edit: bool = False


class CampaignDetailOut(BaseModel):
    id: str
    code: str
    title: str
    category: str
    status: str
    starts_on: date
    ends_on: date | None = None
    facility: str | None = None
    location: str | None = None
    short_description: str | None = None
    objective: str | None = None
    test_matrix: str | None = None
    expected_measurements: str | None = None
    boundary_conditions: str | None = None
    success_criteria: str | None = None
    risks_or_open_points: str | None = None
    created_by: CampaignPersonOut
    workpackages: list[CampaignWorkpackageOut] = Field(default_factory=list)
    participants: list[CampaignParticipantOut] = Field(default_factory=list)
    documents: list[CampaignDocumentOut] = Field(default_factory=list)
    can_edit: bool = False
    can_upload_photo: bool = False
    can_create_note: bool = False


# ---- Requests ---------------------------------------------------------


class CampaignCreateRequest(BaseModel):
    code: str = Field(min_length=1)
    title: str = Field(min_length=1)
    category: str = "other"
    status: str = "planned"
    starts_on: date
    ends_on: date | None = None
    facility: str | None = None
    location: str | None = None
    short_description: str | None = None
    objective: str | None = None
    test_matrix: str | None = None
    expected_measurements: str | None = None
    boundary_conditions: str | None = None
    success_criteria: str | None = None
    risks_or_open_points: str | None = None
    workpackage_ids: list[str] = Field(default_factory=list)


class CampaignPatchRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1)
    title: str | None = Field(default=None, min_length=1)
    category: str | None = None
    status: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    facility: str | None = None
    location: str | None = None
    short_description: str | None = None
    objective: str | None = None
    test_matrix: str | None = None
    expected_measurements: str | None = None
    boundary_conditions: str | None = None
    success_criteria: str | None = None
    risks_or_open_points: str | None = None
    workpackage_ids: list[str] | None = None


class CampaignParticipantAddRequest(BaseModel):
    person_id: str = Field(min_length=36, max_length=36)
    role: str = "other"
    note: str | None = None


class CampaignParticipantPatchRequest(BaseModel):
    role: str | None = None
    note: str | None = None


class CampaignDocumentLinkAddRequest(BaseModel):
    document_id: str = Field(min_length=36, max_length=36)
    label: str = "other"


# ---- Block 0028 — Foto-Upload für Testkampagnen -----------------------


class CampaignPhotoOut(BaseModel):
    id: str
    original_filename: str
    mime_type: str
    file_size_bytes: int
    sha256: str
    caption: str | None = None
    taken_at: datetime | None = None
    uploaded_by: CampaignPersonOut
    created_at: datetime
    updated_at: datetime
    can_edit: bool = False


class CampaignPhotoCaptionRequest(BaseModel):
    caption: str | None = None


# ---- Block 0029 — Kampagnennotizen ------------------------------------


class CampaignNoteOut(BaseModel):
    id: str
    campaign_id: str
    body_md: str
    author: CampaignPersonOut
    created_at: datetime
    updated_at: datetime
    can_edit: bool = False


class CampaignNoteCreateRequest(BaseModel):
    body_md: str = Field(min_length=1)


class CampaignNoteUpdateRequest(BaseModel):
    body_md: str = Field(min_length=1)


__all__ = [
    "CampaignCreateRequest",
    "CampaignDetailOut",
    "CampaignDocumentLinkAddRequest",
    "CampaignDocumentOut",
    "CampaignListItemOut",
    "CampaignNoteCreateRequest",
    "CampaignNoteOut",
    "CampaignNoteUpdateRequest",
    "CampaignParticipantAddRequest",
    "CampaignParticipantOut",
    "CampaignParticipantPatchRequest",
    "CampaignPatchRequest",
    "CampaignPersonOut",
    "CampaignPhotoCaptionRequest",
    "CampaignPhotoOut",
    "CampaignWorkpackageOut",
]
