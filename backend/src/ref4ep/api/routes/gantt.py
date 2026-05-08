"""Gantt-Timeline (Block 0026).

Reines Lesen für eingeloggte Nutzer. Liefert in einem Aufruf:
Workpackage-Spuren mit Meilensteinen (Ampel-eingefärbt),
Testkampagnen (Zeitraum), Meetings (Punkte) sowie das
Projekt-Zeitfenster.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ref4ep.api.deps import get_current_person, get_session
from ref4ep.api.schemas.gantt import (
    GanttBoardOut,
    GanttCampaignOut,
    GanttMeetingOut,
    GanttMilestoneOut,
    GanttTrackOut,
)
from ref4ep.domain.models import Person
from ref4ep.services.gantt_service import (
    GanttCampaign,
    GanttMeeting,
    GanttMilestone,
    GanttService,
    GanttTrack,
)

router = APIRouter(prefix="/api")

SessionDep = Annotated[Session, Depends(get_session)]
PersonDep = Annotated[Person, Depends(get_current_person)]


def _milestone_out(ms: GanttMilestone) -> GanttMilestoneOut:
    return GanttMilestoneOut(
        id=ms.id,
        code=ms.code,
        title=ms.title,
        planned_date=ms.planned_date,
        actual_date=ms.actual_date,
        status=ms.status,
        traffic_light=ms.traffic_light,
        note=ms.note,
    )


def _campaign_out(c: GanttCampaign) -> GanttCampaignOut:
    return GanttCampaignOut(
        id=c.id,
        code=c.code,
        title=c.title,
        starts_on=c.starts_on,
        ends_on=c.ends_on,
        status=c.status,
    )


def _meeting_out(m: GanttMeeting) -> GanttMeetingOut:
    return GanttMeetingOut(id=m.id, title=m.title, on_date=m.on_date, status=m.status)


def _track_out(t: GanttTrack) -> GanttTrackOut:
    return GanttTrackOut(
        code=t.code,
        title=t.title,
        sort_order=t.sort_order,
        parent_code=t.parent_code,
        start_date=t.start_date,
        end_date=t.end_date,
        milestones=[_milestone_out(ms) for ms in t.milestones],
        campaigns=[_campaign_out(c) for c in t.campaigns],
        meetings=[_meeting_out(m) for m in t.meetings],
    )


@router.get("/gantt", response_model=GanttBoardOut)
def get_gantt(_: PersonDep, session: SessionDep) -> GanttBoardOut:
    board = GanttService(session).build()
    return GanttBoardOut(
        today=board.today,
        project_start=board.project_start,
        project_end=board.project_end,
        tracks=[_track_out(t) for t in board.tracks],
    )
