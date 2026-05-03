"""SQLAlchemy-Modelle für Identität, Projektstruktur und Dokumente.

Sprint-1-Tabellen:
- partner       — Konsortialpartner
- person        — Konsortiumsangehörige mit Login
- workpackage   — Arbeitspakete (zweistufige Hierarchie)
- membership    — Verknüpfung Person × Workpackage × WP-Rolle

Sprint-2-Tabellen:
- document          — projektbezogener Registereintrag mit WP-Bezug
- document_version  — append-only Versionseinträge mit Storage-Key

UUID-Spalten als CHAR(36) für Dialektneutralität (SQLite + PostgreSQL).
Zeitstempel als ``DateTime(timezone=True)``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ref4ep.domain.base import Base

if TYPE_CHECKING:
    pass


# Plattform- und WP-Rollen als String-Konstanten (Validierung im Service-Layer
# und über CHECK-Constraints; eigener Python-Enum-Typ nicht nötig für Sprint 1).
PLATFORM_ROLES = ("admin", "member")
WP_ROLES = ("wp_lead", "wp_member")

# Dokument-Enums (Sprint 2). status und visibility sind im Schema komplett
# vorgesehen, in Sprint 2 aber konstant 'draft' / 'workpackage'. Release- und
# Sichtbarkeits-Workflows folgen Sprint 3, öffentliche Bibliothek Sprint 4.
DOCUMENT_TYPES = ("deliverable", "report", "note", "other")
DOCUMENT_STATUSES = ("draft", "in_review", "released")
DOCUMENT_VISIBILITIES = ("workpackage", "internal", "public")


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _now_utc() -> datetime:
    return datetime.now(UTC)


class Partner(Base):
    __tablename__ = "partner"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    short_name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    website: Mapped[str | None] = mapped_column(String, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc, onupdate=_now_utc
    )

    persons: Mapped[list[Person]] = relationship(back_populates="partner")
    led_workpackages: Mapped[list[Workpackage]] = relationship(back_populates="lead_partner")


class Person(Base):
    __tablename__ = "person"
    __table_args__ = (
        CheckConstraint("platform_role IN ('admin','member')", name="ck_person_platform_role"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    partner_id: Mapped[str] = mapped_column(String(36), ForeignKey("partner.id"), nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    platform_role: Mapped[str] = mapped_column(String, nullable=False, default="member")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc, onupdate=_now_utc
    )

    partner: Mapped[Partner] = relationship(back_populates="persons")
    memberships: Mapped[list[Membership]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )


class Workpackage(Base):
    __tablename__ = "workpackage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    code: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    parent_workpackage_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workpackage.id"), nullable=True
    )
    lead_partner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("partner.id"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc, onupdate=_now_utc
    )

    parent: Mapped[Workpackage | None] = relationship(
        remote_side="Workpackage.id", back_populates="children"
    )
    children: Mapped[list[Workpackage]] = relationship(back_populates="parent")
    lead_partner: Mapped[Partner] = relationship(back_populates="led_workpackages")
    memberships: Mapped[list[Membership]] = relationship(
        back_populates="workpackage", cascade="all, delete-orphan"
    )


class Membership(Base):
    __tablename__ = "membership"
    __table_args__ = (
        UniqueConstraint("person_id", "workpackage_id", name="uq_membership_person_workpackage"),
        CheckConstraint("wp_role IN ('wp_lead','wp_member')", name="ck_membership_wp_role"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    person_id: Mapped[str] = mapped_column(String(36), ForeignKey("person.id"), nullable=False)
    workpackage_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workpackage.id"), nullable=False
    )
    wp_role: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )

    person: Mapped[Person] = relationship(back_populates="memberships")
    workpackage: Mapped[Workpackage] = relationship(back_populates="memberships")


# --------------------------------------------------------------------------- #
# Sprint 2 — Dokumentenregister                                               #
# --------------------------------------------------------------------------- #


class Document(Base):
    __tablename__ = "document"
    __table_args__ = (
        UniqueConstraint("workpackage_id", "slug", name="uq_document_wp_slug"),
        CheckConstraint(
            "document_type IN ('deliverable','report','note','other')",
            name="ck_document_document_type",
        ),
        CheckConstraint("status IN ('draft','in_review','released')", name="ck_document_status"),
        CheckConstraint(
            "visibility IN ('workpackage','internal','public')",
            name="ck_document_visibility",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    workpackage_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workpackage.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    document_type: Mapped[str] = mapped_column(String, nullable=False)
    deliverable_code: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    visibility: Mapped[str] = mapped_column(String, nullable=False, default="workpackage")
    created_by_person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id"), nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc, onupdate=_now_utc
    )

    workpackage: Mapped[Workpackage] = relationship()
    created_by: Mapped[Person] = relationship()
    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number",
    )


class DocumentVersion(Base):
    __tablename__ = "document_version"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_version_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("document.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    version_label: Mapped[str | None] = mapped_column(String, nullable=True)
    change_note: Mapped[str] = mapped_column(String, nullable=False)
    storage_key: Mapped[str] = mapped_column(String, nullable=False)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by_person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id"), nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )

    document: Mapped[Document] = relationship(back_populates="versions")
    uploaded_by: Mapped[Person] = relationship()
