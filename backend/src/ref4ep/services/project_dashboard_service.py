"""Aggregate für das Projekt-Cockpit (Block 0010).

Liest die bestehenden ``Workpackage``- und ``Milestone``-Daten und
fasst sie für das interne Dashboard zusammen — keine eigene
Tabelle, keine neue Migration. Vier Aggregate stehen im Mittelpunkt:

1. ``upcoming_milestones``     — die nächsten geplanten / gefährdeten
                                 / verschobenen Meilensteine ab heute,
                                 sortiert nach Plandatum aufsteigend,
                                 mit konfigurierbarem Limit.
2. ``overdue_milestones``      — alle nicht erreichten/entfallenen
                                 Meilensteine mit ``planned_date``
                                 in der Vergangenheit. Vollständig.
3. ``workpackages_with_open_issues``
                                — alle nicht-gelöschten Arbeitspakete
                                 mit nicht-leerem ``open_issues``.
                                 Sortiert: kritisch zuerst, dann nach
                                 ``sort_order``/``code``.
4. ``status_counts``           — Anzahl nicht-gelöschter WPs pro
                                 Statuswert (alle fünf Werte aus
                                 ``WORKPACKAGE_STATUSES``).

Der ``today``-Parameter ist injizierbar, damit Tests deterministisch
arbeiten können; defaultet auf ``date.today()``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ref4ep.domain.models import (
    DOCUMENT_STATUSES,
    TEST_CAMPAIGN_STATUSES,
    WORKPACKAGE_STATUSES,
    Document,
    Meeting,
    MeetingAction,
    Milestone,
    TestCampaign,
    Workpackage,
)
from ref4ep.services.milestone_health import (
    TrafficLight,
    TrafficLightCounts,
    compute_workpackage_health,
)

# Status, in denen ein Meilenstein offen / nicht final ist (also
# überfällig werden kann oder als „nächste" angezeigt wird).
OPEN_MILESTONE_STATUSES: frozenset[str] = frozenset({"planned", "postponed", "at_risk"})

# Standardlimit für ``upcoming_milestones`` — die UI zeigt eine
# kompakte Karte, fünf Einträge passen gut. Über den Aufrufer
# konfigurierbar.
DEFAULT_UPCOMING_LIMIT = 5


@dataclass(frozen=True)
class MilestoneSummary:
    id: str
    code: str
    title: str
    workpackage_code: str | None
    workpackage_title: str | None
    planned_date: date
    actual_date: date | None
    status: str
    days_to_planned: int  # > 0 Zukunft, == 0 heute, < 0 Vergangenheit
    note: str | None


@dataclass(frozen=True)
class WorkpackageOpenIssue:
    code: str
    title: str
    status: str
    open_issues: str
    next_steps: str | None


@dataclass(frozen=True)
class WorkpackageStatusEntry:
    code: str
    title: str
    status: str


@dataclass(frozen=True)
class WorkpackageHealthEntry:
    """Aggregat-Ampelzeile pro Arbeitspaket für das Dashboard."""

    code: str
    title: str
    status: str  # WP-Status (planned/in_progress/…)
    traffic_light: TrafficLight
    milestone_counts: TrafficLightCounts
    document_counts: dict[str, int]  # status → count, alle 3 DOCUMENT_STATUSES
    next_milestone: MilestoneSummary | None


@dataclass(frozen=True)
class MilestoneProgress:
    achieved: int
    total: int


@dataclass(frozen=True)
class TimelineEvent:
    """Eintrag im 60-Tage-Zeitstrahl. ``date`` ist fachliches
    Eintrittsdatum; bei Meetings die Datums-Komponente von
    ``starts_at``."""

    date: date
    kind: str  # "milestone" | "meeting" | "campaign"
    id: str
    title: str
    workpackage_code: str | None
    status: str | None  # je nach Quelle


@dataclass(frozen=True)
class ProjectDashboard:
    today: date
    upcoming_milestones: list[MilestoneSummary]
    overdue_milestones: list[MilestoneSummary]
    workpackages_with_open_issues: list[WorkpackageOpenIssue]
    status_counts: dict[str, int]
    workpackage_status_overview: list[WorkpackageStatusEntry]
    # Block 0025 — Ampel-Dashboard:
    workpackage_health: list[WorkpackageHealthEntry] = field(default_factory=list)
    milestone_progress: MilestoneProgress = field(default_factory=lambda: MilestoneProgress(0, 0))
    open_meeting_actions: int = 0
    campaign_status_counts: dict[str, int] = field(default_factory=dict)
    timeline_next_60_days: list[TimelineEvent] = field(default_factory=list)


def _milestone_summary(ms: Milestone, today: date) -> MilestoneSummary:
    delta = (ms.planned_date - today).days
    return MilestoneSummary(
        id=ms.id,
        code=ms.code,
        title=ms.title,
        workpackage_code=ms.workpackage.code if ms.workpackage else None,
        workpackage_title=ms.workpackage.title if ms.workpackage else None,
        planned_date=ms.planned_date,
        actual_date=ms.actual_date,
        status=ms.status,
        days_to_planned=delta,
        note=ms.note,
    )


class ProjectDashboardService:
    def __init__(self, session: Session, *, today: date | None = None) -> None:
        self.session = session
        self.today = today or date.today()

    # ---- Bausteine ------------------------------------------------------

    def upcoming_milestones(self, *, limit: int = DEFAULT_UPCOMING_LIMIT) -> list[MilestoneSummary]:
        stmt = (
            select(Milestone)
            .where(
                Milestone.planned_date >= self.today,
                Milestone.status.in_(OPEN_MILESTONE_STATUSES),
            )
            .order_by(Milestone.planned_date.asc(), Milestone.code.asc())
            .limit(limit)
        )
        return [_milestone_summary(ms, self.today) for ms in self.session.scalars(stmt)]

    def overdue_milestones(self) -> list[MilestoneSummary]:
        stmt = (
            select(Milestone)
            .where(
                Milestone.planned_date < self.today,
                Milestone.status.in_(OPEN_MILESTONE_STATUSES),
            )
            .order_by(Milestone.planned_date.asc(), Milestone.code.asc())
        )
        return [_milestone_summary(ms, self.today) for ms in self.session.scalars(stmt)]

    def workpackages_with_open_issues(self) -> list[WorkpackageOpenIssue]:
        stmt = (
            select(Workpackage)
            .where(
                Workpackage.is_deleted.is_(False),
                Workpackage.open_issues.isnot(None),
                Workpackage.open_issues != "",
            )
            .order_by(Workpackage.sort_order.asc(), Workpackage.code.asc())
        )
        wps = list(self.session.scalars(stmt))
        # „kritisch" zuerst, dann nach sort_order. Die DB-Order erledigt
        # bereits sort_order; wir sortieren in-memory zusätzlich nach
        # Status-Priorität.
        priority = {"critical": 0, "waiting_for_input": 1}
        wps.sort(key=lambda wp: (priority.get(wp.status, 9), wp.sort_order, wp.code))
        return [
            WorkpackageOpenIssue(
                code=wp.code,
                title=wp.title,
                status=wp.status,
                open_issues=wp.open_issues or "",
                next_steps=wp.next_steps,
            )
            for wp in wps
        ]

    def status_counts(self) -> dict[str, int]:
        """Anzahl pro Status — alle Statuswerte sind im Ergebnis enthalten."""
        wps = self._all_active_workpackages()
        counts: dict[str, int] = {status: 0 for status in WORKPACKAGE_STATUSES}
        for wp in wps:
            counts[wp.status] = counts.get(wp.status, 0) + 1
        return counts

    def workpackage_status_overview(self) -> list[WorkpackageStatusEntry]:
        """Kompakte Statusliste aller WPs — UI rendert das als Tabelle."""
        return [
            WorkpackageStatusEntry(code=wp.code, title=wp.title, status=wp.status)
            for wp in self._all_active_workpackages()
        ]

    # ---- Block 0025 — Ampel-Dashboard ----------------------------------

    def workpackage_health(self) -> list[WorkpackageHealthEntry]:
        """Pro Arbeitspaket: Ampel (aus Meilensteinen), Deliverable-
        Counts pro Status, nächster offener Meilenstein.
        """
        wps = list(self._all_active_workpackages())
        if not wps:
            return []
        wp_ids = [wp.id for wp in wps]

        # Meilensteine pro WP einmal sammeln (ein Query).
        ms_stmt = select(Milestone).where(Milestone.workpackage_id.in_(wp_ids))
        milestones_by_wp: dict[str, list[Milestone]] = {wp.id: [] for wp in wps}
        for ms in self.session.scalars(ms_stmt):
            milestones_by_wp.setdefault(ms.workpackage_id, []).append(ms)

        # Deliverable-Counts pro WP × status (ein groupby-Query).
        doc_counts_stmt = (
            select(
                Document.workpackage_id,
                Document.status,
                func.count(Document.id),
            )
            .where(Document.is_deleted.is_(False))
            .where(Document.workpackage_id.in_(wp_ids))
            .group_by(Document.workpackage_id, Document.status)
        )
        doc_counts: dict[str, dict[str, int]] = {
            wp.id: {s: 0 for s in DOCUMENT_STATUSES} for wp in wps
        }
        for wp_id, status_value, count in self.session.execute(doc_counts_stmt):
            doc_counts.setdefault(wp_id, {s: 0 for s in DOCUMENT_STATUSES})[status_value] = count

        result: list[WorkpackageHealthEntry] = []
        for wp in wps:
            wp_milestones = milestones_by_wp.get(wp.id, [])
            light, counts = compute_workpackage_health(wp_milestones, today=self.today)
            # nächster offener Meilenstein (planned/postponed/at_risk,
            # planned_date >= heute), sortiert.
            upcoming = sorted(
                [
                    ms
                    for ms in wp_milestones
                    if ms.status in OPEN_MILESTONE_STATUSES and ms.planned_date >= self.today
                ],
                key=lambda ms: (ms.planned_date, ms.code),
            )
            next_ms = _milestone_summary(upcoming[0], self.today) if upcoming else None
            result.append(
                WorkpackageHealthEntry(
                    code=wp.code,
                    title=wp.title,
                    status=wp.status,
                    traffic_light=light,
                    milestone_counts=counts,
                    document_counts=doc_counts.get(wp.id, {s: 0 for s in DOCUMENT_STATUSES}),
                    next_milestone=next_ms,
                )
            )
        return result

    def milestone_progress(self) -> MilestoneProgress:
        """Fortschrittsbalken: Anzahl ``achieved`` vs. Gesamt
        (ohne ``cancelled``)."""
        total_stmt = select(func.count(Milestone.id)).where(Milestone.status != "cancelled")
        achieved_stmt = select(func.count(Milestone.id)).where(Milestone.status == "achieved")
        total = int(self.session.scalar(total_stmt) or 0)
        achieved = int(self.session.scalar(achieved_stmt) or 0)
        return MilestoneProgress(achieved=achieved, total=total)

    def open_meeting_actions(self) -> int:
        """Zähler offener Aufgaben (Status open / in_progress) projektweit."""
        stmt = select(func.count(MeetingAction.id)).where(
            MeetingAction.status.in_(("open", "in_progress"))
        )
        return int(self.session.scalar(stmt) or 0)

    def campaign_status_counts(self) -> dict[str, int]:
        """Anzahl Kampagnen pro Statuswert — alle Statuswerte enthalten."""
        counts = {s: 0 for s in TEST_CAMPAIGN_STATUSES}
        stmt = select(TestCampaign.status, func.count(TestCampaign.id)).group_by(
            TestCampaign.status
        )
        for status_value, count in self.session.execute(stmt):
            counts[status_value] = count
        return counts

    def timeline_next_60_days(self) -> list[TimelineEvent]:
        """Kommende 60 Tage: offene Meilensteine, Meetings, Kampagnen-
        Starts. Sortiert nach Datum aufsteigend.
        """
        until = self.today + timedelta(days=60)
        events: list[TimelineEvent] = []

        ms_stmt = (
            select(Milestone)
            .where(Milestone.status.in_(OPEN_MILESTONE_STATUSES))
            .where(Milestone.planned_date >= self.today)
            .where(Milestone.planned_date <= until)
        )
        for ms in self.session.scalars(ms_stmt):
            events.append(
                TimelineEvent(
                    date=ms.planned_date,
                    kind="milestone",
                    id=ms.id,
                    title=f"{ms.code} — {ms.title}",
                    workpackage_code=ms.workpackage.code if ms.workpackage else None,
                    status=ms.status,
                )
            )

        # Meetings: starts_at ist Datetime mit TZ; Vergleich gegen
        # 00:00 today (UTC) und 23:59:59 until (UTC), grobe Bandbreite.
        start_dt = datetime.combine(self.today, time.min, tzinfo=UTC)
        end_dt = datetime.combine(until, time.max, tzinfo=UTC)
        mtg_stmt = (
            select(Meeting)
            .where(Meeting.starts_at >= start_dt)
            .where(Meeting.starts_at <= end_dt)
            .where(Meeting.status != "cancelled")
        )
        for mtg in self.session.scalars(mtg_stmt):
            wp_codes = [link.workpackage.code for link in mtg.workpackage_links]
            events.append(
                TimelineEvent(
                    date=mtg.starts_at.date(),
                    kind="meeting",
                    id=mtg.id,
                    title=mtg.title,
                    workpackage_code=wp_codes[0] if wp_codes else None,
                    status=mtg.status,
                )
            )

        camp_stmt = (
            select(TestCampaign)
            .where(TestCampaign.starts_on >= self.today)
            .where(TestCampaign.starts_on <= until)
        )
        for camp in self.session.scalars(camp_stmt):
            wp_codes = [link.workpackage.code for link in camp.workpackage_links]
            events.append(
                TimelineEvent(
                    date=camp.starts_on,
                    kind="campaign",
                    id=camp.id,
                    title=f"{camp.code} — {camp.title}",
                    workpackage_code=wp_codes[0] if wp_codes else None,
                    status=camp.status,
                )
            )

        events.sort(key=lambda e: (e.date, e.kind, e.title))
        return events

    # ---- Komposition ----------------------------------------------------

    def build(self, *, upcoming_limit: int = DEFAULT_UPCOMING_LIMIT) -> ProjectDashboard:
        return ProjectDashboard(
            today=self.today,
            upcoming_milestones=self.upcoming_milestones(limit=upcoming_limit),
            overdue_milestones=self.overdue_milestones(),
            workpackages_with_open_issues=self.workpackages_with_open_issues(),
            status_counts=self.status_counts(),
            workpackage_status_overview=self.workpackage_status_overview(),
            workpackage_health=self.workpackage_health(),
            milestone_progress=self.milestone_progress(),
            open_meeting_actions=self.open_meeting_actions(),
            campaign_status_counts=self.campaign_status_counts(),
            timeline_next_60_days=self.timeline_next_60_days(),
        )

    # ---- internal -------------------------------------------------------

    def _all_active_workpackages(self) -> Iterable[Workpackage]:
        stmt = (
            select(Workpackage)
            .where(Workpackage.is_deleted.is_(False))
            .order_by(Workpackage.sort_order.asc(), Workpackage.code.asc())
        )
        return list(self.session.scalars(stmt))
