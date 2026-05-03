"""HTML-View /downloads — Sichtbarkeit der freigegebenen public-Dokumente."""

from __future__ import annotations

import io

from fastapi.testclient import TestClient


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def _publish(client: TestClient, title: str) -> str:
    create = client.post(
        "/api/workpackages/WP3/documents",
        json={"title": title, "document_type": "deliverable", "deliverable_code": "D3.X"},
        headers=_csrf(client),
    )
    assert create.status_code == 201
    doc_id = create.json()["id"]
    upload = client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": ("v1.pdf", io.BytesIO(b"%PDF-1.4 inhalt"), "application/pdf")},
        data={"change_note": "erste Version"},
        headers=_csrf(client),
    )
    assert upload.status_code == 201
    n = upload.json()["version"]["version_number"]
    client.post(
        f"/api/documents/{doc_id}/status",
        json={"to": "in_review"},
        headers=_csrf(client),
    )
    client.post(
        f"/api/documents/{doc_id}/release",
        json={"version_number": n},
        headers=_csrf(client),
    )
    client.post(
        f"/api/documents/{doc_id}/visibility",
        json={"to": "public"},
        headers=_csrf(client),
    )
    return doc_id


def test_downloads_page_lists_only_public_released(
    client: TestClient, member_client: TestClient, lead_in_wp3
) -> None:
    _publish(member_client, "ÖffentlichesDokument")
    # Ein nicht veröffentlichtes Dokument darf NICHT erscheinen.
    member_client.post(
        "/api/workpackages/WP3/documents",
        json={"title": "NurDraft", "document_type": "note"},
        headers=_csrf(member_client),
    )

    client.cookies.clear()
    r = client.get("/downloads")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    assert "ÖffentlichesDokument" in body
    assert "NurDraft" not in body
    assert "v1.pdf" in body
    assert "/api/public/documents/WP3/offentlichesdokument/download" in body


def test_downloads_page_shows_empty_message_when_no_public_docs(
    client: TestClient, seeded_session
) -> None:
    client.cookies.clear()
    r = client.get("/downloads")
    assert r.status_code == 200
    assert "Aktuell sind keine öffentlich freigegebenen Dokumente" in r.text


def test_download_detail_page_shows_metadata(
    client: TestClient, member_client: TestClient, lead_in_wp3
) -> None:
    _publish(member_client, "DetailTest")
    client.cookies.clear()
    r = client.get("/downloads/WP3/detailtest")
    assert r.status_code == 200
    body = r.text
    assert "DetailTest" in body
    assert "WP3" in body
    assert "D3.X" in body
    assert "v1.pdf" in body
    assert "/api/public/documents/WP3/detailtest/download" in body


def test_download_detail_page_404_for_unknown(client: TestClient, seeded_session) -> None:
    client.cookies.clear()
    r = client.get("/downloads/WP3/gibt-es-nicht")
    assert r.status_code == 404


def test_download_detail_page_404_for_internal(
    client: TestClient, member_client: TestClient, lead_in_wp3
) -> None:
    create = member_client.post(
        "/api/workpackages/WP3/documents",
        json={"title": "InternalDoc", "document_type": "note"},
        headers=_csrf(member_client),
    )
    doc_id = create.json()["id"]
    upload = member_client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": ("v.pdf", io.BytesIO(b"%PDF-1.4 i"), "application/pdf")},
        data={"change_note": "Initial-Entwurf"},
        headers=_csrf(member_client),
    )
    n = upload.json()["version"]["version_number"]
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
    r = client.get("/downloads/WP3/internaldoc")
    assert r.status_code == 404


# --- Praxistest-Korrekturrunde: Spalten, leere Codes, Datum --------------


def _publish_with(
    client: TestClient,
    title: str,
    *,
    deliverable_code: str | None = None,
    description: str | None = None,
) -> str:
    create = client.post(
        "/api/workpackages/WP3/documents",
        json={
            "title": title,
            "document_type": "deliverable",
            "deliverable_code": deliverable_code,
            "description": description,
        },
        headers=_csrf(client),
    )
    assert create.status_code == 201, create.text
    doc_id = create.json()["id"]
    upload = client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": ("v1.pdf", io.BytesIO(b"%PDF-1.4 inhalt"), "application/pdf")},
        data={"change_note": "Initial-Entwurf"},
        headers=_csrf(client),
    )
    n = upload.json()["version"]["version_number"]
    client.post(
        f"/api/documents/{doc_id}/status",
        json={"to": "in_review"},
        headers=_csrf(client),
    )
    client.post(
        f"/api/documents/{doc_id}/release",
        json={"version_number": n},
        headers=_csrf(client),
    )
    client.post(
        f"/api/documents/{doc_id}/visibility",
        json={"to": "public"},
        headers=_csrf(client),
    )
    return doc_id


def test_downloads_table_uses_dokumentcode_header(
    client: TestClient, member_client: TestClient, lead_in_wp3
) -> None:
    _publish_with(member_client, "HeaderProbe", deliverable_code="D9.9")
    client.cookies.clear()
    body = client.get("/downloads").text
    assert "Dokumentcode" in body
    # Alte rein-„Code"-Header darf nicht mehr in der Tabelle stehen.
    assert "<th>Code</th>" not in body


def test_downloads_table_shows_em_dash_for_empty_code(
    client: TestClient, member_client: TestClient, lead_in_wp3
) -> None:
    _publish_with(member_client, "OhneCode", deliverable_code=None)
    client.cookies.clear()
    body = client.get("/downloads").text
    assert "OhneCode" in body
    # Em-Dash erscheint im Tabellenfeld, nicht (nur) im Spaltenheader.
    assert "<td>—</td>" in body


def test_downloads_table_uses_german_date_format(
    client: TestClient, member_client: TestClient, lead_in_wp3
) -> None:
    from datetime import datetime

    _publish_with(member_client, "DatumsTest")
    client.cookies.clear()
    body = client.get("/downloads").text
    today = datetime.now().strftime("%d.%m.%Y")
    assert today in body
    iso_today = datetime.now().strftime("%Y-%m-%d")
    # ISO-Datum darf in der Tabellenzeile nicht mehr erscheinen
    # (Backslash-Form als negative Probe — Datum war bisher 2026-05-03 o. ä.).
    assert iso_today not in body


def test_download_detail_shows_em_dash_for_empty_code_and_description(
    client: TestClient, member_client: TestClient, lead_in_wp3
) -> None:
    _publish_with(
        member_client,
        "DetailMitText",
        deliverable_code=None,
        description="Inhaltliche Kurzbeschreibung des Dokuments.",
    )
    client.cookies.clear()
    body = client.get("/downloads/WP3/detailmittext").text
    assert "Dokumentcode" in body
    # Em-Dash für leeren Code im Detail.
    assert "<dd>—</dd>" in body
    # Beschreibung wird angezeigt.
    assert "Inhaltliche Kurzbeschreibung" in body
