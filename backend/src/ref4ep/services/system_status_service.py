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

import shutil
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
class SystemStatus:
    app: AppInfo
    database: DatabaseInfo
    backups: BackupInfo
    storage: StorageInfo
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
    *,
    now: datetime,
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
        counts = _collect_counts(self.session, today=current_time)
        health = _derive_health(database, backups, storage, now=current_time)
        return SystemStatus(
            app=AppInfo(
                name=self.app_name,
                version=self.app_version,
                current_time=current_time,
            ),
            database=database,
            backups=backups,
            storage=storage,
            counts=counts,
            health=health,
            logs=None,
        )
