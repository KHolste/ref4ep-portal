// Aggregierter Projektkalender (Block 0023).
//
// Reine Lesesicht. Lädt /api/calendar/events?from=…&to=…&… und
// zeichnet ein Monatsraster + eine Agenda-Liste. Bearbeiten erfolgt
// weiterhin auf den jeweiligen Detailseiten — der Kalender hat KEINE
// Drag-and-Drop-Funktion, KEINE ICS-Exporte, KEINE E-Mail-Versendung.
//
// Quellen werden im Backend zusammengeführt — vier Typen:
//   meeting / campaign / milestone / action
//
// Visuelle Unterscheidung über CSS-Klassen plus Typ-Text auf jedem
// Chip — nicht nur Farbe.

import {
  api,
  appendChildren,
  crossNav,
  h,
  renderEmpty,
  renderError,
  renderLoading,
  renderRichEmpty,
} from "/portal/common.js";

const TYPE_LABELS = {
  meeting: "Meeting",
  campaign: "Kampagne",
  milestone: "Meilenstein",
  action: "Aufgabe",
};

const TYPE_FILTER_OPTIONS = [
  { value: "", label: "Alle Typen" },
  { value: "meeting", label: "Meetings" },
  { value: "campaign", label: "Testkampagnen" },
  { value: "milestone", label: "Meilensteine" },
  { value: "action", label: "Aufgaben" },
];

const MONTH_NAMES_DE = [
  "Januar",
  "Februar",
  "März",
  "April",
  "Mai",
  "Juni",
  "Juli",
  "August",
  "September",
  "Oktober",
  "November",
  "Dezember",
];

const WEEKDAYS_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

// Maximale Chips, die direkt in einer Tageszelle erscheinen — Rest
// landet als „+N weitere"-Hinweis. Agenda-Liste zeigt alle.
const MAX_CHIPS_PER_DAY = 4;

// ---- Datums-Helfer ----------------------------------------------------

function pad2(n) {
  return String(n).padStart(2, "0");
}

