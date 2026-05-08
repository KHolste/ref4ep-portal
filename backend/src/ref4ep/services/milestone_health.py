"""Ampel-Logik für Meilensteine (Block 0025).

Pure Funktionen, keine DB-Abhängigkeit, keine Service-Initialisierung —
damit auch von der späteren Gantt-Visualisierung (Feature 1) ohne
Umweg importierbar.

Ampel-Werte:
- ``green``  — Meilenstein erreicht oder weit genug in der Zukunft.
- ``yellow`` — Plandatum in unter 30 Tagen, noch nicht erreicht.
- ``red``    — Plandatum überschritten ohne Erreichung, oder
               manuell auf ``at_risk`` gesetzt.
- ``gray``   — Status ``cancelled`` (entfallen), oder bei
               WP-Aggregation: kein einziger Meilenstein vorhanden.

Status-Mapping zu den Code-Werten (siehe ``MILESTONE_STATUSES``):
- ``achieved`` → green
- ``cancelled`` → gray
- ``at_risk`` → red
- ``planned`` / ``postponed`` → datumsabhängig (red/yellow/green)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Literal

from ref4ep.domain.models import Milestone

# Schwelle für „nahe Deadline" (gelbe Phase). Auslegung der User-
# Spezifikation „Plandatum in weniger als 30 Tagen".
NEAR_DEADLINE_DAYS = 30

TrafficLight = Literal["green", "yellow", "red", "gray"]

# Reihenfolge nach Schwere — die WP-Aggregation nimmt das schlechteste
# Element der Menge. Indexgröße = Schwere.
_SEVERITY: dict[TrafficLight, int] = {"gray": 0, "green": 1, "yellow": 2, "red": 3}


@dataclass(frozen=True)
class TrafficLightCounts:
    """Zähler pro Ampelwert für eine WP-Aggregation."""

    green: int = 0
    yellow: int = 0
    red: int = 0
    gray: int = 0

    @property
    def total(self) -> int:
        return self.green + self.yellow + self.red + self.gray


def compute_milestone_traffic_light(
    milestone: Milestone, *, today: date | None = None
) -> TrafficLight:
    """Ampelwert für einen einzelnen Meilenstein.

    Auslegung der User-Spezifikation:
    - ``achieved`` → green (unabhängig vom Datum)
    - ``cancelled`` → gray (entfallen)
    - ``at_risk`` → red (manuell gefährdet)
    - ``planned`` / ``postponed`` mit ``planned_date < today``
      und Status ≠ ``achieved`` → red (überfällig)
    - ``planned`` / ``postponed`` mit ``0 ≤ delta < 30 Tage`` → yellow
    - ``planned`` / ``postponed`` mit ``delta ≥ 30 Tage`` → green
      (noch weit hin, nichts zu tun)

    ``today`` ist injizierbar — Tests bleiben deterministisch.
    """
    if milestone.status == "achieved":
        return "green"
    if milestone.status == "cancelled":
        return "gray"
    if milestone.status == "at_risk":
        return "red"
    # planned / postponed → datumsabhängig
    today = today or date.today()
    delta_days = (milestone.planned_date - today).days
    if delta_days < 0:
        return "red"
    if delta_days < NEAR_DEADLINE_DAYS:
        return "yellow"
    return "green"


def compute_workpackage_health(
    milestones: Iterable[Milestone], *, today: date | None = None
) -> tuple[TrafficLight, TrafficLightCounts]:
    """Aggregat-Ampel für ein Arbeitspaket.

    Nimmt das **schlechteste** Element der Meilenstein-Menge. Bei
    leerer Menge: ``gray`` (nicht bewertbar — semantisch wie „alle
    entfallen"). Im zweiten Rückgabewert sind die Einzelzähler, damit
    die UI sie als Mini-Histogramm darstellen kann.

    Reihenfolge der Schwere: red > yellow > green > gray.
    """
    counts: dict[TrafficLight, int] = {"green": 0, "yellow": 0, "red": 0, "gray": 0}
    has_any = False
    for ms in milestones:
        has_any = True
        light = compute_milestone_traffic_light(ms, today=today)
        counts[light] += 1
    summary = TrafficLightCounts(
        green=counts["green"],
        yellow=counts["yellow"],
        red=counts["red"],
        gray=counts["gray"],
    )
    if not has_any:
        return "gray", summary
    # höchste Schwere bestimmt das Aggregat (gray-only zählt als gray).
    worst: TrafficLight = "gray"
    for light, c in counts.items():
        if c == 0:
            continue
        if _SEVERITY[light] > _SEVERITY[worst]:
            worst = light
    return worst, summary
