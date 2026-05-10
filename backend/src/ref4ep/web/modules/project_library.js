// Projektbibliothek (Block 0035).
//
// Zentrale Übersicht über projektbezogene Dokumente. Kachelansicht
// für vorbereitete Bibliotheksbereiche; Klick auf eine Kachel
// filtert die Dokumentliste. Sichtbarkeit kommt aus dem Backend
// (``enforce_visibility=true``); das Modul fügt KEINE eigenen
// Sichtbarkeitsregeln hinzu.
//
// Upload eines Dokuments ohne WP-Bezug ist Admins vorbehalten;
// die Versions-Anlage läuft anschließend über die Detailseite.

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
      "Eine eigene Verknüpfung von Dokumenten zu Meilensteinen ist noch nicht umgesetzt; diese Kachel zeigt vorerst Dokumente mit Bibliotheksbereich Meilenstein.",
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
  other: "sonstig",
};

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
      onclick: () => onPick(null),
    },
    h("div", { class: "library-tile-title" }, "Alle Dokumente"),
    h("div", { class: "library-tile-description muted" }, "Filter zurücksetzen."),
  );
  return h(
    "div",
    { class: "library-tile-grid" },
    allBtn,
    ...SECTIONS.map((s) => renderTile(s, s.key === activeKey, onPick)),
  );
}

function renderDocumentCard(doc) {
  const sectionLabel = doc.library_section ? SECTION_LABELS[doc.library_section] : null;
  const wpLabel = doc.workpackage_code
    ? `${doc.workpackage_code}${doc.workpackage_title ? " — " + doc.workpackage_title : ""}`
    : "ohne Arbeitspaketbezug";
  const meta = [
    sectionLabel ? `Bereich: ${sectionLabel}` : null,
    `Typ: ${DOC_TYPE_LABELS[doc.document_type] || doc.document_type || "—"}`,
    `Status: ${STATUS_LABELS[doc.status] || doc.status}`,
    `Sichtbarkeit: ${VISIBILITY_LABELS[doc.visibility] || doc.visibility}`,
  ]
    .filter(Boolean)
    .join(" · ");
  return h(
    "article",
    { class: "library-doc-card" },
    h(
      "a",
      { class: "library-doc-title", href: `/portal/documents/${doc.id}` },
      doc.title,
    ),
    h("div", { class: "library-doc-meta muted" }, meta),
    h("div", { class: "library-doc-meta muted" }, wpLabel),
    h(
      "div",
      { class: "library-doc-meta muted" },
      `Aktualisiert: ${formatDate(doc.updated_at)}`,
    ),
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
    ...["other", "paper", "report", "note"].map((t) =>
      h("option", { value: t }, DOC_TYPE_LABELS[t]),
    ),
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
    h("p", { class: "muted" }, "Hier hochgeladene Dokumente landen ohne Arbeitspaket-Bezug in der Projektbibliothek. Nur Admins."),
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

  const state = {
    section: null, // null = alle
    workpackage: "",
    statusFilter: "",
    q: "",
    withoutWorkpackage: false,
  };

  const isAdmin = ctx?.me?.person?.platform_role === "admin";

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

  function pickSection(key) {
    state.section = key;
    load();
  }

  async function load() {
    listSlot.replaceChildren(renderLoading("Dokumente werden geladen …"));
    let docs = [];
    try {
      docs = await api("GET", buildQuery(state));
    } catch (err) {
      listSlot.replaceChildren(renderError(err));
      return;
    }
    docs = applyClientSideFilter(state, docs);
    if (!docs.length) {
      listSlot.replaceChildren(
        renderRichEmpty(
          "Keine Dokumente in dieser Auswahl",
          state.section
            ? "Es gibt aktuell keine sichtbaren Dokumente in dieser Kachel."
            : "Es gibt aktuell keine sichtbaren Dokumente.",
          isAdmin ? { label: "Dokument hochladen …", onClick: onUpload } : null,
        ),
      );
    } else {
      listSlot.replaceChildren(...docs.map(renderDocumentCard));
    }
    tileSlot.replaceChildren(renderTileGrid(state.section, pickSection));
  }

  // Filterleiste
  const qInput = h("input", {
    type: "search",
    placeholder: "Suche im Titel/Code …",
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
  const withoutWpToggle = h("input", { type: "checkbox" });
  withoutWpToggle.addEventListener("change", () => {
    state.withoutWorkpackage = withoutWpToggle.checked;
    load();
  });

  const filterBar = h(
    "div",
    { class: "library-filter-bar" },
    h("label", {}, "Suche", qInput),
    h("label", {}, "Status", statusSelect),
    h("label", {}, "Arbeitspaket", wpInput),
    h(
      "label",
      { class: "checkbox-row" },
      withoutWpToggle,
      h("span", {}, "nur ohne Arbeitspaketbezug"),
    ),
  );

  const actionBar = isAdmin
    ? h(
        "div",
        { class: "actions" },
        h("button", { type: "button", onclick: onUpload }, "Dokument hochladen …"),
      )
    : null;

  appendChildren(
    container,
    pageHeader(
      "Projektbibliothek",
      "Zentrale Übersicht über Projektunterlagen, Arbeitspaket-Dokumente, Literatur, Vorträge und weitere freigegebene Dokumente.",
    ),
    actionBar,
    tileSlot,
    filterBar,
    listSlot,
    modalSlot,
  );

  // initial render: tiles + first load
  tileSlot.replaceChildren(renderTileGrid(state.section, pickSection));
  await load();
}
