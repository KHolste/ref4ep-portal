"""Initial-Seed aus YAML-Quelldateien (siehe MVP-Spec §13).

Idempotent: bereits vorhandene Datensätze (Partner per ``short_name``,
Workpackage per ``code``) werden nicht überschrieben. Sub-WPs erben
den Lead-Partner ihres Parents, sofern keine eigene Angabe vorliegt.
"""

from __future__ import annotations

from importlib import resources
from typing import Any

import yaml
from sqlalchemy.orm import Session

from ref4ep.domain.models import Partner, Workpackage
from ref4ep.services.workpackage_service import _sort_key_from_code

KNOWN_SOURCES = ("antrag",)


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

        partners_added, partners_skipped = self._seed_partners(data.get("partners", []))
        wps_added, wps_skipped = self._seed_workpackages(data.get("workpackages", []))

        self.session.flush()

        return {
            "source": source,  # type: ignore[dict-item]
            "partners_added": partners_added,
            "partners_skipped": partners_skipped,
            "workpackages_added": wps_added,
            "workpackages_skipped": wps_skipped,
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

    def _seed_workpackages(self, items: list[dict[str, Any]]) -> tuple[int, int]:
        # Partner-Lookup einmal aufbauen.
        partners_by_short = {p.short_name: p for p in self.session.query(Partner).all()}

        # Wir machen zwei Durchgänge: erst Parents (kein "parent"-Feld),
        # dann Children. So existieren Parents bevor Children sie referenzieren.
        parents = [it for it in items if not it.get("parent")]
        children = [it for it in items if it.get("parent")]

        added = 0
        skipped = 0

        added_p, skipped_p = self._seed_wp_batch(parents, partners_by_short, parent_lookup={})
        added += added_p
        skipped += skipped_p
        self.session.flush()

        # Parent-Lookup nach erstem Durchgang aufbauen (inkl. bereits vorhandener)
        parent_lookup = {wp.code: wp for wp in self.session.query(Workpackage).all()}
        added_c, skipped_c = self._seed_wp_batch(children, partners_by_short, parent_lookup)
        added += added_c
        skipped += skipped_c
        self.session.flush()

        return added, skipped

    def _seed_wp_batch(
        self,
        items: list[dict[str, Any]],
        partners_by_short: dict[str, Partner],
        parent_lookup: dict[str, Workpackage],
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

            wp = Workpackage(
                code=code,
                title=item["title"],
                description=item.get("description"),
                parent_workpackage_id=parent_wp.id if parent_wp else None,
                lead_partner_id=lead_partner.id,
                sort_order=_sort_key_from_code(code),
            )
            self.session.add(wp)
            # In-Memory-Lookup aktualisieren, falls Geschwister auf diesen
            # WP verweisen sollten (Sprint-1-Daten machen das nicht, aber
            # der Code bleibt robust).
            parent_lookup[code] = wp
            added += 1
        return added, skipped