function isoDate(d) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function startOfMonth(d) {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function endOfMonth(d) {
  return new Date(d.getFullYear(), d.getMonth() + 1, 0);
}

function addMonths(d, n) {
  return new Date(d.getFullYear(), d.getMonth() + n, 1);
}

function sameDay(a, b) {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function formatDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("de-DE", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDateOnly(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("de-DE", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

// ---- Event-Klassen / -Status ------------------------------------------

const PHASE_LABELS = {
  start: "Start",
  running: "läuft",
  end: "Ende",
};

function eventClasses(event, phase) {
  const cls = [`calendar-event`, `calendar-event-${event.type}`];
  if (phase && phase !== "single") cls.push(`calendar-event-phase-${phase}`);
  if (event.is_overdue) cls.push("calendar-event-overdue");
  if (event.status === "cancelled") cls.push("calendar-event-cancelled");
  return cls.join(" ");
}

function eventTooltip(event, phase) {
  // Vollständiger Tooltip — der Chip zeigt nur einen Ausschnitt.
  const lines = [];
  const typeLabel = TYPE_LABELS[event.type] || event.type;
  lines.push(`${typeLabel}: ${event.title}`);
  if (event.all_day) {
    if (
      event.ends_at &&
      !sameDay(new Date(event.starts_at), new Date(event.ends_at))
    ) {
      lines.push(
        `Zeitraum: ${formatDateOnly(event.starts_at)} – ${formatDateOnly(event.ends_at)}`,
      );
    } else {
      lines.push(`Datum: ${formatDateOnly(event.starts_at)}`);
    }
  } else if (event.ends_at) {
    lines.push(
      `Zeitraum: ${formatDateTime(event.starts_at)} – ${formatDateTime(event.ends_at)}`,
    );
  } else {
    lines.push(`Datum: ${formatDateTime(event.starts_at)}`);
  }
  if (event.status) lines.push(`Status: ${event.status}`);
  if (event.workpackage_codes && event.workpackage_codes.length) {
    lines.push(`WP: ${event.workpackage_codes.join(", ")}`);
  }
  if (event.is_overdue) lines.push("Überfällig");
  if (phase && phase !== "single") {
    lines.push(`Phase: ${PHASE_LABELS[phase]}`);
  }
  if (event.description) lines.push(event.description);
  return lines.join("\n");
}

function eventChip(event, phase = "single") {
  // Chip im Monatsraster: optionales Phasen-Präfix + Typkürzel + Titel,
  // klickbar; voller Inhalt liegt im title-Tooltip.
  const typeLabel = TYPE_LABELS[event.type] || event.type;
  const phaseText =
    phase && phase !== "single" ? PHASE_LABELS[phase] || null : null;
  return h(
    "a",
    {
      class: eventClasses(event, phase),
      href: event.link,
      title: eventTooltip(event, phase),
    },
    phaseText ? h("span", { class: "calendar-event-phase" }, phaseText) : null,
    h("span", { class: "calendar-event-type" }, typeLabel),
    " ",
    h("span", { class: "calendar-event-title" }, event.title),
  );
}

// ---- Multi-day-Expansion -----------------------------------------------
//
// Mehrtägige Testkampagnen werden für das Monatsraster auf eine
// Eintragsinstanz **pro betroffenen Kalendertag** expandiert. Jede
// Instanz trägt die Phase ``start`` / ``running`` / ``end``. Die
// Agenda-Liste verarbeitet dagegen die unveränderte Event-Liste —
// dort wird ein Eintrag nicht dupliziert.

function startOfDay(d) {
  const out = new Date(d);
  out.setHours(0, 0, 0, 0);
  return out;
}

function expandEventForGrid(event) {
  const startDay = startOfDay(new Date(event.starts_at));
  const isMultiDayCampaign =
    event.type === "campaign" &&
    event.all_day === true &&
    event.ends_at &&
    !sameDay(new Date(event.starts_at), new Date(event.ends_at));
  if (!isMultiDayCampaign) {
    return [{ event, phase: "single", day: startDay }];
  }
  const endDay = startOfDay(new Date(event.ends_at));
  const out = [];
  const cur = new Date(startDay);
  // Hartes Sicherheitslimit: 366 Iterationen reichen weit über jede
  // realistische Kampagnenlänge — verhindert Endlosschleife bei
  // verbogenen Eingaben.
  for (let i = 0; i < 366 && cur <= endDay; i += 1) {
    let phase;
    if (sameDay(cur, startDay)) phase = "start";
    else if (sameDay(cur, endDay)) phase = "end";
    else phase = "running";
    out.push({ event, phase, day: new Date(cur) });
    cur.setDate(cur.getDate() + 1);
  }
  return out;
}

function expandedEventsForGrid(events) {
  return events.flatMap(expandEventForGrid);
}

function entriesForDay(expandedEntries, day) {
  return expandedEntries.filter((entry) => sameDay(entry.day, day));
}

// ---- Monatsraster -----------------------------------------------------

function buildMonthCells(viewDate) {
  // Liefert ein Array aus 6 × 7 = 42 Date-Objekten, das den Monat
  // im klassischen Mo–So-Raster aufspannt. Erste Spalte = Montag.
  const first = startOfMonth(viewDate);
  // getDay(): 0 = So, 1 = Mo, … 6 = Sa. Verschiebung Mo-zentriert:
  const offset = (first.getDay() + 6) % 7;
  const start = new Date(first);
  start.setDate(first.getDate() - offset);
  const cells = [];
  for (let i = 0; i < 42; i += 1) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    cells.push(d);
  }
  return cells;
}

function monthGridRange(viewDate) {
  // Sichtbarer Rasterbereich (inkl. Randtage des Vor-/Folgemonats),
  // damit die API-Abfrage genau das abdeckt, was im Raster erscheint.
  // Vorher wurde fälschlich nur startOfMonth/endOfMonth verwendet —
  // das führte dazu, dass z. B. ein Meilenstein am 28.04.2026 in der
  // Maiansicht nicht geladen wurde, obwohl er dort als Randtag-Zelle
  // angezeigt würde.
  const cells = buildMonthCells(viewDate);
  return { from: cells[0], to: cells[cells.length - 1] };
}

function renderDayCell(day, viewDate, today, expandedEntries, onMore) {
  const inMonth = day.getMonth() === viewDate.getMonth();
  const isToday = sameDay(day, today);
  const cls = ["calendar-cell"];
  if (!inMonth) cls.push("calendar-cell-other-month");
  if (isToday) cls.push("calendar-cell-today");

  const dayEntries = entriesForDay(expandedEntries, day);
  const visible = dayEntries.slice(0, MAX_CHIPS_PER_DAY);
  const hidden = dayEntries.length - visible.length;
  const moreLink =
    hidden > 0
      ? h(
          "button",
          {
            type: "button",
            class: "calendar-more-link linklike",
            onclick: () => onMore(day),
          },
          `+ ${hidden} weitere`,
        )
      : null;

  return h(
    "div",
    { class: cls.join(" "), "data-date": isoDate(day) },
    h("div", { class: "calendar-day-number" }, String(day.getDate())),
    ...visible.map((entry) => eventChip(entry.event, entry.phase)),
    moreLink,
  );
}

function renderMonthGrid(viewDate, events, today, onMore) {
  // Multi-day-Expansion findet hier statt — die Agenda darunter sieht
  // weiterhin die ungekürzte Event-Liste.
  const expandedEntries = expandedEventsForGrid(events);
  const headerRow = h(
    "div",
    { class: "calendar-grid-head" },
    ...WEEKDAYS_DE.map((name) => h("div", { class: "calendar-weekday" }, name)),
  );
  const cells = buildMonthCells(viewDate).map((day) =>
    renderDayCell(day, viewDate, today, expandedEntries, onMore),
  );
  return h(
    "div",
    { class: "calendar-grid-wrap", role: "grid", "aria-label": "Monatsraster" },
    headerRow,
    h("div", { class: "calendar-grid" }, ...cells),
  );
}

// ---- Agenda-Liste -----------------------------------------------------

function agendaPeriod(event) {
  if (event.all_day) {
    if (event.ends_at && !sameDay(new Date(event.starts_at), new Date(event.ends_at))) {
      return `${formatDateOnly(event.starts_at)} – ${formatDateOnly(event.ends_at)}`;
    }
    return formatDateOnly(event.starts_at);
  }
  if (event.ends_at) {
    return `${formatDateTime(event.starts_at)} – ${formatDateTime(event.ends_at)}`;
  }
  return formatDateTime(event.starts_at);
}

function renderAgendaItem(event) {
  return h(
    "li",
    {
      class: `calendar-agenda-item calendar-event-${event.type}`,
      // ``data-date`` ermöglicht den „+N weitere"-Sprung aus dem Monatsraster.
      "data-date": isoDate(new Date(event.starts_at)),
    },
    h("div", { class: "calendar-agenda-period" }, agendaPeriod(event)),
    h(
      "div",
      { class: "calendar-agenda-body" },
      h("span", { class: "calendar-agenda-type" }, TYPE_LABELS[event.type] || event.type),
      " ",
      h("a", { href: event.link, class: "calendar-agenda-title" }, event.title),
      event.workpackage_codes && event.workpackage_codes.length
        ? h("span", { class: "muted" }, ` · WP: ${event.workpackage_codes.join(", ")}`)
        : null,
      event.status
        ? h(
            "span",
            {
              class: `calendar-agenda-status${
                event.status === "cancelled" ? " calendar-event-cancelled" : ""
              }${event.is_overdue ? " calendar-event-overdue" : ""}`,
            },
            ` · ${event.status}`,
          )
        : null,
      event.description
        ? h("div", { class: "muted calendar-agenda-desc" }, event.description)
        : null,
    ),
  );
}

function renderAgenda(events) {
  if (!events.length) {
    return renderRichEmpty(
      "Keine Termine im gewählten Zeitraum",
      "Der Kalender zeigt Meetings, Testkampagnen, Meilensteine und Aufgaben " +
        "mit Frist. Wechsle den Monat oder passe die Filter an.",
    );
  }
  return h("ul", { class: "calendar-agenda-list" }, ...events.map(renderAgendaItem));
}

// ---- Hauptrender ------------------------------------------------------

function renderTypeLegend() {
  // Sichtbare Typ-Legende über dem Raster — nicht nur Farbe, auch
  // Klartext „Meeting / Kampagne / Meilenstein / Aufgabe".
  return h(
    "div",
    { class: "calendar-legend", role: "group", "aria-label": "Typ-Legende" },
    h("span", { class: "calendar-legend-title" }, "Legende:"),
    ...["meeting", "campaign", "milestone", "action"].map((t) =>
      h(
        "span",
        { class: "calendar-legend-item" },
        h("span", { class: `calendar-legend-swatch calendar-event-${t}` }),
        TYPE_LABELS[t] || t,
      ),
    ),
  );
}

export async function render(container, _ctx) {
  container.classList.add("page-wide");
  const today = new Date();
  let viewDate = startOfMonth(today);
  const typeFilter = h(
    "select",
    {},
    ...TYPE_FILTER_OPTIONS.map((opt) =>
      h("option", { value: opt.value }, opt.label),
    ),
  );
  const wpFilter = h("input", {
    type: "text",
    placeholder: "WP-Code, z. B. WP3.1",
  });
  const mineCheckbox = h("input", { type: "checkbox" });
  const todayBtn = h("button", { type: "button", class: "calendar-nav-today" }, "Heute");
  const prevBtn = h(
    "button",
    {
      type: "button",
      class: "calendar-nav-prev",
      "aria-label": "Vorheriger Monat",
    },
    "← Voriger Monat",
  );
  const nextBtn = h(
    "button",
    {
      type: "button",
      class: "calendar-nav-next",
      "aria-label": "Nächster Monat",
    },
    "Nächster Monat →",
  );
  const monthLabel = h("span", { class: "calendar-month-label" }, "");
  const resetBtn = h(
    "button",
    { type: "button", class: "secondary calendar-filter-reset" },
    "Zurücksetzen",
  );

  const filterBox = h(
    "fieldset",
    { class: "calendar-filterbox filterbox" },
    h("legend", {}, "Kalender filtern"),
    h(
      "label",
      { class: "checkbox-row" },
      mineCheckbox,
      h("span", {}, "Meine Einträge"),
    ),
    h("label", {}, "Typ", typeFilter),
    h("label", {}, "Arbeitspaket", wpFilter),
    resetBtn,
  );

  const navBar = h(
    "div",
    { class: "calendar-nav" },
    prevBtn,
    monthLabel,
    nextBtn,
    todayBtn,
  );

  const calendarSlot = h(
    "div",
    { class: "calendar-grid-slot" },
    renderLoading("Kalender wird geladen …"),
  );
  const agendaSlot = h(
    "section",
    { class: "calendar-agenda-section" },
    h("h2", {}, "Agenda"),
    renderLoading("Termine werden geladen …"),
  );

  function updateMonthLabel() {
    monthLabel.textContent = `${MONTH_NAMES_DE[viewDate.getMonth()]} ${viewDate.getFullYear()}`;
  }

  async function refresh() {
    updateMonthLabel();
    calendarSlot.replaceChildren(renderLoading("Kalender wird geladen …"));
    agendaSlot.replaceChildren(
      h("h2", {}, "Agenda"),
      renderLoading("Termine werden geladen …"),
    );
    // Sichtbarer Rasterbereich (Mo der ersten Zeile bis So der letzten
    // Zeile) — schließt Randtage des Vor-/Folgemonats ein.
    const gridRange = monthGridRange(viewDate);
    const params = new URLSearchParams();
    params.set("from", isoDate(gridRange.from));
    params.set("to", isoDate(gridRange.to));
    if (typeFilter.value) params.set("type", typeFilter.value);
    if (wpFilter.value.trim()) params.set("workpackage", wpFilter.value.trim());
    if (mineCheckbox.checked) params.set("mine", "true");
    let events;
    try {
      events = await api("GET", `/api/calendar/events?${params.toString()}`);
    } catch (err) {
      calendarSlot.replaceChildren(renderError(err));
      agendaSlot.replaceChildren(h("h2", {}, "Agenda"), renderError(err));
      return;
    }

    function onMore(day) {
      // Scrollt zur Agenda-Position dieses Tages — wir markieren den
      // ersten passenden Eintrag kurz, damit klar ist, was „+N weitere"
      // bedeutet.
      const dayIso = isoDate(day);
      const target = agendaSlot.querySelector(`[data-date="${dayIso}"]`);
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        target.classList.add("calendar-agenda-flash");
        setTimeout(() => target.classList.remove("calendar-agenda-flash"), 1400);
      }
    }

    calendarSlot.replaceChildren(renderMonthGrid(viewDate, events, today, onMore));
    agendaSlot.replaceChildren(h("h2", {}, "Agenda"), renderAgenda(events));
  }

  prevBtn.addEventListener("click", () => {
    viewDate = addMonths(viewDate, -1);
    refresh();
  });
  nextBtn.addEventListener("click", () => {
    viewDate = addMonths(viewDate, 1);
    refresh();
  });
  todayBtn.addEventListener("click", () => {
    viewDate = startOfMonth(today);
    refresh();
  });
  typeFilter.addEventListener("change", refresh);
  wpFilter.addEventListener("change", refresh);
  mineCheckbox.addEventListener("change", refresh);
  resetBtn.addEventListener("click", () => {
    typeFilter.value = "";
    wpFilter.value = "";
    mineCheckbox.checked = false;
    refresh();
  });

  appendChildren(
    container,
    h("h1", {}, "Kalender"),
    h(
      "p",
      { class: "muted" },
      "Aggregierte Sicht auf Meetings, Testkampagnen, Meilensteine und " +
        "Aufgaben mit Frist. Bearbeiten erfolgt weiter auf der jeweiligen Detailseite.",
    ),
    navBar,
    filterBox,
    renderTypeLegend(),
    calendarSlot,
    agendaSlot,
    crossNav(),
  );

  await refresh();
}
