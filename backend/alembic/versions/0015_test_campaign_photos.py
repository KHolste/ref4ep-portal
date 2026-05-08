"""Foto-Upload für Testkampagnen (Block 0028).

Eine neue Tabelle, keine Änderungen an bestehenden Modellen.
Eigenständiges Foto-Modell — bewusst nicht als ``Document`` mit
``type=photo``, weil Documents formale, versionierte Unterlagen mit
Review-/Release-Lifecycle sind. Photos sind informelle Aufnahmen
zu Kampagnen mit Caption + Soft-Delete.

Storage-Schicht und MIME-Validierung werden wiederverwendet; das
Storage-Key-Schema ist ``photos/{campaign_id}/{photo_id}.bin`` —
parallel zu ``documents/{document_id}/{version_id}.bin``.

Revision ID: 0015_test_campaign_photos
Revises: 0014_seed_workpackage_schedule
Create Date: 2026-05-08
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0015_test_campaign_photos"
down_revision: Union[str, None] = "0014_seed_workpackage_schedule"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "test_campaign_photo",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("uploaded_by_person_id", sa.String(length=36), nullable=False),
        sa.Column("storage_key", sa.String(), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("caption", sa.String(), nullable=True),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=True),
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
            name="fk_test_campaign_photo_campaign",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_person_id"],
            ["person.id"],
            name="fk_test_campaign_photo_uploader",
        ),
    )
    op.create_index(
        "ix_test_campaign_photo_campaign",
        "test_campaign_photo",
        ["campaign_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_test_campaign_photo_campaign", table_name="test_campaign_photo")
    op.drop_table("test_campaign_photo")
