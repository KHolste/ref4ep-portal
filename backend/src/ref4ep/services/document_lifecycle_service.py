"""Dokument-Lebenszyklus: Status, Sichtbarkeit, Release.

Bündelt Status- (`set_status`), Freigabe- (`release`/`unrelease`)
und Sichtbarkeitsänderungen (`set_visibility`). Audit-Pflicht
über den optional injizierten ``AuditLogger``.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ref4ep.domain.models import (
    DOCUMENT_STATUSES,
    DOCUMENT_VISIBILITIES,
    Document,
    DocumentVersion,
)
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.document_service import DocumentNotFoundError
from ref4ep.services.permissions import (
    AuthContext,
    can_read_document,
    can_release,
    can_set_status,
    can_set_visibility,
    can_unrelease,
)


class InvalidStatusTransitionError(ValueError):
    """Unzulässiger Übergang zwischen Status-Werten."""


class DocumentLifecycleService:
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

    # ---- Helpers --------------------------------------------------------

    def _load(self, document_id: str) -> Document:
        document = self.session.get(Document, document_id)
        if document is None or document.is_deleted:
            raise DocumentNotFoundError(document_id)
        if not can_read_document(self.auth, document):
            raise DocumentNotFoundError(document_id)
        return document

    # ---- set_status -----------------------------------------------------

    def set_status(self, document_id: str, *, to: Literal["draft", "in_review"]) -> Document:
        document = self._load(document_id)
        if to not in ("draft", "in_review"):
            raise ValueError(f"set_status erlaubt nur draft/in_review, nicht {to!r}.")
        if document.status == to:
            return document
        # Erlaubte Übergänge: draft → in_review, in_review → draft.
        valid = (document.status, to) in {("draft", "in_review"), ("in_review", "draft")}
        if not valid:
            raise InvalidStatusTransitionError(
                f"Übergang {document.status!r} → {to!r} nicht erlaubt."
            )
        if not can_set_status(self.auth, document):
            raise PermissionError("Nicht berechtigt, den Status zu ändern.")
        if to == "in_review":
            has_versions = self.session.scalar(
                select(DocumentVersion.id)
                .where(DocumentVersion.document_id == document.id)
                .limit(1)
            )
            if not has_versions:
                raise ValueError(
                    "Dokument benötigt mindestens eine Version, bevor es zur Review geht."
                )
        before = {"status": document.status}
        document.status = to
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "document.set_status",
                entity_type="document",
                entity_id=document.id,
                before=before,
                after={"status": document.status},
            )
        return document

    # ---- release --------------------------------------------------------

    def release(self, document_id: str, *, version_number: int) -> Document:
        document = self._load(document_id)
        if document.status not in ("in_review", "released"):
            raise InvalidStatusTransitionError(
                f"Release nur aus in_review/released möglich, nicht aus {document.status!r}."
            )
        if not can_release(self.auth, document):
            raise PermissionError("Nicht berechtigt, dieses Dokument freizugeben.")

        version = self.session.scalars(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.version_number == version_number,
            )
        ).first()
        if version is None:
            raise DocumentNotFoundError(f"version {version_number} of document {document.id}")
        # Service garantiert die semantische Bindung über die FK hinaus
        # (DB-FK akzeptiert jede gültige Version, auch fremder Dokumente,
        # falls jemand die ID raten würde).
        if version.document_id != document.id:
            raise DocumentNotFoundError(f"version {version_number} of document {document.id}")

        before = {
            "status": document.status,
            "released_version_id": document.released_version_id,
        }
        document.status = "released"
        document.released_version_id = version.id
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "document.release",
                entity_type="document",
                entity_id=document.id,
                before=before,
                after={
                    "status": document.status,
                    "released_version_id": document.released_version_id,
                    "released_version_number": version.version_number,
                },
            )
        return document

    # ---- unrelease ------------------------------------------------------

    def unrelease(self, document_id: str) -> Document:
        document = self._load(document_id)
        if document.status != "released":
            raise InvalidStatusTransitionError(
                f"Unrelease nur aus released möglich, nicht aus {document.status!r}."
            )
        if not can_unrelease(self.auth):
            raise PermissionError("Nur Admin darf eine Freigabe zurückziehen.")
        before = {
            "status": document.status,
            "released_version_id": document.released_version_id,
        }
        document.status = "draft"
        document.released_version_id = None
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "document.unrelease",
                entity_type="document",
                entity_id=document.id,
                before=before,
                after={"status": document.status, "released_version_id": None},
            )
        return document

    # ---- set_visibility -------------------------------------------------

    def set_visibility(
        self,
        document_id: str,
        *,
        to: Literal["workpackage", "internal", "public"],
    ) -> Document:
        document = self._load(document_id)
        if to not in DOCUMENT_VISIBILITIES:
            raise ValueError(f"Unbekannte Sichtbarkeit: {to!r}")
        if document.visibility == to:
            return document
        if not can_set_visibility(self.auth, document, to=to):
            raise PermissionError(f"Nicht berechtigt, Sichtbarkeit auf {to!r} zu setzen.")
        before = {"visibility": document.visibility}
        document.visibility = to
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "document.set_visibility",
                entity_type="document",
                entity_id=document.id,
                before=before,
                after={"visibility": document.visibility},
            )
        return document


__all__ = [
    "DOCUMENT_STATUSES",
    "DocumentLifecycleService",
    "InvalidStatusTransitionError",
]
