"""Workpackage-Zeitplandaten für Bestandsdatenbanken (Block 0027).

Block 0027 hat die Spalten ``start_date``/``end_date`` an
``workpackage`` ergänzt. Der ``SeedService`` schreibt nur in *neue*
WPs, nicht in bereits bestehende — auf einer Bestands-DB (Production
seit dem ersten Seed) bleiben deshalb die Datumsfelder leer.

Diese Migration trägt die Antrags-Zeitplanwerte für die bekannten
Sub-WP-Codes nach. Sie ist defensiv:

- **Up**: setzt ``start_date``/``end_date`` nur, wenn **beide** Felder
  ``NULL`` sind. Sobald ein Admin/WP-Lead manuell etwas eingetragen
  hat (auch nur Start oder nur Ende), wird der Datensatz übersprungen.
- **Down**: löscht die hier gesetzten Werte nur, wenn beide Werte
  **exakt** den Seed-Werten entsprechen. Manuell geänderte Termine
  bleiben unangetastet.

Werte sind eingefroren (Stand: ``antrag_initial.yaml`` zur
Migrationszeit). Wenn der Antrag künftig revidiert wird, gehört das
in einen neuen Block — diese Migration bleibt fix. Synchronität zur
YAML wird per Asset-Test in ``tests/test_seed_yaml_sync.py``
verifiziert.

Anker: ``project_start_date = 2026-03-01`` — konsistent zur YAML und
zu den Meilenstein-Daten (MS1 Kick-off, MS3 Referenz-HT, MS4 Projekt-
abschluss).

Revision ID: 0014_seed_workpackage_schedule
Revises: 0013_workpackage_schedule
Create Date: 2026-05-08
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0014_seed_workpackage_schedule"
down_revision: Union[str, None] = "0013_workpackage_schedule"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Anker und Konvertierungs-Konvention identisch zum SeedService:
# start_month → erster Tag des Monats, end_month → letzter Tag.
PROJECT_START = date(2026, 3, 1)

# (code, start_month, end_month) — synchron zu antrag_initial.yaml.
WP_SCHEDULE: tuple[tuple[str, int, int], ...] = (
    ("WP1.1", 1, 36),
    ("WP1.2", 1, 36),
    ("WP2.1", 1, 24),
    ("WP2.2", 6, 13),
    ("WP3.1", 1, 24),
    ("WP3.2", 24, 34),
    ("WP3.3", 24, 36),
    ("WP4.1", 1, 13),
    ("WP4.2", 7, 18),
    ("WP4.3", 1, 24),
    ("WP4.4", 1, 24),
    ("WP4.5", 1, 24),
    ("WP4.6", 1, 24),
    ("WP5.1", 21, 24),
    ("WP5.2", 21, 24),
    ("WP5.3", 13, 24),
    ("WP5.4", 22, 36),
    ("WP6.1", 1, 24),
    ("WP6.2", 24, 36),
    ("WP6.3", 13, 36),
    ("WP6.4", 22, 36),
    ("WP7.1", 1, 24),
    ("WP7.2", 1, 24),
    ("WP7.3", 24, 36),
    ("WP8.1", 1, 18),
    ("WP8.2", 17, 36),
    ("WP8.3", 1, 36),
)


def _add_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    return date(year, month, 1)


def _last_day_of_month(d: date) -> date:
    next_month = _add_months(date(d.year, d.month, 1), 1)
    return next_month - timedelta(days=1)


def _resolve(month_pair: tuple[int, int]) -> tuple[date, date]:
    start_month, end_month = month_pair
    start = _add_months(PROJECT_START, start_month - 1)
    end = _last_day_of_month(_add_months(PROJECT_START, end_month - 1))
    return start, end


def upgrade() -> None:
    bind = op.get_bind()
    workpackage = sa.table(
        "workpackage",
        sa.column("code", sa.String),
        sa.column("start_date", sa.Date),
        sa.column("end_date", sa.Date),
    )
    for code, start_month, end_month in WP_SCHEDULE:
        start, end = _resolve((start_month, end_month))
        # Defensiv: nur Datensätze mit beiden Feldern NULL; manuelle
        # Werte (auch teilweise) bleiben unverändert.
        bind.execute(
            sa.update(workpackage)
            .where(workpackage.c.code == code)
            .where(workpackage.c.start_date.is_(None))
            .where(workpackage.c.end_date.is_(None))
            .values(start_date=start, end_date=end)
        )


def downgrade() -> None:
    bind = op.get_bind()
    workpackage = sa.table(
        "workpackage",
        sa.column("code", sa.String),
        sa.column("start_date", sa.Date),
        sa.column("end_date", sa.Date),
    )
    for code, start_month, end_month in WP_SCHEDULE:
        start, end = _resolve((start_month, end_month))
        # Defensiv: nur löschen, wenn beide Werte EXAKT den Seed-Werten
        # entsprechen. Manuell geänderte Termine bleiben.
        bind.execute(
            sa.update(workpackage)
            .where(workpackage.c.code == code)
            .where(workpackage.c.start_date == start)
            .where(workpackage.c.end_date == end)
            .values(start_date=None, end_date=None)
        )
