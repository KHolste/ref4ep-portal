"""Aggregierter Projektkalender (Block 0023).

Liest Termine aus den vorhandenen Quell-Tabellen — kein neues
Datenmodell, keine Migration:

- ``Meeting``         (starts_at, ends_at)            type ``meeting``
- ``TestCampaign``    (starts_on, ends_on)            type ``campaign``
- ``Milestone``       (planned_date)                  type ``milestone``
- ``MeetingAction``   (due_date)                      type ``action``

Entscheidungen, die der Service trifft:

- **Meilensteine** werden konsistent über ``planned_date`` einsortiert,
  auch wenn ``actual_date`` und ``status='achieved'`` gesetzt sind. So
  bleibt der Kalender als Plansicht stabil; das tatsächliche Datum
  steht in der Beschreibung. (Begründung: würde sich beim Wechsel auf
  ``actual_date`` der Eintrag verschieben, wäre die Plansicht unruhig.)
- **Abgesagte / abgebrochene Events** (Meeting ``status='cancelled'``,
  Campaign ``status='cancelled'``) bleiben **sichtbar**, aber mit
  unverändertem Status — die UI hängt eine ``calendar-event-cancelled``-
  Klasse an. So bleibt nachvollziehbar, was ursprünglich geplant war.
- **MS4 / Gesamtprojekt-Meilenstein** (``workpackage_id IS NULL``)
  wird auch bei ``mine=true`` mitgeliefert, weil er für alle relevant
  ist.
- **Aufgaben** sind ``is_overdue=True``, wenn ``due_date < today``
  UND ``status in ('open','in_progress')``.

Das Backend gibt nur Lesedaten aus — keine Auditdetails, keine
Beschluss-/Aufgabentexte aus dem Audit. Die ``description`` enthält
ausschließlich kurze Kontextzeilen (Zeitraum, WP-Hinweis, Frist).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ref4ep.domain.models import (
    Meeting,
    MeetingAction,
    MeetingParticipant,
    MeetingWorkpackage,
    Membership,
    Milestone,
    TestCampaign,
    TestCampaignParticipant,
    TestCampaignWorkpackage,
    Workpackage,
)

CALENDAR_EVENT_TYPES: tuple[str, ...] = ("meeting", "campaign", "milestone", "action")


@dataclass(frozen=True)
class CalendarEvent:
    """Normalisierte Kalender-Ereignisse aus mehreren Quellen."""

    id: str  # globally unique, z. B. "meeting:<uuid>"
    source_id: str
    type: str  # meeting | campaign | milestone | action
    title: str
    starts_at: datetime
    ends_at: datetime | None
    all_day: bool
    status: str | None
    workpackage_codes: list[str]
    link: str
    description: str | None
    is_overdue: bool


# --------------------------------------------------------------------------- #
# Helfer                                                                      #
# --------------------------------------------------------------------------- #


def _start_of_day_utc(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=UTC)


def _end_of_day_utc(d: date) -> datetime:
    return datetime.combine(d, time.max, tzinfo=UTC)


def _ensure_aware_utc(dt: datetime | None) -> datetime | None:
    """SQLite reicht ``DateTime(timezone=True)`` als naive Werte zurück —
    wir hängen UTC an, damit die Sortierung über alle Quellen hinweg
    konsistent ist (sonst: ``can't compare naive and aware datetimes``)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _format_date_de(d: date) -> str:
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def _wp_codes_from_links(links: Iterable) -> list[str]:
    return sorted(link.workpackage.code for link in links if link.workpackage is not None)


# --------------------------------------------------------------------------- #
# Service                                                                     #
# --------------------------------------------------------------------------- #


class CalendarService:
    def __init__(
        self,
        session: Session,
        *,
        person_id: str | None = None,
    ) -> None:
        self.session = session
        self.person_id = person_id

    # ---- Membership-Helfer ---------------------------------------------

    def _own_wp_ids(self) -> set[str]:
        if not self.person_id:
            return set()
        rows = self.session.scalars(
            select(Membership.workpackage_id).where(Membership.person_id == self.person_id)
        ).all()
        return set(rows)

    def _wp_id_for_code(self, code: str) -> str | None:
        wp = self.session.scalars(select(Workpackage).where(Workpackage.code == code)).first()
        return wp.id if wp is not None else None

    # ---- Aggregator -----------------------------------------------------

    def list_events(
        self,
        *,
        from_: date,
        to: date,
        types: list[str] | None = None,
        workpackage_code: str | None = None,
        mine: bool = False,
        today: date | None = None,
    ) -> list[CalendarEvent]:
        if to < from_:
            raise ValueError("``to`` darf nicht vor ``from`` liegen.")
        if types is not None:
            for t in types:
                if t not in CALENDAR_EVENT_TYPES:
                    raise ValueError(f"type: ungültiger Wert {t!r}")
        active_types = set(types) if types else set(CALENDAR_EVENT_TYPES)
        today_date = today or date.today()

        wp_filter_id: str | None = None
        if workpackage_code is not None:
            wp_filter_id = self._wp_id_for_code(workpackage_code)
            if wp_filter_id is None:
                # Unbekannter WP-Code → keine Treffer.
                return []

        own_wps = self._own_wp_ids() if mine else set()

        events: list[CalendarEvent] = []
        if "meeting" in active_types:
            events.extend(
                self._meetings(
                    from_=from_,
                    to=to,
                    wp_filter_id=wp_filter_id,
                    mine=mine,
                    own_wps=own_wps,
                )
            )
        if "campaign" in active_types:
            events.extend(
                self._campaigns(
                    from_=from_,
                    to=to,
                    wp_filter_id=wp_filter_id,
                    mine=mine,
                    own_wps=own_wps,
                )
            )
        if "milestone" in active_types:
            events.extend(
                self._milestones(
                    from_=from_,
                    to=to,
                    wp_filter_id=wp_filter_id,
                    mine=mine,
                    own_wps=own_wps,
                )
            )
        if "action" in active_types:
            events.extend(
                self._actions(
                    from_=from_,
                    to=to,
                    wp_filter_id=wp_filter_id,
                    mine=mine,
                    today=today_date,
                )
            )

        # Sortierung: starts_at, dann Typ, dann Titel.
        events.sort(key=lambda e: (e.starts_at, e.type, e.title.lower()))
        return events

    # ---- Quelle: Meetings ----------------------------------------------

    def _meetings(
        self,
        *,
        from_: date,
        to: date,
        wp_filter_id: str | None,
        mine: bool,
        own_wps: set[str],
    ) -> list[CalendarEvent]:
        from_dt = _start_of_day_utc(from_)
        to_dt = _end_of_day_utc(to)
        # Range-Overlap auf datetime-Spalten:
        #   meeting.starts_at <= to_dt
        #   AND COALESCE(meeting.ends_at, meeting.starts_at) >= from_dt
        stmt = select(Meeting).where(
            Meeting.starts_at <= to_dt,
            or_(
                Meeting.ends_at.is_(None) & (Meeting.starts_at >= from_dt),
                Meeting.ends_at >= from_dt,
            ),
        )
        if wp_filter_id is not None:
            stmt = stmt.where(
                Meeting.id.in_(
                    select(MeetingWorkpackage.meeting_id).where(
                        MeetingWorkpackage.workpackage_id == wp_filter_id
                    )
                )
            )
        if mine and self.person_id:
            participant_meetings = select(MeetingParticipant.meeting_id).where(
                MeetingParticipant.person_id == self.person_id
            )
            wp_meetings = (
                select(MeetingWorkpackage.meeting_id).where(
                    MeetingWorkpackage.workpackage_id.in_(own_wps)
                )
                if own_wps
                else None
            )
            if wp_meetings is not None:
                stmt = stmt.where(
                    or_(
                        Meeting.id.in_(participant_meetings),
                        Meeting.id.in_(wp_meetings),
                    )
                )
            else:
                stmt = stmt.where(Meeting.id.in_(participant_meetings))

        out: list[CalendarEvent] = []
        for m in self.session.scalars(stmt):
            wp_codes = _wp_codes_from_links(m.workpackage_links)
            description_parts: list[str] = []
            if m.location:
                description_parts.append(f"Ort: {m.location}")
            if m.ends_at:
                description_parts.append(f"Ende: {m.ends_at.strftime('%d.%m.%Y %H:%M')}")
            out.append(
                CalendarEvent(
                    id=f"meeting:{m.id}",
                    source_id=m.id,
                    type="meeting",
                    title=m.title,
                    starts_at=_ensure_aware_utc(m.starts_at),
                    ends_at=_ensure_aware_utc(m.ends_at),
                    all_day=False,
                    status=m.status,
                    workpackage_codes=wp_codes,
                    link=f"/portal/meetings/{m.id}",
                    description=" · ".join(description_parts) or None,
                    is_overdue=False,
                )
            )
        return out

    # ---- Quelle: Testkampagnen -----------------------------------------

    def _campaigns(
        self,
        *,
        from_: date,
        to: date,
        wp_filter_id: str | None,
        mine: bool,
        own_wps: set[str],
    ) -> list[CalendarEvent]:
        # Datum-Range-Overlap:
        #   starts_on <= to AND COALESCE(ends_on, starts_on) >= from
        stmt = select(TestCampaign).where(
            TestCampaign.starts_on <= to,
            or_(
                TestCampaign.ends_on.is_(None) & (TestCampaign.starts_on >= from_),
                TestCampaign.ends_on >= from_,
            ),
        )
        if wp_filter_id is not None:
            stmt = stmt.where(
                TestCampaign.id.in_(
                    select(TestCampaignWorkpackage.campaign_id).where(
                        TestCampaignWorkpackage.workpackage_id == wp_filter_id
                    )
                )
            )
        if mine and self.person_id:
            participant_campaigns = select(TestCampaignParticipant.campaign_id).where(
                TestCampaignParticipant.person_id == self.person_id
            )
            wp_campaigns = (
                select(TestCampaignWorkpackage.campaign_id).where(
                    TestCampaignWorkpackage.workpackage_id.in_(own_wps)
                )
                if own_wps
                else None
            )
            if wp_campaigns is not None:
                stmt = stmt.where(
                    or_(
                        TestCampaign.id.in_(participant_campaigns),
                        TestCampaign.id.in_(wp_campaigns),
                    )
                )
            else:
                stmt = stmt.where(TestCampaign.id.in_(participant_campaigns))

        out: list[CalendarEvent] = []
        for c in self.session.scalars(stmt):
            wp_codes = _wp_codes_from_links(c.workpackage_links)
            period = (
                f"{_format_date_de(c.starts_on)} – {_format_date_de(c.ends_on)}"
                if c.ends_on
                else _format_date_de(c.starts_on)
            )
            description_parts: list[str] = [f"Zeitraum: {period}"]
            if c.facility:
                description_parts.append(f"Facility: {c.facility}")
            out.append(
                CalendarEvent(
                    id=f"campaign:{c.id}",
                    source_id=c.id,
                    type="campaign",
                    title=f"{c.code} — {c.title}",
                    # MVP: Anzeige am Startdatum, Zeitraum in der description.
                    starts_at=_start_of_day_utc(c.starts_on),
                    ends_at=_start_of_day_utc(c.ends_on) if c.ends_on else None,
                    all_day=True,
                    status=c.status,
                    workpackage_codes=wp_codes,
                    link=f"/portal/campaigns/{c.id}",
                    description=" · ".join(description_parts),
                    is_overdue=False,
                )
            )
        return out

    # ---- Quelle: Meilensteine ------------------------------------------

    def _milestones(
        self,
        *,
        from_: date,
        to: date,
        wp_filter_id: str | None,
        mine: bool,
        own_wps: set[str],
    ) -> list[CalendarEvent]:
        # Konsistent über planned_date einsortieren — siehe Modul-Docstring.
        stmt = select(Milestone).where(
            Milestone.planned_date >= from_,
            Milestone.planned_date <= to,
        )
        if wp_filter_id is not None:
            stmt = stmt.where(Milestone.workpackage_id == wp_filter_id)
        if mine:
            # Eigene WPs ODER MS4 (workpackage_id IS NULL) — Gesamtprojekt
            # ist für alle relevant.
            if own_wps:
                stmt = stmt.where(
                    or_(
                        Milestone.workpackage_id.in_(own_wps),
                        Milestone.workpackage_id.is_(None),
                    )
                )
            else:
                stmt = stmt.where(Milestone.workpackage_id.is_(None))

        out: list[CalendarEvent] = []
        for ms in self.session.scalars(stmt):
            wp_codes = [ms.workpackage.code] if ms.workpackage is not None else []
            description_parts: list[str] = []
            if ms.actual_date is not None:
                description_parts.append(f"Ist-Datum: {_format_date_de(ms.actual_date)}")
            if not wp_codes:
                description_parts.append("Gesamtprojekt")
            out.append(
                CalendarEvent(
                    id=f"milestone:{ms.id}",
                    source_id=ms.id,
                    type="milestone",
                    title=f"{ms.code} — {ms.title}",
                    starts_at=_start_of_day_utc(ms.planned_date),
                    ends_at=None,
                    all_day=True,
                    status=ms.status,
                    workpackage_codes=wp_codes,
                    link="/portal/milestones",
                    description=" · ".join(description_parts) or None,
                    is_overdue=False,
                )
            )
        return out

    # ---- Quelle: Aufgaben ----------------------------------------------

    def _actions(
        self,
        *,
        from_: date,
        to: date,
        wp_filter_id: str | None,
        mine: bool,
        today: date,
    ) -> list[CalendarEvent]:
        # Aufgaben ohne due_date erscheinen NICHT im Kalender.
        stmt = select(MeetingAction).where(
            MeetingAction.due_date.is_not(None),
            MeetingAction.due_date >= from_,
            MeetingAction.due_date <= to,
        )
        if wp_filter_id is not None:
            stmt = stmt.where(MeetingAction.workpackage_id == wp_filter_id)
        if mine and self.person_id:
            stmt = stmt.where(MeetingAction.responsible_person_id == self.person_id)

        out: list[CalendarEvent] = []
        for a in self.session.scalars(stmt):
            wp_codes = [a.workpackage.code] if a.workpackage is not None else []
            is_overdue = bool(
                a.due_date is not None
                and a.due_date < today
                and a.status in ("open", "in_progress")
            )
            description_parts: list[str] = [f"Frist: {_format_date_de(a.due_date)}"]
            if a.responsible is not None:
                description_parts.append(f"Verantwortlich: {a.responsible.display_name}")
            if a.meeting is not None:
                description_parts.append(f"Aus Meeting: {a.meeting.title}")
            out.append(
                CalendarEvent(
                    id=f"action:{a.id}",
                    source_id=a.id,
                    type="action",
                    # ``a.text`` kann lang sein; kürzen wir bewusst nicht im
                    # Backend — die UI macht das per CSS.
                    title=a.text,
                    starts_at=_start_of_day_utc(a.due_date),
                    ends_at=None,
                    all_day=True,
                    status=a.status,
                    workpackage_codes=wp_codes,
                    # Aufgaben verlinken zur Meeting-Detail (dort sind sie
                    # bearbeitbar). Falls ohne Meeting → Aufgaben-Übersicht.
                    link=(
                        f"/portal/meetings/{a.meeting_id}" if a.meeting_id else "/portal/actions"
                    ),
                    description=" · ".join(description_parts),
                    is_overdue=is_overdue,
                )
            )
        return out
