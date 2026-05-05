"""Systemstatus-/Smoke-Test-Service (Admin-only).

Sammelt Betriebs- und Smoke-Test-Werte: DB- und Alembic-Status,
Backup-Erkennung, Speicherplatz, Objektzahlen, abgeleitete Health-
Warnings.

Bewusst defensive Implementierung — der Endpoint soll auch dann
antworten, wenn einzelne Bestandteile (Backup-Verzeichnis,
``alembic_version``-Tabelle, …) fehlen oder unzugänglich sind. Fehler
werden in die ``warnings``/``errors``-Liste übersetzt, statt einen
500er auszulösen.

Sicherheits-Filter:
- Keine Secrets aus ``.env`` ausgeben.
- Keine Datenbank-Passwörter, keine Session-Secrets.
- Nur Pfade, die betrieblich sinnvoll sind.
"""

from __future__ import annotations

import os
import shutil
import tarfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from ref4ep.domain.models import (
    Document,
    Meeting,
    MeetingAction,
    Partner,
    Person,
)

BACKUP_FILENAME_GLOB = "ref4ep-backup-*.tar.gz"
BACKUP_STALE_AFTER_HOURS = 48
DISK_FREE_WARNING_PERCENT = 15.0
DISK_FREE_ERROR_PERCENT = 5.0


@dataclass(frozen=True)
class AppInfo:
    name: str
    version: str
    current_time: datetime


@dataclass(frozen=True)
class DatabaseInfo:
    alembic_revision: str | None
    db_path: str | None
    db_size_bytes: int | None
    db_exists: bool


@dataclass(frozen=True)
class BackupInfo:
    backup_dir: str
    backup_dir_exists: bool
    latest_backup_name: str | None
    latest_backup_mtime: datetime | None
    latest_backup_size_bytes: int | None
    backup_count: int


@dataclass(frozen=True)
class StorageInfo:
    data_dir: str
    measured_at_path: str
    total_bytes: int | None
    used_bytes: int | None
    free_bytes: int | None
    free_percent: float | None


@dataclass(frozen=True)
class CountsInfo:
    persons: int
    active_persons: int
    partners: int
    documents: int
    meetings: int
    open_actions: int
    overdue_actions: int


@dataclass(frozen=True)
class HealthInfo:
    status: str  # "ok" | "warning" | "error"
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UploadStorageInfo:
    """Trennung Metadaten ↔ Dateispeicher sichtbar machen.

    Felder mit ``None`` zeigen explizit „unbekannt" an (z. B. wenn das
    Backup gar nicht existiert oder das Dokument-Unterverzeichnis fehlt)
    — sie sind nicht 0/false, damit die UI „nein" und „unbekannt"
    auseinanderhalten kann.
    """

    storage_dir: str
    storage_dir_exists: bool
    storage_total_bytes: int
    storage_file_count: int
    data_dir: str
    data_dir_total_bytes: int
    data_file_count: int
    document_storage_file_count: int | None
    document_storage_total_bytes: int | None
    backup_contains_storage: bool | None
    backup_contains_database: bool | None
    backup_checked_name: str | None


@dataclass(frozen=True)
class SystemStatus:
    app: AppInfo
    database: DatabaseInfo
    backups: BackupInfo
    storage: StorageInfo
    uploads: UploadStorageInfo
    counts: CountsInfo
    health: HealthInfo
    # logs ist absichtlich None — siehe Bericht/offene Punkte.
    logs: dict | None = None


# --------------------------------------------------------------------------- #
# Helfer                                                                      #
# --------------------------------------------------------------------------- #


def _sqlite_path_from_url(database_url: str) -> str | None:
    """Liefert den Datei-Pfad einer SQLite-URL — sonst ``None``."""
    try:
        url = make_url(database_url)
    except Exception:
        return None
    if not url.drivername.startswith("sqlite"):
        return None
    db = url.database
    if not db or db == ":memory:":
        return None
    return db


def _first_existing_path(path: Path) -> Path:
    """Erster existierender Pfad in der Eltern-Kette — fällt auf ``Path.cwd()``
    zurück, damit ``shutil.disk_usage`` nicht crasht."""
    p = path
    seen: set[Path] = set()
    while p not in seen:
        seen.add(p)
        if p.exists():
            return p
        if p.parent == p:
            break
        p = p.parent
    return Path.cwd()


def get_alembic_revision(engine: Engine) -> str | None:
    """Liest die aktuelle Alembic-Revision aus ``alembic_version``.

    Greift bewusst nicht auf das Alembic-CLI zu. Ergebnis ist ``None``,
    wenn die Tabelle fehlt oder leer ist.
    """
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).first()
            if row is None:
                return None
            return str(row[0])
    except Exception:
        return None


