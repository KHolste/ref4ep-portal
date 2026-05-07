"""API: Reverse-Pfad Dokument → Testkampagne.

Phase 1 von Block-Erweiterung „Dokument einer Testkampagne zuordnen".
Endpunkte ``POST/DELETE /api/documents/{id}/test-campaigns``,
``GET /api/documents/{id}.test_campaigns``. Nutzt die existierende
n:m-Tabelle ``test_campaign_document_link``; keine Migration.
"""

from __future__ import annotations

import json
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.domain.models import AuditLog, Person
from ref4ep.services.document_service import DocumentService
from ref4ep.services.permissions import AuthContext
from ref4ep.services.test_campaign_service import TestCampaignService
from ref4ep.services.workpackage_service import WorkpackageService


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def _wp_id(session: Session, code: str) -> str:
    wp = WorkpackageService(session).get_by_code(code)
    assert wp is not None
    return wp.id


def _create_campaign(
    session: Session, *, code: str, wp_codes: list[str], title: str = "Kampagne"
) -> str:
    """Kampagne direkt über den Service anlegen (Pattern aus
    ``test_campaigns_api.py``)."""
    admin = session.query(Person).filter_by(email="admin@test.example").one()
    wp_ids = [_wp_id(session, c) for c in wp_codes]
    campaign = TestCampaignService(
        session, role=admin.platform_role, person_id=admin.id
    ).create_campaign(
        code=code,
        title=title,
        starts_on=date.today(),
        workpackage_ids=wp_ids,
    )
    session.commit()
    return campaign.id


