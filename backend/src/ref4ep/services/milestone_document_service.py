"""Meilenstein-Dokumentverknüpfungen (Block 0039).

Eigene Service-Klasse statt Erweiterung von ``MilestoneService`` —
hält die Berechtigungslogik (``can_edit``) wieder, fügt aber den
Sichtbarkeitsschutz für das verknüpfte Dokument auf der Lese- und
Schreibseite hinzu.

Berechtigungen:
- Verknüpfen / Entfernen: Admin oder WP-Lead des Meilenstein-WPs.
  Bei übergreifendem Meilenstein (workpackage_id IS NULL): nur Admin.
- Lesen: jede eingeloggte Person bekommt nur Verknüpfungen zu
  Dokumenten, die sie über ``can_read_document`` lesen darf.
- Verknüpfen erfordert zusätzlich Leserecht am Dokument — sonst
  könnte ein Lead über die Verknüpfung Existenz-Lecks erzeugen.

Audit-Aktionen: ``milestone.document_link.add`` /
``milestone.document_link.remove``.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ref4ep.domain.models import Document, Milestone, MilestoneDocumentLink
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.document_service import DocumentNotFoundError, DocumentService
from ref4ep.services.milestone_service import MilestoneService
from ref4ep.services.permissions import can_read_document


class MilestoneNotFoundError(LookupError):
    def __init__(self, milestone_id: str) -> None:
        super().__init__(f"Meilenstein {milestone_id} nicht gefunden.")
        self.milestone_id = milestone_id


class MilestoneDocumentLinkNotFoundError(LookupError):
    def __init__(self, milestone_id: str, document_id: str) -> None:
        super().__init__(
            f"Verknüpfung Meilenstein {milestone_id} × Dokument {document_id} nicht gefunden."
        )
        self.milestone_id = milestone_id
        self.document_id = document_id


class MilestoneDocumentLinkConflictError(ValueError):
    def __init__(self, milestone_id: str, document_id: str) -> None:
        super().__init__(
            f"Dokument {document_id} ist bereits mit Meilenstein {milestone_id} verknüpft."
        )
        self.milestone_id = milestone_id
        self.document_id = document_id


class MilestoneDocumentService:
    def __init__(
        self,
        session: Session,
        *,
        role: str | None = None,
        person_id: str | None = None,
        auth=None,
        audit: AuditLogger | None = None,
    ) -> None:
        self.session = session
        self.role = role
        self.person_id = person_id
        # ``auth`` wird für ``can_read_document`` gebraucht; ``role`` /
        # ``person_id`` für die Milestone-Schreibberechtigung. Beide
        # Wege werden im Routenlayer parallel gepflegt.
        self.auth = auth
        self.audit = audit

    # ---- helpers ------------------------------------------------------

    def _milestone_service(self) -> MilestoneService:
        return MilestoneService(self.session, role=self.role, person_id=self.person_id)

    def _load_milestone(self, milestone_id: str) -> Milestone:
        m = self.session.get(Milestone, milestone_id)
        if m is None:
            raise MilestoneNotFoundError(milestone_id)
        return m

    def _require_edit(self, milestone: Milestone) -> None:
        if not self._milestone_service().can_edit(milestone):
            raise PermissionError(
                "Verknüpfen/Entfernen erfordert Admin oder WP-Lead des Meilenstein-Arbeitspakets."
            )

    def _visible_documents(
        self, links: Iterable[MilestoneDocumentLink]
    ) -> list[MilestoneDocumentLink]:
        return [
            link
            for link in links
            if not link.document.is_deleted and can_read_document(self.auth, link.document)
        ]

    # ---- read ----------------------------------------------------------

    def list_documents(self, milestone_id: str) -> list[MilestoneDocumentLink]:
        """Sichtbare Verknüpfungen, sortiert nach Anlagedatum
        (älteste zuerst). Existenz-Leak-Schutz: unbekannter Meilenstein
        liefert ``MilestoneNotFoundError``."""
        self._load_milestone(milestone_id)
        stmt = (
            select(MilestoneDocumentLink)
            .where(MilestoneDocumentLink.milestone_id == milestone_id)
            .order_by(MilestoneDocumentLink.created_at)
        )
        links = list(self.session.scalars(stmt))
        return self._visible_documents(links)

    def list_milestones_for_document(self, document_id: str) -> list[Milestone]:
        """Liste der Meilensteine, mit denen ein bestimmtes Dokument
        verknüpft ist. Sichtbarkeit des Dokuments wird vom Aufrufer
        sichergestellt (Detail-Route prüft ``can_read_document``)."""
        stmt = (
            select(Milestone)
            .join(
                MilestoneDocumentLink,
                MilestoneDocumentLink.milestone_id == Milestone.id,
            )
            .where(MilestoneDocumentLink.document_id == document_id)
            .order_by(Milestone.planned_date, Milestone.code)
        )
        return list(self.session.scalars(stmt))

    def list_documents_linked_to_any_milestone(self) -> list[Document]:
        """Alle Dokumente, die mindestens eine Meilenstein-Verknüpfung
        haben. Sichtbarkeit wird auf Aufruferseite mit
        ``can_read_document`` gefiltert (vgl. ``DocumentService``)."""
        stmt = (
            select(Document)
            .join(
                MilestoneDocumentLink,
                MilestoneDocumentLink.document_id == Document.id,
            )
            .where(Document.is_deleted.is_(False))
            .group_by(Document.id)
        )
        return list(self.session.scalars(stmt))

    # ---- write ---------------------------------------------------------

    def add_link(self, milestone_id: str, *, document_id: str) -> MilestoneDocumentLink:
        if self.auth is None:
            raise PermissionError("Nicht angemeldet.")
        milestone = self._load_milestone(milestone_id)
        self._require_edit(milestone)

        # Dokument muss existieren UND vom Akteur lesbar sein —
        # verhindert Existenz-Lecks über die Verknüpfung.
        try:
            document = DocumentService(self.session, auth=self.auth).get_by_id(document_id)
        except DocumentNotFoundError as exc:
            # ``get_by_id`` wirft 404 sowohl bei Nichtexistenz als auch
            # bei fehlender Sichtbarkeit — beides geben wir als
            # „nicht gefunden" weiter.
            raise MilestoneNotFoundError(document_id) from exc

        link = MilestoneDocumentLink(
            id=str(uuid.uuid4()),
            milestone_id=milestone.id,
            document_id=document.id,
            created_by_person_id=self.auth.person_id,
        )
        self.session.add(link)
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise MilestoneDocumentLinkConflictError(milestone.id, document.id) from exc

        if self.audit is not None:
            self.audit.log(
                "milestone.document_link.add",
                entity_type="milestone_document_link",
                entity_id=link.id,
                after={
                    "milestone_id": milestone.id,
                    "milestone_code": milestone.code,
                    "document_id": document.id,
                    "document_title": document.title,
                },
            )
        return link

    def remove_link(self, milestone_id: str, *, document_id: str) -> None:
        if self.auth is None:
            raise PermissionError("Nicht angemeldet.")
        milestone = self._load_milestone(milestone_id)
        self._require_edit(milestone)

        link = self.session.scalars(
            select(MilestoneDocumentLink).where(
                MilestoneDocumentLink.milestone_id == milestone_id,
                MilestoneDocumentLink.document_id == document_id,
            )
        ).first()
        if link is None:
            raise MilestoneDocumentLinkNotFoundError(milestone_id, document_id)

        link_id = link.id
        document_title = link.document.title if link.document is not None else None
        self.session.delete(link)
        self.session.flush()

        if self.audit is not None:
            self.audit.log(
                "milestone.document_link.remove",
                entity_type="milestone_document_link",
                entity_id=link_id,
                before={
                    "milestone_id": milestone.id,
                    "milestone_code": milestone.code,
                    "document_id": document_id,
                    "document_title": document_title,
                },
            )


__all__ = [
    "MilestoneDocumentLinkConflictError",
    "MilestoneDocumentLinkNotFoundError",
    "MilestoneDocumentService",
    "MilestoneNotFoundError",
]
