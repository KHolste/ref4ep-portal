"""Alembic-Migrationen — Sprint 1."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from alembic import command
from tests.conftest import ALEMBIC_DIR, ALEMBIC_INI

CURRENT_HEAD = "0003_documents"
IDENTITY_TABLES = {"partner", "person", "workpackage", "membership"}
DOCUMENT_TABLES = {"document", "document_version"}


def _make_config(db_url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_upgrade_head_writes_current_revision(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    engine = create_engine(db_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert version == CURRENT_HEAD


def test_head_revision_matches(tmp_db_path: Path) -> None:
    cfg = _make_config(f"sqlite:///{tmp_db_path}")
    heads = list(ScriptDirectory.from_config(cfg).get_heads())
    assert heads == [CURRENT_HEAD]


def test_upgrade_head_creates_identity_tables(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    engine = create_engine(db_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert IDENTITY_TABLES.issubset(tables)


def test_downgrade_to_baseline_drops_identity_tables(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0001_baseline")
    engine = create_engine(db_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert IDENTITY_TABLES.isdisjoint(tables)


def test_full_downgrade_to_base(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    engine = create_engine(db_url)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        assert result is None


def test_base_metadata_has_identity_tables() -> None:
    """Sprint 1: Identity-Modelle sind in Base.metadata registriert."""
    from ref4ep.domain import models  # noqa: F401 — Trigger der Registrierung
    from ref4ep.domain.base import Base

    assert IDENTITY_TABLES.issubset(set(Base.metadata.tables.keys()))


def test_upgrade_head_creates_document_tables(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    engine = create_engine(db_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert DOCUMENT_TABLES.issubset(tables)


def test_document_table_has_no_released_version_id(tmp_db_path: Path) -> None:
    """Sprint 2 enthält bewusst kein released_version_id-Feld."""
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    engine = create_engine(db_url)
    inspector = inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("document")}
    assert "released_version_id" not in columns


def test_downgrade_to_0002_drops_document_tables(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0002_identity_and_project")
    engine = create_engine(db_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert DOCUMENT_TABLES.isdisjoint(tables)
    assert IDENTITY_TABLES.issubset(tables)


def test_base_metadata_has_document_tables() -> None:
    from ref4ep.domain import models  # noqa: F401
    from ref4ep.domain.base import Base

    assert DOCUMENT_TABLES.issubset(set(Base.metadata.tables.keys()))
