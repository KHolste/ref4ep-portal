"""Schemas rund um Identität, Stammdaten und Auth."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class PartnerRefOut(BaseModel):
    id: str
    short_name: str
    name: str


class PartnerOut(BaseModel):
    id: str
    short_name: str
    name: str
    country: str
    website: str | None = None


class PartnerDetailOut(BaseModel):
    """Detail-Sicht für eingeloggte Personen.

    Enthält alle fachlich öffentlichen Felder. ``internal_note`` ist
    nur für Admins gefüllt und wird sonst weggelassen.

    Block 0008: Personenbezogene Felder sind nicht mehr Teil der
    Partner-Stammdaten — sie liegen ausschließlich in
    ``PartnerContact``.
    """

    id: str
    short_name: str
    name: str
    country: str
    website: str | None = None
    unit_name: str | None = None
    organization_address_line: str | None = None
    organization_postal_code: str | None = None
    organization_city: str | None = None
    organization_country: str | None = None
    unit_address_same_as_organization: bool = True
    unit_address_line: str | None = None
    unit_postal_code: str | None = None
    unit_city: str | None = None
    unit_country: str | None = None
    is_active: bool = True
    internal_note: str | None = None
    can_edit: bool = False


class PartnerPatchRequest(BaseModel):
    """WP-Lead-Patch — Whitelist erzwingt der Service zusätzlich."""

    name: str | None = Field(default=None, min_length=1)
    website: str | None = None
    unit_name: str | None = None
    organization_address_line: str | None = None
    organization_postal_code: str | None = None
    organization_city: str | None = None
    organization_country: str | None = Field(default=None, min_length=2, max_length=2)
    unit_address_same_as_organization: bool | None = None
    unit_address_line: str | None = None
    unit_postal_code: str | None = None
    unit_city: str | None = None
    unit_country: str | None = Field(default=None, min_length=2, max_length=2)


# --------------------------------------------------------------------------- #
# Block 0007 — Partnerkontakte                                                #
# --------------------------------------------------------------------------- #


class PartnerContactOut(BaseModel):
    """Kontakt-Sicht. ``internal_note`` ist nur für Admins gefüllt."""

    id: str
    partner_id: str
    name: str
    title_or_degree: str | None = None
    email: str | None = None
    phone: str | None = None
    function: str | None = None
    organization_unit: str | None = None
    workpackage_notes: str | None = None
    is_primary_contact: bool = False
    is_project_lead: bool = False
    visibility: str = "internal"
    is_active: bool = True
    internal_note: str | None = None


class PartnerContactCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    title_or_degree: str | None = None
    email: str | None = None
    phone: str | None = None
    function: str | None = None
    organization_unit: str | None = None
    workpackage_notes: str | None = None
    is_primary_contact: bool = False
    is_project_lead: bool = False
    visibility: str = Field(default="internal")
    internal_note: str | None = None


class PartnerContactPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    title_or_degree: str | None = None
    email: str | None = None
    phone: str | None = None
    function: str | None = None
    organization_unit: str | None = None
    workpackage_notes: str | None = None
    is_primary_contact: bool | None = None
    is_project_lead: bool | None = None
    visibility: str | None = None
    internal_note: str | None = None
    is_active: bool | None = None


class PersonOut(BaseModel):
    id: str
    email: str
    display_name: str
    partner: PartnerRefOut
    platform_role: str
    is_active: bool
    must_change_password: bool


class WorkpackageRefOut(BaseModel):
    code: str
    title: str
    lead_partner: PartnerRefOut


class WorkpackageOut(BaseModel):
    id: str
    code: str
    title: str
    parent_code: str | None = None
    lead_partner: PartnerRefOut
    sort_order: int
    start_date: date | None = None
    end_date: date | None = None


class WorkpackageMilestoneOut(BaseModel):
    """Schmaler Meilenstein-View für die WP-Detailseite."""

    id: str
    code: str
    title: str
    planned_date: date
    actual_date: date | None = None
    status: str
    note: str | None = None


class WorkpackageContactOut(BaseModel):
    """Kontaktperson des Lead-Partners auf der WP-Cockpit-Seite."""

    id: str
    name: str
    title_or_degree: str | None = None
    email: str | None = None
    phone: str | None = None
    function: str | None = None
    is_primary_contact: bool = False
    is_project_lead: bool = False


class WorkpackageDetailOut(BaseModel):
    code: str
    title: str
    description: str | None
    parent: WorkpackageRefOut | None
    lead_partner: PartnerRefOut
    children: list[WorkpackageRefOut]
    memberships: list[WPMembershipOut]
    # Block 0009 — Cockpit-Felder.
    status: str = "planned"
    summary: str | None = None
    next_steps: str | None = None
    open_issues: str | None = None
    can_edit_status: bool = False
    # Block 0027 — Zeitplan.
    start_date: date | None = None
    end_date: date | None = None
    lead_partner_contacts: list[WorkpackageContactOut] = Field(default_factory=list)
    milestones: list[WorkpackageMilestoneOut] = Field(default_factory=list)


class WorkpackageStatusPatchRequest(BaseModel):
    """PATCH des WP-Cockpits — alle Felder optional, Whitelist im Service.

    Block 0027 ergänzt ``start_date``/``end_date``; der Service prüft
    fachliche Konsistenz (``end_date >= start_date``).
    """

    status: str | None = None
    summary: str | None = None
    next_steps: str | None = None
    open_issues: str | None = None
    start_date: date | None = None
    end_date: date | None = None


class MilestoneOut(BaseModel):
    id: str
    code: str
    title: str
    workpackage_id: str | None = None
    workpackage_code: str | None = None
    workpackage_title: str | None = None
    planned_date: date
    actual_date: date | None = None
    status: str
    note: str | None = None
    can_edit: bool = False


class MilestonePatchRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    planned_date: date | None = None
    actual_date: date | None = None
    status: str | None = None
    note: str | None = None


# Block 0039 — Meilenstein-Dokumentverknüpfungen.


class MilestoneDocumentLinkOut(BaseModel):
    """Kompakte Sicht eines mit einem Meilenstein verknüpften Dokuments."""

    document_id: str
    title: str
    document_type: str
    library_section: str | None = None
    workpackage_code: str | None = None
    status: str
    visibility: str
    created_at: datetime


class MilestoneDocumentLinkAddRequest(BaseModel):
    document_id: str = Field(min_length=36, max_length=36)


class DocumentMilestoneRefOut(BaseModel):
    """Kompakte Sicht eines Meilensteins, mit dem ein Dokument
    verknüpft ist (für die Anzeige im Dokumentdetail)."""

    id: str
    code: str
    title: str
    planned_date: date
    status: str


# --------------------------------------------------------------------------- #
# Block 0010 — Projekt-Cockpit                                                #
# --------------------------------------------------------------------------- #


class CockpitMilestoneOut(BaseModel):
    """Schmale Meilenstein-Sicht für die Cockpit-Karten."""

    id: str
    code: str
    title: str
    workpackage_code: str | None = None
    workpackage_title: str | None = None
    planned_date: date
    actual_date: date | None = None
    status: str
    days_to_planned: int
    note: str | None = None


class CockpitOpenIssueOut(BaseModel):
    code: str
    title: str
    status: str
    open_issues: str
    next_steps: str | None = None


class CockpitWorkpackageStatusOut(BaseModel):
    code: str
    title: str
    status: str


class CockpitMilestoneCountsOut(BaseModel):
    """Mini-Histogramm pro WP — Anzahl Meilensteine je Ampelwert."""

    green: int = 0
    yellow: int = 0
    red: int = 0
    gray: int = 0


class CockpitWorkpackageHealthOut(BaseModel):
    """Ampel-Sicht pro Arbeitspaket (Block 0025)."""

    code: str
    title: str
    status: str
    traffic_light: str  # green | yellow | red | gray
    milestone_counts: CockpitMilestoneCountsOut
    document_counts: dict[str, int] = Field(default_factory=dict)
    next_milestone: CockpitMilestoneOut | None = None


class CockpitMilestoneProgressOut(BaseModel):
    achieved: int = 0
    total: int = 0


class CockpitTimelineEventOut(BaseModel):
    """Eintrag im 60-Tage-Zeitstrahl."""

    date: date
    kind: str  # milestone | meeting | campaign
    id: str
    title: str
    workpackage_code: str | None = None
    status: str | None = None


class ProjectCockpitOut(BaseModel):
    today: date
    upcoming_milestones: list[CockpitMilestoneOut] = Field(default_factory=list)
    overdue_milestones: list[CockpitMilestoneOut] = Field(default_factory=list)
    workpackages_with_open_issues: list[CockpitOpenIssueOut] = Field(default_factory=list)
    status_counts: dict[str, int] = Field(default_factory=dict)
    workpackage_status_overview: list[CockpitWorkpackageStatusOut] = Field(default_factory=list)
    # Block 0025 — Ampel-Dashboard:
    workpackage_health: list[CockpitWorkpackageHealthOut] = Field(default_factory=list)
    milestone_progress: CockpitMilestoneProgressOut = Field(
        default_factory=CockpitMilestoneProgressOut
    )
    open_meeting_actions: int = 0
    campaign_status_counts: dict[str, int] = Field(default_factory=dict)
    timeline_next_60_days: list[CockpitTimelineEventOut] = Field(default_factory=list)


class MembershipOut(BaseModel):
    workpackage_code: str
    workpackage_title: str
    wp_role: str
    lead_partner: PartnerRefOut


class WPMembershipOut(BaseModel):
    person_email: str
    person_display_name: str
    wp_role: str


class MePartnerRoleOut(BaseModel):
    """Block 0045 — kompakte Sicht auf eine Partnerrolle der
    eingeloggten Person. Aktuell ist ``role`` ausschließlich
    ``partner_lead`` (UI-Label „Projektleitung")."""

    partner_id: str
    partner_short_name: str
    role: str


class MeOut(BaseModel):
    person: PersonOut
    memberships: list[MembershipOut]
    # Block 0045 — Partnerrollen der eingeloggten Person. Frontend
    # nutzt das z. B., um den „Mein Team"-Eintrag auch für
    # Projektleitungen ohne WP-Lead-Mitgliedschaft sichtbar zu machen.
    partner_roles: list[MePartnerRoleOut] = Field(default_factory=list)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    person: PersonOut
    must_change_password: bool


class PasswordChangeRequest(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=10)


# --------------------------------------------------------------------------- #
# Block 0013 — „Mein Team" für WP-Leads                                       #
# --------------------------------------------------------------------------- #


class LeadPersonOut(BaseModel):
    """Schmale Personen-Sicht für die Lead-Team-Seite — kein password_hash."""

    id: str
    email: str
    display_name: str
    is_active: bool
    must_change_password: bool


class LeadPersonCreateRequest(BaseModel):
    """Anlegen einer Person durch WP-Lead. Partner und Plattformrolle
    werden serverseitig erzwungen — Client darf hier nichts mitschicken."""

    email: str = Field(min_length=3)
    display_name: str = Field(min_length=1)
    initial_password: str | None = Field(default=None, min_length=10)


class LeadPersonCreatedOut(BaseModel):
    person: LeadPersonOut
    initial_password: str = Field(
        description="Klartext, einmalig nach Anlage. Nicht erneut abrufbar."
    )


class LeadWorkpackageMemberOut(BaseModel):
    person_id: str
    email: str
    display_name: str
    wp_role: str


class LeadWorkpackageOut(BaseModel):
    code: str
    title: str
    my_role: str
    members: list[LeadWorkpackageMemberOut] = Field(default_factory=list)


class LeadAddMembershipRequest(BaseModel):
    person_id: str = Field(min_length=36, max_length=36)
    wp_role: str = Field(default="wp_member")


class LeadSetMembershipRoleRequest(BaseModel):
    wp_role: str


# --------------------------------------------------------------------------- #
# Block 0015 — Meeting-/Protokollregister                                     #
# --------------------------------------------------------------------------- #


class MeetingWorkpackageOut(BaseModel):
    code: str
    title: str


class MeetingPersonOut(BaseModel):
    id: str
    display_name: str
    email: str


class MeetingDocumentOut(BaseModel):
    document_id: str
    title: str
    deliverable_code: str | None = None
    label: str


class MeetingDecisionOut(BaseModel):
    id: str
    text: str
    status: str
    workpackage_code: str | None = None
    responsible_person: MeetingPersonOut | None = None


class MeetingActionOut(BaseModel):
    id: str
    text: str
    status: str
    due_date: date | None = None
    workpackage_code: str | None = None
    responsible_person: MeetingPersonOut | None = None
    note: str | None = None


class MeetingListItemOut(BaseModel):
    id: str
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    format: str
    category: str
    status: str
    workpackages: list[MeetingWorkpackageOut] = Field(default_factory=list)
    open_actions: int = 0
    decisions: int = 0
    can_edit: bool = False


class MeetingDetailOut(BaseModel):
    id: str
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    format: str
    location: str | None = None
    category: str
    status: str
    summary: str | None = None
    extra_participants: str | None = None
    created_by: MeetingPersonOut
    workpackages: list[MeetingWorkpackageOut] = Field(default_factory=list)
    participants: list[MeetingPersonOut] = Field(default_factory=list)
    decisions: list[MeetingDecisionOut] = Field(default_factory=list)
    actions: list[MeetingActionOut] = Field(default_factory=list)
    documents: list[MeetingDocumentOut] = Field(default_factory=list)
    can_edit: bool = False


class MeetingCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    starts_at: datetime
    ends_at: datetime | None = None
    format: str = "online"
    location: str | None = None
    category: str = "other"
    status: str = "planned"
    summary: str | None = None
    extra_participants: str | None = None
    workpackage_ids: list[str] = Field(default_factory=list)


class MeetingPatchRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    format: str | None = None
    location: str | None = None
    category: str | None = None
    status: str | None = None
    summary: str | None = None
    extra_participants: str | None = None
    workpackage_ids: list[str] | None = None


class MeetingParticipantAddRequest(BaseModel):
    person_id: str = Field(min_length=36, max_length=36)


class MeetingDecisionCreateRequest(BaseModel):
    text: str = Field(min_length=1)
    workpackage_id: str | None = None
    responsible_person_id: str | None = None
    status: str = "open"


class MeetingDecisionPatchRequest(BaseModel):
    text: str | None = Field(default=None, min_length=1)
    status: str | None = None
    workpackage_id: str | None = None
    responsible_person_id: str | None = None


class MeetingActionCreateRequest(BaseModel):
    text: str = Field(min_length=1)
    workpackage_id: str | None = None
    responsible_person_id: str | None = None
    due_date: date | None = None
    status: str = "open"
    note: str | None = None


class MeetingActionPatchRequest(BaseModel):
    text: str | None = Field(default=None, min_length=1)
    status: str | None = None
    workpackage_id: str | None = None
    responsible_person_id: str | None = None
    due_date: date | None = None
    note: str | None = None


class MeetingDocumentLinkAddRequest(BaseModel):
    document_id: str = Field(min_length=36, max_length=36)
    label: str = "other"


# --------------------------------------------------------------------------- #
# Block 0018 — zentrale Aufgabenübersicht                                     #
# --------------------------------------------------------------------------- #


class ActionListItemOut(BaseModel):
    id: str
    text: str
    status: str
    due_date: date | None = None
    note: str | None = None
    meeting_id: str
    meeting_title: str
    workpackage_code: str | None = None
    workpackage_title: str | None = None
    responsible_person: MeetingPersonOut | None = None
    can_edit: bool = False
    created_at: datetime
    updated_at: datetime


class ActionPatchRequest(BaseModel):
    status: str | None = None
    note: str | None = None
    due_date: date | None = None
    responsible_person_id: str | None = None
    workpackage_id: str | None = None
    text: str | None = Field(default=None, min_length=1)


# --------------------------------------------------------------------------- #
# Block 0018 — Aktivitäts-Feed                                                #
# --------------------------------------------------------------------------- #


class ActivityEntryOut(BaseModel):
    timestamp: datetime
    actor: str | None = None
    type: str  # document/meeting/action/decision/workpackage/team/milestone/other
    title: str
    description: str | None = None
    link: str | None = None


# --------------------------------------------------------------------------- #
# Block 0018 — personalisierte Cockpit-Sicht                                  #
# --------------------------------------------------------------------------- #


class MyWorkpackageOut(BaseModel):
    code: str
    title: str
    wp_role: str  # wp_lead / wp_member
    status: str


class MyMeetingOut(BaseModel):
    id: str
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    status: str
    workpackage_codes: list[str] = Field(default_factory=list)


class MyActionOut(BaseModel):
    id: str
    text: str
    status: str
    due_date: date | None = None
    overdue: bool = False
    meeting_id: str
    meeting_title: str
    workpackage_code: str | None = None


class MyCockpitOut(BaseModel):
    today: date
    my_workpackages: list[MyWorkpackageOut] = Field(default_factory=list)
    my_lead_workpackages: list[MyWorkpackageOut] = Field(default_factory=list)
    my_open_actions: list[MyActionOut] = Field(default_factory=list)
    my_overdue_actions: list[MyActionOut] = Field(default_factory=list)
    my_next_meetings: list[MyMeetingOut] = Field(default_factory=list)


WorkpackageDetailOut.model_rebuild()
