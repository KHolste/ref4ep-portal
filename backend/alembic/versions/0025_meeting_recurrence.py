"""Wiederkehrende Termine/Meetings — V1 (Block 0052).

Zwei neue Spalten am ``meeting``-Modell:

- ``recurrence_rule``  (NOT NULL, Default ``none``) — einer von
  none/weekly/biweekly/monthly. Bestandstermine sind damit automatisch
  ``none`` (einmalig) — keine Datenänderung erzwungen.
- ``recurrence_until`` (nullable Date) — Enddatum der Serie.

Keine neue Tabelle, keine Änderung an Bestandsterminen. Die Werte werden
im ``MeetingService`` validiert (kein DB-CHECK, wie bei anderen
app-validierten Feldern). Die Expansion in konkrete Vorkommen erfolgt
ausschließlich lesend im ``CalendarService`` für den abgefragten
Zeitraum — es werden keine Vorkommen materialisiert.

Revision ID: 0025_meeting_recurrence
Revises: 0024_test_campaign_attachments
Create Date: 2026-06-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0025_meeting_recurrence"
down_revision: Union[str, None] = "0024_test_campaign_attachments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("meeting") as batch_op:
        batch_op.add_column(
            sa.Column(
                "recurrence_rule",
                sa.String(),
                nullable=False,
                server_default="none",
            )
        )
        batch_op.add_column(sa.Column("recurrence_until", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("meeting") as batch_op:
        batch_op.drop_column("recurrence_until")
        batch_op.drop_column("recurrence_rule")
