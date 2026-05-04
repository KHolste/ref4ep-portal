"""Partner-Stammdaten in Organisation und bearbeitende Einheit trennen.

Hintergrund: Der Praxistest hat doppelte Pflege gezeigt — eine Person
wurde sowohl als ``primary_contact_*`` am Partner als auch als
``PartnerContact`` geführt. Personenbezogene Felder fliegen daher
aus den Partner-Stammdaten raus; an Person dranhängen geht
ausschließlich über ``partner_contact``.

Diese Migration:

1. Personenbezogene Spalten entfernen (``primary_contact_name``,
   ``contact_email``, ``contact_phone``, ``project_role_note``).
2. Bisherige Adressspalten in Organisationsadresse umbenennen
   (``address_line`` → ``organization_address_line`` usw.) — die
   Werte bleiben erhalten, weil sie inhaltlich genau das waren.
3. Neue Felder für die bearbeitende Einheit anlegen
   (``unit_name`` plus ``unit_address_*``) sowie das Flag
   ``unit_address_same_as_organization`` (Default ``true``, damit
   Bestandszeilen sinnvoll initialisiert sind).

Alle Schritte laufen in einem ``batch_alter_table``-Block — SQLite
schreibt damit die Tabelle einmalig neu, statt für jeden Schritt
ein eigenes ``ALTER TABLE`` zu versuchen (das es nicht beherrscht).

Revision ID: 0008_partner_organization_fields
Revises: 0007_partner_contacts
Create Date: 2026-05-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_partner_organization_fields"
down_revision: Union[str, None] = "0007_partner_contacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Spalten, die mit dieser Migration verschwinden (waren personenbezogen).
PERSON_COLUMNS = (
    "primary_contact_name",
    "contact_email",
    "contact_phone",
    "project_role_note",
)

# Renames: alte Adressspalten beschreiben die Organisationsadresse,
# bekommen darum klarere Namen — Werte bleiben erhalten.
RENAMES = (
    ("address_line", "organization_address_line"),
    ("postal_code", "organization_postal_code"),
    ("city", "organization_city"),
    ("address_country", "organization_country"),
)


def upgrade() -> None:
    with op.batch_alter_table("partner") as batch_op:
        for old_name, new_name in RENAMES:
            batch_op.alter_column(old_name, new_column_name=new_name)
        batch_op.add_column(sa.Column("unit_name", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "unit_address_same_as_organization",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch_op.add_column(sa.Column("unit_address_line", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("unit_postal_code", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("unit_city", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("unit_country", sa.String(length=2), nullable=True))
        for col in PERSON_COLUMNS:
            batch_op.drop_column(col)


def downgrade() -> None:
    with op.batch_alter_table("partner") as batch_op:
        # Personenbezogene Spalten in der ursprünglichen Reihenfolge wieder anlegen.
        for col in PERSON_COLUMNS:
            batch_op.add_column(sa.Column(col, sa.String(), nullable=True))
        # Neue Einheits-Spalten droppen.
        for col in (
            "unit_country",
            "unit_city",
            "unit_postal_code",
            "unit_address_line",
            "unit_address_same_as_organization",
            "unit_name",
        ):
            batch_op.drop_column(col)
        # Renames rückgängig machen.
        for old_name, new_name in RENAMES:
            batch_op.alter_column(new_name, new_column_name=old_name)
