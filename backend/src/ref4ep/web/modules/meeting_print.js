// Druck-/Protokollansicht eines Meetings (Block 0018).
//
// Kompakte, druckfreundliche Sicht: keine Aktionsbuttons, keine
// Dialog-Elemente. Header und Cross-Nav werden per ``@media print`` in
// style.css ausgeblendet. Der Aufruf erfolgt über
// /portal/meetings/{id}/print — derselbe Auth- und Berechtigungspfad
// wie die normale Detailseite (Server filtert nach can_view).

import { api, h, renderError, renderLoading } from "/portal/common.js";

const FORMAT_LABELS = {
  online: "online",
  in_person: "Präsenz",
  hybrid: "hybrid",
};

const CATEGORY_LABELS = {
  consortium: "Konsortialtreffen",
  jour_fixe: "Jour fixe",
  workpackage: "Arbeitspaket-Treffen",
  technical: "Technisches Abstimmungstreffen",
  review: "Review / Freigabe",
  test_campaign: "Messkampagnenbesprechung",
  other: "Sonstiges",
};

const STATUS_LABELS = {
  planned: "geplant",
  held: "durchgeführt",
  minutes_draft: "Protokoll in Arbeit",
  minutes_approved: "Protokoll abgestimmt",
  completed: "abgeschlossen",
  cancelled: "abgesagt",
};

const DECISION_STATUS_LABELS = {
  open: "offen",
  valid: "gültig",
  replaced: "ersetzt",
  revoked: "aufgehoben",
};

const ACTION_STATUS_LABELS = {
  open: "offen",
  in_progress: "in Arbeit",
  done: "erledigt",
  cancelled: "entfällt",
};

const DOC_LABEL_LABELS = {
  agenda: "Agenda",
  minutes: "Protokoll",
  presentation: "Präsentation",
  decision_template: "Beschlussvorlage",
  attachment: "Anlage",
  other: "Sonstiges",
};

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

function formatDate(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

function renderHeader(meeting) {
  return h(
    "header",
    { class: "meeting-print-header" },
    h("h1", {}, meeting.title),
    h(
      "p",
      { class: "muted" },
      "Termin: ",
      formatDateTime(meeting.starts_at),
      meeting.ends_at ? ` – ${formatDateTime(meeting.ends_at)}` : "",
      " · ",
      `Format: ${FORMAT_LABELS[meeting.format] || meeting.format}`,
      meeting.location ? ` · Ort: ${meeting.location}` : "",
    ),
    h(
      "p",
      { class: "muted" },
      `Kategorie: ${CATEGORY_LABELS[meeting.category] || meeting.category}`,
      " · ",
      `Status: ${STATUS_LABELS[meeting.status] || meeting.status}`,
      " · ",
      "Angelegt von ",
      meeting.created_by ? meeting.created_by.display_name : "—",
    ),
  );
}

function renderWpsBlock(meeting) {
  if (!meeting.workpackages.length) return null;
  const items = meeting.workpackages.map((wp) =>
    h("li", {}, h("strong", {}, wp.code), ` — ${wp.title}`),
  );
  return h("section", {}, h("h2", {}, "Arbeitspakete"), h("ul", {}, ...items));
}

function renderParticipantsBlock(meeting) {
  const items = meeting.participants.map((p) =>
    h("li", {}, `${p.display_name} <${p.email}>`),
  );
  const list = items.length
    ? h("ul", {}, ...items)
    : h("p", { class: "muted" }, "Keine Teilnehmenden eingetragen.");
  return h(
    "section",
    {},
    h("h2", {}, "Teilnehmende"),
    list,
    meeting.extra_participants
      ? h("p", { class: "muted" }, `Zusätzlich: ${meeting.extra_participants}`)
      : null,
  );
}

function renderSummaryBlock(meeting) {
  if (!meeting.summary) return null;
  return h(
    "section",
    {},
    h("h2", {}, "Zusammenfassung"),
    h("p", { class: "preserve-line" }, meeting.summary),
  );
}

function renderDecisionsBlock(meeting) {
  if (!meeting.decisions.length) return null;
  const rows = meeting.decisions.map((d, idx) =>
    h(
      "tr",
      {},
      h("td", {}, String(idx + 1)),
      h("td", { class: "preserve-line" }, d.text),
      h("td", {}, d.workpackage_code || "—"),
      h("td", {}, d.responsible_person?.display_name || "—"),
      h("td", {}, DECISION_STATUS_LABELS[d.status] || d.status),
    ),
  );
  return h(
    "section",
    {},
    h("h2", {}, "Beschlüsse"),
    h(
      "table",
      {},
      h(
        "thead",
        {},
        h(
          "tr",
          {},
          h("th", {}, "#"),
          h("th", {}, "Beschluss"),
          h("th", {}, "WP"),
          h("th", {}, "Verantwortlich"),
          h("th", {}, "Status"),
        ),
      ),
      h("tbody", {}, ...rows),
    ),
  );
}

function renderActionsBlock(meeting) {
  if (!meeting.actions.length) return null;
  const rows = meeting.actions.map((a, idx) =>
    h(
      "tr",
      {},
      h("td", {}, String(idx + 1)),
      h(
        "td",
        { class: "preserve-line" },
        a.text,
        a.note ? h("div", { class: "muted" }, a.note) : null,
      ),
      h("td", {}, a.workpackage_code || "—"),
      h("td", {}, a.responsible_person?.display_name || "—"),
      h("td", {}, formatDate(a.due_date)),
      h("td", {}, ACTION_STATUS_LABELS[a.status] || a.status),
    ),
  );
  return h(
    "section",
    {},
    h("h2", {}, "Aufgaben"),
    h(
      "table",
      {},
      h(
        "thead",
        {},
        h(
          "tr",
          {},
          h("th", {}, "#"),
          h("th", {}, "Aufgabe"),
          h("th", {}, "WP"),
          h("th", {}, "Verantwortlich"),
          h("th", {}, "Frist"),
          h("th", {}, "Status"),
        ),
      ),
      h("tbody", {}, ...rows),
    ),
  );
}

function renderDocumentsBlock(meeting) {
  if (!meeting.documents.length) return null;
  const items = meeting.documents.map((d) =>
    h(
      "li",
      {},
      h("strong", {}, DOC_LABEL_LABELS[d.label] || d.label),
      ": ",
      d.title,
      d.deliverable_code ? ` (${d.deliverable_code})` : "",
    ),
  );
  return h("section", {}, h("h2", {}, "Dokumente"), h("ul", {}, ...items));
}

export async function render(container, ctx) {
  const meetingId = ctx.params.id;
  container.replaceChildren(renderLoading("Protokollansicht wird geladen …"));

  let meeting;
  try {
    meeting = await api("GET", `/api/meetings/${meetingId}`);
  } catch (err) {
    container.replaceChildren(renderError(err));
    return;
  }

  const article = h(
    "article",
    { class: "meeting-print" },
    h(
      "div",
      { class: "meeting-print-toolbar no-print" },
      h(
        "a",
        { href: `/portal/meetings/${meetingId}` },
        "← zurück zur Detailansicht",
      ),
      " · ",
      h(
        "button",
        {
          type: "button",
          class: "linklike",
          onclick: () => window.print(),
        },
        "Drucken …",
      ),
    ),
    renderHeader(meeting),
    renderSummaryBlock(meeting),
    renderWpsBlock(meeting),
    renderParticipantsBlock(meeting),
    renderDecisionsBlock(meeting),
    renderActionsBlock(meeting),
    renderDocumentsBlock(meeting),
  );

  container.replaceChildren(article);
}
