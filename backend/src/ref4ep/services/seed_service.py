"""Initial-Seed aus YAML-Quelldateien (siehe MVP-Spec §13).

Idempotent: bereits vorhandene Datensätze (Partner per ``short_name``,
Workpackage per ``code``, Milestone per ``code``) werden nicht
überschrieben. Sub-WPs erben den Lead-Partner ihres Parents, sofern
keine eigene Angabe vorliegt.

Block 0009: zusätzlich werden die vier Projekt-Meilensteine angelegt
(MS1–MS4). MS4 hängt an keinem konkreten WP — Gesamtprojekt-Meilenstein.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from importlib import resources
from typing import Any

import yaml
from sqlalchemy.orm import Session

from ref4ep.domain.models import MILESTONE_STATUSES, Milestone, Partner, Workpackage
from ref4ep.services.workpackage_service import _sort_key_from_code

KNOWN_SOURCES = ("antrag",)


def _coerce_date(value: object) -> date:
    """Akzeptiert ``date`` (PyYAML parsed YYYY-MM-DD automatisch) oder ``str``."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"Erwartetes Datum, bekam {type(value).__name__}: {value!r}")


def _add_months(d: date, months: int) -> date:
    """Datums-Addition in Monaten ohne externe Bibliothek (Tag bleibt 1)."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    return date(year, month, 1)


def _last_day_of_month(d: date) -> date:
    """Letzter Kalendertag im Monat von ``d``."""
    next_month = _add_months(date(d.year, d.month, 1), 1)
    return next_month - timedelta(days=1)


def _month_to_start_date(month: object, project_start: date | None) -> date | None:
    """``Projektmonat → erster Tag des Monats``. ``None`` wenn Monat
    fehlt oder kein Projektstart-Anker vorhanden ist."""
    if month is None or project_start is None:
        return None
    if not isinstance(month, int) or month < 1:
        raise ValueError(f"start_month muss positive Ganzzahl sein, bekam {month!r}")
    return _add_months(project_start, month - 1)


def _month_to_end_date(month: object, project_start: date | None) -> date | None:
    """``Projektmonat → letzter Tag des Monats``."""
    if month is None or project_start is None:
        return None
    if not isinstance(month, int) or month < 1:
        raise ValueError(f"end_month muss positive Ganzzahl sein, bekam {month!r}")
    return _last_day_of_month(_add_months(project_start, month - 1))


def _load_seed_data(source: str) -> dict[str, Any]:
    if source not in KNOWN_SOURCES:
        raise ValueError(f"Unbekannte Seed-Quelle: {source}")
    seed_dir = resources.files("ref4ep.cli") / "seed_data"
    seed_file = seed_dir / f"{source}_initial.yaml"
    raw = seed_file.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Seed-Datei {source}_initial.yaml hat falsches Wurzelformat.")
    return data


class SeedService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def apply_initial_seed(self, *, source: str = "antrag") -> dict[str, int]:
        data = _load_seed_data(source)

        # Block 0027: Anker für Monat→Datum-Konvertierung der WP-Zeiten.
        project_start_raw = data.get("project_start_date")
        project_start = _coerce_date(project_start_raw) if project_start_raw is not None else None

        partners_added, partners_skipped = self._seed_partners(data.get("partners", []))
        wps_added, wps_skipped = self._seed_workpackages(
            data.get("workpackages", []), project_start=project_start
        )
        ms_added, ms_skipped = self._seed_milestones(data.get("milestones", []))

        self.session.flush()

        return {
            "source": source,  # type: ignore[dict-item]
            "partners_added": partners_added,
            "partners_skipped": partners_skipped,
            "workpackages_added": wps_added,
            "workpackages_skipped": wps_skipped,
            "milestones_added": ms_added,
            "milestones_skipped": ms_skipped,
        }

    # ---- internals ------------------------------------------------------

    def _seed_partners(self, items: list[dict[str, Any]]) -> tuple[int, int]:
        added = 0
        skipped = 0
        for item in items:
            short_name = item["short_name"]
            existing = self.session.query(Partner).filter_by(short_name=short_name).first()
            if existing is not None:
                skipped += 1
                continue
            partner = Partner(
                short_name=short_name,
                name=item["name"],
                country=item["country"],
                website=item.get("website"),
            )
            self.session.add(partner)
            added += 1
        self.session.flush()
        return added, skipped

    def _seed_workpackages(
        self,
        items: list[dict[str, Any]],
        *,
        project_start: date | None = None,
    ) -> tuple[int, int]:
        # Partner-Lookup einmal aufbauen.
        partners_by_short = {p.short_name: p for p in self.session.query(Partner).all()}

        # Wir machen zwei Durchgänge: erst Parents (kein "parent"-Feld),
        # dann Children. So existieren Parents bevor Children sie referenzieren.
        parents = [it for it in items if not it.get("parent")]
        children = [it for it in items if it.get("parent")]

        added = 0
        skipped = 0

        added_p, skipped_p = self._seed_wp_batch(
            parents, partners_by_short, parent_lookup={}, project_start=project_start
        )
        added += added_p
        skipped += skipped_p
        self.session.flush()

        # Parent-Lookup nach erstem Durchgang aufbauen (inkl. bereits vorhandener)
        parent_lookup = {wp.code: wp for wp in self.session.query(Workpackage).all()}
        added_c, skipped_c = self._seed_wp_batch(
            children, partners_by_short, parent_lookup, project_start=project_start
        )
        added += added_c
        skipped += skipped_c
        self.session.flush()

        return added, skipped

    def _seed_wp_batch(
        self,
        items: list[dict[str, Any]],
        partners_by_short: dict[str, Partner],
        parent_lookup: dict[str, Workpackage],
        *,
        project_start: date | None = None,
    ) -> tuple[int, int]:
        added = 0
        skipped = 0
        for item in items:
            code = item["code"]
            existing = self.session.query(Workpackage).filter_by(code=code).first()
            if existing is not None:
                skipped += 1
                continue

            parent_code = item.get("parent")
            parent_wp: Workpackage | None = None
            if parent_code:
                parent_wp = parent_lookup.get(parent_code)
                if parent_wp is None:
                    raise LookupError(
                        f"Seed: Parent-WP {parent_code!r} für {code!r} nicht gefunden."
                    )

            # Lead-Partner: explizit oder vom Parent geerbt.
            lead_short = item.get("lead")
            if not lead_short and parent_wp is not None:
                lead_partner = partners_by_short.get(parent_wp.lead_partner.short_name)
            else:
                lead_partner = partners_by_short.get(lead_short) if lead_short else None
            if lead_partner is None:
                raise LookupError(
                    f"Seed: Lead-Partner für WP {code!r} nicht ermittelbar "
                    f"(weder eigenes 'lead' noch Parent-Vererbung)."
                )

            # Block 0027 — Zeitplan-Felder aus monatsbasierten Antragsdaten.
            start_date = _month_to_start_date(item.get("start_month"), project_start)
            end_date = _month_to_end_date(item.get("end_month"), project_start)

            wp = Workpackage(
                code=code,
                title=item["title"],
                description=item.get("description"),
                parent_workpackage_id=parent_wp.id if parent_wp else None,
                lead_partner_id=lead_partner.id,
                sort_order=_sort_key_from_code(code),
                start_date=start_date,
                end_date=end_date,
            )
            self.session.add(wp)
            # In-Memory-Lookup aktualisieren, falls Geschwister auf diesen
            # WP verweisen sollten (Sprint-1-Daten machen das nicht, aber
            # der Code bleibt robust).
            parent_lookup[code] = wp
            added += 1
        return added, skipped

    def _seed_milestones(self, items: list[dict[str, Any]]) -> tuple[int, int]:
        if not items:
            return 0, 0
        wps_by_code = {wp.code: wp for wp in self.session.query(Workpackage).all()}
        added = 0
        skipped = 0
        for item in items:
            code = item["code"]
            existing = self.session.query(Milestone).filter_by(code=code).first()
            if existing is not None:
                skipped += 1
                continue
            wp_code = item.get("workpackage")
            wp_id: str | None = None
            if wp_code:
                wp = wps_by_code.get(wp_code)
                if wp is None:
                    raise LookupError(
                        f"Seed: Meilenstein {code!r} verweist auf unbekanntes WP {wp_code!r}."
                    )
                wp_id = wp.id
            status_value = item.get("status", "planned")
            if status_value not in MILESTONE_STATUSES:
                raise ValueError(
                    f"Seed: Meilenstein {code!r} hat ungültigen status {status_value!r}."
                )
            planned_date = _coerce_date(item["planned_date"])
            actual_raw = item.get("actual_date")
            actual_date = _coerce_date(actual_raw) if actual_raw is not None else None
            milestone = Milestone(
                code=code,
                title=item["title"],
                workpackage_id=wp_id,
                planned_date=planned_date,
                actual_date=actual_date,
                status=status_value,
                note=item.get("note"),
            )
            self.session.add(milestone)
            added += 1
        self.session.flush()
        return added, skipped
