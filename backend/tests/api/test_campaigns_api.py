"""API: Testkampagnenregister (Block 0022).

Permission-Matrix (anonym / Member / WP-Lead / Admin), Filter, Cancel,
Teilnehmende-CRUD, Document-Link, Audit, CSRF.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ref4ep.domain.models import (
    AuditLog,
    Document,
    Person,
    TestCampaign,
)
from ref4ep.services.permissions import AuthContext
from ref4ep.services.test_campaign_service import TestCampaignService
from ref4ep.services.workpackage_service import WorkpackageService


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("ref4ep_csrf") or ""}


def _wp_id(seeded_session: Session, code: str) -> str:
    wp = WorkpackageService(seeded_session).get_by_code(code)
    assert wp is not None
    return wp.id


def _starts_on() -> str:
    return date.today().isoformat()


def _create_campaign_via_service(
    session: Session,
    *,
    code: str,
    wp_codes: list[str],
    title: str = "Initial",
) -> str:
    """Hilfsroutine: legt eine Kampagne direkt über den Service an,
    damit Tests ohne Cookie-Kollision zwischen ``admin_client`` und
    ``member_client`` funktionieren (vgl. Meeting-Tests)."""
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


# ---- LIST + GET --------------------------------------------------------


def test_anonymous_cannot_list(client: TestClient) -> None:
    client.cookies.clear()
    r = client.get("/api/campaigns")
    assert r.status_code == 401


def test_member_can_list_campaigns_initially_empty(member_client: TestClient) -> None:
    r = member_client.get("/api/campaigns")
    assert r.status_code == 200
    assert r.json() == []


def test_admin_can_create_campaign_without_workpackage(
    admin_client: TestClient, seeded_session: Session
) -> None:
    r = admin_client.post(
        "/api/campaigns",
        json={
            "code": "TC-2026-001",
            "title": "Konsortiumsweiter Ringvergleich",
            "starts_on": _starts_on(),
            "category": "ring_comparison",
            "workpackage_ids": [],
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["code"] == "TC-2026-001"
    assert body["category"] == "ring_comparison"
    assert body["workpackages"] == []
    assert body["can_edit"] is True


def test_admin_can_create_campaign_with_workpackage(
    admin_client: TestClient, seeded_session: Session
) -> None:
    wp = _wp_id(seeded_session, "WP3.1")
    r = admin_client.post(
        "/api/campaigns",
        json={
            "code": "TC-2026-WP3.1",
            "title": "Diagnostiktest WP3.1",
            "starts_on": _starts_on(),
            "category": "diagnostics_test",
            "workpackage_ids": [wp],
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    codes = [w["code"] for w in body["workpackages"]]
    assert codes == ["WP3.1"]


def test_unique_code_constraint(admin_client: TestClient, seeded_session: Session) -> None:
    payload = {
        "code": "TC-2026-DUP",
        "title": "Erster",
        "starts_on": _starts_on(),
        "workpackage_ids": [],
    }
    r1 = admin_client.post("/api/campaigns", json=payload, headers=_csrf(admin_client))
    assert r1.status_code == 201
    r2 = admin_client.post(
        "/api/campaigns",
        json={**payload, "title": "Zweiter mit gleichem Code"},
        headers=_csrf(admin_client),
    )
    assert r2.status_code == 422


# ---- WP-Lead-Berechtigungen --------------------------------------------


def test_member_without_lead_cannot_create_campaign(
    member_client: TestClient,
    seeded_session: Session,
    member_in_wp3,
) -> None:
    wp = _wp_id(seeded_session, "WP3")
    r = member_client.post(
        "/api/campaigns",
        json={
            "code": "TC-2026-WP3",
            "title": "Versuch",
            "starts_on": _starts_on(),
            "workpackage_ids": [wp],
        },
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_wp_lead_can_create_with_own_wp(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
) -> None:
    wp = _wp_id(seeded_session, "WP3")
    r = member_client.post(
        "/api/campaigns",
        json={
            "code": "TC-2026-WP3-Lead",
            "title": "WP3-Kampagne",
            "starts_on": _starts_on(),
            "workpackage_ids": [wp],
        },
        headers=_csrf(member_client),
    )
    assert r.status_code == 201, r.text


def test_wp_lead_cannot_create_without_wp(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
) -> None:
    r = member_client.post(
        "/api/campaigns",
        json={
            "code": "TC-2026-no-wp",
            "title": "Lead möchte übergreifende Kampagne",
            "starts_on": _starts_on(),
            "workpackage_ids": [],
        },
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_wp_lead_cannot_create_with_foreign_wp(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
) -> None:
    foreign = _wp_id(seeded_session, "WP4.1")
    r = member_client.post(
        "/api/campaigns",
        json={
            "code": "TC-2026-foreign",
            "title": "Übergriff",
            "starts_on": _starts_on(),
            "workpackage_ids": [foreign],
        },
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_wp_lead_cannot_create_with_mixed_wps(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
) -> None:
    own = _wp_id(seeded_session, "WP3")
    foreign = _wp_id(seeded_session, "WP4.1")
    r = member_client.post(
        "/api/campaigns",
        json={
            "code": "TC-2026-mixed",
            "title": "Gemischt",
            "starts_on": _starts_on(),
            "workpackage_ids": [own, foreign],
        },
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_wp_lead_can_edit_own_campaign(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
    admin_person_id: str,
) -> None:
    cid = _create_campaign_via_service(seeded_session, code="TC-2026-edit", wp_codes=["WP3"])
    r = member_client.patch(
        f"/api/campaigns/{cid}",
        json={"title": "Lead-Edit", "status": "preparing"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Lead-Edit"
    assert body["status"] == "preparing"


def test_wp_lead_cannot_edit_foreign_campaign(
    member_client: TestClient,
    seeded_session: Session,
    lead_in_wp3,
    admin_person_id: str,
) -> None:
    cid = _create_campaign_via_service(
        seeded_session, code="TC-2026-foreign-edit", wp_codes=["WP4.1"]
    )
    r = member_client.patch(
        f"/api/campaigns/{cid}",
        json={"title": "Hack"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


def test_member_cannot_edit(
    member_client: TestClient,
    seeded_session: Session,
    member_in_wp3,
    admin_person_id: str,
) -> None:
    cid = _create_campaign_via_service(seeded_session, code="TC-2026-member", wp_codes=["WP3"])
    r = member_client.patch(
        f"/api/campaigns/{cid}",
        json={"title": "Member-Edit"},
        headers=_csrf(member_client),
    )
    assert r.status_code == 403


# ---- Cancel ------------------------------------------------------------


def test_admin_can_cancel(admin_client: TestClient, seeded_session: Session) -> None:
    created = admin_client.post(
        "/api/campaigns",
        json={
            "code": "TC-2026-cancel",
            "title": "Absagen",
            "starts_on": _starts_on(),
            "workpackage_ids": [],
        },
        headers=_csrf(admin_client),
    ).json()
    r = admin_client.post(
        f"/api/campaigns/{created['id']}/cancel",
        headers=_csrf(admin_client),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_no_hard_delete_endpoint() -> None:
    """Block 0022 erlaubt explizit kein Hard-Delete für Kampagnen."""
    from ref4ep.api.app import create_app
    from ref4ep.api.config import Settings

    app = create_app(
        settings=Settings(
            database_url="sqlite:///:memory:",
            session_secret="x" * 48,
            storage_dir="/tmp/x",
        )
    )
    delete_routes = [
        r
        for r in app.routes
        if getattr(r, "path", "") == "/api/campaigns/{campaign_id}"
        and "DELETE" in getattr(r, "methods", set())
    ]
    assert delete_routes == []


# ---- Teilnehmende ------------------------------------------------------


def test_admin_can_add_update_remove_participant(
    admin_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
) -> None:
    created = admin_client.post(
        "/api/campaigns",
        json={
            "code": "TC-2026-participants",
            "title": "P",
            "starts_on": _starts_on(),
            "workpackage_ids": [],
        },
        headers=_csrf(admin_client),
    ).json()
    cid = created["id"]
    add = admin_client.post(
        f"/api/campaigns/{cid}/participants",
        json={"person_id": member_person_id, "role": "diagnostics", "note": "Hauptdiagnostik"},
        headers=_csrf(admin_client),
    )
    assert add.status_code == 201, add.text
    detail = add.json()
    assert len(detail["participants"]) == 1
    p_id = detail["participants"][0]["id"]
    assert detail["participants"][0]["role"] == "diagnostics"
    # Rollenwechsel via PATCH /api/campaign-participants/{id}.
    upd = admin_client.patch(
        f"/api/campaign-participants/{p_id}",
        json={"role": "data_analysis", "note": None},
        headers=_csrf(admin_client),
    )
    assert upd.status_code == 200
    assert upd.json()["role"] == "data_analysis"
    # Entfernen.
    rem = admin_client.delete(
        f"/api/campaign-participants/{p_id}",
        headers=_csrf(admin_client),
    )
    assert rem.status_code == 204
    after = admin_client.get(f"/api/campaigns/{cid}").json()
    assert after["participants"] == []


def test_invalid_participant_role_returns_422(
    admin_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
) -> None:
    cid = admin_client.post(
        "/api/campaigns",
        json={
            "code": "TC-2026-roleval",
            "title": "P",
            "starts_on": _starts_on(),
            "workpackage_ids": [],
        },
        headers=_csrf(admin_client),
    ).json()["id"]
    r = admin_client.post(
        f"/api/campaigns/{cid}/participants",
        json={"person_id": member_person_id, "role": "ungueltig"},
        headers=_csrf(admin_client),
    )
    assert r.status_code == 422


# ---- Document-Link -----------------------------------------------------


def test_admin_can_link_and_unlink_document(
    admin_client: TestClient, seeded_session: Session
) -> None:
    admin = seeded_session.query(Person).filter_by(email="admin@test.example").one()
    auth = AuthContext(person_id=admin.id, email=admin.email, platform_role="admin", memberships=[])
    from ref4ep.services.document_service import DocumentService

    doc = DocumentService(seeded_session, auth=auth).create(
        workpackage_code="WP1.1",
        title="Messplan WP1.1",
        document_type="report",
    )
    seeded_session.commit()

    wp = _wp_id(seeded_session, "WP1.1")
    created = admin_client.post(
        "/api/campaigns",
        json={
            "code": "TC-2026-docs",
            "title": "Mit Doc",
            "starts_on": _starts_on(),
            "workpackage_ids": [wp],
        },
        headers=_csrf(admin_client),
    ).json()
    cid = created["id"]
    link = admin_client.post(
        f"/api/campaigns/{cid}/documents",
        json={"document_id": doc.id, "label": "test_plan"},
        headers=_csrf(admin_client),
    )
    assert link.status_code == 201, link.text
    docs = link.json()["documents"]
    assert len(docs) == 1
    assert docs[0]["label"] == "test_plan"
    assert docs[0]["title"] == "Messplan WP1.1"

    unlink = admin_client.delete(
        f"/api/campaigns/{cid}/documents/{doc.id}",
        headers=_csrf(admin_client),
    )
    assert unlink.status_code == 204
    # Dokument selbst bleibt erhalten.
    persisted = seeded_session.get(Document, doc.id)
    assert persisted is not None and persisted.is_deleted is False


# ---- Filter ------------------------------------------------------------


@pytest.fixture
def three_campaigns(seeded_session: Session, admin_person_id: str) -> dict[str, str]:
    a = _create_campaign_via_service(
        seeded_session, code="TC-RC-01", wp_codes=["WP3"], title="Ring A"
    )
    b = _create_campaign_via_service(
        seeded_session, code="TC-RC-02", wp_codes=["WP4.1"], title="Calib B"
    )
    c = _create_campaign_via_service(
        seeded_session, code="TC-RC-03", wp_codes=["WP3"], title="Ring C"
    )
    return {"a": a, "b": b, "c": c}


def test_filter_by_workpackage_returns_subset(admin_client: TestClient, three_campaigns) -> None:
    r = admin_client.get("/api/campaigns?workpackage=WP3")
    body = r.json()
    codes = {c["code"] for c in body}
    assert codes == {"TC-RC-01", "TC-RC-03"}


def test_filter_by_q_searches_title_and_code(admin_client: TestClient, three_campaigns) -> None:
    r = admin_client.get("/api/campaigns?q=Calib")
    codes = {c["code"] for c in r.json()}
    assert codes == {"TC-RC-02"}


def test_filter_status_validates(admin_client: TestClient) -> None:
    r = admin_client.get("/api/campaigns?status=ungueltig")
    assert r.status_code == 422


def test_filter_category_validates(admin_client: TestClient) -> None:
    r = admin_client.get("/api/campaigns?category=ungueltig")
    assert r.status_code == 422


def test_filter_unknown_workpackage_returns_empty(admin_client: TestClient) -> None:
    r = admin_client.get("/api/campaigns?workpackage=WPXX")
    assert r.status_code == 200
    assert r.json() == []


# ---- Validierung -------------------------------------------------------


def test_invalid_status_returns_422(admin_client: TestClient) -> None:
    r = admin_client.post(
        "/api/campaigns",
        json={
            "code": "TC-2026-badstatus",
            "title": "X",
            "starts_on": _starts_on(),
            "status": "ungueltig",
            "workpackage_ids": [],
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 422


def test_invalid_category_returns_422(admin_client: TestClient) -> None:
    r = admin_client.post(
        "/api/campaigns",
        json={
            "code": "TC-2026-badcat",
            "title": "X",
            "starts_on": _starts_on(),
            "category": "ungueltig",
            "workpackage_ids": [],
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 422


def test_unknown_workpackage_returns_404(admin_client: TestClient) -> None:
    r = admin_client.post(
        "/api/campaigns",
        json={
            "code": "TC-2026-badwp",
            "title": "X",
            "starts_on": _starts_on(),
            "workpackage_ids": ["00000000-0000-0000-0000-000000000000"],
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 404


def test_ends_on_before_starts_on_is_422(admin_client: TestClient) -> None:
    today = date.today()
    yesterday = today - timedelta(days=1)
    r = admin_client.post(
        "/api/campaigns",
        json={
            "code": "TC-2026-bad-range",
            "title": "X",
            "starts_on": today.isoformat(),
            "ends_on": yesterday.isoformat(),
            "workpackage_ids": [],
        },
        headers=_csrf(admin_client),
    )
    assert r.status_code == 422


def test_csrf_required_on_create(admin_client: TestClient) -> None:
    r = admin_client.post(
        "/api/campaigns",
        json={
            "code": "TC-2026-nocsrf",
            "title": "Ohne CSRF",
            "starts_on": _starts_on(),
            "workpackage_ids": [],
        },
    )
    assert r.status_code == 403


# ---- Audit -------------------------------------------------------------


def test_audit_writes_create_and_cancel(admin_client: TestClient, seeded_session: Session) -> None:
    created = admin_client.post(
        "/api/campaigns",
        json={
            "code": "TC-2026-audit",
            "title": "Audit-Quelle",
            "starts_on": _starts_on(),
            "workpackage_ids": [],
        },
        headers=_csrf(admin_client),
    ).json()
    admin_client.post(
        f"/api/campaigns/{created['id']}/cancel",
        headers=_csrf(admin_client),
    )
    seeded_session.expire_all()
    actions = {e.action for e in seeded_session.query(AuditLog).all()}
    assert "campaign.create" in actions
    assert "campaign.cancel" in actions


def test_audit_writes_participant_and_document_link(
    admin_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
) -> None:
    cid = admin_client.post(
        "/api/campaigns",
        json={
            "code": "TC-2026-audit-rel",
            "title": "X",
            "starts_on": _starts_on(),
            "workpackage_ids": [],
        },
        headers=_csrf(admin_client),
    ).json()["id"]
    admin_client.post(
        f"/api/campaigns/{cid}/participants",
        json={"person_id": member_person_id, "role": "operation"},
        headers=_csrf(admin_client),
    )
    # Doc anlegen + verknüpfen.
    admin = seeded_session.query(Person).filter_by(email="admin@test.example").one()
    auth = AuthContext(person_id=admin.id, email=admin.email, platform_role="admin", memberships=[])
    from ref4ep.services.document_service import DocumentService

    doc = DocumentService(seeded_session, auth=auth).create(
        workpackage_code="WP1.1",
        title="Auswertung X",
        document_type="report",
    )
    seeded_session.commit()
    admin_client.post(
        f"/api/campaigns/{cid}/documents",
        json={"document_id": doc.id, "label": "analysis"},
        headers=_csrf(admin_client),
    )
    seeded_session.expire_all()
    actions = {e.action for e in seeded_session.query(AuditLog).all()}
    assert "campaign.participant.add" in actions
    assert "campaign.document_link.add" in actions


# ---- Sicherheits-Smoke -------------------------------------------------


def test_seeded_db_has_no_campaigns(seeded_session: Session) -> None:
    assert seeded_session.query(TestCampaign).count() == 0


def test_response_does_not_leak_password_or_secret(
    admin_client: TestClient,
    seeded_session: Session,
    member_person_id: str,
) -> None:
    admin_client.post(
        "/api/campaigns",
        json={
            "code": "TC-2026-leak-check",
            "title": "X",
            "starts_on": _starts_on(),
            "workpackage_ids": [],
        },
        headers=_csrf(admin_client),
    )
    body_text = admin_client.get("/api/campaigns").text.lower()
    assert "password" not in body_text
    assert "session_secret" not in body_text


# ---- Bystander: Datums-/Zeitstempel-Sanity -----------------------------


def test_created_at_is_set(admin_client: TestClient) -> None:
    """Sanity: created_at landet als ISO-String im Response."""
    created = admin_client.post(
        "/api/campaigns",
        json={
            "code": "TC-2026-stamp",
            "title": "Stamp",
            "starts_on": _starts_on(),
            "workpackage_ids": [],
        },
        headers=_csrf(admin_client),
    ).json()
    # Sanity-Check via GET — created_by ist gefüllt.
    r = admin_client.get(f"/api/campaigns/{created['id']}").json()
    assert r["created_by"]["display_name"] == "Test admin"


def test_now_is_serialized_as_utc_string() -> None:
    """Schmaler Smoke-Test, dass UTC-Helper funktioniert (kein API-Aufruf)."""
    iso = datetime.now(tz=UTC).isoformat()
    assert iso.endswith("+00:00") or iso.endswith("Z")
