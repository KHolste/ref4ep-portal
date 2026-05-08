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
const LABEL_WIDTH_MIN = 180;
const LABEL_WIDTH_MAX = 340;
const LABEL_PADDING = 16; // links/rechts im Label-Bereich
const SUBTRACK_INDENT = 8; // Einrückung von Unter-Arbeitspaketen
// Heuristischer Faktor für die Pixel-Schätzung pro Zeichen. Empirisch
// kalibriert: 0.55 schnitt zu viele Titel ab — 0.60 ist konservativer.
const TEXT_WIDTH_FACTOR = 0.6;
const RIGHT_MARGIN = 20;
const ROW_HEIGHT = 42;
const HEADER_HEIGHT = 48; // Achsen-Skala oben
const MARKER_RADIUS = 7; // Meilenstein-Punkt
const MEETING_RADIUS = 4; // Meeting-Punkt
const BAR_HEIGHT = 14; // Kampagnen-Balken
// Block 0027 — WP-Balken (dünner und blasser als Kampagnen, damit
// visuelle Hierarchie zwischen Plan-Zeitraum und Kampagnen-Zeitraum
// klar bleibt).
const WP_BAR_HEIGHT_SUB = 8;
const WP_BAR_HEIGHT_TOP = 6;
const WP_BAR_FILL_SUB = "#cdd5e0";
const WP_BAR_FILL_TOP = "#9ca7b8";
const FALLBACK_CONTAINER_WIDTH = 1100;
const PX_PER_DAY_MIN = 1;
const PX_PER_DAY_MAX = 28;
const RESIZE_DEBOUNCE_MS = 80;

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

// Deutsche 3-Buchstaben-Monatsabkürzungen für die Achsenbeschriftung.
// Reihenfolge identisch zu Date.getUTCMonth() (0 = Januar).
const MONTH_LABELS_DE = [
  "Jan",
  "Feb",
  "Mär",
  "Apr",
  "Mai",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Okt",
  "Nov",
  "Dez",
];

