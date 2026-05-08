// Arbeitspaket-Detail / Cockpit (Block 0009).
//
// Sektionen:
//  - Header mit Status-Badge
//  - Cockpit (Kurzbeschreibung, nächste Schritte, offene Punkte)
//  - Lead-Partner + Kontaktpersonen
//  - Mitglieder
//  - Unterarbeitspakete
//  - Meilensteine
//  - Dokumente

import {
  api,
  crossNav,
  h,
  pageHeader,
  renderEmpty,
  renderError,
  renderLoading,
} from "/portal/common.js";

const TYPE_LABELS = {
  deliverable: "Deliverable",
  report: "Report",
  note: "Notiz",
  other: "Sonstiges",
};

const WP_STATUS_LABELS = {
  planned: "geplant",
  in_progress: "in Arbeit",
  waiting_for_input: "wartet auf Input",
  critical: "kritisch",
  completed: "abgeschlossen",
};

const WP_STATUS_BADGE = {
  planned: "badge-draft",
  in_progress: "badge-released",
  waiting_for_input: "badge-draft",
  critical: "badge-draft",
  completed: "badge-released",
};

const MS_STATUS_LABELS = {
  planned: "geplant",
  achieved: "erreicht",
  postponed: "verschoben",
  at_risk: "gefährdet",
  cancelled: "entfallen",
};

function nullIfBlank(value) {
  const v = (value || "").trim();
  return v === "" ? null : v;
}

