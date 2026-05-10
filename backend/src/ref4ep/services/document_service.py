"""Dokument-Verwaltung (Metadaten, ohne Datei-Upload).

Schreibmethoden prüfen Workpackage-Mitgliedschaft (oder Admin) im
Service-Layer und schreiben — sofern ein ``AuditLogger`` injiziert
ist — Audit-Einträge.
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ref4ep.domain.models import DOCUMENT_TYPES, LIBRARY_SECTIONS, Document, Workpackage
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.permissions import (
    AuthContext,
    can_admin,
    can_read_document,
    can_soft_delete_document,
    can_write_document,
    is_member_of,
)
from ref4ep.services.workpackage_service import WorkpackageService

_SLUG_NON_WORD = re.compile(r"[^\w-]+", re.UNICODE)
_SLUG_DASHES = re.compile(r"-{2,}")


class DocumentNotFoundError(LookupError):
    """Wird vom Service geworfen, wenn ein Dokument nicht (sichtbar) ist."""


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = _SLUG_NON_WORD.sub("-", ascii_only.strip().lower())
    cleaned = _SLUG_DASHES.sub("-", cleaned).strip("-")
    return cleaned or "dokument"


class DocumentService:
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

    # ---- read -----------------------------------------------------------

    def list_for_workpackage(self, workpackage_code: str) -> list[Document]:
        wp = WorkpackageService(self.session).get_by_code(workpackage_code)
        if wp is None:
            return []
        if self.auth is None:
            return []
        is_admin = can_admin(self.auth.platform_role)
        if not is_admin and not is_member_of(self.auth, wp.id):
            return []
        stmt = (
            select(Document)
            .where(Document.workpackage_id == wp.id, Document.is_deleted.is_(False))
            .order_by(Document.created_at.desc())
        )
        return list(self.session.scalars(stmt))

    def list_internal(
        self,
        *,
        include_archived: bool = False,
        workpackage_code: str | None = None,
        q: str | None = None,
        library_section: str | None = None,
        without_workpackage: bool = False,
        enforce_visibility: bool = False,
        status: str | None = None,
    ) -> list[Document]:
        """Globale interne Dokumentliste (Block 0017).

        Berechtigung: alle eingeloggten Personen — die Routen-Schicht
        erzwingt das. Per-Dokument-``can_read_document``-Prüfung wird
        hier bewusst NICHT angewendet, weil das Listing als
        Auswahlhilfe für interne UI-Module dient (z. B. Meeting-
        Doc-Verknüpfung). Wer Inhalte holen will, geht weiterhin
        durch ``get_by_id``, das die Sichtbarkeit prüft.

        Filter:
        - ``include_archived=False`` blendet ``is_deleted``-Dokumente
          aus (das Projekt hat aktuell kein eigenes Archiv-Flag, wir
          nutzen ``is_deleted`` als Stellvertreter).
        - ``workpackage_code`` filtert auf einen WP. Unbekannter Code
          → leere Liste (kein 404), konsistent mit
          ``list_for_workpackage``.
        - ``q`` ist eine case-insensitive Substring-Suche über
          ``deliverable_code`` und ``title``.

        Sortierung: nach ``workpackage.sort_order``, dann ``code``,
        dann ``title``.
        """
        from sqlalchemy import func, or_

        # Block 0035: ``workpackage_id`` ist nullable. Statt INNER JOIN
        # auf Workpackage ein Outer JOIN — sonst fielen Bibliotheks-
        # Dokumente ohne WP-Bezug aus der Liste.
        stmt = select(Document).outerjoin(Workpackage, Workpackage.id == Document.workpackage_id)
        if not include_archived:
            stmt = stmt.where(Document.is_deleted.is_(False))
        if workpackage_code is not None:
            wp = WorkpackageService(self.session).get_by_code(workpackage_code)
            if wp is None:
                return []
            stmt = stmt.where(Document.workpackage_id == wp.id)
        if without_workpackage:
            stmt = stmt.where(Document.workpackage_id.is_(None))
        if library_section is not None:
            if library_section not in LIBRARY_SECTIONS:
                raise ValueError(f"Unbekannter Bibliotheksbereich: {library_section!r}")
            stmt = stmt.where(Document.library_section == library_section)
        if status is not None:
            stmt = stmt.where(Document.status == status)
        if q:
            needle = f"%{q.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Document.deliverable_code).like(needle),
                    func.lower(Document.title).like(needle),
                )
            )
        # Sortierung: WP-Sortierung zuerst (NULL-WP-Dokumente am Anfang
        # oder Ende — SQLite/Postgres behandeln NULL hier verschieden;
        # wir akzeptieren das pragmatisch).
        stmt = stmt.order_by(Workpackage.sort_order, Workpackage.code, Document.title)
        documents = list(self.session.scalars(stmt))
        if enforce_visibility:
            documents = [d for d in documents if can_read_document(self.auth, d)]
        return documents

    def get_by_id(self, document_id: str) -> Document:
        document = self.session.get(Document, document_id)
        if document is None or document.is_deleted:
            raise DocumentNotFoundError(document_id)
        if not can_read_document(self.auth, document):
            # Existenz-Leakage-Schutz: 404 statt 403.
            raise DocumentNotFoundError(document_id)
        return document

    # ---- write ----------------------------------------------------------

    def _require_write(self, workpackage: Workpackage) -> None:
        if self.auth is None:
            raise PermissionError("Nicht angemeldet.")
        if can_admin(self.auth.platform_role):
            return
        if not is_member_of(self.auth, workpackage.id):
            raise PermissionError("Kein WP-Mitglied.")

    def create(
        self,
        *,
        workpackage_code: str | None,
        title: str,
        document_type: str,
        deliverable_code: str | None = None,
        description: str | None = None,
        library_section: str | None = None,
        visibility: str | None = None,
    ) -> Document:
        """Legt ein neues Dokument an.

        Block 0035: ``workpackage_code`` darf ``None`` sein — Admins
        können dann übergreifende Bibliotheksdokumente ohne WP-Bezug
        anlegen. Ohne WP ist nur Admin schreibberechtigt.
        ``library_section`` ist optional; wenn gesetzt, muss der Wert
        in :data:`LIBRARY_SECTIONS` enthalten sein.
        """
        if document_type not in DOCUMENT_TYPES:
            raise ValueError(f"Unbekannter Dokumenttyp: {document_type!r}")
        title = (title or "").strip()
        if not title:
            raise ValueError("Titel darf nicht leer sein.")
        if library_section is not None and library_section not in LIBRARY_SECTIONS:
            raise ValueError(f"Unbekannter Bibliotheksbereich: {library_section!r}")

        wp: Workpackage | None = None
        if workpackage_code is not None:
            wp = WorkpackageService(self.session).get_by_code(workpackage_code)
            if wp is None:
                raise LookupError(f"Workpackage {workpackage_code!r} nicht gefunden.")
            self._require_write(wp)
        else:
            if self.auth is None:
                raise PermissionError("Nicht angemeldet.")
            if not can_admin(self.auth.platform_role):
                raise PermissionError(
                    "Dokumente ohne Arbeitspaket-Bezug dürfen nur Admins anlegen."
                )

        assert self.auth is not None

        # Default-Visibility: WP-Bezug → ``workpackage`` (wie bisher);
        # ohne WP-Bezug → ``internal`` (nicht ``workpackage``, weil das
        # ohne WP keinen Sinn ergibt).
        if visibility is None:
            visibility = "workpackage" if wp is not None else "internal"
        if visibility not in ("workpackage", "internal", "public"):
            raise ValueError(f"Unbekannte Sichtbarkeit: {visibility!r}")
        if wp is None and visibility == "workpackage":
            raise ValueError(
                "Sichtbarkeit ``workpackage`` ist ohne Arbeitspaket-Bezug nicht erlaubt."
            )

        slug = slugify(title)
        document = Document(
            workpackage_id=wp.id if wp is not None else None,
            title=title,
            slug=slug,
            document_type=document_type,
            deliverable_code=(deliverable_code or None),
            description=((description or "").strip() or None),
            status="draft",
            visibility=visibility,
            library_section=library_section,
            created_by_person_id=self.auth.person_id,
        )
        self.session.add(document)
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            scope = workpackage_code if workpackage_code is not None else "Projektbibliothek"
            raise ValueError(f"Slug {slug!r} existiert in {scope!r} bereits.") from exc

        if self.audit is not None:
            self.audit.log(
                "document.create",
                entity_type="document",
                entity_id=document.id,
                after={
                    "workpackage_id": document.workpackage_id,
                    "title": document.title,
                    "slug": document.slug,
                    "document_type": document.document_type,
                    "deliverable_code": document.deliverable_code,
                    "description": document.description,
                    "status": document.status,
                    "visibility": document.visibility,
                    "library_section": document.library_section,
                },
            )
        return document

    def update_metadata(
        self,
        document_id: str,
        *,
        title: str | None = None,
        document_type: str | None = None,
        deliverable_code: str | None = None,
        description: str | None = None,
    ) -> Document:
        document = self.session.get(Document, document_id)
        if document is None or document.is_deleted:
            raise DocumentNotFoundError(document_id)
        if not can_write_document(self.auth, document):
            raise PermissionError("Nicht berechtigt, dieses Dokument zu ändern.")

        before = {
            "title": document.title,
            "document_type": document.document_type,
            "deliverable_code": document.deliverable_code,
            "description": document.description,
        }

        if title is not None:
            stripped = title.strip()
            if not stripped:
                raise ValueError("Titel darf nicht leer sein.")
            document.title = stripped
        if document_type is not None:
            if document_type not in DOCUMENT_TYPES:
                raise ValueError(f"Unbekannter Dokumenttyp: {document_type!r}")
            document.document_type = document_type
        if deliverable_code is not None:
            document.deliverable_code = deliverable_code or None
        if description is not None:
            document.description = (description or "").strip() or None
        self.session.flush()

        if self.audit is not None:
            after = {
                "title": document.title,
                "document_type": document.document_type,
                "deliverable_code": document.deliverable_code,
                "description": document.description,
            }
            if after != before:
                self.audit.log(
                    "document.update",
                    entity_type="document",
                    entity_id=document.id,
                    before=before,
                    after=after,
                )
        return document

    def soft_delete(self, document_id: str) -> Document:
        """Sprint 3: nur Admin; setzt is_deleted=True. Versionen + Storage bleiben."""
        document = self.session.get(Document, document_id)
        if document is None or document.is_deleted:
            raise DocumentNotFoundError(document_id)
        if not can_soft_delete_document(self.auth):
            raise PermissionError("Nur Admin darf Dokumente soft-löschen.")
        document.is_deleted = True
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "document.delete",
                entity_type="document",
                entity_id=document.id,
                before={"is_deleted": False},
                after={"is_deleted": True},
            )
        return document
