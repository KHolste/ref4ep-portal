"""Gantt-Timeline-Aggregat (Block 0026).

Liefert die Daten für eine reine Lese-Visualisierung der Projekt-
Timeline: Meilensteine, Testkampagnen und Meetings auf einer
Zeitachse, gegliedert nach Arbeitspaket.

Architekturanker:
- Pure Aggregator, keine eigene Tabelle, keine Migration.
- Nutzt ``compute_milestone_traffic_light`` aus ``milestone_health``,
  damit die Ampel-Logik mit dem Projekt-Cockpit (Block 0025)
  identisch bleibt.
- Der Calendar-Service ist als Datenquellen-Mehrtypen-Vorbild
  bekannt; Gantt braucht aber Vollständigkeit (auch ohne
  Datumsfenster) und WP-Gruppierung als Spuren — daher eigener
  Service.

Projektzeitraum:
- ``project_start`` ist das früheste fachliche Datum
  (Meilenstein-Plandatum, Kampagnen-Start, Meeting-Start),
  gerundet auf den Monatsanfang. Fallback: heute, falls die DB
  leer ist.
- ``project_end`` = ``project_start`` + 36 Monate, oder das
  späteste vorhandene Datum (falls jemand das Projekt verlängert
  hat) — der größere der beiden Werte.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ref4ep.domain.models import (
    Meeting,
    Milestone,
    TestCampaign,
    Workpackage,
)
from ref4ep.services.milestone_health import (
    TrafficLight,
    compute_milestone_traffic_light,
)

# Standard-Projektdauer in Monaten ab dem ersten Datum.
PROJECT_DURATION_MONTHS = 36

# Sammelzeile für Meilensteine ohne WP-Bezug (z. B. Konsortial-MS).
CONSORTIUM_TRACK_CODE = "KONSORTIUM"
CONSORTIUM_TRACK_TITLE = "Konsortium (übergreifend)"


@dataclass(frozen=True)
class GanttMilestone:
    id: str
    code: str
    title: str
    planned_date: date
    actual_date: date | None
    status: str
    traffic_light: TrafficLight
    note: str | None


@dataclass(frozen=True)
class GanttCampaign:
    id: str
    code: str
    title: str
    starts_on: date
    ends_on: date | None  # None = offen, gestrichelt darstellen
    status: str


@dataclass(frozen=True)
class GanttMeeting:
    id: str
    title: str
    on_date: date
    status: str


@dataclass(frozen=True)
class GanttTrack:
    """Eine Zeile in der Gantt-Visualisierung."""

    code: str  # WP-Code oder ``CONSORTIUM_TRACK_CODE``
    title: str
    sort_order: int
    milestones: list[GanttMilestone]
    campaigns: list[GanttCampaign]
    meetings: list[GanttMeeting]


@dataclass(frozen=True)
class GanttBoard:
    today: date
    project_start: date
    project_end: date
    tracks: list[GanttTrack]


def _first_of_month(d: date) -> date:
    return date(d.year, d.month, 1)


def _add_months(d: date, months: int) -> date:
    """Datums-Addition in Monaten ohne externe Bibliothek."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    # Bei Monatsende-Adjustment kein Feinschliff nötig — wir werden
    # den Wert immer weiter zum Monatsanfang oder -ende runden.
    day = min(d.day, 28)  # robust gegen Februar-Sondefall
    return date(year, month, day)


