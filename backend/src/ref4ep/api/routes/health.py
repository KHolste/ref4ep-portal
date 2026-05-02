"""Health-Endpoint mit DB-Ping."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ref4ep.api.deps import get_engine

logger = logging.getLogger(__name__)

router = APIRouter()

EngineDep = Annotated[Engine, Depends(get_engine)]


@router.get("/api/health")
def health(request: Request, engine: EngineDep) -> dict[str, str]:
    db_status = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("DB-Ping fehlgeschlagen: %s", exc)
        db_status = "error"

    return {
        "status": "ok",
        "db": db_status,
        "version": request.app.state.version,
    }
