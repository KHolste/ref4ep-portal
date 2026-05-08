"""Workpackage-Zeitplan: optionale Datumsfelder (Block 0027).

Zwei neue nullable Date-Spalten am ``workpackage``-Modell für die
manuelle Terminplanung. Hauptpakete werden im Gantt aus den Kindern
aggregiert, deshalb sind beide Felder optional.

Revision ID: 0013_workpackage_schedule
Revises: 0012_document_comments
Create Date: 2026-05-08
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0013_workpackage_schedule"
down_revision: Union[str, None] = "0012_document_comments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workpackage") as batch_op:
        batch_op.add_column(sa.Column("start_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("end_date", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workpackage") as batch_op:
        batch_op.drop_column("end_date")
        batch_op.drop_column("start_date")