function shortMonthLabel(d) {
  const yy = String(d.getUTCFullYear() % 100).padStart(2, "0");
  return `${MONTH_LABELS_DE[d.getUTCMonth()]} ${yy}`;
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

// Pixel-Schätzung: konservativer Faktor TEXT_WIDTH_FACTOR pro Zeichen
// reicht für Layout-Entscheidungen (Label-Breite, Ellipsis-Kürzung).
// Exakte DOM-Messung würde jeden Render-Pass kostbare ms aufdrücken.
function estimateTextWidth(text, fontSize) {
  return Math.ceil((text || "").length * fontSize * TEXT_WIDTH_FACTOR);
}

// Schriftgrößen passen sich an die verfügbare Achsenbreite an.
// Heuristik: kleiner Bildschirm (Laptop) → 11/12 px,
// mittlerer (Full-HD)             → 12/13 px,
// großer Monitor                  → 13/14 px.
function chooseFontSizes(axisWidth) {
  if (axisWidth >= 1400) return { axis: 13, track: 14, today: 13 };
  if (axisWidth >= 900) return { axis: 12, track: 13, today: 12 };
  return { axis: 11, track: 12, today: 11 };
}

// Hauptpakete sind Codes ohne Punkt (``WP1``, ``WP3`` …); Unterpakete
// haben einen Sub-Index (``WP1.1``). Die Konsortium-Sammelspur
// (``KONSORTIUM``) enthält ebenfalls keinen Punkt und wird damit als
// Top-Level-Eintrag dargestellt, was fachlich passt.
function isTopLevelTrack(track) {
  return !track.code.includes(".");
}

// Block 0027 — WP-Balken pro Track. Sub-WPs nehmen ihre eigenen
// Datumsfelder; Hauptpakete bekommen ein Aggregat aus den Kindern
// (min(start), max(end)), wenn sie selbst keine eigenen Werte haben.
// Datumsstrings sind ISO-formatiert; lexikografische Sortierung ist
// deshalb äquivalent zur chronologischen.
function computeWpBars(tracks) {
  const childrenByParent = {};
  for (const t of tracks) {
    if (t.parent_code) {
      if (!childrenByParent[t.parent_code]) childrenByParent[t.parent_code] = [];
      childrenByParent[t.parent_code].push(t);
    }
  }
  const bars = {};
  for (const t of tracks) {
    const isTop = isTopLevelTrack(t);
    if (!isTop) {
      bars[t.code] = {
        start: t.start_date || null,
        end: t.end_date || null,
        aggregate: false,
      };
      continue;
    }
    // Top-Level: eigene Werte bevorzugt, sonst aus Kindern aggregieren.
    if (t.start_date && t.end_date) {
      bars[t.code] = { start: t.start_date, end: t.end_date, aggregate: false };
      continue;
    }
    const children = childrenByParent[t.code] || [];
    const childStarts = children.map((c) => c.start_date).filter(Boolean).sort();
    const childEnds = children.map((c) => c.end_date).filter(Boolean).sort();
    bars[t.code] = {
      start: childStarts.length ? childStarts[0] : t.start_date || null,
      end: childEnds.length ? childEnds[childEnds.length - 1] : t.end_date || null,
      aggregate: true,
    };
  }
  return bars;
}

// Berechnet die linke Label-Spalte aus dem längsten Track-Label.
// Hauptpakete sind +1 px größer, deshalb sind sie der Worst Case.
function chooseLabelWidth(tracks, baseFontSize) {
  if (!tracks.length) return LABEL_WIDTH_MIN;
  let widest = 0;
  for (const t of tracks) {
    const text = `${t.code} — ${t.title}`;
    const isTop = isTopLevelTrack(t);
    const fs = isTop ? baseFontSize + 1 : baseFontSize;
    const indent = isTop ? 0 : SUBTRACK_INDENT;
    const w = estimateTextWidth(text, fs) + LABEL_PADDING * 2 + indent;
    if (w > widest) widest = w;
  }
  return Math.max(LABEL_WIDTH_MIN, Math.min(LABEL_WIDTH_MAX, widest));
}

// Kürzt einen Text auf eine Pixelbreite und hängt „…" an, falls nötig.
function fitLabelText(text, maxPx, fontSize) {
  if (estimateTextWidth(text, fontSize) <= maxPx) return text;
  let s = text;
  // Greedy: Zeichen rückwärts kürzen, bis es plus „…" reinpasst.
  while (s.length > 1 && estimateTextWidth(`${s}…`, fontSize) > maxPx) {
    s = s.slice(0, -1);
  }
  return `${s}…`;
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

function renderBoard(board, mode, containerWidth) {
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

  // Schritt 1: Schriftgrößen aus der voraussichtlichen Achsenbreite
  // ableiten (vorläufig: Containerbreite minus Default-Label).
  const provisionalAxis = Math.max(
    300,
    containerWidth - LABEL_WIDTH_MIN - RIGHT_MARGIN,
  );
  const fontSizes = chooseFontSizes(provisionalAxis);

  // Schritt 2: tatsächliche Label-Breite aus dem längsten Track ableiten.
  const labelWidth = chooseLabelWidth(tracks, fontSizes.track);
  const maxLabelTextWidth = labelWidth - LABEL_PADDING * 2;

  // Schritt 3: Pixel pro Tag — Achsenbreite füllt jetzt die echte
  // verfügbare Breite. Min/Max verhindern unbrauchbar dichte/leere
  // Skalen.
  const availableAxis = Math.max(
    300,
    containerWidth - labelWidth - RIGHT_MARGIN,
  );
  const pxPerDay = Math.max(
    PX_PER_DAY_MIN,
    Math.min(PX_PER_DAY_MAX, availableAxis / totalDays),
  );
  const axisWidth = Math.round(totalDays * pxPerDay);
  const totalWidth = labelWidth + axisWidth + RIGHT_MARGIN;
  const totalHeight = HEADER_HEIGHT + tracks.length * ROW_HEIGHT + 20;

  function xOfDate(d) {
    const days = daysBetween(windowStart, d);
    return labelWidth + Math.max(0, Math.min(axisWidth, days * pxPerDay));
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
          "font-size": fontSizes.axis,
          fill: "#555",
        },
        shortMonthLabel(cursor),
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
          "font-size": fontSizes.today,
          fill: "#c62828",
        },
        "heute",
      ),
    );
  }

  // Block 0027 — WP-Balken pro Track vorab berechnen (Aggregat für
  // Hauptpakete aus den Kindern).
  const wpBars = computeWpBars(tracks);

  // Spuren.
  tracks.forEach((track, idx) => {
    const yTop = HEADER_HEIGHT + idx * ROW_HEIGHT;
    const yMid = yTop + ROW_HEIGHT / 2;
    const isTop = isTopLevelTrack(track);

    // Zeilen-Hintergrund.
    // Hauptpakete: einheitlicher heller Akzent (entspricht
    // ``--cockpit-divider`` aus style.css) — visuelle Hierarchie.
    // Unterpakete: alternierend wie bisher.
    let rowFill = null;
    if (isTop) {
      rowFill = "#eef2f7";
    } else if (idx % 2 === 0) {
      rowFill = "#fafafa";
    }
    if (rowFill) {
      root.append(
        svg("rect", {
          x: 0,
          y: yTop,
          width: totalWidth,
          height: ROW_HEIGHT,
          fill: rowFill,
        }),
      );
    }

    // Label links (Code + Titel) mit Ellipsis bei Überlauf, voller Text
    // im Tooltip. Hauptpakete: fett, +1 px Schrift, ohne Einrückung.
    // Unterpakete: normal, eingerückt (``SUBTRACK_INDENT``).
    const fullLabel = `${track.code} — ${track.title}`;
    const labelFontSize = isTop ? fontSizes.track + 1 : fontSizes.track;
    const labelX = LABEL_PADDING / 2 + (isTop ? 0 : SUBTRACK_INDENT);
    const labelMaxPx = maxLabelTextWidth - (isTop ? 0 : SUBTRACK_INDENT);
    const fitted = fitLabelText(fullLabel, labelMaxPx, labelFontSize);
    const labelText = svg(
      "text",
      {
        x: labelX,
        y: yMid + 4,
        class: isTop ? "gantt-track-label gantt-track-top" : "gantt-track-label",
        "font-size": labelFontSize,
        "font-weight": isTop ? "bold" : "normal",
        fill: "#222",
      },
      fitted,
    );
    if (fitted !== fullLabel) {
      labelText.append(svg("title", {}, fullLabel));
    }
    root.append(
      labelText,
      svg("line", {
        x1: labelWidth,
        x2: totalWidth - 10,
        y1: yTop + ROW_HEIGHT - 0.5,
        y2: yTop + ROW_HEIGHT - 0.5,
        stroke: "#eee",
        "stroke-width": 1,
      }),
    );

    // Block 0027 — WP-Balken (vor Kampagnen, damit Kampagnen-Balken
    // optisch oben drauf liegen). Bei fehlenden Datumswerten wird
    // nichts gezeichnet.
    const wpBar = wpBars[track.code];
    if (wpBar && wpBar.start && wpBar.end) {
      const wpStart = parseISODate(wpBar.start);
      const wpEnd = parseISODate(wpBar.end);
      if (wpEnd >= windowStart && wpStart <= windowEnd) {
        const wpX1 = xOfDate(wpStart < windowStart ? windowStart : wpStart);
        const wpX2 = xOfDate(wpEnd > windowEnd ? windowEnd : wpEnd);
        const wpWidth = Math.max(2, wpX2 - wpX1);
        const wpHeight = isTop ? WP_BAR_HEIGHT_TOP : WP_BAR_HEIGHT_SUB;
        const wpFill = isTop ? WP_BAR_FILL_TOP : WP_BAR_FILL_SUB;
        const wpClass = isTop
          ? "gantt-wp-bar gantt-wp-bar-top"
          : "gantt-wp-bar gantt-wp-bar-sub";
        const wpRect = svg("rect", {
          x: wpX1,
          y: yMid - wpHeight / 2,
          width: wpWidth,
          height: wpHeight,
          rx: 2,
          ry: 2,
          fill: wpFill,
          "fill-opacity": 0.85,
          class: wpClass,
        });
        const aggregateNote = wpBar.aggregate ? " (aus Sub-WPs)" : "";
        const tooltip = `${track.code} — ${track.title}\nStart: ${wpBar.start}\nEnde: ${wpBar.end}${aggregateNote}`;
        wpRect.append(svg("title", {}, tooltip));
        root.append(wpRect);
      }
    }

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

  function measureWidth() {
    // boardSlot.clientWidth wird vom Browser nach dem Layout-Pass
    // aktualisiert. Im SPA-Fall ist das beim ersten rerender unmittelbar
    // nach replaceChildren bereits korrekt; falls 0 → Fallback.
    return boardSlot.clientWidth || window.innerWidth - 40 || FALLBACK_CONTAINER_WIDTH;
  }

  function rerender() {
    filterSlot.replaceChildren(
      renderFilterBar(mode, (next) => {
        mode = next;
        rerender();
      }),
    );
    boardSlot.replaceChildren(renderBoard(board, mode, measureWidth()));
  }

  container.replaceChildren(
    pageHeader("Projekt-Timeline", "Gantt-Sicht über Meilensteine, Testkampagnen und Meetings"),
    filterSlot,
    boardSlot,
    legendSlot,
    crossNav(),
  );
  rerender();

  // ResizeObserver re-rendert beim Browserfenster-Resize. Debounce
  // verhindert 60-fps-Flackern beim Drag-Resize. Wenn ``boardSlot`` aus
  // dem DOM entfernt wird (SPA-Wechsel), bekommt der Observer keine
  // weiteren Events — kein expliziter Disconnect nötig.
  if (typeof ResizeObserver !== "undefined") {
    let resizeTimer = null;
    let lastWidth = measureWidth();
    const observer = new ResizeObserver(() => {
      const w = measureWidth();
      if (Math.abs(w - lastWidth) < 8) return; // Mikro-Jitter ignorieren
      lastWidth = w;
      if (resizeTimer) clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        if (boardSlot.isConnected) rerender();
      }, RESIZE_DEBOUNCE_MS);
    });
    observer.observe(boardSlot);
  }
}
