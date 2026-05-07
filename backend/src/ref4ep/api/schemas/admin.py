"""Admin-Schemas für /api/admin/persons, /partners und Mitgliedschaften.

Wichtig: ``password_hash`` wird **nirgends** in einem Antwort-Schema
exportiert. Das einzige Klartext-Passwort, das die API jemals
zurückgibt, ist das ``initial_password`` in
``AdminPersonCreatedOut`` und ``AdminPasswordResetResponse``
(beides einmalig nach Admin-Aktion).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Personen                                                                    #
# --------------------------------------------------------------------------- #


class AdminPartnerRefOut(BaseModel):
    id: str
    short_name: str
    name: str


class AdminMembershipOut(BaseModel):
    workpackage_id: str
    workpackage_code: str
    workpackage_title: str
    wp_role: str


class AdminPersonOut(BaseModel):
    id: str
    email: str
    display_name: str
    partner: AdminPartnerRefOut
    platform_role: str
    is_active: bool
    must_change_password: bool


class AdminPersonDetailOut(AdminPersonOut):
    memberships: list[AdminMembershipOut] = Field(default_factory=list)


class AdminPersonCreatedOut(BaseModel):
    person: AdminPersonOut
    initial_password: str = Field(
        description="Klartext, einmalig nach Anlage. Nicht erneut abrufbar."
    )


class AdminPasswordResetResponse(BaseModel):
    initial_password: str = Field(
        description="Klartext, einmalig nach Reset. Nicht erneut abrufbar."
    )


# ---- Requests -----------------------------------------------------------


class AdminPersonCreateRequest(BaseModel):
    email: str = Field(min_length=3)
    display_name: str = Field(min_length=1)
    partner_id: str = Field(min_length=36, max_length=36)
    platform_role: Literal["admin", "member"] = "member"
    initial_password: str | None = Field(default=None, min_length=10)


class AdminPersonPatchRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1)
    partner_id: str | None = Field(default=None, min_length=36, max_length=36)
    email: str | None = Field(default=None, min_length=3)


class AdminSetRoleRequest(BaseModel):
    role: Literal["admin", "member"]


class AdminResetPasswordRequest(BaseModel):
    initial_password: str | None = Field(default=None, min_length=10)


# --------------------------------------------------------------------------- #
# Partner                                                                     #
# --------------------------------------------------------------------------- #


class AdminPartnerOut(BaseModel):
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
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class AdminPartnerCreateRequest(BaseModel):
    """Anlegen — minimal. Weitere Felder werden auf der Detailseite gepflegt."""

    short_name: str = Field(min_length=1)
    name: str = Field(min_length=1)
    country: str = Field(min_length=2, max_length=2)
    website: str | None = None
    unit_name: str | None = None


class AdminPartnerPatchRequest(BaseModel):
    short_name: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    country: str | None = Field(default=None, min_length=2, max_length=2)
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
    is_active: bool | None = None
    internal_note: str | None = None


# --------------------------------------------------------------------------- #
# Mitgliedschaften                                                            #
# --------------------------------------------------------------------------- #


class AdminMembershipAddRequest(BaseModel):
    workpackage_code: str = Field(min_length=1)
    wp_role: Literal["wp_lead", "wp_member"]


class AdminMembershipPatchRequest(BaseModel):
    wp_role: Literal["wp_lead", "wp_member"]


__all__ = [
    "AdminMembershipAddRequest",
    "AdminMembershipOut",
    "AdminMembershipPatchRequest",
    "AdminPartnerCreateRequest",
    "AdminPartnerOut",
    "AdminPartnerPatchRequest",
    "AdminPartnerRefOut",
    "AdminPasswordResetResponse",
    "AdminPersonCreateRequest",
    "AdminPersonCreatedOut",
    "AdminPersonDetailOut",
    "AdminPersonOut",
    "AdminPersonPatchRequest",
    "AdminResetPasswordRequest",
    "AdminSetRoleRequest",
]
