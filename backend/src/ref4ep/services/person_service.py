"""Personen-Verwaltung und Authentifizierung.

Schreibende Methoden auf Plattformrolle ``admin`` beschränkt; eigene
Operationen (``change_password``) sind ausgenommen.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ref4ep.domain.models import PLATFORM_ROLES, Person
from ref4ep.services.auth import (
    MIN_PASSWORD_LEN,
    hash_password,
    needs_rehash,
    verify_password,
)
from ref4ep.services.permissions import can_admin


def _norm_email(email: str) -> str:
    return email.strip().lower()


class PersonService:
    def __init__(
        self,
        session: Session,
        *,
        role: str | None = None,
        person_id: str | None = None,
    ) -> None:
        self.session = session
        self.role = role
        self.person_id = person_id

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
        # TODO Sprint 3: audit_logger.log_action("person.create", person.id, ...)
        return person

    def reset_password(self, person_id: str, new_password: str) -> None:
        self._require_admin()
        person = self.get_by_id(person_id)
        if person is None or person.is_deleted:
            raise LookupError(f"Person {person_id} nicht gefunden.")
        person.password_hash = hash_password(new_password)
        person.must_change_password = True
        self.session.flush()
        # TODO Sprint 3: audit_logger.log_action("person.reset_password", person.id, ...)

    def set_role(self, person_id: str, role: str) -> None:
        self._require_admin()
        if role not in PLATFORM_ROLES:
            raise ValueError(f"Unbekannte Plattformrolle: {role}")
        person = self.get_by_id(person_id)
        if person is None or person.is_deleted:
            raise LookupError(f"Person {person_id} nicht gefunden.")
        person.platform_role = role
        self.session.flush()
        # TODO Sprint 3: audit_logger.log_action("person.set_role", person.id, ...)

    def enable(self, person_id: str) -> None:
        self._require_admin()
        person = self.get_by_id(person_id)
        if person is None or person.is_deleted:
            raise LookupError(f"Person {person_id} nicht gefunden.")
        person.is_active = True
        self.session.flush()

    def disable(self, person_id: str) -> None:
        self._require_admin()
        person = self.get_by_id(person_id)
        if person is None or person.is_deleted:
            raise LookupError(f"Person {person_id} nicht gefunden.")
        person.is_active = False
        self.session.flush()

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
        # TODO Sprint 3: audit_logger.log_action("person.change_password", person.id, ...)
