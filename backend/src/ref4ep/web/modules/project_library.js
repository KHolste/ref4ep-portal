// Projektbibliothek (Block 0035).
//
// Zentrale Übersicht über projektbezogene Dokumente. Kachelansicht
// für vorbereitete Bibliotheksbereiche; Klick auf eine Kachel
// filtert die Dokumentliste. Sichtbarkeit kommt aus dem Backend
// (``enforce_visibility=true``); das Modul fügt KEINE eigenen
// Sichtbarkeitsregeln hinzu.
//
// Upload eines Dokuments ohne WP-Bezug steht allen eingeloggten
// Konsortiumsmitgliedern offen; die Versions-Anlage läuft anschließend
// über die Detailseite. Anonyme Aufrufer sehen den Upload-Button nicht.

import {
  api,
  appendChildren,
  createFileDropzone,
  h,
  pageHeader,
  renderError,
  renderLoading,
  renderRichEmpty,
} from "/portal/common.js";

const SECTIONS = [
  {
    key: "project",
    label: "Projektunterlagen",
    description:
      "Anträge, Vereinbarungen, Berichte, Vorlagen und administrative Unterlagen.",
  },
  {
    key: "workpackage",
    label: "Arbeitspaket-Dokumente",
    description: "Dokumente mit Bezug zu Haupt- und Unterarbeitspaketen.",
  },
  {
    key: "milestone",
    label: "Meilenstein-Dokumente",
    description:
      "Nachweise, Präsentationen und Unterlagen zu Projektmeilensteinen.",
    hint:
      "Dokumente mit Bibliotheksbereich Meilenstein. Direkte Verknüpfungen werden in der jeweiligen Meilensteinansicht gepflegt.",
  },
  {
    key: "literature",
    label: "Literatur & Veröffentlichungen",
    description: "Paper, Standards, Reports und projektbezogene Literatur.",
  },
  {
    key: "presentation",
    label: "Vorträge",
    description: "Kick-Offs, Projekttreffen, Reviews und Konferenzbeiträge.",
  },
  {
    key: "thesis",
    label: "Abschlussarbeiten",
    description: "Bachelor-, Master-, Promotions- und Projektarbeiten.",
  },
  // Block 0050 — fachliche Themenfelder der Projektbibliothek.
  {
    key: "technical_documentation",
    label: "Technische Dokumentation",
    description:
      "Zeichnungen, CAD/STEP, Schnittstellen, Geräteunterlagen.",
  },
  {
    key: "measurement_test_campaigns",
    label: "Mess- und Testkampagnen",
    description:
      "Testpläne, Protokolle, Messbedingungen, Facility-Infos.",
  },
  {
    key: "round_robin",
    label: "Ringvergleiche",
    description:
      "Ablauf, Teilnehmerinfos, Datenformate, Vergleichsunterlagen.",
  },
  {
    key: "meetings_minutes",
    label: "Meetings & Protokolle",
    description: "Agenden, Protokolle, Beschlüsse.",
  },
  {
    key: "standards_procedures",
    label: "Standards & Verfahren",
    description:
      "Messvorschriften, Kalibrierverfahren, Auswerteprozeduren.",
  },
  {
    key: "templates_forms",
    label: "Vorlagen & Formulare",
    description:
      "Protokollvorlagen, Datenblattvorlagen, Upload-/Namenskonventionen.",
  },
  {
    key: "software_data_formats",
    label: "Software & Datenformate",
    description:
      "Auswerteskripte, Formatbeschreibungen, Datenstandards.",
  },
];

const SECTION_LABELS = Object.fromEntries(SECTIONS.map((s) => [s.key, s.label]));

const STATUS_LABELS = {
  draft: "Entwurf",
  in_review: "in Review",
  released: "freigegeben",
};

const VISIBILITY_LABELS = {
  workpackage: "Arbeitspaket",
  internal: "intern",
  public: "öffentlich",
};

const DOC_TYPE_LABELS = {
  deliverable: "Deliverable",
  report: "Bericht",
  note: "Notiz",
  paper: "Paper",
  thesis: "Abschlussarbeit",
  presentation: "Präsentation",
  protocol: "Protokoll",
  specification: "Spezifikation",
  template: "Vorlage",
  dataset: "Datensatz",
  other: "sonstig",
};

