"""Meeting-/Protokollregister (Block 0015).

Ein einziger Service kapselt CRUD für ``Meeting``,
``MeetingDecision``, ``MeetingAction``, ``MeetingDocumentLink`` und
``MeetingParticipant``. Berechtigungslogik liegt zentral in
``can_edit_meeting`` und wird von allen Schreibmethoden geteilt.

Berechtigungs-Regel (im Bericht dokumentiert):
- Admin darf alles.
- WP-Lead darf ein Meeting anlegen/bearbeiten gdw. **alle** mit dem
  Meeting verknüpften Workpackages zu seinen ``wp_lead``-WPs gehören.
- Konsortialtreffen ohne WP-Bezug → nur Admin.
- Wenn ein bestehendes Meeting fremde WPs enthält, kann der WP-Lead
  es nicht bearbeiten — bewusste Vereinfachung gegenüber feiner
  Feldlogik. Im Bericht festgehalten.

Hard-Delete gibt es nicht. Meetings werden über
``cancel_meeting`` auf ``status='cancelled'`` gesetzt; Decisions/
Actions verbleiben in der DB und werden über ihren eigenen Status
abgeschlossen. ``MeetingDocumentLink`` darf entfernt werden — nur
die Verknüpfung verschwindet, das Dokument bleibt.

Audit-Aktionen:
- ``meeting.create``           / ``meeting.update`` / ``meeting.cancel``
- ``meeting.decision.create``  / ``meeting.decision.update``
- ``meeting.action.create``    / ``meeting.action.update``
- ``meeting.document_link.add`` / ``meeting.document_link.remove``
- ``meeting.participant.add``  / ``meeting.participant.remove``
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ref4ep.domain.models import (
    MEETING_ACTION_STATUSES,
    MEETING_CATEGORIES,
    MEETING_DECISION_STATUSES,
    MEETING_DOCUMENT_LABELS,
    MEETING_FORMATS,
    MEETING_STATUSES,
    Document,
    Meeting,
    MeetingAction,
    MeetingDecision,
    MeetingDocumentLink,
    MeetingParticipant,
    MeetingWorkpackage,
    Membership,
    Person,
    Workpackage,
)
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.permissions import can_admin
from ref4ep.services.validators import normalise_text


def _filter_workpackage_ids(session: Session, workpackage_ids: Iterable[str]) -> list[str]:
    """Verifiziert, dass alle WP-IDs existieren und nicht gelöscht sind.

    Wirft ``LookupError``, wenn eine ID nicht gefunden wird.
    Dedupliziert und behält die Eingabereihenfolge.
    """
    seen: list[str] = []
    seen_set: set[str] = set()
    for wp_id in workpackage_ids:
        if wp_id in seen_set:
            continue
        wp = session.get(Workpackage, wp_id)
        if wp is None or wp.is_deleted:
            raise LookupError(f"Workpackage {wp_id} nicht gefunden.")
        seen.append(wp_id)
        seen_set.add(wp_id)
    return seen


class MeetingService:
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

    # ---- Lese-Helfer ----------------------------------------------------

    def get(self, meeting_id: str) -> Meeting | None:
        return self.session.get(Meeting, meeting_id)

    def list_meetings(
        self,
        *,
        status: str | None = None,
        category: str | None = None,
        workpackage_code: str | None = None,
    ) -> list[Meeting]:
        stmt = select(Meeting)
        if status is not None:
            stmt = stmt.where(Meeting.status == status)
        if category is not None:
            stmt = stmt.where(Meeting.category == category)
        if workpackage_code is not None:
            wp = self.session.scalars(
                select(Workpackage).where(Workpackage.code == workpackage_code)
            ).first()
            if wp is None:
                return []
            stmt = stmt.where(
                Meeting.id.in_(
                    select(MeetingWorkpackage.meeting_id).where(
                        MeetingWorkpackage.workpackage_id == wp.id
                    )
                )
            )
        stmt = stmt.order_by(Meeting.starts_at.desc(), Meeting.title)
        return list(self.session.scalars(stmt))

    # ---- Berechtigung ---------------------------------------------------

    def _is_admin(self) -> bool:
        return can_admin(self.role or "")

    def _own_lead_wp_ids(self) -> set[str]:
        if not self.person_id:
            return set()
        rows = self.session.scalars(
            select(Membership.workpackage_id).where(
                Membership.person_id == self.person_id,
                Membership.wp_role == "wp_lead",
            )
        ).all()
        return set(rows)

    def can_edit_meeting(self, meeting: Meeting) -> bool:
        """Vollständige Berechtigungslogik fürs Schreiben am Meeting.

        - Admin: ja.
        - WP-Lead: nur, wenn das Meeting mind. eine WP hat **und**
          alle WPs zu seinen Lead-WPs gehören.
        - Sonst: nein.
        """
        if self._is_admin():
            return True
        if not self.person_id:
            return False
        wp_ids = {link.workpackage_id for link in meeting.workpackage_links}
        if not wp_ids:
            return False
        own = self._own_lead_wp_ids()
        return wp_ids.issubset(own) and bool(own & wp_ids)

    def can_create_meeting_with_workpackages(self, workpackage_ids: Iterable[str]) -> bool:
        """Wer darf ein neues Meeting mit dieser WP-Liste anlegen?

        - Admin: immer.
        - WP-Lead: nur wenn die Liste nicht leer ist und alle WPs
          seine eigenen Lead-WPs sind.
        """
        ids = set(workpackage_ids)
        if self._is_admin():
            return True
        if not ids:
            return False
        own = self._own_lead_wp_ids()
        return ids.issubset(own)

    # ---- Schreiben — Meeting -------------------------------------------

    def _validate_meeting_fields(self, *, format_: str, category: str, status: str) -> None:
        if format_ not in MEETING_FORMATS:
            raise ValueError(f"format: ungültiger Wert {format_!r}")
        if category not in MEETING_CATEGORIES:
            raise ValueError(f"category: ungültiger Wert {category!r}")
        if status not in MEETING_STATUSES:
            raise ValueError(f"status: ungültiger Wert {status!r}")

    def create_meeting(
        self,
        *,
        title: str,
        starts_at: datetime,
        ends_at: datetime | None = None,
        format_: str = "online",
        location: str | None = None,
        category: str = "other",
        status: str = "planned",
        summary: str | None = None,
        extra_participants: str | None = None,
        workpackage_ids: list[str] | None = None,
    ) -> Meeting:
        if not self.person_id:
            raise PermissionError("Anonymer Aufruf — Anlegen nicht erlaubt.")
        wp_ids = _filter_workpackage_ids(self.session, workpackage_ids or [])
        if not self.can_create_meeting_with_workpackages(wp_ids):
            raise PermissionError(
                "Nur Admin oder WP-Lead der genannten Arbeitspakete darf ein Meeting anlegen."
            )
        self._validate_meeting_fields(format_=format_, category=category, status=status)
        meeting = Meeting(
            title=title.strip(),
            starts_at=starts_at,
            ends_at=ends_at,
            format=format_,
            location=normalise_text(location),
            category=category,
            status=status,
            summary=normalise_text(summary),
            extra_participants=normalise_text(extra_participants),
            created_by_id=self.person_id,
        )
        self.session.add(meeting)
        self.session.flush()
        for wp_id in wp_ids:
            self.session.add(MeetingWorkpackage(meeting_id=meeting.id, workpackage_id=wp_id))
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "meeting.create",
                entity_type="meeting",
                entity_id=meeting.id,
                after={
                    "title": meeting.title,
                    "starts_at": meeting.starts_at.isoformat(),
                    "format": meeting.format,
                    "category": meeting.category,
                    "status": meeting.status,
                    "workpackage_ids": wp_ids,
                },
            )
        return meeting

    def update_meeting(
        self,
        meeting_id: str,
        *,
        fields: dict[str, object],
        workpackage_ids: list[str] | None = None,
    ) -> Meeting:
        meeting = self.get(meeting_id)
        if meeting is None:
            raise LookupError(f"Meeting {meeting_id} nicht gefunden.")
        if not self.can_edit_meeting(meeting):
            raise PermissionError(
                "Kein Schreibrecht — Admin oder Lead aller beteiligten WPs nötig."
            )

        before = self._meeting_snapshot(meeting)

        # Wenn die WP-Liste geändert wird, gilt für die NEUE Liste die gleiche
        # Berechtigungslogik wie beim Anlegen.
        if workpackage_ids is not None:
            new_ids = _filter_workpackage_ids(self.session, workpackage_ids)
            if not self.can_create_meeting_with_workpackages(new_ids):
                raise PermissionError("WP-Lead darf nur eigene Lead-WPs setzen.")
            current = {link.workpackage_id for link in meeting.workpackage_links}
            target = set(new_ids)
            for link in list(meeting.workpackage_links):
                if link.workpackage_id not in target:
                    self.session.delete(link)
            for wp_id in new_ids:
                if wp_id not in current:
                    self.session.add(
                        MeetingWorkpackage(meeting_id=meeting.id, workpackage_id=wp_id)
                    )

        for key, raw in fields.items():
            if key not in {
                "title",
                "starts_at",
                "ends_at",
                "format",
                "location",
                "category",
                "status",
                "summary",
                "extra_participants",
            }:
                continue
            value = raw
            if isinstance(value, str):
                value = normalise_text(value)
                if key == "title" and not value:
                    raise ValueError("title darf nicht leer sein.")
            if key == "format" and value is not None and value not in MEETING_FORMATS:
                raise ValueError(f"format: ungültiger Wert {raw!r}")
            if key == "category" and value is not None and value not in MEETING_CATEGORIES:
                raise ValueError(f"category: ungültiger Wert {raw!r}")
            if key == "status" and value is not None and value not in MEETING_STATUSES:
                raise ValueError(f"status: ungültiger Wert {raw!r}")
            setattr(meeting, key, value)
        self.session.flush()

        after = self._meeting_snapshot(meeting)
        if self.audit is not None and after != before:
            self.audit.log(
                "meeting.update",
                entity_type="meeting",
                entity_id=meeting.id,
                before=before,
                after=after,
            )
        return meeting

    def cancel_meeting(self, meeting_id: str) -> Meeting:
        """Soft-Cancel via ``status='cancelled'`` — kein Hard-Delete."""
        meeting = self.get(meeting_id)
        if meeting is None:
            raise LookupError(f"Meeting {meeting_id} nicht gefunden.")
        if not self.can_edit_meeting(meeting):
            raise PermissionError("Kein Schreibrecht für dieses Meeting.")
        if meeting.status == "cancelled":
            return meeting
        before = {"status": meeting.status}
        meeting.status = "cancelled"
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "meeting.cancel",
                entity_type="meeting",
                entity_id=meeting.id,
                before=before,
                after={"status": meeting.status},
            )
        return meeting

    def _meeting_snapshot(self, meeting: Meeting) -> dict[str, object]:
        return {
            "title": meeting.title,
            "starts_at": meeting.starts_at.isoformat() if meeting.starts_at else None,
            "ends_at": meeting.ends_at.isoformat() if meeting.ends_at else None,
            "format": meeting.format,
            "location": meeting.location,
            "category": meeting.category,
            "status": meeting.status,
            "summary": meeting.summary,
            "extra_participants": meeting.extra_participants,
            "workpackage_ids": sorted(link.workpackage_id for link in meeting.workpackage_links),
        }

    def delete_meeting_admin(self, meeting_id: str) -> None:
        """Hard-Delete eines Meetings durch einen Admin.

        Bewusst eng gefasst: nur Plattform-``admin`` darf löschen — auch
        WP-Leads des betroffenen Arbeitspakets nicht. Abhängige
        Datensätze (``meeting_workpackage``, ``meeting_participant``,
        ``meeting_decision``, ``meeting_action``,
        ``meeting_document_link``) werden über die SQLAlchemy-
        ``cascade="all, delete-orphan"``-Beziehungen am ``Meeting``
        mitentfernt — unabhängig davon, ob SQLite ``PRAGMA
        foreign_keys`` gesetzt hat. Verknüpfte ``Document``-Zeilen
        bleiben bestehen, weil ``MeetingDocumentLink`` nur die
        Verknüpfung modelliert.

        Audit-Aktion: ``meeting.delete`` mit Snapshot ``meeting_id``,
        ``title``, ``starts_at`` und betroffenen WP-Codes — keine
        sensiblen Inhalte.
        """
        if not self._is_admin():
            raise PermissionError("Nur Admin darf Meetings hart löschen.")
        meeting = self.get(meeting_id)
        if meeting is None:
            raise LookupError(f"Meeting {meeting_id} nicht gefunden.")
        # Snapshot vor dem Löschen — danach sind die Beziehungen weg.
        snapshot: dict[str, object] = {
            "meeting_id": meeting.id,
            "title": meeting.title,
            "starts_at": meeting.starts_at.isoformat() if meeting.starts_at else None,
            "workpackage_codes": sorted(
                link.workpackage.code for link in meeting.workpackage_links
            ),
        }
        self.session.delete(meeting)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "meeting.delete",
                entity_type="meeting",
                entity_id=snapshot["meeting_id"],  # type: ignore[arg-type]
                before=snapshot,
            )

    # ---- Teilnehmende ---------------------------------------------------

    def add_participant(self, meeting_id: str, person_id: str) -> MeetingParticipant:
        meeting = self.get(meeting_id)
        if meeting is None:
            raise LookupError(f"Meeting {meeting_id} nicht gefunden.")
        if not self.can_edit_meeting(meeting):
            raise PermissionError("Kein Schreibrecht für dieses Meeting.")
        person = self.session.get(Person, person_id)
        if person is None or person.is_deleted:
            raise LookupError(f"Person {person_id} nicht gefunden.")
        existing = self.session.get(MeetingParticipant, (meeting_id, person_id))
        if existing is not None:
            return existing
        participant = MeetingParticipant(meeting_id=meeting_id, person_id=person_id)
        self.session.add(participant)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "meeting.participant.add",
                entity_type="meeting",
                entity_id=meeting_id,
                after={"person_id": person_id},
            )
        return participant

    def remove_participant(self, meeting_id: str, person_id: str) -> None:
        meeting = self.get(meeting_id)
        if meeting is None:
            raise LookupError(f"Meeting {meeting_id} nicht gefunden.")
        if not self.can_edit_meeting(meeting):
            raise PermissionError("Kein Schreibrecht für dieses Meeting.")
        existing = self.session.get(MeetingParticipant, (meeting_id, person_id))
        if existing is None:
            return
        self.session.delete(existing)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "meeting.participant.remove",
                entity_type="meeting",
                entity_id=meeting_id,
                before={"person_id": person_id},
            )

    # ---- Beschlüsse -----------------------------------------------------

    def create_decision(
        self,
        meeting_id: str,
        *,
        text: str,
        workpackage_id: str | None = None,
        responsible_person_id: str | None = None,
        status: str = "open",
    ) -> MeetingDecision:
        meeting = self.get(meeting_id)
        if meeting is None:
            raise LookupError(f"Meeting {meeting_id} nicht gefunden.")
        if not self.can_edit_meeting(meeting):
            raise PermissionError("Kein Schreibrecht für dieses Meeting.")
        if status not in MEETING_DECISION_STATUSES:
            raise ValueError(f"status: ungültiger Wert {status!r}")
        text_clean = normalise_text(text)
        if not text_clean:
            raise ValueError("text darf nicht leer sein.")
        if workpackage_id is not None:
            _filter_workpackage_ids(self.session, [workpackage_id])
        if responsible_person_id is not None:
            person = self.session.get(Person, responsible_person_id)
            if person is None or person.is_deleted:
                raise LookupError(f"Person {responsible_person_id} nicht gefunden.")
        decision = MeetingDecision(
            meeting_id=meeting_id,
            workpackage_id=workpackage_id,
            text=text_clean,
            status=status,
            responsible_person_id=responsible_person_id,
        )
        self.session.add(decision)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "meeting.decision.create",
                entity_type="meeting_decision",
                entity_id=decision.id,
                after={
                    "meeting_id": meeting_id,
                    "workpackage_id": decision.workpackage_id,
                    "status": decision.status,
                },
            )
        return decision

    def update_decision(
        self,
        decision_id: str,
        *,
        fields: dict[str, object],
    ) -> MeetingDecision:
        decision = self.session.get(MeetingDecision, decision_id)
        if decision is None:
            raise LookupError(f"Beschluss {decision_id} nicht gefunden.")
        meeting = decision.meeting
        if not self.can_edit_meeting(meeting):
            raise PermissionError("Kein Schreibrecht für dieses Meeting.")
        before = {
            "text": decision.text,
            "status": decision.status,
            "workpackage_id": decision.workpackage_id,
            "responsible_person_id": decision.responsible_person_id,
        }
        for key, raw in fields.items():
            if key not in {"text", "status", "workpackage_id", "responsible_person_id"}:
                continue
            value = raw
            if isinstance(value, str):
                value = normalise_text(value)
            if key == "text" and not value:
                raise ValueError("text darf nicht leer sein.")
            if key == "status" and value not in MEETING_DECISION_STATUSES:
                raise ValueError(f"status: ungültiger Wert {raw!r}")
            if key == "workpackage_id" and value:
                _filter_workpackage_ids(self.session, [value])
            if key == "responsible_person_id" and value:
                person = self.session.get(Person, value)
                if person is None or person.is_deleted:
                    raise LookupError(f"Person {value} nicht gefunden.")
            setattr(decision, key, value if value != "" else None)
        self.session.flush()
        after = {
            "text": decision.text,
            "status": decision.status,
            "workpackage_id": decision.workpackage_id,
            "responsible_person_id": decision.responsible_person_id,
        }
        if self.audit is not None and after != before:
            self.audit.log(
                "meeting.decision.update",
                entity_type="meeting_decision",
                entity_id=decision.id,
                before=before,
                after=after,
            )
        return decision

    # ---- Aufgaben -------------------------------------------------------

    def create_action(
        self,
        meeting_id: str,
        *,
        text: str,
        workpackage_id: str | None = None,
        responsible_person_id: str | None = None,
        due_date: date | None = None,
        status: str = "open",
        note: str | None = None,
    ) -> MeetingAction:
        meeting = self.get(meeting_id)
        if meeting is None:
            raise LookupError(f"Meeting {meeting_id} nicht gefunden.")
        if not self.can_edit_meeting(meeting):
            raise PermissionError("Kein Schreibrecht für dieses Meeting.")
        if status not in MEETING_ACTION_STATUSES:
            raise ValueError(f"status: ungültiger Wert {status!r}")
        text_clean = normalise_text(text)
        if not text_clean:
            raise ValueError("text darf nicht leer sein.")
        if workpackage_id is not None:
            _filter_workpackage_ids(self.session, [workpackage_id])
        if responsible_person_id is not None:
            person = self.session.get(Person, responsible_person_id)
            if person is None or person.is_deleted:
                raise LookupError(f"Person {responsible_person_id} nicht gefunden.")
        action = MeetingAction(
            meeting_id=meeting_id,
            workpackage_id=workpackage_id,
            responsible_person_id=responsible_person_id,
            text=text_clean,
            due_date=due_date,
            status=status,
            note=normalise_text(note),
        )
        self.session.add(action)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "meeting.action.create",
                entity_type="meeting_action",
                entity_id=action.id,
                after={
                    "meeting_id": meeting_id,
                    "workpackage_id": action.workpackage_id,
                    "status": action.status,
                    "due_date": action.due_date.isoformat() if action.due_date else None,
                },
            )
        return action

    def update_action(
        self,
        action_id: str,
        *,
        fields: dict[str, object],
    ) -> MeetingAction:
        action = self.session.get(MeetingAction, action_id)
        if action is None:
            raise LookupError(f"Aufgabe {action_id} nicht gefunden.")
        meeting = action.meeting
        if not self.can_edit_meeting(meeting):
            raise PermissionError("Kein Schreibrecht für dieses Meeting.")
        before = {
            "text": action.text,
            "status": action.status,
            "workpackage_id": action.workpackage_id,
            "responsible_person_id": action.responsible_person_id,
            "due_date": action.due_date.isoformat() if action.due_date else None,
            "note": action.note,
        }
        for key, raw in fields.items():
            if key not in {
                "text",
                "status",
                "workpackage_id",
                "responsible_person_id",
                "due_date",
                "note",
            }:
                continue
            value = raw
            if isinstance(value, str):
                value = normalise_text(value)
            if key == "text" and not value:
                raise ValueError("text darf nicht leer sein.")
            if key == "status" and value not in MEETING_ACTION_STATUSES:
                raise ValueError(f"status: ungültiger Wert {raw!r}")
            if key == "workpackage_id" and value:
                _filter_workpackage_ids(self.session, [value])
            if key == "responsible_person_id" and value:
                person = self.session.get(Person, value)
                if person is None or person.is_deleted:
                    raise LookupError(f"Person {value} nicht gefunden.")
            setattr(action, key, value if value != "" else None)
        self.session.flush()
        after = {
            "text": action.text,
            "status": action.status,
            "workpackage_id": action.workpackage_id,
            "responsible_person_id": action.responsible_person_id,
            "due_date": action.due_date.isoformat() if action.due_date else None,
            "note": action.note,
        }
        if self.audit is not None and after != before:
            self.audit.log(
                "meeting.action.update",
                entity_type="meeting_action",
                entity_id=action.id,
                before=before,
                after=after,
            )
        return action

    # ---- Dokumentverknüpfungen -----------------------------------------

    def add_document_link(
        self, meeting_id: str, *, document_id: str, label: str = "other"
    ) -> MeetingDocumentLink:
        meeting = self.get(meeting_id)
        if meeting is None:
            raise LookupError(f"Meeting {meeting_id} nicht gefunden.")
        if not self.can_edit_meeting(meeting):
            raise PermissionError("Kein Schreibrecht für dieses Meeting.")
        if label not in MEETING_DOCUMENT_LABELS:
            raise ValueError(f"label: ungültiger Wert {label!r}")
        doc = self.session.get(Document, document_id)
        if doc is None or doc.is_deleted:
            raise LookupError(f"Dokument {document_id} nicht gefunden.")
        existing = self.session.get(MeetingDocumentLink, (meeting_id, document_id))
        if existing is not None:
            if existing.label != label:
                existing.label = label
                self.session.flush()
            return existing
        link = MeetingDocumentLink(meeting_id=meeting_id, document_id=document_id, label=label)
        self.session.add(link)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "meeting.document_link.add",
                entity_type="meeting",
                entity_id=meeting_id,
                after={"document_id": document_id, "label": label},
            )
        return link

    def remove_document_link(self, meeting_id: str, document_id: str) -> None:
        meeting = self.get(meeting_id)
        if meeting is None:
            raise LookupError(f"Meeting {meeting_id} nicht gefunden.")
        if not self.can_edit_meeting(meeting):
            raise PermissionError("Kein Schreibrecht für dieses Meeting.")
        existing = self.session.get(MeetingDocumentLink, (meeting_id, document_id))
        if existing is None:
            return
        label = existing.label
        self.session.delete(existing)
        self.session.flush()
        if self.audit is not None:
            self.audit.log(
                "meeting.document_link.remove",
                entity_type="meeting",
                entity_id=meeting_id,
                before={"document_id": document_id, "label": label},
            )
