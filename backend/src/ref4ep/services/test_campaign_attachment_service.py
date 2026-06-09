"""Datei-Anhänge für Testkampagnen (Block 0044).

Eigenständiger Service — bewusst nicht in ``DocumentVersionService``
integriert (Documents sind formale Unterlagen mit Review-Lifecycle)
und auch nicht in ``TestCampaignPhotoService`` (nur PNG/JPEG).
Anhänge sind beliebige Beilagen (PDF, CSV, Office, Bilder) mit
optionaler Beschreibung und Soft-Delete. Für Bild-MIME-Typen wird ein
Thumbnail erzeugt; bei anderen Typen bleiben die Thumbnail-Felder NULL.

Berechtigungen:
- Lesen: wer die Kampagne sehen darf (alle eingeloggten Nutzer).
- Upload: ``TestCampaignParticipant`` der Kampagne oder Admin.
- Beschreibung ändern / Löschen: Uploader oder Admin.

Audit-Aktionen: ``campaign.attachment.upload`` /
``.update_description`` / ``.delete``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from io import BytesIO
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from ref4ep.domain.models import TestCampaign, TestCampaignAttachment
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.image_thumbnail import ThumbnailError, generate_thumbnail
from ref4ep.services.permissions import (
    AuthContext,
    can_admin,
    is_campaign_participant,
)
from ref4ep.services.storage_validation import (
    attachment_has_thumbnail_support,
    compute_attachment_storage_key,
    compute_attachment_thumbnail_storage_key,
    validate_attachment_mime,
)
from ref4ep.storage import Storage


class CampaignNotFoundError(LookupError):
    """Kampagne existiert nicht oder ist für den Aufrufer unsichtbar."""

    def __init__(self, campaign_id: str) -> None:
        super().__init__(f"Testkampagne {campaign_id} nicht gefunden.")
        self.campaign_id = campaign_id


class CampaignAttachmentNotFoundError(LookupError):
    """Anhang existiert nicht oder ist soft-deleted."""

    def __init__(self, attachment_id: str) -> None:
        super().__init__(f"Anhang {attachment_id} nicht gefunden.")
        self.attachment_id = attachment_id


class TestCampaignAttachmentService:
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

    def _is_uploader(self, attachment: TestCampaignAttachment) -> bool:
        return self.auth is not None and self.auth.person_id == attachment.uploaded_by_person_id

    def _load_campaign(self, campaign_id: str) -> TestCampaign:
        campaign = self.session.get(TestCampaign, campaign_id)
        if campaign is None:
            raise CampaignNotFoundError(campaign_id)
        return campaign

    def _load_visible_attachment(self, attachment_id: str) -> TestCampaignAttachment:
        attachment = self.session.get(TestCampaignAttachment, attachment_id)
        if attachment is None or attachment.is_deleted:
            raise CampaignAttachmentNotFoundError(attachment_id)
        return attachment

    # ---- read -----------------------------------------------------------

    def list_for_campaign(self, campaign_id: str) -> list[TestCampaignAttachment]:
        """Sichtbare Anhänge einer Kampagne, neueste zuerst."""
        self._load_campaign(campaign_id)  # für Existenz-Check
        stmt = (
            select(TestCampaignAttachment)
            .where(TestCampaignAttachment.campaign_id == campaign_id)
            .where(TestCampaignAttachment.is_deleted.is_(False))
        )
        attachments = list(self.session.scalars(stmt))
        attachments.sort(key=lambda a: a.created_at, reverse=True)
        return attachments

    def get_visible(self, attachment_id: str) -> TestCampaignAttachment:
        return self._load_visible_attachment(attachment_id)

    def open_read_stream(self, attachment_id: str) -> tuple[TestCampaignAttachment, BinaryIO]:
        """Liefert Anhang + offenen Lese-Stream für Download. Aufrufer
        muss den Stream schließen."""
        if self.storage is None:
            raise RuntimeError("Storage-Backend nicht konfiguriert.")
        attachment = self._load_visible_attachment(attachment_id)
        return attachment, self.storage.open_read(attachment.storage_key)

    def open_thumbnail_stream(
        self, attachment_id: str
    ) -> tuple[TestCampaignAttachment, BinaryIO, str, int, bool]:
        """Liefert ``(attachment, stream, mime_type, size_bytes, is_thumbnail)``.

        Hat der Anhang kein Thumbnail-Artefakt (z. B. PDF/CSV/Office),
        wird das Original zurückgegeben (``is_thumbnail=False``).
        """
        if self.storage is None:
            raise RuntimeError("Storage-Backend nicht konfiguriert.")
        attachment = self._load_visible_attachment(attachment_id)
        if attachment.thumbnail_storage_key:
            return (
                attachment,
                self.storage.open_read(attachment.thumbnail_storage_key),
                attachment.thumbnail_mime_type or attachment.mime_type,
                attachment.thumbnail_size_bytes or attachment.file_size_bytes,
                True,
            )
        return (
            attachment,
            self.storage.open_read(attachment.storage_key),
            attachment.mime_type,
            attachment.file_size_bytes,
            False,
        )

    # ---- write ----------------------------------------------------------

    def upload(
        self,
        campaign_id: str,
        *,
        file_stream: BinaryIO,
        original_filename: str,
        mime_type: str,
        description: str | None = None,
    ) -> TestCampaignAttachment:
        if self.storage is None:
            raise RuntimeError("Storage-Backend nicht konfiguriert.")
        if self.auth is None:
            raise PermissionError("Nicht angemeldet.")

        campaign = self._load_campaign(campaign_id)
        if not is_campaign_participant(self.auth, campaign):
            raise PermissionError(
                "Nur Teilnehmende der Kampagne oder Admin dürfen Anhänge hochladen."
            )

        validate_attachment_mime(mime_type)

        attachment_id = str(uuid.uuid4())
        storage_key = compute_attachment_storage_key(campaign_id, attachment_id)
        write_result = self.storage.put_stream(storage_key, file_stream)
        if write_result.file_size_bytes <= 0:
            raise ValueError("Datei ist leer.")

        cleaned_description = (description or "").strip() or None
        cleaned_filename = (original_filename or "").strip() or "unbenannt"

        # Thumbnail nur für Bild-MIME-Typen. Fehler dürfen den Upload
        # nicht scheitern lassen; der Anhang bleibt im Bestand.
        thumbnail_storage_key: str | None = None
        thumbnail_mime_type: str | None = None
        thumbnail_size_bytes: int | None = None
        thumbnail_error: str | None = None
        if attachment_has_thumbnail_support(mime_type):
            try:
                with self.storage.open_read(storage_key) as fh:
                    source_bytes = fh.read()
                thumb_bytes, thumb_mime = generate_thumbnail(source_bytes)
                thumbnail_storage_key = compute_attachment_thumbnail_storage_key(
                    campaign_id, attachment_id
                )
                thumb_write = self.storage.put_stream(
                    thumbnail_storage_key, BytesIO(thumb_bytes)
                )
                thumbnail_mime_type = thumb_mime
                thumbnail_size_bytes = thumb_write.file_size_bytes
            except ThumbnailError as exc:
                thumbnail_storage_key = None
                thumbnail_error = str(exc)
            except OSError as exc:
                thumbnail_storage_key = None
                thumbnail_error = f"Thumbnail-IO fehlgeschlagen: {exc}"

        attachment = TestCampaignAttachment(
            id=attachment_id,
            campaign_id=campaign_id,
            uploaded_by_person_id=self.auth.person_id,
            storage_key=storage_key,
            original_filename=cleaned_filename,
            mime_type=mime_type,
            file_size_bytes=write_result.file_size_bytes,
            sha256=write_result.sha256,
            description=cleaned_description,
            thumbnail_storage_key=thumbnail_storage_key,
            thumbnail_mime_type=thumbnail_mime_type,
            thumbnail_size_bytes=thumbnail_size_bytes,
        )
        self.session.add(attachment)
        self.session.flush()
        if self.audit is not None:
            after = {
                "campaign_id": campaign_id,
                "original_filename": attachment.original_filename,
                "mime_type": attachment.mime_type,
                "file_size_bytes": attachment.file_size_bytes,
                "sha256": attachment.sha256,
                "description": attachment.description,
                "thumbnail_mime_type": attachment.thumbnail_mime_type,
                "thumbnail_size_bytes": attachment.thumbnail_size_bytes,
            }
            if thumbnail_error is not None:
                after["thumbnail_error"] = thumbnail_error
            self.audit.log(
                "campaign.attachment.upload",
                entity_type="test_campaign_attachment",
                entity_id=attachment.id,
                after=after,
            )
        return attachment

    def update_description(
        self, attachment_id: str, *, description: str | None
    ) -> TestCampaignAttachment:
        attachment = self._load_visible_attachment(attachment_id)
        if not (self._is_admin() or self._is_uploader(attachment)):
            raise PermissionError("Nur Uploader oder Admin dürfen die Beschreibung ändern.")
        before = attachment.description
        new_description = (description or "").strip() or None
        attachment.description = new_description
        self.session.flush()
        if self.audit is not None and before != attachment.description:
            self.audit.log(
                "campaign.attachment.update_description",
                entity_type="test_campaign_attachment",
                entity_id=attachment.id,
                before={"description": before},
                after={"description": attachment.description},
            )
        return attachment

    def soft_delete(self, attachment_id: str) -> None:
        attachment = self._load_visible_attachment(attachment_id)
        if not (self._is_admin() or self._is_uploader(attachment)):
            raise PermissionError("Nur Uploader oder Admin dürfen den Anhang löschen.")
        attachment.is_deleted = True
        attachment.updated_at = datetime.now(tz=UTC)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "campaign.attachment.delete",
                entity_type="test_campaign_attachment",
                entity_id=attachment.id,
                before={"is_deleted": False},
                after={"is_deleted": True},
            )


__all__ = [
    "CampaignAttachmentNotFoundError",
    "CampaignNotFoundError",
    "TestCampaignAttachmentService",
]
