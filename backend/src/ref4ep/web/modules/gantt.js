// Gantt-Timeline (Block 0026).
//
// Reines Lesen — keine Drag-and-Drop-Interaktion, kein Framework.
// SVG wird clientseitig aus den Daten von /api/gantt gerendert.
// Ampel-Farben für Meilenstein-Marker spiegeln die Backend-Funktion
// compute_milestone_traffic_light (siehe services/milestone_health.py).

import {
  api,
  crossNav,
  h,
  pageHeader,
  renderEmpty,
  renderError,
  renderLoading,
} from "/portal/common.js";

const SVG_NS = "http://www.w3.org/2000/svg";

// Layout-Konstanten — Pixel.
const LABEL_WIDTH = 200; // linke Spalte mit WP-Label
const ROW_HEIGHT = 36;
const HEADER_HEIGHT = 48; // Achsen-Skala oben
const MARKER_RADIUS = 7; // Meilenstein-Punkt
const MEETING_RADIUS = 4; // Meeting-Punkt
const BAR_HEIGHT = 14; // Kampagnen-Balken

// Ampel-Farben — bewusst inline, weil das SVG sie als
// presentation-Attribute braucht (CSS-Vererbung im SVG ist tückisch).
const TRAFFIC_FILL = {
  green: "#2e7d32",
  yellow: "#f9a825",
  red: "#c62828",
  gray: "#9e9e9e",
};

const TRAFFIC_LABELS_DE = {
  green: "grün",
  yellow: "gelb",
  red: "rot",
  gray: "neutral",
};

// Filter-Optionen für die Zeitachse.
// "Quartal" und "Jahr" zentrieren um heute, "Gesamt" zeigt das ganze
// Projektfenster.
const RANGE_OPTIONS = [
  { value: "quarter", label: "Quartal" },
  { value: "year", label: "Jahr" },
  { value: "all", label: "Gesamt" },
];

function svg(tag, attrs = {}, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    el.setAttribute(k, String(v));
  }
  for (const c of children) {
    if (c == null) continue;
    el.append(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return el;
}

function parseISODate(s) {
  return new Date(`${s}T00:00:00Z`);
}

function daysBetween(a, b) {
  return Math.round((b.getTime() - a.getTime()) / (1000 * 60 * 60 * 24));
}

function addMonths(d, n) {
  const r = new Date(d);
  r.setUTCMonth(r.getUTCMonth() + n);
  return r;
}

function firstOfMonth(d) {
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1));
}

