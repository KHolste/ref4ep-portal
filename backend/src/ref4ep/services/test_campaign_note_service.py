"""Kampagnennotizen für Testkampagnen (Block 0029).

Niedrigschwellige Arbeitsnotizen / Brainstorming-Notizen — bewusst
KEIN Laborbuch und kein Document-Subtyp. Markdown-Body, Autor und
Soft-Delete; keine Versionierung, kein Review-/Release-Lifecycle.

Berechtigungen:
- Lesen: alle eingeloggten Nutzer (auth-only über die API).
- Erstellen: Kampagnenteilnehmer + Admin (gleiche Regel wie
  Foto-Upload aus Block 0028 — bestehender Helfer wird wiederverwendet).
- Bearbeiten / Löschen: Autor + Admin.

Audit-Aktionen: ``campaign.note.create`` / ``.update`` / ``.delete``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ref4ep.domain.models import TestCampaign, TestCampaignNote
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.permissions import (
    AuthContext,
    can_admin,
    is_campaign_participant,
)


class CampaignNotFoundError(LookupError):
    """Kampagne existiert nicht."""

    def __init__(self, campaign_id: str) -> None:
        super().__init__(f"Testkampagne {campaign_id} nicht gefunden.")
        self.campaign_id = campaign_id


class CampaignNoteNotFoundError(LookupError):
    """Notiz existiert nicht oder ist soft-deleted."""

    def __init__(self, note_id: str) -> None:
        super().__init__(f"Kampagnennotiz {note_id} nicht gefunden.")
        self.note_id = note_id


class TestCampaignNoteService:
    # pytest sammelt sonst diese Klasse als Test-Klasse ein.
    __test__ = False

    MAX_BODY_LEN = 20_000

    def __init__(
        self,
        session: Session,
        *,
        auth: AuthContext | None = None,
        audit: AuditLogger | None = None,
    ) -> None:
        self.session = session
        self.auth = auth
        self.audit = audit

    # ---- helpers --------------------------------------------------------

    def _is_admin(self) -> bool:
        return self.auth is not None and can_admin(self.auth.platform_role)

    def _is_author(self, note: TestCampaignNote) -> bool:
        return self.auth is not None and self.auth.person_id == note.author_person_id

    def _load_campaign(self, campaign_id: str) -> TestCampaign:
        campaign = self.session.get(TestCampaign, campaign_id)
        if campaign is None:
            raise CampaignNotFoundError(campaign_id)
        return campaign

    def _load_visible_note(self, note_id: str) -> TestCampaignNote:
        note = self.session.get(TestCampaignNote, note_id)
        if note is None or note.is_deleted:
            raise CampaignNoteNotFoundError(note_id)
        return note

    @staticmethod
    def _clean_body(body: str | None) -> str:
        cleaned = (body or "").strip()
        if not cleaned:
            raise ValueError("Notiz darf nicht leer sein.")
        if len(cleaned) > TestCampaignNoteService.MAX_BODY_LEN:
            raise ValueError(
                f"Notiz zu lang: {len(cleaned)} Zeichen "
                f"(Limit {TestCampaignNoteService.MAX_BODY_LEN})."
            )
        return cleaned

    # ---- read -----------------------------------------------------------

    def list_for_campaign(self, campaign_id: str) -> list[TestCampaignNote]:
        """Sichtbare Notizen einer Kampagne, neueste zuerst."""
        self._load_campaign(campaign_id)  # Existenz-Check
        stmt = (
            select(TestCampaignNote)
            .where(TestCampaignNote.campaign_id == campaign_id)
            .where(TestCampaignNote.is_deleted.is_(False))
            .order_by(TestCampaignNote.created_at.desc())
        )
        return list(self.session.scalars(stmt))

    def get_visible(self, note_id: str) -> TestCampaignNote:
        return self._load_visible_note(note_id)

    # ---- write ----------------------------------------------------------

    def create(self, campaign_id: str, *, body_md: str) -> TestCampaignNote:
        if self.auth is None:
            raise PermissionError("Nicht angemeldet.")
        campaign = self._load_campaign(campaign_id)
        if not is_campaign_participant(self.auth, campaign):
            raise PermissionError(
                "Nur Teilnehmende der Kampagne oder Admin dürfen Notizen anlegen."
            )

        cleaned = self._clean_body(body_md)
        note = TestCampaignNote(
            id=str(uuid.uuid4()),
            campaign_id=campaign_id,
            author_person_id=self.auth.person_id,
            body_md=cleaned,
        )
        self.session.add(note)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "campaign.note.create",
                entity_type="test_campaign_note",
                entity_id=note.id,
                after={"campaign_id": campaign_id, "body_md": note.body_md},
            )
        return note

    def update(self, note_id: str, *, body_md: str) -> TestCampaignNote:
        note = self._load_visible_note(note_id)
        if not (self._is_admin() or self._is_author(note)):
            raise PermissionError("Nur Autor oder Admin dürfen die Notiz bearbeiten.")
        cleaned = self._clean_body(body_md)
        before = note.body_md
        if cleaned == before:
            # Nichts zu tun — auch kein Audit-Eintrag.
            return note
        note.body_md = cleaned
        note.updated_at = datetime.now(tz=UTC)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "campaign.note.update",
                entity_type="test_campaign_note",
                entity_id=note.id,
                before={"body_md": before},
                after={"body_md": note.body_md},
            )
        return note

    def soft_delete(self, note_id: str) -> None:
        note = self._load_visible_note(note_id)
        if not (self._is_admin() or self._is_author(note)):
            raise PermissionError("Nur Autor oder Admin dürfen die Notiz löschen.")
        note.is_deleted = True
        note.updated_at = datetime.now(tz=UTC)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "campaign.note.delete",
                entity_type="test_campaign_note",
                entity_id=note.id,
                before={"is_deleted": False},
                after={"is_deleted": True},
            )
