"""Schemas für die Gantt-Timeline (Block 0026)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class GanttMilestoneOut(BaseModel):
    id: str
    code: str
    title: str
    planned_date: date
    actual_date: date | None = None
    status: str
    traffic_light: str  # green | yellow | red | gray
    note: str | None = None


class GanttCampaignOut(BaseModel):
    id: str
    code: str
    title: str
    starts_on: date
    ends_on: date | None = None  # None = offen, Frontend rendert gestrichelt
    status: str


class GanttMeetingOut(BaseModel):
    id: str
    title: str
    on_date: date
    status: str


class GanttTrackOut(BaseModel):
    code: str
    title: str
    sort_order: int
    parent_code: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    milestones: list[GanttMilestoneOut] = Field(default_factory=list)
    campaigns: list[GanttCampaignOut] = Field(default_factory=list)
    meetings: list[GanttMeetingOut] = Field(default_factory=list)


class GanttBoardOut(BaseModel):
    today: date
    project_start: date
    project_end: date
    tracks: list[GanttTrackOut] = Field(default_factory=list)


__all__ = [
    "GanttBoardOut",
    "GanttCampaignOut",
    "GanttMeetingOut",
    "GanttMilestoneOut",
    "GanttTrackOut",
]
