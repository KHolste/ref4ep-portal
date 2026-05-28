"""Fachliche Themenfelder in der Projektbibliothek (Block 0050).

Erweitert ``ck_document_library_section`` um sieben fachliche
Themenfelder der Projektbibliothek:

- ``technical_documentation`` (Technische Dokumentation)
- ``measurement_test_campaigns`` (Mess- und Testkampagnen)
- ``round_robin`` (Ringvergleiche)
- ``meetings_minutes`` (Meetings & Protokolle)
- ``standards_procedures`` (Standards & Verfahren)
- ``templates_forms`` (Vorlagen & Formulare)
- ``software_data_formats`` (Software & Datenformate)

Die bisherigen Slugs (``project``, ``milestone``, ``literature``,
``presentation``, ``thesis``) bleiben gültig. Bestehende Dokumente
werden nicht angerührt — Downgrade entfernt die neuen Slugs aus dem
Constraint und scheitert bei vorhandenen Dokumenten, die einen der
neuen Werte nutzen. Lieber explizit fehlschlagen als fremde Daten
verstummen lassen — dasselbe Muster wie in Migration 0020.

Revision ID: 0023_library_section_themes
Revises: 0022_partner_roles
Create Date: 2026-05-28
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0023_library_section_themes"
down_revision: Union[str, None] = "0022_partner_roles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD = (
    "library_section IS NULL OR "
    "library_section IN ('project','milestone','literature','presentation','thesis')"
)
_NEW = (
    "library_section IS NULL OR "
    "library_section IN ("
    "'project','milestone','literature','presentation','thesis',"
    "'technical_documentation','measurement_test_campaigns','round_robin',"
    "'meetings_minutes','standards_procedures','templates_forms',"
    "'software_data_formats'"
    ")"
)


def upgrade() -> None:
    with op.batch_alter_table("document") as batch:
        batch.drop_constraint("ck_document_library_section", type_="check")
        batch.create_check_constraint("ck_document_library_section", _NEW)


def downgrade() -> None:
    with op.batch_alter_table("document") as batch:
        batch.drop_constraint("ck_document_library_section", type_="check")
        batch.create_check_constraint("ck_document_library_section", _OLD)
