"""Projektbibliothek (Block 0035).

Zwei kleine Erweiterungen am ``document``-Schema:

1. ``workpackage_id`` wird nullable. Damit können Admins
   übergreifende Projektunterlagen anlegen, die keinem konkreten
   Arbeitspaket zugeordnet sind.
2. Neues nullable Feld ``library_section`` markiert, in welcher Kachel
   der Projektbibliothek das Dokument auftaucht. Erlaubt:
   ``project``, ``milestone``, ``literature``, ``presentation``,
   ``thesis``. Bestandsdokumente bleiben mit NULL bestehen und
   erscheinen weiter über die ``Arbeitspaket-Dokumente``-Kachel,
   solange sie ein ``workpackage_id`` haben.

Berechtigungen ändern sich nicht durch das Schema — der
PermissionService prüft bei NULL-``workpackage_id`` nur noch
Visibility und Admin-Status.

Revision ID: 0018_project_library
Revises: 0017_test_campaign_photo_thumbnails
Create Date: 2026-05-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0018_project_library"
down_revision: Union[str, None] = "0017_test_campaign_photo_thumbnails"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LIBRARY_CHECK = (
    "library_section IS NULL OR "
    "library_section IN ('project','milestone','literature','presentation','thesis')"
)


def upgrade() -> None:
    with op.batch_alter_table("document") as batch:
        batch.alter_column("workpackage_id", existing_type=sa.String(length=36), nullable=True)
        batch.add_column(sa.Column("library_section", sa.String(), nullable=True))
        batch.create_check_constraint("ck_document_library_section", _LIBRARY_CHECK)


def downgrade() -> None:
    # Entwürfe ohne WP-Bezug müssten vor dem Downgrade gelöscht oder
    # einem WP zugewiesen werden — sonst scheitert der NOT-NULL-Switch
    # auf vorhandenen Daten. In der Server-DB existieren solche Zeilen
    # erst mit dem zugehörigen Frontend-Patch.
    with op.batch_alter_table("document") as batch:
        batch.drop_constraint("ck_document_library_section", type_="check")
        batch.drop_column("library_section")
        batch.alter_column("workpackage_id", existing_type=sa.String(length=36), nullable=False)
