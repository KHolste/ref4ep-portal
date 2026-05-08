"""TestCampaignNoteService — Permission-Matrix, Soft-Delete, Audit (Block 0029)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from ref4ep.domain.models import AuditLog, Person, TestCampaignNote
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.permissions import AuthContext
from ref4ep.services.person_service import PersonService
from ref4ep.services.test_campaign_note_service import (
    CampaignNoteNotFoundError,
    CampaignNotFoundError,
    TestCampaignNoteService,
)
from ref4ep.services.test_campaign_service import TestCampaignService
from ref4ep.services.workpackage_service import WorkpackageService


def _admin_auth(session: Session) -> tuple[Person, AuthContext]:
    admin = session.query(Person).filter_by(email="admin@test.example").one()
    return admin, AuthContext(
        person_id=admin.id, email=admin.email, platform_role="admin", memberships=[]
    )


def _create_member(session: Session, *, email: str) -> Person:
    partner = PartnerService(session).get_by_short_name("JLU")
    assert partner is not None
    person = PersonService(session, role="admin").create(
        email=email,
        display_name=email.split("@")[0],
        partner_id=partner.id,
        password="StrongPw1!",
        platform_role="member",
    )
    session.commit()
    return person


def _create_campaign(session: Session, *, code: str = "TC-NOTE") -> str:
    admin = session.query(Person).filter_by(email="admin@test.example").one()
    wp = WorkpackageService(session).get_by_code("WP3")
    assert wp is not None
    campaign = TestCampaignService(
        session, role=admin.platform_role, person_id=admin.id
    ).create_campaign(
        code=code,
        title="Notiz-Kampagne",
        starts_on=date.today(),
        workpackage_ids=[wp.id],
    )
    session.commit()
    return campaign.id


def _participant_auth(person: Person) -> AuthContext:
    return AuthContext(
        person_id=person.id,
        email=person.email,
        platform_role=person.platform_role,
        memberships=[],
    )


def _add_participant(session: Session, campaign_id: str, person_id: str) -> None:
    admin = session.query(Person).filter_by(email="admin@test.example").one()
    TestCampaignService(session, role=admin.platform_role, person_id=admin.id).add_participant(
        campaign_id, person_id=person_id, role="diagnostics"
    )
    session.commit()


@pytest.fixture
def admin_seeded(seeded_session: Session) -> Session:
    if not seeded_session.query(Person).filter_by(email="admin@test.example").first():
        partner = PartnerService(seeded_session).get_by_short_name("JLU")
        assert partner is not None
        PersonService(seeded_session, role="admin").create(
            email="admin@test.example",
            display_name="Admin",
            partner_id=partner.id,
            password="StrongPw1!",
            platform_role="admin",
        )
        seeded_session.commit()
    return seeded_session


# ---- Read --------------------------------------------------------------


def test_list_for_unknown_campaign_raises(admin_seeded: Session) -> None:
    _, auth = _admin_auth(admin_seeded)
    with pytest.raises(CampaignNotFoundError):
        TestCampaignNoteService(admin_seeded, auth=auth).list_for_campaign(
            "00000000-0000-0000-0000-000000000000"
        )


def test_list_returns_empty_for_new_campaign(admin_seeded: Session) -> None:
    cid = _create_campaign(admin_seeded)
    _, auth = _admin_auth(admin_seeded)
    assert TestCampaignNoteService(admin_seeded, auth=auth).list_for_campaign(cid) == []


# ---- Create + permissions ----------------------------------------------


def test_admin_can_create_note(admin_seeded: Session) -> None:
    cid = _create_campaign(admin_seeded)
    _, auth = _admin_auth(admin_seeded)
    note = TestCampaignNoteService(admin_seeded, auth=auth).create(
        cid, body_md="**Idee:** Strömungsmessung erweitern."
    )
    assert note.body_md.startswith("**Idee:**")
    assert note.is_deleted is False


def test_participant_can_create_note(admin_seeded: Session) -> None:
    cid = _create_campaign(admin_seeded, code="TC-NOTE-PART")
    member = _create_member(admin_seeded, email="np@test.example")
    _add_participant(admin_seeded, cid, member.id)
    note = TestCampaignNoteService(admin_seeded, auth=_participant_auth(member)).create(
        cid, body_md="Beobachtung: Druck schwankt."
    )
    assert note.author_person_id == member.id


def test_non_participant_cannot_create_note(admin_seeded: Session) -> None:
    cid = _create_campaign(admin_seeded, code="TC-NOTE-NOPART")
    outsider = _create_member(admin_seeded, email="out@test.example")
    with pytest.raises(PermissionError):
        TestCampaignNoteService(admin_seeded, auth=_participant_auth(outsider)).create(
            cid, body_md="darf ich nicht"
        )


def test_empty_body_rejected(admin_seeded: Session) -> None:
    cid = _create_campaign(admin_seeded, code="TC-NOTE-EMPTY")
    _, auth = _admin_auth(admin_seeded)
    with pytest.raises(ValueError, match="leer"):
        TestCampaignNoteService(admin_seeded, auth=auth).create(cid, body_md="   ")


def test_too_long_body_rejected(admin_seeded: Session) -> None:
    cid = _create_campaign(admin_seeded, code="TC-NOTE-LONG")
    _, auth = _admin_auth(admin_seeded)
    with pytest.raises(ValueError, match="zu lang"):
        TestCampaignNoteService(admin_seeded, auth=auth).create(
            cid, body_md="x" * (TestCampaignNoteService.MAX_BODY_LEN + 1)
        )


# ---- Update -----------------------------------------------------------


def test_author_can_update_note(admin_seeded: Session) -> None:
    cid = _create_campaign(admin_seeded, code="TC-NOTE-UPD")
    member = _create_member(admin_seeded, email="upd@test.example")
    _add_participant(admin_seeded, cid, member.id)
    auth = _participant_auth(member)
    note = TestCampaignNoteService(admin_seeded, auth=auth).create(cid, body_md="alt")
    updated = TestCampaignNoteService(admin_seeded, auth=auth).update(note.id, body_md="neu")
    assert updated.body_md == "neu"


def test_admin_can_update_foreign_note(admin_seeded: Session) -> None:
    cid = _create_campaign(admin_seeded, code="TC-NOTE-ADMINUPD")
    member = _create_member(admin_seeded, email="someone2@test.example")
    _add_participant(admin_seeded, cid, member.id)
    note = TestCampaignNoteService(admin_seeded, auth=_participant_auth(member)).create(
        cid, body_md="Mitglieder-Notiz"
    )
    _, admin_auth = _admin_auth(admin_seeded)
    updated = TestCampaignNoteService(admin_seeded, auth=admin_auth).update(
        note.id, body_md="vom Admin"
    )
    assert updated.body_md == "vom Admin"


def test_other_participant_cannot_update(admin_seeded: Session) -> None:
    cid = _create_campaign(admin_seeded, code="TC-NOTE-FOREIGN")
    author = _create_member(admin_seeded, email="auth@test.example")
    intruder = _create_member(admin_seeded, email="intr@test.example")
    _add_participant(admin_seeded, cid, author.id)
    _add_participant(admin_seeded, cid, intruder.id)
    note = TestCampaignNoteService(admin_seeded, auth=_participant_auth(author)).create(
        cid, body_md="meins"
    )
    with pytest.raises(PermissionError):
        TestCampaignNoteService(admin_seeded, auth=_participant_auth(intruder)).update(
            note.id, body_md="übergriff"
        )


def test_update_with_same_body_is_noop(admin_seeded: Session) -> None:
    """Audit-Eintrag soll nur bei tatsächlicher Änderung entstehen."""
    from ref4ep.services.audit_logger import AuditLogger

    cid = _create_campaign(admin_seeded, code="TC-NOTE-NOOP")
    _, auth = _admin_auth(admin_seeded)
    audit = AuditLogger(admin_seeded, actor_person_id=auth.person_id)
    service = TestCampaignNoteService(admin_seeded, auth=auth, audit=audit)
    note = service.create(cid, body_md="gleich")
    admin_seeded.commit()
    before_count = admin_seeded.query(AuditLog).filter_by(action="campaign.note.update").count()
    service.update(note.id, body_md="gleich")
    admin_seeded.commit()
    after_count = admin_seeded.query(AuditLog).filter_by(action="campaign.note.update").count()
    assert after_count == before_count


# ---- Soft-Delete -------------------------------------------------------


def test_author_can_soft_delete(admin_seeded: Session) -> None:
    cid = _create_campaign(admin_seeded, code="TC-NOTE-DEL")
    member = _create_member(admin_seeded, email="del@test.example")
    _add_participant(admin_seeded, cid, member.id)
    auth = _participant_auth(member)
    note = TestCampaignNoteService(admin_seeded, auth=auth).create(cid, body_md="weg")
    TestCampaignNoteService(admin_seeded, auth=auth).soft_delete(note.id)
    refreshed = admin_seeded.get(TestCampaignNote, note.id)
    assert refreshed is not None and refreshed.is_deleted is True
    assert TestCampaignNoteService(admin_seeded, auth=auth).list_for_campaign(cid) == []


def test_get_visible_raises_for_deleted(admin_seeded: Session) -> None:
    cid = _create_campaign(admin_seeded, code="TC-NOTE-VIS")
    _, auth = _admin_auth(admin_seeded)
    note = TestCampaignNoteService(admin_seeded, auth=auth).create(cid, body_md="x")
    TestCampaignNoteService(admin_seeded, auth=auth).soft_delete(note.id)
    with pytest.raises(CampaignNoteNotFoundError):
        TestCampaignNoteService(admin_seeded, auth=auth).get_visible(note.id)


# ---- Audit -------------------------------------------------------------


def test_create_emits_audit_entry(admin_seeded: Session) -> None:
    from ref4ep.services.audit_logger import AuditLogger

    cid = _create_campaign(admin_seeded, code="TC-NOTE-AUDIT")
    _, auth = _admin_auth(admin_seeded)
    audit = AuditLogger(admin_seeded, actor_person_id=auth.person_id)
    TestCampaignNoteService(admin_seeded, auth=auth, audit=audit).create(cid, body_md="Audit")
    admin_seeded.commit()
    actions = {row.action for row in admin_seeded.query(AuditLog).all()}
    assert "campaign.note.create" in actions


def test_update_and_delete_emit_audit_entries(admin_seeded: Session) -> None:
    from ref4ep.services.audit_logger import AuditLogger

    cid = _create_campaign(admin_seeded, code="TC-NOTE-AUDIT2")
    _, auth = _admin_auth(admin_seeded)
    audit = AuditLogger(admin_seeded, actor_person_id=auth.person_id)
    service = TestCampaignNoteService(admin_seeded, auth=auth, audit=audit)
    note = service.create(cid, body_md="alt")
    service.update(note.id, body_md="neu")
    service.soft_delete(note.id)
    admin_seeded.commit()
    actions = {row.action for row in admin_seeded.query(AuditLog).all()}
    assert "campaign.note.update" in actions
    assert "campaign.note.delete" in actions


def test_listing_sorts_newest_first(admin_seeded: Session) -> None:
    cid = _create_campaign(admin_seeded, code="TC-NOTE-SORT")
    _, auth = _admin_auth(admin_seeded)
    service = TestCampaignNoteService(admin_seeded, auth=auth)
    n1 = service.create(cid, body_md="erste")
    n2 = service.create(cid, body_md="zweite")
    notes = service.list_for_campaign(cid)
    assert [n.id for n in notes] == [n2.id, n1.id]
