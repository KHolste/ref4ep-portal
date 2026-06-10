// Testkampagnen — Liste (Block 0022).
//
// Tabellenansicht aller Kampagnen mit Filtern (Status, Kategorie,
// Arbeitspaket-Code, Volltextsuche). Anlegen-Button öffnet einen
// Dialog; sichtbar für jede eingeloggte Person — der Server lehnt ab,
// wenn die Berechtigung fehlt (Admin oder Lead aller WPs).
//
// Wichtig: Kampagnen kennen KEINEN eigenen Datei-Upload. Dokumente
// werden ausschließlich über das Dokumentenregister verlinkt.

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

// Status → ruhiger Farbton (gleiche Logik wie im restlichen
// Designsystem): geplant/aktiv = teal (info), abgeschlossen = grün (ok),
// verschoben = amber (warn), abgebrochen = neutral. Kein grelles Rot.
const STATUS_TONE = {
  planned: "info",
  preparing: "info",
  running: "info",
  completed: "ok",
  evaluated: "ok",
  postponed: "warn",
  cancelled: "neutral",
};

function statusBadge(status) {
  const tone = STATUS_TONE[status] || "neutral";
  return h(
    "span",
    { class: `badge campaign-status-badge campaign-status-badge--${tone}` },
    STATUS_LABELS[status] || status,
  );
}

function metaRow(label, value) {
  return h(
    "div",
    { class: "campaign-meta-row" },
    h("span", { class: "campaign-meta-label" }, label),
    h("span", { class: "campaign-meta-value" }, value || "—"),
  );
}

// Kompakte Stat-Chips aus bereits geladenen Listendaten — keine neue
// fachliche Berechnung, keine zusätzliche API-Abfrage.
function renderCampaignStats(campaigns) {
  const total = campaigns.length;
  const running = campaigns.filter((c) => c.status === "running").length;
  const planned = campaigns.filter(
    (c) => c.status === "planned" || c.status === "preparing",
  ).length;
  const completed = campaigns.filter(
    (c) => c.status === "completed" || c.status === "evaluated",
  ).length;
  const docs = campaigns.reduce((sum, c) => sum + (c.documents_count || 0), 0);
  const stats = [
    { value: total, label: total === 1 ? "Kampagne" : "Kampagnen" },
    { value: running, label: "laufend" },
    { value: planned, label: "geplant" },
    { value: completed, label: "abgeschlossen" },
    { value: docs, label: docs === 1 ? "Dokument" : "Dokumente" },
  ];
  return stats.map((s) =>
    h(
      "span",
      { class: "campaign-stat" },
      h("span", { class: "campaign-stat-value" }, String(s.value)),
      h("span", { class: "campaign-stat-label" }, s.label),
    ),
  );
}

