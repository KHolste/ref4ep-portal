"""Partnerbezogene Rollen (Block 0043).

Neue Tabelle ``partner_role`` für Person × Partner × Rolle.
Aktuell ist nur ``partner_lead`` (UI-Label „Projektleitung") gültig;
CHECK-Constraint hält den Wertebereich eng. Wirkung auf
Berechtigungen folgt in den Patches 0045/0046.

Revision ID: 0022_partner_roles
Revises: 0021_milestone_document_links
Create Date: 2026-05-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0022_partner_roles"
down_revision: Union[str, None] = "0021_milestone_document_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "partner_role",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("person_id", sa.String(length=36), nullable=False),
        sa.Column("partner_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("created_by_person_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name="fk_partner_role_person",
        ),
        sa.ForeignKeyConstraint(
            ["partner_id"],
            ["partner.id"],
            name="fk_partner_role_partner",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_person_id"],
            ["person.id"],
            name="fk_partner_role_creator",
        ),
        sa.CheckConstraint("role IN ('partner_lead')", name="ck_partner_role_role"),
        sa.UniqueConstraint(
            "person_id", "partner_id", "role", name="uq_partner_role_person_partner_role"
        ),
    )
    op.create_index("ix_partner_role_person", "partner_role", ["person_id"])
    op.create_index("ix_partner_role_partner", "partner_role", ["partner_id"])


def downgrade() -> None:
    op.drop_index("ix_partner_role_partner", table_name="partner_role")
    op.drop_index("ix_partner_role_person", table_name="partner_role")
    op.drop_table("partner_role")
