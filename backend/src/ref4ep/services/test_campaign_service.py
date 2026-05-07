"""Testkampagnenregister (Block 0022).

Service kapselt CRUD für ``TestCampaign``, die m:n-Verknüpfung mit
Workpackages, beteiligte Personen (``TestCampaignParticipant`` mit
Rolle) und Dokumentverknüpfungen (``TestCampaignDocumentLink``, nur
Verknüpfung — kein Upload).

Berechtigungslogik (analog ``MeetingService``):
- Admin: alles.
- WP-Lead: anlegen/bearbeiten gdw. **alle** Kampagnen-WPs eigene
  Lead-WPs sind. Konsortiumsweite Kampagnen ohne WP-Bezug sind
  Admin-only.
- Member: nur lesen.

Cancel über ``status='cancelled'``; **kein** Hard-Delete in diesem Block.
Audit-Aktionen:
- ``campaign.create`` / ``campaign.update`` / ``campaign.cancel``
- ``campaign.participant.add`` / ``.update`` / ``.remove``
- ``campaign.document_link.add`` / ``.remove``
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ref4ep.domain.models import (
    TEST_CAMPAIGN_CATEGORIES,
    TEST_CAMPAIGN_DOCUMENT_LABELS,
    TEST_CAMPAIGN_PARTICIPANT_ROLES,
    TEST_CAMPAIGN_STATUSES,
    Document,
    Membership,
    Person,
    TestCampaign,
    TestCampaignDocumentLink,
    TestCampaignParticipant,
    TestCampaignWorkpackage,
    Workpackage,
)
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.permissions import can_admin
from ref4ep.services.validators import normalise_text


def _filter_workpackage_ids(session: Session, workpackage_ids: Iterable[str]) -> list[str]:
    """Verifiziert, dass alle WP-IDs existieren und nicht gelöscht sind."""
    seen: list[str] = []
    seen_set: set[str] = set()
    for wp_id in workpackage_ids:
        if wp_id in seen_set:
            continue
        wp = session.get(Workpackage, wp_id)
        if wp is None or wp.is_deleted:
            raise LookupError(f"Workpackage {wp_id} nicht gefunden.")
        seen.append(wp_id)
        seen_set.add(wp_id)
    return seen


class TestCampaignService:
    # pytest sammelt sonst diese Klasse als Test-Klasse ein (Name beginnt mit „Test").
    __test__ = False

    def __init__(
        self,
        session: Session,
        *,
        role: str | None = None,
        person_id: str | None = None,
        audit: AuditLogger | None = None,
    ) -> None:
        self.session = session
        self.role = role
        self.person_id = person_id
        self.audit = audit

    # ---- Lese-Helfer ----------------------------------------------------

    def get(self, campaign_id: str) -> TestCampaign | None:
        return self.session.get(TestCampaign, campaign_id)

    def get_by_code(self, code: str) -> TestCampaign | None:
        return self.session.scalars(select(TestCampaign).where(TestCampaign.code == code)).first()

    def list_campaigns(
        self,
        *,
        status: str | None = None,
        category: str | None = None,
        workpackage_code: str | None = None,
        q: str | None = None,
    ) -> list[TestCampaign]:
        stmt = select(TestCampaign)
        if status is not None:
            if status not in TEST_CAMPAIGN_STATUSES:
                raise ValueError(f"status: ungültiger Wert {status!r}")
            stmt = stmt.where(TestCampaign.status == status)
        if category is not None:
            if category not in TEST_CAMPAIGN_CATEGORIES:
                raise ValueError(f"category: ungültiger Wert {category!r}")
            stmt = stmt.where(TestCampaign.category == category)
        if workpackage_code is not None:
            wp = self.session.scalars(
                select(Workpackage).where(Workpackage.code == workpackage_code)
            ).first()
            if wp is None:
                return []
            stmt = stmt.where(
                TestCampaign.id.in_(
                    select(TestCampaignWorkpackage.campaign_id).where(
                        TestCampaignWorkpackage.workpackage_id == wp.id
                    )
                )
            )
        if q:
            term = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    TestCampaign.code.ilike(term),
                    TestCampaign.title.ilike(term),
                    TestCampaign.facility.ilike(term),
                )
            )
        stmt = stmt.order_by(TestCampaign.starts_on.desc(), TestCampaign.title)
        return list(self.session.scalars(stmt))

    # ---- Berechtigung ---------------------------------------------------

    def _is_admin(self) -> bool:
        return can_admin(self.role or "")

    def _own_lead_wp_ids(self) -> set[str]:
        if not self.person_id:
            return set()
        rows = self.session.scalars(
            select(Membership.workpackage_id).where(
                Membership.person_id == self.person_id,
                Membership.wp_role == "wp_lead",
            )
        ).all()
        return set(rows)

    def can_edit_campaign(self, campaign: TestCampaign) -> bool:
        """- Admin: ja.
        - WP-Lead: nur, wenn Kampagne mind. eine WP hat **und** alle
          WPs zu seinen Lead-WPs gehören.
        - sonst: nein.
        """
        if self._is_admin():
            return True
        if not self.person_id:
            return False
        wp_ids = {link.workpackage_id for link in campaign.workpackage_links}
        if not wp_ids:
            return False
        own = self._own_lead_wp_ids()
        return wp_ids.issubset(own) and bool(own & wp_ids)

    def can_create_campaign_with_workpackages(self, workpackage_ids: Iterable[str]) -> bool:
        ids = set(workpackage_ids)
        if self._is_admin():
            return True
        if not ids:
            return False
        own = self._own_lead_wp_ids()
        return ids.issubset(own)

    # ---- Validierung ----------------------------------------------------

    def _validate_fields(self, *, category: str, status: str) -> None:
        if category not in TEST_CAMPAIGN_CATEGORIES:
            raise ValueError(f"category: ungültiger Wert {category!r}")
        if status not in TEST_CAMPAIGN_STATUSES:
            raise ValueError(f"status: ungültiger Wert {status!r}")

    @staticmethod
    def _normalise_code(code: str) -> str:
        cleaned = (code or "").strip()
        if not cleaned:
            raise ValueError("code darf nicht leer sein.")
        return cleaned

    # ---- Schreiben — Kampagne -------------------------------------------

    def create_campaign(
        self,
        *,
        code: str,
        title: str,
        starts_on: date,
        ends_on: date | None = None,
        category: str = "other",
        status: str = "planned",
        facility: str | None = None,
        location: str | None = None,
        short_description: str | None = None,
        objective: str | None = None,
        test_matrix: str | None = None,
        expected_measurements: str | None = None,
        boundary_conditions: str | None = None,
        success_criteria: str | None = None,
        risks_or_open_points: str | None = None,
        workpackage_ids: list[str] | None = None,
    ) -> TestCampaign:
        if not self.person_id:
            raise PermissionError("Anonymer Aufruf — Anlegen nicht erlaubt.")
        wp_ids = _filter_workpackage_ids(self.session, workpackage_ids or [])
        if not self.can_create_campaign_with_workpackages(wp_ids):
            raise PermissionError(
                "Nur Admin oder WP-Lead aller genannten Arbeitspakete darf eine "
                "Testkampagne anlegen."
            )
        self._validate_fields(category=category, status=status)
        code_clean = self._normalise_code(code)
        if self.get_by_code(code_clean) is not None:
            raise ValueError(f"code {code_clean!r} existiert bereits.")
        title_clean = (title or "").strip()
        if not title_clean:
            raise ValueError("title darf nicht leer sein.")
        if ends_on is not None and ends_on < starts_on:
            raise ValueError("ends_on darf nicht vor starts_on liegen.")

        campaign = TestCampaign(
            code=code_clean,
            title=title_clean,
            category=category,
            status=status,
            starts_on=starts_on,
            ends_on=ends_on,
            facility=normalise_text(facility),
            location=normalise_text(location),
            short_description=normalise_text(short_description),
            objective=normalise_text(objective),
            test_matrix=normalise_text(test_matrix),
            expected_measurements=normalise_text(expected_measurements),
            boundary_conditions=normalise_text(boundary_conditions),
            success_criteria=normalise_text(success_criteria),
            risks_or_open_points=normalise_text(risks_or_open_points),
            created_by_id=self.person_id,
        )
        self.session.add(campaign)
        self.session.flush()
        for wp_id in wp_ids:
            self.session.add(TestCampaignWorkpackage(campaign_id=campaign.id, workpackage_id=wp_id))
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "campaign.create",
                entity_type="test_campaign",
                entity_id=campaign.id,
                after={
                    "code": campaign.code,
                    "title": campaign.title,
                    "category": campaign.category,
                    "status": campaign.status,
                    "starts_on": campaign.starts_on.isoformat(),
                    "workpackage_ids": wp_ids,
                },
            )
        return campaign

    def update_campaign(
        self,
        campaign_id: str,
        *,
        fields: dict[str, object],
        workpackage_ids: list[str] | None = None,
    ) -> TestCampaign:
        campaign = self.get(campaign_id)
        if campaign is None:
            raise LookupError(f"Testkampagne {campaign_id} nicht gefunden.")
        if not self.can_edit_campaign(campaign):
            raise PermissionError(
                "Kein Schreibrecht — Admin oder Lead aller beteiligten WPs nötig."
            )
        before = self._snapshot(campaign)

        if workpackage_ids is not None:
            new_ids = _filter_workpackage_ids(self.session, workpackage_ids)
            if not self.can_create_campaign_with_workpackages(new_ids):
                raise PermissionError("WP-Lead darf nur eigene Lead-WPs setzen.")
            current = {link.workpackage_id for link in campaign.workpackage_links}
            target = set(new_ids)
            for link in list(campaign.workpackage_links):
                if link.workpackage_id not in target:
                    self.session.delete(link)
            for wp_id in new_ids:
                if wp_id not in current:
                    self.session.add(
                        TestCampaignWorkpackage(campaign_id=campaign.id, workpackage_id=wp_id)
                    )

        for key, raw in fields.items():
            if key not in {
                "code",
                "title",
                "category",
                "status",
                "starts_on",
                "ends_on",
                "facility",
                "location",
                "short_description",
                "objective",
                "test_matrix",
                "expected_measurements",
                "boundary_conditions",
                "success_criteria",
                "risks_or_open_points",
            }:
                continue
            value = raw
            if isinstance(value, str):
                value = normalise_text(value)
            if key == "code":
                if not value:
                    raise ValueError("code darf nicht leer sein.")
                # Code darf wechseln, aber nur auf einen freien.
                if value != campaign.code:
                    other = self.get_by_code(value)
                    if other is not None and other.id != campaign.id:
                        raise ValueError(f"code {value!r} existiert bereits.")
            if key == "title" and not value:
                raise ValueError("title darf nicht leer sein.")
            if key == "category" and value is not None and value not in TEST_CAMPAIGN_CATEGORIES:
                raise ValueError(f"category: ungültiger Wert {raw!r}")
            if key == "status" and value is not None and value not in TEST_CAMPAIGN_STATUSES:
                raise ValueError(f"status: ungültiger Wert {raw!r}")
            setattr(campaign, key, value)
        # Bereichs-Plausibilität nach dem Setzen prüfen (starts_on/ends_on
        # können in beliebiger Reihenfolge im fields-dict liegen).
        if (
            campaign.ends_on is not None
            and campaign.starts_on is not None
            and campaign.ends_on < campaign.starts_on
        ):
            raise ValueError("ends_on darf nicht vor starts_on liegen.")
        self.session.flush()
        after = self._snapshot(campaign)
        if self.audit is not None and after != before:
            self.audit.log(
                "campaign.update",
                entity_type="test_campaign",
                entity_id=campaign.id,
                before=before,
                after=after,
            )
        return campaign

    def cancel_campaign(self, campaign_id: str) -> TestCampaign:
        campaign = self.get(campaign_id)
        if campaign is None:
            raise LookupError(f"Testkampagne {campaign_id} nicht gefunden.")
        if not self.can_edit_campaign(campaign):
            raise PermissionError("Kein Schreibrecht für diese Kampagne.")
        if campaign.status == "cancelled":
            return campaign
        before = {"status": campaign.status}
        campaign.status = "cancelled"
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "campaign.cancel",
                entity_type="test_campaign",
                entity_id=campaign.id,
                before=before,
                after={"status": campaign.status},
            )
        return campaign

    def _snapshot(self, campaign: TestCampaign) -> dict[str, object]:
        return {
            "code": campaign.code,
            "title": campaign.title,
            "category": campaign.category,
            "status": campaign.status,
            "starts_on": campaign.starts_on.isoformat() if campaign.starts_on else None,
            "ends_on": campaign.ends_on.isoformat() if campaign.ends_on else None,
            "facility": campaign.facility,
            "location": campaign.location,
            "workpackage_ids": sorted(link.workpackage_id for link in campaign.workpackage_links),
        }

    # ---- Teilnehmende ---------------------------------------------------

    def add_participant(
        self,
        campaign_id: str,
        *,
        person_id: str,
        role: str = "other",
        note: str | None = None,
    ) -> TestCampaignParticipant:
        campaign = self.get(campaign_id)
        if campaign is None:
            raise LookupError(f"Testkampagne {campaign_id} nicht gefunden.")
        if not self.can_edit_campaign(campaign):
            raise PermissionError("Kein Schreibrecht für diese Kampagne.")
        if role not in TEST_CAMPAIGN_PARTICIPANT_ROLES:
            raise ValueError(f"role: ungültiger Wert {role!r}")
        person = self.session.get(Person, person_id)
        if person is None or person.is_deleted:
            raise LookupError(f"Person {person_id} nicht gefunden.")
        existing = self.session.scalars(
            select(TestCampaignParticipant).where(
                TestCampaignParticipant.campaign_id == campaign_id,
                TestCampaignParticipant.person_id == person_id,
            )
        ).first()
        if existing is not None:
            return existing
        participant = TestCampaignParticipant(
            campaign_id=campaign_id,
            person_id=person_id,
            role=role,
            note=normalise_text(note),
        )
        self.session.add(participant)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "campaign.participant.add",
                entity_type="test_campaign",
                entity_id=campaign_id,
                after={"person_id": person_id, "role": role},
            )
        return participant

    def update_participant(
        self,
        participant_id: str,
        *,
        fields: dict[str, object],
    ) -> TestCampaignParticipant:
        participant = self.session.get(TestCampaignParticipant, participant_id)
        if participant is None:
            raise LookupError(f"Teilnehmender {participant_id} nicht gefunden.")
        if not self.can_edit_campaign(participant.campaign):
            raise PermissionError("Kein Schreibrecht für diese Kampagne.")
        before = {"role": participant.role, "note": participant.note}
        for key, raw in fields.items():
            if key not in {"role", "note"}:
                continue
            value = raw
            if isinstance(value, str):
                value = normalise_text(value)
            if key == "role":
                if value not in TEST_CAMPAIGN_PARTICIPANT_ROLES:
                    raise ValueError(f"role: ungültiger Wert {raw!r}")
            setattr(participant, key, value)
        self.session.flush()
        after = {"role": participant.role, "note": participant.note}
        if self.audit is not None and after != before:
            self.audit.log(
                "campaign.participant.update",
                entity_type="test_campaign",
                entity_id=participant.campaign_id,
                before=before,
                after=after,
            )
        return participant

    def remove_participant(self, participant_id: str) -> None:
        participant = self.session.get(TestCampaignParticipant, participant_id)
        if participant is None:
            return
        if not self.can_edit_campaign(participant.campaign):
            raise PermissionError("Kein Schreibrecht für diese Kampagne.")
        snapshot = {
            "person_id": participant.person_id,
            "role": participant.role,
        }
        campaign_id = participant.campaign_id
        self.session.delete(participant)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "campaign.participant.remove",
                entity_type="test_campaign",
                entity_id=campaign_id,
                before=snapshot,
            )

    # ---- Dokumentverknüpfungen -----------------------------------------

    def list_links_for_document(self, document_id: str) -> list[TestCampaignDocumentLink]:
        """Alle Kampagnenverknüpfungen eines Dokuments. Liest nur."""
        stmt = (
            select(TestCampaignDocumentLink)
            .join(TestCampaign, TestCampaign.id == TestCampaignDocumentLink.campaign_id)
            .where(TestCampaignDocumentLink.document_id == document_id)
            .order_by(TestCampaign.starts_on.desc(), TestCampaign.title)
        )
        return list(self.session.scalars(stmt))

    def _persist_document_link(
        self,
        campaign_id: str,
        *,
        document_id: str,
        label: str,
    ) -> TestCampaignDocumentLink:
        """Insert/Upsert + Audit. Aufrufer hat Permission und Existenz
        bereits geprüft.
        """
        if label not in TEST_CAMPAIGN_DOCUMENT_LABELS:
            raise ValueError(f"label: ungültiger Wert {label!r}")
        existing = self.session.get(TestCampaignDocumentLink, (campaign_id, document_id))
        if existing is not None:
            if existing.label != label:
                before = {"label": existing.label}
                existing.label = label
                self.session.flush()
                if self.audit is not None:
                    self.audit.log(
                        "campaign.document_link.add",
                        entity_type="test_campaign",
                        entity_id=campaign_id,
                        before=before,
                        after={"document_id": document_id, "label": label},
                    )
            return existing
        link = TestCampaignDocumentLink(
            campaign_id=campaign_id, document_id=document_id, label=label
        )
        self.session.add(link)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "campaign.document_link.add",
                entity_type="test_campaign",
                entity_id=campaign_id,
                after={"document_id": document_id, "label": label},
            )
        return link

    def add_document_link(
        self,
        campaign_id: str,
        *,
        document_id: str,
        label: str = "other",
    ) -> TestCampaignDocumentLink:
        """Eintrittspunkt von der Kampagnen-Seite: erfordert
        ``can_edit_campaign``."""
        campaign = self.get(campaign_id)
        if campaign is None:
            raise LookupError(f"Testkampagne {campaign_id} nicht gefunden.")
        if not self.can_edit_campaign(campaign):
            raise PermissionError("Kein Schreibrecht für diese Kampagne.")
        doc = self.session.get(Document, document_id)
        if doc is None or doc.is_deleted:
            raise LookupError(f"Dokument {document_id} nicht gefunden.")
        return self._persist_document_link(campaign_id, document_id=document_id, label=label)

    def link_document(
        self,
        document: Document,
        *,
        campaign_id: str,
        label: str = "other",
    ) -> TestCampaignDocumentLink:
        """Eintrittspunkt von der Dokument-Seite. Erwartet ein bereits
        geladenes, schreibbares Dokument; die Berechtigung am Dokument
        muss vom Aufrufer geprüft sein.

        Invariante: Workpackage des Dokuments muss zur WP-Menge der
        Kampagne gehören. Sonst ``ValueError``.
        """
        campaign = self.get(campaign_id)
        if campaign is None:
            raise LookupError(f"Testkampagne {campaign_id} nicht gefunden.")
        campaign_wp_ids = {link.workpackage_id for link in campaign.workpackage_links}
        if document.workpackage_id not in campaign_wp_ids:
            raise ValueError("Dokument-Workpackage gehört nicht zur Kampagne.")
        return self._persist_document_link(campaign_id, document_id=document.id, label=label)

    def remove_document_link(self, campaign_id: str, document_id: str) -> None:
        """Eintrittspunkt von der Kampagnen-Seite: erfordert
        ``can_edit_campaign``."""
        campaign = self.get(campaign_id)
        if campaign is None:
            raise LookupError(f"Testkampagne {campaign_id} nicht gefunden.")
        if not self.can_edit_campaign(campaign):
            raise PermissionError("Kein Schreibrecht für diese Kampagne.")
        existing = self.session.get(TestCampaignDocumentLink, (campaign_id, document_id))
        if existing is None:
            return
        label = existing.label
        self.session.delete(existing)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "campaign.document_link.remove",
                entity_type="test_campaign",
                entity_id=campaign_id,
                before={"document_id": document_id, "label": label},
            )

    def unlink_document(self, document: Document, *, campaign_id: str) -> None:
        """Eintrittspunkt von der Dokument-Seite. Berechtigung am Dokument
        muss vom Aufrufer geprüft sein.
        """
        campaign = self.get(campaign_id)
        if campaign is None:
            raise LookupError(f"Testkampagne {campaign_id} nicht gefunden.")
        existing = self.session.get(TestCampaignDocumentLink, (campaign_id, document.id))
        if existing is None:
            return
        label = existing.label
        self.session.delete(existing)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "campaign.document_link.remove",
                entity_type="test_campaign",
                entity_id=campaign_id,
                before={"document_id": document.id, "label": label},
            )
