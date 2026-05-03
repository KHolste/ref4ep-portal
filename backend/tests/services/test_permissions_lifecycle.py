"""Lifecycle-Berechtigungs-Helper."""

from __future__ import annotations

from types import SimpleNamespace

from ref4ep.services.permissions import (
    AuthContext,
    MembershipInfo,
    can_release,
    can_set_status,
    can_set_visibility,
    can_unrelease,
    can_view_audit_log,
)


def _doc(workpackage_id: str = "wp-1") -> SimpleNamespace:
    return SimpleNamespace(
        id="d1",
        workpackage_id=workpackage_id,
        is_deleted=False,
    )


def _auth(*, role: str = "member", wp_role: str | None = None) -> AuthContext:
    memberships = (
        [MembershipInfo(workpackage_id="wp-1", workpackage_code="WP1", wp_role=wp_role)]
        if wp_role
        else []
    )
    return AuthContext(person_id="p", email="p@x", platform_role=role, memberships=memberships)


def test_can_set_status_member() -> None:
    assert can_set_status(_auth(wp_role="wp_member"), _doc()) is True


def test_can_set_status_no_membership() -> None:
    assert can_set_status(_auth(), _doc()) is False


def test_can_release_member_false_lead_true() -> None:
    assert can_release(_auth(wp_role="wp_member"), _doc()) is False
    assert can_release(_auth(wp_role="wp_lead"), _doc()) is True


def test_can_release_admin_without_membership() -> None:
    assert can_release(_auth(role="admin"), _doc()) is True


def test_can_unrelease_admin_only() -> None:
    assert can_unrelease(_auth(role="admin")) is True
    assert can_unrelease(_auth(wp_role="wp_lead")) is False
    assert can_unrelease(None) is False


def test_can_set_visibility_public_requires_lead() -> None:
    assert can_set_visibility(_auth(wp_role="wp_member"), _doc(), to="public") is False
    assert can_set_visibility(_auth(wp_role="wp_lead"), _doc(), to="public") is True
    assert can_set_visibility(_auth(role="admin"), _doc(), to="public") is True


def test_can_set_visibility_internal_member_ok() -> None:
    assert can_set_visibility(_auth(wp_role="wp_member"), _doc(), to="internal") is True


def test_can_view_audit_log_admin_only() -> None:
    assert can_view_audit_log(_auth(role="admin")) is True
    assert can_view_audit_log(_auth(wp_role="wp_lead")) is False
    assert can_view_audit_log(None) is False
