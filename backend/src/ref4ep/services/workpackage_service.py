"""Workpackage- und Mitgliedschafts-Verwaltung."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ref4ep.domain.models import WP_ROLES, Membership, Partner, Person, Workpackage
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.permissions import can_admin


def _sort_key_from_code(code: str) -> int:
    """Stabiles ``sort_order`` für ``WP1``, ``WP1.1``, ``WP10.3`` …

    Format-Annahme: ``WP<major>[.<minor>]`` mit kleinen Zahlen. Wir
    ergeben einen Integer-Schlüssel, der numerisch nach Major und
    Minor sortiert.
    """
    rest = code.removeprefix("WP")
    if "." in rest:
        major_str, minor_str = rest.split(".", 1)
        major = int(major_str)
        minor = int(minor_str)
    else:
        major = int(rest)
        minor = 0
    return major * 100 + minor


class WorkpackageService:
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

    # ---- helpers --------------------------------------------------------

    def _require_admin(self) -> None:
        if not can_admin(self.role or ""):
            raise PermissionError("Nur Admin darf Stammdaten verändern.")

    # ---- read -----------------------------------------------------------

    def list_workpackages(self, *, parents_only: bool = False) -> list[Workpackage]:
        stmt = select(Workpackage).where(Workpackage.is_deleted.is_(False))
        if parents_only:
            stmt = stmt.where(Workpackage.parent_workpackage_id.is_(None))
        stmt = stmt.order_by(Workpackage.sort_order, Workpackage.code)
        return list(self.session.scalars(stmt))

    def get_by_code(self, code: str) -> Workpackage | None:
        stmt = select(Workpackage).where(
            Workpackage.code == code, Workpackage.is_deleted.is_(False)
        )
        return self.session.scalars(stmt).first()

    def get_by_id(self, workpackage_id: str) -> Workpackage | None:
        return self.session.get(Workpackage, workpackage_id)

    def get_children(self, parent_id: str) -> list[Workpackage]:
        stmt = (
            select(Workpackage)
            .where(
                Workpackage.parent_workpackage_id == parent_id,
                Workpackage.is_deleted.is_(False),
            )
            .order_by(Workpackage.sort_order, Workpackage.code)
        )
        return list(self.session.scalars(stmt))

    # ---- write ----------------------------------------------------------

    def create(
        self,
        *,
        code: str,
        title: str,
        lead_partner_short_name: str,
        description: str | None = None,
        parent_code: str | None = None,
        sort_order: int | None = None,
    ) -> Workpackage:
        self._require_admin()
        partner = self.session.scalars(
            select(Partner).where(
                Partner.short_name == lead_partner_short_name,
                Partner.is_deleted.is_(False),
            )
        ).first()
        if partner is None:
            raise LookupError(f"Lead-Partner {lead_partner_short_name} nicht gefunden.")

        parent_id: str | None = None
        if parent_code:
            parent = self.get_by_code(parent_code)
            if parent is None:
                raise LookupError(f"Parent-WP {parent_code} nicht gefunden.")
            parent_id = parent.id

        wp = Workpackage(
            code=code,
            title=title,
            description=description,
            parent_workpackage_id=parent_id,
            lead_partner_id=partner.id,
            sort_order=sort_order if sort_order is not None else _sort_key_from_code(code),
        )
        self.session.add(wp)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "workpackage.create",
                entity_type="workpackage",
                entity_id=wp.id,
                after={
                    "code": wp.code,
                    "title": wp.title,
                    "parent_workpackage_id": wp.parent_workpackage_id,
                    "lead_partner_id": wp.lead_partner_id,
                },
            )
        return wp

    # ---- memberships ----------------------------------------------------

    def list_memberships(
        self,
        *,
        person_id: str | None = None,
        workpackage_id: str | None = None,
    ) -> list[Membership]:
        stmt = select(Membership)
        if person_id is not None:
            stmt = stmt.where(Membership.person_id == person_id)
        if workpackage_id is not None:
            stmt = stmt.where(Membership.workpackage_id == workpackage_id)
        return list(self.session.scalars(stmt))

    def add_membership(self, person_id: str, workpackage_id: str, wp_role: str) -> Membership:
        self._require_admin()
        if wp_role not in WP_ROLES:
            raise ValueError(f"Unbekannte WP-Rolle: {wp_role}")
        if self.session.get(Person, person_id) is None:
            raise LookupError(f"Person {person_id} nicht gefunden.")
        if self.session.get(Workpackage, workpackage_id) is None:
            raise LookupError(f"Workpackage {workpackage_id} nicht gefunden.")
        existing = self.session.scalars(
            select(Membership).where(
                Membership.person_id == person_id,
                Membership.workpackage_id == workpackage_id,
            )
        ).first()
        if existing is not None:
            raise ValueError("Mitgliedschaft existiert bereits.")
        membership = Membership(person_id=person_id, workpackage_id=workpackage_id, wp_role=wp_role)
        self.session.add(membership)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "membership.add",
                entity_type="membership",
                entity_id=membership.id,
                after={
                    "person_id": membership.person_id,
                    "workpackage_id": membership.workpackage_id,
                    "wp_role": membership.wp_role,
                },
            )
        return membership

    def set_membership_role(self, person_id: str, workpackage_id: str, wp_role: str) -> Membership:
        """Wechsel der WP-Rolle einer bestehenden Mitgliedschaft."""
        self._require_admin()
        if wp_role not in WP_ROLES:
            raise ValueError(f"Unbekannte WP-Rolle: {wp_role}")
        membership = self.session.scalars(
            select(Membership).where(
                Membership.person_id == person_id,
                Membership.workpackage_id == workpackage_id,
            )
        ).first()
        if membership is None:
            raise LookupError("Mitgliedschaft nicht gefunden.")
        if membership.wp_role == wp_role:
            return membership
        before = {"wp_role": membership.wp_role}
        membership.wp_role = wp_role
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "membership.set_role",
                entity_type="membership",
                entity_id=membership.id,
                before=before,
                after={"wp_role": membership.wp_role},
            )
        return membership

    def remove_membership(self, person_id: str, workpackage_id: str) -> None:
        self._require_admin()
        membership = self.session.scalars(
            select(Membership).where(
                Membership.person_id == person_id,
                Membership.workpackage_id == workpackage_id,
            )
        ).first()
        if membership is None:
            return
        snapshot = {
            "person_id": membership.person_id,
            "workpackage_id": membership.workpackage_id,
            "wp_role": membership.wp_role,
        }
        membership_id = membership.id
        self.session.delete(membership)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "membership.remove",
                entity_type="membership",
                entity_id=membership_id,
                before=snapshot,
            )
