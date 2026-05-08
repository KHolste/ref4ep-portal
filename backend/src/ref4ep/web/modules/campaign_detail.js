// Testkampagnen-Detailseite (Block 0022 + UX-Folgepass).
//
// Aufbau in sieben klar getrennten Sektionen:
//   1. Übersicht           — Code, Kategorie, Status, Zeitraum, Facility
//   2. Fachliche Details   — Ziel, Testmatrix, Messgrößen, Randbedingungen,
//                            Erfolgskriterien, Risiken (mit Empty-State)
//   3. Arbeitspakete       — Liste der WP-Codes
//   4. Fotos (Block 0028)  — Galerie mit Bildunterschrift, Upload für
//                            Teilnehmende und Admin
//   5. Kampagnennotizen    — niedrigschwellige Arbeitsnotizen mit Mini-
//      (Block 0029)         Markdown-Renderer; KEIN Laborbuch
//   6. Beteiligte Personen — Karten pro Person mit Rollen-Pill (deutsch,
//                            kein UPPER-Badge)
//   7. Dokumente           — Karten mit Label, Titel, WP, Entknüpfen-Button
//
// Aktionen erscheinen nur, wenn ``can_edit=true``. Es gibt KEINEN
// Datei-Upload — Dokumente werden ausschließlich über
// /api/documents?include_archived=false ausgewählt und verlinkt.

