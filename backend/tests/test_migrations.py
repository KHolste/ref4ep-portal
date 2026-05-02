"""Alembic-Baseline gegen leere SQLite-DB."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from alembic import command
from tests.conftest import ALEMBIC_DIR, ALEMBIC_INI


def _make_config(db_url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_upgrade_head_creates_alembic_version_table(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)

    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        assert result is not None
        assert result[0] == "0001_baseline"


def test_head_revision_is_baseline(tmp_db_path: Path) -> None:
    cfg = _make_config(f"sqlite:///{tmp_db_path}")
    script = ScriptDirectory.from_config(cfg)
    heads = list(script.get_heads())
    assert heads == ["0001_baseline"]


def test_downgrade_base_is_reversible(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    engine = create_engine(db_url)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        assert result is None


def test_base_metadata_has_no_app_tables() -> None:
    """Sprint 0: Base.metadata darf noch keine Domain-Tabellen tragen."""
    from ref4ep.domain.base import Base

    assert Base.metadata.tables == {}
