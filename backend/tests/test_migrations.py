"""Alembic-Migrationen — Sprint 1."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from alembic import command
from tests.conftest import ALEMBIC_DIR, ALEMBIC_INI

CURRENT_HEAD = "0004_audit_and_release"
IDENTITY_TABLES = {"partner", "person", "workpackage", "membership"}
DOCUMENT_TABLES = {"document", "document_version"}
AUDIT_TABLES = {"audit_log"}


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


def test_document_table_has_released_version_id(tmp_db_path: Path) -> None:
    """Sprint 3: released_version_id-Spalte ist vorhanden."""
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    engine = create_engine(db_url)
    inspector = inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("document")}
    assert "released_version_id" in columns


def test_document_released_version_id_has_fk(tmp_db_path: Path) -> None:
    """Sprint 3: released_version_id ist ein echter Foreign Key auf document_version.id."""
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    engine = create_engine(db_url)
    inspector = inspect(engine)
    fks = inspector.get_foreign_keys("document")
    matching = [
        fk
        for fk in fks
        if fk.get("referred_table") == "document_version"
        and fk.get("constrained_columns") == ["released_version_id"]
    ]
    assert matching, f"Erwartet FK auf document_version.id, gefunden: {fks}"


def test_released_version_id_rejects_unknown_uuid(tmp_db_path: Path) -> None:
    """Sprint 3: DB lehnt unbekannte UUID in released_version_id ab."""
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    engine = create_engine(db_url)
    # SQLite muss FKs explizit aktiviert werden.
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys = ON")
        # Vorbedingung: ein gültiges Workpackage und eine Person aus dem Seed —
        # aber wir haben einen frischen tmp DB, also legen wir minimale Daten direkt an.
        conn.exec_driver_sql(
            "INSERT INTO partner (id, name, short_name, country, is_deleted, "
            "created_at, updated_at) VALUES "
            "('11111111-1111-1111-1111-111111111111', 'P', 'P', 'DE', 0, "
            "datetime('now'), datetime('now'))"
        )
        conn.exec_driver_sql(
            "INSERT INTO person (id, email, display_name, partner_id, password_hash, "
            "platform_role, is_active, must_change_password, is_deleted, "
            "created_at, updated_at) VALUES "
            "('22222222-2222-2222-2222-222222222222', 'p@x', 'P', "
            "'11111111-1111-1111-1111-111111111111', 'h', 'admin', 1, 0, 0, "
            "datetime('now'), datetime('now'))"
        )
        conn.exec_driver_sql(
            "INSERT INTO workpackage (id, code, title, lead_partner_id, sort_order, "
            "is_deleted, created_at, updated_at) VALUES "
            "('33333333-3333-3333-3333-333333333333', 'WX', 'WX', "
            "'11111111-1111-1111-1111-111111111111', 0, 0, datetime('now'), datetime('now'))"
        )
        conn.exec_driver_sql(
            "INSERT INTO document (id, workpackage_id, title, slug, document_type, "
            "status, visibility, created_by_person_id, is_deleted, "
            "created_at, updated_at) VALUES "
            "('44444444-4444-4444-4444-444444444444', "
            "'33333333-3333-3333-3333-333333333333', 'D', 'd', 'note', "
            "'draft', 'workpackage', '22222222-2222-2222-2222-222222222222', 0, "
            "datetime('now'), datetime('now'))"
        )

    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys = ON")
        try:
            conn.exec_driver_sql(
                "UPDATE document SET released_version_id = "
                "'99999999-9999-9999-9999-999999999999' "
                "WHERE id = '44444444-4444-4444-4444-444444444444'"
            )
        except Exception as exc:
            assert "FOREIGN KEY" in str(exc).upper() or "constraint" in str(exc).lower()
        else:
            raise AssertionError("FK-Constraint hätte unbekannte UUID ablehnen müssen.")


def test_upgrade_head_creates_audit_table(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    engine = create_engine(db_url)
    tables = set(inspect(engine).get_table_names())
    assert AUDIT_TABLES.issubset(tables)


def test_downgrade_to_0003_drops_audit_and_release(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0003_documents")
    engine = create_engine(db_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert AUDIT_TABLES.isdisjoint(tables)
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
