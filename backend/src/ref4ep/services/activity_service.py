"""Aktivitäts-Feed (Block 0018).

Liest die letzten ``audit_log``-Einträge und mappt sie auf eine
für die UI lesbare Struktur. Sicherheits-Filter:
- Keine Klartext-Beschluss- oder Aufgabentexte werden weitergegeben.
- Keine Passwort-Felder.
- Personenbezogene Aktionen (Person anlegen / Passwort) werden zwar
  als „team"-Eintrag geführt, aber nur mit Aktor + neutralem Titel.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ref4ep.domain.models import (
    AuditLog,
    Document,
    Meeting,
    MeetingAction,
    MeetingDecision,
    Milestone,
    Workpackage,
)

# Mapping action-prefix → category in der UI.
_ACTION_TO_CATEGORY: dict[str, str] = {
    "document.": "document",
    "meeting.delete": "meeting",
    "meeting.cancel": "meeting",
    "meeting.create": "meeting",
    "meeting.update": "meeting",
    "meeting.participant.": "meeting",
    "meeting.document_link.": "meeting",
    "meeting.action.": "action",
    "meeting.decision.": "decision",
    "workpackage.update_status": "workpackage",
    "workpackage.create": "workpackage",
    "milestone.": "milestone",
    "membership.": "team",
    "person.create": "team",
    "person.create_by_wp_lead": "team",
    "person.update": "team",
    "person.set_role": "team",
    "person.enable": "team",
    "person.disable": "team",
    "person.reset_password": "team",
    "partner.": "team",
    "partner_contact.": "team",
}

# Aktionen, die wir bewusst nicht ausspielen — z. B. eigene
# Passwortänderungen sind reine Selbst-Operationen.
_SUPPRESSED_ACTIONS: frozenset[str] = frozenset({"person.change_password"})

# Maximale Antwortgröße — Block-pragmatisch.
DEFAULT_LIMIT = 50
DEFAULT_LOOKBACK_DAYS = 14


@dataclass(frozen=True)
class ActivityEntry:
    timestamp: datetime
    actor: str | None
    type: str
    title: str
    description: str | None
    link: str | None


def _category_for(action: str) -> str:
    for prefix, cat in _ACTION_TO_CATEGORY.items():
        if action.startswith(prefix):
            return cat
    return "other"


def _safe_load_details(details: str | None) -> dict | None:
    if not details:
        return None
    try:
        data = json.loads(details)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _short_title_for(
    session: Session, action: str, entity_type: str, entity_id: str
) -> tuple[str, str | None]:
    """Liefert ``(title, link)`` für den Audit-Eintrag — neutraler
    Titel, kein vertraulicher Inhalt."""
    if entity_type == "document":
        doc = session.get(Document, entity_id)
        if doc is not None:
            return f"Dokument: {doc.title}", f"/portal/documents/{doc.id}"
    if entity_type == "meeting":
        meeting = session.get(Meeting, entity_id)
        if meeting is not None:
            return f"Meeting: {meeting.title}", f"/portal/meetings/{meeting.id}"
    if entity_type == "meeting_action":
        action_obj = session.get(MeetingAction, entity_id)
        if action_obj is not None:
            return ("Aufgabe in Meeting aktualisiert", f"/portal/meetings/{action_obj.meeting_id}")
    if entity_type == "meeting_decision":
        decision = session.get(MeetingDecision, entity_id)
        if decision is not None:
            return (
                "Beschluss in Meeting aktualisiert",
                f"/portal/meetings/{decision.meeting_id}",
            )
    if entity_type == "workpackage":
        wp = session.get(Workpackage, entity_id)
        if wp is not None:
            return f"Arbeitspaket: {wp.code} — {wp.title}", f"/portal/workpackages/{wp.code}"
    if entity_type == "milestone":
        ms = session.get(Milestone, entity_id)
        if ms is not None:
            return f"Meilenstein: {ms.code} — {ms.title}", "/portal/milestones"
    if entity_type == "person":
        # Bewusst keinen Personennamen — nur ein neutrales Label.
        return ("Personen- oder Team-Änderung", None)
    if entity_type == "membership":
        return ("Mitgliedschaft geändert", None)
    if entity_type == "partner":
        return ("Partnerdaten geändert", None)
    if entity_type == "partner_contact":
        return ("Partnerkontakt geändert", None)
    return (action, None)


def _description_for(action: str, details: dict | None) -> str | None:
    """Knappe Beschreibung — keine Klartextinhalte aus Beschlüssen/Aufgaben."""
    if details is None:
        return None
    after = details.get("after") or {}
    if action == "workpackage.update_status":
        new = (after or {}).get("status")
        if new:
            return f"Status → {new}"
    if action == "milestone.update":
        new = (after or {}).get("status")
        if new:
            return f"Status → {new}"
    if action.startswith("meeting.action."):
        new = (after or {}).get("status")
        if new:
            return f"Aufgabenstatus → {new}"
    if action.startswith("meeting.decision."):
        new = (after or {}).get("status")
        if new:
            return f"Beschlussstatus → {new}"
    if action == "meeting.cancel":
        return "Meeting wurde abgesagt"
    if action == "meeting.delete":
        return "Meeting wurde gelöscht"
    if action == "meeting.create":
        return "Meeting wurde angelegt"
    if action == "document.create":
        return "Dokument wurde angelegt"
    if action.startswith("document."):
        return action.replace("document.", "Dokument: ")
    if action == "membership.add" or action == "membership.add_by_wp_lead":
        return "Mitglied wurde hinzugefügt"
    if action == "membership.remove" or action == "membership.remove_by_wp_lead":
        return "Mitglied wurde entfernt"
    if action.startswith("person.create"):
        return "Person wurde angelegt"
    return None


class ActivityService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def recent(
        self,
        *,
        since: datetime | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> list[ActivityEntry]:
        """Liefert die letzten Audit-Einträge ab ``since`` als
        Aktivitätsstrom. Default: ``DEFAULT_LOOKBACK_DAYS`` Tage."""
        if since is None:
            since = datetime.now(tz=UTC) - timedelta(days=DEFAULT_LOOKBACK_DAYS)
        stmt = (
            select(AuditLog)
            .where(AuditLog.created_at >= since)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        out: list[ActivityEntry] = []
        for entry in self.session.scalars(stmt):
            if entry.action in _SUPPRESSED_ACTIONS:
                continue
            cat = _category_for(entry.action)
            details = _safe_load_details(entry.details)
            title, link = _short_title_for(
                self.session, entry.action, entry.entity_type, entry.entity_id
            )
            description = _description_for(entry.action, details)
            actor = self._actor_label(entry)
            out.append(
                ActivityEntry(
                    timestamp=entry.created_at,
                    actor=actor,
                    type=cat,
                    title=title,
                    description=description,
                    link=link,
                )
            )
        return out

    @staticmethod
    def _actor_label(entry: AuditLog) -> str | None:
        if entry.actor is not None:
            return entry.actor.display_name or entry.actor.email
        return entry.actor_label
