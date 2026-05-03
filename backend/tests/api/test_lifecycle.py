"""API-Tests für Status-, Release-, Unrelease-, Visibility-Endpunkte und Soft-Delete."""

from __future__ import annotations

import io

from fastapi.testclient import TestClient

from tests.conftest import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    MEMBER_EMAIL,
    MEMBER_PASSWORD,
)


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def _login_admin(client: TestClient) -> None:
    r = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text


def _login_member(client: TestClient) -> None:
    r = client.post("/api/auth/login", json={"email": MEMBER_EMAIL, "password": MEMBER_PASSWORD})
    assert r.status_code == 200, r.text


def _create_doc_with_version(client: TestClient, wp_code: str = "WP3") -> tuple[str, int]:
    create = client.post(
        f"/api/workpackages/{wp_code}/documents",
        json={"title": "Lifecycle-Test", "document_type": "report"},
        headers=_csrf(client),
    )
    assert create.status_code == 201, create.text
    doc_id = create.json()["id"]
    upload = client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": ("v1.pdf", io.BytesIO(b"%PDF-1.4 v1"), "application/pdf")},
        data={"change_note": "erste Version"},
        headers=_csrf(client),
    )
    assert upload.status_code == 201, upload.text
    return doc_id, upload.json()["version"]["version_number"]


# ---- status -------------------------------------------------------------


