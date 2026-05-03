"""Erweiterte Partner-Felder (Adresse, Kontakt, Verwaltung).

Ergänzt der Tabelle ``partner`` Spalten für allgemeine Kontakt-
informationen, Postanschrift, primären Projektkontakt sowie
Verwaltungsfelder (``is_active``, ``internal_note``).

``is_deleted`` (Sprint 1) bleibt unverändert für Soft-Delete.
``is_active`` ist davon getrennt: bezeichnet die fachliche
Aktivität des Partners im Projekt.

Revision ID: 0006_partner_extended_fields
Revises: 0005_document_description
Create Date: 2026-05-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_partner_extended_fields"
down_revision: Union[str, None] = "0005_document_description"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("partner") as batch_op:
        batch_op.add_column(sa.Column("general_email", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("address_line", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("postal_code", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("city", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("address_country", sa.String(length=2), nullable=True))
        batch_op.add_column(
            sa.Column("primary_contact_name", sa.String(), nullable=True)
        )
        batch_op.add_column(sa.Column("contact_email", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("contact_phone", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("project_role_note", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch_op.add_column(sa.Column("internal_note", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("partner") as batch_op:
        for col in (
            "internal_note",
            "is_active",
            "project_role_note",
            "contact_phone",
            "contact_email",
            "primary_contact_name",
            "address_country",
            "city",
            "postal_code",
            "address_line",
            "general_email",
        ):
            batch_op.drop_column(col)