class GanttService:
    """Aggregiert Gantt-Daten. Liefert ein flaches ``GanttBoard``-DTO."""

    def __init__(self, session: Session, *, today: date | None = None) -> None:
        self.session = session
        self.today = today or date.today()

    # ---- Lese-Bausteine ------------------------------------------------

    def _load_workpackages(self) -> list[Workpackage]:
        stmt = (
            select(Workpackage)
            .where(Workpackage.is_deleted.is_(False))
            .order_by(Workpackage.sort_order.asc(), Workpackage.code.asc())
        )
        return list(self.session.scalars(stmt))

    def _load_milestones(self) -> list[Milestone]:
        return list(self.session.scalars(select(Milestone)))

    def _load_campaigns(self) -> list[TestCampaign]:
        return list(self.session.scalars(select(TestCampaign)))

    def _load_meetings(self) -> list[Meeting]:
        stmt = select(Meeting).where(Meeting.status != "cancelled")
        return list(self.session.scalars(stmt))

    # ---- Projektzeitraum -----------------------------------------------

    def _determine_project_window(
        self,
        milestones: list[Milestone],
        campaigns: list[TestCampaign],
        meetings: list[Meeting],
    ) -> tuple[date, date]:
        """Frühestes Datum (Monatsanfang) bis ``+ 36 Monate``, mind.
        bis zum spätesten existenten Datum."""
        candidates_low: list[date] = []
        candidates_high: list[date] = []
        for ms in milestones:
            candidates_low.append(ms.planned_date)
            candidates_high.append(ms.actual_date or ms.planned_date)
        for c in campaigns:
            candidates_low.append(c.starts_on)
            candidates_high.append(c.ends_on or c.starts_on)
        for m in meetings:
            d = m.starts_at.date()
            candidates_low.append(d)
            candidates_high.append(m.ends_at.date() if m.ends_at else d)
        if not candidates_low:
            # Leere DB: wir setzen Projektfenster um heute.
            start = _first_of_month(self.today)
            end = _add_months(start, PROJECT_DURATION_MONTHS)
            return start, end
        start = _first_of_month(min(candidates_low))
        end_candidate = _add_months(start, PROJECT_DURATION_MONTHS)
        latest = max(candidates_high)
        return start, max(end_candidate, latest)

    # ---- Aggregat ------------------------------------------------------

    def build(self) -> GanttBoard:
        wps = self._load_workpackages()
        milestones = self._load_milestones()
        campaigns = self._load_campaigns()
        meetings = self._load_meetings()

        project_start, project_end = self._determine_project_window(milestones, campaigns, meetings)

        # Spur pro WP (sort_order, code) plus eine Konsortial-Sammelspur.
        track_buckets: dict[str | None, dict] = {}
        for wp in wps:
            track_buckets[wp.id] = {
                "code": wp.code,
                "title": wp.title,
                "sort_order": wp.sort_order,
                "milestones": [],
                "campaigns": [],
                "meetings": [],
            }
        # Konsortial-Bucket (key=None) bekommt ein hohes sort_order, damit
        # er ans Ende rutscht.
        track_buckets[None] = {
            "code": CONSORTIUM_TRACK_CODE,
            "title": CONSORTIUM_TRACK_TITLE,
            "sort_order": 10_000,
            "milestones": [],
            "campaigns": [],
            "meetings": [],
        }

        for ms in milestones:
            light = compute_milestone_traffic_light(ms, today=self.today)
            entry = GanttMilestone(
                id=ms.id,
                code=ms.code,
                title=ms.title,
                planned_date=ms.planned_date,
                actual_date=ms.actual_date,
                status=ms.status,
                traffic_light=light,
                note=ms.note,
            )
            track_key = ms.workpackage_id if ms.workpackage_id is not None else None
            bucket = track_buckets.get(track_key)
            if bucket is None:
                # Falls ein MS auf ein gelöschtes/entferntes WP zeigt:
                # in Konsortial-Spur einsortieren.
                bucket = track_buckets[None]
            bucket["milestones"].append(entry)

        for c in campaigns:
            entry_c = GanttCampaign(
                id=c.id,
                code=c.code,
                title=c.title,
                starts_on=c.starts_on,
                ends_on=c.ends_on,
                status=c.status,
            )
            wp_links = list(c.workpackage_links)
            if not wp_links:
                track_buckets[None]["campaigns"].append(entry_c)
            else:
                # Eine Kampagne kann mehrere WPs haben: wir zeigen sie in
                # jeder zugehörigen Spur (visuelle Klarheit, kein
                # zusätzlicher Datenverbrauch).
                for link in wp_links:
                    bucket = track_buckets.get(link.workpackage_id)
                    if bucket is not None:
                        bucket["campaigns"].append(entry_c)

        for m in meetings:
            entry_m = GanttMeeting(
                id=m.id,
                title=m.title,
                on_date=m.starts_at.date(),
                status=m.status,
            )
            wp_links = list(m.workpackage_links)
            if not wp_links:
                track_buckets[None]["meetings"].append(entry_m)
            else:
                for link in wp_links:
                    bucket = track_buckets.get(link.workpackage_id)
                    if bucket is not None:
                        bucket["meetings"].append(entry_m)

        # In sortierte Track-Liste umwandeln. Spur ohne Inhalt drinlassen
        # — auch leere WP-Spuren sind in einem Gantt-Plan informativ.
        # Konsortial-Spur nur, wenn sie Inhalt hat.
        tracks: list[GanttTrack] = []
        for key, b in track_buckets.items():
            if key is None and not (b["milestones"] or b["campaigns"] or b["meetings"]):
                continue
            tracks.append(
                GanttTrack(
                    code=b["code"],
                    title=b["title"],
                    sort_order=b["sort_order"],
                    milestones=sorted(b["milestones"], key=lambda x: x.planned_date),
                    campaigns=sorted(b["campaigns"], key=lambda x: x.starts_on),
                    meetings=sorted(b["meetings"], key=lambda x: x.on_date),
                )
            )
        tracks.sort(key=lambda t: (t.sort_order, t.code))

        return GanttBoard(
            today=self.today,
            project_start=project_start,
            project_end=project_end,
            tracks=tracks,
        )


# Hilfs-Konstanten zur Vermeidung „magische Importe in Tests":
__all__ = [
    "CONSORTIUM_TRACK_CODE",
    "CONSORTIUM_TRACK_TITLE",
    "GanttBoard",
    "GanttCampaign",
    "GanttMeeting",
    "GanttMilestone",
    "GanttService",
    "GanttTrack",
    "PROJECT_DURATION_MONTHS",
]