def _collect_database(engine: Engine, database_url: str) -> DatabaseInfo:
    revision = get_alembic_revision(engine)
    db_path_str = _sqlite_path_from_url(database_url)
    if db_path_str is None:
        # Nicht-SQLite-Backend (z. B. Postgres in Prod) — Pfad/Größe liefern
        # wir hier nicht, weil shutil das nicht ohne Server-Login könnte.
        return DatabaseInfo(
            alembic_revision=revision,
            db_path=None,
            db_size_bytes=None,
            db_exists=True,
        )
    db_path = Path(db_path_str)
    if db_path.is_file():
        return DatabaseInfo(
            alembic_revision=revision,
            db_path=str(db_path),
            db_size_bytes=db_path.stat().st_size,
            db_exists=True,
        )
    return DatabaseInfo(
        alembic_revision=revision,
        db_path=str(db_path),
        db_size_bytes=None,
        db_exists=False,
    )


def _collect_backups(backup_dir_str: str) -> BackupInfo:
    backup_dir = Path(backup_dir_str)
    if not backup_dir.is_dir():
        return BackupInfo(
            backup_dir=str(backup_dir),
            backup_dir_exists=False,
            latest_backup_name=None,
            latest_backup_mtime=None,
            latest_backup_size_bytes=None,
            backup_count=0,
        )
    files = [p for p in backup_dir.glob(BACKUP_FILENAME_GLOB) if p.is_file()]
    if not files:
        return BackupInfo(
            backup_dir=str(backup_dir),
            backup_dir_exists=True,
            latest_backup_name=None,
            latest_backup_mtime=None,
            latest_backup_size_bytes=None,
            backup_count=0,
        )
    latest = max(files, key=lambda p: p.stat().st_mtime)
    stat = latest.stat()
    return BackupInfo(
        backup_dir=str(backup_dir),
        backup_dir_exists=True,
        latest_backup_name=latest.name,
        latest_backup_mtime=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        latest_backup_size_bytes=stat.st_size,
        backup_count=len(files),
    )


def _collect_storage(data_dir_str: str) -> StorageInfo:
    data_dir = Path(data_dir_str)
    measured_at = _first_existing_path(data_dir)
    try:
        usage = shutil.disk_usage(str(measured_at))
    except OSError:
        return StorageInfo(
            data_dir=str(data_dir),
            measured_at_path=str(measured_at),
            total_bytes=None,
            used_bytes=None,
            free_bytes=None,
            free_percent=None,
        )
    free_percent = round((usage.free / usage.total) * 100.0, 1) if usage.total > 0 else None
    return StorageInfo(
        data_dir=str(data_dir),
        measured_at_path=str(measured_at),
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
        free_percent=free_percent,
    )


def _walk_files(root: Path) -> tuple[int, int, list[str]]:
    """Liefert ``(file_count, total_bytes, walk_warnings)``.

    Folgt KEINEN Symlinks (verhindert Endlosschleifen und überraschende
    Größen). Einzel-Errors (z. B. ``PermissionError`` auf einer Datei)
    werden gesammelt und durchgereicht; die Iteration läuft weiter.
    """
    if not root.is_dir():
        return 0, 0, []
    file_count = 0
    total_bytes = 0
    walk_warnings: list[str] = []
    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            it = os.scandir(current)
        except OSError as exc:
            walk_warnings.append(f"Verzeichnis {current} nicht lesbar: {exc}.")
            continue
        with it:
            for entry in it:
                try:
                    if entry.is_symlink():
                        # Nicht folgen.
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        file_count += 1
                        try:
                            total_bytes += entry.stat(follow_symlinks=False).st_size
                        except OSError as exc:
                            walk_warnings.append(f"Größe von {entry.path} nicht lesbar: {exc}.")
                except OSError as exc:
                    walk_warnings.append(f"Eintrag {entry.path} nicht lesbar: {exc}.")
    return file_count, total_bytes, walk_warnings


def _normalize_member_name(name: str) -> str:
    """Vereinheitlicht Tar-Mitgliederpfade — Backslashes, ``./``-Präfix,
    führende Slashes — damit Substring-Tests robust greifen."""
    n = name.replace("\\", "/").lstrip("/")
    while n.startswith("./"):
        n = n[2:]
    return n