function cardFor(campaign) {
  // Karten-Layout statt enger Tabelle — lange Titel brechen sauber um,
  // breite Bildschirme nutzen den Raum (siehe campaign-card-grid).
  const period = campaign.ends_on
    ? `${formatDate(campaign.starts_on)} – ${formatDate(campaign.ends_on)}`
    : formatDate(campaign.starts_on);
  const wpsValue = campaign.workpackages.length
    ? campaign.workpackages.map((w) => w.code).join(", ")
    : "—";
  return h(
    "article",
    { class: "campaign-card" },
    h(
      "header",
      { class: "campaign-card-head" },
      h("span", { class: "campaign-card-code" }, campaign.code),
      statusBadge(campaign.status),
    ),
    h(
      "h2",
      { class: "campaign-card-title" },
      h("a", { href: `/portal/campaigns/${campaign.id}` }, campaign.title),
    ),
    h(
      "div",
      { class: "campaign-meta" },
      metaRow("Zeitraum", period),
      metaRow("Kategorie", CATEGORY_LABELS[campaign.category] || campaign.category),
      metaRow("Facility", campaign.facility),
      metaRow("Arbeitspakete", wpsValue),
      metaRow("Personen", String(campaign.participants_count)),
      metaRow("Dokumente", String(campaign.documents_count)),
    ),
    h(
      "div",
      { class: "campaign-card-footer" },
      h("a", { href: `/portal/campaigns/${campaign.id}` }, "Details anzeigen →"),
    ),
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
  container.classList.add("page-wide");
  // Modul-Scope für den Designsystem-Polish (gleiche Shell wie
  // Cockpit/Arbeitspakete/Projektbibliothek).
  container.classList.add("campaigns-page");
  const headerNodes = [
    pageHeader(
      "Testkampagnen",
      "Übersicht der Testkampagnen — Ringvergleiche, Referenzmessungen, " +
        "Facility-Tests, Kalibrierungen und Langzeittests.",
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
  const resetBtn = h(
    "button",
    { type: "button", class: "secondary campaign-filter-reset" },
    "Zurücksetzen",
  );
  const filterBar = h(
    "fieldset",
    { class: "campaign-filterbox meeting-filterbox filterbox" },
    h("legend", {}, "Testkampagnen filtern"),
    statusFilter,
    categoryFilter,
    wpFilter,
    qFilter,
    refreshBtn,
    resetBtn,
  );

  const dialogSlot = h("div", {});
  const tableSlot = h("div", {}, renderLoading("Testkampagnen werden geladen …"));
  const createBtn = h("button", { type: "button" }, "Testkampagne anlegen …");
  // Stat-Chips im Kopfband — werden nach jedem Laden gefüllt/geleert.
  const statsSlot = h("div", { class: "campaigns-stats" });

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
      statsSlot.replaceChildren();
      const filtersActive =
        statusFilter.value ||
        categoryFilter.value ||
        wpFilter.value.trim() ||
        qFilter.value.trim();
      const message = filtersActive
        ? "Passe die Filter an oder setze sie zurück."
        : "Testkampagnen bündeln Ringvergleiche, Referenzmessungen und Facility-Tests. " +
          "WP-Leads und Admins können hier neue Testkampagnen anlegen.";
      const action = filtersActive
        ? null
        : { label: "Testkampagne anlegen …", onClick: openCreate };
      tableSlot.replaceChildren(
        renderRichEmpty(
          filtersActive
            ? "Keine Testkampagnen für die aktuelle Filterauswahl"
            : "Noch keine Testkampagnen angelegt",
          message,
          action,
        ),
      );
      return;
    }
    statsSlot.replaceChildren(...renderCampaignStats(campaigns));
    // Karten-Grid statt Tabelle — bessere Lesbarkeit für lange Titel
    // und effizientere Bildschirmbreiten-Nutzung.
    const grid = h(
      "div",
      { class: "campaign-card-grid", role: "list" },
      ...campaigns.map((c) => h("div", { role: "listitem" }, cardFor(c))),
    );
    tableSlot.replaceChildren(grid);
  }
  refreshBtn.addEventListener("click", refresh);
  resetBtn.addEventListener("click", () => {
    statusFilter.value = "";
    categoryFilter.value = "";
    wpFilter.value = "";
    qFilter.value = "";
    refresh();
  });

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

  // Kopfband analog zu Arbeitspakete/Projektbibliothek: links Titel/
  // Unterzeile + Stat-Chips, rechts die Primäraktion „… anlegen".
  // ``headerNodes`` enthält genau EINEN Knoten (pageHeader); ein früherer
  // Verweis auf einen zweiten, nicht existierenden Listeneintrag war
  // ``undefined`` und wurde als sichtbarer Text gerendert — daher hier
  // bewusst nur ``headerNodes[0]``.
  const hero = h(
    "header",
    { class: "campaigns-hero" },
    h("div", { class: "campaigns-hero-main" }, headerNodes[0], statsSlot),
    h("div", { class: "campaigns-hero-actions" }, createBtn),
  );
  container.replaceChildren(hero, filterBar, tableSlot, dialogSlot, crossNav());
  await refresh();
}
