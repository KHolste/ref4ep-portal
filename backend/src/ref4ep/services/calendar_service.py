"""Aggregierter Projektkalender (Block 0023).

Liest Termine aus den vorhandenen Quell-Tabellen — kein neues
Datenmodell, keine Migration:

- ``Meeting``         (starts_at, ends_at)            type ``meeting``
- ``TestCampaign``    (starts_on, ends_on)            type ``campaign``
- ``Milestone``       (planned_date)                  type ``milestone``
- ``MeetingAction``   (due_date)                      type ``action``

Entscheidungen, die der Service trifft:

- **Meilensteine** werden grundsätzlich über ``planned_date``
  einsortiert. **Ausnahme**: Wenn ``status == 'achieved'`` UND
  ``actual_date`` gesetzt ist, gilt ``actual_date`` als Kalenderdatum —
  fachlich liegt der Meilenstein dann am echten Erreichungstag, nicht
  am ursprünglichen Plandatum. Die Description enthält in dem Fall
  beide Daten („Plandatum: …  ·  Ist-Datum: …"), damit die
  Verschiebung nachvollziehbar bleibt. Es gibt nie zwei Einträge für
  denselben Meilenstein.
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
from datetime import date, datetime, time, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ref4ep.domain.models import (
    MEETING_RECURRENCE_LABELS_DE,
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


def _start_of_day(d: date) -> datetime:
    """Tagesanfang als naive ``datetime`` in lokaler Projektzeit.

    Das Portal behandelt vom Nutzer eingegebene Zeiten konsistent als
    naive Werte in Europe/Berlin (siehe Frontend-Helfer in common.js).
    Damit Sortierung und Vergleiche zwischen Quellen aufgehen, müssen
    auch die aus ``date``-Spalten abgeleiteten Werte naive bleiben."""
    return datetime.combine(d, time.min)


def _end_of_day(d: date) -> datetime:
    """Tagesende als naive ``datetime`` in lokaler Projektzeit."""
    return datetime.combine(d, time.max)


def _strip_tzinfo(dt: datetime | None) -> datetime | None:
    """Datetime auf naive normalisieren, ohne den Wert umzurechnen.

    Hintergrund: Die Meeting-Tabelle ist als ``DateTime(timezone=True)``
    deklariert, SQLite speichert sie aber als naive Zeichenkette und
    liefert sie auch naive zurück. Eingehende Datentypen aus Tests/
    Migrationen können vereinzelt aware sein — wir entfernen das
    ``tzinfo``, damit ``events.sort(...)`` (das die Quellen mischt) nie
    auf ``can't compare naive and aware datetimes`` läuft.

    Der Wert wird **nicht** in eine andere Zeitzone konvertiert — die
    bisher fälschliche UTC-Etikettierung war genau die Ursache der
    Zwei-Stunden-Verschiebung in der Meeting-Anzeige."""
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def _format_date_de(d: date) -> str:
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def _wp_codes_from_links(links: Iterable) -> list[str]:
    return sorted(link.workpackage.code for link in links if link.workpackage is not None)


# --------------------------------------------------------------------------- #
# Wiederholungen (Block 0052 — V1)                                            #
# --------------------------------------------------------------------------- #

# Sicherheits-Backstop gegen Endlosschleifen. Die Expansion ist ohnehin
# durch das abgefragte Fenster UND ``recurrence_until`` begrenzt; dieser
# Deckel greift nur bei kaputten Daten.
_MAX_OCCURRENCES = 750


def expand_recurrence_dates(
    base_date: date,
    rule: str,
    until: date,
    *,
    window_from: date,
    window_to: date,
) -> list[date]:
    """Konkrete Vorkommen einer Serie INNERHALB des Fensters.

    Erzeugt nur Termine im Bereich ``[window_from, window_to]`` und nie
    nach ``until`` — die Expansion ist damit doppelt begrenzt (Fenster +
    Serienende) und kann keine unbegrenzte Liste liefern.

    - ``weekly`` / ``biweekly``: Schrittweite 7 bzw. 14 Tage ab dem
      Startdatum.
    - ``monthly``: gleicher Kalendertag je Monat. Monate ohne diesen Tag
      (z. B. der 31. im Februar) werden übersprungen — kein Ausweichen
      auf einen Nachbartag.
    """
    out: list[date] = []
    if rule in ("weekly", "biweekly"):
        step = 7 if rule == "weekly" else 14
        for n in range(_MAX_OCCURRENCES):
            occ = base_date + timedelta(days=step * n)
            if occ > until or occ > window_to:
                break
            if occ >= window_from:
                out.append(occ)
        return out
    if rule == "monthly":
        for n in range(_MAX_OCCURRENCES):
            year = base_date.year + (base_date.month - 1 + n) // 12
            month = (base_date.month - 1 + n) % 12 + 1
            # Jeder Tag eines Monats liegt >= dem Monatsersten; sobald der
            # Monatserste sowohl ``until`` als auch das Fensterende
            # überschreitet, kann kein weiteres Vorkommen mehr passen.
            month_first = date(year, month, 1)
            if month_first > until or month_first > window_to:
                break
            try:
                occ = date(year, month, base_date.day)
            except ValueError:
                continue  # diesen Monat gibt es den Tag nicht → überspringen
            if occ > until or occ > window_to:
                break
            if occ >= window_from:
                out.append(occ)
        return out
    # ``none`` oder unbekannt → keine Expansion.
    return []


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
        from_dt = _start_of_day(from_)
        to_dt = _end_of_day(to)
        # Range-Overlap auf datetime-Spalten. Zwei Fälle:
        #   - Einmalige Termine (recurrence_rule == 'none'): wie bisher
        #     COALESCE(ends_at, starts_at) >= from_dt.
        #   - Serien (recurrence_rule != 'none'): die Serie überlappt das
        #     Fenster, wenn ihr Beginn nicht nach ``to`` liegt UND ihr
        #     Ende (recurrence_until) nicht vor ``from`` liegt. Die
        #     konkreten Vorkommen werden danach in Python expandiert.
        stmt = select(Meeting).where(
            Meeting.starts_at <= to_dt,
            or_(
                (Meeting.recurrence_rule == "none")
                & or_(
                    Meeting.ends_at.is_(None) & (Meeting.starts_at >= from_dt),
                    Meeting.ends_at >= from_dt,
                ),
                (Meeting.recurrence_rule != "none") & (Meeting.recurrence_until >= from_),
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
            base_start = _strip_tzinfo(m.starts_at)
            base_end = _strip_tzinfo(m.ends_at)
            recurring = m.recurrence_rule not in (None, "none") and m.recurrence_until is not None

            if not recurring:
                description_parts: list[str] = []
                if m.location:
                    description_parts.append(f"Ort: {m.location}")
                if base_end:
                    description_parts.append(f"Ende: {base_end.strftime('%d.%m.%Y %H:%M')}")
                out.append(
                    CalendarEvent(
                        id=f"meeting:{m.id}",
                        source_id=m.id,
                        type="meeting",
                        title=m.title,
                        starts_at=base_start,
                        ends_at=base_end,
                        all_day=False,
                        status=m.status,
                        workpackage_codes=wp_codes,
                        link=f"/portal/meetings/{m.id}",
                        description=" · ".join(description_parts) or None,
                        is_overdue=False,
                    )
                )
                continue

            # Serie: konkrete Vorkommen NUR im abgefragten Fenster erzeugen.
            duration = (base_end - base_start) if base_end else None
            series_note = (
                f"Serie: {MEETING_RECURRENCE_LABELS_DE.get(m.recurrence_rule, m.recurrence_rule)}"
                f" bis {_format_date_de(m.recurrence_until)}"
            )
            for occ_date in expand_recurrence_dates(
                base_start.date(),
                m.recurrence_rule,
                m.recurrence_until,
                window_from=from_,
                window_to=to,
            ):
                occ_start = datetime.combine(occ_date, base_start.time())
                occ_end = (occ_start + duration) if duration is not None else None
                description_parts = []
                if m.location:
                    description_parts.append(f"Ort: {m.location}")
                if occ_end:
                    description_parts.append(f"Ende: {occ_end.strftime('%d.%m.%Y %H:%M')}")
                description_parts.append(series_note)
                out.append(
                    CalendarEvent(
                        # Pro Vorkommen eindeutige ID (gleiche source_id);
                        # die UI rendert so mehrere konkrete Termine einer Serie.
                        id=f"meeting:{m.id}:{occ_date.isoformat()}",
                        source_id=m.id,
                        type="meeting",
                        title=m.title,
                        starts_at=occ_start,
                        ends_at=occ_end,
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
                    starts_at=_start_of_day(c.starts_on),
                    ends_at=_start_of_day(c.ends_on) if c.ends_on else None,
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
        # Effektives Kalenderdatum:
        #   - status='achieved' UND actual_date gesetzt → actual_date
        #   - sonst                                       → planned_date
        # Damit verschiebt sich ein „erreichter" Meilenstein im Kalender
        # auf seinen tatsächlichen Erreichungstag — bei einem Meilenstein
        # wird also nie zweimal gerendert.
        achieved_in_window = (
            (Milestone.status == "achieved")
            & Milestone.actual_date.is_not(None)
            & (Milestone.actual_date >= from_)
            & (Milestone.actual_date <= to)
        )
        planned_in_window = (
            ((Milestone.status != "achieved") | Milestone.actual_date.is_(None))
            & (Milestone.planned_date >= from_)
            & (Milestone.planned_date <= to)
        )
        stmt = select(Milestone).where(or_(achieved_in_window, planned_in_window))
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
            uses_actual = ms.status == "achieved" and ms.actual_date is not None
            effective_date = ms.actual_date if uses_actual else ms.planned_date
            description_parts: list[str] = []
            if uses_actual:
                # Beide Daten in der Description, damit die Verschiebung
                # vom Plan- zum Ist-Termin nachvollziehbar bleibt.
                description_parts.append(
                    f"Plandatum: {_format_date_de(ms.planned_date)} "
                    f"· Ist-Datum: {_format_date_de(ms.actual_date)}"
                )
            elif ms.actual_date is not None:
                # Ist-Datum gesetzt, aber nicht „achieved" → trotzdem
                # transparent als Zusatzinfo zeigen.
                description_parts.append(f"Ist-Datum: {_format_date_de(ms.actual_date)}")
            if not wp_codes:
                description_parts.append("Gesamtprojekt")
            out.append(
                CalendarEvent(
                    id=f"milestone:{ms.id}",
                    source_id=ms.id,
                    type="milestone",
                    title=f"{ms.code} — {ms.title}",
                    starts_at=_start_of_day(effective_date),
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
                    starts_at=_start_of_day(a.due_date),
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
