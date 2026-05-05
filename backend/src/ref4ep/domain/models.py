"""SQLAlchemy-Modelle für Identität, Projektstruktur, Dokumente und Audit.

Sprint-1-Tabellen:
- partner       — Konsortialpartner
- person        — Konsortiumsangehörige mit Login
- workpackage   — Arbeitspakete (zweistufige Hierarchie)
- membership    — Verknüpfung Person × Workpackage × WP-Rolle

Sprint-2-Tabellen:
- document          — projektbezogener Registereintrag mit WP-Bezug
- document_version  — append-only Versionseinträge mit Storage-Key

Sprint-3-Erweiterungen:
- audit_log         — Audit-Einträge für jede schreibende Aktion
- document.released_version_id  — FK auf document_version.id
                                  (zyklisch, mit use_alter=True)

UUID-Spalten als CHAR(36) für Dialektneutralität (SQLite + PostgreSQL).
Zeitstempel als ``DateTime(timezone=True)``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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

# Block 0009 — Cockpit-Status pro Arbeitspaket. Default ``planned``.
WORKPACKAGE_STATUSES = (
    "planned",
    "in_progress",
    "waiting_for_input",
    "critical",
    "completed",
)
WORKPACKAGE_STATUS_LABELS_DE = {
    "planned": "geplant",
    "in_progress": "in Arbeit",
    "waiting_for_input": "wartet auf Input",
    "critical": "kritisch",
    "completed": "abgeschlossen",
}

# Block 0009 — Meilensteine. ``MS4`` darf ``workpackage_id = NULL``
# haben (Gesamtprojekt-Meilenstein).
MILESTONE_STATUSES = (
    "planned",
    "achieved",
    "postponed",
    "at_risk",
    "cancelled",
)
MILESTONE_STATUS_LABELS_DE = {
    "planned": "geplant",
    "achieved": "erreicht",
    "postponed": "verschoben",
    "at_risk": "gefährdet",
    "cancelled": "entfallen",
}

# Block 0015 — Meeting-/Protokollregister.
MEETING_FORMATS = ("online", "in_person", "hybrid")
MEETING_FORMAT_LABELS_DE = {
    "online": "online",
    "in_person": "Präsenz",
    "hybrid": "hybrid",
}

MEETING_CATEGORIES = (
    "consortium",
    "jour_fixe",
    "workpackage",
    "technical",
    "review",
    "test_campaign",
    "other",
)
MEETING_CATEGORY_LABELS_DE = {
    "consortium": "Konsortialtreffen",
    "jour_fixe": "Jour fixe",
    "workpackage": "Arbeitspaket-Treffen",
    "technical": "Technisches Abstimmungstreffen",
    "review": "Review / Freigabe",
    "test_campaign": "Messkampagnenbesprechung",
    "other": "Sonstiges",
}

MEETING_STATUSES = (
    "planned",
    "held",
    "minutes_draft",
    "minutes_approved",
    "completed",
    "cancelled",
)
MEETING_STATUS_LABELS_DE = {
    "planned": "geplant",
    "held": "durchgeführt",
    "minutes_draft": "Protokoll in Arbeit",
    "minutes_approved": "Protokoll abgestimmt",
    "completed": "abgeschlossen",
    "cancelled": "abgesagt",
}

MEETING_DECISION_STATUSES = ("open", "valid", "replaced", "revoked")
MEETING_DECISION_STATUS_LABELS_DE = {
    "open": "offen",
    "valid": "gültig",
    "replaced": "ersetzt",
    "revoked": "aufgehoben",
}

MEETING_ACTION_STATUSES = ("open", "in_progress", "done", "cancelled")
MEETING_ACTION_STATUS_LABELS_DE = {
    "open": "offen",
    "in_progress": "in Arbeit",
    "done": "erledigt",
    "cancelled": "entfällt",
}

MEETING_DOCUMENT_LABELS = (
    "agenda",
    "minutes",
    "presentation",
    "decision_template",
    "attachment",
    "other",
)
MEETING_DOCUMENT_LABEL_LABELS_DE = {
    "agenda": "Agenda",
    "minutes": "Protokoll",
    "presentation": "Präsentation",
    "decision_template": "Beschlussvorlage",
    "attachment": "Anlage",
    "other": "Sonstiges",
}

# Block 0022 — Testkampagnenregister.
TEST_CAMPAIGN_CATEGORIES = (
    "ring_comparison",
    "reference_measurement",
    "diagnostics_test",
    "calibration",
    "facility_characterization",
    "endurance_test",
    "acceptance_test",
    "other",
)
TEST_CAMPAIGN_CATEGORY_LABELS_DE = {
    "ring_comparison": "Ringvergleich",
    "reference_measurement": "Referenzmessung",
    "diagnostics_test": "Diagnostiktest",
    "calibration": "Kalibrierung",
    "facility_characterization": "Facility-Charakterisierung",
    "endurance_test": "Langzeittest",
    "acceptance_test": "Abnahmetest",
    "other": "Sonstiges",
}

TEST_CAMPAIGN_STATUSES = (
    "planned",
    "preparing",
    "running",
    "completed",
    "evaluated",
    "cancelled",
    "postponed",
)
TEST_CAMPAIGN_STATUS_LABELS_DE = {
    "planned": "geplant",
    "preparing": "in Vorbereitung",
    "running": "laufend",
    "completed": "abgeschlossen",
    "evaluated": "ausgewertet",
    "cancelled": "abgebrochen",
    "postponed": "verschoben",
}

TEST_CAMPAIGN_PARTICIPANT_ROLES = (
    "campaign_lead",
    "facility_responsible",
    "diagnostics",
    "data_analysis",
    "operation",
    "safety",
    "observer",
    "other",
)
TEST_CAMPAIGN_PARTICIPANT_ROLE_LABELS_DE = {
    "campaign_lead": "Kampagnenleitung",
    "facility_responsible": "Facility-Verantwortung",
    "diagnostics": "Diagnostik",
    "data_analysis": "Datenanalyse",
    "operation": "Betrieb",
    "safety": "Sicherheit",
    "observer": "Beobachtung",
    "other": "Sonstiges",
}

TEST_CAMPAIGN_DOCUMENT_LABELS = (
    "test_plan",
    "setup_plan",
    "safety_document",
    "raw_data_description",
    "protocol",
    "analysis",
    "presentation",
    "attachment",
    "other",
)
TEST_CAMPAIGN_DOCUMENT_LABEL_LABELS_DE = {
    "test_plan": "Messplan",
    "setup_plan": "Aufbauplan",
    "safety_document": "Sicherheitsunterlage",
    "raw_data_description": "Rohdatenbeschreibung",
    "protocol": "Protokoll",
    "analysis": "Auswertung",
    "presentation": "Präsentation",
    "attachment": "Anlage",
    "other": "Sonstiges",
}

# Dokument-Enums (Sprint 2). status und visibility sind im Schema komplett
# vorgesehen, in Sprint 2 aber konstant 'draft' / 'workpackage'. Release- und
# Sichtbarkeits-Workflows folgen Sprint 3, öffentliche Bibliothek Sprint 4.
DOCUMENT_TYPES = ("deliverable", "report", "note", "other")
DOCUMENT_STATUSES = ("draft", "in_review", "released")
DOCUMENT_VISIBILITIES = ("workpackage", "internal", "public")

# Sichtbarkeit der Kontaktpersonen (Block 0007). ``public`` ist im
# Datenmodell vorbereitet, wird aber in diesem Block noch nicht
# öffentlich ausgespielt.
PARTNER_CONTACT_VISIBILITIES = ("internal", "public")

# Vorgegebene Funktions-Auswahlliste für Kontaktpersonen. Die Liste
# wird im UI angeboten; im Datenmodell bleibt ``function`` ein
# freier String (eingehende Werte werden im Service jedoch validiert
# und auf diese Whitelist eingeschränkt — ``None`` bedeutet
# "nicht angegeben").
PARTNER_CONTACT_FUNCTIONS = (
    "Projektleitung",
    "stellvertretende Projektleitung",
    "wissenschaftliche Projektkoordination",
    "Professorin/Professor",
    "Senior Scientist",
    "Postdoc",
    "Doktorandin/Doktorand",
    "wissenschaftliche Mitarbeiterin/wissenschaftlicher Mitarbeiter",
    "Technikerin/Techniker",
    "studentische Hilfskraft",
    "Masterstudentin/Masterstudent",
    "Bachelorstudentin/Bachelorstudent",
    "Administration",
    "Ansprechperson für Daten/Dokumente",
    "Ansprechperson für Finanzen/Verwaltung",
    "sonstige Funktion",
)


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
    # Migration 0006/0007/0008: Partner-Stammdaten beschreiben jetzt
    # ausschließlich Organisation und bearbeitende Einheit. Personen
    # liegen ausschließlich in ``partner_contact``.
    #
    # Bearbeitende Einheit innerhalb der Organisation
    # (z. B. „I. Physikalisches Institut" bei der JLU). Optional.
    unit_name: Mapped[str | None] = mapped_column(String, nullable=True)
    # Postanschrift der Organisation.
    organization_address_line: Mapped[str | None] = mapped_column(String, nullable=True)
    organization_postal_code: Mapped[str | None] = mapped_column(String, nullable=True)
    organization_city: Mapped[str | None] = mapped_column(String, nullable=True)
    organization_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    # Postanschrift der bearbeitenden Einheit. Wenn das Flag gesetzt
    # ist (Default), übernimmt die UI die Organisationsadresse und
    # die unit_address_*-Felder bleiben leer.
    unit_address_same_as_organization: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    unit_address_line: Mapped[str | None] = mapped_column(String, nullable=True)
    unit_postal_code: Mapped[str | None] = mapped_column(String, nullable=True)
    unit_city: Mapped[str | None] = mapped_column(String, nullable=True)
    unit_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    # Fachliche Aktivität im Projekt — getrennt von ``is_deleted``.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    internal_note: Mapped[str | None] = mapped_column(String, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc, onupdate=_now_utc
    )

    persons: Mapped[list[Person]] = relationship(back_populates="partner")
    led_workpackages: Mapped[list[Workpackage]] = relationship(back_populates="lead_partner")
    contacts: Mapped[list[PartnerContact]] = relationship(
        back_populates="partner",
        cascade="all, delete-orphan",
        order_by="PartnerContact.name",
    )


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
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned','in_progress','waiting_for_input','critical','completed')",
            name="ck_workpackage_status",
        ),
    )

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
    # Block 0009 — Cockpit-Felder.
    status: Mapped[str] = mapped_column(String, nullable=False, default="planned")
    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    next_steps: Mapped[str | None] = mapped_column(String, nullable=True)
    open_issues: Mapped[str | None] = mapped_column(String, nullable=True)
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
    milestones: Mapped[list[Milestone]] = relationship(
        back_populates="workpackage",
        order_by="Milestone.code",
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
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    visibility: Mapped[str] = mapped_column(String, nullable=False, default="workpackage")
    # Sprint-3: FK auf document_version.id mit use_alter=True wegen Zyklus
    # document ↔ document_version. Service-Layer prüft zusätzlich, dass die
    # referenzierte Version zum richtigen Dokument gehört.
    released_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "document_version.id",
            name="fk_document_released_version",
            use_alter=True,
        ),
        nullable=True,
    )
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
        foreign_keys="DocumentVersion.document_id",
    )
    released_version: Mapped[DocumentVersion | None] = relationship(
        foreign_keys=[released_version_id],
        post_update=True,
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

    document: Mapped[Document] = relationship(back_populates="versions", foreign_keys=[document_id])
    uploaded_by: Mapped[Person] = relationship()


# --------------------------------------------------------------------------- #
# Sprint 3 — Audit-Log                                                        #
# --------------------------------------------------------------------------- #


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    actor_person_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("person.id"), nullable=True
    )
    actor_label: Mapped[str | None] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    details: Mapped[str | None] = mapped_column(String, nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )

    actor: Mapped[Person | None] = relationship()


# --------------------------------------------------------------------------- #
# Block 0007 — Partnerkontakte                                                #
# --------------------------------------------------------------------------- #


class PartnerContact(Base):
    __tablename__ = "partner_contact"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('internal','public')",
            name="ck_partner_contact_visibility",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    partner_id: Mapped[str] = mapped_column(String(36), ForeignKey("partner.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    title_or_degree: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    function: Mapped[str | None] = mapped_column(String, nullable=True)
    organization_unit: Mapped[str | None] = mapped_column(String, nullable=True)
    workpackage_notes: Mapped[str | None] = mapped_column(String, nullable=True)
    is_primary_contact: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_project_lead: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    visibility: Mapped[str] = mapped_column(String, nullable=False, default="internal")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    internal_note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc, onupdate=_now_utc
    )

    partner: Mapped[Partner] = relationship(back_populates="contacts")


# --------------------------------------------------------------------------- #
# Block 0009 — Meilensteine                                                   #
# --------------------------------------------------------------------------- #


class Milestone(Base):
    __tablename__ = "milestone"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned','achieved','postponed','at_risk','cancelled')",
            name="ck_milestone_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    code: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    # Nullable: MS4 (Projektende) hängt an keinem konkreten WP.
    workpackage_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workpackage.id"), nullable=True
    )
    planned_date: Mapped[date] = mapped_column(Date, nullable=False)
    actual_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="planned")
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc, onupdate=_now_utc
    )

    workpackage: Mapped[Workpackage | None] = relationship(back_populates="milestones")


# --------------------------------------------------------------------------- #
# Block 0015 — Meeting-/Protokollregister                                     #
# --------------------------------------------------------------------------- #


class Meeting(Base):
    __tablename__ = "meeting"
    __table_args__ = (
        CheckConstraint("format IN ('online','in_person','hybrid')", name="ck_meeting_format"),
        CheckConstraint(
            "category IN ('consortium','jour_fixe','workpackage','technical',"
            "'review','test_campaign','other')",
            name="ck_meeting_category",
        ),
        CheckConstraint(
            "status IN ('planned','held','minutes_draft','minutes_approved',"
            "'completed','cancelled')",
            name="ck_meeting_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    title: Mapped[str] = mapped_column(String, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    format: Mapped[str] = mapped_column(String, nullable=False, default="online")
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str] = mapped_column(String, nullable=False, default="other")
    status: Mapped[str] = mapped_column(String, nullable=False, default="planned")
    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    extra_participants: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by_id: Mapped[str] = mapped_column(String(36), ForeignKey("person.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc, onupdate=_now_utc
    )

    created_by: Mapped[Person] = relationship()
    workpackage_links: Mapped[list[MeetingWorkpackage]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )
    participant_links: Mapped[list[MeetingParticipant]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )
    decisions: Mapped[list[MeetingDecision]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
        order_by="MeetingDecision.created_at",
    )
    actions: Mapped[list[MeetingAction]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
        order_by="MeetingAction.created_at",
    )
    document_links: Mapped[list[MeetingDocumentLink]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )


class MeetingWorkpackage(Base):
    __tablename__ = "meeting_workpackage"

    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meeting.id", ondelete="CASCADE"), primary_key=True
    )
    workpackage_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workpackage.id"), primary_key=True
    )

    meeting: Mapped[Meeting] = relationship(back_populates="workpackage_links")
    workpackage: Mapped[Workpackage] = relationship()


class MeetingParticipant(Base):
    __tablename__ = "meeting_participant"

    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meeting.id", ondelete="CASCADE"), primary_key=True
    )
    person_id: Mapped[str] = mapped_column(String(36), ForeignKey("person.id"), primary_key=True)

    meeting: Mapped[Meeting] = relationship(back_populates="participant_links")
    person: Mapped[Person] = relationship()


class MeetingDecision(Base):
    __tablename__ = "meeting_decision"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open','valid','replaced','revoked')",
            name="ck_meeting_decision_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meeting.id", ondelete="CASCADE"), nullable=False
    )
    workpackage_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workpackage.id"), nullable=True
    )
    text: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    responsible_person_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("person.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc, onupdate=_now_utc
    )

    meeting: Mapped[Meeting] = relationship(back_populates="decisions")
    workpackage: Mapped[Workpackage | None] = relationship()
    responsible: Mapped[Person | None] = relationship()


class MeetingAction(Base):
    __tablename__ = "meeting_action"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open','in_progress','done','cancelled')",
            name="ck_meeting_action_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meeting.id", ondelete="CASCADE"), nullable=False
    )
    workpackage_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workpackage.id"), nullable=True
    )
    responsible_person_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("person.id"), nullable=True
    )
    text: Mapped[str] = mapped_column(String, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc, onupdate=_now_utc
    )

    meeting: Mapped[Meeting] = relationship(back_populates="actions")
    workpackage: Mapped[Workpackage | None] = relationship()
    responsible: Mapped[Person | None] = relationship()


class MeetingDocumentLink(Base):
    __tablename__ = "meeting_document_link"
    __table_args__ = (
        CheckConstraint(
            "label IN ('agenda','minutes','presentation','decision_template','attachment','other')",
            name="ck_meeting_document_link_label",
        ),
    )

    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meeting.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document.id"), primary_key=True
    )
    label: Mapped[str] = mapped_column(String, nullable=False, default="other")

    meeting: Mapped[Meeting] = relationship(back_populates="document_links")
    document: Mapped[Document] = relationship()


# --------------------------------------------------------------------------- #
# Block 0022 — Testkampagnenregister                                          #
# --------------------------------------------------------------------------- #


class TestCampaign(Base):
    __tablename__ = "test_campaign"
    # pytest sammelt sonst diese Klasse als Test-Klasse ein (Name beginnt mit „Test").
    __test__ = False
    __table_args__ = (
        UniqueConstraint("code", name="uq_test_campaign_code"),
        CheckConstraint(
            "category IN ('ring_comparison','reference_measurement','diagnostics_test',"
            "'calibration','facility_characterization','endurance_test',"
            "'acceptance_test','other')",
            name="ck_test_campaign_category",
        ),
        CheckConstraint(
            "status IN ('planned','preparing','running','completed','evaluated',"
            "'cancelled','postponed')",
            name="ck_test_campaign_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    code: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False, default="other")
    status: Mapped[str] = mapped_column(String, nullable=False, default="planned")
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    facility: Mapped[str | None] = mapped_column(String, nullable=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    short_description: Mapped[str | None] = mapped_column(String, nullable=True)
    objective: Mapped[str | None] = mapped_column(String, nullable=True)
    test_matrix: Mapped[str | None] = mapped_column(String, nullable=True)
    expected_measurements: Mapped[str | None] = mapped_column(String, nullable=True)
    boundary_conditions: Mapped[str | None] = mapped_column(String, nullable=True)
    success_criteria: Mapped[str | None] = mapped_column(String, nullable=True)
    risks_or_open_points: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by_id: Mapped[str] = mapped_column(String(36), ForeignKey("person.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc, onupdate=_now_utc
    )

    created_by: Mapped[Person] = relationship()
    workpackage_links: Mapped[list[TestCampaignWorkpackage]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    participant_links: Mapped[list[TestCampaignParticipant]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="TestCampaignParticipant.created_at",
    )
    document_links: Mapped[list[TestCampaignDocumentLink]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )


class TestCampaignWorkpackage(Base):
    __tablename__ = "test_campaign_workpackage"

    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_campaign.id", ondelete="CASCADE"), primary_key=True
    )
    workpackage_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workpackage.id"), primary_key=True
    )

    campaign: Mapped[TestCampaign] = relationship(back_populates="workpackage_links")
    workpackage: Mapped[Workpackage] = relationship()


class TestCampaignParticipant(Base):
    __tablename__ = "test_campaign_participant"
    __table_args__ = (
        UniqueConstraint("campaign_id", "person_id", name="uq_test_campaign_participant_pair"),
        CheckConstraint(
            "role IN ('campaign_lead','facility_responsible','diagnostics',"
            "'data_analysis','operation','safety','observer','other')",
            name="ck_test_campaign_participant_role",
        ),
    )

    # Surrogate-PK, weil ``role`` per PATCH änderbar ist und der Endpunkt
    # ``/api/campaign-participants/{id}`` einen stabilen, kurzen Schlüssel
    # braucht (analog zu MeetingDecision/MeetingAction).
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_campaign.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[str] = mapped_column(String(36), ForeignKey("person.id"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="other")
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc, onupdate=_now_utc
    )

    campaign: Mapped[TestCampaign] = relationship(back_populates="participant_links")
    person: Mapped[Person] = relationship()


class TestCampaignDocumentLink(Base):
    __tablename__ = "test_campaign_document_link"
    __table_args__ = (
        CheckConstraint(
            "label IN ('test_plan','setup_plan','safety_document','raw_data_description',"
            "'protocol','analysis','presentation','attachment','other')",
            name="ck_test_campaign_document_link_label",
        ),
    )

    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_campaign.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document.id"), primary_key=True
    )
    label: Mapped[str] = mapped_column(String, nullable=False, default="other")

    campaign: Mapped[TestCampaign] = relationship(back_populates="document_links")
    document: Mapped[Document] = relationship()
