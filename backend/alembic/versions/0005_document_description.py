"""Optionale Dokument-Beschreibung (Praxistest-Korrekturrunde).

Ergänzt ``document.description`` als nullable Text-Spalte. Erlaubt
eine freie Beschreibung getrennt vom Dokumentcode/Deliverable-Code.

Revision ID: 0005_document_description
Revises: 0004_audit_and_release
Create Date: 2026-05-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_document_description"
down_revision: Union[str, None] = "0004_audit_and_release"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("document") as batch_op:
        batch_op.add_column(sa.Column("description", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("document") as batch_op:
        batch_op.drop_column("description")
