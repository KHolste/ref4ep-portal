"""Rollen- und Berechtigungs-Helfer.

Sprint-1-Stand: Plattformrolle (admin/member) wird in Routen
ausgewertet, WP-Rollen sind testbar.
Sprint-2-Erweiterung: ``can_read_document`` / ``can_write_document``
für Dokument-Routen. Die Implementierung deckt bereits die volle
MVP-§7-Logik (workpackage / internal / public, draft / released)
ab, damit Sprint 3 sie ohne Anpassung weiterverwenden kann.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ref4ep.domain.models import Document


@dataclass(frozen=True)
class MembershipInfo:
    workpackage_id: str
    workpackage_code: str
    wp_role: str


@dataclass
class AuthContext:
    person_id: str
    email: str
    platform_role: str
    memberships: list[MembershipInfo]


def can_admin(role: str) -> bool:
    return role == "admin"


def is_member_of(auth: AuthContext, workpackage_id: str) -> bool:
    return any(m.workpackage_id == workpackage_id for m in auth.memberships)


def is_wp_lead(auth: AuthContext, workpackage_id: str) -> bool:
    return any(
        m.workpackage_id == workpackage_id and m.wp_role == "wp_lead" for m in auth.memberships
    )


# --------------------------------------------------------------------------- #
# Dokument-Berechtigungen (Sprint 2)                                          #
# --------------------------------------------------------------------------- #


def can_read_document(auth: AuthContext | None, document: Document) -> bool:
    """Volle MVP-§7-Lesbarkeit (Sprint 2 nutzt nur die ersten Zweige)."""
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
    if is_member_of(auth, document.workpackage_id):
        if document.visibility in ("workpackage", "internal"):
            return True
    # 4. Eingeloggt → internal sichtbar
    if document.visibility == "internal":
        return True
    return False


def can_write_document(auth: AuthContext | None, document: Document) -> bool:
    """Wer darf Metadaten ändern bzw. neue Versionen hochladen (Sprint 2)."""
    if auth is None or document.is_deleted:
        return False
    if can_admin(auth.platform_role):
        return True
    return is_member_of(auth, document.workpackage_id)
