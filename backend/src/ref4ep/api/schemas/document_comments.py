"""Schemas für Dokumentkommentare auf Versionsebene (Block 0024)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from ref4ep.api.schemas.documents import PersonRef


class DocumentCommentVersionRef(BaseModel):
    """Kompakte Version-Referenz für Comment-Listen.

    Reicht aus, damit das Frontend zur Versionsdetailseite springen
    kann (Versionsnummer + Dokument-id) ohne ein zweites Round-Trip.
    """

    id: str
    version_number: int
    document_id: str


class DocumentCommentOut(BaseModel):
    id: str
    document_version: DocumentCommentVersionRef
    author: PersonRef
    text: str
    status: Literal["open", "submitted"]
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None = None


class DocumentCommentCreateRequest(BaseModel):
    text: str = Field(min_length=1)


class DocumentCommentUpdateRequest(BaseModel):
    text: str = Field(min_length=1)


__all__ = [
    "DocumentCommentCreateRequest",
    "DocumentCommentOut",
    "DocumentCommentUpdateRequest",
    "DocumentCommentVersionRef",
]
