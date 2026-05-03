"""Partner-Verwaltung.

Schreibende Methoden setzen Plattformrolle ``admin`` voraus und
schreiben — sofern ein ``AuditLogger`` injiziert ist — Audit-
Einträge.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ref4ep.domain.models import Partner
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.permissions import can_admin


class PartnerService:
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

    # ---- read -----------------------------------------------------------

    def list_partners(self, *, include_deleted: bool = False) -> list[Partner]:
        stmt = select(Partner).order_by(Partner.short_name)
        if not include_deleted:
            stmt = stmt.where(Partner.is_deleted.is_(False))
        return list(self.session.scalars(stmt))

    def get_by_short_name(self, short_name: str) -> Partner | None:
        stmt = select(Partner).where(
            Partner.short_name == short_name, Partner.is_deleted.is_(False)
        )
        return self.session.scalars(stmt).first()

    def get_by_id(self, partner_id: str) -> Partner | None:
        return self.session.get(Partner, partner_id)

    # ---- write ----------------------------------------------------------

    def _require_admin(self) -> None:
        if not can_admin(self.role or ""):
            raise PermissionError("Nur Admin darf Partner verändern.")

    def create(
        self,
        *,
        name: str,
        short_name: str,
        country: str,
        website: str | None = None,
    ) -> Partner:
        self._require_admin()
        partner = Partner(
            name=name,
            short_name=short_name,
            country=country,
            website=website,
        )
        self.session.add(partner)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "partner.create",
                entity_type="partner",
                entity_id=partner.id,
                after={
                    "name": partner.name,
                    "short_name": partner.short_name,
                    "country": partner.country,
                    "website": partner.website,
                },
            )
        return partner

    def update(self, partner_id: str, **fields) -> Partner:
        self._require_admin()
        partner = self.get_by_id(partner_id)
        if partner is None or partner.is_deleted:
            raise LookupError(f"Partner {partner_id} nicht gefunden.")
        before = {k: getattr(partner, k) for k in ("name", "short_name", "country", "website")}
        for key, value in fields.items():
            if key in {"name", "short_name", "country", "website"}:
                setattr(partner, key, value)
        self.session.flush()
        if self.audit is not None:
            after = {k: getattr(partner, k) for k in ("name", "short_name", "country", "website")}
            if after != before:
                self.audit.log(
                    "partner.update",
                    entity_type="partner",
                    entity_id=partner.id,
                    before=before,
                    after=after,
                )
        return partner

    def soft_delete(self, partner_id: str) -> None:
        self._require_admin()
        partner = self.get_by_id(partner_id)
        if partner is None or partner.is_deleted:
            return
        partner.is_deleted = True
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "partner.delete",
                entity_type="partner",
                entity_id=partner.id,
                before={"is_deleted": False},
                after={"is_deleted": True},
            )
