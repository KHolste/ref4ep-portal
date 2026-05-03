"""Service-Schicht für die öffentliche Download-Bibliothek (Sprint 4).

Liefert ausschließlich Dokumente, die alle vier MVP-§9.1-Bedingungen
erfüllen:

- ``is_deleted = false``
- ``visibility = 'public'``
- ``status = 'released'``
- ``released_version_id IS NOT NULL``

Identitäts- und Lifecycle-Services bleiben außen vor; dieser Service
ist die einzige Quelle der öffentlichen Sicht und enthält keinerlei
Auth-Annahme — Aufrufer (HTTP-Routen) entscheiden, ob sie Anonyme
durchlassen.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ref4ep.domain.models import Document, DocumentVersion, Workpackage


def _public_filter():
    return (
        Document.is_deleted.is_(False),
        Document.visibility == "public",
        Document.status == "released",
        Document.released_version_id.isnot(None),
    )


class PublicDocumentService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ---- list -----------------------------------------------------------

    def list_public(self) -> list[Document]:
        stmt = select(Document).where(*_public_filter()).order_by(Document.updated_at.desc())
        return list(self.session.scalars(stmt))

    # ---- detail / lookup ------------------------------------------------

    def get_public_by_wp_and_slug(self, *, wp_code: str, slug: str) -> Document | None:
        wp = self.session.scalars(
            select(Workpackage).where(
                Workpackage.code == wp_code, Workpackage.is_deleted.is_(False)
            )
        ).first()
        if wp is None:
            return None
        stmt = select(Document).where(
            Document.workpackage_id == wp.id,
            Document.slug == slug,
            *_public_filter(),
        )
        return self.session.scalars(stmt).first()

    # ---- download -------------------------------------------------------

    def get_for_public_download(
        self, *, wp_code: str, slug: str
    ) -> tuple[Document, DocumentVersion] | None:
        document = self.get_public_by_wp_and_slug(wp_code=wp_code, slug=slug)
        if document is None or document.released_version_id is None:
            return None
        version = self.session.get(DocumentVersion, document.released_version_id)
        if version is None or version.document_id != document.id:
            # Sollte dank FK + Service-Invarianten nicht eintreten,
            # aber defensive Prüfung kostet nichts.
            return None
        return document, version
