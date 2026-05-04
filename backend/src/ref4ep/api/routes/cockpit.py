"""Projekt-Cockpit (Block 0010).

Liefert ein Aggregat aus den nächsten / überfälligen Meilensteinen,
den offenen Punkten der Arbeitspakete und einer kompakten
Statusübersicht. Reines Lesen, nur für eingeloggte Personen.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ref4ep.api.deps import get_current_person, get_session
from ref4ep.api.schemas import (
    CockpitMilestoneOut,
    CockpitOpenIssueOut,
    CockpitWorkpackageStatusOut,
    ProjectCockpitOut,
)
from ref4ep.domain.models import Person
from ref4ep.services.project_dashboard_service import (
    DEFAULT_UPCOMING_LIMIT,
    MilestoneSummary,
    ProjectDashboardService,
    WorkpackageOpenIssue,
    WorkpackageStatusEntry,
)

router = APIRouter(prefix="/api")

SessionDep = Annotated[Session, Depends(get_session)]
PersonDep = Annotated[Person, Depends(get_current_person)]


def _ms_out(ms: MilestoneSummary) -> CockpitMilestoneOut:
    return CockpitMilestoneOut(
        id=ms.id,
        code=ms.code,
        title=ms.title,
        workpackage_code=ms.workpackage_code,
        workpackage_title=ms.workpackage_title,
        planned_date=ms.planned_date,
        actual_date=ms.actual_date,
        status=ms.status,
        days_to_planned=ms.days_to_planned,
        note=ms.note,
    )


def _issue_out(issue: WorkpackageOpenIssue) -> CockpitOpenIssueOut:
    return CockpitOpenIssueOut(
        code=issue.code,
        title=issue.title,
        status=issue.status,
        open_issues=issue.open_issues,
        next_steps=issue.next_steps,
    )


def _status_entry_out(entry: WorkpackageStatusEntry) -> CockpitWorkpackageStatusOut:
    return CockpitWorkpackageStatusOut(
        code=entry.code,
        title=entry.title,
        status=entry.status,
    )


@router.get("/cockpit/project", response_model=ProjectCockpitOut)
def get_project_cockpit(
    _: PersonDep,
    session: SessionDep,
    upcoming_limit: int = Query(default=DEFAULT_UPCOMING_LIMIT, ge=1, le=20),
) -> ProjectCockpitOut:
    dashboard = ProjectDashboardService(session).build(upcoming_limit=upcoming_limit)
    return ProjectCockpitOut(
        today=dashboard.today,
        upcoming_milestones=[_ms_out(ms) for ms in dashboard.upcoming_milestones],
        overdue_milestones=[_ms_out(ms) for ms in dashboard.overdue_milestones],
        workpackages_with_open_issues=[
            _issue_out(i) for i in dashboard.workpackages_with_open_issues
        ],
        status_counts=dashboard.status_counts,
        workpackage_status_overview=[
            _status_entry_out(e) for e in dashboard.workpackage_status_overview
        ],
    )
