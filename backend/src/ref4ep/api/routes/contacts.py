"""Projektweites Kontaktverzeichnis (Block 0053).

``GET /api/contacts`` liefert **allen** eingeloggten Personen die
Kontaktdaten des gesamten Projekts — ausdrücklich unabhängig von der
eigenen Einrichtung und den eigenen Arbeitspaketen. Die Liste führt
gepflegte Partnerkontakte und Portal-Accounts zusammen; die Logik
steckt in ``ContactDirectoryService``.

Zwei Felder bleiben Admins vorbehalten (identisch zur Kontaktpflege
auf der Partner-Detailseite):

- ``internal_note`` wird nur für Admins gefüllt,
- ``include_inactive=true`` wirkt nur für Admins und fällt sonst
  still auf ``False`` zurück (keine 403 — die Seite soll für alle
  funktionieren).

Schreiboperationen gibt es hier bewusst nicht: Kontakte werden
weiterhin über ``/api/partners/{id}/contacts`` durch Admin bzw.
Partner-/WP-Leitung gepflegt.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ref4ep.api.deps import get_auth_context, get_session
from ref4ep.api.schemas import (
    ContactDirectoryEntryOut,
    ContactDirectoryPartnerOut,
    ContactDirectoryWorkpackageOut,
)
from ref4ep.services.contact_directory_service import (
    ContactDirectoryService,
    DirectoryEntry,
)
from ref4ep.services.permissions import AuthContext, can_admin

router = APIRouter(prefix="/api")

SessionDep = Annotated[Session, Depends(get_session)]
AuthDep = Annotated[AuthContext, Depends(get_auth_context)]


def _entry_out(entry: DirectoryEntry, *, include_internal: bool) -> ContactDirectoryEntryOut:
    return ContactDirectoryEntryOut(
        key=entry.key,
        sources=list(entry.sources),
        name=entry.name,
        partner=ContactDirectoryPartnerOut(
            id=entry.partner.id,
            short_name=entry.partner.short_name,
            name=entry.partner.name,
            unit_name=entry.partner.unit_name,
        ),
        title_or_degree=entry.title_or_degree,
        email=entry.email,
        phone=entry.phone,
        function=entry.function,
        organization_unit=entry.organization_unit,
        workpackage_notes=entry.workpackage_notes,
        is_primary_contact=entry.is_primary_contact,
        is_project_lead=entry.is_project_lead,
        is_partner_lead=entry.is_partner_lead,
        is_portal_user=entry.is_portal_user,
        is_active=entry.is_active,
        contact_id=entry.contact_id,
        person_id=entry.person_id,
        internal_note=entry.internal_note if include_internal else None,
        workpackages=[
            ContactDirectoryWorkpackageOut(code=wp.code, title=wp.title, wp_role=wp.wp_role)
            for wp in entry.workpackages
        ],
    )


@router.get("/contacts", response_model=list[ContactDirectoryEntryOut])
def list_contact_directory(
    session: SessionDep,
    auth: AuthDep,
    include_inactive: bool = False,
) -> list[ContactDirectoryEntryOut]:
    is_admin = can_admin(auth.platform_role)
    entries = ContactDirectoryService(session).list_entries(
        include_inactive=include_inactive and is_admin,
    )
    return [_entry_out(e, include_internal=is_admin) for e in entries]
