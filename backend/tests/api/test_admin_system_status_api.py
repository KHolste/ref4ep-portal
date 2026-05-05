"""API: Admin-Systemstatus (Block 0019).

Permission-Matrix, Backup-Erkennung (fehlend / leer / aktuell / alt),
Storage, Counts, Datenleckschutz.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.domain.models import Person
from ref4ep.services.meeting_service import MeetingService

# ---- Auth-Matrix -----------------------------------------------------


def test_anonymous_cannot_read_status(client: TestClient) -> None:
    client.cookies.clear()
    r = client.get("/api/admin/system/status")
    assert r.status_code == 401


def test_member_cannot_read_status(member_client: TestClient) -> None:
    r = member_client.get("/api/admin/system/status")
    assert r.status_code == 403


def test_wp_lead_cannot_read_status(member_client: TestClient, lead_in_wp3) -> None:
    """WP-Lead ist plattformrechtlich Member — Endpoint bleibt verboten."""
    r = member_client.get("/api/admin/system/status")
    assert r.status_code == 403


def test_admin_can_read_status(admin_client: TestClient) -> None:
    r = admin_client.get("/api/admin/system/status")
    assert r.status_code == 200, r.text
    body = r.json()
    # Pflichtsektionen vorhanden.
    assert "app" in body and "current_time" in body["app"]
    assert "database" in body
    assert "backups" in body
    assert "storage" in body
    assert "counts" in body
    assert "health" in body
    # Logs werden in diesem Block bewusst noch nicht ausgespielt.
    assert body["logs"] is None


# ---- Datenbank / Alembic ---------------------------------------------


def test_response_contains_alembic_revision(admin_client: TestClient) -> None:
    body = admin_client.get("/api/admin/system/status").json()
    rev = body["database"]["alembic_revision"]
    assert rev is not None and isinstance(rev, str) and rev != ""


def test_response_contains_db_path_and_size(admin_client: TestClient) -> None:
    body = admin_client.get("/api/admin/system/status").json()
    db = body["database"]
    # Tests laufen mit SQLite — db_path muss gesetzt und Datei vorhanden sein.
    assert db["db_path"]
    assert db["db_exists"] is True
    assert isinstance(db["db_size_bytes"], int) and db["db_size_bytes"] > 0


# ---- Storage ---------------------------------------------------------


def test_response_contains_storage_metrics(admin_client: TestClient) -> None:
    body = admin_client.get("/api/admin/system/status").json()
    s = body["storage"]
    assert "free_bytes" in s and isinstance(s["free_bytes"], int)
    assert "free_percent" in s and isinstance(s["free_percent"], float)
    assert s["free_bytes"] >= 0
    assert 0.0 <= s["free_percent"] <= 100.0


# ---- Counts ----------------------------------------------------------


def test_counts_reflect_seeded_db(
    admin_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
) -> None:
    body = admin_client.get("/api/admin/system/status").json()
    c = body["counts"]
    # Mindestens admin + member existieren.
    assert c["persons"] >= 2
    assert c["active_persons"] >= 2
    # Seed legt Partner an.
    assert c["partners"] >= 1
    # Noch keine Meetings/Actions/Documents im Seed.
    assert c["documents"] == 0
    assert c["meetings"] == 0
    assert c["open_actions"] == 0
    assert c["overdue_actions"] == 0


def test_counts_track_new_meeting_actions(
    admin_client: TestClient,
    seeded_session: Session,
    admin_person_id: str,
) -> None:
    admin = seeded_session.query(Person).filter_by(email="admin@test.example").one()
    service = MeetingService(seeded_session, role=admin.platform_role, person_id=admin.id)
    meeting = service.create_meeting(
        title="Aufgabenquelle",
        starts_at=datetime.now(tz=UTC),
        workpackage_ids=[],
    )
    service.create_action(meeting_id=meeting.id, text="X", status="open")
    service.create_action(meeting_id=meeting.id, text="Y", status="in_progress")
    service.create_action(meeting_id=meeting.id, text="Z", status="done")
    seeded_session.commit()
    body = admin_client.get("/api/admin/system/status").json()
    c = body["counts"]
    assert c["meetings"] == 1
    assert c["open_actions"] == 2  # open + in_progress; done zählt nicht


# ---- Backups ---------------------------------------------------------


@pytest.fixture
def with_backup_dir(admin_client: TestClient, tmp_path: Path):
    """Setzt den Backup-Pfad in den App-Settings auf einen Test-Pfad und
    räumt nach dem Test wieder auf."""
    original = admin_client.app.state.settings.backup_dir

    def _set(path: Path) -> None:
        admin_client.app.state.settings.backup_dir = str(path)

    yield _set
    admin_client.app.state.settings.backup_dir = original


def test_missing_backup_dir_yields_warning_not_500(
    admin_client: TestClient, tmp_path: Path, with_backup_dir
) -> None:
    nonexistent = tmp_path / "no-such-backup-dir"
    with_backup_dir(nonexistent)
    r = admin_client.get("/api/admin/system/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["backups"]["backup_dir_exists"] is False
    assert body["backups"]["backup_count"] == 0
    assert body["backups"]["latest_backup_name"] is None
    assert any("Backup-Verzeichnis nicht gefunden" in w for w in body["health"]["warnings"])
    # Status darf nicht „ok" sein — wenigstens warning.
    assert body["health"]["status"] in ("warning", "error")


def test_empty_backup_dir_yields_warning(
    admin_client: TestClient, tmp_path: Path, with_backup_dir
) -> None:
    backup_dir = tmp_path / "backups-empty"
    backup_dir.mkdir()
    with_backup_dir(backup_dir)
    body = admin_client.get("/api/admin/system/status").json()
    assert body["backups"]["backup_dir_exists"] is True
    assert body["backups"]["backup_count"] == 0
    assert any("Keine Backups" in w for w in body["health"]["warnings"])


def test_recent_backup_is_detected(
    admin_client: TestClient, tmp_path: Path, with_backup_dir
) -> None:
    backup_dir = tmp_path / "backups-fresh"
    backup_dir.mkdir()
    fresh = backup_dir / "ref4ep-backup-20260601-120000.tar.gz"
    fresh.write_bytes(b"x" * 2048)
    # Frische Datei (jetzt) soll keine „älter als"-Warnung erzeugen.
    older = backup_dir / "ref4ep-backup-20260101-080000.tar.gz"
    older.write_bytes(b"x" * 512)
    old_ts = (datetime.now(tz=UTC) - timedelta(hours=12)).timestamp()
    fresh_ts = datetime.now(tz=UTC).timestamp()
    os.utime(fresh, (fresh_ts, fresh_ts))
    os.utime(older, (old_ts, old_ts))
    with_backup_dir(backup_dir)

    body = admin_client.get("/api/admin/system/status").json()
    b = body["backups"]
    assert b["backup_count"] == 2
    assert b["latest_backup_name"] == "ref4ep-backup-20260601-120000.tar.gz"
    assert b["latest_backup_size_bytes"] == 2048
    assert b["latest_backup_mtime"] is not None
    # Aktuelles Backup → keine „älter als"-Warnung.
    assert not any("älter als" in w for w in body["health"]["warnings"])


def test_old_backup_yields_stale_warning(
    admin_client: TestClient, tmp_path: Path, with_backup_dir
) -> None:
    backup_dir = tmp_path / "backups-old"
    backup_dir.mkdir()
    f = backup_dir / "ref4ep-backup-20200101-120000.tar.gz"
    f.write_bytes(b"x" * 1024)
    five_days_ago = (datetime.now(tz=UTC) - timedelta(days=5)).timestamp()
    os.utime(f, (five_days_ago, five_days_ago))
    with_backup_dir(backup_dir)

    body = admin_client.get("/api/admin/system/status").json()
    assert any("älter als" in w for w in body["health"]["warnings"])


def test_unrelated_files_are_not_counted_as_backups(
    admin_client: TestClient, tmp_path: Path, with_backup_dir
) -> None:
    backup_dir = tmp_path / "backups-mixed"
    backup_dir.mkdir()
    # Match: gehört dazu.
    (backup_dir / "ref4ep-backup-20260601-120000.tar.gz").write_bytes(b"x")
    # Kein Match: README, anderes Format, falsche Endung.
    (backup_dir / "README.md").write_bytes(b"x")
    (backup_dir / "ref4ep-backup-20260601-120000.zip").write_bytes(b"x")
    (backup_dir / "ref4ep-backup-other.tar.gz.bak").write_bytes(b"x")
    with_backup_dir(backup_dir)

    body = admin_client.get("/api/admin/system/status").json()
    assert body["backups"]["backup_count"] == 1


# ---- Health-Aggregation ----------------------------------------------


def test_health_status_warning_when_only_warnings(
    admin_client: TestClient, tmp_path: Path, with_backup_dir
) -> None:
    with_backup_dir(tmp_path / "no-such")
    body = admin_client.get("/api/admin/system/status").json()
    assert body["health"]["status"] == "warning"
    assert body["health"]["warnings"]


# ---- Sicherheits-Smoke (keine Secrets) -------------------------------


def test_response_does_not_leak_session_secret_or_passwords(
    admin_client: TestClient,
) -> None:
    body_text = admin_client.get("/api/admin/system/status").text
    lower = body_text.lower()
    # Tests-Setup nutzt 48× "x" als Session-Secret — eine 16er-Sequenz wäre
    # ein klares Indiz für ein Leak. Keine echten Secrets im Repo.
    assert "x" * 16 not in body_text
    # Keine Passwort-Felder im Stream.
    assert "password" not in lower
    assert "session_secret" not in lower
    # Kein Database-URL-Schema („sqlite:///") als Volltext.
    assert "sqlite:///" not in body_text


# ---- Block 0021 — Upload-Speicher-Sektion ----------------------------


import tarfile  # noqa: E402 — bewusst lokal importiert für die Block-Tests.


@pytest.fixture
def setup_backup_archive(admin_client: TestClient, tmp_path: Path, with_backup_dir):
    """Hilfsfixture: legt ein Backup-Verzeichnis an, schreibt ein
    tar.gz-Archiv mit konfigurierbaren Inhalten und setzt es als
    aktuelles Backup-Verzeichnis in den Settings."""

    backup_dir = tmp_path / "backups-uploads"
    backup_dir.mkdir()

    def _write(*, name: str, members: list[str], corrupt: bool = False) -> Path:
        archive = backup_dir / name
        if corrupt:
            # Bewusst kein gültiges gzip — Tarfile soll Lesefehler werfen.
            archive.write_bytes(b"not really a tar.gz file")
        else:
            with tarfile.open(str(archive), mode="w:gz") as tf:
                for member_name in members:
                    payload = member_name.encode("utf-8")
                    info = tarfile.TarInfo(name=member_name)
                    info.size = len(payload)
                    tf.addfile(info, fileobj=__import__("io").BytesIO(payload))
        with_backup_dir(backup_dir)
        return archive

    return _write


def _populate_storage_with_files(admin_client: TestClient, *, files: dict[str, bytes]) -> None:
    """Schreibt Dateien in das storage_dir der App. Übergibt relative
    Pfade (z. B. ``"a.txt"`` oder ``"documents/x.bin"``)."""
    storage_dir = Path(admin_client.app.state.settings.storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    for rel, payload in files.items():
        target = storage_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)


def test_response_contains_uploads_section_with_required_fields(
    admin_client: TestClient,
) -> None:
    body = admin_client.get("/api/admin/system/status").json()
    assert "uploads" in body
    u = body["uploads"]
    for key in (
        "storage_dir",
        "storage_dir_exists",
        "storage_total_bytes",
        "storage_file_count",
        "data_dir",
        "data_dir_total_bytes",
        "data_file_count",
        "document_storage_file_count",
        "document_storage_total_bytes",
        "backup_contains_storage",
        "backup_contains_database",
        "backup_checked_name",
    ):
        assert key in u, f"uploads.{key} fehlt"


def test_uploads_count_files_in_storage(admin_client: TestClient) -> None:
    _populate_storage_with_files(
        admin_client,
        files={
            "a.bin": b"x" * 100,
            "sub/b.bin": b"y" * 200,
            "sub/sub2/c.bin": b"z" * 300,
        },
    )
    u = admin_client.get("/api/admin/system/status").json()["uploads"]
    assert u["storage_dir_exists"] is True
    assert u["storage_file_count"] == 3
    assert u["storage_total_bytes"] == 600


def test_empty_storage_dir_yields_warning_no_500(admin_client: TestClient) -> None:
    # Default-Test-Storage ist initial leer.
    body = admin_client.get("/api/admin/system/status").json()
    u = body["uploads"]
    assert u["storage_dir_exists"] is True
    assert u["storage_file_count"] == 0
    assert u["storage_total_bytes"] == 0
    assert any("Keine Upload-Dateien" in w for w in body["health"]["warnings"])


def test_missing_storage_dir_yields_warning_no_500(
    admin_client: TestClient, tmp_path: Path
) -> None:
    nonexistent = tmp_path / "no-storage-here"
    admin_client.app.state.settings.storage_dir = str(nonexistent)
    try:
        body = admin_client.get("/api/admin/system/status").json()
    finally:
        # Storage-Setting nicht dauerhaft kaputt zurücklassen.
        pass
    u = body["uploads"]
    assert u["storage_dir_exists"] is False
    assert u["storage_file_count"] == 0
    assert any("Upload-Speicherverzeichnis nicht gefunden" in w for w in body["health"]["warnings"])


def test_data_dir_total_includes_db_and_storage_files(
    admin_client: TestClient,
) -> None:
    _populate_storage_with_files(admin_client, files={"a.bin": b"x" * 1024})
    u = admin_client.get("/api/admin/system/status").json()["uploads"]
    # data/ enthält die Test-DB + a.bin → mindestens beide Dateien.
    assert u["data_file_count"] >= 2
    # data_dir_total_bytes umfasst zumindest die 1024-Byte-Datei.
    assert u["data_dir_total_bytes"] >= 1024


def test_documents_subdir_is_reported_when_present(admin_client: TestClient) -> None:
    _populate_storage_with_files(
        admin_client,
        files={
            "documents/x.pdf": b"PDFDATA" * 10,
            "documents/y.pdf": b"PDFDATA" * 5,
            "other/z.bin": b"x",
        },
    )
    u = admin_client.get("/api/admin/system/status").json()["uploads"]
    # Nur die Dateien unter documents/ zählen für die Dokument-Aufschlüsselung.
    assert u["document_storage_file_count"] == 2
    assert u["document_storage_total_bytes"] == 7 * (10 + 5)
    # storage_file_count zählt alle.
    assert u["storage_file_count"] == 3


def test_documents_subdir_is_null_when_missing(admin_client: TestClient) -> None:
    u = admin_client.get("/api/admin/system/status").json()["uploads"]
    # Default-Test-Storage hat kein documents/-Unterverzeichnis.
    assert u["document_storage_file_count"] is None
    assert u["document_storage_total_bytes"] is None


def test_backup_check_skipped_when_no_backup_present(
    admin_client: TestClient, tmp_path: Path, with_backup_dir
) -> None:
    empty = tmp_path / "no-backups-uploads-test"
    empty.mkdir()
    with_backup_dir(empty)
    u = admin_client.get("/api/admin/system/status").json()["uploads"]
    assert u["backup_checked_name"] is None
    assert u["backup_contains_database"] is None
    assert u["backup_contains_storage"] is None


def test_backup_with_db_and_storage_passes_checks(
    admin_client: TestClient, setup_backup_archive
) -> None:
    setup_backup_archive(
        name="ref4ep-backup-20260601-120000.tar.gz",
        members=["data/ref4ep.db", "data/storage/documents/x.pdf"],
    )
    body = admin_client.get("/api/admin/system/status").json()
    u = body["uploads"]
    assert u["backup_checked_name"] == "ref4ep-backup-20260601-120000.tar.gz"
    assert u["backup_contains_database"] is True
    assert u["backup_contains_storage"] is True
    # Keine Backup-Inhalt-Warnings.
    warnings = body["health"]["warnings"]
    assert not any("Backup enthält keine" in w for w in warnings)
    assert not any("Backup enthält keinen" in w for w in warnings)


def test_backup_without_database_yields_warning(
    admin_client: TestClient, setup_backup_archive
) -> None:
    setup_backup_archive(
        name="ref4ep-backup-20260601-120000.tar.gz",
        members=["data/storage/documents/x.pdf"],
    )
    body = admin_client.get("/api/admin/system/status").json()
    u = body["uploads"]
    assert u["backup_contains_database"] is False
    assert u["backup_contains_storage"] is True
    assert any(
        "Neuestes Backup enthält keine Datenbankdatei" in w for w in body["health"]["warnings"]
    )


def test_backup_without_storage_yields_warning(
    admin_client: TestClient, setup_backup_archive
) -> None:
    setup_backup_archive(
        name="ref4ep-backup-20260601-120000.tar.gz",
        members=["data/ref4ep.db"],
    )
    body = admin_client.get("/api/admin/system/status").json()
    u = body["uploads"]
    assert u["backup_contains_database"] is True
    assert u["backup_contains_storage"] is False
    assert any(
        "Neuestes Backup enthält keinen Upload-Speicher" in w for w in body["health"]["warnings"]
    )


def test_corrupt_backup_yields_warning_not_500(
    admin_client: TestClient, setup_backup_archive
) -> None:
    setup_backup_archive(
        name="ref4ep-backup-20260601-120000.tar.gz",
        members=[],
        corrupt=True,
    )
    r = admin_client.get("/api/admin/system/status")
    assert r.status_code == 200, r.text
    body = r.json()
    u = body["uploads"]
    # Lesefehler → Inhaltsfelder bleiben „unbekannt".
    assert u["backup_contains_database"] is None
    assert u["backup_contains_storage"] is None
    assert any("Backup-Archiv konnte nicht gelesen werden" in w for w in body["health"]["warnings"])


def test_uploads_section_does_not_leak_secrets(admin_client: TestClient) -> None:
    body_text = admin_client.get("/api/admin/system/status").text
    lower = body_text.lower()
    assert "session_secret" not in lower
    assert "password" not in lower
