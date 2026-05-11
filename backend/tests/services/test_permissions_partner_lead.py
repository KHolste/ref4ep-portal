"""Permissions-Helfer für partnerbezogene Projektleitung (Block 0045).

Geprüft wird ausschließlich der neue Pfad in
``services/permissions.py``. Dokument-/WP-/Meilenstein-Permissions
werden in diesem Patch ausdrücklich **nicht** erweitert; passende
Negativtests verhindern Regressionen."""

from __future__ import annotations

from ref4ep.services.permissions import (
    AuthContext,
    MembershipInfo,
    PartnerRoleInfo,
    can_read_document,
    can_release,
    can_write_document,
    is_partner_lead_for,
    partner_lead_partner_ids,
)


def _make_auth(*, partner_roles: list[PartnerRoleInfo] | None = None) -> AuthContext:
    return AuthContext(
        person_id="p",
        email="p@x",
        platform_role="member",
        memberships=[],
        partner_roles=partner_roles or [],
    )


def test_is_partner_lead_for_true_for_matching_partner() -> None:
    auth = _make_auth(partner_roles=[PartnerRoleInfo("part-1", "partner_lead")])
    assert is_partner_lead_for(auth, "part-1") is True


def test_is_partner_lead_for_false_for_other_partner() -> None:
    auth = _make_auth(partner_roles=[PartnerRoleInfo("part-1", "partner_lead")])
    assert is_partner_lead_for(auth, "part-2") is False


def test_is_partner_lead_for_anonymous() -> None:
    assert is_partner_lead_for(None, "part-1") is False


def test_partner_lead_partner_ids_collects_only_partner_lead_role() -> None:
    auth = _make_auth(
        partner_roles=[
            PartnerRoleInfo("a", "partner_lead"),
            PartnerRoleInfo("b", "partner_lead"),
        ]
    )
    assert partner_lead_partner_ids(auth) == {"a", "b"}


def test_partner_lead_does_not_grant_document_read() -> None:
    """Sichtbarkeit von Dokumenten bleibt Membership-basiert. Eine
    Partnerleitung ohne Membership darf das WP-Dokument NICHT lesen."""

    class DummyDoc:
        is_deleted = False
        visibility = "workpackage"
        status = "draft"
        workpackage_id = "wp-1"

    auth = _make_auth(partner_roles=[PartnerRoleInfo("part-1", "partner_lead")])
    assert can_read_document(auth, DummyDoc()) is False


def test_partner_lead_does_not_grant_document_write() -> None:
    class DummyDoc:
        is_deleted = False
        workpackage_id = "wp-1"
        visibility = "workpackage"
        status = "draft"

    auth = _make_auth(partner_roles=[PartnerRoleInfo("part-1", "partner_lead")])
    assert can_write_document(auth, DummyDoc()) is False


def test_partner_lead_does_not_grant_document_release() -> None:
    class DummyDoc:
        is_deleted = False
        workpackage_id = "wp-1"
        visibility = "workpackage"
        status = "in_review"

    auth = _make_auth(partner_roles=[PartnerRoleInfo("part-1", "partner_lead")])
    assert can_release(auth, DummyDoc()) is False


def test_admin_still_passes_all_paths() -> None:
    """Wp-Lead-/Admin-Bestandsverhalten unverändert."""

    class DummyDoc:
        is_deleted = False
        workpackage_id = "wp-1"
        visibility = "workpackage"
        status = "in_review"

    auth = AuthContext(
        person_id="a",
        email="a@x",
        platform_role="admin",
        memberships=[],
        partner_roles=[],
    )
    assert can_read_document(auth, DummyDoc()) is True
    assert can_write_document(auth, DummyDoc()) is True
    assert can_release(auth, DummyDoc()) is True


def test_wp_lead_path_unchanged() -> None:
    """WP-Lead darf das eigene WP-Dokument weiter freigeben — die
    Erweiterung um Partnerleitung darf das nicht verändern."""

    class DummyDoc:
        is_deleted = False
        workpackage_id = "wp-1"
        visibility = "workpackage"
        status = "in_review"

    auth = AuthContext(
        person_id="p",
        email="p@x",
        platform_role="member",
        memberships=[MembershipInfo("wp-1", "WP1", "wp_lead")],
        partner_roles=[],
    )
    assert can_release(auth, DummyDoc()) is True
