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
    MyActionOut,
    MyCockpitOut,
    MyMeetingOut,
    MyWorkpackageOut,
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


# --------------------------------------------------------------------------- #
# Block 0018 — personalisierte Cockpit-Sicht                                  #
# --------------------------------------------------------------------------- #


@router.get("/cockpit/me", response_model=MyCockpitOut)
def get_my_cockpit(actor: PersonDep, session: SessionDep) -> MyCockpitOut:
    """Persönlicher Bereich: eigene WPs, Aufgaben, nächste Meetings."""
    from datetime import UTC, date, datetime

    from sqlalchemy import select

    from ref4ep.domain.models import (
        Meeting,
        MeetingAction,
        MeetingParticipant,
        MeetingWorkpackage,
        Membership,
    )

    today = date.today()
    now = datetime.now(tz=UTC)

    # Eigene Memberships → Lead-WPs + alle WPs.
    memberships = list(
        session.scalars(
            select(Membership)
            .where(Membership.person_id == actor.id)
            .order_by(Membership.created_at)
        )
    )
    wp_ids_member = {m.workpackage_id for m in memberships}

    def _wp_out(m: Membership) -> MyWorkpackageOut:
        return MyWorkpackageOut(
            code=m.workpackage.code,
            title=m.workpackage.title,
            wp_role=m.wp_role,
            status=m.workpackage.status,
        )

    my_wps = [
        _wp_out(m)
        for m in sorted(memberships, key=lambda m: (m.workpackage.sort_order, m.workpackage.code))
        if not m.workpackage.is_deleted
    ]
    my_lead_wps = [w for w in my_wps if w.wp_role == "wp_lead"]

    # Eigene Aufgaben (responsible == self), offen + überfällig.
    actions = list(
        session.scalars(
            select(MeetingAction)
            .where(MeetingAction.responsible_person_id == actor.id)
            .order_by(MeetingAction.due_date.asc(), MeetingAction.created_at.asc())
        )
    )
    open_actions: list[MyActionOut] = []
    overdue_actions: list[MyActionOut] = []
    for a in actions:
        is_overdue = (
            a.due_date is not None and a.due_date < today and a.status in ("open", "in_progress")
        )
        item = MyActionOut(
            id=a.id,
            text=a.text,
            status=a.status,
            due_date=a.due_date,
            overdue=is_overdue,
            meeting_id=a.meeting_id,
            meeting_title=a.meeting.title,
            workpackage_code=a.workpackage.code if a.workpackage else None,
        )
        if is_overdue:
            overdue_actions.append(item)
        elif a.status in ("open", "in_progress"):
            open_actions.append(item)

    # Nächste Meetings: Teilnehmer ODER WP-Bezug zu eigenen WPs, starts_at >= now,
    # status nicht cancelled.
    participant_meeting_ids = {
        row[0]
        for row in session.execute(
            select(MeetingParticipant.meeting_id).where(MeetingParticipant.person_id == actor.id)
        )
    }
    if wp_ids_member:
        wp_meeting_ids = {
            row[0]
            for row in session.execute(
                select(MeetingWorkpackage.meeting_id).where(
                    MeetingWorkpackage.workpackage_id.in_(wp_ids_member)
                )
            )
        }
    else:
        wp_meeting_ids = set()
    relevant = participant_meeting_ids | wp_meeting_ids
    if relevant:
        meetings = list(
            session.scalars(
                select(Meeting)
                .where(
                    Meeting.id.in_(relevant),
                    Meeting.starts_at >= now,
                    Meeting.status != "cancelled",
                )
                .order_by(Meeting.starts_at.asc())
                .limit(10)
            )
        )
    else:
        meetings = []

    def _meeting_out(meeting: Meeting) -> MyMeetingOut:
        wp_codes = sorted(link.workpackage.code for link in meeting.workpackage_links)
        return MyMeetingOut(
            id=meeting.id,
            title=meeting.title,
            starts_at=meeting.starts_at,
            ends_at=meeting.ends_at,
            status=meeting.status,
            workpackage_codes=wp_codes,
        )

    return MyCockpitOut(
        today=today,
        my_workpackages=my_wps,
        my_lead_workpackages=my_lead_wps,
        my_open_actions=open_actions,
        my_overdue_actions=overdue_actions,
        my_next_meetings=[_meeting_out(m) for m in meetings],
    )
