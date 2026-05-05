"""Schemas für den Admin-Systemstatus-Endpoint (Block 0019)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AppInfoOut(BaseModel):
    name: str
    version: str
    current_time: datetime


class DatabaseInfoOut(BaseModel):
    alembic_revision: str | None = None
    db_path: str | None = None
    db_size_bytes: int | None = None
    db_exists: bool


class BackupInfoOut(BaseModel):
    backup_dir: str
    backup_dir_exists: bool
    latest_backup_name: str | None = None
    latest_backup_mtime: datetime | None = None
    latest_backup_size_bytes: int | None = None
    backup_count: int


class StorageInfoOut(BaseModel):
    data_dir: str
    measured_at_path: str
    total_bytes: int | None = None
    used_bytes: int | None = None
    free_bytes: int | None = None
    free_percent: float | None = None


class CountsInfoOut(BaseModel):
    persons: int
    active_persons: int
    partners: int
    documents: int
    meetings: int
    open_actions: int
    overdue_actions: int


class HealthInfoOut(BaseModel):
    status: str  # "ok" | "warning" | "error"
    warnings: list[str] = Field(default_factory=list)


class SystemStatusOut(BaseModel):
    app: AppInfoOut
    database: DatabaseInfoOut
    backups: BackupInfoOut
    storage: StorageInfoOut
    counts: CountsInfoOut
    health: HealthInfoOut
    # logs ist in diesem Block bewusst noch nicht ausgeliefert.
    logs: dict | None = None
