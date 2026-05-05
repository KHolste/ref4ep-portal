"""Testkampagnenregister (Block 0022).

Vier neue Tabellen — keine Änderungen an bestehenden Modellen:

- ``test_campaign``                 — Kampagnen-Stammdaten (Code, Titel,
                                      Kategorie, Status, Zeitraum,
                                      Facility, Beschreibungen).
- ``test_campaign_workpackage``     — m:n Verknüpfung Kampagne × WP.
- ``test_campaign_participant``     — Beteiligte Personen mit Rolle/
                                      Notiz; Surrogat-UUID-PK, damit
                                      ``role`` per PATCH änderbar ist.
- ``test_campaign_document_link``   — Verknüpfung auf bestehende
                                      Documents (Messplan, Protokoll, …).
                                      Kein eigener Upload-Pfad.

CHECK-Constraints sichern die String-Enums (category, status, role,
label). ``code`` ist unique.

Revision ID: 0011_test_campaigns
Revises: 0010_meetings
Create Date: 2026-05-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0011_test_campaigns"
down_revision: Union[str, None] = "0010_meetings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "test_campaign",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False, server_default="other"),
        sa.Column("status", sa.String(), nullable=False, server_default="planned"),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("facility", sa.String(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("short_description", sa.String(), nullable=True),
        sa.Column("objective", sa.String(), nullable=True),
        sa.Column("test_matrix", sa.String(), nullable=True),
        sa.Column("expected_measurements", sa.String(), nullable=True),
        sa.Column("boundary_conditions", sa.String(), nullable=True),
        sa.Column("success_criteria", sa.String(), nullable=True),
        sa.Column("risks_or_open_points", sa.String(), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["person.id"], name="fk_test_campaign_created_by"
        ),
        sa.UniqueConstraint("code", name="uq_test_campaign_code"),
        sa.CheckConstraint(
            "category IN ('ring_comparison','reference_measurement','diagnostics_test',"
            "'calibration','facility_characterization','endurance_test',"
            "'acceptance_test','other')",
            name="ck_test_campaign_category",
        ),
        sa.CheckConstraint(
            "status IN ('planned','preparing','running','completed','evaluated',"
            "'cancelled','postponed')",
            name="ck_test_campaign_status",
        ),
    )
    op.create_index("ix_test_campaign_starts_on", "test_campaign", ["starts_on"])
    op.create_index("ix_test_campaign_status", "test_campaign", ["status"])

    op.create_table(
        "test_campaign_workpackage",
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("workpackage_id", sa.String(length=36), nullable=False),
        sa.PrimaryKeyConstraint(
            "campaign_id", "workpackage_id", name="pk_test_campaign_workpackage"
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["test_campaign.id"],
            name="fk_tcw_campaign",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workpackage_id"], ["workpackage.id"], name="fk_tcw_workpackage"
        ),
    )
    op.create_index(
        "ix_tcw_workpackage", "test_campaign_workpackage", ["workpackage_id"]
    )

    op.create_table(
        "test_campaign_participant",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("person_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="other"),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["test_campaign.id"],
            name="fk_tcp_campaign",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], name="fk_tcp_person"),
        sa.UniqueConstraint(
            "campaign_id", "person_id", name="uq_test_campaign_participant_pair"
        ),
        sa.CheckConstraint(
            "role IN ('campaign_lead','facility_responsible','diagnostics',"
            "'data_analysis','operation','safety','observer','other')",
            name="ck_test_campaign_participant_role",
        ),
    )
    op.create_index(
        "ix_tcp_campaign", "test_campaign_participant", ["campaign_id"]
    )

    op.create_table(
        "test_campaign_document_link",
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("label", sa.String(), nullable=False, server_default="other"),
        sa.PrimaryKeyConstraint(
            "campaign_id", "document_id", name="pk_test_campaign_document_link"
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["test_campaign.id"],
            name="fk_tcdl_campaign",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["document.id"], name="fk_tcdl_document"
        ),
        sa.CheckConstraint(
            "label IN ('test_plan','setup_plan','safety_document','raw_data_description',"
            "'protocol','analysis','presentation','attachment','other')",
            name="ck_test_campaign_document_link_label",
        ),
    )
    op.create_index("ix_tcdl_document", "test_campaign_document_link", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_tcdl_document", table_name="test_campaign_document_link")
    op.drop_table("test_campaign_document_link")
    op.drop_index("ix_tcp_campaign", table_name="test_campaign_participant")
    op.drop_table("test_campaign_participant")
    op.drop_index("ix_tcw_workpackage", table_name="test_campaign_workpackage")
    op.drop_table("test_campaign_workpackage")
    op.drop_index("ix_test_campaign_status", table_name="test_campaign")
    op.drop_index("ix_test_campaign_starts_on", table_name="test_campaign")
    op.drop_table("test_campaign")
