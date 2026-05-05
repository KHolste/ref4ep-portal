// Meilensteinübersicht (Block 0009 + UX-Polish).
//
// Vertikale Timeline aller Projekt-Meilensteine — Status, Zeiträume und
// Notizen sind als Karte pro Meilenstein lesbar. Berechtigte (Admin
// oder WP-Lead des MS-Arbeitspakets) bekommen einen Bearbeiten-Dialog.

import {
  api,
  crossNav,
  h,
  renderEmpty,
  renderError,
  renderLoading,
  renderRichEmpty,
} from "/portal/common.js";

const STATUS_LABELS = {
  planned: "geplant",
  achieved: "erreicht",
  postponed: "verschoben",
  at_risk: "gefährdet",
  cancelled: "entfallen",
};

const STATUS_BADGE = {
  planned: "badge-draft",
  achieved: "badge-released",
  postponed: "badge-draft",
  at_risk: "badge-draft",
  cancelled: "badge-draft",
};

function nullIfBlank(value) {
  const v = (value || "").trim();
  return v === "" ? null : v;
}

function formatDate(iso) {
  if (!iso) return null;
  // ``iso`` ist YYYY-MM-DD. Wir wandeln in deutsche Schreibweise.
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

function statusBadge(status) {
  return h(
    "span",
    { class: `badge ${STATUS_BADGE[status] || "badge-draft"}` },
    STATUS_LABELS[status] || status,
  );
}

function renderEditForm(milestone, onSaved, onCancel) {
  const titleInput = h("input", { type: "text", value: milestone.title || "", required: true });
  const plannedInput = h("input", {
    type: "date",
    value: milestone.planned_date || "",
    required: true,
  });
  const actualInput = h("input", { type: "date", value: milestone.actual_date || "" });
  const statusSelect = h(
    "select",
    {},
    ...Object.entries(STATUS_LABELS).map(([value, label]) =>
      h(
        "option",
        { value, ...(milestone.status === value ? { selected: "" } : {}) },
        label,
      ),
    ),
  );
  const noteInput = h("textarea", { rows: "3" }, milestone.note || "");
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    const payload = {
      title: titleInput.value,
      planned_date: plannedInput.value,
      actual_date: nullIfBlank(actualInput.value),
      status: statusSelect.value,
      note: nullIfBlank(noteInput.value),
    };
    try {
      await api("PATCH", `/api/milestones/${milestone.id}`, payload);
      onSaved();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    }
  }

  return h(
    "form",
    { class: "stacked", onsubmit: onSubmit },
    h("label", {}, "Titel", titleInput),
    h("label", {}, "Plandatum", plannedInput),
    h(
      "label",
      {},
      "Istdatum (optional)",
      actualInput,
      h(
        "small",
        { class: "field-hint" },
        "Bei Status „erreicht“ und leerem Istdatum trägt der Server automatisch das heutige Datum ein.",
      ),
    ),
    h("label", {}, "Status", statusSelect),
    h("label", {}, "Notiz", noteInput),
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit" }, "Speichern"),
      h("button", { type: "button", class: "secondary", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

function timelineItem(milestone, onEdit) {
  const wpLink = milestone.workpackage_code
    ? h(
        "a",
        { href: `/portal/workpackages/${milestone.workpackage_code}` },
        `${milestone.workpackage_code} — ${milestone.workpackage_title || ""}`,
      )
    : h("span", { class: "muted" }, "Gesamtprojekt");

  const itemClasses = ["timeline-item"];
  if (milestone.status === "achieved") itemClasses.push("timeline-item-achieved");
  if (milestone.status === "cancelled") itemClasses.push("timeline-item-cancelled");

  const metaLines = [
    h(
      "p",
      { class: "timeline-meta" },
      "Plandatum: ",
      h("strong", {}, formatDate(milestone.planned_date) || "—"),
      milestone.actual_date
        ? h(
            "span",
            {},
            " · Istdatum: ",
            h("strong", {}, formatDate(milestone.actual_date)),
          )
        : null,
    ),
    h("p", { class: "timeline-meta" }, "Arbeitspaket: ", wpLink),
  ];

  return h(
    "li",
    { class: itemClasses.join(" ") },
    h(
      "article",
      { class: "timeline-card" },
      h(
        "div",
        { class: "timeline-head" },
        h(
          "h3",
          { class: "timeline-title" },
          h("span", { class: "timeline-code" }, milestone.code),
          " — ",
          h("span", {}, milestone.title),
        ),
        statusBadge(milestone.status),
      ),
      ...metaLines,
      milestone.note ? h("p", { class: "timeline-note" }, milestone.note) : null,
      milestone.can_edit
        ? h(
            "div",
            { class: "timeline-actions" },
            h(
              "button",
              {
                type: "button",
                class: "button-secondary button-compact",
                onclick: () => onEdit(milestone),
              },
              "Bearbeiten …",
            ),
          )
        : null,
    ),
  );
}

export async function render(container, _ctx) {
  container.classList.add("page-wide");
  const dialogContainer = h("div", {});

  function clearDialog() {
    dialogContainer.replaceChildren();
  }

  function showDialog(title, body) {
    dialogContainer.replaceChildren(h("div", { class: "dialog" }, h("h3", {}, title), body));
  }

  function header() {
    return [
      h("h1", {}, "Meilensteine"),
      h(
        "p",
        { class: "muted" },
        "Projekt-Meilensteine aus dem Antrag. Bearbeiten dürfen Admins und der WP-Lead des Meilenstein-Arbeitspakets; den Gesamtprojekt-Meilenstein nur Admins.",
      ),
    ];
  }

  async function rerender() {
    container.replaceChildren(...header(), renderLoading("Meilensteine werden geladen …"));
    let milestones = [];
    try {
      milestones = await api("GET", "/api/milestones");
    } catch (err) {
      container.replaceChildren(...header(), renderError(err));
      return;
    }

    function onEdit(ms) {
      showDialog(
        `Meilenstein ${ms.code} bearbeiten`,
        renderEditForm(
          ms,
          () => {
            clearDialog();
            rerender();
          },
          clearDialog,
        ),
      );
    }

    // Sortiere Meilensteine nach Plandatum (aufsteigend) — das ergibt
    // einen lesbaren Projektverlauf von links/oben nach unten.
    const sorted = milestones
      .slice()
      .sort((a, b) => (a.planned_date || "").localeCompare(b.planned_date || ""));
    const body = sorted.length
      ? h(
          "ol",
          { class: "timeline" },
          ...sorted.map((ms) => timelineItem(ms, onEdit)),
        )
      : renderRichEmpty(
          "Noch keine Meilensteine angelegt",
          "Meilensteine markieren wichtige Projekttermine. Sie kommen aus dem Antrag und " +
            "werden vom Admin oder vom WP-Lead des zugehörigen Arbeitspakets gepflegt.",
        );

    container.replaceChildren(
      ...header(),
      body,
      dialogContainer,
      crossNav("/portal/milestones"),
    );
  }

  await rerender();
}
