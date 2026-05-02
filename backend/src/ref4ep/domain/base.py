"""Gemeinsamer SQLAlchemy-DeclarativeBase.

In Sprint 0 ist ``Base.metadata`` leer. Sprint 1 ergänzt die ersten
Modelle (``partner``, ``person``, ``workpackage``, ``membership``).
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
