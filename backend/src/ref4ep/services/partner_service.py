"""Partner-Verwaltung.

Schreibende Methoden setzen Plattformrolle ``admin`` voraus und
schreiben — sofern ein ``AuditLogger`` injiziert ist — Audit-
Einträge.

Migration 0006: Partnerstammdaten wurden um Kontakt-, Adress-
und Verwaltungsfelder erweitert. Admins dürfen alle Felder
ändern; WP-Leads dürfen über ``update_by_wp_lead`` ausschließlich
die fachlich öffentlichen Felder ihres eigenen Partners
bearbeiten (siehe ``WP_LEAD_FIELDS``).

Block 0007: ``general_email`` wurde wieder entfernt — Kontakt
läuft ausschließlich über ``PartnerContact``.

Block 0008: Personenbezogene Partnerfelder
(``primary_contact_name``, ``contact_email``, ``contact_phone``,
``project_role_note``) sind weg; Adressspalten heißen
``organization_*`` und es gibt eigene Felder für die
bearbeitende Einheit (``unit_name``, ``unit_address_*``,
``unit_address_same_as_organization``).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ref4ep.domain.models import Membership, Partner, Workpackage
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.permissions import can_admin
from ref4ep.services.validators import normalise_text, validate_country_code

# Felder, die sowohl bei Create als auch beim Vergleich für Audit
# berücksichtigt werden. Reihenfolge bestimmt die Reihenfolge in
# Audit-Einträgen.
ADMIN_FIELDS: tuple[str, ...] = (
    "name",
    "short_name",
    "country",
    "website",
    "unit_name",
    "organization_address_line",
    "organization_postal_code",
    "organization_city",
    "organization_country",
    "unit_address_same_as_organization",
    "unit_address_line",
    "unit_postal_code",
    "unit_city",
    "unit_country",
    "is_active",
    "internal_note",
)

# Whitelist für WP-Lead-Edit: alles, was die fachlich-öffentliche
# Außendarstellung des Partners betrifft. Verwaltungsfelder
# (is_active, internal_note), Identitätsfelder (short_name,
# country) und Soft-Delete bleiben Admin-only.
WP_LEAD_FIELDS: tuple[str, ...] = (
    "name",
    "website",
    "unit_name",
    "organization_address_line",
    "organization_postal_code",
    "organization_city",
    "organization_country",
    "unit_address_same_as_organization",
    "unit_address_line",
    "unit_postal_code",
    "unit_city",
    "unit_country",
)

# Spalten, die ISO-3166-1-alpha-2-Validierung bekommen.
COUNTRY_FIELDS: frozenset[str] = frozenset({"country", "organization_country", "unit_country"})


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

    def is_wp_lead_for_partner(self, person_id: str, partner_id: str) -> bool:
        """True, wenn ``person_id`` ein WP-Lead in einem WP ist, das diesen Partner führt."""
        stmt = (
            select(Membership.id)
            .join(Workpackage, Workpackage.id == Membership.workpackage_id)
            .where(
                Membership.person_id == person_id,
                Membership.wp_role == "wp_lead",
                Workpackage.lead_partner_id == partner_id,
                Workpackage.is_deleted.is_(False),
            )
            .limit(1)
        )
        return self.session.scalars(stmt).first() is not None

    # ---- write ----------------------------------------------------------

    def _require_admin(self) -> None:
        if not can_admin(self.role or ""):
            raise PermissionError("Nur Admin darf Partner verändern.")

    def _snapshot(self, partner: Partner, fields: tuple[str, ...]) -> dict[str, object]:
        return {k: getattr(partner, k) for k in fields}

    def create(
        self,
        *,
        name: str,
        short_name: str,
        country: str,
        website: str | None = None,
        unit_name: str | None = None,
        organization_address_line: str | None = None,
        organization_postal_code: str | None = None,
        organization_city: str | None = None,
        organization_country: str | None = None,
        unit_address_same_as_organization: bool = True,
        unit_address_line: str | None = None,
        unit_postal_code: str | None = None,
        unit_city: str | None = None,
        unit_country: str | None = None,
        is_active: bool = True,
        internal_note: str | None = None,
    ) -> Partner:
        self._require_admin()
        validate_country_code(country, "country")
        validate_country_code(organization_country, "organization_country")
        validate_country_code(unit_country, "unit_country")
        partner = Partner(
            name=name,
            short_name=short_name,
            country=country,
            website=normalise_text(website),
            unit_name=normalise_text(unit_name),
            organization_address_line=normalise_text(organization_address_line),
            organization_postal_code=normalise_text(organization_postal_code),
            organization_city=normalise_text(organization_city),
            organization_country=normalise_text(organization_country),
            unit_address_same_as_organization=unit_address_same_as_organization,
            unit_address_line=normalise_text(unit_address_line),
            unit_postal_code=normalise_text(unit_postal_code),
            unit_city=normalise_text(unit_city),
            unit_country=normalise_text(unit_country),
            is_active=is_active,
            internal_note=normalise_text(internal_note),
        )
        self.session.add(partner)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "partner.create",
                entity_type="partner",
                entity_id=partner.id,
                after=self._snapshot(partner, ADMIN_FIELDS),
            )
        return partner

    def _apply_update(
        self,
        partner: Partner,
        fields: dict[str, object],
        allowed: tuple[str, ...],
        *,
        action: str,
    ) -> Partner:
        before = self._snapshot(partner, allowed)
        for key, raw_value in fields.items():
            if key not in allowed:
                continue
            value: object = raw_value
            if isinstance(value, str):
                value = normalise_text(value)
            if key in COUNTRY_FIELDS and (value is None or isinstance(value, str)):
                validate_country_code(value, key)
            setattr(partner, key, value)
        # Wenn Einheitsadresse identisch zur Organisationsadresse sein soll,
        # leeren wir die unit_address_*-Felder defensiv — egal, ob die
        # Whitelist sie enthielt oder nicht. Damit gibt es keine
        # widersprüchliche Anzeige (Flag = true, aber Adressfelder gefüllt).
        if partner.unit_address_same_as_organization:
            for field in (
                "unit_address_line",
                "unit_postal_code",
                "unit_city",
                "unit_country",
            ):
                setattr(partner, field, None)
        self.session.flush()
        if self.audit is not None:
            after = self._snapshot(partner, allowed)
            if after != before:
                self.audit.log(
                    action,
                    entity_type="partner",
                    entity_id=partner.id,
                    before=before,
                    after=after,
                )
        return partner

    def update(self, partner_id: str, **fields: object) -> Partner:
        self._require_admin()
        partner = self.get_by_id(partner_id)
        if partner is None or partner.is_deleted:
            raise LookupError(f"Partner {partner_id} nicht gefunden.")
        return self._apply_update(partner, fields, ADMIN_FIELDS, action="partner.update")

    def update_by_wp_lead(self, partner_id: str, **fields: object) -> Partner:
        """Update, eingeschränkt auf ``WP_LEAD_FIELDS``.

        Voraussetzung: ``self.person_id`` ist ein WP-Lead in einem
        Arbeitspaket, dessen ``lead_partner_id`` dem Partner
        entspricht. Soft-deleted oder fachlich inaktive Partner
        können nicht geändert werden.
        """
        if not self.person_id:
            raise PermissionError("Kein eingeloggter Nutzer.")
        partner = self.get_by_id(partner_id)
        if partner is None or partner.is_deleted:
            raise LookupError(f"Partner {partner_id} nicht gefunden.")
        if not self.is_wp_lead_for_partner(self.person_id, partner_id):
            raise PermissionError("Nur WP-Leads des Partners dürfen ihn bearbeiten.")
        # Felder ausserhalb der Whitelist werden still ignoriert; das ist
        # zugleich die Schutzschicht gegen versehentliches Setzen von
        # short_name/country/internal_note/is_active/is_deleted.
        return self._apply_update(
            partner, fields, WP_LEAD_FIELDS, action="partner.update_by_wp_lead"
        )

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
