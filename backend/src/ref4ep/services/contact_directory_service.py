"""Projektweites Kontaktverzeichnis (Block 0053).

Fachliche Zusage des Blocks: **jede eingeloggte Person sieht die
Kontaktdaten des gesamten Projekts** — nicht nur die der eigenen
Einrichtung oder der Arbeitspakete, in denen sie Mitglied ist. Der
Service ist damit bewusst *nicht* membership-gefiltert; die einzige
Einschränkung ist die zwischen „aktiv" und „deaktiviert" (siehe
unten).

Zwei Datentöpfe werden zu *einer* Liste zusammengeführt:

- ``PartnerContact`` — gepflegte Kontaktpersonen je Partner
  (Block 0007). Enthält Telefon, Funktion, Organisationseinheit.
- ``Person``          — Portal-Accounts. Liefern zusätzlich die
  Arbeitspaket-Mitgliedschaften und die Partnerrolle
  ``partner_lead`` (UI-Label „Projektleitung").

Zusammenführung: Ein Kontakt und ein Account gelten als *dieselbe*
Person, wenn E-Mail (case-insensitiv) **und** Partner übereinstimmen.
Dann entsteht ein einziger Eintrag mit ``sources == ["contact",
"person"]``. Bewusst konservativ: gleiche E-Mail bei
unterschiedlichem Partner deutet auf einen Datenfehler hin und wird
nicht stillschweigend verschmolzen — beide Einträge bleiben sichtbar.

Sichtbarkeit (Block 0053, abgestimmt):

- Alle eingeloggten Personen sehen alle **aktiven** Einträge aller
  Partner.
- ``internal_note`` bleibt Admins vorbehalten (die Route füllt das
  Feld nur für sie) — identisch zur Regel in
  ``partner_contact_service``.
- Deaktivierte Kontakte / Accounts erscheinen nur, wenn ein Admin
  ``include_inactive`` setzt.

Der Service ist rein lesend: Anlegen und Ändern von Kontakten bleibt
unverändert bei ``PartnerContactService`` (Admin bzw. Partner-/
WP-Leitung) auf der Partner-Detailseite.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ref4ep.domain.models import (
    Membership,
    Partner,
    PartnerContact,
    Person,
)

SOURCE_CONTACT = "contact"
SOURCE_PERSON = "person"


@dataclass(frozen=True)
class DirectoryPartner:
    id: str
    short_name: str
    name: str
    unit_name: str | None = None


@dataclass(frozen=True)
class DirectoryWorkpackage:
    code: str
    title: str
    wp_role: str


@dataclass
class DirectoryEntry:
    """Eine Person im Projekt — unabhängig von der Herkunft der Daten."""

    key: str
    sources: list[str]
    name: str
    partner: DirectoryPartner
    title_or_degree: str | None = None
    email: str | None = None
    phone: str | None = None
    function: str | None = None
    organization_unit: str | None = None
    workpackage_notes: str | None = None
    is_primary_contact: bool = False
    is_project_lead: bool = False
    is_partner_lead: bool = False
    is_portal_user: bool = False
    is_active: bool = True
    contact_id: str | None = None
    person_id: str | None = None
    internal_note: str | None = None
    workpackages: list[DirectoryWorkpackage] = field(default_factory=list)


def _email_key(email: str | None) -> str | None:
    value = (email or "").strip().lower()
    return value or None


def _partner_out(partner: Partner) -> DirectoryPartner:
    return DirectoryPartner(
        id=partner.id,
        short_name=partner.short_name,
        name=partner.name,
        unit_name=partner.unit_name,
    )


class ContactDirectoryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ---- Laden ----------------------------------------------------------

    def _partners(self) -> dict[str, Partner]:
        stmt = select(Partner).where(Partner.is_deleted.is_(False))
        return {p.id: p for p in self.session.scalars(stmt)}

    def _contacts(self, *, include_inactive: bool) -> list[PartnerContact]:
        stmt = select(PartnerContact).order_by(PartnerContact.name)
        if not include_inactive:
            stmt = stmt.where(PartnerContact.is_active.is_(True))
        return list(self.session.scalars(stmt))

    def _persons(self, *, include_inactive: bool) -> list[Person]:
        stmt = (
            select(Person)
            .where(Person.is_deleted.is_(False))
            .options(
                selectinload(Person.memberships).selectinload(Membership.workpackage),
                selectinload(Person.partner_roles),
            )
            .order_by(Person.display_name)
        )
        if not include_inactive:
            stmt = stmt.where(Person.is_active.is_(True))
        return list(self.session.scalars(stmt))

    # ---- Abbildung ------------------------------------------------------

    def _entry_from_contact(self, contact: PartnerContact, partner: Partner) -> DirectoryEntry:
        return DirectoryEntry(
            key=f"contact:{contact.id}",
            sources=[SOURCE_CONTACT],
            name=contact.name,
            partner=_partner_out(partner),
            title_or_degree=contact.title_or_degree,
            email=contact.email,
            phone=contact.phone,
            function=contact.function,
            organization_unit=contact.organization_unit,
            workpackage_notes=contact.workpackage_notes,
            is_primary_contact=contact.is_primary_contact,
            is_project_lead=contact.is_project_lead,
            is_active=contact.is_active,
            contact_id=contact.id,
            internal_note=contact.internal_note,
        )

    def _entry_from_person(self, person: Person, partner: Partner) -> DirectoryEntry:
        return DirectoryEntry(
            key=f"person:{person.id}",
            sources=[SOURCE_PERSON],
            name=person.display_name,
            partner=_partner_out(partner),
            email=person.email,
            is_partner_lead=_is_partner_lead(person),
            is_portal_user=True,
            is_active=person.is_active,
            person_id=person.id,
            workpackages=_workpackages_of(person),
        )

    def _merge_person_into(self, entry: DirectoryEntry, person: Person) -> None:
        """Account-Daten auf einen bestehenden Kontakt-Eintrag legen.

        Die gepflegten Kontaktfelder (Telefon, Funktion, …) gewinnen —
        der Account steuert nur bei, was er exklusiv weiß:
        Mitgliedschaften, Partnerrolle, Portal-Zugang.
        """
        entry.sources.append(SOURCE_PERSON)
        entry.person_id = person.id
        entry.is_portal_user = True
        entry.is_partner_lead = _is_partner_lead(person)
        entry.workpackages = _workpackages_of(person)
        if not entry.email:
            entry.email = person.email
        # Ein deaktivierter Account macht einen aktiven Kontakteintrag
        # nicht ungültig — die Person ist weiter erreichbar.
        entry.is_active = entry.is_active or person.is_active

    # ---- Öffentliche API ------------------------------------------------

    def list_entries(self, *, include_inactive: bool = False) -> list[DirectoryEntry]:
        partners = self._partners()
        entries: list[DirectoryEntry] = []
        # (partner_id, email) → Eintrag, für die Zusammenführung.
        by_partner_email: dict[tuple[str, str], DirectoryEntry] = {}

        for contact in self._contacts(include_inactive=include_inactive):
            partner = partners.get(contact.partner_id)
            if partner is None:
                # Kontakt eines gelöschten Partners — nicht anzeigen.
                continue
            entry = self._entry_from_contact(contact, partner)
            entries.append(entry)
            email = _email_key(contact.email)
            if email is not None:
                by_partner_email.setdefault((partner.id, email), entry)

        for person in self._persons(include_inactive=include_inactive):
            partner = partners.get(person.partner_id)
            if partner is None:
                continue
            email = _email_key(person.email)
            existing = by_partner_email.get((partner.id, email)) if email else None
            if existing is not None and existing.person_id is None:
                self._merge_person_into(existing, person)
                continue
            entries.append(self._entry_from_person(person, partner))

        entries.sort(key=lambda e: (e.partner.short_name.lower(), e.name.lower()))
        return entries


def _is_partner_lead(person: Person) -> bool:
    return any(
        role.role == "partner_lead" and role.partner_id == person.partner_id
        for role in person.partner_roles
    )


def _workpackages_of(person: Person) -> list[DirectoryWorkpackage]:
    items = [
        DirectoryWorkpackage(
            code=m.workpackage.code,
            title=m.workpackage.title,
            wp_role=m.wp_role,
        )
        for m in person.memberships
        if m.workpackage is not None
    ]
    items.sort(key=lambda w: w.code)
    return items


__all__ = [
    "SOURCE_CONTACT",
    "SOURCE_PERSON",
    "ContactDirectoryService",
    "DirectoryEntry",
    "DirectoryPartner",
    "DirectoryWorkpackage",
]
