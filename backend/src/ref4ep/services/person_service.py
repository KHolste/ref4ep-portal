"""Personen-Verwaltung und Authentifizierung.

Schreibende Methoden auf Plattformrolle ``admin`` beschränkt; eigene
Operationen (``change_password``) sind ausgenommen. Audit-Pflicht
über den optional injizierten ``AuditLogger``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ref4ep.domain.models import PLATFORM_ROLES, Person
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.auth import (
    MIN_PASSWORD_LEN,
    hash_password,
    needs_rehash,
    verify_password,
)
from ref4ep.services.permissions import can_admin


class EmailAlreadyExists(ValueError):
    """E-Mail ist bereits an einen anderen Account vergeben."""


def _norm_email(email: str) -> str:
    return email.strip().lower()


def _validate_email_shape(email: str) -> None:
    if not email:
        raise ValueError("E-Mail darf nicht leer sein.")
    if "@" not in email:
        raise ValueError("E-Mail muss ein '@' enthalten.")
    local, _, domain = email.rpartition("@")
    if not local or "." not in domain:
        raise ValueError("E-Mail ist nicht gültig.")


class PersonService:
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
            raise PermissionError("Nur Admin darf diese Operation ausführen.")

    # ---- read -----------------------------------------------------------

    def list_persons(self, *, include_deleted: bool = False) -> list[Person]:
        stmt = select(Person).order_by(Person.email)
        if not include_deleted:
            stmt = stmt.where(Person.is_deleted.is_(False))
        return list(self.session.scalars(stmt))

    def get_by_email(self, email: str) -> Person | None:
        stmt = select(Person).where(
            Person.email == _norm_email(email), Person.is_deleted.is_(False)
        )
        return self.session.scalars(stmt).first()

    def get_by_id(self, person_id: str) -> Person | None:
        return self.session.get(Person, person_id)

    # ---- authenticate ---------------------------------------------------

    def authenticate(self, email: str, password: str) -> Person | None:
        person = self.get_by_email(email)
        if person is None or not person.is_active or person.is_deleted:
            return None
        if not verify_password(password, person.password_hash):
            return None
        if needs_rehash(person.password_hash):
            person.password_hash = hash_password(password)
            self.session.flush()
        return person

    # ---- write (admin) --------------------------------------------------

    def create(
        self,
        *,
        email: str,
        display_name: str,
        partner_id: str,
        password: str,
        platform_role: str = "member",
    ) -> Person:
        self._require_admin()
        if platform_role not in PLATFORM_ROLES:
            raise ValueError(f"Unbekannte Plattformrolle: {platform_role}")
        person = Person(
            email=_norm_email(email),
            display_name=display_name,
            partner_id=partner_id,
            password_hash=hash_password(password),
            platform_role=platform_role,
            is_active=True,
            must_change_password=True,
        )
        self.session.add(person)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "person.create",
                entity_type="person",
                entity_id=person.id,
                after={
                    "email": person.email,
                    "display_name": person.display_name,
                    "partner_id": person.partner_id,
                    "platform_role": person.platform_role,
                    "is_active": person.is_active,
                    "must_change_password": person.must_change_password,
                },
            )
        return person

    def update(
        self,
        person_id: str,
        *,
        display_name: str | None = None,
        partner_id: str | None = None,
        email: str | None = None,
    ) -> Person:
        """Admin-Update von Anzeigename, Partner-Zuordnung und/oder E-Mail.

        E-Mail-Änderung lässt Passwort und ``must_change_password``
        unangetastet. Bestehende Sessions sind ``person_id``-basiert und
        bleiben gültig.
        """
        self._require_admin()
        person = self.get_by_id(person_id)
        if person is None or person.is_deleted:
            raise LookupError(f"Person {person_id} nicht gefunden.")

        before = {
            "display_name": person.display_name,
            "partner_id": person.partner_id,
            "email": person.email,
        }

        if display_name is not None:
            stripped = display_name.strip()
            if not stripped:
                raise ValueError("Anzeigename darf nicht leer sein.")
            person.display_name = stripped
        if partner_id is not None:
            from ref4ep.domain.models import Partner

            target = self.session.get(Partner, partner_id)
            if target is None or target.is_deleted:
                raise LookupError(f"Partner {partner_id} nicht gefunden.")
            person.partner_id = partner_id
        if email is not None:
            normalized = _norm_email(email)
            _validate_email_shape(normalized)
            if normalized != person.email:
                existing = self.get_by_email(normalized)
                if existing is not None and existing.id != person.id:
                    raise EmailAlreadyExists(f"E-Mail {normalized!r} ist bereits vergeben.")
                person.email = normalized

        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise EmailAlreadyExists(f"E-Mail {person.email!r} ist bereits vergeben.") from exc

        if self.audit is not None:
            after = {
                "display_name": person.display_name,
                "partner_id": person.partner_id,
                "email": person.email,
            }
            if after != before:
                self.audit.log(
                    "person.update",
                    entity_type="person",
                    entity_id=person.id,
                    before=before,
                    after=after,
                )
        return person

    def reset_password(self, person_id: str, new_password: str) -> None:
        self._require_admin()
        person = self.get_by_id(person_id)
        if person is None or person.is_deleted:
            raise LookupError(f"Person {person_id} nicht gefunden.")
        person.password_hash = hash_password(new_password)
        person.must_change_password = True
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "person.reset_password",
                entity_type="person",
                entity_id=person.id,
                after={"must_change_password": True},
            )

    def set_role(self, person_id: str, role: str) -> None:
        self._require_admin()
        if role not in PLATFORM_ROLES:
            raise ValueError(f"Unbekannte Plattformrolle: {role}")
        person = self.get_by_id(person_id)
        if person is None or person.is_deleted:
            raise LookupError(f"Person {person_id} nicht gefunden.")
        before = {"platform_role": person.platform_role}
        person.platform_role = role
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "person.set_role",
                entity_type="person",
                entity_id=person.id,
                before=before,
                after={"platform_role": person.platform_role},
            )

    def enable(self, person_id: str) -> None:
        self._require_admin()
        person = self.get_by_id(person_id)
        if person is None or person.is_deleted:
            raise LookupError(f"Person {person_id} nicht gefunden.")
        if person.is_active:
            return
        person.is_active = True
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "person.enable",
                entity_type="person",
                entity_id=person.id,
                before={"is_active": False},
                after={"is_active": True},
            )

    def disable(self, person_id: str) -> None:
        self._require_admin()
        person = self.get_by_id(person_id)
        if person is None or person.is_deleted:
            raise LookupError(f"Person {person_id} nicht gefunden.")
        if not person.is_active:
            return
        person.is_active = False
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "person.disable",
                entity_type="person",
                entity_id=person.id,
                before={"is_active": True},
                after={"is_active": False},
            )

    # ---- write (WP-Lead) ------------------------------------------------

    def create_by_wp_lead(
        self,
        *,
        actor_partner_id: str,
        email: str,
        display_name: str,
        password: str,
    ) -> Person:
        """Anlegen einer Person durch eine WP-Lead-Person (Block 0013).

        Server erzwingt:
        - Plattformrolle ``member`` (Lead darf keine Admins erzeugen).
        - Partner gleich dem eigenen Partner der aufrufenden Person —
          ``actor_partner_id`` wird vom Routen-Layer aus dem
          eingeloggten Account bezogen, **nicht** aus dem Request.

        Audit-Aktion: ``person.create_by_wp_lead``. Klartextpasswort
        landet **nicht** im Audit; der Aufrufer erhält es einmalig
        zurück.
        """
        # Mindestpasswort-Schutz schon hier (verhindert eine Person
        # mit triviallem Passwort, falls Routen-Validierung umgangen wird).
        if len(password) < MIN_PASSWORD_LEN:
            raise ValueError(
                f"Initialpasswort muss mindestens {MIN_PASSWORD_LEN} Zeichen lang sein."
            )
        person = Person(
            email=_norm_email(email),
            display_name=display_name,
            partner_id=actor_partner_id,
            password_hash=hash_password(password),
            platform_role="member",
            is_active=True,
            must_change_password=True,
        )
        self.session.add(person)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "person.create_by_wp_lead",
                entity_type="person",
                entity_id=person.id,
                after={
                    "email": person.email,
                    "display_name": person.display_name,
                    "partner_id": person.partner_id,
                    "platform_role": person.platform_role,
                    "is_active": person.is_active,
                    "must_change_password": person.must_change_password,
                },
            )
        return person

    # ---- write (eigene) -------------------------------------------------

    def change_password(self, person_id: str, old: str, new: str) -> None:
        person = self.get_by_id(person_id)
        if person is None or person.is_deleted:
            raise LookupError(f"Person {person_id} nicht gefunden.")
        if len(new) < MIN_PASSWORD_LEN:
            raise ValueError(
                f"Neues Passwort muss mindestens {MIN_PASSWORD_LEN} Zeichen lang sein."
            )
        if not verify_password(old, person.password_hash):
            raise PermissionError("Altes Passwort ist falsch.")
        person.password_hash = hash_password(new)
        person.must_change_password = False
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "person.change_password",
                entity_type="person",
                entity_id=person.id,
                after={"must_change_password": False},
            )
