// Testkampagnen — Liste (Block 0022).
//
// Tabellenansicht aller Kampagnen mit Filtern (Status, Kategorie,
// Arbeitspaket-Code, Volltextsuche). Anlegen-Button öffnet einen
// Dialog; sichtbar für jede eingeloggte Person — der Server lehnt ab,
// wenn die Berechtigung fehlt (Admin oder Lead aller WPs).
//
// Wichtig: Kampagnen kennen KEINEN eigenen Datei-Upload. Dokumente
// werden ausschließlich über das Dokumentenregister verlinkt.

import { api, crossNav, h, renderEmpty, renderError, renderLoading } from "/portal/common.js";

const CATEGORY_LABELS = {
  ring_comparison: "Ringvergleich",
  reference_measurement: "Referenzmessung",
  diagnostics_test: "Diagnostiktest",
  calibration: "Kalibrierung",
  facility_characterization: "Facility-Charakterisierung",
  endurance_test: "Langzeittest",
  acceptance_test: "Abnahmetest",
  other: "Sonstiges",
};

const STATUS_LABELS = {
  planned: "geplant",
  preparing: "in Vorbereitung",
  running: "laufend",
  completed: "abgeschlossen",
  evaluated: "ausgewertet",
  cancelled: "abgebrochen",
  postponed: "verschoben",
};

function formatDate(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

function nullIfBlank(value) {
  const v = (value || "").trim();
  return v === "" ? null : v;
}

function statusBadge(status) {
  return h("span", { class: "badge" }, STATUS_LABELS[status] || status);
}

function rowFor(campaign) {
  const wpsCell = campaign.workpackages.length
    ? campaign.workpackages.map((w) => w.code).join(", ")
    : h("span", { class: "muted" }, "—");
  const period = campaign.ends_on
    ? `${formatDate(campaign.starts_on)} – ${formatDate(campaign.ends_on)}`
    : formatDate(campaign.starts_on);
  return h(
    "tr",
    {},
    h("td", {}, period),
    h("td", {}, campaign.code),
    h("td", {}, h("a", { href: `/portal/campaigns/${campaign.id}` }, campaign.title)),
    h("td", {}, CATEGORY_LABELS[campaign.category] || campaign.category),
    h("td", {}, statusBadge(campaign.status)),
    h("td", {}, campaign.facility || h("span", { class: "muted" }, "—")),
    h("td", {}, wpsCell),
    h("td", {}, String(campaign.participants_count)),
    h("td", {}, String(campaign.documents_count)),
  );
}

function renderCreateDialog(workpackages, onSaved, onCancel) {
  const codeInput = h("input", { type: "text", required: true, placeholder: "z. B. TC-2026-001" });
  const titleInput = h("input", { type: "text", required: true });
  const startsOnInput = h("input", { type: "date", required: true });
  const endsOnInput = h("input", { type: "date" });
  const categorySelect = h(
    "select",
    {},
    ...Object.entries(CATEGORY_LABELS).map(([v, l]) =>
      h("option", { value: v, ...(v === "other" ? { selected: "" } : {}) }, l),
    ),
  );
  const statusSelect = h(
    "select",
    {},
    ...Object.entries(STATUS_LABELS).map(([v, l]) =>
      h("option", { value: v, ...(v === "planned" ? { selected: "" } : {}) }, l),
    ),
  );
  const facilityInput = h("input", {
    type: "text",
    placeholder: "z. B. JUMBO-Prüfstand",
  });
  const locationInput = h("input", { type: "text", placeholder: "Ort" });
  const shortDescInput = h("textarea", { rows: "2" });
  const wpSelect = h(
    "select",
    { multiple: "" },
    ...workpackages.map((wp) => h("option", { value: wp.id }, `${wp.code} — ${wp.title}`)),
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
      code: codeInput.value.trim(),
      title: titleInput.value,
      starts_on: startsOnInput.value,
      ends_on: nullIfBlank(endsOnInput.value),
      category: categorySelect.value,
      status: statusSelect.value,
      facility: nullIfBlank(facilityInput.value),
      location: nullIfBlank(locationInput.value),
      short_description: nullIfBlank(shortDescInput.value),
      workpackage_ids: selectedWpIds(),
    };
    try {
      const created = await api("POST", "/api/campaigns", payload);
      onSaved(created);
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    }
  }

  return h(
    "form",
    { class: "stacked", onsubmit: onSubmit },
    h("label", {}, "Code", codeInput),
    h("label", {}, "Titel", titleInput),
    h("label", {}, "Beginn", startsOnInput),
    h("label", {}, "Ende (optional)", endsOnInput),
    h("label", {}, "Kategorie", categorySelect),
    h("label", {}, "Status", statusSelect),
    h("label", {}, "Facility (optional)", facilityInput),
    h("label", {}, "Ort (optional)", locationInput),
    h("label", {}, "Kurzbeschreibung (optional)", shortDescInput),
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

export async function render(container, _ctx) {
  const headerNodes = [
    h("h1", {}, "Testkampagnen"),
    h(
      "p",
      { class: "muted" },
      "Eigene Sicht für experimentelle Durchführungen — Ringvergleiche, " +
        "Referenzmessungen, Facility-Tests, Kalibrierungen und Langzeittests.",
    ),
  ];

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
  const qFilter = h("input", { type: "text", placeholder: "Suche in Code/Titel/Facility" });
  const refreshBtn = h("button", { type: "button" }, "Filtern");
  const filterBar = h(
    "fieldset",
    { class: "campaign-filterbox meeting-filterbox" },
    h("legend", {}, "Testkampagnen filtern"),
    statusFilter,
    categoryFilter,
    wpFilter,
    qFilter,
    refreshBtn,
  );

  const dialogSlot = h("div", {});
  const tableSlot = h("div", {}, renderLoading("Testkampagnen werden geladen …"));
  const createBtn = h("button", { type: "button" }, "Testkampagne anlegen …");

  function clearDialog() {
    dialogSlot.replaceChildren();
  }

  async function refresh() {
    tableSlot.replaceChildren(renderLoading("Testkampagnen werden geladen …"));
    const params = new URLSearchParams();
    if (statusFilter.value) params.set("status", statusFilter.value);
    if (categoryFilter.value) params.set("category", categoryFilter.value);
    if (wpFilter.value.trim()) params.set("workpackage", wpFilter.value.trim());
    if (qFilter.value.trim()) params.set("q", qFilter.value.trim());
    const url = `/api/campaigns${params.toString() ? "?" + params.toString() : ""}`;
    let campaigns;
    try {
      campaigns = await api("GET", url);
    } catch (err) {
      tableSlot.replaceChildren(renderError(err));
      return;
    }
    if (!campaigns.length) {
      tableSlot.replaceChildren(renderEmpty("Keine Testkampagnen gefunden."));
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
          h("th", {}, "Zeitraum"),
          h("th", {}, "Code"),
          h("th", {}, "Titel"),
          h("th", {}, "Kategorie"),
          h("th", {}, "Status"),
          h("th", {}, "Facility"),
          h("th", {}, "Arbeitspakete"),
          h("th", {}, "Personen"),
          h("th", {}, "Dokumente"),
        ),
      ),
      h("tbody", {}, ...campaigns.map(rowFor)),
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
        h("h3", {}, "Testkampagne anlegen"),
        renderCreateDialog(
          workpackages,
          (created) => {
            clearDialog();
            window.location.href = `/portal/campaigns/${created.id}`;
          },
          clearDialog,
        ),
      ),
    );
  }
  createBtn.addEventListener("click", openCreate);

  const headerRow = h("div", { class: "section-header" }, headerNodes[0], createBtn);
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