def test_set_status_in_review_as_member(member_client: TestClient, member_in_wp3) -> None:
    doc_id, _ = _create_doc_with_version(member_client)
    r = member_client.post(
        f"/api/documents/{doc_id}/status",
        json={"to": "in_review"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "in_review"


def test_set_status_invalid_value_returns_422(member_client: TestClient, member_in_wp3) -> None:
    doc_id, _ = _create_doc_with_version(member_client)
    r = member_client.post(
        f"/api/documents/{doc_id}/status",
        json={"to": "released"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 422


def test_set_status_anonymous_blocked(client: TestClient, member_in_wp3) -> None:
    """Anonyme Zugriffe werden geblockt — entweder durch CSRF (403) oder Auth (401)."""
    r = client.post("/api/documents/whatever/status", json={"to": "in_review"})
    assert r.status_code in (401, 403)


# ---- release ------------------------------------------------------------


def test_release_requires_wp_lead(member_client: TestClient, member_in_wp3) -> None:
    doc_id, n = _create_doc_with_version(member_client)
    member_client.post(
        f"/api/documents/{doc_id}/status",
        json={"to": "in_review"},
        headers=_csrf(member_client),
    )
    r = member_client.post(
        f"/api/documents/{doc_id}/release",
        json={"version_number": n},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_release_as_wp_lead_succeeds(member_client: TestClient, lead_in_wp3) -> None:
    doc_id, n = _create_doc_with_version(member_client)
    member_client.post(
        f"/api/documents/{doc_id}/status",
        json={"to": "in_review"},
        headers=_csrf(member_client),
    )
    r = member_client.post(
        f"/api/documents/{doc_id}/release",
        json={"version_number": n},
        headers=_csrf(member_client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "released"
    assert body["released_version_id"]
    assert body["released_version"]["version_number"] == n


def test_release_with_unknown_version_404(member_client: TestClient, lead_in_wp3) -> None:
    doc_id, _ = _create_doc_with_version(member_client)
    member_client.post(
        f"/api/documents/{doc_id}/status",
        json={"to": "in_review"},
        headers=_csrf(member_client),
    )
    r = member_client.post(
        f"/api/documents/{doc_id}/release",
        json={"version_number": 99},
        headers=_csrf(member_client),
    )
    assert r.status_code == 404


def test_release_from_draft_409(member_client: TestClient, lead_in_wp3) -> None:
    doc_id, n = _create_doc_with_version(member_client)
    r = member_client.post(
        f"/api/documents/{doc_id}/release",
        json={"version_number": n},
        headers=_csrf(member_client),
    )
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "invalid_status_transition"


# ---- unrelease ----------------------------------------------------------


def test_unrelease_admin_only(admin_person_id, member_client: TestClient, lead_in_wp3) -> None:
    # member_client ist als Lead eingeloggt (lead_in_wp3 macht ihn zum Lead).
    doc_id, n = _create_doc_with_version(member_client)
    member_client.post(
        f"/api/documents/{doc_id}/status",
        json={"to": "in_review"},
        headers=_csrf(member_client),
    )
    member_client.post(
        f"/api/documents/{doc_id}/release",
        json={"version_number": n},
        headers=_csrf(member_client),
    )
    # WP-Lead darf nicht
    r = member_client.post(
        f"/api/documents/{doc_id}/unrelease", json={}, headers=_csrf(member_client)
    )
    assert r.status_code == 403
    # Switch zu Admin durch Re-Login auf demselben Client.
    _login_admin(member_client)
    r = member_client.post(
        f"/api/documents/{doc_id}/unrelease", json={}, headers=_csrf(member_client)
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "draft"
    assert r.json()["released_version_id"] is None


# ---- visibility ---------------------------------------------------------


def test_visibility_member_can_internal(member_client: TestClient, member_in_wp3) -> None:
    doc_id, _ = _create_doc_with_version(member_client)
    r = member_client.post(
        f"/api/documents/{doc_id}/visibility",
        json={"to": "internal"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 200
    assert r.json()["visibility"] == "internal"


def test_visibility_public_requires_lead(member_client: TestClient, member_in_wp3) -> None:
    doc_id, _ = _create_doc_with_version(member_client)
    r = member_client.post(
        f"/api/documents/{doc_id}/visibility",
        json={"to": "public"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_visibility_public_as_lead_ok(member_client: TestClient, lead_in_wp3) -> None:
    doc_id, _ = _create_doc_with_version(member_client)
    r = member_client.post(
        f"/api/documents/{doc_id}/visibility",
        json={"to": "public"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 200
    assert r.json()["visibility"] == "public"


# ---- soft-delete --------------------------------------------------------


def test_soft_delete_admin_only_and_hides_from_list(
    admin_person_id, member_client: TestClient, member_in_wp3
) -> None:
    doc_id, _ = _create_doc_with_version(member_client)
    # Member darf nicht
    r = member_client.delete(f"/api/documents/{doc_id}", headers=_csrf(member_client))
    assert r.status_code == 403
    # Admin re-login auf demselben Client
    _login_admin(member_client)
    r = member_client.delete(f"/api/documents/{doc_id}", headers=_csrf(member_client))
    assert r.status_code == 200, r.text
    # Wieder als Member einloggen, prüfen dass Liste den Eintrag nicht mehr enthält
    _login_member(member_client)
    listed = member_client.get("/api/workpackages/WP3/documents")
    assert all(d["id"] != doc_id for d in listed.json())


# ---- no auto-release ----------------------------------------------------


def test_upload_after_release_does_not_change_release(
    member_client: TestClient, lead_in_wp3
) -> None:
    doc_id, v1 = _create_doc_with_version(member_client)
    member_client.post(
        f"/api/documents/{doc_id}/status",
        json={"to": "in_review"},
        headers=_csrf(member_client),
    )
    rel = member_client.post(
        f"/api/documents/{doc_id}/release",
        json={"version_number": v1},
        headers=_csrf(member_client),
    )
    released_id = rel.json()["released_version_id"]
    # Neue Version hochladen
    upload = member_client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": ("v2.pdf", io.BytesIO(b"%PDF-1.4 v2"), "application/pdf")},
        data={"change_note": "zweite Version"},
        headers=_csrf(member_client),
    )
    assert upload.status_code == 201
    # Detail abrufen
    detail = member_client.get(f"/api/documents/{doc_id}").json()
    assert detail["status"] == "released"
    assert detail["released_version_id"] == released_id
    assert detail["released_version"]["version_number"] == v1
    assert detail["latest_version"]["version_number"] == 2