// Reihenfolge in Dokumenttyp-Dropdowns; identisch zu
// ``document_detail.js::TYPE_OPTIONS``.
const DOC_TYPE_OPTIONS = [
  "other",
  "paper",
  "report",
  "deliverable",
  "presentation",
  "protocol",
  "thesis",
  "specification",
  "template",
  "dataset",
  "note",
];

function formatDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}`;
}

function buildQuery(state) {
  const params = new URLSearchParams();
  params.set("enforce_visibility", "true");
  if (state.section) {
    if (state.section === "workpackage") {
      // Pseudo-Bereich: alle Dokumente mit WP-Bezug.
      // Backend kennt diesen Pseudo-Schlüssel nicht; wir filtern
      // clientseitig, indem wir KEIN ``library_section`` setzen und
      // unten die Liste herausfiltern.
    } else {
      params.set("library_section", state.section);
    }
  }
  if (state.workpackage) params.set("workpackage", state.workpackage);
  if (state.statusFilter) params.set("status_filter", state.statusFilter);
  if (state.q) params.set("q", state.q);
  if (state.withoutWorkpackage) params.set("without_workpackage", "true");
  return `/api/documents?${params.toString()}`;
}

function applyClientSideFilter(state, docs) {
  if (state.section === "workpackage") {
    return docs.filter((d) => d.workpackage_code);
  }
  return docs;
}

function renderTile(section, isActive, onPick) {
  return h(
    "button",
    {
      type: "button",
      class: `library-tile${isActive ? " active" : ""}`,
      "aria-pressed": isActive ? "true" : "false",
      onclick: () => onPick(section.key),
    },
    h("div", { class: "library-tile-title" }, section.label),
    h("div", { class: "library-tile-description muted" }, section.description),
    section.hint ? h("div", { class: "library-tile-hint muted" }, section.hint) : null,
  );
}

function renderTileGrid(activeKey, onPick) {
  const allBtn = h(
    "button",
    {
      type: "button",
      class: `library-tile library-tile-all${activeKey === null ? " active" : ""}`,
      "aria-pressed": activeKey === null ? "true" : "false",
      onclick: () => onPick(null),
    },
    h("div", { class: "library-tile-title" }, "Alle Dokumente"),
    h("div", { class: "library-tile-description muted" }, "Kategoriefilter aufheben."),
  );
  return h(
    "div",
    { class: "library-tile-grid" },
    allBtn,
    ...SECTIONS.map((s) => renderTile(s, s.key === activeKey, onPick)),
  );
}

// Kategorien liegen in einem ein- und ausklappbaren Bereich. Standardmäßig
// zugeklappt: die Ergebnisliste beginnt dadurch auf einem 1440×900-Desktop
// direkt unterhalb von Kopf und Filtern. Der Zustand bleibt über
// ``state.categoriesOpen`` erhalten, die aktive Kategorie steht immer in
// der Zusammenfassung.
function renderCategoryPanel(state, onPick, onToggle) {
  const activeLabel = state.section
    ? SECTION_LABELS[state.section] || state.section
    : "Alle Dokumente";
  const panel = h(
    "details",
    { class: "library-categories" },
    h(
      "summary",
      { class: "library-categories-summary" },
      h("span", { class: "library-categories-label" }, "Kategorie"),
      h("span", { class: "library-categories-active" }, activeLabel),
      h(
        "span",
        { class: "library-categories-hint muted" },
        `${SECTIONS.length} Bereiche zur Auswahl`,
      ),
    ),
    renderTileGrid(state.section, onPick),
  );
  panel.open = state.categoriesOpen;
  panel.addEventListener("toggle", () => onToggle(panel.open));
  return panel;
}

function libBadge(text, tone) {
  return h("span", { class: `library-badge library-badge--${tone}` }, text);
}

// Sortierung läuft rein clientseitig über die bereits geladene Liste —
// keine Backend-Erweiterung nur für die Anzeige.
const SORT_OPTIONS = [
  { key: "updated_desc", label: "Zuletzt aktualisiert" },
  { key: "title_asc", label: "Titel (A–Z)" },
];

function sortDocuments(docs, key) {
  const list = [...docs];
  if (key === "title_asc") {
    list.sort((a, b) => (a.title || "").localeCompare(b.title || "", "de"));
    return list;
  }
  list.sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")));
  return list;
}

// ``data-label`` trägt die Spaltenüberschrift; auf schmalen Bildschirmen
// blendet das Stylesheet den Tabellenkopf aus und zeigt sie stattdessen
// vor dem Wert an — dieselbe DOM-Struktur, Kartenoptik per CSS.
function docCell(label, ...children) {
  return h("td", { class: "library-doc-cell", "data-label": label }, ...children);
}

function renderDocumentRow(doc) {
  const sectionLabel = doc.library_section ? SECTION_LABELS[doc.library_section] : null;
  const statusTone =
    doc.status === "released" ? "ok" : doc.status === "in_review" ? "warn" : "neutral";
  const wpNode = doc.workpackage_code
    ? h(
        "a",
        {
          href: `/portal/workpackages/${doc.workpackage_code}`,
          title: doc.workpackage_title || doc.workpackage_code,
        },
        doc.workpackage_code,
      )
    : h("span", { class: "muted" }, "ohne Arbeitspaketbezug");
  return h(
    "tr",
    { class: "library-doc-row library-doc-card" },
    docCell(
      "Titel",
      h("a", { class: "library-doc-title", href: `/portal/documents/${doc.id}` }, doc.title),
      doc.latest_version_label
        ? h("span", { class: "library-doc-version muted" }, `Version ${doc.latest_version_label}`)
        : null,
    ),
    docCell(
      "Status",
      h(
        "span",
        { class: "library-doc-badges" },
        libBadge(STATUS_LABELS[doc.status] || doc.status, statusTone),
        libBadge(
          VISIBILITY_LABELS[doc.visibility] || doc.visibility,
          doc.visibility === "public" ? "info" : "neutral",
        ),
      ),
    ),
    docCell(
      "Kategorie",
      sectionLabel ? libBadge(sectionLabel, "section") : h("span", { class: "muted" }, "—"),
    ),
    docCell("Typ", DOC_TYPE_LABELS[doc.document_type] || doc.document_type || "—"),
    docCell("Arbeitspaket", wpNode),
    docCell("Aktualisiert", formatDate(doc.updated_at)),
    docCell(
      "Aktion",
      h("a", { class: "library-doc-open", href: `/portal/documents/${doc.id}` }, "Öffnen"),
    ),
  );
}

function renderDocumentTable(docs) {
  return h(
    "table",
    { class: "library-doc-table" },
    h(
      "thead",
      {},
      h(
        "tr",
        {},
        h("th", { scope: "col" }, "Titel"),
        h("th", { scope: "col" }, "Status"),
        h("th", { scope: "col" }, "Kategorie"),
        h("th", { scope: "col" }, "Typ"),
        h("th", { scope: "col" }, "Arbeitspaket"),
        h("th", { scope: "col" }, "Aktualisiert"),
        h("th", { scope: "col" }, "Aktion"),
      ),
    ),
    h("tbody", {}, ...docs.map(renderDocumentRow)),
  );
}

function renderUploadDialog(onSaved, onCancel) {
  // Drag-and-Drop-Upload mit klassischem Pflicht-Dateifeld.
  const fileInput = h("input", { type: "file", required: true });
  const dropzone = createFileDropzone({
    input: fileInput,
    ariaLabel: "Datei für Bibliotheks-Dokument",
  });
  const titleInput = h("input", { type: "text", required: true, minlength: "1" });
  const sectionSelect = h(
    "select",
    {},
    h("option", { value: "" }, "— ohne Bereich —"),
    ...SECTIONS.filter((s) => s.key !== "workpackage").map((s) =>
      h("option", { value: s.key }, s.label),
    ),
  );
  const visibilitySelect = h(
    "select",
    {},
    h("option", { value: "internal" }, "intern"),
    h("option", { value: "public" }, "öffentlich"),
  );
  const typeSelect = h(
    "select",
    {},
    ...DOC_TYPE_OPTIONS.map((t) => h("option", { value: t }, DOC_TYPE_LABELS[t])),
  );
  const noteInput = h("textarea", {
    rows: "2",
    placeholder: "Änderungsnotiz (optional)",
  });
  const descriptionInput = h("textarea", {
    rows: "2",
    placeholder: "Beschreibung (optional)",
  });
  const errorBox = h("p", { class: "error", style: "display:none" }, "");
  const statusBox = h("p", { class: "muted", style: "display:none" }, "Wird hochgeladen …");
  const submitBtn = h("button", { type: "submit" }, "Hochladen");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    if (!fileInput.files.length) {
      errorBox.textContent = "Bitte eine Datei wählen.";
      errorBox.style.display = "";
      return;
    }
    submitBtn.disabled = true;
    statusBox.style.display = "";
    try {
      const created = await api("POST", "/api/library/documents", {
        title: titleInput.value,
        document_type: typeSelect.value,
        description: (descriptionInput.value || "").trim() || null,
        library_section: sectionSelect.value || null,
        visibility: visibilitySelect.value,
      });
      // Anschließend Versions-Upload (multipart, bestehender Endpunkt).
      const formData = new FormData();
      formData.append("file", fileInput.files[0]);
      // Block 0036: leere Notiz weglassen — Server setzt
      // automatisch ``Initialer Upload`` für Erst-Versionen.
      const noteValue = (noteInput.value || "").trim();
      if (noteValue) formData.append("change_note", noteValue);
      const csrf = (document.cookie.match(/(?:^|;\s*)ref4ep_csrf=([^;]+)/) || [])[1];
      const response = await fetch(`/api/documents/${created.id}/versions`, {
        method: "POST",
        body: formData,
        credentials: "same-origin",
        headers: csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : {},
      });
      if (response.status === 401) {
        window.location.href = "/login";
        return;
      }
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        const message = payload?.detail?.error?.message || `HTTP ${response.status}`;
        throw new Error(message);
      }
      onSaved();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    } finally {
      submitBtn.disabled = false;
      statusBox.style.display = "none";
    }
  }

  return h(
    "form",
    { class: "stacked library-upload-form", onsubmit: onSubmit, enctype: "multipart/form-data" },
    h("p", { class: "muted" }, "Hier hochgeladene Dokumente landen ohne Arbeitspaket-Bezug in der Projektbibliothek. Eingeloggte Konsortiumsmitglieder dürfen anlegen und neue Versionen hochladen."),
    h("label", {}, "Datei", dropzone),
    h("label", {}, "Titel", titleInput),
    h("label", {}, "Bibliotheksbereich (optional)", sectionSelect),
    h("label", {}, "Dokumenttyp", typeSelect),
    h("label", {}, "Sichtbarkeit", visibilitySelect),
    h("label", {}, "Änderungsnotiz (optional)", noteInput),
    h("label", {}, "Beschreibung (optional)", descriptionInput),
    statusBox,
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      submitBtn,
      h("button", { type: "button", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

export async function render(container, ctx) {
  container.classList.add("page-wide");
  // Modul-Scope für den Designsystem-Polish (gleiches Niveau wie Cockpit).
  container.classList.add("project-library-page");

  const state = {
    section: null, // null = alle
    workpackage: "",
    statusFilter: "",
    q: "",
    withoutWorkpackage: false,
    sort: "updated_desc",
    categoriesOpen: false,
  };

  // Bibliotheks-Upload steht jedem eingeloggten Konsortiumsmitglied
  // offen; anonyme Aufrufer sehen den Button nicht. Die Backend-Route
  // ``POST /api/library/documents`` setzt dieselbe Schwelle.
  const isLoggedIn = Boolean(ctx?.me?.person);

  // Block 0035-Folgepatch: echtes Modal-Overlay statt Inline-Dialog am
  // Seitenende. ``modalSlot`` lebt fest am Container-Anfang, das Modal
  // wird per Backdrop-Klick oder ESC geschlossen. Der bestehende
  // Inline-``.dialog``-Helper bleibt für andere Module unverändert.
  const modalSlot = h("div", {});
  let modalKeyHandler = null;
  function clearModal() {
    if (modalKeyHandler) {
      document.removeEventListener("keydown", modalKeyHandler);
      modalKeyHandler = null;
    }
    document.body.classList.remove("modal-open");
    modalSlot.replaceChildren();
  }
  function showModal(title, bodyEl) {
    const closeBtn = h(
      "button",
      {
        type: "button",
        class: "library-modal-close",
        "aria-label": "Schließen",
      },
      "×",
    );
    closeBtn.addEventListener("click", clearModal);
    const dialog = h(
      "div",
      {
        class: "library-modal",
        role: "dialog",
        "aria-modal": "true",
        "aria-label": title,
      },
      h(
        "div",
        { class: "library-modal-head" },
        h("h3", { class: "library-modal-title" }, title),
        closeBtn,
      ),
      h("div", { class: "library-modal-body" }, bodyEl),
    );
    const backdrop = h("div", { class: "library-modal-backdrop" }, dialog);
    backdrop.addEventListener("click", (ev) => {
      if (ev.target === backdrop) clearModal();
    });
    modalKeyHandler = (ev) => {
      if (ev.key === "Escape") clearModal();
    };
    document.addEventListener("keydown", modalKeyHandler);
    document.body.classList.add("modal-open");
    modalSlot.replaceChildren(backdrop);
  }
  function onUpload() {
    showModal(
      "Dokument hochladen",
      renderUploadDialog(
        () => {
          clearModal();
          load();
        },
        clearModal,
      ),
    );
  }

  const listSlot = h("div", { class: "library-doc-list" });
  const tileSlot = h("div", {});
  const resultSlot = h("div", { class: "library-result-bar" });

  function pickSection(key) {
    state.section = key;
    load();
  }

  function onCategoriesToggle(open) {
    state.categoriesOpen = open;
  }

  // Aktive Filter als entfernbare Chips — man sieht ohne Blick in die
  // Filterleiste, wonach gerade eingeschränkt wird.
  function activeFilterChips() {
    const chips = [];
    const push = (label, clear) => {
      const btn = h(
        "button",
        {
          type: "button",
          class: "library-filter-chip",
          "aria-label": `Filter entfernen: ${label}`,
        },
        label,
        h("span", { class: "library-filter-chip-x", "aria-hidden": "true" }, "×"),
      );
      btn.addEventListener("click", () => {
        clear();
        syncControls();
        load();
      });
      chips.push(btn);
    };
    if (state.section) {
      push(`Kategorie: ${SECTION_LABELS[state.section] || state.section}`, () => {
        state.section = null;
      });
    }
    if (state.q) push(`Suche: ${state.q}`, () => { state.q = ""; });
    if (state.statusFilter) {
      push(`Status: ${STATUS_LABELS[state.statusFilter] || state.statusFilter}`, () => {
        state.statusFilter = "";
      });
    }
    if (state.workpackage) {
      push(`Arbeitspaket: ${state.workpackage}`, () => { state.workpackage = ""; });
    }
    if (state.withoutWorkpackage) {
      push("Ohne Arbeitspaketbezug", () => { state.withoutWorkpackage = false; });
    }
    return chips;
  }

  function renderResultBar(count) {
    const chips = activeFilterChips();
    const countText = count === 1 ? "1 Dokument" : `${count} Dokumente`;
    return [
      h(
        "p",
        { class: "library-result-count", role: "status" },
        countText,
        chips.length ? " · gefiltert" : "",
      ),
      chips.length ? h("div", { class: "library-active-filters" }, ...chips) : null,
    ].filter(Boolean);
  }

  async function load() {
    listSlot.replaceChildren(renderLoading("Dokumente werden geladen …"));
    let docs = [];
    try {
      docs = await api("GET", buildQuery(state));
    } catch (err) {
      listSlot.replaceChildren(renderError(err));
      resultSlot.replaceChildren();
      return;
    }
    docs = sortDocuments(applyClientSideFilter(state, docs), state.sort);
    resultSlot.replaceChildren(...renderResultBar(docs.length));
    if (!docs.length) {
      listSlot.replaceChildren(
        renderRichEmpty(
          "Keine Dokumente in dieser Auswahl",
          state.section
            ? "Es gibt aktuell keine sichtbaren Dokumente in dieser Kategorie."
            : "Es gibt aktuell keine sichtbaren Dokumente.",
          isLoggedIn ? { label: "Dokument hochladen", onClick: onUpload } : null,
        ),
      );
    } else {
      listSlot.replaceChildren(renderDocumentTable(docs));
    }
    tileSlot.replaceChildren(renderCategoryPanel(state, pickSection, onCategoriesToggle));
  }

  // Filterleiste — die Suche ist das Hauptwerkzeug und steht deshalb
  // zuerst und breit; alles Weitere schließt rechts kompakt an.
  const qInput = h("input", {
    type: "search",
    placeholder: "Titel oder Dokumentcode …",
    value: state.q,
  });
  qInput.addEventListener("input", () => {
    state.q = qInput.value;
  });
  qInput.addEventListener("change", () => {
    state.q = qInput.value;
    load();
  });
  const statusSelect = h(
    "select",
    {},
    h("option", { value: "" }, "Alle Status"),
    h("option", { value: "released" }, "freigegeben"),
    h("option", { value: "in_review" }, "in Review"),
    h("option", { value: "draft" }, "Entwurf"),
  );
  statusSelect.addEventListener("change", () => {
    state.statusFilter = statusSelect.value;
    load();
  });
  const wpInput = h("input", { type: "text", placeholder: "WP-Code (z. B. WP3)" });
  wpInput.addEventListener("change", () => {
    state.workpackage = wpInput.value.trim();
    load();
  });
  const sortSelect = h(
    "select",
    {},
    ...SORT_OPTIONS.map((o) => h("option", { value: o.key }, o.label)),
  );
  sortSelect.addEventListener("change", () => {
    state.sort = sortSelect.value;
    load();
  });
  const withoutWpToggle = h("input", { type: "checkbox" });
  withoutWpToggle.addEventListener("change", () => {
    state.withoutWorkpackage = withoutWpToggle.checked;
    load();
  });
  const resetAllBtn = h(
    "button",
    { type: "button", class: "button-secondary library-filter-reset" },
    "Alle Filter zurücksetzen",
  );

  // Bedienelemente auf den State nachziehen — nötig, wenn ein Filter
  // über einen Chip oder den Zurücksetzen-Button entfernt wurde.
  function syncControls() {
    qInput.value = state.q;
    statusSelect.value = state.statusFilter;
    wpInput.value = state.workpackage;
    sortSelect.value = state.sort;
    withoutWpToggle.checked = state.withoutWorkpackage;
  }

  resetAllBtn.addEventListener("click", () => {
    state.section = null;
    state.q = "";
    state.statusFilter = "";
    state.workpackage = "";
    state.withoutWorkpackage = false;
    syncControls();
    load();
  });

  const filterBar = h(
    "div",
    { class: "library-filter-bar", role: "search" },
    h("label", { class: "library-filter-field library-filter-field--search" }, "Suche", qInput),
    h("label", { class: "library-filter-field" }, "Status", statusSelect),
    h("label", { class: "library-filter-field" }, "Arbeitspaket", wpInput),
    h("label", { class: "library-filter-field" }, "Sortierung", sortSelect),
    h(
      "label",
      { class: "checkbox-row library-filter-toggle" },
      withoutWpToggle,
      h("span", {}, "Nur ohne Arbeitspaketbezug"),
    ),
    resetAllBtn,
  );

  const actionBar = isLoggedIn
    ? h(
        "div",
        { class: "actions" },
        h("button", { type: "button", onclick: onUpload }, "Dokument hochladen"),
      )
    : null;

  appendChildren(
    container,
    // Ruhiger Seitenkopf mit Upload als klare Primäraktion rechts.
    h(
      "header",
      { class: "library-hero" },
      h(
        "div",
        { class: "library-hero-main" },
        pageHeader(
          "Projektbibliothek",
          "Zentrale Übersicht über Projektunterlagen, Arbeitspaket-Dokumente, Literatur, Vorträge und weitere freigegebene Dokumente.",
        ),
      ),
      actionBar,
    ),
    filterBar,
    tileSlot,
    resultSlot,
    listSlot,
    modalSlot,
  );

  // initial render: Kategorien (eingeklappt) + erster Ladevorgang
  syncControls();
  tileSlot.replaceChildren(renderCategoryPanel(state, pickSection, onCategoriesToggle));
  await load();
}
