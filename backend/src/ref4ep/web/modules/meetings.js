// Meeting-/Protokollregister — Liste (Block 0015).
//
// Tabellenansicht aller Meetings mit einfachen Filtern (Status,
// Kategorie, Arbeitspaket-Code). Anlegen-Button öffnet einen Dialog;
// sichtbar für jede eingeloggte Person — der Server lehnt ab, wenn
// die Berechtigung fehlt (Admin oder Lead aller gewählten WPs).

import {
  api,
  crossNav,
  h,
  pageHeader,
  renderEmpty,
  renderError,
  renderLoading,
  renderRichEmpty,
} from "/portal/common.js";

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

function formatDate(iso) {
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

function nullIfBlank(value) {
  const v = (value || "").trim();
  return v === "" ? null : v;
}

function renderCreateDialog(workpackages, onSaved, onCancel) {
  const titleInput = h("input", { type: "text", required: true });
  const startsAtInput = h("input", { type: "datetime-local", required: true });
  const endsAtInput = h("input", { type: "datetime-local" });
  const formatSelect = h(
    "select",
    {},
    ...Object.entries(FORMAT_LABELS).map(([v, l]) => h("option", { value: v }, l)),
  );
  const categorySelect = h(
    "select",
    {},
    ...Object.entries(CATEGORY_LABELS).map(([v, l]) =>
      h("option", { value: v, ...(v === "other" ? { selected: "" } : {}) }, l),
    ),
  );
  const locationInput = h("input", {
    type: "text",
    placeholder: "Ort, Raum oder Online-Link",
  });
  const summaryInput = h("textarea", { rows: "3" });
  const extraInput = h("input", {
    type: "text",
    placeholder: "Externe Personen, kommagetrennt",
  });
  const wpSelect = h(
    "select",
    { multiple: "" },
    ...workpackages.map((wp) =>
      h("option", { value: wp.id }, `${wp.code} — ${wp.title}`),
    ),
  );
  const wpHelp = h(
    "small",
    { class: "field-hint" },
    "Mehrfachauswahl möglich. WP-Leads dürfen nur eigene Arbeitspakete auswählen.",
  );
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  function selectedWpIds() {
    return Array.from(wpSelect.selectedOptions).map((opt) => opt.value);
  }

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    const payload = {
      title: titleInput.value,
      starts_at: new Date(startsAtInput.value).toISOString(),
      ends_at: endsAtInput.value ? new Date(endsAtInput.value).toISOString() : null,
      format: formatSelect.value,
      category: categorySelect.value,
      location: nullIfBlank(locationInput.value),
      summary: nullIfBlank(summaryInput.value),
      extra_participants: nullIfBlank(extraInput.value),
      workpackage_ids: selectedWpIds(),
    };
    try {
      const created = await api("POST", "/api/meetings", payload);
      onSaved(created);
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    }
  }

  return h(
    "form",
    { class: "stacked", onsubmit: onSubmit },
    h("label", {}, "Titel", titleInput),
    h("label", {}, "Beginn", startsAtInput),
    h("label", {}, "Ende (optional)", endsAtInput),
    h("label", {}, "Format", formatSelect),
    h("label", {}, "Kategorie", categorySelect),
    h("label", {}, "Ort / Online-Link", locationInput),
    h("label", {}, "Zusammenfassung (optional)", summaryInput),
    h("label", {}, "Zusätzliche Teilnehmende (optional)", extraInput),
    h("label", {}, "Zugehörige Arbeitspakete", wpSelect, wpHelp),
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit" }, "Anlegen"),
      h("button", { type: "button", class: "secondary", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

function statusBadge(status) {
  return h("span", { class: "badge" }, STATUS_LABELS[status] || status);
}

function rowFor(meeting) {
  const wpsCell = meeting.workpackages.length
    ? meeting.workpackages.map((w) => w.code).join(", ")
    : h("span", { class: "muted" }, "—");
  return h(
    "tr",
    {},
    h("td", {}, formatDate(meeting.starts_at)),
    h("td", {}, h("a", { href: `/portal/meetings/${meeting.id}` }, meeting.title)),
    h("td", {}, CATEGORY_LABELS[meeting.category] || meeting.category),
    h("td", {}, FORMAT_LABELS[meeting.format] || meeting.format),
    h("td", {}, statusBadge(meeting.status)),
    h("td", {}, wpsCell),
    h("td", {}, String(meeting.open_actions)),
    h("td", {}, String(meeting.decisions)),
  );
}

export async function render(container, _ctx) {
  container.classList.add("page-wide");
  const headerNodes = [
    pageHeader(
      "Meetings",
      "Strukturierte Ablage für Treffen, Beschlüsse, Aufgaben und Protokoll-Verknüpfungen.",
    ),
  ];

  // Filter-Felder werden später wieder verwendet — wir definieren sie früh,
  // damit der Refresh sie ansprechen kann.
  const statusFilter = h(
    "select",
    {},
    h("option", { value: "" }, "Alle Status"),
    ...Object.entries(STATUS_LABELS).map(([v, l]) => h("option", { value: v }, l)),
  );
  const categoryFilter = h(
    "select",
    {},
    h("option", { value: "" }, "Alle Kategorien"),
    ...Object.entries(CATEGORY_LABELS).map(([v, l]) => h("option", { value: v }, l)),
  );
  const wpFilter = h("input", {
    type: "text",
    placeholder: "WP-Code filtern, z. B. WP3.1",
  });
  const refreshBtn = h("button", { type: "button" }, "Filtern");
  const filterBar = h(
    "fieldset",
    { class: "meeting-filterbox filterbox" },
    h("legend", {}, "Meetings filtern"),
    statusFilter,
    categoryFilter,
    wpFilter,
    refreshBtn,
  );

  const dialogSlot = h("div", {});
  const tableSlot = h("div", {}, renderLoading("Meetings werden geladen …"));
  const createBtn = h("button", { type: "button" }, "Meeting anlegen …");

  function clearDialog() {
    dialogSlot.replaceChildren();
  }

  async function refresh() {
    tableSlot.replaceChildren(renderLoading("Meetings werden geladen …"));
    const params = new URLSearchParams();
    if (statusFilter.value) params.set("status", statusFilter.value);
    if (categoryFilter.value) params.set("category", categoryFilter.value);
    if (wpFilter.value.trim()) params.set("workpackage", wpFilter.value.trim());
    const url = `/api/meetings${params.toString() ? "?" + params.toString() : ""}`;
    let meetings;
    try {
      meetings = await api("GET", url);
    } catch (err) {
      tableSlot.replaceChildren(renderError(err));
      return;
    }
    if (!meetings.length) {
      // Wenn Filter gesetzt sind, ist „nichts gefunden" eine andere
      // Aussage als „noch nichts angelegt".
      const filtersActive =
        statusFilter.value || categoryFilter.value || wpFilter.value.trim();
      if (filtersActive) {
        tableSlot.replaceChildren(
          renderRichEmpty(
            "Keine Meetings für die aktuelle Filterauswahl",
            "Passe Status, Kategorie oder WP-Code an oder setze die Filter zurück.",
          ),
        );
      } else {
        tableSlot.replaceChildren(
          renderRichEmpty(
            "Noch keine Meetings angelegt",
            "Meetings dienen zur Ablage von Protokollen, Beschlüssen und Aufgaben. " +
              "WP-Leads und Admins können hier neue Meetings hinzufügen.",
            { label: "Meeting anlegen …", onClick: openCreate },
          ),
        );
      }
      return;
    }
    const table = h(
      "table",
      {},
      h(
        "thead",
        {},
        h(
          "tr",
          {},
          h("th", {}, "Datum"),
          h("th", {}, "Titel"),
          h("th", {}, "Kategorie"),
          h("th", {}, "Format"),
          h("th", {}, "Status"),
          h("th", {}, "Arbeitspakete"),
          h("th", {}, "Offene Aufgaben"),
          h("th", {}, "Beschlüsse"),
        ),
      ),
      h("tbody", {}, ...meetings.map(rowFor)),
    );
    tableSlot.replaceChildren(table);
  }

  refreshBtn.addEventListener("click", refresh);

  async function openCreate() {
    dialogSlot.replaceChildren(renderLoading("Arbeitspakete werden geladen …"));
    let workpackages;
    try {
      workpackages = await api("GET", "/api/workpackages");
    } catch (err) {
      dialogSlot.replaceChildren(renderError(err));
      return;
    }
    dialogSlot.replaceChildren(
      h(
        "div",
        { class: "dialog" },
        h("h3", {}, "Meeting anlegen"),
        renderCreateDialog(
          workpackages,
          (created) => {
            clearDialog();
            window.location.href = `/portal/meetings/${created.id}`;
          },
          clearDialog,
        ),
      ),
    );
  }
  createBtn.addEventListener("click", openCreate);

  const headerRow = h(
    "div",
    { class: "section-header" },
    headerNodes[0],
    createBtn,
  );

  container.replaceChildren(
    headerRow,
    headerNodes[1],
    filterBar,
    tableSlot,
    dialogSlot,
    crossNav(),
  );

  await refresh();
}
