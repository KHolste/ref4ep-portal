"""Verwaltung der Projekt-/Kontaktpersonen pro Partner (Block 0007).

Berechtigungsmatrix (in der Route + hier doppelt geprüft):

- ``admin``     darf alle Kontakte aller Partner anlegen,
                bearbeiten, deaktivieren.
- ``wp_lead``   darf Kontakte nur für den eigenen Partner — d. h.
                den ``lead_partner`` eines WPs, in dem die Person
                ``wp_role == "wp_lead"`` ist.
- ``member``    darf nur lesen, soweit sichtbar (siehe
                ``visible_for``).

Hard-Delete gibt es nicht: Kontakte werden über
``is_active = False`` deaktiviert. ``internal_note`` ist
ausschließlich für Admins lesbar/schreibbar.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ref4ep.domain.models import (
    PARTNER_CONTACT_FUNCTIONS,
    PARTNER_CONTACT_VISIBILITIES,
    Partner,
    PartnerContact,
)
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.permissions import can_admin
from ref4ep.services.validators import normalise_text, validate_email

# Felder, die der Service akzeptiert (Reihenfolge bestimmt Audit-Reihenfolge).
WRITABLE_FIELDS: tuple[str, ...] = (
    "name",
    "title_or_degree",
    "email",
    "phone",
    "function",
    "organization_unit",
    "workpackage_notes",
    "is_primary_contact",
    "is_project_lead",
    "visibility",
    "is_active",
    "internal_note",
)

# Felder, die nur Admins schreiben dürfen (Lead darf sie nicht setzen).
ADMIN_ONLY_FIELDS: frozenset[str] = frozenset({"internal_note"})


def _function_allowed(value: str | None) -> bool:
    return value is None or value in PARTNER_CONTACT_FUNCTIONS


class PartnerContactService:
    def __init__(
        self,
        session: Session,
        *,
        role: str | None = None,
        person_id: str | None = None,
        audit: AuditLogger | None = None,
    ) -> None:
        self.session = session
        self.role = role
        self.person_id = person_id
        self.audit = audit

    # ---- Berechtigungs-Helfer ------------------------------------------

    def _is_admin(self) -> bool:
        return can_admin(self.role or "")

    def _is_lead_for(self, partner_id: str) -> bool:
        """Block 0045 — WP-Lead des Lead-Partner-WPs **oder**
        Projektleitung (``partner_lead``) für den Partner."""
        if not self.person_id:
            return False
        return PartnerService(self.session).is_partner_representative(self.person_id, partner_id)

    def can_manage(self, partner_id: str) -> bool:
        return self._is_admin() or self._is_lead_for(partner_id)

    # ---- Lesen ----------------------------------------------------------

    def list_for_partner(
        self, partner_id: str, *, include_inactive: bool = False
    ) -> list[PartnerContact]:
        """Alle Kontakte eines Partners nach Sichtbarkeit der Rolle gefiltert.

        - admin / wp_lead des Partners: sieht alle Kontakte (inkl.
          inaktiver, wenn ``include_inactive=True``).
        - andere Eingeloggte: nur ``is_active`` Kontakte mit
          ``visibility`` ∈ {internal, public}.

        ``visibility = public`` ist im Datenmodell vorbereitet; ein
        eigener öffentlicher Endpoint wird in diesem Block bewusst
        nicht freigeschaltet.
        """
        stmt = (
            select(PartnerContact)
            .where(PartnerContact.partner_id == partner_id)
            .order_by(PartnerContact.name)
        )
        if not include_inactive:
            stmt = stmt.where(PartnerContact.is_active.is_(True))
        if not self.can_manage(partner_id):
            # Member sehen nur intern/öffentlich aktive Kontakte.
            stmt = stmt.where(PartnerContact.visibility.in_(PARTNER_CONTACT_VISIBILITIES))
        return list(self.session.scalars(stmt))

    def get(self, contact_id: str) -> PartnerContact | None:
        return self.session.get(PartnerContact, contact_id)

    # ---- Schreiben ------------------------------------------------------

    def _require_partner_exists(self, partner_id: str) -> Partner:
        partner = self.session.get(Partner, partner_id)
        if partner is None or partner.is_deleted:
            raise LookupError(f"Partner {partner_id} nicht gefunden.")
        return partner

    def _require_can_manage(self, partner_id: str) -> None:
        if not self.can_manage(partner_id):
            raise PermissionError("Nur Admin oder WP-Lead des Partners darf Kontakte verwalten.")

    def _normalise_payload(self, payload: dict[str, object]) -> dict[str, object]:
        """Trim, Validierung, Whitelist-Filter — wirft ValueError bei Verstoß."""
        cleaned: dict[str, object] = {}
        for key, raw in payload.items():
            if key not in WRITABLE_FIELDS:
                continue
            if not self._is_admin() and key in ADMIN_ONLY_FIELDS:
                # Lead-Whitelist: silent ignore — sonst würde ein versehentliches
                # Mitschicken vom Frontend zur 422 führen.
                continue
            value: object = raw
            if isinstance(value, str):
                value = normalise_text(value)
            if key == "email":
                validate_email(value if isinstance(value, str) else None, "email")
            if key == "function" and not _function_allowed(
                value if isinstance(value, str) or value is None else None
            ):
                raise ValueError(
                    "function: ungültiger Wert — bitte aus der Auswahlliste verwenden."
                )
            if key == "visibility" and value not in PARTNER_CONTACT_VISIBILITIES:
                raise ValueError("visibility: erwartet 'internal' oder 'public'.")
            cleaned[key] = value
        return cleaned

    def _snapshot(self, contact: PartnerContact) -> dict[str, object]:
        return {k: getattr(contact, k) for k in WRITABLE_FIELDS} | {
            "partner_id": contact.partner_id,
        }

    def create(self, *, partner_id: str, **fields: object) -> PartnerContact:
        self._require_partner_exists(partner_id)
        self._require_can_manage(partner_id)
        cleaned = self._normalise_payload(fields)
        if not cleaned.get("name"):
            raise ValueError("name: Pflichtfeld.")
        contact = PartnerContact(partner_id=partner_id)
        for key, value in cleaned.items():
            setattr(contact, key, value)
        # Defaults explizit setzen, falls Aufrufer sie nicht mitschickt.
        if "visibility" not in cleaned:
            contact.visibility = "internal"
        self.session.add(contact)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "partner_contact.create",
                entity_type="partner_contact",
                entity_id=contact.id,
                after=self._snapshot(contact),
            )
        return contact

    def update(self, contact_id: str, **fields: object) -> PartnerContact:
        contact = self.get(contact_id)
        if contact is None:
            raise LookupError(f"Kontakt {contact_id} nicht gefunden.")
        self._require_can_manage(contact.partner_id)
        cleaned = self._normalise_payload(fields)
        before = self._snapshot(contact)
        for key, value in cleaned.items():
            setattr(contact, key, value)
        self.session.flush()
        if self.audit is not None:
            after = self._snapshot(contact)
            if after != before:
                self.audit.log(
                    "partner_contact.update",
                    entity_type="partner_contact",
                    entity_id=contact.id,
                    before=before,
                    after=after,
                )
        return contact

    def deactivate(self, contact_id: str) -> PartnerContact:
        """Soft-Delete via ``is_active = False`` — kein Hard-Delete."""
        contact = self.get(contact_id)
        if contact is None:
            raise LookupError(f"Kontakt {contact_id} nicht gefunden.")
        self._require_can_manage(contact.partner_id)
        if contact.is_active:
            contact.is_active = False
            self.session.flush()
            if self.audit is not None:
                self.audit.log(
                    "partner_contact.deactivate",
                    entity_type="partner_contact",
                    entity_id=contact.id,
                    before={"is_active": True},
                    after={"is_active": False},
                )
        return contact

    def reactivate(self, contact_id: str) -> PartnerContact:
        contact = self.get(contact_id)
        if contact is None:
            raise LookupError(f"Kontakt {contact_id} nicht gefunden.")
        self._require_can_manage(contact.partner_id)
        if not contact.is_active:
            contact.is_active = True
            self.session.flush()
            if self.audit is not None:
                self.audit.log(
                    "partner_contact.reactivate",
                    entity_type="partner_contact",
                    entity_id=contact.id,
                    before={"is_active": False},
                    after={"is_active": True},
                )
        return contact
