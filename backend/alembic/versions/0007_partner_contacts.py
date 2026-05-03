"""Partnerkontakte einführen, ``general_email`` entfernen.

Aufräumen der Partner-Stammdaten: Die zentrale Partner-E-Mail
fällt weg — Kontakt läuft im Konsortium über konkrete
Projektpersonen. Stattdessen bekommt jeder Partner eine eigene
``partner_contact``-Tabelle mit beliebig vielen Kontaktpersonen
(Name, Funktion, Sichtbarkeit, Aktivitäts-Flag, Audit-Felder).

SQLite kennt kein natives ``DROP COLUMN`` — wir nutzen den
``batch_alter_table``-Weg von Alembic, der die Tabelle mit
geänderter Definition neu schreibt.

Revision ID: 0007_partner_contacts
Revises: 0006_partner_extended_fields
Create Date: 2026-05-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_partner_contacts"
down_revision: Union[str, None] = "0006_partner_extended_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) general_email entfernen — über batch_alter_table SQLite-kompatibel.
    with op.batch_alter_table("partner") as batch_op:
        batch_op.drop_column("general_email")

    # 2) partner_contact-Tabelle anlegen.
    op.create_table(
        "partner_contact",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("partner_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("title_or_degree", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("function", sa.String(), nullable=True),
        sa.Column("organization_unit", sa.String(), nullable=True),
        sa.Column("workpackage_notes", sa.String(), nullable=True),
        sa.Column(
            "is_primary_contact",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "is_project_lead",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("visibility", sa.String(), nullable=False, server_default="internal"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("internal_note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["partner_id"], ["partner.id"], name="fk_partner_contact_partner"
        ),
        sa.CheckConstraint(
            "visibility IN ('internal','public')",
            name="ck_partner_contact_visibility",
        ),
    )
    op.create_index(
        "ix_partner_contact_partner_active",
        "partner_contact",
        ["partner_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_partner_contact_partner_active", table_name="partner_contact")
    op.drop_table("partner_contact")
    with op.batch_alter_table("partner") as batch_op:
        batch_op.add_column(sa.Column("general_email", sa.String(), nullable=True))
