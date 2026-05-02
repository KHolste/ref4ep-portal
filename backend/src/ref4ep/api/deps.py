"""FastAPI-Dependencies für Sprint 0.

Liefert Settings (Singleton) und die SQLAlchemy-Engine, die in
``app.state.engine`` abgelegt wurde. Session-Maker, Auth- und
CSRF-Dependencies folgen ab Sprint 1.
"""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.engine import Engine

from ref4ep.api.config import Settings
from ref4ep.api.config import get_settings as _get_settings


def get_settings() -> Settings:
    return _get_settings()


def get_engine(request: Request) -> Engine:
    return request.app.state.engine
