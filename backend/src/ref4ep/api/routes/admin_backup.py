"""Admin-Backup-Trigger-Endpoint (Block 0033).

``POST /api/admin/backup/start`` — startet den fest definierten
``ref4ep-backup.service`` über eine eng gefasste sudoers-Drop-In-Regel.
Liefert ein strukturiertes Ergebnis; HTTP 200 auch bei
``result='failure'``, weil der API-Aufruf technisch verarbeitet
wurde.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ref4ep.api.config import Settings
from ref4ep.api.deps import (
    get_audit_logger,
    get_auth_context,
    get_settings,
    require_csrf,
)
from ref4ep.api.schemas.admin_backup import BackupTriggerOut
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.backup_trigger_service import BackupTriggerService
from ref4ep.services.permissions import AuthContext, can_admin

router = APIRouter(prefix="/api/admin")

AuthDep = Annotated[AuthContext, Depends(get_auth_context)]
AuditDep = Annotated[AuditLogger, Depends(get_audit_logger)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _build_trigger_service(audit: AuditLogger, settings: Settings) -> BackupTriggerService:
    return BackupTriggerService(
        audit=audit,
        command=settings.backup_trigger_command,
        timeout_seconds=settings.backup_trigger_timeout_seconds,
    )


@router.post(
    "/backup/start",
    response_model=BackupTriggerOut,
    dependencies=[Depends(require_csrf)],
)
def start_backup(
    auth: AuthDep,
    audit: AuditDep,
    settings: SettingsDep,
) -> BackupTriggerOut:
    if not can_admin(auth.platform_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "Nur Admin."}},
        )
    result = _build_trigger_service(audit, settings).start()
    return BackupTriggerOut(
        result=result.result,
        triggered_at=result.triggered_at,
        exit_code=result.exit_code,
        message=result.message,
    )
