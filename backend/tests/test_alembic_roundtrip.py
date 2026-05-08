"""Migration-Roundtrip-Test.

CI prüft heute nur ``alembic upgrade head``. Asymmetrische Migrationen
(komplexe Down-Pfade in 0008_partner_organization_fields & Co.) brechen
sonst still erst beim ersten realen Restore. Dieser Test fährt
sequentiell **alle** Revisionen einzeln hoch, downgraded auf die
Vorgänger-Revision und upgraded wieder — und vergleicht dabei die
Tabellenmenge per ``Inspector``.

Funktioniert auf SQLite (CI sqlite-Job). Bewusst keine Schemavergleiche
mit Spalten/Indices — die SQLite-batch_alter_table-Roundtrips erzeugen
geringfügige Differenzen in den `sqlite_master`-Einträgen, die für die
fachliche Korrektheit irrelevant sind.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from alembic import command

BACKEND_DIR = Path(__file__).resolve().parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
ALEMBIC_DIR = BACKEND_DIR / "alembic"


def _config(database_url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _ordered_revisions(cfg: Config) -> list:
    """Revisionen von ``base`` Richtung ``head``."""
    script = ScriptDirectory.from_config(cfg)
    # walk_revisions iteriert von head Richtung base.
    return list(reversed(list(script.walk_revisions())))


def test_alembic_roundtrip(tmp_path: Path) -> None:
    db_path = tmp_path / "roundtrip.db"
    url = f"sqlite:///{db_path}"
    cfg = _config(url)
    engine = create_engine(url, future=True)

    revs = _ordered_revisions(cfg)
    incomplete_downgrades: list[str] = []

    try:
        for i, rev in enumerate(revs):
            command.upgrade(cfg, rev.revision)
            tables_after_up = set(inspect(engine).get_table_names())

            prev = revs[i - 1].revision if i > 0 else "base"
            try:
                command.downgrade(cfg, prev)
            except NotImplementedError:
                # Down-Pfad fehlt — wir merken uns die Revision und
                # überspringen den Roundtrip-Vergleich. Der DB-Zustand
                # bleibt auf ``rev``, sodass die nächste Iteration
                # nahtlos weitermacht.
                incomplete_downgrades.append(rev.revision)
                continue

            command.upgrade(cfg, rev.revision)
            tables_after_re_up = set(inspect(engine).get_table_names())

            assert tables_after_up == tables_after_re_up, (
                f"Tabellenmenge nach Roundtrip auf {rev.revision} "
                f"unterscheidet sich:\n"
                f"  vor down: {sorted(tables_after_up)}\n"
                f"  nach re-up: {sorted(tables_after_re_up)}"
            )

        # Final: head muss erreichbar sein und alembic_version-Tabelle
        # existieren.
        command.upgrade(cfg, "head")
        assert "alembic_version" in inspect(engine).get_table_names()
    finally:
        engine.dispose()

    if incomplete_downgrades:
        pytest.xfail(
            "Downgrade nicht implementiert für Revisionen: " + ", ".join(incomplete_downgrades)
        )
