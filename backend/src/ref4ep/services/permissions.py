"""Rollen- und Berechtigungs-Helfer.

Sprint-1-Stand: Plattformrolle (admin/member) wird in Routen
ausgewertet, WP-Rollen sind testbar.
Sprint-2-Erweiterung: ``can_read_document`` / ``can_write_document``
für Dokument-Routen. Die Implementierung deckt bereits die volle
MVP-§7-Logik (workpackage / internal / public, draft / released)
ab, damit Sprint 3 sie ohne Anpassung weiterverwenden kann.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ref4ep.domain.models import Document, TestCampaign


@dataclass(frozen=True)
class MembershipInfo:
    workpackage_id: str
    workpackage_code: str
    wp_role: str


@dataclass(frozen=True)
class PartnerRoleInfo:
    """Block 0045 — passiv gehaltene Partnerrolle im AuthContext.

    Aktuell ist ``role`` ausschließlich ``partner_lead`` (UI-Label
    „Projektleitung"). Wirkung auf Permissions wird über die Helper
    ``is_partner_lead_for`` / Service-Pfade gesteuert; das Vorhalten
    der Liste im AuthContext spart DB-Roundtrips in heißen Pfaden."""

    partner_id: str
    role: str


@dataclass
class AuthContext:
    person_id: str
    email: str
    platform_role: str
    memberships: list[MembershipInfo]
    # Block 0045 — Liste der Partnerrollen der eingeloggten Person.
    partner_roles: list[PartnerRoleInfo] = field(default_factory=list)


def can_admin(role: str) -> bool:
    return role == "admin"


def is_member_of(auth: AuthContext, workpackage_id: str) -> bool:
    return any(m.workpackage_id == workpackage_id for m in auth.memberships)


def is_wp_lead(auth: AuthContext, workpackage_id: str) -> bool:
    return any(
        m.workpackage_id == workpackage_id and m.wp_role == "wp_lead" for m in auth.memberships
    )


def is_partner_lead_for(auth: AuthContext | None, partner_id: str) -> bool:
    """True, wenn der eingeloggte Account Partnerleitung
    (``partner_lead``) für den genannten Partner ist.

    Wirkungsbereich (Block 0045): Personen- und Partnerstammdaten-
    Verwaltung des eigenen Partners. **Erweitert ausdrücklich nicht**
    Lese-/Schreibrechte auf Dokumente, WPs, Meilensteine oder
    Testkampagnen — diese Pfade folgen weiter ``Membership`` /
    ``can_admin``.
    """
    if auth is None:
        return False
    return any(
        pr.partner_id == partner_id and pr.role == "partner_lead" for pr in auth.partner_roles
    )


def partner_lead_partner_ids(auth: AuthContext | None) -> set[str]:
    """Set der Partner-IDs, für die der Account Projektleitung ist."""
    if auth is None:
        return set()
    return {pr.partner_id for pr in auth.partner_roles if pr.role == "partner_lead"}


# --------------------------------------------------------------------------- #
# Dokument-Berechtigungen (Sprint 2)                                          #
# --------------------------------------------------------------------------- #


def can_read_document(auth: AuthContext | None, document: Document) -> bool:
    """Volle MVP-§7-Lesbarkeit (Sprint 2 nutzt nur die ersten Zweige).

    Block 0035: ``document.workpackage_id`` darf NULL sein
    (Projektbibliothek). Der WP-Membership-Pfad greift dann nicht;
    Admins und ``visibility=internal``/``public``-Pfade bleiben aktiv.
    """
    if document.is_deleted:
        return False
    # 1. Öffentlich freigegeben — auch anonym (Sprint 4 aktiviert das Frontend).
    if document.visibility == "public" and document.status == "released":
        return True
    if auth is None:
        return False
    # 2. Admin
    if can_admin(auth.platform_role):
        return True
    # 3. Mitglied des Workpackages → workpackage / internal sichtbar
    if document.workpackage_id is not None and is_member_of(auth, document.workpackage_id):
        if document.visibility in ("workpackage", "internal"):
            return True
    # 4. Eingeloggt → internal sichtbar
    if document.visibility == "internal":
        return True
    return False


def can_write_document(auth: AuthContext | None, document: Document) -> bool:
    """Wer darf Metadaten ändern bzw. neue Versionen hochladen (Sprint 2).

    Block 0035: bei ``workpackage_id IS NULL`` (Projektbibliothek) ist
    ausschließlich Admin schreibberechtigt.
    """
    if auth is None or document.is_deleted:
        return False
    if can_admin(auth.platform_role):
        return True
    if document.workpackage_id is None:
        return False
    return is_member_of(auth, document.workpackage_id)


# --------------------------------------------------------------------------- #
# Sprint 3 — Lifecycle-Berechtigungen                                         #
# --------------------------------------------------------------------------- #


def can_set_status(auth: AuthContext | None, document: Document) -> bool:
    """draft ↔ in_review: WP-Mitglied oder Admin."""
    return can_write_document(auth, document)


def can_release(auth: AuthContext | None, document: Document) -> bool:
    """release / re-release: WP-Lead oder Admin.

    Block 0035: bei ``workpackage_id IS NULL`` ist die WP-Lead-Schiene
    nicht definiert — nur Admin darf freigeben."""
    if auth is None or document.is_deleted:
        return False
    if can_admin(auth.platform_role):
        return True
    if document.workpackage_id is None:
        return False
    return is_wp_lead(auth, document.workpackage_id)


def can_unrelease(auth: AuthContext | None) -> bool:
    """released → draft: ausschließlich Admin."""
    if auth is None:
        return False
    return can_admin(auth.platform_role)


def can_set_visibility(auth: AuthContext | None, document: Document, *, to: str) -> bool:
    """Sichtbarkeit ändern: WP-Mitglied oder Admin; public nur WP-Lead/Admin.

    Block 0035: bei ``workpackage_id IS NULL`` ist nur Admin
    schreibberechtigt."""
    if auth is None or document.is_deleted:
        return False
    if can_admin(auth.platform_role):
        return True
    if document.workpackage_id is None:
        return False
    if to == "public":
        return is_wp_lead(auth, document.workpackage_id)
    return is_member_of(auth, document.workpackage_id)


def can_soft_delete_document(auth: AuthContext | None) -> bool:
    """Soft-Delete eines Dokuments: ausschließlich Admin."""
    if auth is None:
        return False
    return can_admin(auth.platform_role)


def can_comment_document(auth: AuthContext | None, document: Document) -> bool:
    """Kommentar zu einem Dokument anlegen.

    - Freigegebene Dokumente: jedes Konsortiumsmitglied (eingeloggt).
    - Nicht freigegebene Dokumente: WP-Mitglied oder Admin
      (gleiche Schwelle wie Schreibrecht auf das Dokument).
    """
    if auth is None or document.is_deleted:
        return False
    if can_admin(auth.platform_role):
        return True
    if document.status == "released":
        return True
    if document.workpackage_id is None:
        return False
    return is_member_of(auth, document.workpackage_id)


def can_view_audit_log(auth: AuthContext | None) -> bool:
    if auth is None:
        return False
    return can_admin(auth.platform_role)


# --------------------------------------------------------------------------- #
# Block 0028 — Testkampagnen-Beteiligung                                      #
# --------------------------------------------------------------------------- #


def is_campaign_participant(auth: AuthContext | None, campaign: TestCampaign) -> bool:
    """Wahr, wenn der Aufrufer als Participant in der Kampagne eingetragen
    ist. Admin gilt zusätzlich, weil er ohnehin überall schreiben darf.

    Nutzung u. a. für Foto-Uploads (Block 0028) und Kampagnennotizen
    (Block 0029): „darf in dieser Kampagne aktiv beitragen".
    """
    if auth is None:
        return False
    if can_admin(auth.platform_role):
        return True
    return any(link.person_id == auth.person_id for link in campaign.participant_links)
