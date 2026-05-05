"""Schemas für den aggregierten Projektkalender (Block 0023)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CalendarEventOut(BaseModel):
    id: str
    source_id: str
    type: str  # meeting | campaign | milestone | action
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    all_day: bool
    status: str | None = None
    workpackage_codes: list[str] = Field(default_factory=list)
    link: str
    description: str | None = None
    is_overdue: bool = False
