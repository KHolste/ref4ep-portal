"""Dokumentenregister mit Versionierung (Sprint 2).

Legt die Tabellen ``document`` und ``document_version`` mit
Constraints und Indexen an. Sprint 2 enthält **kein**
``released_version_id``-Feld (Release-Workflow folgt erst Sprint 3
per separater Revision).

Revision ID: 0003_documents
Revises: 0002_identity_and_project
Create Date: 2026-05-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_documents"
down_revision: Union[str, None] = "0002_identity_and_project"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workpackage_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("document_type", sa.String(), nullable=False),
        sa.Column("deliverable_code", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("visibility", sa.String(), nullable=False, server_default="workpackage"),
        sa.Column("created_by_person_id", sa.String(length=36), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workpackage_id"], ["workpackage.id"], name="fk_document_workpackage"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_person_id"], ["person.id"], name="fk_document_created_by"
        ),
        sa.UniqueConstraint("workpackage_id", "slug", name="uq_document_wp_slug"),
        sa.CheckConstraint(
            "document_type IN ('deliverable','report','note','other')",
            name="ck_document_document_type",
        ),
        sa.CheckConstraint(
            "status IN ('draft','in_review','released')", name="ck_document_status"
        ),
        sa.CheckConstraint(
            "visibility IN ('workpackage','internal','public')",
            name="ck_document_visibility",
        ),
    )
    op.create_index(
        "ix_document_workpackage_active",
        "document",
        ["workpackage_id", "is_deleted"],
    )

    op.create_table(
        "document_version",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("version_label", sa.String(), nullable=True),
        sa.Column("change_note", sa.String(), nullable=False),
        sa.Column("storage_key", sa.String(), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by_person_id", sa.String(length=36), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["document.id"], name="fk_document_version_document"
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_person_id"], ["person.id"], name="fk_document_version_uploaded_by"
        ),
        sa.UniqueConstraint(
            "document_id", "version_number", name="uq_document_version_number"
        ),
    )
    op.create_index(
        "ix_document_version_doc_uploaded_at",
        "document_version",
        ["document_id", "uploaded_at"],
    )
    op.create_index("ix_document_version_sha256", "document_version", ["sha256"])


def downgrade() -> None:
    op.drop_index("ix_document_version_sha256", table_name="document_version")
    op.drop_index("ix_document_version_doc_uploaded_at", table_name="document_version")
    op.drop_table("document_version")
    op.drop_index("ix_document_workpackage_active", table_name="document")
    op.drop_table("document")
