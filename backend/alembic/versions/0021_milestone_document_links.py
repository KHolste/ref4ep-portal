"""Meilenstein-Dokumentverknüpfungen (Block 0039).

Neue Many-to-Many-Tabelle ``milestone_document_link``. Audit-Trail
liegt im bestehenden ``audit_log`` (Aktionen
``milestone.document_link.add`` / ``.remove``); deshalb braucht der
Link-Datensatz selbst keinen ``is_deleted``-Pfad.

Revision ID: 0021_milestone_document_links
Revises: 0020_document_types_science
Create Date: 2026-05-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0021_milestone_document_links"
down_revision: Union[str, None] = "0020_document_types_science"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "milestone_document_link",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("milestone_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_person_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["milestone_id"],
            ["milestone.id"],
            name="fk_milestone_document_link_milestone",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name="fk_milestone_document_link_document",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_person_id"],
            ["person.id"],
            name="fk_milestone_document_link_creator",
        ),
        sa.UniqueConstraint(
            "milestone_id", "document_id", name="uq_milestone_document_link"
        ),
    )
    op.create_index(
        "ix_milestone_document_link_milestone",
        "milestone_document_link",
        ["milestone_id"],
    )
    op.create_index(
        "ix_milestone_document_link_document",
        "milestone_document_link",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_milestone_document_link_document",
        table_name="milestone_document_link",
    )
    op.drop_index(
        "ix_milestone_document_link_milestone",
        table_name="milestone_document_link",
    )
    op.drop_table("milestone_document_link")
