"""Baseline-Revision für Sprint 0.

Bewusst leer. Sprint 1 fügt die ersten Tabellen
(``partner``, ``person``, ``workpackage``, ``membership``) hinzu.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-02
"""

from __future__ import annotations

from typing import Sequence, Union

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
