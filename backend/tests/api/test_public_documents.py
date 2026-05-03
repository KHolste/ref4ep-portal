"""Anonyme Public-API: /api/public/documents + /{wp}/{slug} + /download."""

from __future__ import annotations

import hashlib
import io

import pytest
from fastapi.testclient import TestClient


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def _create_doc_with_version(
    client: TestClient, wp_code: str = "WP3", title: str = "Public-Test"
) -> tuple[str, int]:
    create = client.post(
        f"/api/workpackages/{wp_code}/documents",
        json={"title": title, "document_type": "report"},
        headers=_csrf(client),
    )
    assert create.status_code == 201, create.text
    doc_id = create.json()["id"]
    upload = client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": ("v1.pdf", io.BytesIO(b"%PDF-1.4 inhalt-v1"), "application/pdf")},
        data={"change_note": "erste Version"},
        headers=_csrf(client),
    )
    assert upload.status_code == 201, upload.text
    return doc_id, upload.json()["version"]["version_number"]


def _release_and_publish(client: TestClient, doc_id: str, version_number: int) -> None:
    r = client.post(
        f"/api/documents/{doc_id}/status",
        json={"to": "in_review"},
        headers=_csrf(client),
    )
    assert r.status_code == 200, r.text
    r = client.post(
        f"/api/documents/{doc_id}/release",
        json={"version_number": version_number},
        headers=_csrf(client),
    )
    assert r.status_code == 200, r.text
    r = client.post(
        f"/api/documents/{doc_id}/visibility",
        json={"to": "public"},
        headers=_csrf(client),
    )
    assert r.status_code == 200, r.text


@pytest.fixture
def published_document(member_client: TestClient, lead_in_wp3) -> tuple[str, int]:
    doc_id, n = _create_doc_with_version(member_client, title="Published Doc")
    _release_and_publish(member_client, doc_id, n)
    return doc_id, n


# --- list ----------------------------------------------------------------


def test_list_anonymous_returns_only_published(
    client: TestClient, member_client: TestClient, lead_in_wp3
) -> None:
    # eine freigegebene+öffentliche, eine nur draft, eine internal
    doc_pub, n = _create_doc_with_version(member_client, title="Pub")
    _release_and_publish(member_client, doc_pub, n)

    _create_doc_with_version(member_client, title="DraftEntry")  # bleibt draft

    doc_int, n2 = _create_doc_with_version(member_client, title="Internal")
    member_client.post(
        f"/api/documents/{doc_int}/status",
        json={"to": "in_review"},
        headers=_csrf(member_client),
    )
    member_client.post(
        f"/api/documents/{doc_int}/release",
        json={"version_number": n2},
        headers=_csrf(member_client),
    )
    member_client.post(
        f"/api/documents/{doc_int}/visibility",
        json={"to": "internal"},
        headers=_csrf(member_client),
    )

    # Anonymer Aufruf — kein Cookie/CSRF.
    client.cookies.clear()
    r = client.get("/api/public/documents")
    assert r.status_code == 200
    items = r.json()
    titles = [d["title"] for d in items]
    assert "Pub" in titles
    assert "DraftEntry" not in titles
    assert "Internal" not in titles


# --- detail --------------------------------------------------------------


def test_detail_anonymous_works_for_public(client: TestClient, published_document) -> None:
    client.cookies.clear()
    r = client.get("/api/public/documents/WP3/published-doc")
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Published Doc"
    assert body["workpackage"]["code"] == "WP3"
    assert body["released_version"]["version_number"] == 1
    assert body["download_url"].endswith("/download")


def test_detail_unknown_returns_404(client: TestClient, member_in_wp3) -> None:
    client.cookies.clear()
    r = client.get("/api/public/documents/WP3/gibt-es-nicht")
    assert r.status_code == 404


def test_detail_for_internal_doc_returns_404(
    client: TestClient, member_client: TestClient, lead_in_wp3
) -> None:
    doc_id, n = _create_doc_with_version(member_client, title="Konsortial")
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
    member_client.post(
        f"/api/documents/{doc_id}/visibility",
        json={"to": "internal"},
        headers=_csrf(member_client),
    )
    client.cookies.clear()
    r = client.get("/api/public/documents/WP3/konsortial")
    assert r.status_code == 404


# --- download ------------------------------------------------------------


def test_download_anonymous_streams_published_version(
    client: TestClient, published_document
) -> None:
    client.cookies.clear()
    r = client.get("/api/public/documents/WP3/published-doc/download")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert (
        hashlib.sha256(r.content).hexdigest() == hashlib.sha256(b"%PDF-1.4 inhalt-v1").hexdigest()
    )


def test_download_for_draft_returns_404(
    client: TestClient, member_client: TestClient, member_in_wp3
) -> None:
    _create_doc_with_version(member_client, title="DraftDoc")  # bleibt draft
    client.cookies.clear()
    r = client.get("/api/public/documents/WP3/draftdoc/download")
    assert r.status_code == 404


# --- new version after release does not change public --------------------


def test_new_version_does_not_replace_public_version(
    client: TestClient, member_client: TestClient, lead_in_wp3
) -> None:
    doc_id, n = _create_doc_with_version(member_client, title="VersionsTest")
    _release_and_publish(member_client, doc_id, n)
    # Neue Version hochladen
    upload = member_client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": ("v2.pdf", io.BytesIO(b"%PDF-1.4 v2 anders"), "application/pdf")},
        data={"change_note": "zweite Version"},
        headers=_csrf(member_client),
    )
    assert upload.status_code == 201

    # Anonyme Sicht zeigt weiterhin v1 als released_version
    client.cookies.clear()
    r = client.get("/api/public/documents/WP3/versionstest")
    assert r.status_code == 200
    body = r.json()
    assert body["released_version"]["version_number"] == 1
    assert body["released_version"]["original_filename"] == "v1.pdf"

    dl = client.get("/api/public/documents/WP3/versionstest/download")
    assert dl.status_code == 200
    assert (
        hashlib.sha256(dl.content).hexdigest() == hashlib.sha256(b"%PDF-1.4 inhalt-v1").hexdigest()
    )


# --- soft-delete hides public --------------------------------------------


def test_soft_deleted_disappears_from_public(
    client: TestClient, admin_person_id, member_client: TestClient, lead_in_wp3
) -> None:
    doc_id, n = _create_doc_with_version(member_client, title="DeleteMe")
    _release_and_publish(member_client, doc_id, n)
    # Admin-Login auf demselben Client für DELETE
    from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD

    member_client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    member_client.delete(f"/api/documents/{doc_id}", headers=_csrf(member_client))

    client.cookies.clear()
    r = client.get("/api/public/documents")
    titles = [d["title"] for d in r.json()]
    assert "DeleteMe" not in titles
    r = client.get("/api/public/documents/WP3/deleteme/download")
    assert r.status_code == 404