def _inspect_backup_contents(
    backup_path: Path,
) -> tuple[bool | None, bool | None, str | None]:
    """Prüft ein tar.gz-Archiv, ob es ``data/ref4ep.db`` und einen
    ``data/storage``-Eintrag enthält.

    Liest die Mitgliederliste sequentiell (ohne komplette Extraktion)
    und bricht ab, sobald beide gefunden wurden.

    Liefert ``(contains_database, contains_storage, error_message)``.
    Bei Lesefehler ist die Rückgabe ``(None, None, msg)``.
    """
    try:
        with tarfile.open(str(backup_path), mode="r:gz") as tf:
            db_found = False
            storage_found = False
            for member in tf:
                name = _normalize_member_name(member.name)
                if not db_found and (
                    "data/ref4ep.db" in name or name.endswith("/ref4ep.db") or name == "ref4ep.db"
                ):
                    db_found = True
                if not storage_found and "data/storage" in name:
                    storage_found = True
                if db_found and storage_found:
                    break
            return db_found, storage_found, None
    except (OSError, tarfile.TarError, EOFError) as exc:
        return (
            None,
            None,
            f"Backup-Archiv konnte nicht gelesen werden: {exc}.",
        )


def _collect_uploads(
    storage_dir_str: str, backups: BackupInfo
) -> tuple[UploadStorageInfo, list[str]]:
    storage_dir = Path(storage_dir_str)
    data_dir = storage_dir.parent
    extra_warnings: list[str] = []

    storage_exists = storage_dir.is_dir()
    if storage_exists:
        s_count, s_bytes, s_walk = _walk_files(storage_dir)
        extra_warnings.extend(s_walk)
    else:
        s_count, s_bytes = 0, 0

    if data_dir.is_dir():
        d_count, d_bytes, d_walk = _walk_files(data_dir)
        extra_warnings.extend(d_walk)
    else:
        d_count, d_bytes = 0, 0

    documents_dir = storage_dir / "documents"
    if documents_dir.is_dir():
        doc_count, doc_bytes, doc_walk = _walk_files(documents_dir)
        extra_warnings.extend(doc_walk)
        document_storage_file_count: int | None = doc_count
        document_storage_total_bytes: int | None = doc_bytes
    else:
        document_storage_file_count = None
        document_storage_total_bytes = None

    backup_contains_database: bool | None = None
    backup_contains_storage: bool | None = None
    backup_checked_name: str | None = None
    if backups.backup_dir_exists and backups.latest_backup_name:
        backup_path = Path(backups.backup_dir) / backups.latest_backup_name
        backup_checked_name = backups.latest_backup_name
        contains_db, contains_storage, err = _inspect_backup_contents(backup_path)
        backup_contains_database = contains_db
        backup_contains_storage = contains_storage
        if err:
            extra_warnings.append(err)

    return (
        UploadStorageInfo(
            storage_dir=str(storage_dir),
            storage_dir_exists=storage_exists,
            storage_total_bytes=s_bytes,
            storage_file_count=s_count,
            data_dir=str(data_dir),
            data_dir_total_bytes=d_bytes,
            data_file_count=d_count,
            document_storage_file_count=document_storage_file_count,
            document_storage_total_bytes=document_storage_total_bytes,
            backup_contains_storage=backup_contains_storage,
            backup_contains_database=backup_contains_database,
            backup_checked_name=backup_checked_name,
        ),
        extra_warnings,
    )


def _collect_counts(session: Session, today: datetime | None = None) -> CountsInfo:
    today_date = (today or datetime.now(tz=UTC)).date()
    persons = session.scalar(select(func.count(Person.id)).where(Person.is_deleted.is_(False)))
    active_persons = session.scalar(
        select(func.count(Person.id)).where(
            Person.is_deleted.is_(False), Person.is_active.is_(True)
        )
    )
    partners = session.scalar(select(func.count(Partner.id)).where(Partner.is_deleted.is_(False)))
    documents = session.scalar(
        select(func.count(Document.id)).where(Document.is_deleted.is_(False))
    )
    # ``Meeting`` und ``MeetingAction`` haben keinen Soft-Delete — Hard-Delete
    # ist möglich, wir zählen also einfach den Tabellenstand.
    meetings = session.scalar(select(func.count(Meeting.id)))
    open_actions = session.scalar(
        select(func.count(MeetingAction.id)).where(
            MeetingAction.status.in_(("open", "in_progress"))
        )
    )
    overdue_actions = session.scalar(
        select(func.count(MeetingAction.id)).where(
            MeetingAction.status.in_(("open", "in_progress")),
            MeetingAction.due_date.is_not(None),
            MeetingAction.due_date < today_date,
        )
    )
    return CountsInfo(
        persons=int(persons or 0),
        active_persons=int(active_persons or 0),
        partners=int(partners or 0),
        documents=int(documents or 0),
        meetings=int(meetings or 0),
        open_actions=int(open_actions or 0),
        overdue_actions=int(overdue_actions or 0),
    )


