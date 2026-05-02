"""Schemas rund um Identität, Stammdaten und Auth."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PartnerRefOut(BaseModel):
    short_name: str
    name: str


class PartnerOut(BaseModel):
    id: str
    short_name: str
    name: str
    country: str
    website: str | None = None


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
