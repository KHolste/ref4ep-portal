"""Identität und Projektstruktur (Sprint 1).

Legt die Tabellen ``partner``, ``person``, ``workpackage``, ``membership``
mit Constraints und Indexen an.

Revision ID: 0002_identity_and_project
Revises: 0001_baseline
Create Date: 2026-05-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_identity_and_project"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "partner",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("short_name", sa.String(), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("website", sa.String(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_partner_name"),
        sa.UniqueConstraint("short_name", name="uq_partner_short_name"),
    )

    op.create_table(
        "person",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("partner_id", sa.String(length=36), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("platform_role", sa.String(), nullable=False, server_default="member"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "must_change_password", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["partner_id"], ["partner.id"], name="fk_person_partner"),
        sa.UniqueConstraint("email", name="uq_person_email"),
        sa.CheckConstraint(
            "platform_role IN ('admin','member')", name="ck_person_platform_role"
        ),
    )

    op.create_table(
        "workpackage",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("parent_workpackage_id", sa.String(length=36), nullable=True),
        sa.Column("lead_partner_id", sa.String(length=36), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_workpackage_id"], ["workpackage.id"], name="fk_workpackage_parent"
        ),
        sa.ForeignKeyConstraint(
            ["lead_partner_id"], ["partner.id"], name="fk_workpackage_lead_partner"
        ),
        sa.UniqueConstraint("code", name="uq_workpackage_code"),
    )
    op.create_index(
        "ix_workpackage_parent",
        "workpackage",
        ["parent_workpackage_id"],
    )

    op.create_table(
        "membership",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("person_id", sa.String(length=36), nullable=False),
        sa.Column("workpackage_id", sa.String(length=36), nullable=False),
        sa.Column("wp_role", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], name="fk_membership_person"),
        sa.ForeignKeyConstraint(
            ["workpackage_id"], ["workpackage.id"], name="fk_membership_workpackage"
        ),
        sa.UniqueConstraint(
            "person_id", "workpackage_id", name="uq_membership_person_workpackage"
        ),
        sa.CheckConstraint(
            "wp_role IN ('wp_lead','wp_member')", name="ck_membership_wp_role"
        ),
    )


def downgrade() -> None:
    op.drop_table("membership")
    op.drop_index("ix_workpackage_parent", table_name="workpackage")
    op.drop_table("workpackage")
    op.drop_table("person")
    op.drop_table("partner")
