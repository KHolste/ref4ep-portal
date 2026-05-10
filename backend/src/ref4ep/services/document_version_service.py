"""Dokument-Versionen — Upload (append-only) und Download-Lookup.

``upload_new_version`` schreibt zuerst in den Storage (mit
SHA-256-/Größenberechnung), legt anschließend den DB-Datensatz an
und reiht dabei die ``version_number`` server-seitig ein. Bei
parallelen Uploads (UNIQUE-Konflikt) wird einmal mit der nächsten
Nummer wiederholt.
"""

from __future__ import annotations

import uuid
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ref4ep.domain.models import Document, DocumentVersion
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.document_service import DocumentNotFoundError
from ref4ep.services.permissions import (
    AuthContext,
    can_read_document,
    can_write_document,
)
from ref4ep.services.storage_validation import (
    CHANGE_NOTE_DEFAULT_FIRST,
    CHANGE_NOTE_DEFAULT_NEXT,
    compute_storage_key,
    validate_change_note,
    validate_mime,
)
from ref4ep.storage import Storage


class DocumentVersionService:
    def __init__(
        self,
        session: Session,
        *,
        auth: AuthContext | None = None,
        storage: Storage | None = None,
        audit: AuditLogger | None = None,
    ) -> None:
        self.session = session
        self.auth = auth
        self.storage = storage
        self.audit = audit

    # ---- read -----------------------------------------------------------

    def list_for_document(self, document_id: str) -> list[DocumentVersion]:
        document = self.session.get(Document, document_id)
        if document is None or document.is_deleted or not can_read_document(self.auth, document):
            raise DocumentNotFoundError(document_id)
        stmt = (
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number)
        )
        return list(self.session.scalars(stmt))

    def get_for_download(self, document_id: str, version_number: int) -> DocumentVersion:
        document = self.session.get(Document, document_id)
        if document is None or document.is_deleted or not can_read_document(self.auth, document):
            raise DocumentNotFoundError(document_id)
        stmt = select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.version_number == version_number,
        )
        version = self.session.scalars(stmt).first()
        if version is None:
            raise DocumentNotFoundError(f"version {version_number} of {document_id}")
        return version

    # ---- write ----------------------------------------------------------

    def _next_version_number(self, document_id: str) -> int:
        current = self.session.scalar(
            select(func.max(DocumentVersion.version_number)).where(
                DocumentVersion.document_id == document_id
            )
        )
        return (current or 0) + 1

    def upload_new_version(
        self,
        document_id: str,
        *,
        file_stream: BinaryIO,
        original_filename: str,
        mime_type: str,
        change_note: str | None = None,
        version_label: str | None = None,
    ) -> tuple[DocumentVersion, list[str]]:
        if self.storage is None:
            raise RuntimeError("Storage-Backend nicht konfiguriert.")
        if self.auth is None:
            raise PermissionError("Nicht angemeldet.")

        document = self.session.get(Document, document_id)
        if document is None or document.is_deleted:
            raise DocumentNotFoundError(document_id)
        if not can_write_document(self.auth, document):
            raise PermissionError("Nicht berechtigt, in dieses Dokument zu schreiben.")

        validate_mime(mime_type)
        cleaned_note = validate_change_note(change_note)
        original_filename = (original_filename or "").strip() or "unbenannt"

        # Block 0036: Wenn der Nutzer keine Änderungsnotiz mitgibt,
        # füllen wir einen neutralen Default ein. Erst-Upload bekommt
        # eine andere Default-Notiz als Folge-Versionen, damit das
        # Dokumentdetail die Genese sauber wiedergibt.
        if not cleaned_note:
            has_existing_versions = (
                self.session.scalars(
                    select(DocumentVersion.id).where(DocumentVersion.document_id == document_id)
                ).first()
                is not None
            )
            cleaned_note = (
                CHANGE_NOTE_DEFAULT_NEXT if has_existing_versions else CHANGE_NOTE_DEFAULT_FIRST
            )

        version_id = str(uuid.uuid4())
        storage_key = compute_storage_key(document_id, version_id)
        write_result = self.storage.put_stream(storage_key, file_stream)
        if write_result.file_size_bytes <= 0:
            raise ValueError("Datei ist leer.")

        warnings: list[str] = []
        existing_same_hash = self.session.scalars(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.sha256 == write_result.sha256,
            )
        ).first()
        if existing_same_hash is not None:
            warnings.append(f"duplicate_content_of_v{existing_same_hash.version_number}")

        # Bis zu zweimal versuchen — bei UNIQUE-Race auf (document_id, version_number).
        for attempt in range(2):
            version_number = self._next_version_number(document_id)
            version = DocumentVersion(
                id=version_id,
                document_id=document_id,
                version_number=version_number,
                version_label=version_label or None,
                change_note=cleaned_note,
                storage_key=storage_key,
                original_filename=original_filename,
                mime_type=mime_type,
                file_size_bytes=write_result.file_size_bytes,
                sha256=write_result.sha256,
                uploaded_by_person_id=self.auth.person_id,
            )
            self.session.add(version)
            try:
                self.session.flush()
                if self.audit is not None:
                    self.audit.log(
                        "document_version.upload",
                        entity_type="document_version",
                        entity_id=version.id,
                        after={
                            "document_id": version.document_id,
                            "version_number": version.version_number,
                            "version_label": version.version_label,
                            "original_filename": version.original_filename,
                            "mime_type": version.mime_type,
                            "file_size_bytes": version.file_size_bytes,
                            "sha256": version.sha256,
                        },
                    )
                return version, warnings
            except IntegrityError:
                self.session.rollback()
                if attempt == 1:
                    raise

        raise RuntimeError("Unreachable: Upload nicht abgeschlossen.")
