"""Schema für den manuellen Admin-Backup-Trigger (Block 0033)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class BackupTriggerOut(BaseModel):
    result: Literal["success", "failure"]
    triggered_at: datetime
    exit_code: int
    message: str


__all__ = ["BackupTriggerOut"]
