"""Dokumentkommentare auf Versionsebene (Block 0024).

Lebenszyklus eines Kommentars in zwei Stufen:

- ``open`` — privat: nur der Autor (und Admin) sehen ihn, der Autor
  kann ihn editieren oder direkt löschen lassen.
- ``submitted`` — eingereicht: für alle sichtbar, die das Dokument
  lesen dürfen; unveränderlich. ``submitted_at`` markiert den
  Übergang.

Soft-Delete (``is_deleted=True``) durch Admin als Ausnahmefall —
kein Hard-Delete (Konsortium-Prinzip). Audit hält jede der vier
Aktionen fest: ``create``, ``update``, ``submit``, ``delete``.

Sichtbarkeitsregel (verteidigt gegen Existenz-Leakage):
- Dokument muss vom Aufrufer lesbar sein (``can_read_document``).
- ``open``-Kommentare sieht nur der Autor selbst oder Admin.
- ``is_deleted=True`` Kommentare verschwinden aus allen Listen
  (Audit-Log hält sie fest).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ref4ep.domain.models import (
    DOCUMENT_COMMENT_STATUSES,
    DocumentComment,
    DocumentVersion,
)
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.permissions import (
    AuthContext,
    can_admin,
    can_comment_document,
    can_read_document,
)


class DocumentCommentNotFoundError(LookupError):
    """Kommentar existiert nicht oder ist für den Aufrufer unsichtbar."""

    def __init__(self, comment_id: str) -> None:
        super().__init__(f"Kommentar {comment_id} nicht gefunden.")
        self.comment_id = comment_id


class DocumentVersionNotFoundError(LookupError):
    """Dokumentversion existiert nicht oder ist für den Aufrufer unsichtbar."""

    def __init__(self, version_id: str) -> None:
        super().__init__(f"Dokumentversion {version_id} nicht gefunden.")
        self.version_id = version_id


class DocumentCommentService:
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

    def _is_author(self, comment: DocumentComment) -> bool:
        return self.auth is not None and self.auth.person_id == comment.author_person_id

    def _load_version(self, document_version_id: str) -> DocumentVersion:
        version = self.session.get(DocumentVersion, document_version_id)
        if version is None:
            raise DocumentVersionNotFoundError(document_version_id)
        if not can_read_document(self.auth, version.document):
            raise DocumentVersionNotFoundError(document_version_id)
        return version

    def _load_visible(self, comment_id: str) -> DocumentComment:
        """Lädt Kommentar, prüft Sichtbarkeit. Wirft sonst NotFound."""
        comment = self.session.get(DocumentComment, comment_id)
        if comment is None or comment.is_deleted:
            raise DocumentCommentNotFoundError(comment_id)
        if not can_read_document(self.auth, comment.document_version.document):
            raise DocumentCommentNotFoundError(comment_id)
        if comment.status == "open" and not (self._is_admin() or self._is_author(comment)):
            raise DocumentCommentNotFoundError(comment_id)
        return comment

    def _filter_visible(self, comments: list[DocumentComment]) -> list[DocumentComment]:
        is_admin = self._is_admin()
        out: list[DocumentComment] = []
        for c in comments:
            if c.is_deleted:
                continue
            if not can_read_document(self.auth, c.document_version.document):
                continue
            if c.status == "open" and not (is_admin or self._is_author(c)):
                continue
            out.append(c)
        return out

    # ---- read -----------------------------------------------------------

    def list_for_version(self, document_version_id: str) -> list[DocumentComment]:
        """Sichtbare Kommentare zu einer Version, älteste zuerst."""
        version = self._load_version(document_version_id)
        return self._filter_visible(list(version.comments))

    def list_global(
        self,
        *,
        document_version_id: str | None = None,
        author_person_id: str | None = None,
        status: str | None = None,
    ) -> list[DocumentComment]:
        """Globale Übersicht über alle sichtbaren Kommentare, neueste zuerst.

        Optionale Filter: nach Version, Autor, Status.
        """
        stmt = select(DocumentComment).where(DocumentComment.is_deleted.is_(False))
        if document_version_id is not None:
            stmt = stmt.where(DocumentComment.document_version_id == document_version_id)
        if author_person_id is not None:
            stmt = stmt.where(DocumentComment.author_person_id == author_person_id)
        if status is not None:
            if status not in DOCUMENT_COMMENT_STATUSES:
                raise ValueError(f"status: ungültiger Wert {status!r}")
            stmt = stmt.where(DocumentComment.status == status)
        stmt = stmt.order_by(DocumentComment.created_at.desc())
        return self._filter_visible(list(self.session.scalars(stmt)))

    def get_visible(self, comment_id: str) -> DocumentComment:
        """Single-Read mit Existenz-Leak-Schutz."""
        return self._load_visible(comment_id)

    # ---- write ----------------------------------------------------------

    def create(self, document_version_id: str, *, text: str) -> DocumentComment:
        if self.auth is None:
            raise PermissionError("Nicht angemeldet.")
        cleaned = (text or "").strip()
        if not cleaned:
            raise ValueError("Kommentartext darf nicht leer sein.")
        version = self._load_version(document_version_id)
        if not can_comment_document(self.auth, version.document):
            raise PermissionError("Nicht berechtigt, hier zu kommentieren.")
        comment = DocumentComment(
            document_version_id=version.id,
            author_person_id=self.auth.person_id,
            text=cleaned,
            status="open",
        )
        self.session.add(comment)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "document_comment.create",
                entity_type="document_comment",
                entity_id=comment.id,
                after={
                    "document_version_id": comment.document_version_id,
                    "status": comment.status,
                },
            )
        return comment

    def update(self, comment_id: str, *, text: str) -> DocumentComment:
        """Editiert eigenen ``open``-Kommentar. ``submitted`` ist
        unveränderlich.
        """
        comment = self._load_visible(comment_id)
        if not self._is_author(comment):
            raise PermissionError("Nur der Autor darf den Kommentar bearbeiten.")
        if comment.status != "open":
            raise ValueError("Eingereichte Kommentare können nicht mehr bearbeitet werden.")
        cleaned = (text or "").strip()
        if not cleaned:
            raise ValueError("Kommentartext darf nicht leer sein.")
        before_text = comment.text
        comment.text = cleaned
        self.session.flush()
        if self.audit is not None and before_text != comment.text:
            self.audit.log(
                "document_comment.update",
                entity_type="document_comment",
                entity_id=comment.id,
                before={"text": before_text},
                after={"text": comment.text},
            )
        return comment

    def submit(self, comment_id: str) -> DocumentComment:
        """Übergang ``open`` → ``submitted``: setzt ``submitted_at``,
        ab dann unveränderlich.
        """
        comment = self._load_visible(comment_id)
        if not self._is_author(comment):
            raise PermissionError("Nur der Autor darf den Kommentar einreichen.")
        if comment.status != "open":
            raise ValueError("Kommentar ist bereits eingereicht.")
        now = datetime.now(tz=UTC)
        comment.status = "submitted"
        comment.submitted_at = now
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "document_comment.submit",
                entity_type="document_comment",
                entity_id=comment.id,
                before={"status": "open"},
                after={"status": "submitted", "submitted_at": now},
            )
        return comment

    def soft_delete(self, comment_id: str) -> DocumentComment:
        """Admin-Soft-Delete. Kein Hard-Delete."""
        comment = self._load_visible(comment_id)
        if not self._is_admin():
            raise PermissionError("Nur Admin darf Kommentare löschen.")
        comment.is_deleted = True
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "document_comment.delete",
                entity_type="document_comment",
                entity_id=comment.id,
                before={"is_deleted": False},
                after={"is_deleted": True},
            )
        return comment
