"""Service: ContactDirectoryService (Block 0053).

Deckt die Randfälle ab, die über die API schwer herzustellen sind:
gelöschte Partner, deaktivierte Personen, Kontakte ohne E-Mail.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ref4ep.services.contact_directory_service import ContactDirectoryService
from ref4ep.services.partner_contact_service import PartnerContactService
from ref4ep.services.partner_service import PartnerService
from ref4ep.services.person_service import PersonService

PASSWORD = "D1rectoryP4ss!"


def _partners(session: Session) -> PartnerService:
    return PartnerService(session, role="admin", person_id="fixture")


def _persons(session: Session) -> PersonService:
    return PersonService(session, role="admin", person_id="fixture")


def _contacts(session: Session) -> PartnerContactService:
    return PartnerContactService(session, role="admin", person_id="fixture")


def _names(entries) -> set[str]:
    return {e.name for e in entries}


def test_contacts_of_soft_deleted_partner_are_hidden(seeded_session: Session) -> None:
    partner = _partners(seeded_session).create(
        name="Verlassene Einrichtung", short_name="GONE", country="DE"
    )
    _contacts(seeded_session).create(partner_id=partner.id, name="Verwaister Kontakt")
    seeded_session.commit()

    entries = ContactDirectoryService(seeded_session).list_entries()
    assert "Verwaister Kontakt" in _names(entries)

    _partners(seeded_session).soft_delete(partner.id)
    seeded_session.commit()

    entries = ContactDirectoryService(seeded_session).list_entries()
    assert "Verwaister Kontakt" not in _names(entries)


def test_deactivated_account_only_visible_with_include_inactive(
    seeded_session: Session,
) -> None:
    partner = _partners(seeded_session).get_by_short_name("JLU")
    assert partner is not None
    person = _persons(seeded_session).create(
        email="ruhend@test.example",
        display_name="Ruhendes Konto",
        partner_id=partner.id,
        password=PASSWORD,
    )
    _persons(seeded_session).disable(person.id)
    seeded_session.commit()

    service = ContactDirectoryService(seeded_session)
    assert "Ruhendes Konto" not in _names(service.list_entries())
    assert "Ruhendes Konto" in _names(service.list_entries(include_inactive=True))


def test_contacts_without_email_are_never_merged(seeded_session: Session) -> None:
    """Ohne E-Mail gibt es keinen Abgleich — zwei namenlose Treffer
    dürfen nicht zufällig zu einem Eintrag verschmelzen."""
    partner = _partners(seeded_session).get_by_short_name("JLU")
    assert partner is not None
    svc = _contacts(seeded_session)
    svc.create(partner_id=partner.id, name="Ohne Mail A")
    svc.create(partner_id=partner.id, name="Ohne Mail B")
    seeded_session.commit()

    entries = ContactDirectoryService(seeded_session).list_entries()
    without_mail = [e for e in entries if e.name.startswith("Ohne Mail")]
    assert len(without_mail) == 2
    assert all(e.sources == ["contact"] for e in without_mail)
    assert all(e.person_id is None for e in without_mail)


def test_merged_entry_keeps_contact_fields_and_gains_memberships(
    seeded_session: Session, member_person_id: str, member_in_wp3: str
) -> None:
    from tests.conftest import MEMBER_EMAIL

    partner = _partners(seeded_session).get_by_short_name("JLU")
    assert partner is not None
    _contacts(seeded_session).create(
        partner_id=partner.id,
        name="Gepflegter Name",
        email=MEMBER_EMAIL,
        phone="+49 641 99-2",
        function="Postdoc",
    )
    seeded_session.commit()

    entries = ContactDirectoryService(seeded_session).list_entries()
    merged = [e for e in entries if (e.email or "").lower() == MEMBER_EMAIL]
    assert len(merged) == 1
    entry = merged[0]
    assert entry.name == "Gepflegter Name"
    assert entry.phone == "+49 641 99-2"
    assert entry.function == "Postdoc"
    assert entry.is_portal_user is True
    assert entry.person_id == member_person_id
    assert {wp.code for wp in entry.workpackages} == {"WP3"}


def test_entries_are_sorted_by_partner_then_name(seeded_session: Session) -> None:
    entries = ContactDirectoryService(seeded_session).list_entries()
    keys = [(e.partner.short_name.lower(), e.name.lower()) for e in entries]
    assert keys == sorted(keys)
