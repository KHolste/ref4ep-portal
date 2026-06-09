"""Kampagnen-Anhänge — beliebige Dateien (Block 0044).

Eine neue Tabelle, keine Änderungen an bestehenden Modellen.
Eigenständiges Anhang-Modell — bewusst nicht als ``Document``
(formale, versionierte Unterlage mit Review-/Release-Lifecycle) und
nicht als ``TestCampaignPhoto`` (nur PNG/JPEG). Anhänge sind beliebige
Beilagen (PDF, CSV, Office, Bilder) mit Beschreibung + Soft-Delete.

Storage-Schicht und MIME-Validierung werden wiederverwendet; das
Storage-Key-Schema ist ``attachments/{campaign_id}/{attachment_id}.bin``
(Thumbnail: ``…/{attachment_id}.thumb.bin``) — parallel zu
``photos/{campaign_id}/{photo_id}.bin``.

Revision ID: 0024_test_campaign_attachments
Revises: 0023_library_section_themes
Create Date: 2026-06-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0024_test_campaign_attachments"
down_revision: Union[str, None] = "0023_library_section_themes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "test_campaign_attachment",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("uploaded_by_person_id", sa.String(length=36), nullable=False),
        sa.Column("storage_key", sa.String(), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("thumbnail_storage_key", sa.String(), nullable=True),
        sa.Column("thumbnail_mime_type", sa.String(), nullable=True),
        sa.Column("thumbnail_size_bytes", sa.Integer(), nullable=True),
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
            name="fk_test_campaign_attachment_campaign",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_person_id"],
            ["person.id"],
            name="fk_test_campaign_attachment_uploader",
        ),
    )
    op.create_index(
        "ix_test_campaign_attachment_campaign",
        "test_campaign_attachment",
        ["campaign_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_test_campaign_attachment_campaign", table_name="test_campaign_attachment"
    )
    op.drop_table("test_campaign_attachment")
