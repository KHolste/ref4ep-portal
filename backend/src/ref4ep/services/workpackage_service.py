"""Workpackage- und Mitgliedschafts-Verwaltung."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ref4ep.domain.models import (
    WORKPACKAGE_STATUSES,
    WP_ROLES,
    Membership,
    Partner,
    Person,
    Workpackage,
)
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.permissions import can_admin
from ref4ep.services.validators import normalise_text

# Felder, die über ``update_status`` gesetzt werden können.
# Block 0009: Cockpit-Felder. Block 0027: Zeitplan-Felder ergänzt.
WP_STATUS_FIELDS: tuple[str, ...] = (
    "status",
    "summary",
    "next_steps",
    "open_issues",
    "start_date",
    "end_date",
)


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

    # ---- Cockpit (Block 0009) ------------------------------------------

    def is_wp_lead(self, person_id: str, workpackage_id: str) -> bool:
        """True, wenn ``person_id`` als ``wp_lead`` in diesem WP eingetragen ist."""
        stmt = (
            select(Membership.id)
            .where(
                Membership.person_id == person_id,
                Membership.workpackage_id == workpackage_id,
                Membership.wp_role == "wp_lead",
            )
            .limit(1)
        )
        return self.session.scalars(stmt).first() is not None

    def update_status(self, workpackage_id: str, **fields: object) -> Workpackage:
        """Aktualisiert die Cockpit-Felder eines Arbeitspakets.

        Berechtigung: ``admin`` darf jedes WP, ``wp_lead`` darf nur
        eigene WPs (lt. Membership). Member ohne Lead-Rolle und
        anonyme Aufrufer werden mit ``PermissionError`` abgewiesen.
        Audit-Log wird geschrieben, wenn sich tatsächlich etwas
        ändert.
        """
        wp = self.get_by_id(workpackage_id)
        if wp is None or wp.is_deleted:
            raise LookupError(f"Workpackage {workpackage_id} nicht gefunden.")
        is_admin = can_admin(self.role or "")
        is_lead = bool(self.person_id) and self.is_wp_lead(self.person_id, workpackage_id)
        if not (is_admin or is_lead):
            raise PermissionError(
                "Nur Admin oder WP-Lead dieses Arbeitspakets darf den Status ändern."
            )

        before = {k: getattr(wp, k) for k in WP_STATUS_FIELDS}
        for key, raw in fields.items():
            if key not in WP_STATUS_FIELDS:
                continue
            value: object = raw
            # Datumsfelder (date | None) bewusst nicht durch
            # ``normalise_text`` schicken — sie sind keine Strings.
            if isinstance(value, str) and key not in ("start_date", "end_date"):
                value = normalise_text(value)
            if key == "status":
                if value not in WORKPACKAGE_STATUSES:
                    raise ValueError(
                        f"status: ungültiger Wert {raw!r} — "
                        f"erlaubt: {', '.join(WORKPACKAGE_STATUSES)}"
                    )
            setattr(wp, key, value)

        # Zeitplan-Konsistenz (Block 0027): wenn beide Werte gesetzt
        # sind, muss ``end_date`` ≥ ``start_date`` sein. Einzelne
        # Nullwerte sind erlaubt (z. B. nur Start, Ende offen).
        if wp.start_date is not None and wp.end_date is not None and wp.end_date < wp.start_date:
            raise ValueError("end_date muss am oder nach start_date liegen.")

        self.session.flush()
        if self.audit is not None:
            after = {k: getattr(wp, k) for k in WP_STATUS_FIELDS}
            if after != before:
                self.audit.log(
                    "workpackage.update_status",
                    entity_type="workpackage",
                    entity_id=wp.id,
                    before=before,
                    after=after,
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

    # ---- WP-Lead-Mitgliedschaftsverwaltung (Block 0013) ---------------

    def list_lead_workpackages(self, person_id: str) -> list[Workpackage]:
        """Alle nicht-gelöschten Workpackages, in denen ``person_id`` wp_lead ist."""
        stmt = (
            select(Workpackage)
            .join(Membership, Membership.workpackage_id == Workpackage.id)
            .where(
                Membership.person_id == person_id,
                Membership.wp_role == "wp_lead",
                Workpackage.is_deleted.is_(False),
            )
            .order_by(Workpackage.sort_order, Workpackage.code)
        )
        return list(self.session.scalars(stmt))

    def add_membership_by_wp_lead(
        self,
        *,
        actor_person_id: str,
        actor_partner_id: str,
        workpackage_id: str,
        target_person_id: str,
        wp_role: str = "wp_member",
    ) -> Membership:
        """Fügt eine Person des eigenen Partners dem eigenen WP hinzu.

        Schutz auf Service-Ebene (zusätzlich zur Routen-Prüfung):
        - Aufrufer muss in diesem WP ``wp_lead`` sein.
        - Zielperson muss zum gleichen Partner gehören wie der Aufrufer.
        - ``wp_role`` ∈ {wp_member, wp_lead}.
        """
        if wp_role not in WP_ROLES:
            raise ValueError(f"Unbekannte WP-Rolle: {wp_role}")
        if not self.is_wp_lead(actor_person_id, workpackage_id):
            raise PermissionError("Nur WP-Lead dieses Arbeitspakets darf Mitglieder hinzufügen.")
        target = self.session.get(Person, target_person_id)
        if target is None or target.is_deleted:
            raise LookupError(f"Person {target_person_id} nicht gefunden.")
        if target.partner_id != actor_partner_id:
            raise PermissionError("WP-Lead darf nur Personen des eigenen Partners hinzufügen.")
        existing = self.session.scalars(
            select(Membership).where(
                Membership.person_id == target_person_id,
                Membership.workpackage_id == workpackage_id,
            )
        ).first()
        if existing is not None:
            raise ValueError("Mitgliedschaft existiert bereits.")
        membership = Membership(
            person_id=target_person_id,
            workpackage_id=workpackage_id,
            wp_role=wp_role,
        )
        self.session.add(membership)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "membership.add_by_wp_lead",
                entity_type="membership",
                entity_id=membership.id,
                after={
                    "person_id": membership.person_id,
                    "workpackage_id": membership.workpackage_id,
                    "wp_role": membership.wp_role,
                    "actor_person_id": actor_person_id,
                },
            )
        return membership

    def set_membership_role_by_wp_lead(
        self,
        *,
        actor_person_id: str,
        workpackage_id: str,
        target_person_id: str,
        wp_role: str,
    ) -> Membership:
        """Rolle einer Mitgliedschaft im eigenen WP ändern.

        Sicherheits-Constraint: ein WP muss mindestens einen
        ``wp_lead`` behalten. Der letzte verbliebene Lead darf sich
        nicht selbst herabstufen — sonst gäbe es keinen Lead mehr,
        der das WP weiter verwalten könnte.
        """
        if wp_role not in WP_ROLES:
            raise ValueError(f"Unbekannte WP-Rolle: {wp_role}")
        if not self.is_wp_lead(actor_person_id, workpackage_id):
            raise PermissionError("Nur WP-Lead dieses Arbeitspakets darf Rollen ändern.")
        membership = self.session.scalars(
            select(Membership).where(
                Membership.person_id == target_person_id,
                Membership.workpackage_id == workpackage_id,
            )
        ).first()
        if membership is None:
            raise LookupError("Mitgliedschaft nicht gefunden.")
        if membership.wp_role == wp_role:
            return membership
        # Mindestens ein wp_lead muss bleiben.
        if membership.wp_role == "wp_lead" and wp_role != "wp_lead":
            other_leads = self.session.scalars(
                select(Membership.id).where(
                    Membership.workpackage_id == workpackage_id,
                    Membership.wp_role == "wp_lead",
                    Membership.person_id != target_person_id,
                )
            ).first()
            if other_leads is None:
                raise ValueError(
                    "Letzter WP-Lead darf nicht herabgestuft werden — bitte zuerst "
                    "eine andere Person zum wp_lead machen."
                )
        before = {"wp_role": membership.wp_role}
        membership.wp_role = wp_role
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "membership.set_role_by_wp_lead",
                entity_type="membership",
                entity_id=membership.id,
                before=before,
                after={
                    "wp_role": membership.wp_role,
                    "actor_person_id": actor_person_id,
                },
            )
        return membership

    def remove_membership_by_wp_lead(
        self,
        *,
        actor_person_id: str,
        workpackage_id: str,
        target_person_id: str,
    ) -> None:
        """Entfernt eine Mitgliedschaft aus dem eigenen WP.

        Person bleibt erhalten (kein Hard-Delete, keine Deaktivierung).
        Wenn die Mitgliedschaft nicht existiert, ist die Operation
        idempotent (kein Fehler).
        Letzter wp_lead darf sich nicht selbst entfernen — sonst stünde
        das WP ohne Lead da.
        """
        if not self.is_wp_lead(actor_person_id, workpackage_id):
            raise PermissionError("Nur WP-Lead dieses Arbeitspakets darf Mitglieder entfernen.")
        membership = self.session.scalars(
            select(Membership).where(
                Membership.person_id == target_person_id,
                Membership.workpackage_id == workpackage_id,
            )
        ).first()
        if membership is None:
            return
        if membership.wp_role == "wp_lead":
            other_leads = self.session.scalars(
                select(Membership.id).where(
                    Membership.workpackage_id == workpackage_id,
                    Membership.wp_role == "wp_lead",
                    Membership.person_id != target_person_id,
                )
            ).first()
            if other_leads is None:
                raise ValueError(
                    "Letzter WP-Lead darf nicht entfernt werden — bitte zuerst "
                    "eine andere Person zum wp_lead machen."
                )
        snapshot = {
            "person_id": membership.person_id,
            "workpackage_id": membership.workpackage_id,
            "wp_role": membership.wp_role,
            "actor_person_id": actor_person_id,
        }
        membership_id = membership.id
        self.session.delete(membership)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "membership.remove_by_wp_lead",
                entity_type="membership",
                entity_id=membership_id,
                before=snapshot,
            )