function formatDate(iso) {
  if (!iso) return null;
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

function statusBadge(status) {
  return h(
    "span",
    { class: `badge ${WP_STATUS_BADGE[status] || "badge-draft"}` },
    WP_STATUS_LABELS[status] || status,
  );
}

function renderCockpitView(wp) {
  function block(title, value) {
    return h(
      "section",
      {},
      h("h3", {}, title),
      value
        ? h("p", { class: "doc-description" }, value)
        : h("p", { class: "muted" }, "—"),
    );
  }
  // Block 0027: Zeitplan kompakt anzeigen.
  const start = wp.start_date || "—";
  const end = wp.end_date || "—";
  const isTopLevel = !wp.parent;
  const scheduleBlock = h(
    "section",
    {},
    h("h3", {}, "Zeitplan"),
    h("p", {}, `Start: ${start} · Ende: ${end}`),
    isTopLevel
      ? h(
          "p",
          { class: "muted" },
          "Datumsfelder am Hauptpaket werden im Zeitplan automatisch aus den Unterpaketen abgeleitet; manuelle Werte sind optional.",
        )
      : null,
  );
  return h(
    "div",
    {},
    scheduleBlock,
    block("Kurzbeschreibung / aktueller Stand", wp.summary),
    block("Nächste Schritte", wp.next_steps),
    block("Offene Punkte", wp.open_issues),
  );
}

function renderCockpitEditForm(wp, onSaved, onCancel) {
  const statusSelect = h(
    "select",
    {},
    ...Object.entries(WP_STATUS_LABELS).map(([value, label]) =>
      h(
        "option",
        { value, ...(wp.status === value ? { selected: "" } : {}) },
        label,
      ),
    ),
  );
  const summaryInput = h("textarea", { rows: "4" }, wp.summary || "");
  const nextStepsInput = h("textarea", { rows: "4" }, wp.next_steps || "");
  const openIssuesInput = h("textarea", { rows: "4" }, wp.open_issues || "");
  // Block 0027 — optionale Datumsfelder.
  const startDateInput = h("input", {
    type: "date",
    value: wp.start_date || "",
  });
  const endDateInput = h("input", {
    type: "date",
    value: wp.end_date || "",
  });
  const isTopLevel = !wp.parent;
  const scheduleHint = isTopLevel
    ? h(
        "small",
        { class: "field-hint" },
        "Bei Hauptpaketen optional — der Gantt-Aggregatbalken wird aus den Sub-WPs gerechnet.",
      )
    : null;
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    try {
      await api("PATCH", `/api/workpackages/${encodeURIComponent(wp.code)}`, {
        status: statusSelect.value,
        summary: nullIfBlank(summaryInput.value),
        next_steps: nullIfBlank(nextStepsInput.value),
        open_issues: nullIfBlank(openIssuesInput.value),
        start_date: startDateInput.value || null,
        end_date: endDateInput.value || null,
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
    h("label", {}, "Status", statusSelect),
    h("label", {}, "Startdatum", startDateInput),
    h("label", {}, "Enddatum", endDateInput),
    scheduleHint,
    h("label", {}, "Kurzbeschreibung / aktueller Stand", summaryInput),
    h("label", {}, "Nächste Schritte", nextStepsInput),
    h("label", {}, "Offene Punkte", openIssuesInput),
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit" }, "Speichern"),
      h("button", { type: "button", class: "secondary", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

function renderLeadContacts(wp) {
  const contacts = wp.lead_partner_contacts || [];
  if (!contacts.length) {
    return h(
      "section",
      {},
      h("h2", {}, "Kontaktpersonen des Lead-Partners"),
      h(
        "p",
        { class: "muted" },
        "Der Lead-Partner hat noch keine internen Kontaktpersonen hinterlegt.",
      ),
    );
  }
  const items = contacts.map((c) =>
    h(
      "li",
      {},
      c.title_or_degree ? `${c.title_or_degree} ${c.name}` : c.name,
      c.function ? ` — ${c.function}` : "",
      c.email ? [" · ", h("a", { href: `mailto:${c.email}` }, c.email)] : null,
      c.phone ? ` · ${c.phone}` : "",
      c.is_primary_contact
        ? h("span", { class: "badge badge-released" }, "Hauptkontakt")
        : null,
      c.is_project_lead
        ? h("span", { class: "badge badge-released" }, "Projektleitung")
        : null,
    ),
  );
  return h(
    "section",
    {},
    h("h2", {}, "Kontaktpersonen des Lead-Partners"),
    h("ul", {}, ...items),
    h(
      "p",
      { class: "muted" },
      h("a", { href: `/portal/partners/${wp.lead_partner.id}` }, "Alle Kontaktpersonen ansehen"),
    ),
  );
}

function renderMilestones(wp) {
  const milestones = wp.milestones || [];
  if (!milestones.length) {
    return h(
      "section",
      {},
      h("h2", {}, "Meilensteine"),
      h(
        "p",
        { class: "muted" },
        "Diesem Arbeitspaket ist kein Meilenstein zugeordnet.",
      ),
    );
  }
  const rows = milestones.map((ms) =>
    h(
      "tr",
      {},
      h("td", {}, ms.code),
      h("td", {}, ms.title),
      h("td", {}, formatDate(ms.planned_date) || "—"),
      h(
        "td",
        {},
        ms.actual_date ? formatDate(ms.actual_date) : h("span", { class: "muted" }, "—"),
      ),
      h(
        "td",
        {},
        h(
          "span",
          { class: "badge" },
          MS_STATUS_LABELS[ms.status] || ms.status,
        ),
      ),
    ),
  );
  return h(
    "section",
    {},
    h("h2", {}, "Meilensteine"),
    h(
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
          h("th", {}, "Plandatum"),
          h("th", {}, "Istdatum"),
          h("th", {}, "Status"),
        ),
      ),
      h("tbody", {}, ...rows),
    ),
    h(
      "p",
      { class: "muted" },
      h("a", { href: "/portal/milestones" }, "Zur Meilensteinübersicht"),
    ),
  );
}

function renderDocumentsSection(wpCode, documents, onCreate) {
  const headerRow = h(
    "div",
    { class: "section-header" },
    h("h2", {}, "Dokumente"),
    h("button", { type: "button", onclick: onCreate }, "Neues Dokument anlegen …"),
  );

  if (!documents.length) {
    return h(
      "section",
      {},
      headerRow,
      renderEmpty("Noch keine Dokumente in diesem Arbeitspaket — leg das erste an."),
    );
  }

  const rows = documents.map((d) =>
    h(
      "tr",
      {},
      h("td", {}, d.deliverable_code || ""),
      h("td", {}, h("a", { href: `/portal/documents/${d.id}` }, d.title)),
      h("td", {}, TYPE_LABELS[d.document_type] || d.document_type),
      h("td", {}, d.status),
      h("td", {}, d.latest_version ? `v${d.latest_version.version_number}` : "—"),
      h("td", {}, new Date(d.updated_at).toLocaleDateString("de-DE")),
    ),
  );

  return h(
    "section",
    {},
    headerRow,
    h(
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
          h("th", {}, "Typ"),
          h("th", {}, "Status"),
          h("th", {}, "Letzte"),
          h("th", {}, "Aktualisiert"),
        ),
      ),
      h("tbody", {}, ...rows),
    ),
  );
}

function openCreateDialog(wpCode, onCreated) {
  const errorBox = h("p", { class: "error", style: "display:none" }, "");
  const titleInput = h("input", { type: "text", name: "title", required: true });
  const typeSelect = h(
    "select",
    { name: "document_type" },
    h("option", { value: "deliverable" }, "Deliverable"),
    h("option", { value: "report" }, "Report"),
    h("option", { value: "note" }, "Notiz"),
    h("option", { value: "other" }, "Sonstiges"),
  );
  const codeInput = h("input", {
    type: "text",
    name: "deliverable_code",
    placeholder: "z. B. D1.1",
  });
  const codeHelp = h(
    "small",
    { class: "field-hint" },
    "Optional — z. B. „D1.1“ oder „REF4EP-WP1-001“. Leer lassen, falls kein Code vergeben wird.",
  );
  const descriptionInput = h("textarea", {
    name: "description",
    rows: "3",
    placeholder: "Kurze inhaltliche Beschreibung (optional)",
  });
  const descriptionHelp = h(
    "small",
    { class: "field-hint" },
    "Optional. Erscheint im Dokument-Detail; nicht in der öffentlichen Bibliothek.",
  );

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    try {
      const created = await api(
        "POST",
        `/api/workpackages/${encodeURIComponent(wpCode)}/documents`,
        {
          title: titleInput.value,
          document_type: typeSelect.value,
          deliverable_code: codeInput.value || null,
          description: descriptionInput.value || null,
        },
      );
      onCreated(created);
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    }
  }

  const form = h(
    "form",
    { class: "stacked", onsubmit: onSubmit },
    h("label", {}, "Titel", titleInput),
    h("label", {}, "Typ", typeSelect),
    h("label", {}, "Dokumentcode (optional)", codeInput, codeHelp),
    h("label", {}, "Beschreibung (optional)", descriptionInput, descriptionHelp),
    errorBox,
    h("button", { type: "submit" }, "Anlegen"),
  );

  return h("div", { class: "dialog" }, h("h3", {}, "Neues Dokument anlegen"), form);
}

export async function render(container, ctx) {
  container.classList.add("page-wide");
  const code = ctx.params.code;
  let wp;
  let documents = [];

  async function load() {
    [wp, documents] = await Promise.all([
      api("GET", `/api/workpackages/${encodeURIComponent(code)}`),
      api("GET", `/api/workpackages/${encodeURIComponent(code)}/documents`),
    ]);
  }

  container.replaceChildren(
    pageHeader(code),
    renderLoading("Arbeitspaket-Details werden geladen …"),
  );

  try {
    await load();
  } catch (err) {
    container.replaceChildren(pageHeader(code), renderError(err));
    return;
  }

  let editingCockpit = false;
  const dialogContainer = h("div", {});

  function clearDialog() {
    dialogContainer.replaceChildren();
  }

  function rerender() {
    const editBtn =
      wp.can_edit_status && !editingCockpit
        ? h(
            "button",
            {
              type: "button",
              onclick: () => {
                editingCockpit = true;
                rerender();
              },
            },
            "Cockpit bearbeiten …",
          )
        : null;
    const headerRow = pageHeader(`${wp.code} — ${wp.title}`, null, {
      actions: editBtn,
    });

    const headerMeta = h(
      "div",
      {},
      h(
        "p",
        {},
        "Status: ",
        statusBadge(wp.status),
      ),
      h(
        "p",
        {},
        "Lead-Partner: ",
        h(
          "a",
          { href: `/portal/partners/${wp.lead_partner.id}` },
          `${wp.lead_partner.name} (${wp.lead_partner.short_name})`,
        ),
      ),
      wp.parent
        ? h(
            "p",
            {},
            "Übergeordnet: ",
            h("a", { href: `/portal/workpackages/${wp.parent.code}` }, wp.parent.code),
            ` — ${wp.parent.title}`,
          )
        : null,
      wp.description ? h("p", {}, wp.description) : null,
    );

    const cockpitSection = editingCockpit
      ? h(
          "section",
          {},
          h("h2", {}, "Cockpit bearbeiten"),
          renderCockpitEditForm(
            wp,
            async () => {
              await load();
              editingCockpit = false;
              rerender();
            },
            () => {
              editingCockpit = false;
              rerender();
            },
          ),
        )
      : h("section", {}, h("h2", {}, "Cockpit"), renderCockpitView(wp));

    const childrenSection =
      wp.children && wp.children.length
        ? h(
            "section",
            {},
            h("h2", {}, "Unterarbeitspakete"),
            h(
              "ul",
              {},
              ...wp.children.map((c) =>
                h(
                  "li",
                  {},
                  h("a", { href: `/portal/workpackages/${c.code}` }, c.code),
                  ` — ${c.title} (${c.lead_partner.short_name})`,
                ),
              ),
            ),
          )
        : null;

    const memberSection =
      wp.memberships && wp.memberships.length
        ? h(
            "section",
            {},
            h("h2", {}, "Mitglieder"),
            h(
              "ul",
              {},
              ...wp.memberships.map((m) =>
                h("li", {}, `${m.person_display_name} <${m.person_email}> (${m.wp_role})`),
              ),
            ),
          )
        : h(
            "section",
            {},
            h("h2", {}, "Mitglieder"),
            renderEmpty("Noch keine Mitglieder eingetragen."),
          );

    function openCreate() {
      dialogContainer.replaceChildren(
        openCreateDialog(code, (created) => {
          ctx.navigate(`/portal/documents/${created.id}`);
        }),
      );
    }

    const documentsSection = renderDocumentsSection(code, documents, openCreate);

    container.replaceChildren(
      headerRow,
      headerMeta,
      cockpitSection,
      childrenSection || h("div", {}),
      renderLeadContacts(wp),
      memberSection,
      renderMilestones(wp),
      documentsSection,
      dialogContainer,
      crossNav("/portal/workpackages"),
    );
  }

  rerender();
}