function isoMonthLabel(d) {
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

// Berechnet das aktuell sichtbare Datumsfenster auf Basis des
// Filter-Modus und des Projektfensters.
function computeVisibleWindow(mode, today, projectStart, projectEnd) {
  if (mode === "all") return [projectStart, projectEnd];
  if (mode === "year") {
    const start = firstOfMonth(addMonths(today, -3));
    const end = firstOfMonth(addMonths(start, 12));
    return [start, end];
  }
  // quarter
  const start = firstOfMonth(addMonths(today, -1));
  const end = firstOfMonth(addMonths(start, 3));
  return [start, end];
}

function renderFilterBar(currentMode, onChange) {
  const bar = h(
    "div",
    { class: "gantt-filter-bar" },
    h("span", { class: "muted" }, "Zeitraum: "),
    ...RANGE_OPTIONS.map((opt) => {
      const btn = h(
        "button",
        {
          type: "button",
          class:
            opt.value === currentMode
              ? "gantt-range-btn gantt-range-btn-active"
              : "gantt-range-btn",
          onclick: () => onChange(opt.value),
        },
        opt.label,
      );
      return btn;
    }),
  );
  return bar;
}

function renderLegend() {
  return h(
    "div",
    { class: "gantt-legend muted" },
    h("strong", {}, "Legende: "),
    "● Meilenstein (Farbe = Ampel) · ▬ Testkampagne · ○ Meeting · gestrichelt = offene Kampagne",
  );
}

function renderBoard(board, mode) {
  const tracks = board.tracks || [];
  if (!tracks.length) {
    return renderEmpty(
      "Keine Daten für die Timeline — sobald Meilensteine, Kampagnen oder Meetings angelegt sind, erscheinen sie hier.",
    );
  }
  const today = parseISODate(board.today);
  const projectStart = parseISODate(board.project_start);
  const projectEnd = parseISODate(board.project_end);
  const [windowStart, windowEnd] = computeVisibleWindow(
    mode,
    today,
    projectStart,
    projectEnd,
  );
  const totalDays = daysBetween(windowStart, windowEnd);
  if (totalDays <= 0) {
    return renderEmpty("Ungültiges Zeitfenster.");
  }

  // Pixel pro Tag — Achsenbreite skaliert mit Dauer, aber min/max
  // halten das Layout brauchbar.
  const pxPerDay = Math.max(1, Math.min(24, 1100 / totalDays));
  const axisWidth = Math.round(totalDays * pxPerDay);
  const totalWidth = LABEL_WIDTH + axisWidth + 20; // 20 = rechter Rand
  const totalHeight = HEADER_HEIGHT + tracks.length * ROW_HEIGHT + 20;

  function xOfDate(d) {
    const days = daysBetween(windowStart, d);
    return LABEL_WIDTH + Math.max(0, Math.min(axisWidth, days * pxPerDay));
  }

  const root = svg("svg", {
    class: "gantt-svg",
    viewBox: `0 0 ${totalWidth} ${totalHeight}`,
    width: totalWidth,
    height: totalHeight,
    role: "img",
    "aria-label": "Projekt-Timeline",
  });

  // Hintergrund + Achse: Monatsmarken.
  let cursor = firstOfMonth(windowStart);
  while (cursor <= windowEnd) {
    const x = xOfDate(cursor);
    root.append(
      svg("line", {
        x1: x,
        x2: x,
        y1: HEADER_HEIGHT - 8,
        y2: totalHeight - 10,
        stroke: "#e0e0e0",
        "stroke-width": 1,
      }),
      svg(
        "text",
        {
          x: x + 2,
          y: HEADER_HEIGHT - 14,
          class: "gantt-axis-label",
          "font-size": 10,
          fill: "#555",
        },
        isoMonthLabel(cursor),
      ),
    );
    cursor = addMonths(cursor, 1);
  }

  // Heute-Linie (vertikal, rot).
  if (today >= windowStart && today <= windowEnd) {
    const xToday = xOfDate(today);
    root.append(
      svg("line", {
        x1: xToday,
        x2: xToday,
        y1: HEADER_HEIGHT - 8,
        y2: totalHeight - 10,
        stroke: "#c62828",
        "stroke-width": 2,
        "stroke-dasharray": "4,3",
      }),
      svg(
        "text",
        {
          x: xToday + 4,
          y: HEADER_HEIGHT - 2,
          class: "gantt-today-label",
          "font-size": 11,
          fill: "#c62828",
        },
        "heute",
      ),
    );
  }

  // Spuren.
  tracks.forEach((track, idx) => {
    const yTop = HEADER_HEIGHT + idx * ROW_HEIGHT;
    const yMid = yTop + ROW_HEIGHT / 2;

    // Zeilen-Hintergrund (alternierend hell).
    if (idx % 2 === 0) {
      root.append(
        svg("rect", {
          x: 0,
          y: yTop,
          width: totalWidth,
          height: ROW_HEIGHT,
          fill: "#fafafa",
        }),
      );
    }

    // Label links (Code + Titel).
    root.append(
      svg(
        "text",
        {
          x: 8,
          y: yMid + 4,
          class: "gantt-track-label",
          "font-size": 12,
          fill: "#222",
        },
        `${track.code} — ${track.title}`,
      ),
      svg("line", {
        x1: LABEL_WIDTH,
        x2: totalWidth - 10,
        y1: yTop + ROW_HEIGHT - 0.5,
        y2: yTop + ROW_HEIGHT - 0.5,
        stroke: "#eee",
        "stroke-width": 1,
      }),
    );

    // Kampagnen-Balken.
    for (const c of track.campaigns) {
      const start = parseISODate(c.starts_on);
      const end = c.ends_on ? parseISODate(c.ends_on) : windowEnd;
      // Komplett außerhalb? Skip.
      if (end < windowStart || start > windowEnd) continue;
      const x1 = xOfDate(start < windowStart ? windowStart : start);
      const x2 = xOfDate(end > windowEnd ? windowEnd : end);
      const width = Math.max(2, x2 - x1);
      const rect = svg("rect", {
        x: x1,
        y: yMid - BAR_HEIGHT / 2,
        width,
        height: BAR_HEIGHT,
        rx: 2,
        ry: 2,
        fill: "#1976d2",
        "fill-opacity": 0.25,
        stroke: "#1976d2",
        "stroke-width": 1,
        "stroke-dasharray": c.ends_on ? null : "5,3",
        class: "gantt-campaign-bar",
      });
      const tooltip = `Kampagne ${c.code} — ${c.title}\n${c.starts_on} – ${
        c.ends_on || "offen"
      }\nStatus: ${c.status}`;
      rect.append(svg("title", {}, tooltip));
      root.append(rect);
    }

    // Meilenstein-Marker (Kreis, Ampel-Farbe).
    for (const ms of track.milestones) {
      const d = parseISODate(ms.planned_date);
      if (d < windowStart || d > windowEnd) continue;
      const cx = xOfDate(d);
      const fill = TRAFFIC_FILL[ms.traffic_light] || TRAFFIC_FILL.gray;
      const circle = svg("circle", {
        cx,
        cy: yMid,
        r: MARKER_RADIUS,
        fill,
        stroke: "#222",
        "stroke-width": 1,
        class: `gantt-milestone gantt-milestone-${ms.traffic_light}`,
      });
      const tooltip = `Meilenstein ${ms.code} — ${ms.title}\nPlandatum: ${
        ms.planned_date
      }\nStatus: ${ms.status} (${TRAFFIC_LABELS_DE[ms.traffic_light]})`;
      circle.append(svg("title", {}, tooltip));
      root.append(circle);
    }

    // Meeting-Marker (kleiner Kreis, hellblau).
    for (const m of track.meetings) {
      const d = parseISODate(m.on_date);
      if (d < windowStart || d > windowEnd) continue;
      const cx = xOfDate(d);
      const c = svg("circle", {
        cx,
        cy: yMid,
        r: MEETING_RADIUS,
        fill: "#90caf9",
        stroke: "#1565c0",
        "stroke-width": 1,
        class: "gantt-meeting",
      });
      c.append(svg("title", {}, `Meeting: ${m.title}\n${m.on_date}\nStatus: ${m.status}`));
      root.append(c);
    }
  });

  // Wrapper für horizontales Scrollen.
  return h(
    "div",
    { class: "gantt-scroll" },
    root,
  );
}

export async function render(container, _ctx) {
  container.replaceChildren(
    pageHeader("Projekt-Timeline", "Gantt-Sicht über Meilensteine, Testkampagnen und Meetings"),
    renderLoading("Timeline wird geladen …"),
  );

  let board;
  try {
    board = await api("GET", "/api/gantt");
  } catch (err) {
    container.replaceChildren(
      pageHeader("Projekt-Timeline"),
      renderError(err),
    );
    return;
  }

  let mode = "year";
  const filterSlot = h("div", {});
  const boardSlot = h("div", {});
  const legendSlot = renderLegend();

  function rerender() {
    filterSlot.replaceChildren(
      renderFilterBar(mode, (next) => {
        mode = next;
        rerender();
      }),
    );
    boardSlot.replaceChildren(renderBoard(board, mode));
  }

  container.replaceChildren(
    pageHeader("Projekt-Timeline", "Gantt-Sicht über Meilensteine, Testkampagnen und Meetings"),
    filterSlot,
    boardSlot,
    legendSlot,
    crossNav(),
  );
  rerender();
}
