"""Alembic-Migrationen — Sprint 1."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from alembic import command
from tests.conftest import ALEMBIC_DIR, ALEMBIC_INI

CURRENT_HEAD = "0018_project_library"
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


def test_document_description_column_exists(tmp_db_path: Path) -> None:
    """Praxistest-Korrekturrunde: optionale Beschreibungsspalte."""
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    engine = create_engine(db_url)
    columns = {c["name"]: c for c in inspect(engine).get_columns("document")}
    assert "description" in columns
    assert columns["description"]["nullable"] is True


def test_downgrade_drops_description(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0004_audit_and_release")
    engine = create_engine(db_url)
    columns = {c["name"] for c in inspect(engine).get_columns("document")}
    assert "description" not in columns


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


# Block 0008-State: Partner-Stammdaten beschreiben Organisation und
# bearbeitende Einheit. Die personenbezogenen Spalten aus 0006 sind weg
# (siehe ``PARTNER_REMOVED_PERSON_COLUMNS``).
PARTNER_ORGANIZATION_COLUMNS = {
    "unit_name",
    "organization_address_line",
    "organization_postal_code",
    "organization_city",
    "organization_country",
    "unit_address_same_as_organization",
    "unit_address_line",
    "unit_postal_code",
    "unit_city",
    "unit_country",
    "is_active",
    "internal_note",
}

PARTNER_REMOVED_PERSON_COLUMNS = {
    "primary_contact_name",
    "contact_email",
    "contact_phone",
    "project_role_note",
}


def test_partner_extended_columns_exist(tmp_db_path: Path) -> None:
    """Block 0008: Organisations-/Einheits-Felder da, Personenfelder weg."""
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    engine = create_engine(db_url)
    columns = {c["name"]: c for c in inspect(engine).get_columns("partner")}
    missing = PARTNER_ORGANIZATION_COLUMNS - set(columns)
    assert not missing, f"Fehlende Spalten: {missing}"
    # 0008: personenbezogene Spalten müssen alle weg sein.
    assert PARTNER_REMOVED_PERSON_COLUMNS.isdisjoint(set(columns))
    # 0007: general_email bleibt entfernt.
    assert "general_email" not in columns
    # Alte Adress-Spaltennamen sind durch organization_*-Renames weg.
    for old_name in ("address_line", "postal_code", "city", "address_country"):
        assert old_name not in columns
    # NOT-NULL-Pflichten:
    for col in ("is_active", "unit_address_same_as_organization"):
        assert columns[col]["nullable"] is False


def test_partner_downgrade_removes_organization_columns(tmp_db_path: Path) -> None:
    """Downgrade auf 0005 entfernt alle 0006/0007/0008-Erweiterungen."""
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0005_document_description")
    engine = create_engine(db_url)
    columns = {c["name"] for c in inspect(engine).get_columns("partner")}
    assert columns.isdisjoint(PARTNER_ORGANIZATION_COLUMNS)


def test_downgrade_to_0007_restores_person_columns_and_old_address_names(
    tmp_db_path: Path,
) -> None:
    """Downgrade 0008 → 0007: alte Adressnamen + Personenfelder kommen zurück."""
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0007_partner_contacts")
    engine = create_engine(db_url)
    columns = {c["name"] for c in inspect(engine).get_columns("partner")}
    # Personenbezogene Felder wieder vorhanden (für Bestandsdaten).
    assert PARTNER_REMOVED_PERSON_COLUMNS.issubset(columns)
    # Adressspalten haben wieder die alten Namen.
    for old_name in ("address_line", "postal_code", "city", "address_country"):
        assert old_name in columns
    # Neue Einheits-Spalten weg.
    for new_name in (
        "unit_name",
        "unit_address_same_as_organization",
        "unit_address_line",
        "unit_postal_code",
        "unit_city",
        "unit_country",
        "organization_address_line",
        "organization_postal_code",
        "organization_city",
        "organization_country",
    ):
        assert new_name not in columns


def test_partner_address_data_survives_rename_round_trip(tmp_db_path: Path) -> None:
    """Bestehender Datensatz mit Adresswerten bleibt nach 0007→0008 lesbar.

    Wir starten in 0007 (alte Spaltennamen), legen einen Partner mit
    Adresse an, fahren auf head (0008) hoch und prüfen, dass die
    Werte unter den neuen Namen ``organization_*`` ankommen.
    """
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "0007_partner_contacts")
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO partner (id, name, short_name, country, "
            "address_line, postal_code, city, address_country, "
            "is_active, is_deleted, created_at, updated_at) VALUES "
            "('p1', 'P1', 'P1', 'DE', 'Hauptstr. 1', '12345', 'Stadt', 'DE', "
            "1, 0, datetime('now'), datetime('now'))"
        )
    command.upgrade(cfg, "head")
    with engine.begin() as conn:
        row = conn.exec_driver_sql(
            "SELECT organization_address_line, organization_postal_code, "
            "organization_city, organization_country, "
            "unit_address_same_as_organization "
            "FROM partner WHERE id = 'p1'"
        ).fetchone()
    assert row == ("Hauptstr. 1", "12345", "Stadt", "DE", 1)


# ---- Block 0007 — Partnerkontakte --------------------------------------


PARTNER_CONTACT_COLUMNS = {
    "id",
    "partner_id",
    "name",
    "title_or_degree",
    "email",
    "phone",
    "function",
    "organization_unit",
    "workpackage_notes",
    "is_primary_contact",
    "is_project_lead",
    "visibility",
    "is_active",
    "internal_note",
    "created_at",
    "updated_at",
}


def test_partner_contact_table_exists_with_expected_columns(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    assert "partner_contact" in set(inspector.get_table_names())
    cols = {c["name"] for c in inspector.get_columns("partner_contact")}
    assert PARTNER_CONTACT_COLUMNS == cols


def test_partner_contact_has_partner_fk(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    fks = inspector.get_foreign_keys("partner_contact")
    matching = [
        fk
        for fk in fks
        if fk.get("referred_table") == "partner" and fk.get("constrained_columns") == ["partner_id"]
    ]
    assert matching, f"FK partner_id → partner.id fehlt: {fks}"


def test_general_email_is_dropped_at_head(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    cols = {c["name"] for c in inspector.get_columns("partner")}
    assert "general_email" not in cols


def test_downgrade_to_0006_restores_general_email_and_drops_contacts(
    tmp_db_path: Path,
) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0006_partner_extended_fields")
    inspector = inspect(create_engine(db_url))
    assert "partner_contact" not in set(inspector.get_table_names())
    cols = {c["name"] for c in inspector.get_columns("partner")}
    assert "general_email" in cols


# ---- Block 0009 — WP-Cockpit-Felder + Milestone-Tabelle ----------------


WORKPACKAGE_COCKPIT_COLUMNS = {"status", "summary", "next_steps", "open_issues"}
MILESTONE_COLUMNS = {
    "id",
    "code",
    "title",
    "workpackage_id",
    "planned_date",
    "actual_date",
    "status",
    "note",
    "created_at",
    "updated_at",
}


def test_workpackage_has_cockpit_fields(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    cols = {c["name"]: c for c in inspector.get_columns("workpackage")}
    assert WORKPACKAGE_COCKPIT_COLUMNS.issubset(set(cols))
    # status ist NOT NULL mit Default 'planned'.
    assert cols["status"]["nullable"] is False
    for soft in ("summary", "next_steps", "open_issues"):
        assert cols[soft]["nullable"] is True


def test_milestone_table_exists_with_expected_columns(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    assert "milestone" in set(inspector.get_table_names())
    cols = {c["name"] for c in inspector.get_columns("milestone")}
    assert MILESTONE_COLUMNS == cols
    # workpackage_id darf NULL sein (Gesamtprojekt-MS).
    nullable = {c["name"]: c["nullable"] for c in inspector.get_columns("milestone")}
    assert nullable["workpackage_id"] is True
    assert nullable["actual_date"] is True
    assert nullable["planned_date"] is False


def test_milestone_has_workpackage_fk(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    fks = inspector.get_foreign_keys("milestone")
    matching = [
        fk
        for fk in fks
        if fk.get("referred_table") == "workpackage"
        and fk.get("constrained_columns") == ["workpackage_id"]
    ]
    assert matching, f"FK milestone.workpackage_id → workpackage.id fehlt: {fks}"


def test_no_deliverable_table_exists(tmp_db_path: Path) -> None:
    """Ref4EP hat keine formalen Deliverables — kein Modell, keine Tabelle."""
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    assert "deliverable" not in set(inspector.get_table_names())


def test_downgrade_to_0008_drops_milestones_and_cockpit_fields(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0008_partner_organization_fields")
    inspector = inspect(create_engine(db_url))
    assert "milestone" not in set(inspector.get_table_names())
    cols = {c["name"] for c in inspector.get_columns("workpackage")}
    assert cols.isdisjoint(WORKPACKAGE_COCKPIT_COLUMNS)


# ---- Block 0015 — Meeting-/Protokollregister --------------------------


MEETING_TABLES = {
    "meeting",
    "meeting_workpackage",
    "meeting_participant",
    "meeting_decision",
    "meeting_action",
    "meeting_document_link",
}

MEETING_COLUMNS = {
    "id",
    "title",
    "starts_at",
    "ends_at",
    "format",
    "location",
    "category",
    "status",
    "summary",
    "extra_participants",
    "created_by_id",
    "created_at",
    "updated_at",
}


def test_meeting_tables_exist(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    tables = set(inspector.get_table_names())
    assert MEETING_TABLES.issubset(tables)


def test_meeting_table_has_expected_columns(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    cols = {c["name"] for c in inspector.get_columns("meeting")}
    assert MEETING_COLUMNS == cols


def test_meeting_workpackage_is_link_table(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    cols = {c["name"] for c in inspector.get_columns("meeting_workpackage")}
    assert cols == {"meeting_id", "workpackage_id"}
    fks = inspector.get_foreign_keys("meeting_workpackage")
    referred = {fk.get("referred_table") for fk in fks}
    assert {"meeting", "workpackage"}.issubset(referred)


def test_meeting_document_link_columns(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    cols = {c["name"] for c in inspector.get_columns("meeting_document_link")}
    assert cols == {"meeting_id", "document_id", "label"}
    fks = inspector.get_foreign_keys("meeting_document_link")
    referred = {fk.get("referred_table") for fk in fks}
    assert {"meeting", "document"}.issubset(referred)


def test_no_meeting_attachment_or_upload_table(tmp_db_path: Path) -> None:
    """Block 0015 baut bewusst keinen eigenen Datei-/Upload-Pfad."""
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    tables = set(inspector.get_table_names())
    for forbidden in ("meeting_file", "meeting_upload", "meeting_attachment"):
        assert forbidden not in tables


def test_downgrade_to_0009_drops_meeting_tables(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    # Erst die Test-Kampagnen-Tabellen wegräumen, sonst hängen sie an meeting/workpackage.
    command.downgrade(cfg, "0010_meetings")
    command.downgrade(cfg, "0009_wp_ms")
    inspector = inspect(create_engine(db_url))
    tables = set(inspector.get_table_names())
    assert tables.isdisjoint(MEETING_TABLES)


# ---- Block 0022 — Testkampagnenregister -------------------------------


TEST_CAMPAIGN_TABLES = {
    "test_campaign",
    "test_campaign_workpackage",
    "test_campaign_participant",
    "test_campaign_document_link",
}

TEST_CAMPAIGN_COLUMNS = {
    "id",
    "code",
    "title",
    "category",
    "status",
    "starts_on",
    "ends_on",
    "facility",
    "location",
    "short_description",
    "objective",
    "test_matrix",
    "expected_measurements",
    "boundary_conditions",
    "success_criteria",
    "risks_or_open_points",
    "created_by_id",
    "created_at",
    "updated_at",
}


def test_test_campaign_tables_exist(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    tables = set(inspector.get_table_names())
    assert TEST_CAMPAIGN_TABLES.issubset(tables)


def test_test_campaign_table_has_expected_columns(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    cols = {c["name"] for c in inspector.get_columns("test_campaign")}
    assert TEST_CAMPAIGN_COLUMNS == cols


def test_test_campaign_code_is_unique(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    uqs = inspector.get_unique_constraints("test_campaign")
    cols = [tuple(uq["column_names"]) for uq in uqs]
    assert ("code",) in cols


def test_test_campaign_workpackage_is_link_table(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    cols = {c["name"] for c in inspector.get_columns("test_campaign_workpackage")}
    assert cols == {"campaign_id", "workpackage_id"}
    fks = inspector.get_foreign_keys("test_campaign_workpackage")
    referred = {fk.get("referred_table") for fk in fks}
    assert {"test_campaign", "workpackage"}.issubset(referred)


def test_test_campaign_document_link_columns(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    cols = {c["name"] for c in inspector.get_columns("test_campaign_document_link")}
    assert cols == {"campaign_id", "document_id", "label"}
    fks = inspector.get_foreign_keys("test_campaign_document_link")
    referred = {fk.get("referred_table") for fk in fks}
    assert {"test_campaign", "document"}.issubset(referred)


def test_test_campaign_participant_has_surrogate_id(tmp_db_path: Path) -> None:
    """``role`` ist per PATCH änderbar — die Tabelle hat einen
    Surrogat-PK plus eindeutigem Paar (campaign_id, person_id)."""
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    cols = {c["name"] for c in inspector.get_columns("test_campaign_participant")}
    assert {"id", "campaign_id", "person_id", "role", "note"}.issubset(cols)
    pks = inspector.get_pk_constraint("test_campaign_participant")
    assert pks["constrained_columns"] == ["id"]
    uqs = inspector.get_unique_constraints("test_campaign_participant")
    pairs = [tuple(uq["column_names"]) for uq in uqs]
    assert ("campaign_id", "person_id") in pairs


def test_no_test_campaign_upload_or_file_table(tmp_db_path: Path) -> None:
    """Block 0022 baut keinen eigenen Datei-/Upload-Pfad für Kampagnen."""
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    tables = set(inspector.get_table_names())
    for forbidden in (
        "test_campaign_file",
        "test_campaign_upload",
        "test_campaign_attachment",
        "campaign_file",
    ):
        assert forbidden not in tables


def test_downgrade_to_0010_drops_test_campaign_tables(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    # Erst 0012 wegräumen (document_comment hängt an document_version).
    command.downgrade(cfg, "0011_test_campaigns")
    command.downgrade(cfg, "0010_meetings")
    inspector = inspect(create_engine(db_url))
    tables = set(inspector.get_table_names())
    assert tables.isdisjoint(TEST_CAMPAIGN_TABLES)
    # Meeting-Tabellen müssen aber noch da sein.
    assert MEETING_TABLES.issubset(tables)


# ---- Block 0024 — Dokumentkommentare ----------------------------------


DOCUMENT_COMMENT_COLUMNS = {
    "id",
    "document_version_id",
    "author_person_id",
    "text",
    "status",
    "created_at",
    "updated_at",
    "submitted_at",
    "is_deleted",
}


def test_document_comment_table_exists_with_expected_columns(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    assert "document_comment" in set(inspector.get_table_names())
    cols = {c["name"] for c in inspector.get_columns("document_comment")}
    assert DOCUMENT_COMMENT_COLUMNS == cols


def test_document_comment_has_version_and_author_fk(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    fks = inspector.get_foreign_keys("document_comment")
    referred = {fk.get("referred_table") for fk in fks}
    assert {"document_version", "person"}.issubset(referred)


def test_document_comment_nullability(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    cols = {c["name"]: c for c in inspector.get_columns("document_comment")}
    # submitted_at darf NULL sein, der Rest nicht.
    assert cols["submitted_at"]["nullable"] is True
    for required in (
        "id",
        "document_version_id",
        "author_person_id",
        "text",
        "status",
        "created_at",
        "updated_at",
        "is_deleted",
    ):
        assert cols[required]["nullable"] is False


def test_downgrade_to_0011_drops_document_comment(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0011_test_campaigns")
    inspector = inspect(create_engine(db_url))
    assert "document_comment" not in set(inspector.get_table_names())


# ---- Block 0027 — Workpackage-Zeitplan -------------------------------


def test_workpackage_has_schedule_columns(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    cols = {c["name"]: c for c in inspector.get_columns("workpackage")}
    assert "start_date" in cols
    assert "end_date" in cols
    assert cols["start_date"]["nullable"] is True
    assert cols["end_date"]["nullable"] is True


def test_downgrade_to_0012_drops_schedule_columns(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0012_document_comments")
    inspector = inspect(create_engine(db_url))
    cols = {c["name"] for c in inspector.get_columns("workpackage")}
    assert "start_date" not in cols
    assert "end_date" not in cols


# ---- Block 0027 — Folge-Migration 0014 (Seed-Datumswerte) ------------


def _setup_partner_and_wp(
    db_url: str,
    *,
    code: str,
    start: str | None,
    end: str | None,
    partner_id: str = "11111111-1111-1111-1111-111111111111",
    wp_id_suffix: str = "AAAA",
) -> str:
    """Helfer: erzeuge minimale Partner-/WP-Daten direkt per SQL.

    Wir testen die Migration auf einer fortgeschrittenen Schema-Version
    (head). Der Workpackage-Insert erfordert lead_partner_id und
    sort_order — das kürzeste Setup geht direkt am Cursor.
    """
    engine = create_engine(db_url)
    wp_id = f"99999999-9999-9999-9999-{wp_id_suffix:>012}"
    with engine.begin() as conn:
        # Partner anlegen, falls noch nicht vorhanden.
        existing = conn.exec_driver_sql(
            "SELECT id FROM partner WHERE id = :pid",
            {"pid": partner_id},
        ).fetchone()
        if existing is None:
            conn.exec_driver_sql(
                "INSERT INTO partner (id, name, short_name, country, is_deleted, "
                "created_at, updated_at, is_active, unit_address_same_as_organization) "
                "VALUES (:pid, 'P', :short, 'DE', 0, datetime('now'), datetime('now'), 1, 1)",
                {"pid": partner_id, "short": partner_id[:8]},
            )
        conn.exec_driver_sql(
            "INSERT INTO workpackage (id, code, title, lead_partner_id, sort_order, "
            "is_deleted, created_at, updated_at, status, start_date, end_date) "
            "VALUES (:wid, :code, 'X', :pid, 0, 0, datetime('now'), datetime('now'), "
            "'planned', :start, :end)",
            {"wid": wp_id, "code": code, "pid": partner_id, "start": start, "end": end},
        )
    engine.dispose()
    return wp_id


def _read_dates(db_url: str, code: str) -> tuple[str | None, str | None]:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        row = conn.exec_driver_sql(
            "SELECT start_date, end_date FROM workpackage WHERE code = :code",
            {"code": code},
        ).fetchone()
    engine.dispose()
    return (row[0], row[1]) if row else (None, None)


def test_upgrade_0014_sets_dates_for_null_pairs(tmp_db_path: Path) -> None:
    """Bestands-WP mit NULL/NULL bekommt durch Migration 0014 die
    Seed-Werte."""
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    # Erst auf 0013 hochfahren (Spalten existieren, Seed-Migration noch nicht).
    command.upgrade(cfg, "0013_workpackage_schedule")
    _setup_partner_and_wp(db_url, code="WP3.1", start=None, end=None, wp_id_suffix="000031A")
    # Dann auf head (= 0014) — Werte sollten gesetzt sein.
    command.upgrade(cfg, "head")
    start, end = _read_dates(db_url, "WP3.1")
    assert start == "2026-03-01"
    assert end == "2028-02-29"


def test_upgrade_0014_skips_existing_full_dates(tmp_db_path: Path) -> None:
    """Wenn beide Werte bereits gesetzt sind (manuell), bleibt alles
    unverändert."""
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "0013_workpackage_schedule")
    _setup_partner_and_wp(
        db_url,
        code="WP4.1",
        start="2027-01-15",
        end="2027-09-30",
        wp_id_suffix="000041B",
    )
    command.upgrade(cfg, "head")
    start, end = _read_dates(db_url, "WP4.1")
    assert start == "2027-01-15"
    assert end == "2027-09-30"


def test_upgrade_0014_skips_partial_dates(tmp_db_path: Path) -> None:
    """Wenn nur eines der beiden Felder gesetzt ist, wird der
    Datensatz NICHT überschrieben."""
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "0013_workpackage_schedule")
    _setup_partner_and_wp(
        db_url, code="WP6.3", start="2027-04-01", end=None, wp_id_suffix="000063C"
    )
    command.upgrade(cfg, "head")
    start, end = _read_dates(db_url, "WP6.3")
    assert start == "2027-04-01"
    assert end is None


def test_downgrade_0014_clears_unmodified_seed_values(tmp_db_path: Path) -> None:
    """Wenn die Werte exakt dem Seed entsprechen, räumt das Downgrade
    sie wieder auf (zurück zu NULL/NULL)."""
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "0013_workpackage_schedule")
    _setup_partner_and_wp(db_url, code="WP3.1", start=None, end=None, wp_id_suffix="000031D")
    command.upgrade(cfg, "head")
    # Sanity
    assert _read_dates(db_url, "WP3.1") == ("2026-03-01", "2028-02-29")
    # Down auf 0013
    command.downgrade(cfg, "0013_workpackage_schedule")
    assert _read_dates(db_url, "WP3.1") == (None, None)


def test_downgrade_0014_keeps_modified_values(tmp_db_path: Path) -> None:
    """Manuell veränderte Werte bleiben beim Downgrade erhalten."""
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "0013_workpackage_schedule")
    _setup_partner_and_wp(db_url, code="WP3.1", start=None, end=None, wp_id_suffix="000031E")
    command.upgrade(cfg, "head")
    # Admin ändert das End-Datum manuell.
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "UPDATE workpackage SET end_date = :new_end WHERE code = 'WP3.1'",
            {"new_end": "2028-06-30"},
        )
    engine.dispose()
    # Down auf 0013 — start_date ist Seed-Wert, end_date weicht ab.
    # Da die Bedingung „beide exakt Seed" verlangt, wird nichts angerührt.
    command.downgrade(cfg, "0013_workpackage_schedule")
    start, end = _read_dates(db_url, "WP3.1")
    assert start == "2026-03-01"
    assert end == "2028-06-30"


def test_upgrade_0014_safe_on_unknown_codes(tmp_db_path: Path) -> None:
    """Eine DB ohne die bekannten WP-Codes überlebt das Upgrade
    schadlos (kein Crash, keine Inserts)."""
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "0013_workpackage_schedule")
    _setup_partner_and_wp(db_url, code="WP-FREMD", start=None, end=None, wp_id_suffix="000FREM")
    command.upgrade(cfg, "head")
    # Unbekannter Code bleibt unverändert.
    assert _read_dates(db_url, "WP-FREMD") == (None, None)


def test_migration_0014_values_match_yaml() -> None:
    """Sync-Sicherung: WP_SCHEDULE in der Migration entspricht 1:1
    den ``start_month``/``end_month``-Werten in
    ``antrag_initial.yaml``. Driftet einer der beiden, bricht der
    Test, bevor jemand Bestands-DBs in ein inkonsistentes Schema
    überführt.
    """
    import importlib.util

    import yaml as yaml_lib

    # Migrations-Dateinamen beginnen mit einer Ziffer und sind über
    # ``importlib.import_module`` nicht erreichbar. Direkt per
    # File-Location laden.
    mig_path = ALEMBIC_DIR / "versions" / "0014_seed_workpackage_schedule.py"
    spec = importlib.util.spec_from_file_location("_mig_0014", mig_path)
    assert spec is not None and spec.loader is not None
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    mig_pairs = {code: (sm, em) for code, sm, em in mig.WP_SCHEDULE}

    seed_path = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "ref4ep"
        / "cli"
        / "seed_data"
        / "antrag_initial.yaml"
    )
    seed_data = yaml_lib.safe_load(seed_path.read_text(encoding="utf-8"))
    yaml_pairs = {
        item["code"]: (item.get("start_month"), item.get("end_month"))
        for item in seed_data["workpackages"]
        if item.get("start_month") is not None and item.get("end_month") is not None
    }
    assert mig_pairs == yaml_pairs, (
        "Migration 0014 (WP_SCHEDULE) und antrag_initial.yaml sind aus dem Tritt — "
        "wenn die YAML bewusst geändert wird, muss eine NEUE Migration die Differenz "
        "auf Bestands-DBs nachziehen."
    )


# ---- Block 0028 — Foto-Upload für Testkampagnen ----------------------


TEST_CAMPAIGN_PHOTO_COLUMNS = {
    "id",
    "campaign_id",
    "uploaded_by_person_id",
    "storage_key",
    "original_filename",
    "mime_type",
    "file_size_bytes",
    "sha256",
    "caption",
    "taken_at",
    "created_at",
    "updated_at",
    "is_deleted",
    # Block 0032 — Thumbnail-Felder.
    "thumbnail_storage_key",
    "thumbnail_mime_type",
    "thumbnail_size_bytes",
}


def test_test_campaign_photo_table_exists(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    assert "test_campaign_photo" in set(inspector.get_table_names())
    cols = {c["name"] for c in inspector.get_columns("test_campaign_photo")}
    assert TEST_CAMPAIGN_PHOTO_COLUMNS == cols


def test_test_campaign_photo_has_fks(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    fks = inspect(create_engine(db_url)).get_foreign_keys("test_campaign_photo")
    referred = {fk.get("referred_table") for fk in fks}
    assert {"test_campaign", "person"}.issubset(referred)


def test_downgrade_to_0014_drops_photo_table(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0014_seed_workpackage_schedule")
    inspector = inspect(create_engine(db_url))
    assert "test_campaign_photo" not in set(inspector.get_table_names())


# ---- Block 0029 — Kampagnennotizen -----------------------------------


TEST_CAMPAIGN_NOTE_COLUMNS = {
    "id",
    "campaign_id",
    "author_person_id",
    "body_md",
    "created_at",
    "updated_at",
    "is_deleted",
}


def test_test_campaign_note_table_exists(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    inspector = inspect(create_engine(db_url))
    assert "test_campaign_note" in set(inspector.get_table_names())
    cols = {c["name"] for c in inspector.get_columns("test_campaign_note")}
    assert TEST_CAMPAIGN_NOTE_COLUMNS == cols


def test_test_campaign_note_has_fks(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    fks = inspect(create_engine(db_url)).get_foreign_keys("test_campaign_note")
    referred = {fk.get("referred_table") for fk in fks}
    assert {"test_campaign", "person"}.issubset(referred)


def test_downgrade_to_0015_drops_note_table(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0015_test_campaign_photos")
    inspector = inspect(create_engine(db_url))
    assert "test_campaign_note" not in set(inspector.get_table_names())


# ---- Block 0032 — Foto-Thumbnails -----------------------------------


def test_test_campaign_photo_thumbnail_columns_present(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    cols = {c["name"] for c in inspect(create_engine(db_url)).get_columns("test_campaign_photo")}
    assert {
        "thumbnail_storage_key",
        "thumbnail_mime_type",
        "thumbnail_size_bytes",
    }.issubset(cols)


def test_thumbnail_columns_are_nullable(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    cols = {c["name"]: c for c in inspect(create_engine(db_url)).get_columns("test_campaign_photo")}
    for name in ("thumbnail_storage_key", "thumbnail_mime_type", "thumbnail_size_bytes"):
        assert cols[name]["nullable"] is True


def test_downgrade_to_0016_drops_thumbnail_columns(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0016_test_campaign_notes")
    cols = {c["name"] for c in inspect(create_engine(db_url)).get_columns("test_campaign_photo")}
    assert "thumbnail_storage_key" not in cols
    assert "thumbnail_mime_type" not in cols
    assert "thumbnail_size_bytes" not in cols


# ---- Block 0035 — Projektbibliothek ----------------------------------


def test_document_workpackage_id_is_nullable_after_0018(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    cols = {c["name"]: c for c in inspect(create_engine(db_url)).get_columns("document")}
    assert cols["workpackage_id"]["nullable"] is True


def test_document_has_library_section_after_0018(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    command.upgrade(_make_config(db_url), "head")
    cols = {c["name"]: c for c in inspect(create_engine(db_url)).get_columns("document")}
    assert "library_section" in cols
    assert cols["library_section"]["nullable"] is True


def test_downgrade_to_0017_drops_library_section(tmp_db_path: Path) -> None:
    db_url = f"sqlite:///{tmp_db_path}"
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0017_test_campaign_photo_thumbnails")
    cols = {c["name"] for c in inspect(create_engine(db_url)).get_columns("document")}
    assert "library_section" not in cols
