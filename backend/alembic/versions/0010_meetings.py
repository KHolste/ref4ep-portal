"""Meeting- und Protokollregister (Block 0015).

Sechs neue Tabellen, keine Änderungen an bestehenden Modellen:

- ``meeting``                  — Treffen-Stammdaten (Titel, Zeit, Ort,
                                 Format, Kategorie, Status, Zusammen-
                                 fassung). Soft-Cancel über
                                 ``status = 'cancelled'``; kein Hard-
                                 Delete.
- ``meeting_workpackage``      — m:n Verknüpfung Meeting × WP. Ein
                                 Meeting kann 0..n WPs betreffen.
- ``meeting_participant``      — Portal-Teilnehmende (Person). Externe
                                 stehen frei in
                                 ``meeting.extra_participants``.
- ``meeting_decision``         — Beschlüsse, optional WP-bezogen,
                                 optional verantwortliche Person.
- ``meeting_action``           — Aufgaben, optional WP-bezogen,
                                 optional verantwortlich + Frist.
- ``meeting_document_link``    — Verknüpfung auf bestehende Documents
                                 (Agenda, Protokoll, …). Kein eigener
                                 Upload-Pfad.

CHECK-Constraints sichern die String-Enums (format, category, status,
label).

Revision ID: 0010_meetings
Revises: 0009_wp_ms
Create Date: 2026-05-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_meetings"
down_revision: Union[str, None] = "0009_wp_ms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "meeting",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("format", sa.String(), nullable=False, server_default="online"),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=False, server_default="other"),
        sa.Column("status", sa.String(), nullable=False, server_default="planned"),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column("extra_participants", sa.String(), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["person.id"], name="fk_meeting_created_by"),
        sa.CheckConstraint(
            "format IN ('online','in_person','hybrid')",
            name="ck_meeting_format",
        ),
        sa.CheckConstraint(
            "category IN ('consortium','jour_fixe','workpackage','technical',"
            "'review','test_campaign','other')",
            name="ck_meeting_category",
        ),
        sa.CheckConstraint(
            "status IN ('planned','held','minutes_draft','minutes_approved',"
            "'completed','cancelled')",
            name="ck_meeting_status",
        ),
    )
    op.create_index("ix_meeting_starts_at", "meeting", ["starts_at"])
    op.create_index("ix_meeting_status", "meeting", ["status"])

    op.create_table(
        "meeting_workpackage",
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("workpackage_id", sa.String(length=36), nullable=False),
        sa.PrimaryKeyConstraint("meeting_id", "workpackage_id", name="pk_meeting_workpackage"),
        sa.ForeignKeyConstraint(
            ["meeting_id"], ["meeting.id"], name="fk_mw_meeting", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workpackage_id"], ["workpackage.id"], name="fk_mw_workpackage"
        ),
    )
    op.create_index("ix_mw_workpackage", "meeting_workpackage", ["workpackage_id"])

    op.create_table(
        "meeting_participant",
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("person_id", sa.String(length=36), nullable=False),
        sa.PrimaryKeyConstraint("meeting_id", "person_id", name="pk_meeting_participant"),
        sa.ForeignKeyConstraint(
            ["meeting_id"], ["meeting.id"], name="fk_mp_meeting", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], name="fk_mp_person"),
    )

    op.create_table(
        "meeting_decision",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("workpackage_id", sa.String(length=36), nullable=True),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("responsible_person_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["meeting_id"], ["meeting.id"], name="fk_md_meeting", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workpackage_id"], ["workpackage.id"], name="fk_md_workpackage"
        ),
        sa.ForeignKeyConstraint(
            ["responsible_person_id"], ["person.id"], name="fk_md_responsible"
        ),
        sa.CheckConstraint(
            "status IN ('open','valid','replaced','revoked')",
            name="ck_meeting_decision_status",
        ),
    )
    op.create_index("ix_meeting_decision_meeting", "meeting_decision", ["meeting_id"])

    op.create_table(
        "meeting_action",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("workpackage_id", sa.String(length=36), nullable=True),
        sa.Column("responsible_person_id", sa.String(length=36), nullable=True),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["meeting_id"], ["meeting.id"], name="fk_ma_meeting", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workpackage_id"], ["workpackage.id"], name="fk_ma_workpackage"
        ),
        sa.ForeignKeyConstraint(
            ["responsible_person_id"], ["person.id"], name="fk_ma_responsible"
        ),
        sa.CheckConstraint(
            "status IN ('open','in_progress','done','cancelled')",
            name="ck_meeting_action_status",
        ),
    )
    op.create_index("ix_meeting_action_meeting", "meeting_action", ["meeting_id"])

    op.create_table(
        "meeting_document_link",
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("label", sa.String(), nullable=False, server_default="other"),
        sa.PrimaryKeyConstraint("meeting_id", "document_id", name="pk_meeting_document_link"),
        sa.ForeignKeyConstraint(
            ["meeting_id"], ["meeting.id"], name="fk_mdl_meeting", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"], name="fk_mdl_document"),
        sa.CheckConstraint(
            "label IN ('agenda','minutes','presentation','decision_template',"
            "'attachment','other')",
            name="ck_meeting_document_link_label",
        ),
    )
    op.create_index("ix_mdl_document", "meeting_document_link", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_mdl_document", table_name="meeting_document_link")
    op.drop_table("meeting_document_link")
    op.drop_index("ix_meeting_action_meeting", table_name="meeting_action")
    op.drop_table("meeting_action")
    op.drop_index("ix_meeting_decision_meeting", table_name="meeting_decision")
    op.drop_table("meeting_decision")
    op.drop_table("meeting_participant")
    op.drop_index("ix_mw_workpackage", table_name="meeting_workpackage")
    op.drop_table("meeting_workpackage")
    op.drop_index("ix_meeting_status", table_name="meeting")
    op.drop_index("ix_meeting_starts_at", table_name="meeting")
    op.drop_table("meeting")
