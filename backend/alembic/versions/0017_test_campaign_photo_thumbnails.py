"""Foto-Thumbnails für Testkampagnen (Block 0032).

Drei nullable Felder an ``test_campaign_photo``:
- ``thumbnail_storage_key``: Pfad im Storage zum Thumbnail-Artefakt.
- ``thumbnail_mime_type``: ``image/jpeg`` oder ``image/png``.
- ``thumbnail_size_bytes``: Grösse des Thumbnail-Bytes.

Bewusst kein ``thumbnail_sha256`` — Thumbnail ist abgeleitet, nicht
auditrelevant; bei Bedarf neu erzeugbar.

Bestandsfotos haben die Felder ``NULL``; die API fällt für diese Fotos
auf das Originalbild zurück.

Revision ID: 0017_test_campaign_photo_thumbnails
Revises: 0016_test_campaign_notes
Create Date: 2026-05-08
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0017_test_campaign_photo_thumbnails"
down_revision: Union[str, None] = "0016_test_campaign_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Alembic legt ``alembic_version.version_num`` standardmäßig als
    # ``VARCHAR(32)`` an. Diese Revision-ID
    # ``0017_test_campaign_photo_thumbnails`` ist 35 Zeichen lang —
    # PostgreSQL erzwingt VARCHAR-Längen hart und scheitert beim
    # abschließenden ``UPDATE alembic_version`` mit
    # ``StringDataRightTruncation``. Daher: vor jeder anderen Aktion
    # in dieser Migration die Spalte für PostgreSQL aufweiten. SQLite
    # erzwingt VARCHAR-Längen nicht und braucht den ``ALTER`` nicht;
    # das ``ALTER COLUMN ... TYPE`` würde dort ohnehin nicht greifen.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE alembic_version "
            "ALTER COLUMN version_num TYPE VARCHAR(128)"
        )

    with op.batch_alter_table("test_campaign_photo") as batch:
        batch.add_column(sa.Column("thumbnail_storage_key", sa.String(), nullable=True))
        batch.add_column(sa.Column("thumbnail_mime_type", sa.String(), nullable=True))
        batch.add_column(sa.Column("thumbnail_size_bytes", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("test_campaign_photo") as batch:
        batch.drop_column("thumbnail_size_bytes")
        batch.drop_column("thumbnail_mime_type")
        batch.drop_column("thumbnail_storage_key")
