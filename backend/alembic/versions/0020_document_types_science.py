"""Wissenschaftliche Dokumenttypen ergänzen (Block 0035-Folgepatch 2).

Erweitert ``ck_document_document_type`` um:
``thesis`` (Abschlussarbeit), ``presentation`` (Präsentation),
``protocol`` (Protokoll), ``specification`` (Spezifikation),
``template`` (Vorlage), ``dataset`` (Datensatz). ``paper`` und die
ursprünglichen Typen bleiben wie nach Migration 0019.

Bestehende Daten werden nicht angerührt. Downgrade entfernt die neuen
Typen aus dem Constraint und scheitert bei vorhandenen Dokumenten,
die einen der neuen Werte nutzen — das ist gewollt: lieber explizit
fehlschlagen als fremde Daten verstummen lassen.

Revision ID: 0020_document_types_science
Revises: 0019_document_type_paper
Create Date: 2026-05-10
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0020_document_types_science"
down_revision: Union[str, None] = "0019_document_type_paper"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD = "document_type IN ('deliverable','report','note','paper','other')"
_NEW = (
    "document_type IN ("
    "'deliverable','report','note','paper','thesis','presentation',"
    "'protocol','specification','template','dataset','other'"
    ")"
)


def upgrade() -> None:
    with op.batch_alter_table("document") as batch:
        batch.drop_constraint("ck_document_document_type", type_="check")
        batch.create_check_constraint("ck_document_document_type", _NEW)


def downgrade() -> None:
    with op.batch_alter_table("document") as batch:
        batch.drop_constraint("ck_document_document_type", type_="check")
        batch.create_check_constraint("ck_document_document_type", _OLD)
