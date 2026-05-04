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
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ref4ep.domain.models import (
    WORKPACKAGE_STATUSES,
    Milestone,
    Workpackage,
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
class ProjectDashboard:
    today: date
    upcoming_milestones: list[MilestoneSummary]
    overdue_milestones: list[MilestoneSummary]
    workpackages_with_open_issues: list[WorkpackageOpenIssue]
    status_counts: dict[str, int]
    workpackage_status_overview: list[WorkpackageStatusEntry]


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

    # ---- Komposition ----------------------------------------------------

    def build(self, *, upcoming_limit: int = DEFAULT_UPCOMING_LIMIT) -> ProjectDashboard:
        return ProjectDashboard(
            today=self.today,
            upcoming_milestones=self.upcoming_milestones(limit=upcoming_limit),
            overdue_milestones=self.overdue_milestones(),
            workpackages_with_open_issues=self.workpackages_with_open_issues(),
            status_counts=self.status_counts(),
            workpackage_status_overview=self.workpackage_status_overview(),
        )

    # ---- internal -------------------------------------------------------

    def _all_active_workpackages(self) -> Iterable[Workpackage]:
        stmt = (
            select(Workpackage)
            .where(Workpackage.is_deleted.is_(False))
            .order_by(Workpackage.sort_order.asc(), Workpackage.code.asc())
        )
        return list(self.session.scalars(stmt))
