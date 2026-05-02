"""Rollen- und Berechtigungs-Helfer.

Sprint-1-Stand: nur die Plattformrolle wird in Routen ausgewertet
(Admin-only-CLI). WP-Rollen sind als Daten gespeichert und über
``is_member_of`` / ``is_wp_lead`` testbar; Routen-Konsumenten folgen
ab Sprint 2.
"""

from __future__ import annotations

from dataclasses import dataclass


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
