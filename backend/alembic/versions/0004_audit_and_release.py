"""Audit-Log und Freigabe-Verweis (Sprint 3).

- Legt die Tabelle ``audit_log`` an.
- Ergänzt ``document.released_version_id`` als nullable CHAR(36)
  mit echter Foreign-Key-Constraint
  ``fk_document_released_version`` auf ``document_version.id``.
  Wegen des zyklischen FK (document ↔ document_version) wird im
  SQLAlchemy-Modell ``use_alter=True`` verwendet; die Migration
  selbst kann den FK direkt mit ADD COLUMN setzen, da bei der
  Migration alle Datenwerte initial NULL sind und keine
  Bestandsdaten gefüllt werden.

Revision ID: 0004_audit_and_release
Revises: 0003_documents
Create Date: 2026-05-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_audit_and_release"
down_revision: Union[str, None] = "0003_documents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("actor_person_id", sa.String(length=36), nullable=True),
        sa.Column("actor_label", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("details", sa.String(), nullable=True),
        sa.Column("client_ip", sa.String(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_person_id"], ["person.id"], name="fk_audit_log_actor"
        ),
    )
    op.create_index(
        "ix_audit_log_entity",
        "audit_log",
        ["entity_type", "entity_id", "created_at"],
    )
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])

    with op.batch_alter_table("document") as batch_op:
        batch_op.add_column(
            sa.Column(
                "released_version_id",
                sa.String(length=36),
                sa.ForeignKey(
                    "document_version.id",
                    name="fk_document_released_version",
                    use_alter=True,
                ),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("document") as batch_op:
        batch_op.drop_constraint("fk_document_released_version", type_="foreignkey")
        batch_op.drop_column("released_version_id")

    op.drop_index("ix_audit_log_action", table_name="audit_log")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_table("audit_log")