def _create_doc(client: TestClient, *, wp_code: str, title: str) -> str:
    r = client.post(
        f"/api/workpackages/{wp_code}/documents",
        json={"title": title, "document_type": "report"},
        headers=_csrf(client),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_doc_via_service(
    session: Session,
    *,
    wp_code: str,
    title: str,
    visibility: str | None = None,
) -> str:
    """Doc direkt über den Service anlegen (umgeht Cookie-Kollision
    zwischen admin_client und member_client). Optionale Visibility wird
    nach Anlage direkt am Modell gesetzt — Default-Visibility ist
    ``workpackage``."""
    admin = session.query(Person).filter_by(email="admin@test.example").one()
    auth = AuthContext(
        person_id=admin.id,
        email=admin.email,
        platform_role=admin.platform_role,
        memberships=[],
    )
    document = DocumentService(session, auth=auth).create(
        workpackage_code=wp_code,
        title=title,
        document_type="report",
    )
    if visibility is not None:
        document.visibility = visibility
    session.commit()
    return document.id


# ---- GET /api/documents/{id} liefert test_campaigns ------------------------


def test_document_detail_includes_linked_campaigns(
    member_client: TestClient,
    member_in_wp3,
    admin_person_id: str,
    seeded_session: Session,
) -> None:
    doc_id = _create_doc(member_client, wp_code="WP3", title="Plan A")
    campaign_id = _create_campaign(
        seeded_session, code="TC-WP3-LINK", wp_codes=["WP3"], title="Ringvergleich"
    )

    r = member_client.post(
        f"/api/documents/{doc_id}/test-campaigns",
        json={"campaign_id": campaign_id, "label": "test_plan"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 201, r.text

    detail = member_client.get(f"/api/documents/{doc_id}").json()
    assert "test_campaigns" in detail
    links = detail["test_campaigns"]
    assert len(links) == 1
    assert links[0]["id"] == campaign_id
    assert links[0]["code"] == "TC-WP3-LINK"
    assert links[0]["title"] == "Ringvergleich"
    assert links[0]["label"] == "test_plan"
    assert links[0]["status"] == "planned"


def test_document_detail_test_campaigns_empty_when_no_links(
    member_client: TestClient, member_in_wp3
) -> None:
    doc_id = _create_doc(member_client, wp_code="WP3", title="Solo")
    r = member_client.get(f"/api/documents/{doc_id}")
    assert r.status_code == 200
    assert r.json()["test_campaigns"] == []


# ---- POST /api/documents/{id}/test-campaigns -------------------------------


def test_post_link_creates_audit_entry(
    member_client: TestClient,
    member_in_wp3,
    admin_person_id: str,
    seeded_session: Session,
) -> None:
    doc_id = _create_doc(member_client, wp_code="WP3", title="Audit")
    campaign_id = _create_campaign(
        seeded_session, code="TC-AUDIT", wp_codes=["WP3"]
    )

    r = member_client.post(
        f"/api/documents/{doc_id}/test-campaigns",
        json={"campaign_id": campaign_id, "label": "protocol"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 201, r.text

    entry = (
        seeded_session.query(AuditLog)
        .filter_by(action="campaign.document_link.add", entity_id=campaign_id)
        .one()
    )
    payload = json.loads(entry.details)
    assert payload["after"]["document_id"] == doc_id
    assert payload["after"]["label"] == "protocol"


def test_post_link_idempotent_relabel_writes_before_after(
    member_client: TestClient,
    member_in_wp3,
    admin_person_id: str,
    seeded_session: Session,
) -> None:
    doc_id = _create_doc(member_client, wp_code="WP3", title="Idem")
    campaign_id = _create_campaign(
        seeded_session, code="TC-IDEM", wp_codes=["WP3"]
    )

    r1 = member_client.post(
        f"/api/documents/{doc_id}/test-campaigns",
        json={"campaign_id": campaign_id, "label": "test_plan"},
        headers=_csrf(member_client),
    )
    assert r1.status_code == 201

    r2 = member_client.post(
        f"/api/documents/{doc_id}/test-campaigns",
        json={"campaign_id": campaign_id, "label": "protocol"},
        headers=_csrf(member_client),
    )
    assert r2.status_code == 201, r2.text
    links = r2.json()["test_campaigns"]
    assert len(links) == 1 and links[0]["label"] == "protocol"

    entries = (
        seeded_session.query(AuditLog)
        .filter_by(action="campaign.document_link.add", entity_id=campaign_id)
        .order_by(AuditLog.created_at)
        .all()
    )
    assert len(entries) == 2
    second = json.loads(entries[1].details)
    assert second["before"] == {"label": "test_plan"}
    assert second["after"]["label"] == "protocol"


def test_post_link_unknown_campaign_returns_404(
    member_client: TestClient, member_in_wp3
) -> None:
    doc_id = _create_doc(member_client, wp_code="WP3", title="X")
    r = member_client.post(
        f"/api/documents/{doc_id}/test-campaigns",
        json={
            "campaign_id": "00000000-0000-0000-0000-000000000000",
            "label": "other",
        },
        headers=_csrf(member_client),
    )
    assert r.status_code == 404


def test_post_link_invalid_label_returns_422(
    member_client: TestClient,
    member_in_wp3,
    admin_person_id: str,
    seeded_session: Session,
) -> None:
    doc_id = _create_doc(member_client, wp_code="WP3", title="L")
    campaign_id = _create_campaign(
        seeded_session, code="TC-INV", wp_codes=["WP3"]
    )
    r = member_client.post(
        f"/api/documents/{doc_id}/test-campaigns",
        json={"campaign_id": campaign_id, "label": "not-a-label"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 422


def test_post_link_wp_mismatch_returns_422(
    member_client: TestClient,
    member_in_wp3,
    admin_person_id: str,
    seeded_session: Session,
) -> None:
    """Dokument ist in WP3, Kampagne in WP4 — fachlich inkompatibel."""
    doc_id = _create_doc(member_client, wp_code="WP3", title="Mismatch")
    campaign_id = _create_campaign(
        seeded_session, code="TC-WP4", wp_codes=["WP4"]
    )
    r = member_client.post(
        f"/api/documents/{doc_id}/test-campaigns",
        json={"campaign_id": campaign_id, "label": "other"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["error"]["code"] == "invalid"


def test_post_link_invisible_document_returns_404(
    member_client: TestClient,
    member_in_wp3,
    admin_person_id: str,
    seeded_session: Session,
) -> None:
    """Existenz-Leak-Schutz: ein WP-fremdes Doc mit visibility=workpackage
    ist für den Member unsichtbar → 404, nicht 403."""
    foreign_doc_id = _create_doc_via_service(
        seeded_session, wp_code="WP4", title="Fremd"
    )
    campaign_id = _create_campaign(
        seeded_session, code="TC-FR", wp_codes=["WP4"]
    )
    r = member_client.post(
        f"/api/documents/{foreign_doc_id}/test-campaigns",
        json={"campaign_id": campaign_id, "label": "other"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 404


def test_post_link_visible_but_no_write_returns_403(
    member_client: TestClient,
    member_in_wp3,
    admin_person_id: str,
    seeded_session: Session,
) -> None:
    """Doc liegt in WP4 mit visibility=internal — Member darf lesen
    (eingeloggt + internal), aber nicht schreiben (kein WP4-Mitglied)
    → 403."""
    foreign_doc_id = _create_doc_via_service(
        seeded_session, wp_code="WP4", title="Intern", visibility="internal"
    )
    campaign_id = _create_campaign(
        seeded_session, code="TC-INT", wp_codes=["WP4"]
    )
    # Sanity: Member kann das Doc lesen.
    visible = member_client.get(f"/api/documents/{foreign_doc_id}")
    assert visible.status_code == 200

    r = member_client.post(
        f"/api/documents/{foreign_doc_id}/test-campaigns",
        json={"campaign_id": campaign_id, "label": "other"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["error"]["code"] == "forbidden"


def test_post_link_unknown_document_returns_404(
    member_client: TestClient,
    member_in_wp3,
    admin_person_id: str,
    seeded_session: Session,
) -> None:
    campaign_id = _create_campaign(
        seeded_session, code="TC-UD", wp_codes=["WP3"]
    )
    r = member_client.post(
        "/api/documents/00000000-0000-0000-0000-000000000000/test-campaigns",
        json={"campaign_id": campaign_id, "label": "other"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 404


def test_post_link_without_csrf_blocked(
    member_client: TestClient,
    member_in_wp3,
    admin_person_id: str,
    seeded_session: Session,
) -> None:
    doc_id = _create_doc(member_client, wp_code="WP3", title="NoCSRF")
    campaign_id = _create_campaign(
        seeded_session, code="TC-NCS", wp_codes=["WP3"]
    )
    r = member_client.post(
        f"/api/documents/{doc_id}/test-campaigns",
        json={"campaign_id": campaign_id, "label": "other"},
    )
    assert r.status_code == 403


# ---- DELETE /api/documents/{id}/test-campaigns/{campaign_id} ---------------


def test_delete_link_removes_and_audits(
    member_client: TestClient,
    member_in_wp3,
    admin_person_id: str,
    seeded_session: Session,
) -> None:
    doc_id = _create_doc(member_client, wp_code="WP3", title="Del")
    campaign_id = _create_campaign(
        seeded_session, code="TC-DEL", wp_codes=["WP3"]
    )
    add = member_client.post(
        f"/api/documents/{doc_id}/test-campaigns",
        json={"campaign_id": campaign_id, "label": "analysis"},
        headers=_csrf(member_client),
    )
    assert add.status_code == 201

    r = member_client.delete(
        f"/api/documents/{doc_id}/test-campaigns/{campaign_id}",
        headers=_csrf(member_client),
    )
    assert r.status_code == 204

    detail = member_client.get(f"/api/documents/{doc_id}").json()
    assert detail["test_campaigns"] == []

    entry = (
        seeded_session.query(AuditLog)
        .filter_by(action="campaign.document_link.remove", entity_id=campaign_id)
        .one()
    )
    payload = json.loads(entry.details)
    assert payload["before"]["document_id"] == doc_id
    assert payload["before"]["label"] == "analysis"


def test_delete_link_unknown_campaign_returns_404(
    member_client: TestClient, member_in_wp3
) -> None:
    doc_id = _create_doc(member_client, wp_code="WP3", title="DelU")
    r = member_client.delete(
        f"/api/documents/{doc_id}/test-campaigns/00000000-0000-0000-0000-000000000000",
        headers=_csrf(member_client),
    )
    assert r.status_code == 404


def test_delete_link_idempotent_when_no_link(
    member_client: TestClient,
    member_in_wp3,
    admin_person_id: str,
    seeded_session: Session,
) -> None:
    """Kampagne existiert, Link nicht — 204, kein Audit."""
    doc_id = _create_doc(member_client, wp_code="WP3", title="DelI")
    campaign_id = _create_campaign(
        seeded_session, code="TC-DELI", wp_codes=["WP3"]
    )
    r = member_client.delete(
        f"/api/documents/{doc_id}/test-campaigns/{campaign_id}",
        headers=_csrf(member_client),
    )
    assert r.status_code == 204
    count = (
        seeded_session.query(AuditLog)
        .filter_by(action="campaign.document_link.remove", entity_id=campaign_id)
        .count()
    )
    assert count == 0


def test_delete_link_invisible_document_returns_404(
    member_client: TestClient,
    member_in_wp3,
    admin_person_id: str,
    seeded_session: Session,
) -> None:
    """Existenz-Leak-Schutz beim DELETE: WP-fremdes Doc → 404."""
    foreign_doc_id = _create_doc_via_service(
        seeded_session, wp_code="WP4", title="Fr"
    )
    campaign_id = _create_campaign(
        seeded_session, code="TC-FR2", wp_codes=["WP4"]
    )
    # Verlinken als Admin via Service.
    admin = seeded_session.query(Person).filter_by(email="admin@test.example").one()
    TestCampaignService(
        seeded_session, role=admin.platform_role, person_id=admin.id
    ).add_document_link(campaign_id, document_id=foreign_doc_id, label="other")
    seeded_session.commit()

    r = member_client.delete(
        f"/api/documents/{foreign_doc_id}/test-campaigns/{campaign_id}",
        headers=_csrf(member_client),
    )
    assert r.status_code == 404


def test_delete_link_visible_but_no_write_returns_403(
    member_client: TestClient,
    member_in_wp3,
    admin_person_id: str,
    seeded_session: Session,
) -> None:
    """Doc visibility=internal, Member kann lesen aber nicht schreiben
    → 403, auch beim Entlinken."""
    foreign_doc_id = _create_doc_via_service(
        seeded_session, wp_code="WP4", title="Int", visibility="internal"
    )
    campaign_id = _create_campaign(
        seeded_session, code="TC-INT2", wp_codes=["WP4"]
    )
    admin = seeded_session.query(Person).filter_by(email="admin@test.example").one()
    TestCampaignService(
        seeded_session, role=admin.platform_role, person_id=admin.id
    ).add_document_link(campaign_id, document_id=foreign_doc_id, label="other")
    seeded_session.commit()

    r = member_client.delete(
        f"/api/documents/{foreign_doc_id}/test-campaigns/{campaign_id}",
        headers=_csrf(member_client),
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["error"]["code"] == "forbidden"
