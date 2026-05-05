// Meeting-Detailseite (Block 0015).
//
// Sektionen: Stammdaten / Teilnehmende / Beschlüsse / Aufgaben /
// Dokumente. Aktionsbuttons sind nur sichtbar, wenn ``can_edit``
// gesetzt ist (Server entscheidet).

import { api, crossNav, h, renderEmpty, renderError, renderLoading } from "/portal/common.js";

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

function nullIfBlank(value) {
  const v = (value || "").trim();
  return v === "" ? null : v;
}

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

function statusBadge(status) {
  return h("span", { class: "badge" }, STATUS_LABELS[status] || status);
}

function toLocalInput(iso) {
  // datetime-local braucht "YYYY-MM-DDTHH:MM" ohne Sekunden/Zone.
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

function renderEditMeetingForm(meeting, workpackages, onSaved, onCancel) {
  const titleInput = h("input", { type: "text", value: meeting.title, required: true });
  const startsAtInput = h("input", {
    type: "datetime-local",
    value: toLocalInput(meeting.starts_at),
    required: true,
  });
  const endsAtInput = h("input", {
    type: "datetime-local",
    value: toLocalInput(meeting.ends_at),
  });
  const formatSelect = h(
    "select",
    {},
    ...Object.entries(FORMAT_LABELS).map(([v, l]) =>
      h("option", { value: v, ...(meeting.format === v ? { selected: "" } : {}) }, l),
    ),
  );
  const categorySelect = h(
    "select",
    {},
    ...Object.entries(CATEGORY_LABELS).map(([v, l]) =>
      h("option", { value: v, ...(meeting.category === v ? { selected: "" } : {}) }, l),
    ),
  );
  const statusSelect = h(
    "select",
    {},
    ...Object.entries(STATUS_LABELS).map(([v, l]) =>
      h("option", { value: v, ...(meeting.status === v ? { selected: "" } : {}) }, l),
    ),
  );
  const locationInput = h("input", { type: "text", value: meeting.location || "" });
  const summaryInput = h("textarea", { rows: "3" }, meeting.summary || "");
  const extraInput = h("input", {
    type: "text",
    value: meeting.extra_participants || "",
  });
  const meetingWpCodes = new Set(meeting.workpackages.map((w) => w.code));
  const wpSelect = h(
    "select",
    { multiple: "" },
    ...workpackages.map((wp) =>
      h(
        "option",
        { value: wp.id, ...(meetingWpCodes.has(wp.code) ? { selected: "" } : {}) },
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
      title: titleInput.value,
      starts_at: new Date(startsAtInput.value).toISOString(),
      ends_at: endsAtInput.value ? new Date(endsAtInput.value).toISOString() : null,
      format: formatSelect.value,
      category: categorySelect.value,
      status: statusSelect.value,
      location: nullIfBlank(locationInput.value),
      summary: nullIfBlank(summaryInput.value),
      extra_participants: nullIfBlank(extraInput.value),
      workpackage_ids: selectedWpIds(),
    };
    try {
      await api("PATCH", `/api/meetings/${meeting.id}`, payload);
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
    h("label", {}, "Beginn", startsAtInput),
    h("label", {}, "Ende (optional)", endsAtInput),
    h("label", {}, "Format", formatSelect),
    h("label", {}, "Kategorie", categorySelect),
    h("label", {}, "Status", statusSelect),
    h("label", {}, "Ort / Online-Link", locationInput),
    h("label", {}, "Zusammenfassung", summaryInput),
    h("label", {}, "Zusätzliche Teilnehmende", extraInput),
    h("label", {}, "Arbeitspakete", wpSelect),
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit" }, "Speichern"),
      h("button", { type: "button", class: "secondary", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

function renderDecisionForm(meetingId, workpackages, persons, initial, onSaved, onCancel) {
  const isEdit = !!initial?.id;
  const textInput = h("textarea", { rows: "3", required: true }, initial?.text || "");
  const wpSelect = h(
    "select",
    {},
    h("option", { value: "" }, "— ohne WP-Bezug —"),
    ...workpackages.map((wp) =>
      h(
        "option",
        {
          value: wp.id,
          ...(initial?.workpackage_code === wp.code ? { selected: "" } : {}),
        },
        `${wp.code} — ${wp.title}`,
      ),
    ),
  );
  const responsibleSelect = h(
    "select",
    {},
    h("option", { value: "" }, "— offen —"),
    ...persons.map((p) =>
      h(
        "option",
        {
          value: p.id,
          ...(initial?.responsible_person?.id === p.id ? { selected: "" } : {}),
        },
        `${p.display_name} <${p.email}>`,
      ),
    ),
  );
  const statusSelect = h(
    "select",
    {},
    ...Object.entries(DECISION_STATUS_LABELS).map(([v, l]) =>
      h(
        "option",
        { value: v, ...(initial?.status === v ? { selected: "" } : {}) },
        l,
      ),
    ),
  );
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    const payload = {
      text: textInput.value,
      workpackage_id: nullIfBlank(wpSelect.value),
      responsible_person_id: nullIfBlank(responsibleSelect.value),
      status: statusSelect.value,
    };
    try {
      if (isEdit) {
        await api("PATCH", `/api/meeting-decisions/${initial.id}`, payload);
      } else {
        await api("POST", `/api/meetings/${meetingId}/decisions`, payload);
      }
      onSaved();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    }
  }

  return h(
    "form",
    { class: "stacked", onsubmit: onSubmit },
    h("label", {}, "Beschluss", textInput),
    h("label", {}, "Arbeitspaket", wpSelect),
    h("label", {}, "Verantwortlich", responsibleSelect),
    h("label", {}, "Status", statusSelect),
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit" }, isEdit ? "Speichern" : "Anlegen"),
      h("button", { type: "button", class: "secondary", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

function renderActionForm(meetingId, workpackages, persons, initial, onSaved, onCancel) {
  const isEdit = !!initial?.id;
  const textInput = h("textarea", { rows: "3", required: true }, initial?.text || "");
  const wpSelect = h(
    "select",
    {},
    h("option", { value: "" }, "— ohne WP-Bezug —"),
    ...workpackages.map((wp) =>
      h(
        "option",
        {
          value: wp.id,
          ...(initial?.workpackage_code === wp.code ? { selected: "" } : {}),
        },
        `${wp.code} — ${wp.title}`,
      ),
    ),
  );
  const responsibleSelect = h(
    "select",
    {},
    h("option", { value: "" }, "— offen —"),
    ...persons.map((p) =>
      h(
        "option",
        {
          value: p.id,
          ...(initial?.responsible_person?.id === p.id ? { selected: "" } : {}),
        },
        `${p.display_name} <${p.email}>`,
      ),
    ),
  );
  const dueInput = h("input", { type: "date", value: initial?.due_date || "" });
  const statusSelect = h(
    "select",
    {},
    ...Object.entries(ACTION_STATUS_LABELS).map(([v, l]) =>
      h(
        "option",
        { value: v, ...(initial?.status === v ? { selected: "" } : {}) },
        l,
      ),
    ),
  );
  const noteInput = h("textarea", { rows: "2" }, initial?.note || "");
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    const payload = {
      text: textInput.value,
      workpackage_id: nullIfBlank(wpSelect.value),
      responsible_person_id: nullIfBlank(responsibleSelect.value),
      due_date: nullIfBlank(dueInput.value),
      status: statusSelect.value,
      note: nullIfBlank(noteInput.value),
    };
    try {
      if (isEdit) {
        await api("PATCH", `/api/meeting-actions/${initial.id}`, payload);
      } else {
        await api("POST", `/api/meetings/${meetingId}/actions`, payload);
      }
      onSaved();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    }
  }

  return h(
    "form",
    { class: "stacked", onsubmit: onSubmit },
    h("label", {}, "Aufgabe", textInput),
    h("label", {}, "Arbeitspaket", wpSelect),
    h("label", {}, "Verantwortlich", responsibleSelect),
    h("label", {}, "Frist", dueInput),
    h("label", {}, "Status", statusSelect),
    h("label", {}, "Notiz", noteInput),
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit" }, isEdit ? "Speichern" : "Anlegen"),
      h("button", { type: "button", class: "secondary", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

function renderParticipantForm(meetingId, persons, alreadyIds, onSaved, onCancel) {
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
    ...candidates.map((p) =>
      h("option", { value: p.id }, `${p.display_name} <${p.email}>`),
    ),
  );
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    try {
      await api("POST", `/api/meetings/${meetingId}/participants`, {
        person_id: personSelect.value,
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
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit" }, "Hinzufügen"),
      h("button", { type: "button", class: "secondary", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

function renderDocumentLinkForm(meetingId, documents, alreadyIds, onSaved, onCancel) {
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
    ...candidates.map((d) =>
      h(
        "option",
        { value: d.id },
        d.deliverable_code ? `[${d.deliverable_code}] ${d.title}` : d.title,
      ),
    ),
  );
  const labelSelect = h(
    "select",
    {},
    ...Object.entries(DOC_LABEL_LABELS).map(([v, l]) =>
      h("option", { value: v, ...(v === "minutes" ? { selected: "" } : {}) }, l),
    ),
  );
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    try {
      await api("POST", `/api/meetings/${meetingId}/documents`, {
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

function renderHeader(meeting) {
  return h(
    "div",
    {},
    h("h1", {}, meeting.title, " ", statusBadge(meeting.status)),
    h(
      "p",
      {},
      "Termin: ",
      formatDateTime(meeting.starts_at),
      meeting.ends_at ? ` – ${formatDateTime(meeting.ends_at)}` : "",
    ),
    h("p", {}, `Format: ${FORMAT_LABELS[meeting.format] || meeting.format}`),
    meeting.location ? h("p", {}, `Ort: ${meeting.location}`) : null,
    h("p", {}, `Kategorie: ${CATEGORY_LABELS[meeting.category] || meeting.category}`),
    h(
      "p",
      {},
      "Angelegt von ",
      meeting.created_by ? meeting.created_by.display_name : "—",
    ),
  );
}

function renderWpsBlock(meeting) {
  if (!meeting.workpackages.length) {
    return h(
      "section",
      {},
      h("h2", {}, "Arbeitspakete"),
      renderEmpty("Kein Arbeitspaket-Bezug — Konsortialtreffen oder allgemein."),
    );
  }
  return h(
    "section",
    {},
    h("h2", {}, "Arbeitspakete"),
    h(
      "ul",
      {},
      ...meeting.workpackages.map((wp) =>
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

function renderParticipantsBlock(meeting, canEdit, onAdd, onRemove) {
  const items = meeting.participants.map((p) =>
    h(
      "li",
      {},
      `${p.display_name} <${p.email}>`,
      canEdit
        ? h(
            "button",
            {
              type: "button",
              class: "linklike danger",
              style: "margin-left: 0.5rem",
              onclick: () => onRemove(p),
            },
            "entfernen",
          )
        : null,
    ),
  );
  const heading = h(
    "div",
    { class: "section-header" },
    h("h2", {}, "Teilnehmende"),
    canEdit ? h("button", { type: "button", onclick: onAdd }, "Person hinzufügen …") : null,
  );
  const body = items.length
    ? h("ul", {}, ...items)
    : renderEmpty("Noch keine Teilnehmenden eingetragen.");
  return h(
    "section",
    {},
    heading,
    body,
    meeting.extra_participants
      ? h(
          "p",
          { class: "muted" },
          `Zusätzliche Teilnehmende: ${meeting.extra_participants}`,
        )
      : null,
  );
}

function renderDecisionsBlock(meeting, canEdit, onCreate, onEdit) {
  const heading = h(
    "div",
    { class: "section-header" },
    h("h2", {}, "Beschlüsse"),
    canEdit ? h("button", { type: "button", onclick: onCreate }, "Beschluss hinzufügen …") : null,
  );
  if (!meeting.decisions.length) {
    return h("section", {}, heading, renderEmpty("Noch keine Beschlüsse erfasst."));
  }
  const cards = meeting.decisions.map((d) =>
    h(
      "article",
      { class: "wp-issue-card" },
      h(
        "div",
        { class: "wp-issue-head" },
        h("h3", {}, d.workpackage_code ? `${d.workpackage_code}` : "Konsortium"),
        h("span", { class: "badge" }, DECISION_STATUS_LABELS[d.status] || d.status),
      ),
      h("p", {}, d.text),
      d.responsible_person
        ? h("p", { class: "muted" }, `Verantwortlich: ${d.responsible_person.display_name}`)
        : null,
      canEdit
        ? h(
            "div",
            { class: "form-actions" },
            h(
              "button",
              { type: "button", onclick: () => onEdit(d) },
              "Bearbeiten …",
            ),
          )
        : null,
    ),
  );
  return h("section", {}, heading, ...cards);
}

function renderActionsBlock(meeting, canEdit, onCreate, onEdit) {
  const heading = h(
    "div",
    { class: "section-header" },
    h("h2", {}, "Aufgaben"),
    canEdit ? h("button", { type: "button", onclick: onCreate }, "Aufgabe hinzufügen …") : null,
  );
  if (!meeting.actions.length) {
    return h("section", {}, heading, renderEmpty("Noch keine Aufgaben verteilt."));
  }
  const rows = meeting.actions.map((a) =>
    h(
      "tr",
      {},
      h("td", {}, a.text),
      h("td", {}, a.workpackage_code || h("span", { class: "muted" }, "—")),
      h("td", {}, a.responsible_person?.display_name || h("span", { class: "muted" }, "—")),
      h("td", {}, formatDate(a.due_date)),
      h("td", {}, h("span", { class: "badge" }, ACTION_STATUS_LABELS[a.status] || a.status)),
      h(
        "td",
        {},
        canEdit
          ? h("button", { type: "button", onclick: () => onEdit(a) }, "Bearbeiten …")
          : null,
      ),
    ),
  );
  return h(
    "section",
    {},
    heading,
    h(
      "table",
      {},
      h(
        "thead",
        {},
        h(
          "tr",
          {},
          h("th", {}, "Aufgabe"),
          h("th", {}, "WP"),
          h("th", {}, "Verantwortlich"),
          h("th", {}, "Frist"),
          h("th", {}, "Status"),
          h("th", {}, ""),
        ),
      ),
      h("tbody", {}, ...rows),
    ),
  );
}

function renderDocumentsBlock(meeting, canEdit, onLink, onUnlink) {
  const heading = h(
    "div",
    { class: "section-header" },
    h("h2", {}, "Dokumente"),
    canEdit ? h("button", { type: "button", onclick: onLink }, "Dokument verknüpfen …") : null,
  );
  if (!meeting.documents.length) {
    return h("section", {}, heading, renderEmpty("Noch keine Dokumente verknüpft."));
  }
  const items = meeting.documents.map((d) =>
    h(
      "li",
      {},
      h("strong", {}, DOC_LABEL_LABELS[d.label] || d.label),
      ": ",
      h("a", { href: `/portal/documents/${d.document_id}` }, d.title),
      d.deliverable_code ? ` (${d.deliverable_code})` : "",
      canEdit
        ? h(
            "button",
            {
              type: "button",
              class: "linklike danger",
              style: "margin-left: 0.5rem",
              onclick: () => onUnlink(d),
            },
            "entknüpfen",
          )
        : null,
    ),
  );
  return h("section", {}, heading, h("ul", {}, ...items));
}

export async function render(container, ctx) {
  const meetingId = ctx.params.id;
  container.replaceChildren(
    h("h1", {}, "Meeting"),
    renderLoading("Meeting wird geladen …"),
  );

  let meeting;
  let workpackages = [];
  let persons = [];
  let documents = [];
  try {
    [meeting, workpackages, persons, documents] = await Promise.all([
      api("GET", `/api/meetings/${meetingId}`),
      api("GET", "/api/workpackages"),
      api("GET", "/api/persons"),
      api("GET", "/api/documents?include_archived=false").catch(() => []),
    ]);
  } catch (err) {
    container.replaceChildren(h("h1", {}, "Meeting"), renderError(err));
    return;
  }

  // Falls /api/documents nicht existiert (Block 0015 ändert die
  // Dokument-API nicht), versuchen wir einen schmaleren Aufruf.
  if (!Array.isArray(documents) || !documents.length) {
    try {
      // Bestehende Dokumente kommen pro WP — wir sammeln sie über alle WPs.
      const collected = [];
      for (const wp of workpackages) {
        try {
          const docs = await api(
            "GET",
            `/api/workpackages/${encodeURIComponent(wp.code)}/documents`,
          );
          for (const d of docs) collected.push(d);
        } catch {
          // Wenn ein WP keine Dokumente liefert, ignorieren.
        }
      }
      documents = collected;
    } catch {
      documents = [];
    }
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
      meeting = await api("GET", `/api/meetings/${meetingId}`);
    } catch (err) {
      container.replaceChildren(h("h1", {}, "Meeting"), renderError(err));
      return;
    }
    rerender();
  }

  function onEditMeeting() {
    showDialog(
      "Meeting bearbeiten",
      renderEditMeetingForm(
        meeting,
        workpackages,
        () => {
          clearDialog();
          reload();
        },
        clearDialog,
      ),
    );
  }

  async function onCancelMeeting() {
    if (!confirm("Meeting wirklich absagen? (status='cancelled')")) return;
    try {
      await api("POST", `/api/meetings/${meetingId}/cancel`, {});
      reload();
    } catch (err) {
      alert(err.message);
    }
  }

  function onAddDecision() {
    showDialog(
      "Beschluss hinzufügen",
      renderDecisionForm(
        meetingId,
        workpackages,
        persons,
        null,
        () => {
          clearDialog();
          reload();
        },
        clearDialog,
      ),
    );
  }

  function onEditDecision(decision) {
    showDialog(
      "Beschluss bearbeiten",
      renderDecisionForm(
        meetingId,
        workpackages,
        persons,
        decision,
        () => {
          clearDialog();
          reload();
        },
        clearDialog,
      ),
    );
  }

  function onAddAction() {
    showDialog(
      "Aufgabe hinzufügen",
      renderActionForm(
        meetingId,
        workpackages,
        persons,
        null,
        () => {
          clearDialog();
          reload();
        },
        clearDialog,
      ),
    );
  }

  function onEditAction(action) {
    showDialog(
      "Aufgabe bearbeiten",
      renderActionForm(
        meetingId,
        workpackages,
        persons,
        action,
        () => {
          clearDialog();
          reload();
        },
        clearDialog,
      ),
    );
  }

  function onAddParticipant() {
    const already = new Set(meeting.participants.map((p) => p.id));
    showDialog(
      "Teilnehmende Person hinzufügen",
      renderParticipantForm(
        meetingId,
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

  async function onRemoveParticipant(person) {
    if (!confirm(`${person.display_name} aus den Teilnehmenden entfernen?`)) return;
    try {
      await api("DELETE", `/api/meetings/${meetingId}/participants/${person.id}`);
      reload();
    } catch (err) {
      alert(err.message);
    }
  }

  function onLinkDocument() {
    const already = new Set(meeting.documents.map((d) => d.document_id));
    showDialog(
      "Dokument verknüpfen",
      renderDocumentLinkForm(
        meetingId,
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
    if (!confirm(`Verknüpfung zu „${doc.title}" entfernen? Das Dokument bleibt erhalten.`))
      return;
    try {
      await api("DELETE", `/api/meetings/${meetingId}/documents/${doc.document_id}`);
      reload();
    } catch (err) {
      alert(err.message);
    }
  }

  function rerender() {
    const headerActions = meeting.can_edit
      ? h(
          "div",
          { class: "actions" },
          h("button", { type: "button", onclick: onEditMeeting }, "Meeting bearbeiten …"),
          meeting.status === "cancelled"
            ? null
            : h(
                "button",
                { type: "button", class: "danger", onclick: onCancelMeeting },
                "Meeting absagen …",
              ),
        )
      : null;

    container.replaceChildren(
      h(
        "p",
        { class: "muted" },
        h("a", { href: "/portal/meetings" }, "← zurück zur Meeting-Liste"),
      ),
      renderHeader(meeting),
      headerActions || h("div", {}),
      meeting.summary
        ? h("section", {}, h("h2", {}, "Zusammenfassung"), h("p", {}, meeting.summary))
        : null,
      renderWpsBlock(meeting),
      renderParticipantsBlock(meeting, meeting.can_edit, onAddParticipant, onRemoveParticipant),
      renderDecisionsBlock(meeting, meeting.can_edit, onAddDecision, onEditDecision),
      renderActionsBlock(meeting, meeting.can_edit, onAddAction, onEditAction),
      renderDocumentsBlock(meeting, meeting.can_edit, onLinkDocument, onUnlinkDocument),
      dialogSlot,
      crossNav(),
    );
  }

  rerender();
}
