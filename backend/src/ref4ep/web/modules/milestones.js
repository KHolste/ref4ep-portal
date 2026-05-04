// Meilensteinübersicht (Block 0009).
//
// Tabelle aller Projekt-Meilensteine. Berechtigte (Admin oder
// WP-Lead des MS-Arbeitspakets) bekommen einen Bearbeiten-Dialog.

import { api, crossNav, h, renderEmpty, renderError, renderLoading } from "/portal/common.js";

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

function rowFor(milestone, onEdit) {
  const wpCell = milestone.workpackage_code
    ? h(
        "a",
        { href: `/portal/workpackages/${milestone.workpackage_code}` },
        `${milestone.workpackage_code} — ${milestone.workpackage_title}`,
      )
    : h("span", { class: "muted" }, "Gesamtprojekt");
  return h(
    "tr",
    {},
    h("td", {}, milestone.code),
    h("td", {}, milestone.title),
    h("td", {}, wpCell),
    h("td", {}, formatDate(milestone.planned_date) || "—"),
    h(
      "td",
      {},
      milestone.actual_date
        ? formatDate(milestone.actual_date)
        : h("span", { class: "muted" }, "—"),
    ),
    h("td", {}, statusBadge(milestone.status)),
    h("td", {}, milestone.note || h("span", { class: "muted" }, "—")),
    h(
      "td",
      {},
      milestone.can_edit
        ? h("button", { type: "button", onclick: () => onEdit(milestone) }, "Bearbeiten …")
        : null,
    ),
  );
}

export async function render(container, _ctx) {
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

    const body = milestones.length
      ? h(
          "table",
          {},
          h(
            "thead",
            {},
            h(
              "tr",
              {},
              h("th", {}, "Code"),
              h("th", {}, "Titel"),
              h("th", {}, "Arbeitspaket"),
              h("th", {}, "Plandatum"),
              h("th", {}, "Istdatum"),
              h("th", {}, "Status"),
              h("th", {}, "Notiz"),
              h("th", {}, ""),
            ),
          ),
          h("tbody", {}, ...milestones.map((ms) => rowFor(ms, onEdit))),
        )
      : renderEmpty("Es sind noch keine Meilensteine angelegt.");

    container.replaceChildren(
      ...header(),
      body,
      dialogContainer,
      crossNav("/portal/milestones"),
    );
  }

  await rerender();
}