def _derive_health(
    database: DatabaseInfo,
    backups: BackupInfo,
    storage: StorageInfo,
    uploads: UploadStorageInfo,
    *,
    now: datetime,
    extra_warnings: list[str] | None = None,
) -> HealthInfo:
    warnings: list[str] = []
    has_error = False

    if database.alembic_revision is None:
        warnings.append("Alembic-Version nicht gefunden.")
    if database.db_path is not None and not database.db_exists:
        warnings.append("Datenbank-Datei nicht gefunden.")

    if not backups.backup_dir_exists:
        warnings.append(f"Backup-Verzeichnis nicht gefunden: {backups.backup_dir}.")
    elif backups.backup_count == 0:
        warnings.append("Keine Backups im Backup-Verzeichnis gefunden.")
    elif backups.latest_backup_mtime is not None:
        age = now - backups.latest_backup_mtime
        if age > timedelta(hours=BACKUP_STALE_AFTER_HOURS):
            hours = int(age.total_seconds() // 3600)
            warnings.append(
                f"Letztes Backup älter als {BACKUP_STALE_AFTER_HOURS} Stunden (Alter: {hours} h)."
            )

    if storage.free_percent is not None:
        if storage.free_percent < DISK_FREE_ERROR_PERCENT:
            warnings.append(f"Freier Speicherplatz kritisch niedrig ({storage.free_percent} %).")
            has_error = True
        elif storage.free_percent < DISK_FREE_WARNING_PERCENT:
            warnings.append(f"Freier Speicherplatz niedrig ({storage.free_percent} %).")
    elif storage.total_bytes is None:
        warnings.append("Speicherplatz konnte nicht ermittelt werden.")

    # Upload-Speicher (Block 0021) — Trennung Metadaten / Dateien.
    if not uploads.storage_dir_exists:
        warnings.append("Upload-Speicherverzeichnis nicht gefunden.")
    elif uploads.storage_file_count == 0:
        # Bewusst nur warning, kein error: ein neues System ist legitim leer.
        warnings.append("Keine Upload-Dateien im Storage gefunden.")

    # Backup-Inhaltsprüfung — nur wenn überhaupt ein Archiv geprüft wurde.
    if uploads.backup_checked_name is not None:
        if uploads.backup_contains_database is False:
            warnings.append("Neuestes Backup enthält keine Datenbankdatei.")
        if uploads.backup_contains_storage is False:
            warnings.append("Neuestes Backup enthält keinen Upload-Speicher.")

    if extra_warnings:
        warnings.extend(extra_warnings)

    if has_error:
        status_label = "error"
    elif warnings:
        status_label = "warning"
    else:
        status_label = "ok"
    return HealthInfo(status=status_label, warnings=warnings)


# --------------------------------------------------------------------------- #
# Service                                                                     #
# --------------------------------------------------------------------------- #


class SystemStatusService:
    """Orchestriert die Einzel-Bausteine zu einem Gesamt-Snapshot.

    Aufruf ist read-only — keine Schreibvorgänge, kein Audit-Eintrag.
    Die Berechtigung wird vom Routen-Layer (Admin-only) erzwungen.
    """

    def __init__(
        self,
        session: Session,
        engine: Engine,
        *,
        database_url: str,
        storage_dir: str,
        backup_dir: str,
        app_name: str = "Ref4EP-Portal",
        app_version: str = "",
    ) -> None:
        self.session = session
        self.engine = engine
        self.database_url = database_url
        self.storage_dir = storage_dir
        self.backup_dir = backup_dir
        self.app_name = app_name
        self.app_version = app_version

    def collect(self, *, now: datetime | None = None) -> SystemStatus:
        current_time = now or datetime.now(tz=UTC)
        database = _collect_database(self.engine, self.database_url)
        backups = _collect_backups(self.backup_dir)
        storage = _collect_storage(self.storage_dir)
        uploads, upload_warnings = _collect_uploads(self.storage_dir, backups)
        counts = _collect_counts(self.session, today=current_time)
        health = _derive_health(
            database,
            backups,
            storage,
            uploads,
            now=current_time,
            extra_warnings=upload_warnings,
        )
        return SystemStatus(
            app=AppInfo(
                name=self.app_name,
                version=self.app_version,
                current_time=current_time,
            ),
            database=database,
            backups=backups,
            storage=storage,
            uploads=uploads,
            counts=counts,
            health=health,
            logs=None,
        )
