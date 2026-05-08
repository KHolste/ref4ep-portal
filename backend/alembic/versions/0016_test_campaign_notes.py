"""Kampagnennotizen für Testkampagnen (Block 0029).

Niedrigschwellige Arbeitsnotizen / Brainstorming-Notizen zu einer
Testkampagne. Bewusst KEIN Laborbuch: keine Versionierung, kein
Review-/Release-Lifecycle, kein Titel — nur ein Markdown-Body, Autor
und Soft-Delete.

Eigenständige Tabelle, keine Änderungen an bestehenden Modellen.

Revision ID: 0016_test_campaign_notes
Revises: 0015_test_campaign_photos
Create Date: 2026-05-08
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0016_test_campaign_notes"
down_revision: Union[str, None] = "0015_test_campaign_photos"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "test_campaign_note",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("author_person_id", sa.String(length=36), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["test_campaign.id"],
            name="fk_test_campaign_note_campaign",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_person_id"],
            ["person.id"],
            name="fk_test_campaign_note_author",
        ),
    )
    op.create_index(
        "ix_test_campaign_note_campaign",
        "test_campaign_note",
        ["campaign_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_test_campaign_note_campaign", table_name="test_campaign_note")
    op.drop_table("test_campaign_note")