import {
  api,
  appendChildren,
  crossNav,
  h,
  pageHeader,
  renderEmpty,
  renderError,
  renderLoading,
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

const ROLE_LABELS = {
  campaign_lead: "Kampagnenleitung",
  facility_responsible: "Facility-Verantwortung",
  diagnostics: "Diagnostik",
  data_analysis: "Datenanalyse",
  operation: "Betrieb",
  safety: "Sicherheit",
  observer: "Beobachtung",
  other: "Sonstiges",
};

const DOC_LABEL_LABELS = {
  test_plan: "Messplan",
  setup_plan: "Aufbauplan",
  safety_document: "Sicherheitsunterlage",
  raw_data_description: "Rohdatenbeschreibung",
  protocol: "Protokoll",
  analysis: "Auswertung",
  presentation: "Präsentation",
  attachment: "Anlage",
  other: "Sonstiges",
};

// Reihenfolge bestimmt die UI-Reihenfolge im „Fachliche Details"-Block.
const FACTUAL_FIELDS = [
  ["objective", "Ziel und Zweck"],
  ["test_matrix", "Testmatrix / Betriebspunkte"],
  ["expected_measurements", "Erwartete Messgrößen"],
  ["boundary_conditions", "Randbedingungen"],
  ["success_criteria", "Erfolgskriterien"],
  ["risks_or_open_points", "Risiken / offene Punkte"],
];

function nullIfBlank(value) {
  const v = (value || "").trim();
  return v === "" ? null : v;
}

function formatDate(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

function statusBadge(status) {
  return h("span", { class: "badge" }, STATUS_LABELS[status] || status);
}

function rolePill(role) {
  // Deutsche Anzeige, gemischte Schreibweise (kein UPPER wie .badge).
  return h(
    "span",
    { class: "campaign-role" },
    ROLE_LABELS[role] || role,
  );
}

function docLabelPill(label) {
  return h("span", { class: "campaign-doc-label" }, DOC_LABEL_LABELS[label] || label);
}

function periodText(campaign) {
  return campaign.ends_on
    ? `${formatDate(campaign.starts_on)} – ${formatDate(campaign.ends_on)}`
    : formatDate(campaign.starts_on);
}

// ---- Edit-Formular für die Stammdaten ----------------------------------

function renderEditDialog(campaign, workpackages, onSaved, onCancel) {
  const codeInput = h("input", { type: "text", value: campaign.code, required: true });
  const titleInput = h("input", { type: "text", value: campaign.title, required: true });
  const startsOnInput = h("input", { type: "date", value: campaign.starts_on, required: true });
  const endsOnInput = h("input", { type: "date", value: campaign.ends_on || "" });
  const categorySelect = h(
    "select",
    {},
    ...Object.entries(CATEGORY_LABELS).map(([v, l]) =>
      h("option", { value: v, ...(campaign.category === v ? { selected: "" } : {}) }, l),
    ),
  );
  const statusSelect = h(
    "select",
    {},
    ...Object.entries(STATUS_LABELS).map(([v, l]) =>
      h("option", { value: v, ...(campaign.status === v ? { selected: "" } : {}) }, l),
    ),
  );
  const facilityInput = h("input", { type: "text", value: campaign.facility || "" });
  const locationInput = h("input", { type: "text", value: campaign.location || "" });
  const shortDescInput = h("textarea", { rows: "2" }, campaign.short_description || "");
  const objectiveInput = h("textarea", { rows: "3" }, campaign.objective || "");
  const matrixInput = h("textarea", { rows: "4" }, campaign.test_matrix || "");
  const measurementsInput = h(
    "textarea",
    { rows: "3" },
    campaign.expected_measurements || "",
  );
  const boundaryInput = h(
    "textarea",
    { rows: "3" },
    campaign.boundary_conditions || "",
  );
  const successInput = h("textarea", { rows: "3" }, campaign.success_criteria || "");
  const risksInput = h("textarea", { rows: "3" }, campaign.risks_or_open_points || "");
  const wpCodes = new Set(campaign.workpackages.map((w) => w.code));
  const wpSelect = h(
    "select",
    { multiple: "" },
    ...workpackages.map((wp) =>
      h(
        "option",
        { value: wp.id, ...(wpCodes.has(wp.code) ? { selected: "" } : {}) },
        `${wp.code} — ${wp.title}`,
      ),
    ),
  );
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  function selectedWpIds() {
    return Array.from(wpSelect.selectedOptions).map((opt) => opt.value);
  }

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    const payload = {
      code: codeInput.value,
      title: titleInput.value,
      starts_on: startsOnInput.value,
      ends_on: nullIfBlank(endsOnInput.value),
      category: categorySelect.value,
      status: statusSelect.value,
      facility: nullIfBlank(facilityInput.value),
      location: nullIfBlank(locationInput.value),
      short_description: nullIfBlank(shortDescInput.value),
      objective: nullIfBlank(objectiveInput.value),
      test_matrix: nullIfBlank(matrixInput.value),
      expected_measurements: nullIfBlank(measurementsInput.value),
      boundary_conditions: nullIfBlank(boundaryInput.value),
      success_criteria: nullIfBlank(successInput.value),
      risks_or_open_points: nullIfBlank(risksInput.value),
      workpackage_ids: selectedWpIds(),
    };
    try {
      await api("PATCH", `/api/campaigns/${campaign.id}`, payload);
      onSaved();
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
    h("label", {}, "Facility", facilityInput),
    h("label", {}, "Ort", locationInput),
    h("label", {}, "Kurzbeschreibung", shortDescInput),
    h("label", {}, "Ziel und Zweck", objectiveInput),
    h("label", {}, "Testmatrix / Betriebspunkte", matrixInput),
    h("label", {}, "Erwartete Messgrößen", measurementsInput),
    h("label", {}, "Randbedingungen", boundaryInput),
    h("label", {}, "Erfolgskriterien", successInput),
    h("label", {}, "Risiken / offene Punkte", risksInput),
    h(
      "label",
      {},
      "Zugehörige Arbeitspakete",
      wpSelect,
      h(
        "small",
        { class: "field-hint" },
        "Mehrfachauswahl möglich. WP-Leads dürfen nur eigene Arbeitspakete auswählen.",
      ),
    ),
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit" }, "Speichern"),
      h("button", { type: "button", class: "secondary", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

// ---- Beteiligte Personen ----------------------------------------------

function renderParticipantAddForm(campaignId, persons, alreadyIds, onSaved, onCancel) {
  const candidates = persons.filter((p) => !alreadyIds.has(p.id));
  if (!candidates.length) {
    return h(
      "div",
      {},
      renderEmpty("Alle Personen aus dem Portal sind bereits eingetragen."),
      h(
        "div",
        { class: "form-actions" },
        h("button", { type: "button", class: "secondary", onclick: onCancel }, "Schließen"),
      ),
    );
  }
  const personSelect = h(
    "select",
    {},
    ...candidates.map((p) => h("option", { value: p.id }, `${p.display_name} <${p.email}>`)),
  );
  const roleSelect = h(
    "select",
    {},
    ...Object.entries(ROLE_LABELS).map(([v, l]) =>
      h("option", { value: v, ...(v === "other" ? { selected: "" } : {}) }, l),
    ),
  );
  const noteInput = h("input", { type: "text", placeholder: "Optionale Notiz" });
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    try {
      await api("POST", `/api/campaigns/${campaignId}/participants`, {
        person_id: personSelect.value,
        role: roleSelect.value,
        note: nullIfBlank(noteInput.value),
      });
      onSaved();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    }
  }

  return h(
    "form",
    { class: "stacked", onsubmit: onSubmit },
    h("label", {}, "Person", personSelect),
    h("label", {}, "Rolle", roleSelect),
    h("label", {}, "Notiz (optional)", noteInput),
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit" }, "Hinzufügen"),
      h("button", { type: "button", class: "secondary", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

function renderParticipantEditForm(participant, onSaved, onCancel) {
  const roleSelect = h(
    "select",
    {},
    ...Object.entries(ROLE_LABELS).map(([v, l]) =>
      h("option", { value: v, ...(participant.role === v ? { selected: "" } : {}) }, l),
    ),
  );
  const noteInput = h("input", { type: "text", value: participant.note || "" });
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    try {
      await api("PATCH", `/api/campaign-participants/${participant.id}`, {
        role: roleSelect.value,
        note: nullIfBlank(noteInput.value),
      });
      onSaved();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    }
  }

  return h(
    "form",
    { class: "stacked", onsubmit: onSubmit },
    h("p", {}, `${participant.person.display_name} <${participant.person.email}>`),
    h("label", {}, "Rolle", roleSelect),
    h("label", {}, "Notiz (optional)", noteInput),
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit" }, "Speichern"),
      h("button", { type: "button", class: "secondary", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

// ---- Dokumentverknüpfung (kein Upload) --------------------------------

function renderDocumentLinkForm(campaignId, documents, alreadyIds, onSaved, onCancel) {
  const candidates = documents.filter((d) => !alreadyIds.has(d.id));
  if (!candidates.length) {
    return h(
      "div",
      {},
      renderEmpty("Alle Dokumente sind bereits verknüpft."),
      h(
        "div",
        { class: "form-actions" },
        h("button", { type: "button", class: "secondary", onclick: onCancel }, "Schließen"),
      ),
    );
  }
  const docSelect = h(
    "select",
    {},
    ...candidates.map((d) => {
      const code = d.code ?? d.deliverable_code;
      const wpPart = d.workpackage_code ? `${d.workpackage_code} · ` : "";
      const codePart = code ? `[${code}] ` : "";
      return h("option", { value: d.id }, `${wpPart}${codePart}${d.title}`);
    }),
  );
  const labelSelect = h(
    "select",
    {},
    ...Object.entries(DOC_LABEL_LABELS).map(([v, l]) =>
      h("option", { value: v, ...(v === "test_plan" ? { selected: "" } : {}) }, l),
    ),
  );
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    try {
      await api("POST", `/api/campaigns/${campaignId}/documents`, {
        document_id: docSelect.value,
        label: labelSelect.value,
      });
      onSaved();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    }
  }

  return h(
    "form",
    { class: "stacked", onsubmit: onSubmit },
    h("label", {}, "Dokument", docSelect),
    h("label", {}, "Rolle des Dokuments", labelSelect),
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit" }, "Verknüpfen"),
      h("button", { type: "button", class: "secondary", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

// ---- Render-Sektionen --------------------------------------------------

function renderHeader(campaign) {
  return h(
    "header",
    { class: "campaign-detail-head" },
    h("h1", {}, campaign.title, " ", statusBadge(campaign.status)),
    h(
      "p",
      { class: "muted" },
      `Code: ${campaign.code} · Kategorie: ${
        CATEGORY_LABELS[campaign.category] || campaign.category
      } · ${periodText(campaign)}`,
    ),
    campaign.short_description
      ? h("p", { class: "preserve-line" }, campaign.short_description)
      : null,
  );
}

function kvRow(label, value) {
  return h(
    "div",
    { class: "campaign-kv-row" },
    h("span", { class: "campaign-kv-label" }, label),
    h("span", { class: "campaign-kv-value" }, value || "—"),
  );
}

function renderOverviewCard(campaign) {
  return h(
    "section",
    { class: "campaign-section campaign-overview" },
    h("h2", {}, "Übersicht"),
    h(
      "div",
      { class: "campaign-kv-grid" },
      kvRow("Code", campaign.code),
      kvRow("Kategorie", CATEGORY_LABELS[campaign.category] || campaign.category),
      kvRow("Status", STATUS_LABELS[campaign.status] || campaign.status),
      kvRow("Zeitraum", periodText(campaign)),
      kvRow("Facility", campaign.facility),
      kvRow("Ort", campaign.location),
      kvRow(
        "Angelegt von",
        campaign.created_by ? campaign.created_by.display_name : "—",
      ),
    ),
  );
}

function renderFactualSection(title, value) {
  // Wird nur aufgerufen, wenn ``value`` gefüllt ist — der Caller
  // garantiert das. Damit kann hier kein „null" durchrutschen.
  return h(
    "article",
    { class: "campaign-fact-card" },
    h("h3", {}, title),
    h("p", { class: "preserve-line" }, value),
  );
}

function renderFactualBlock(campaign) {
  const populated = FACTUAL_FIELDS.filter(([key]) => {
    const v = campaign[key];
    return typeof v === "string" && v.trim() !== "";
  });
  if (!populated.length) {
    return h(
      "section",
      { class: "campaign-section" },
      h("h2", {}, "Fachliche Details"),
      renderEmpty("Noch keine fachlichen Details hinterlegt."),
    );
  }
  return h(
    "section",
    { class: "campaign-section" },
    h("h2", {}, "Fachliche Details"),
    h(
      "div",
      { class: "campaign-fact-grid" },
      ...populated.map(([key, label]) => renderFactualSection(label, campaign[key])),
    ),
  );
}

function renderWpsBlock(campaign) {
  if (!campaign.workpackages.length) {
    return h(
      "section",
      { class: "campaign-section" },
      h("h2", {}, "Arbeitspakete"),
      renderEmpty("Kein Arbeitspaket-Bezug — übergreifende Kampagne (Admin-only)."),
    );
  }
  return h(
    "section",
    { class: "campaign-section" },
    h("h2", {}, "Arbeitspakete"),
    h(
      "ul",
      { class: "campaign-wp-list" },
      ...campaign.workpackages.map((wp) =>
        h(
          "li",
          {},
          h("a", { href: `/portal/workpackages/${wp.code}` }, wp.code),
          ` — ${wp.title}`,
        ),
      ),
    ),
  );
}

function renderParticipantCard(participant, canEdit, onEdit, onRemove) {
  return h(
    "article",
    { class: "campaign-participant-card" },
    h(
      "div",
      { class: "campaign-participant-head" },
      h("div", { class: "campaign-participant-name" }, participant.person.display_name),
      rolePill(participant.role),
    ),
    h("div", { class: "campaign-participant-email muted" }, participant.person.email),
    participant.note
      ? h("div", { class: "campaign-participant-note preserve-line" }, participant.note)
      : null,
    canEdit
      ? h(
          "div",
          { class: "form-actions" },
          h("button", { type: "button", onclick: () => onEdit(participant) }, "Bearbeiten …"),
          h(
            "button",
            { type: "button", class: "linklike danger", onclick: () => onRemove(participant) },
            "entfernen",
          ),
        )
      : null,
  );
}

function renderParticipantsBlock(campaign, canEdit, onAdd, onEdit, onRemove) {
  const heading = h(
    "div",
    { class: "section-header" },
    h("h2", {}, "Beteiligte Personen"),
    canEdit ? h("button", { type: "button", onclick: onAdd }, "Person hinzufügen …") : null,
  );
  if (!campaign.participants.length) {
    return h(
      "section",
      { class: "campaign-section" },
      heading,
      renderEmpty("Noch keine Personen eingetragen."),
    );
  }
  return h(
    "section",
    { class: "campaign-section" },
    heading,
    h(
      "div",
      { class: "campaign-participant-grid" },
      ...campaign.participants.map((p) =>
        renderParticipantCard(p, canEdit, onEdit, onRemove),
      ),
    ),
  );
}

function renderDocumentCard(doc, canEdit, onUnlink) {
  return h(
    "article",
    { class: "campaign-document-card" },
    h(
      "div",
      { class: "campaign-document-head" },
      docLabelPill(doc.label),
      h(
        "a",
        { class: "campaign-document-title", href: `/portal/documents/${doc.document_id}` },
        doc.title,
      ),
    ),
    h(
      "div",
      { class: "campaign-document-meta muted" },
      doc.workpackage_code ? `WP: ${doc.workpackage_code}` : "WP: —",
      doc.deliverable_code ? ` · Code: ${doc.deliverable_code}` : "",
    ),
    canEdit
      ? h(
          "div",
          { class: "form-actions" },
          h(
            "button",
            { type: "button", class: "linklike danger", onclick: () => onUnlink(doc) },
            "entknüpfen",
          ),
        )
      : null,
  );
}

// ---- Block 0028 — Fotos -----------------------------------------------

function formatDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const yyyy = d.getFullYear();
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${dd}.${mm}.${yyyy} ${hh}:${mi}`;
}

function formatBytes(n) {
  if (!Number.isFinite(n) || n <= 0) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KiB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MiB`;
}

function renderPhotoUploadDialog(campaignId, onSuccess, onCancel) {
  const fileInput = h("input", {
    type: "file",
    accept: "image/png,image/jpeg",
    required: true,
  });
  const captionInput = h("textarea", {
    rows: "2",
    placeholder: "Bildunterschrift (optional)",
  });
  const takenAtInput = h("input", { type: "datetime-local" });
  const errorBox = h("p", { class: "error", style: "display:none" }, "");
  const statusBox = h("p", { class: "muted", style: "display:none" }, "Lade hoch …");
  const submitBtn = h("button", { type: "submit" }, "Hochladen");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    if (!fileInput.files.length) {
      errorBox.textContent = "Bitte eine Bilddatei wählen.";
      errorBox.style.display = "";
      return;
    }
    submitBtn.disabled = true;
    statusBox.style.display = "";
    try {
      const formData = new FormData();
      formData.append("file", fileInput.files[0]);
      const cap = (captionInput.value || "").trim();
      if (cap) formData.append("caption", cap);
      if (takenAtInput.value) formData.append("taken_at", takenAtInput.value);

      const csrf = (document.cookie.match(/(?:^|;\s*)ref4ep_csrf=([^;]+)/) || [])[1];
      const response = await fetch(`/api/campaigns/${campaignId}/photos`, {
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
      onSuccess(payload);
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
    { class: "stacked", onsubmit: onSubmit, enctype: "multipart/form-data" },
    h("p", { class: "muted" }, "Erlaubt: PNG oder JPEG. Keine Thumbnails, keine EXIF-Auswertung."),
    h("label", {}, "Bilddatei", fileInput),
    h("label", {}, "Bildunterschrift", captionInput),
    h("label", {}, "Aufnahmezeitpunkt (optional)", takenAtInput),
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

function renderPhotoCaptionEditDialog(campaignId, photo, onSaved, onCancel) {
  const captionInput = h(
    "textarea",
    { rows: "3", placeholder: "Bildunterschrift" },
    photo.caption || "",
  );
  const errorBox = h("p", { class: "error", style: "display:none" }, "");
  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    try {
      await api(
        "PATCH",
        `/api/campaigns/${campaignId}/photos/${photo.id}`,
        { caption: nullIfBlank(captionInput.value) },
      );
      onSaved();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    }
  }
  return h(
    "form",
    { class: "stacked", onsubmit: onSubmit },
    h("label", {}, "Bildunterschrift", captionInput),
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit" }, "Speichern"),
      h("button", { type: "button", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

function renderPhotoCard(campaignId, photo, onEditCaption, onDelete) {
  const meta = [
    `${photo.uploaded_by.display_name}`,
    formatDateTime(photo.taken_at || photo.created_at),
    formatBytes(photo.file_size_bytes),
  ].join(" · ");
  const actions = [];
  if (photo.can_edit) {
    actions.push(
      h(
        "button",
        { type: "button", class: "linklike", onclick: () => onEditCaption(photo) },
        "Bildunterschrift bearbeiten …",
      ),
      h(
        "button",
        { type: "button", class: "linklike danger", onclick: () => onDelete(photo) },
        "löschen",
      ),
    );
  }
  return h(
    "article",
    { class: "campaign-photo-card" },
    h(
      "a",
      {
        class: "campaign-photo-image-link",
        href: `/api/campaigns/${campaignId}/photos/${photo.id}/download`,
        target: "_blank",
        rel: "noopener",
      },
      h("img", {
        class: "campaign-photo-image",
        // Block 0032 — Galerie nutzt Thumbnail-Endpoint; bei
        // Bestandsfotos ohne Thumbnail liefert der Server einen
        // Fallback auf das Original.
        src: `/api/campaigns/${campaignId}/photos/${photo.id}/thumbnail`,
        alt: photo.caption || photo.original_filename,
        loading: "lazy",
        decoding: "async",
      }),
    ),
    photo.caption
      ? h("div", { class: "campaign-photo-caption preserve-line" }, photo.caption)
      : null,
    h("div", { class: "campaign-photo-meta muted" }, meta),
    actions.length ? h("div", { class: "form-actions" }, ...actions) : null,
  );
}

function renderPhotosBlock(campaign, photos, onUpload, onEditCaption, onDelete) {
  const heading = h(
    "div",
    { class: "section-header" },
    h("h2", {}, "Fotos"),
    campaign.can_upload_photo
      ? h("button", { type: "button", onclick: onUpload }, "Foto hochladen …")
      : null,
  );
  if (!photos.length) {
    return h(
      "section",
      { class: "campaign-section" },
      heading,
      renderEmpty("Noch keine Fotos zur Kampagne hochgeladen."),
    );
  }
  return h(
    "section",
    { class: "campaign-section" },
    heading,
    h(
      "div",
      { class: "campaign-photo-grid" },
      ...photos.map((p) => renderPhotoCard(campaign.id, p, onEditCaption, onDelete)),
    ),
  );
}

// ---- Block 0029 — Kampagnennotizen + Mini-Markdown ---------------------

// Reine Vanilla-JS-Implementierung. Kein npm, keine externe Library.
// Reihenfolge: HTML escapen → Inline-Code als Platzhalter ausschneiden →
// Block-Strukturen erkennen (Heading, Liste, Tabelle, Blockquote,
// Absatz) → Inline-Formatierung (fett, kursiv) anwenden →
// Inline-Code-Platzhalter zurückspielen.
//
// `photo:<id>`-Einbindung ist NICHT Teil dieses Patches; entsprechende
// Token bleiben als literaler Text stehen.

function escapeHtml(text) {
  // Unicode-Escapes fuer die Quotes — sonst haelt der Asset-Heuristik-
  // Test die rohen Anfuehrungszeichen in den Regex-Literalen faelschlich
  // fuer einen String-Start.
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\u0022/g, "&quot;")
    .replace(/\u0027/g, "&#39;");
}

function renderInline(text) {
  // Inline-Code zwischenspeichern, damit fett/kursiv im Code-Body
  // nicht greift.
  const codes = [];
  let safe = text.replace(/\u0060([^\u0060]+?)\u0060/g, (_, code) => {
    codes.push(code);
    return " CODE" + (codes.length - 1) + " ";
  });
  // Fett vor Kursiv, sonst frisst Kursiv die Sterne.
  safe = safe.replace(/\*\*([^*\n]+?)\*\*/g, "<strong>$1</strong>");
  safe = safe.replace(/__([^_\n]+?)__/g, "<strong>$1</strong>");
  safe = safe.replace(/(^|[^*])\*([^*\n]+?)\*(?!\*)/g, "$1<em>$2</em>");
  safe = safe.replace(/(^|[^_])_([^_\n]+?)_(?!_)/g, "$1<em>$2</em>");
  safe = safe.replace(/ CODE(\d+) /g, (_, idx) => "<code>" + codes[Number(idx)] + "</code>");
  return safe;
}

function renderTableBlock(lines) {
  // Erste Zeile = Header, zweite Zeile = Trenner (---), Rest = Body.
  const stripBorders = (line) => line.replace(/^\s*\|/, "").replace(/\|\s*$/, "");
  const splitCells = (line) => stripBorders(line).split("|").map((c) => c.trim());
  if (lines.length < 2) return null;
  const header = splitCells(lines[0]);
  const sep = splitCells(lines[1]);
  if (!sep.every((c) => /^:?-+:?$/.test(c))) return null;
  const bodyRows = lines.slice(2).map(splitCells);
  const headerHtml = header.map((c) => `<th>${renderInline(c)}</th>`).join("");
  const bodyHtml = bodyRows
    .map((row) => `<tr>${row.map((c) => `<td>${renderInline(c)}</td>`).join("")}</tr>`)
    .join("");
  return `<table class="campaign-note-table"><thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>`;
}

function renderListBlock(lines) {
  const ordered = /^\s*\d+\.\s+/.test(lines[0]);
  const items = lines.map((l) =>
    ordered ? l.replace(/^\s*\d+\.\s+/, "") : l.replace(/^\s*[-*]\s+/, ""),
  );
  const tag = ordered ? "ol" : "ul";
  return `<${tag}>${items.map((i) => `<li>${renderInline(i)}</li>`).join("")}</${tag}>`;
}

function renderBlockquoteBlock(lines) {
  const inner = lines.map((l) => l.replace(/^\s*>\s?/, "")).join("\n");
  return `<blockquote>${renderInline(escapeHtml(inner)).replace(/\n/g, "<br>")}</blockquote>`;
}

function isListLine(line) {
  return /^\s*([-*]|\d+\.)\s+/.test(line);
}

function isTableLine(line) {
  return line.includes("|") && line.trim() !== "";
}

export function renderMarkdown(source) {
  if (!source) return "";
  const escaped = escapeHtml(source);
  // Normalize Windows-Line-Endings.
  const normalized = escaped.replace(/\r\n/g, "\n");
  const blocks = normalized.split(/\n{2,}/);
  return blocks
    .map((block) => {
      const trimmed = block.replace(/^\n+|\n+$/g, "");
      if (!trimmed) return "";
      const lines = trimmed.split("\n");

      // Heading: # / ## / ### / #### …
      const headingMatch = lines.length === 1 && /^(#{1,6})\s+(.+)$/.exec(lines[0]);
      if (headingMatch) {
        const level = headingMatch[1].length;
        return `<h${level}>${renderInline(headingMatch[2])}</h${level}>`;
      }

      // Blockquote: jede Zeile beginnt mit "> ".
      if (lines.every((l) => /^\s*>/.test(l))) {
        return renderBlockquoteBlock(lines);
      }

      // Liste: jede Zeile beginnt mit "- ", "* " oder "1. ".
      if (lines.every(isListLine)) {
        return renderListBlock(lines);
      }

      // Tabelle: erste Zeile enthält "|" und zweite Zeile ist Trenner.
      if (lines.length >= 2 && isTableLine(lines[0]) && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[1])) {
        const tableHtml = renderTableBlock(lines);
        if (tableHtml) return tableHtml;
      }

      // Default: Absatz, Single-Newlines → <br>.
      return `<p>${renderInline(lines.join("\n")).replace(/\n/g, "<br>")}</p>`;
    })
    .join("");
}

function renderNoteCard(note, onEdit, onDelete) {
  const meta = `${note.author.display_name} · ${formatDateTime(note.created_at)}`;
  const body = h("div", { class: "campaign-note-body" });
  body.innerHTML = renderMarkdown(note.body_md);
  const actions = [];
  if (note.can_edit) {
    actions.push(
      h("button", { type: "button", class: "linklike", onclick: () => onEdit(note) }, "Bearbeiten"),
      h(
        "button",
        { type: "button", class: "linklike danger", onclick: () => onDelete(note) },
        "Löschen",
      ),
    );
  }
  return h(
    "article",
    { class: "campaign-note-card" },
    h("div", { class: "campaign-note-meta muted" }, meta),
    body,
    actions.length ? h("div", { class: "form-actions" }, ...actions) : null,
  );
}

// ---- Block 0031 — Markdown-Editor mit Toolbar + Live-Vorschau --------
//
// Eigener kleiner Editor — kein WYSIWYG, keine Library. Nutzer klicken
// Toolbar-Buttons, der Markdown-Quelltext bleibt im Speicher; eine
// Live-Vorschau rendert ``renderMarkdown(textarea.value)``. So müssen
// Nutzer keine Markdown-Syntax kennen.

const TOOLBAR_ACTIONS = [
  { key: "bold", label: "Fett", title: "Fett", apply: wrapInline("**", "**", "fetter Text") },
  { key: "italic", label: "Kursiv", title: "Kursiv", apply: wrapInline("*", "*", "kursiver Text") },
  { key: "code", label: "Code", title: "Inline-Code", apply: wrapInline("`", "`", "code") },
  { key: "heading", label: "Überschrift", title: "Überschrift (H3)", apply: prefixLines("### ", "Überschrift") },
  { key: "ul", label: "Liste", title: "Aufzählung", apply: prefixLines("- ", "Listenpunkt") },
  { key: "ol", label: "Nummerierte Liste", title: "Nummerierte Liste", apply: prefixLines("1. ", "Listenpunkt") },
  { key: "quote", label: "Zitat", title: "Zitat", apply: prefixLines("> ", "Zitat") },
  { key: "table", label: "Tabelle", title: "Beispiel-Tabelle einfügen", apply: insertTable },
  { key: "link", label: "Link", title: "Link", apply: insertLink },
];

function wrapInline(openMark, closeMark, placeholder) {
  return (textarea) => {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selected = textarea.value.slice(start, end);
    const inner = selected || placeholder;
    const replacement = openMark + inner + closeMark;
    textarea.setRangeText(replacement, start, end, "end");
    if (!selected) {
      // Selektion auf den Platzhalter setzen, damit man ihn direkt
      // überschreiben kann.
      const innerStart = start + openMark.length;
      textarea.setSelectionRange(innerStart, innerStart + placeholder.length);
    }
  };
}

function prefixLines(marker, placeholder) {
  return (textarea) => {
    const value = textarea.value;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    // Block-Anfang/-Ende auf Zeilengrenzen ausweiten.
    const blockStart = value.lastIndexOf("\n", start - 1) + 1;
    const blockEnd = end === start ? end : end;
    const original = value.slice(blockStart, blockEnd);
    const baseLines = (original || placeholder).split("\n");
    const prefixed = baseLines.map((l) => marker + l).join("\n");
    // Wenn der Cursor nicht am Zeilenanfang sitzt UND keine Selektion
    // existiert, einen Zeilenumbruch davor sicherstellen — sonst landet
    // der Marker mitten im laufenden Text.
    let leadingBreak = "";
    if (start === end && blockStart < start && !value.slice(blockStart, start).match(/^\s*$/)) {
      leadingBreak = "\n";
    }
    textarea.setRangeText(leadingBreak + prefixed, blockStart, blockEnd, "end");
  };
}

function insertTable(textarea) {
  const tpl =
    "\n| Spalte A | Spalte B |\n| --- | --- |\n| Wert 1 | Wert 2 |\n| Wert 3 | Wert 4 |\n";
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  textarea.setRangeText(tpl, start, end, "end");
}

function insertLink(textarea) {
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  const selected = textarea.value.slice(start, end);
  const linkText = selected || "Linktext";
  const replacement = "[" + linkText + "](https://)";
  textarea.setRangeText(replacement, start, end, "end");
  if (!selected) {
    const textStart = start + 1;
    textarea.setSelectionRange(textStart, textStart + linkText.length);
  }
}

function renderToolbar(textarea) {
  const buttons = TOOLBAR_ACTIONS.map((action) =>
    h(
      "button",
      {
        type: "button",
        class: "campaign-note-toolbar-button",
        title: action.title,
        "aria-label": action.title,
        onclick: () => {
          action.apply(textarea);
          textarea.focus();
          textarea.dispatchEvent(new Event("input", { bubbles: true }));
        },
      },
      action.label,
    ),
  );
  return h(
    "div",
    { class: "campaign-note-toolbar", role: "toolbar", "aria-label": "Notiz-Editor" },
    ...buttons,
  );
}

// Gibt ``{ container, textarea, getValue, setValue }`` zurück. Container
// enthält Toolbar, Textarea und Live-Vorschau in dieser Reihenfolge.
function renderMarkdownEditor(initialText, options = {}) {
  const minRows = options.rows || 8;
  const textarea = h("textarea", {
    class: "campaign-note-textarea",
    rows: String(minRows),
    placeholder: options.placeholder || "",
  });
  if (initialText) textarea.value = initialText;

  const previewLabel = h(
    "div",
    { class: "campaign-note-preview-label muted" },
    "Vorschau",
  );
  const previewBody = h("div", { class: "campaign-note-preview-body" });
  const preview = h(
    "div",
    { class: "campaign-note-preview", "aria-live": "polite" },
    previewLabel,
    previewBody,
  );

  function updatePreview() {
    const raw = textarea.value || "";
    if (raw.trim() === "") {
      preview.classList.add("is-empty");
      previewBody.innerHTML = "";
    } else {
      preview.classList.remove("is-empty");
      previewBody.innerHTML = renderMarkdown(textarea.value);
    }
  }
  textarea.addEventListener("input", updatePreview);
  updatePreview();

  const toolbar = renderToolbar(textarea);
  const help = h(
    "p",
    { class: "muted campaign-note-editor-help" },
    "Formatierung über die Buttons möglich; Markdown-Kenntnisse sind nicht erforderlich.",
  );

  const container = h(
    "div",
    { class: "campaign-note-editor" },
    toolbar,
    textarea,
    help,
    preview,
  );

  return {
    container,
    textarea,
    getValue: () => textarea.value,
    setValue: (v) => {
      textarea.value = v || "";
      updatePreview();
    },
  };
}

function renderNoteComposer(onSubmit) {
  const editor = renderMarkdownEditor("", {
    rows: 7,
    placeholder: "Idee, Beobachtung oder offene Frage notieren …",
  });
  const errorBox = h("p", { class: "error", style: "display:none" }, "");
  const submitBtn = h("button", { type: "submit" }, "Notiz hinzufügen");
  async function handle(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    const body = editor.getValue().trim();
    if (!body) {
      errorBox.textContent = "Bitte einen Text eingeben.";
      errorBox.style.display = "";
      return;
    }
    submitBtn.disabled = true;
    try {
      await onSubmit(body);
      editor.setValue("");
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    } finally {
      submitBtn.disabled = false;
    }
  }
  return h(
    "form",
    { class: "campaign-note-composer stacked", onsubmit: handle },
    editor.container,
    errorBox,
    h("div", { class: "form-actions" }, submitBtn),
  );
}

function renderNoteEditDialog(note, onSaved, onCancel) {
  const editor = renderMarkdownEditor(note.body_md, {
    rows: 10,
    placeholder: "Notiztext",
  });
  const errorBox = h("p", { class: "error", style: "display:none" }, "");
  async function handle(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    const body = editor.getValue().trim();
    if (!body) {
      errorBox.textContent = "Bitte einen Text eingeben.";
      errorBox.style.display = "";
      return;
    }
    try {
      await api("PATCH", `/api/campaign-notes/${note.id}`, { body_md: body });
      onSaved();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    }
  }
  return h(
    "form",
    { class: "stacked campaign-note-edit-dialog", onsubmit: handle },
    h("label", {}, "Notiztext", editor.container),
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit" }, "Speichern"),
      h("button", { type: "button", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

function renderNotesBlock(campaign, notes, onCreate, onEdit, onDelete) {
  const hint = h(
    "p",
    { class: "muted campaign-note-hint" },
    "Gemeinsame Arbeitsnotizen, Ideen, Beobachtungen und offene Fragen zur Testkampagne. Kein formales Laborbuch.",
  );
  const composer = campaign.can_create_note ? renderNoteComposer(onCreate) : null;
  const list = notes.length
    ? h(
        "div",
        { class: "campaign-note-list" },
        ...notes.map((n) => renderNoteCard(n, onEdit, onDelete)),
      )
    : renderEmpty("Noch keine Kampagnennotizen.");
  return h(
    "section",
    { class: "campaign-section" },
    h("h2", {}, "Kampagnennotizen"),
    hint,
    composer,
    list,
  );
}

function renderDocumentsBlock(campaign, canEdit, onLink, onUnlink) {
  const heading = h(
    "div",
    { class: "section-header" },
    h("h2", {}, "Dokumente"),
    canEdit ? h("button", { type: "button", onclick: onLink }, "Dokument verknüpfen …") : null,
  );
  if (!campaign.documents.length) {
    return h(
      "section",
      { class: "campaign-section" },
      heading,
      renderEmpty("Noch keine Dokumente verknüpft."),
    );
  }
  return h(
    "section",
    { class: "campaign-section" },
    heading,
    h(
      "div",
      { class: "campaign-document-grid" },
      ...campaign.documents.map((d) => renderDocumentCard(d, canEdit, onUnlink)),
    ),
  );
}

// ---- Hauptrender ------------------------------------------------------

export async function render(container, ctx) {
  container.classList.add("page-wide");
  const campaignId = ctx.params.id;
  appendChildren(
    container,
    pageHeader("Testkampagne"),
    renderLoading("Testkampagne wird geladen …"),
  );

  let campaign;
  let workpackages = [];
  let persons = [];
  let documents = [];
  let photos = [];
  let notes = [];
  try {
    [campaign, workpackages, persons, documents, photos, notes] = await Promise.all([
      api("GET", `/api/campaigns/${campaignId}`),
      api("GET", "/api/workpackages"),
      api("GET", "/api/persons"),
      api("GET", "/api/documents?include_archived=false").catch(() => []),
      api("GET", `/api/campaigns/${campaignId}/photos`).catch(() => []),
      api("GET", `/api/campaigns/${campaignId}/notes`).catch(() => []),
    ]);
  } catch (err) {
    appendChildren(container, pageHeader("Testkampagne"), renderError(err));
    return;
  }

  const dialogSlot = h("div", {});
  function clearDialog() {
    dialogSlot.replaceChildren();
  }
  function showDialog(title, body) {
    dialogSlot.replaceChildren(h("div", { class: "dialog" }, h("h3", {}, title), body));
  }
  async function reload() {
    try {
      [campaign, photos, notes] = await Promise.all([
        api("GET", `/api/campaigns/${campaignId}`),
        api("GET", `/api/campaigns/${campaignId}/photos`).catch(() => []),
        api("GET", `/api/campaigns/${campaignId}/notes`).catch(() => []),
      ]);
    } catch (err) {
      appendChildren(container, pageHeader("Testkampagne"), renderError(err));
      return;
    }
    rerender();
  }

  function onEditCampaign() {
    showDialog(
      "Testkampagne bearbeiten",
      renderEditDialog(
        campaign,
        workpackages,
        () => {
          clearDialog();
          reload();
        },
        clearDialog,
      ),
    );
  }
  async function onCancelCampaign() {
    if (!confirm("Testkampagne wirklich abbrechen? (status='cancelled')")) return;
    try {
      await api("POST", `/api/campaigns/${campaignId}/cancel`, {});
      reload();
    } catch (err) {
      alert(err.message);
    }
  }
  function onAddParticipant() {
    const already = new Set(campaign.participants.map((p) => p.person.id));
    showDialog(
      "Person hinzufügen",
      renderParticipantAddForm(
        campaignId,
        persons,
        already,
        () => {
          clearDialog();
          reload();
        },
        clearDialog,
      ),
    );
  }
  function onEditParticipant(participant) {
    showDialog(
      "Rolle / Notiz bearbeiten",
      renderParticipantEditForm(
        participant,
        () => {
          clearDialog();
          reload();
        },
        clearDialog,
      ),
    );
  }
  async function onRemoveParticipant(participant) {
    if (!confirm(`${participant.person.display_name} aus der Kampagne entfernen?`)) return;
    try {
      await api("DELETE", `/api/campaign-participants/${participant.id}`);
      reload();
    } catch (err) {
      alert(err.message);
    }
  }
  function onLinkDocument() {
    const already = new Set(campaign.documents.map((d) => d.document_id));
    showDialog(
      "Dokument verknüpfen",
      renderDocumentLinkForm(
        campaignId,
        documents,
        already,
        () => {
          clearDialog();
          reload();
        },
        clearDialog,
      ),
    );
  }
  async function onUnlinkDocument(doc) {
    if (!confirm(`Verknüpfung zu „${doc.title}" entfernen? Das Dokument bleibt erhalten.`)) return;
    try {
      await api("DELETE", `/api/campaigns/${campaignId}/documents/${doc.document_id}`);
      reload();
    } catch (err) {
      alert(err.message);
    }
  }
  function onUploadPhoto() {
    showDialog(
      "Foto hochladen",
      renderPhotoUploadDialog(
        campaignId,
        () => {
          clearDialog();
          reload();
        },
        clearDialog,
      ),
    );
  }
  function onEditPhotoCaption(photo) {
    showDialog(
      "Bildunterschrift bearbeiten",
      renderPhotoCaptionEditDialog(
        campaignId,
        photo,
        () => {
          clearDialog();
          reload();
        },
        clearDialog,
      ),
    );
  }
  async function onDeletePhoto(photo) {
    if (!confirm("Foto wirklich löschen?")) return;
    try {
      await api("DELETE", `/api/campaigns/${campaignId}/photos/${photo.id}`);
      reload();
    } catch (err) {
      alert(err.message);
    }
  }
  async function onCreateNote(body) {
    await api("POST", `/api/campaigns/${campaignId}/notes`, { body_md: body });
    await reload();
  }
  function onEditNote(note) {
    showDialog(
      "Notiz bearbeiten",
      renderNoteEditDialog(
        note,
        () => {
          clearDialog();
          reload();
        },
        clearDialog,
      ),
    );
  }
  async function onDeleteNote(note) {
    if (!confirm("Notiz wirklich löschen?")) return;
    try {
      await api("DELETE", `/api/campaign-notes/${note.id}`);
      reload();
    } catch (err) {
      alert(err.message);
    }
  }

  function rerender() {
    const actionButtons = [];
    if (campaign.can_edit) {
      actionButtons.push(
        h("button", { type: "button", onclick: onEditCampaign }, "Kampagne bearbeiten …"),
      );
      if (campaign.status !== "cancelled") {
        actionButtons.push(
          h(
            "button",
            { type: "button", class: "danger", onclick: onCancelCampaign },
            "Kampagne abbrechen …",
          ),
        );
      }
    }
    const headerActions = actionButtons.length
      ? h("div", { class: "actions" }, ...actionButtons)
      : null;

    // appendChildren filtert null/undefined/false aus — ohne diesen
    // Schutz machte die DOM-API aus ``null`` den Text „null"
    // (Ursache des „nullnullnull"-Bugs vor dem Folgepass).
    appendChildren(
      container,
      h(
        "p",
        { class: "muted" },
        h("a", { href: "/portal/campaigns" }, "← zurück zur Liste der Testkampagnen"),
      ),
      renderHeader(campaign),
      headerActions,
      renderOverviewCard(campaign),
      renderFactualBlock(campaign),
      renderWpsBlock(campaign),
      renderPhotosBlock(campaign, photos, onUploadPhoto, onEditPhotoCaption, onDeletePhoto),
      renderNotesBlock(campaign, notes, onCreateNote, onEditNote, onDeleteNote),
      renderParticipantsBlock(
        campaign,
        campaign.can_edit,
        onAddParticipant,
        onEditParticipant,
        onRemoveParticipant,
      ),
      renderDocumentsBlock(campaign, campaign.can_edit, onLinkDocument, onUnlinkDocument),
      dialogSlot,
      crossNav(),
    );
  }

  rerender();
}
