"""Admin-Systemstatus-Endpoint (Block 0019).

``GET /api/admin/system/status`` — Smoke-Test-Werte für Betreiber.
Ausschließlich Admin-Zugriff; reine Lesesicht (kein Audit-Eintrag,
keine destruktiven Aktionen).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ref4ep.api.config import Settings
from ref4ep.api.deps import get_auth_context, get_engine, get_session, get_settings
from ref4ep.api.schemas.system import (
    AppInfoOut,
    BackupInfoOut,
    CountsInfoOut,
    DatabaseInfoOut,
    HealthInfoOut,
    StorageInfoOut,
    SystemStatusOut,
    UploadStorageInfoOut,
)
from ref4ep.services.permissions import AuthContext, can_admin
from ref4ep.services.system_status_service import SystemStatus, SystemStatusService

router = APIRouter(prefix="/api/admin")

SessionDep = Annotated[Session, Depends(get_session)]
AuthDep = Annotated[AuthContext, Depends(get_auth_context)]
EngineDep = Annotated[Engine, Depends(get_engine)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _to_out(status_obj: SystemStatus) -> SystemStatusOut:
    return SystemStatusOut(
        app=AppInfoOut(
            name=status_obj.app.name,
            version=status_obj.app.version,
            current_time=status_obj.app.current_time,
        ),
        database=DatabaseInfoOut(
            alembic_revision=status_obj.database.alembic_revision,
            db_path=status_obj.database.db_path,
            db_size_bytes=status_obj.database.db_size_bytes,
            db_exists=status_obj.database.db_exists,
        ),
        backups=BackupInfoOut(
            backup_dir=status_obj.backups.backup_dir,
            backup_dir_exists=status_obj.backups.backup_dir_exists,
            latest_backup_name=status_obj.backups.latest_backup_name,
            latest_backup_mtime=status_obj.backups.latest_backup_mtime,
            latest_backup_size_bytes=status_obj.backups.latest_backup_size_bytes,
            backup_count=status_obj.backups.backup_count,
        ),
        storage=StorageInfoOut(
            data_dir=status_obj.storage.data_dir,
            measured_at_path=status_obj.storage.measured_at_path,
            total_bytes=status_obj.storage.total_bytes,
            used_bytes=status_obj.storage.used_bytes,
            free_bytes=status_obj.storage.free_bytes,
            free_percent=status_obj.storage.free_percent,
        ),
        uploads=UploadStorageInfoOut(
            storage_dir=status_obj.uploads.storage_dir,
            storage_dir_exists=status_obj.uploads.storage_dir_exists,
            storage_total_bytes=status_obj.uploads.storage_total_bytes,
            storage_file_count=status_obj.uploads.storage_file_count,
            data_dir=status_obj.uploads.data_dir,
            data_dir_total_bytes=status_obj.uploads.data_dir_total_bytes,
            data_file_count=status_obj.uploads.data_file_count,
            document_storage_file_count=status_obj.uploads.document_storage_file_count,
            document_storage_total_bytes=status_obj.uploads.document_storage_total_bytes,
            backup_contains_storage=status_obj.uploads.backup_contains_storage,
            backup_contains_database=status_obj.uploads.backup_contains_database,
            backup_checked_name=status_obj.uploads.backup_checked_name,
        ),
        counts=CountsInfoOut(
            persons=status_obj.counts.persons,
            active_persons=status_obj.counts.active_persons,
            partners=status_obj.counts.partners,
            documents=status_obj.counts.documents,
            meetings=status_obj.counts.meetings,
            open_actions=status_obj.counts.open_actions,
            overdue_actions=status_obj.counts.overdue_actions,
        ),
        health=HealthInfoOut(
            status=status_obj.health.status,
            warnings=list(status_obj.health.warnings),
        ),
        logs=status_obj.logs,
    )


@router.get("/system/status", response_model=SystemStatusOut)
def get_system_status(
    request: Request,
    auth: AuthDep,
    session: SessionDep,
    engine: EngineDep,
    settings: SettingsDep,
) -> SystemStatusOut:
    if not can_admin(auth.platform_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "Nur Admin."}},
        )
    service = SystemStatusService(
        session,
        engine,
        database_url=settings.database_url,
        storage_dir=settings.storage_dir,
        backup_dir=settings.backup_dir,
        app_name="Ref4EP-Portal",
        app_version=getattr(request.app.state, "version", ""),
    )
    return _to_out(service.collect())
