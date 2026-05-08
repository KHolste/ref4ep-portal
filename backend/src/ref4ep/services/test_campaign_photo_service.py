"""Foto-Upload für Testkampagnen (Block 0028).

Eigenständiger Service — bewusst nicht in ``DocumentVersionService``
integriert. Documents sind formale Unterlagen mit Review-Lifecycle,
Photos sind informelle Aufnahmen mit Caption + Soft-Delete.

Berechtigungen:
- Lesen: wer die Kampagne sehen darf (alle eingeloggten Nutzer).
- Upload: ``TestCampaignParticipant`` der Kampagne oder Admin.
- Caption ändern / Löschen: Uploader oder Admin.

Audit-Aktionen: ``campaign.photo.upload`` / ``.update_caption`` / ``.delete``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from ref4ep.domain.models import TestCampaign, TestCampaignPhoto
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.permissions import (
    AuthContext,
    can_admin,
    is_campaign_participant,
)
from ref4ep.services.storage_validation import (
    compute_photo_storage_key,
    validate_photo_mime,
)
from ref4ep.storage import Storage


class CampaignNotFoundError(LookupError):
    """Kampagne existiert nicht oder ist für den Aufrufer unsichtbar."""

    def __init__(self, campaign_id: str) -> None:
        super().__init__(f"Testkampagne {campaign_id} nicht gefunden.")
        self.campaign_id = campaign_id


class CampaignPhotoNotFoundError(LookupError):
    """Foto existiert nicht oder ist soft-deleted."""

    def __init__(self, photo_id: str) -> None:
        super().__init__(f"Foto {photo_id} nicht gefunden.")
        self.photo_id = photo_id


class TestCampaignPhotoService:
    # pytest sammelt sonst diese Klasse als Test-Klasse ein.
    __test__ = False

    def __init__(
        self,
        session: Session,
        *,
        auth: AuthContext | None = None,
        audit: AuditLogger | None = None,
        storage: Storage | None = None,
    ) -> None:
        self.session = session
        self.auth = auth
        self.audit = audit
        self.storage = storage

    # ---- helpers --------------------------------------------------------

    def _is_admin(self) -> bool:
        return self.auth is not None and can_admin(self.auth.platform_role)

    def _is_uploader(self, photo: TestCampaignPhoto) -> bool:
        return self.auth is not None and self.auth.person_id == photo.uploaded_by_person_id

    def _load_campaign(self, campaign_id: str) -> TestCampaign:
        campaign = self.session.get(TestCampaign, campaign_id)
        if campaign is None:
            raise CampaignNotFoundError(campaign_id)
        return campaign

    def _load_visible_photo(self, photo_id: str) -> TestCampaignPhoto:
        photo = self.session.get(TestCampaignPhoto, photo_id)
        if photo is None or photo.is_deleted:
            raise CampaignPhotoNotFoundError(photo_id)
        return photo

    # ---- read -----------------------------------------------------------

    def list_for_campaign(self, campaign_id: str) -> list[TestCampaignPhoto]:
        """Sichtbare Fotos einer Kampagne, neueste zuerst (sortiert
        nach ``taken_at`` falls gesetzt, sonst ``created_at``)."""
        self._load_campaign(campaign_id)  # für Existenz-Check
        stmt = (
            select(TestCampaignPhoto)
            .where(TestCampaignPhoto.campaign_id == campaign_id)
            .where(TestCampaignPhoto.is_deleted.is_(False))
        )
        photos = list(self.session.scalars(stmt))
        photos.sort(
            key=lambda p: (p.taken_at or p.created_at, p.created_at),
            reverse=True,
        )
        return photos

    def get_visible(self, photo_id: str) -> TestCampaignPhoto:
        return self._load_visible_photo(photo_id)

    def open_read_stream(self, photo_id: str) -> tuple[TestCampaignPhoto, BinaryIO]:
        """Liefert Foto + offenen Lese-Stream für Download. Aufrufer
        muss den Stream schließen."""
        if self.storage is None:
            raise RuntimeError("Storage-Backend nicht konfiguriert.")
        photo = self._load_visible_photo(photo_id)
        return photo, self.storage.open_read(photo.storage_key)

    # ---- write ----------------------------------------------------------

    def upload(
        self,
        campaign_id: str,
        *,
        file_stream: BinaryIO,
        original_filename: str,
        mime_type: str,
        caption: str | None = None,
        taken_at: datetime | None = None,
    ) -> TestCampaignPhoto:
        if self.storage is None:
            raise RuntimeError("Storage-Backend nicht konfiguriert.")
        if self.auth is None:
            raise PermissionError("Nicht angemeldet.")

        campaign = self._load_campaign(campaign_id)
        if not is_campaign_participant(self.auth, campaign):
            raise PermissionError(
                "Nur Teilnehmende der Kampagne oder Admin dürfen Fotos hochladen."
            )

        validate_photo_mime(mime_type)

        photo_id = str(uuid.uuid4())
        storage_key = compute_photo_storage_key(campaign_id, photo_id)
        write_result = self.storage.put_stream(storage_key, file_stream)
        if write_result.file_size_bytes <= 0:
            raise ValueError("Datei ist leer.")

        cleaned_caption = (caption or "").strip() or None
        cleaned_filename = (original_filename or "").strip() or "unbenannt"

        photo = TestCampaignPhoto(
            id=photo_id,
            campaign_id=campaign_id,
            uploaded_by_person_id=self.auth.person_id,
            storage_key=storage_key,
            original_filename=cleaned_filename,
            mime_type=mime_type,
            file_size_bytes=write_result.file_size_bytes,
            sha256=write_result.sha256,
            caption=cleaned_caption,
            taken_at=taken_at,
        )
        self.session.add(photo)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "campaign.photo.upload",
                entity_type="test_campaign_photo",
                entity_id=photo.id,
                after={
                    "campaign_id": campaign_id,
                    "original_filename": photo.original_filename,
                    "mime_type": photo.mime_type,
                    "file_size_bytes": photo.file_size_bytes,
                    "sha256": photo.sha256,
                    "caption": photo.caption,
                    "taken_at": photo.taken_at,
                },
            )
        return photo

    def update_caption(self, photo_id: str, *, caption: str | None) -> TestCampaignPhoto:
        photo = self._load_visible_photo(photo_id)
        if not (self._is_admin() or self._is_uploader(photo)):
            raise PermissionError("Nur Uploader oder Admin dürfen die Caption ändern.")
        before = photo.caption
        new_caption = (caption or "").strip() or None
        photo.caption = new_caption
        self.session.flush()
        if self.audit is not None and before != photo.caption:
            self.audit.log(
                "campaign.photo.update_caption",
                entity_type="test_campaign_photo",
                entity_id=photo.id,
                before={"caption": before},
                after={"caption": photo.caption},
            )
        return photo

    def soft_delete(self, photo_id: str) -> None:
        photo = self._load_visible_photo(photo_id)
        if not (self._is_admin() or self._is_uploader(photo)):
            raise PermissionError("Nur Uploader oder Admin dürfen das Foto löschen.")
        photo.is_deleted = True
        photo.updated_at = datetime.now(tz=UTC)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "campaign.photo.delete",
                entity_type="test_campaign_photo",
                entity_id=photo.id,
                before={"is_deleted": False},
                after={"is_deleted": True},
            )
