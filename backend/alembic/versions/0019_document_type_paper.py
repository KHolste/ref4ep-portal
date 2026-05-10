"""Dokumenttyp ``paper`` ergänzen (Block 0035-Folgepatch).

Erweitert den CHECK-Constraint ``ck_document_document_type`` um den
neuen Typ ``paper`` (für die Bibliotheks-Kachel „Literatur &
Veröffentlichungen"). Bestehende Daten werden nicht angerührt.

Revision ID: 0019_document_type_paper
Revises: 0018_project_library
Create Date: 2026-05-10
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0019_document_type_paper"
down_revision: Union[str, None] = "0018_project_library"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD = "document_type IN ('deliverable','report','note','other')"
_NEW = "document_type IN ('deliverable','report','note','paper','other')"


def upgrade() -> None:
    with op.batch_alter_table("document") as batch:
        batch.drop_constraint("ck_document_document_type", type_="check")
        batch.create_check_constraint("ck_document_document_type", _NEW)


def downgrade() -> None:
    with op.batch_alter_table("document") as batch:
        batch.drop_constraint("ck_document_document_type", type_="check")
        batch.create_check_constraint("ck_document_document_type", _OLD)
