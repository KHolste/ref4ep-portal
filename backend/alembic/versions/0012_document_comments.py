"""Dokumentkommentare auf Versionsebene (Block 0024).

Eine neue Tabelle, keine Änderungen an bestehenden Modellen:

- ``document_comment`` — Review-Kommentare pro Dokumentversion.
  Lebenszyklus ``open`` → ``submitted``: nur Autor sieht und
  editiert ``open``; bei ``submit`` wird ``submitted_at`` gesetzt
  und der Eintrag wird unveränderlich für alle anderen Sichten.
  Admin kann via Soft-Delete (``is_deleted=True``) ausnahmsweise
  entfernen — kein Hard-Delete (Konsortium-Prinzip).

CHECK-Constraint sichert die zwei zulässigen Status. Indices auf
``document_version_id`` (primäre Lese-Query) und
``author_person_id`` (globale „meine Kommentare"-Sicht).

Revision ID: 0012_document_comments
Revises: 0011_test_campaigns
Create Date: 2026-05-08
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0012_document_comments"
down_revision: Union[str, None] = "0011_test_campaigns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_comment",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_version_id", sa.String(length=36), nullable=False),
        sa.Column("author_person_id", sa.String(length=36), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_version.id"],
            name="fk_document_comment_version",
        ),
        sa.ForeignKeyConstraint(
            ["author_person_id"],
            ["person.id"],
            name="fk_document_comment_author",
        ),
        sa.CheckConstraint(
            "status IN ('open','submitted')",
            name="ck_document_comment_status",
        ),
    )
    op.create_index(
        "ix_document_comment_version",
        "document_comment",
        ["document_version_id"],
    )
    op.create_index(
        "ix_document_comment_author",
        "document_comment",
        ["author_person_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_comment_author", table_name="document_comment")
    op.drop_index("ix_document_comment_version", table_name="document_comment")
    op.drop_table("document_comment")
