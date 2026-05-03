"""Schemas rund um Identität, Stammdaten und Auth."""

from __future__ import annotations

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
    """

    id: str
    short_name: str
    name: str
    country: str
    website: str | None = None
    address_line: str | None = None
    postal_code: str | None = None
    city: str | None = None
    address_country: str | None = None
    primary_contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    project_role_note: str | None = None
    is_active: bool = True
    internal_note: str | None = None
    can_edit: bool = False


class PartnerPatchRequest(BaseModel):
    """WP-Lead-Patch — Whitelist erzwingt der Service zusätzlich."""

    name: str | None = Field(default=None, min_length=1)
    website: str | None = None
    address_line: str | None = None
    postal_code: str | None = None
    city: str | None = None
    address_country: str | None = Field(default=None, min_length=2, max_length=2)
    primary_contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    project_role_note: str | None = None


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
    code: str
    title: str
    parent_code: str | None = None
    lead_partner: PartnerRefOut
    sort_order: int


class WorkpackageDetailOut(BaseModel):
    code: str
    title: str
    description: str | None
    parent: WorkpackageRefOut | None
    lead_partner: PartnerRefOut
    children: list[WorkpackageRefOut]
    memberships: list[WPMembershipOut]


class MembershipOut(BaseModel):
    workpackage_code: str
    workpackage_title: str
    wp_role: str
    lead_partner: PartnerRefOut


class WPMembershipOut(BaseModel):
    person_email: str
    person_display_name: str
    wp_role: str


class MeOut(BaseModel):
    person: PersonOut
    memberships: list[MembershipOut]


class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    person: PersonOut
    must_change_password: bool


class PasswordChangeRequest(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=10)


WorkpackageDetailOut.model_rebuild()
