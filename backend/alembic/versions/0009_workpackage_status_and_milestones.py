"""Arbeitspaket-Cockpit + Meilensteine.

Erweitert ``workpackage`` um Cockpit-Felder (``status``, ``summary``,
``next_steps``, ``open_issues``) und legt eine eigenständige
``milestone``-Tabelle an. Im Ref4EP-Antrag gibt es keine formalen
Deliverables — daher entsteht in diesem Block bewusst **kein**
Deliverable-Modell.

``status`` ist NOT NULL mit Default ``'planned'``; Bestandszeilen
bekommen den Default beim Migrationslauf. ``summary``,
``next_steps`` und ``open_issues`` sind freie Texte, optional.

Der ``milestone.workpackage_id``-FK ist bewusst nullable: MS4
(„Projektende") wird als Gesamtprojekt-Meilenstein geführt und
hängt an keinem konkreten WP.

Revision ID: 0009_workpackage_status_and_milestones
Revises: 0008_partner_organization_fields
Create Date: 2026-05-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_wp_ms"
down_revision: Union[str, None] = "0008_partner_organization_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


WP_STATUS_VALUES = ("planned", "in_progress", "waiting_for_input", "critical", "completed")
MS_STATUS_VALUES = ("planned", "achieved", "postponed", "at_risk", "cancelled")


def upgrade() -> None:
    with op.batch_alter_table("workpackage") as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(),
                nullable=False,
                server_default="planned",
            )
        )
        batch_op.add_column(sa.Column("summary", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("next_steps", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("open_issues", sa.String(), nullable=True))
        batch_op.create_check_constraint(
            "ck_workpackage_status",
            "status IN ('planned','in_progress','waiting_for_input','critical','completed')",
        )

    op.create_table(
        "milestone",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(), nullable=False, unique=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("workpackage_id", sa.String(length=36), nullable=True),
        sa.Column("planned_date", sa.Date(), nullable=False),
        sa.Column("actual_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="planned",
        ),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workpackage_id"], ["workpackage.id"], name="fk_milestone_workpackage"
        ),
        sa.CheckConstraint(
            "status IN ('planned','achieved','postponed','at_risk','cancelled')",
            name="ck_milestone_status",
        ),
    )
    op.create_index("ix_milestone_workpackage", "milestone", ["workpackage_id"])
    op.create_index("ix_milestone_planned_date", "milestone", ["planned_date"])


def downgrade() -> None:
    op.drop_index("ix_milestone_planned_date", table_name="milestone")
    op.drop_index("ix_milestone_workpackage", table_name="milestone")
    op.drop_table("milestone")
    with op.batch_alter_table("workpackage") as batch_op:
        batch_op.drop_constraint("ck_workpackage_status", type_="check")
        batch_op.drop_column("open_issues")
        batch_op.drop_column("next_steps")
        batch_op.drop_column("summary")
        batch_op.drop_column("status")
