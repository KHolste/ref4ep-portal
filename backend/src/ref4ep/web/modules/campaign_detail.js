// Testkampagnen-Detailseite (Block 0022 + UX-Folgepass).
//
// Aufbau in fünf klar getrennten Sektionen:
//   1. Übersicht           — Code, Kategorie, Status, Zeitraum, Facility
//   2. Fachliche Details   — Ziel, Testmatrix, Messgrößen, Randbedingungen,
//                            Erfolgskriterien, Risiken (mit Empty-State)
//   3. Arbeitspakete       — Liste der WP-Codes
//   4. Beteiligte Personen — Karten pro Person mit Rollen-Pill (deutsch,
//                            kein UPPER-Badge)
//   5. Dokumente           — Karten mit Label, Titel, WP, Entknüpfen-Button
//
// Aktionen erscheinen nur, wenn ``can_edit=true``. Es gibt KEINEN
// Datei-Upload — Dokumente werden ausschließlich über
// /api/documents?include_archived=false ausgewählt und verlinkt.

import {
  api,
  appendChildren,
  crossNav,
  h,
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
  const campaignId = ctx.params.id;
  appendChildren(
    container,
    h("h1", {}, "Testkampagne"),
    renderLoading("Testkampagne wird geladen …"),
  );

  let campaign;
  let workpackages = [];
  let persons = [];
  let documents = [];
  try {
    [campaign, workpackages, persons, documents] = await Promise.all([
      api("GET", `/api/campaigns/${campaignId}`),
      api("GET", "/api/workpackages"),
      api("GET", "/api/persons"),
      api("GET", "/api/documents?include_archived=false").catch(() => []),
    ]);
  } catch (err) {
    appendChildren(container, h("h1", {}, "Testkampagne"), renderError(err));
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
      campaign = await api("GET", `/api/campaigns/${campaignId}`);
    } catch (err) {
      appendChildren(container, h("h1", {}, "Testkampagne"), renderError(err));
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
