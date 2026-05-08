"""Pure-Function-Tests für die Ampel-Logik (Block 0025).

Keine DB-Anbindung: wir konstruieren minimale Milestone-Stand-ins
über ``SimpleNamespace``. Damit deterministisch und ms-schnell.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from ref4ep.services.milestone_health import (
    NEAR_DEADLINE_DAYS,
    compute_milestone_traffic_light,
    compute_workpackage_health,
)


def _ms(status: str, planned_date: date) -> SimpleNamespace:
    return SimpleNamespace(status=status, planned_date=planned_date)


# ---- compute_milestone_traffic_light -----------------------------------


def test_achieved_is_green_regardless_of_date() -> None:
    today = date(2026, 5, 8)
    past = _ms("achieved", today - timedelta(days=120))
    future = _ms("achieved", today + timedelta(days=400))
    assert compute_milestone_traffic_light(past, today=today) == "green"
    assert compute_milestone_traffic_light(future, today=today) == "green"


def test_cancelled_is_gray() -> None:
    today = date(2026, 5, 8)
    ms = _ms("cancelled", today - timedelta(days=10))
    assert compute_milestone_traffic_light(ms, today=today) == "gray"


def test_at_risk_is_red() -> None:
    today = date(2026, 5, 8)
    # auch wenn das Plandatum noch weit weg ist
    ms = _ms("at_risk", today + timedelta(days=200))
    assert compute_milestone_traffic_light(ms, today=today) == "red"


def test_planned_overdue_is_red() -> None:
    today = date(2026, 5, 8)
    ms = _ms("planned", today - timedelta(days=1))
    assert compute_milestone_traffic_light(ms, today=today) == "red"


def test_postponed_overdue_is_red() -> None:
    today = date(2026, 5, 8)
    ms = _ms("postponed", today - timedelta(days=10))
    assert compute_milestone_traffic_light(ms, today=today) == "red"


def test_planned_near_deadline_is_yellow() -> None:
    today = date(2026, 5, 8)
    ms = _ms("planned", today + timedelta(days=NEAR_DEADLINE_DAYS - 1))
    assert compute_milestone_traffic_light(ms, today=today) == "yellow"
    # Heute selbst → gelb (delta 0, < 30)
    today_ms = _ms("planned", today)
    assert compute_milestone_traffic_light(today_ms, today=today) == "yellow"


def test_planned_far_future_is_green() -> None:
    today = date(2026, 5, 8)
    ms = _ms("planned", today + timedelta(days=NEAR_DEADLINE_DAYS))
    assert compute_milestone_traffic_light(ms, today=today) == "green"
    # Auslegung: weit weg = nichts zu tun = grün.
    far = _ms("postponed", today + timedelta(days=180))
    assert compute_milestone_traffic_light(far, today=today) == "green"


# ---- compute_workpackage_health (Aggregation) -------------------------


def test_empty_workpackage_is_gray() -> None:
    today = date(2026, 5, 8)
    light, counts = compute_workpackage_health([], today=today)
    assert light == "gray"
    assert counts.total == 0


def test_aggregation_takes_worst() -> None:
    today = date(2026, 5, 8)
    mixed = [
        _ms("achieved", today - timedelta(days=10)),  # green
        _ms("planned", today + timedelta(days=200)),  # green
        _ms("planned", today + timedelta(days=10)),  # yellow
        _ms("at_risk", today + timedelta(days=100)),  # red — bestimmt das Aggregat
    ]
    light, counts = compute_workpackage_health(mixed, today=today)
    assert light == "red"
    assert counts.green == 2
    assert counts.yellow == 1
    assert counts.red == 1
    assert counts.gray == 0


def test_aggregation_yellow_dominates_over_green() -> None:
    today = date(2026, 5, 8)
    items = [
        _ms("achieved", today - timedelta(days=30)),
        _ms("planned", today + timedelta(days=10)),
    ]
    light, _ = compute_workpackage_health(items, today=today)
    assert light == "yellow"


def test_aggregation_all_cancelled_is_gray() -> None:
    today = date(2026, 5, 8)
    items = [
        _ms("cancelled", today - timedelta(days=5)),
        _ms("cancelled", today + timedelta(days=20)),
    ]
    light, counts = compute_workpackage_health(items, today=today)
    assert light == "gray"
    assert counts.gray == 2


def test_aggregation_green_when_all_green() -> None:
    today = date(2026, 5, 8)
    items = [
        _ms("achieved", today - timedelta(days=200)),
        _ms("planned", today + timedelta(days=180)),
    ]
    light, counts = compute_workpackage_health(items, today=today)
    assert light == "green"
    assert counts.green == 2
