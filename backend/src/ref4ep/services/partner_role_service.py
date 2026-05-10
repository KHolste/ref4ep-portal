"""Partnerbezogene Rollen (Block 0043).

Aktuell ausschließlich ``partner_lead`` (UI-Label „Projektleitung").
Wirkung auf Berechtigungen folgt in den Patches 0045/0046; in 0043 ist
der Service nur Datenebene + Admin-Verwaltung.

Konventionen:
- ``add_partner_role`` ist **idempotent**: ein zweiter Aufruf mit
  gleichen (person, partner, role) liefert den bestehenden Datensatz
  zurück, ohne Fehler. Begründung: Rollenvergabe in der UI ist
  doppelklick-/Race-anfällig; ein 409 wäre für den Bediener
  irreführend. Der Service hält aber das ``created_at`` und den
  Audit-Eintrag des ersten Aufrufs — der zweite Aufruf schreibt
  **keinen** neuen Audit-Eintrag.
- ``remove_partner_role`` wirft ``PartnerRoleNotFoundError``, wenn die
  Rolle nicht existiert. Begründung: das soll im Admin-UI auffallen,
  nicht stillschweigend als „erledigt" erscheinen.
- Nur Admin darf die Schreiboperationen aufrufen — Permission-Check
  liegt in der Route, der Service prüft `_require_admin` aber zur
  Defense-in-Depth.

Audit-Aktionen: ``partner.role.add`` / ``partner.role.remove``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ref4ep.domain.models import PARTNER_ROLES, Partner, PartnerRole, Person
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.permissions import can_admin


class PartnerRoleNotFoundError(LookupError):
    def __init__(self, person_id: str, partner_id: str, role: str) -> None:
        super().__init__(
            f"Rolle {role!r} für Person {person_id} und Partner {partner_id} nicht gefunden."
        )
        self.person_id = person_id
        self.partner_id = partner_id
        self.role = role


class PartnerRoleService:
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

    # ---- read ----------------------------------------------------------

    def list_for_partner(self, partner_id: str) -> list[PartnerRole]:
        stmt = (
            select(PartnerRole)
            .where(PartnerRole.partner_id == partner_id)
            .order_by(PartnerRole.created_at)
        )
        return list(self.session.scalars(stmt))

    def list_for_person(self, person_id: str) -> list[PartnerRole]:
        stmt = (
            select(PartnerRole)
            .where(PartnerRole.person_id == person_id)
            .order_by(PartnerRole.created_at)
        )
        return list(self.session.scalars(stmt))

    def is_partner_lead_for(self, person_id: str, partner_id: str) -> bool:
        stmt = (
            select(PartnerRole.id)
            .where(
                PartnerRole.person_id == person_id,
                PartnerRole.partner_id == partner_id,
                PartnerRole.role == "partner_lead",
            )
            .limit(1)
        )
        return self.session.scalars(stmt).first() is not None

    # ---- helpers -------------------------------------------------------

    def _require_admin(self) -> None:
        if not can_admin(self.role or ""):
            raise PermissionError("Nur Admin darf Partnerrollen verwalten.")

    def _existing(self, *, person_id: str, partner_id: str, role: str) -> PartnerRole | None:
        stmt = select(PartnerRole).where(
            PartnerRole.person_id == person_id,
            PartnerRole.partner_id == partner_id,
            PartnerRole.role == role,
        )
        return self.session.scalars(stmt).first()

    # ---- write ---------------------------------------------------------

    def add_partner_role(
        self,
        *,
        person_id: str,
        partner_id: str,
        role: str = "partner_lead",
        actor_person_id: str,
    ) -> PartnerRole:
        self._require_admin()
        if role not in PARTNER_ROLES:
            raise ValueError(f"Unbekannte Partnerrolle: {role!r}")

        person = self.session.get(Person, person_id)
        if person is None or person.is_deleted:
            raise LookupError(f"Person {person_id} nicht gefunden.")
        partner = self.session.get(Partner, partner_id)
        if partner is None or partner.is_deleted:
            raise LookupError(f"Partner {partner_id} nicht gefunden.")

        existing = self._existing(person_id=person_id, partner_id=partner_id, role=role)
        if existing is not None:
            # Idempotent: gleiche Vergabe doppelt liefert den vorhandenen
            # Eintrag, ohne neuen Audit-Eintrag.
            return existing

        link = PartnerRole(
            id=str(uuid.uuid4()),
            person_id=person_id,
            partner_id=partner_id,
            role=role,
            created_by_person_id=actor_person_id,
        )
        self.session.add(link)
        self.session.flush()

        if self.audit is not None:
            self.audit.log(
                "partner.role.add",
                entity_type="partner_role",
                entity_id=link.id,
                after={
                    "partner_id": partner_id,
                    "partner_short_name": partner.short_name,
                    "person_id": person_id,
                    "person_email": person.email,
                    "role": role,
                },
            )
        return link

    def remove_partner_role(
        self,
        *,
        person_id: str,
        partner_id: str,
        role: str = "partner_lead",
    ) -> None:
        self._require_admin()
        if role not in PARTNER_ROLES:
            raise ValueError(f"Unbekannte Partnerrolle: {role!r}")

        link = self._existing(person_id=person_id, partner_id=partner_id, role=role)
        if link is None:
            raise PartnerRoleNotFoundError(person_id, partner_id, role)

        link_id = link.id
        partner = link.partner
        person = link.person
        self.session.delete(link)
        self.session.flush()

        if self.audit is not None:
            self.audit.log(
                "partner.role.remove",
                entity_type="partner_role",
                entity_id=link_id,
                before={
                    "partner_id": partner_id,
                    "partner_short_name": partner.short_name if partner else None,
                    "person_id": person_id,
                    "person_email": person.email if person else None,
                    "role": role,
                },
            )


__all__ = [
    "PartnerRoleNotFoundError",
    "PartnerRoleService",
]
