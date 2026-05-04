"""Meilenstein-Verwaltung (Block 0009).

Im Ref4EP-Antrag gibt es vier Projekt-Meilensteine. Diese Service-
Klasse kümmert sich um Lesen, Anlegen und Aktualisieren — das
Anlegen erfolgt in der Praxis aus dem Seed (siehe ``SeedService``);
die API stellt nur Lese- und PATCH-Endpunkte bereit.

Berechtigungen (in der Route + hier doppelt geprüft):

- ``admin``                darf jeden Meilenstein bearbeiten.
- ``wp_lead`` des MS-WP    darf den eigenen Meilenstein bearbeiten.
- Gesamtprojekt-Meilenstein (``workpackage_id is None``) — nur Admin.

Achievement-Regel (im Bericht dokumentiert):
Wenn ``status`` auf ``achieved`` gesetzt wird und kein
``actual_date`` mitgeschickt wurde, **setzt der Service ihn
automatisch auf das heutige Datum**. Wir bevorzugen diesen Pfad
gegenüber einer 422, weil das alltägliche „erreicht heute" so
ohne zweites Feld erfasst werden kann; ein explizit übergebenes
``actual_date`` (auch in der Vergangenheit, etwa bei MS1) bleibt
unangetastet.

Hard-Delete gibt es nicht.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ref4ep.domain.models import MILESTONE_STATUSES, Milestone, Workpackage
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.permissions import can_admin
from ref4ep.services.validators import normalise_text
from ref4ep.services.workpackage_service import WorkpackageService

WRITABLE_FIELDS: tuple[str, ...] = (
    "title",
    "workpackage_id",
    "planned_date",
    "actual_date",
    "status",
    "note",
)


class MilestoneService:
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

    # ---- read -----------------------------------------------------------

    def list_all(self) -> list[Milestone]:
        return list(self.session.scalars(select(Milestone).order_by(Milestone.code)))

    def get(self, milestone_id: str) -> Milestone | None:
        return self.session.get(Milestone, milestone_id)

    def get_by_code(self, code: str) -> Milestone | None:
        return self.session.scalars(select(Milestone).where(Milestone.code == code)).first()

    # ---- berechtigung ---------------------------------------------------

    def _is_admin(self) -> bool:
        return can_admin(self.role or "")

    def can_edit(self, milestone: Milestone) -> bool:
        if self._is_admin():
            return True
        if milestone.workpackage_id is None:
            # Gesamtprojekt-Meilenstein: nur Admin.
            return False
        if not self.person_id:
            return False
        return WorkpackageService(self.session).is_wp_lead(self.person_id, milestone.workpackage_id)

    # ---- write ----------------------------------------------------------

    def create(
        self,
        *,
        code: str,
        title: str,
        planned_date: date,
        workpackage_id: str | None = None,
        actual_date: date | None = None,
        status: str = "planned",
        note: str | None = None,
    ) -> Milestone:
        """Anlegen — schreibend nur intern (Seed/Tests). Audit-frei."""
        if status not in MILESTONE_STATUSES:
            raise ValueError(f"status: ungültiger Wert {status!r}")
        if workpackage_id is not None and self.session.get(Workpackage, workpackage_id) is None:
            raise LookupError(f"Workpackage {workpackage_id} nicht gefunden.")
        if status == "achieved" and actual_date is None:
            actual_date = date.today()
        milestone = Milestone(
            code=code,
            title=title,
            workpackage_id=workpackage_id,
            planned_date=planned_date,
            actual_date=actual_date,
            status=status,
            note=normalise_text(note),
        )
        self.session.add(milestone)
        self.session.flush()
        return milestone

    def _snapshot(self, milestone: Milestone) -> dict[str, object]:
        return {
            "title": milestone.title,
            "workpackage_id": milestone.workpackage_id,
            "planned_date": milestone.planned_date.isoformat() if milestone.planned_date else None,
            "actual_date": milestone.actual_date.isoformat() if milestone.actual_date else None,
            "status": milestone.status,
            "note": milestone.note,
        }

    def update(self, milestone_id: str, **fields: object) -> Milestone:
        milestone = self.get(milestone_id)
        if milestone is None:
            raise LookupError(f"Meilenstein {milestone_id} nicht gefunden.")
        if not self.can_edit(milestone):
            raise PermissionError(
                "Nur Admin oder WP-Lead des Meilenstein-Arbeitspakets "
                "darf diesen Meilenstein ändern."
            )
        before = self._snapshot(milestone)

        # Cleanup + Validierung pro Feld.
        cleaned: dict[str, object] = {}
        for key, raw in fields.items():
            if key not in WRITABLE_FIELDS:
                continue
            value: object = raw
            if isinstance(value, str):
                value = normalise_text(value)
            if key == "status" and value not in MILESTONE_STATUSES:
                raise ValueError(
                    f"status: ungültiger Wert {raw!r} — erlaubt: {', '.join(MILESTONE_STATUSES)}"
                )
            if key == "workpackage_id":
                if isinstance(value, str) and value:
                    if self.session.get(Workpackage, value) is None:
                        raise LookupError(f"Workpackage {value} nicht gefunden.")
                else:
                    value = None
            cleaned[key] = value

        # Status/actual_date-Regel: achieved + kein actual_date → heute.
        new_status = cleaned.get("status", milestone.status)
        if (
            new_status == "achieved"
            and "actual_date" not in cleaned
            and milestone.actual_date is None
        ):
            cleaned["actual_date"] = date.today()

        for key, value in cleaned.items():
            setattr(milestone, key, value)
        self.session.flush()
        if self.audit is not None:
            after = self._snapshot(milestone)
            if after != before:
                self.audit.log(
                    "milestone.update",
                    entity_type="milestone",
                    entity_id=milestone.id,
                    before=before,
                    after=after,
                )
        return milestone
