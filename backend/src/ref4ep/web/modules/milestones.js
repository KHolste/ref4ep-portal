// Meilensteinübersicht (Block 0009 + UX-Polish).
//
// Vertikale Timeline aller Projekt-Meilensteine — Status, Zeiträume und
// Notizen sind als Karte pro Meilenstein lesbar. Berechtigte (Admin
// oder WP-Lead des MS-Arbeitspakets) bekommen einen Bearbeiten-Dialog.

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

const DOCUMENT_TYPE_LABELS = {
  deliverable: "Deliverable",
  meeting_doc: "Meeting-Dokument",
  test_report: "Testbericht",
  paper: "Paper",
  thesis: "Abschlussarbeit",
  presentation: "Präsentation",
  protocol: "Protokoll",
  specification: "Spezifikation",
  template: "Template",
  dataset: "Datensatz",
  manual: "Handbuch",
  note: "Notiz",
  other: "Sonstiges",
};

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

function linkedDocumentRow(milestone, link, canEdit, onChanged) {
  const codePart = link.deliverable_code ? `[${link.deliverable_code}] ` : "";
  const typeLabel = DOCUMENT_TYPE_LABELS[link.document_type] || link.document_type;
  const wpPart = link.workpackage_code ? ` · ${link.workpackage_code}` : "";
  const meta = `${typeLabel}${wpPart}`;
  const titleLink = h(
    "a",
    { href: `/portal/documents/${link.document_id}` },
    `${codePart}${link.title}`,
  );
  const children = [
    h("div", { class: "linked-doc-main" }, titleLink, h("p", { class: "linked-doc-meta muted" }, meta)),
  ];
  if (canEdit) {
    const removeBtn = h(
      "button",
      {
        type: "button",
        class: "button-secondary button-compact",
        onclick: async () => {
          if (!window.confirm(`Verknüpfung mit "${link.title}" wirklich entfernen?`)) return;
          try {
            await api("DELETE", `/api/milestones/${milestone.id}/documents/${link.document_id}`);
            onChanged();
          } catch (err) {
            alert(err.message);
          }
        },
      },
      "Entfernen",
    );
    children.push(h("div", { class: "linked-doc-actions" }, removeBtn));
  }
  return h("li", { class: "linked-doc-row" }, ...children);
}

function renderLinkPicker(milestone, allDocuments, existingIds, onSaved, onCancel) {
  const candidates = allDocuments.filter((d) => !existingIds.has(d.id));
  if (!candidates.length) {
    return h(
      "div",
      {},
      renderEmpty("Keine weiteren Dokumente verfügbar."),
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
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    try {
      await api("POST", `/api/milestones/${milestone.id}/documents`, {
        document_id: docSelect.value,
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
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit" }, "Verknüpfen"),
      h("button", { type: "button", class: "secondary", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

function linkedDocumentsSection(milestone, links, canEdit, onLink, onChanged) {
  const header = h(
    "div",
    { class: "linked-docs-head" },
    h("h4", { class: "linked-docs-title" }, `Verknüpfte Dokumente (${links.length})`),
    canEdit
      ? h(
          "button",
          {
            type: "button",
            class: "button-secondary button-compact",
            onclick: () => onLink(milestone, new Set(links.map((l) => l.document_id))),
          },
          "Dokument verknüpfen …",
        )
      : null,
  );

  const body = links.length
    ? h(
        "ul",
        { class: "linked-docs-list" },
        ...links.map((link) => linkedDocumentRow(milestone, link, canEdit, onChanged)),
      )
    : h("p", { class: "muted small" }, "Noch keine Dokumente verknüpft.");

  return h("section", { class: "linked-docs" }, header, body);
}

function timelineItem(milestone, linkedDocs, onEdit, onLink, onChanged) {
  const wpLink = milestone.workpackage_code
    ? h(
        "a",
        { href: `/portal/workpackages/${milestone.workpackage_code}` },
        `${milestone.workpackage_code} — ${milestone.workpackage_title || ""}`,
      )
    : h("span", { class: "muted" }, "Gesamtprojekt");

  const itemClasses = ["timeline-item"];
  if (milestone.status === "achieved") itemClasses.push("timeline-item-achieved");
  if (milestone.status === "cancelled") itemClasses.push("timeline-item-cancelled");

  const metaLines = [
    h(
      "p",
      { class: "timeline-meta" },
      "Plandatum: ",
      h("strong", {}, formatDate(milestone.planned_date) || "—"),
      milestone.actual_date
        ? h(
            "span",
            {},
            " · Istdatum: ",
            h("strong", {}, formatDate(milestone.actual_date)),
          )
        : null,
    ),
    h("p", { class: "timeline-meta" }, "Arbeitspaket: ", wpLink),
  ];

  return h(
    "li",
    { class: itemClasses.join(" ") },
    h(
      "article",
      { class: "timeline-card" },
      h(
        "div",
        { class: "timeline-head" },
        h(
          "h3",
          { class: "timeline-title" },
          h("span", { class: "timeline-code" }, milestone.code),
          " — ",
          h("span", {}, milestone.title),
        ),
        statusBadge(milestone.status),
      ),
      ...metaLines,
      milestone.note ? h("p", { class: "timeline-note" }, milestone.note) : null,
      linkedDocumentsSection(milestone, linkedDocs, !!milestone.can_edit, onLink, onChanged),
      milestone.can_edit
        ? h(
            "div",
            { class: "timeline-actions" },
            h(
              "button",
              {
                type: "button",
                class: "button-secondary button-compact",
                onclick: () => onEdit(milestone),
              },
              "Bearbeiten …",
            ),
          )
        : null,
    ),
  );
}

export async function render(container, _ctx) {
  container.classList.add("page-wide");
  const dialogContainer = h("div", {});
  const modalContainer = h("div", {});
  let modalKeyHandler = null;

  function clearDialog() {
    dialogContainer.replaceChildren();
  }

  function showDialog(title, body) {
    dialogContainer.replaceChildren(h("div", { class: "dialog" }, h("h3", {}, title), body));
  }

  function clearModal() {
    if (modalKeyHandler) {
      document.removeEventListener("keydown", modalKeyHandler);
      modalKeyHandler = null;
    }
    document.body.classList.remove("modal-open");
    modalContainer.replaceChildren();
  }

  function showModal(title, bodyEl) {
    const closeBtn = h(
      "button",
      { type: "button", class: "portal-modal-close", "aria-label": "Schließen" },
      "×",
    );
    closeBtn.addEventListener("click", clearModal);
    const dialog = h(
      "div",
      { class: "portal-modal", role: "dialog", "aria-modal": "true", "aria-label": title },
      h(
        "div",
        { class: "portal-modal-head" },
        h("h3", { class: "portal-modal-title" }, title),
        closeBtn,
      ),
      h("div", { class: "portal-modal-body" }, bodyEl),
    );
    const backdrop = h("div", { class: "portal-modal-backdrop" }, dialog);
    backdrop.addEventListener("click", (ev) => {
      if (ev.target === backdrop) clearModal();
    });
    modalKeyHandler = (ev) => {
      if (ev.key === "Escape") clearModal();
    };
    document.addEventListener("keydown", modalKeyHandler);
    document.body.classList.add("modal-open");
    modalContainer.replaceChildren(backdrop);
  }

  function header() {
    return [
      pageHeader(
        "Meilensteine",
        "Projekt-Meilensteine aus dem Antrag. Meilensteine mit Arbeitspaketbezug können von Admins und dem jeweiligen WP-Lead bearbeitet werden. Übergreifende Projektmeilensteine können nur von Admins bearbeitet werden.",
      ),
    ];
  }

  async function rerender() {
    container.replaceChildren(...header(), renderLoading("Meilensteine werden geladen …"));
    let milestones = [];
    let linksByMilestone = new Map();
    try {
      milestones = await api("GET", "/api/milestones");
      const linkResults = await Promise.all(
        milestones.map((ms) =>
          api("GET", `/api/milestones/${ms.id}/documents`).catch(() => []),
        ),
      );
      milestones.forEach((ms, i) => linksByMilestone.set(ms.id, linkResults[i] || []));
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

    async function onLink(ms, alreadyIds) {
      let documents = [];
      try {
        documents = await api("GET", "/api/documents");
      } catch (err) {
        alert(err.message);
        return;
      }
      showModal(
        `Dokument mit Meilenstein ${ms.code} verknüpfen`,
        renderLinkPicker(
          ms,
          documents,
          alreadyIds,
          () => {
            clearModal();
            rerender();
          },
          clearModal,
        ),
      );
    }

    function onChanged() {
      rerender();
    }

    // Sortiere Meilensteine nach Plandatum (aufsteigend) — das ergibt
    // einen lesbaren Projektverlauf von links/oben nach unten.
    const sorted = milestones
      .slice()
      .sort((a, b) => (a.planned_date || "").localeCompare(b.planned_date || ""));
    const body = sorted.length
      ? h(
          "ol",
          { class: "timeline" },
          ...sorted.map((ms) =>
            timelineItem(ms, linksByMilestone.get(ms.id) || [], onEdit, onLink, onChanged),
          ),
        )
      : renderRichEmpty(
          "Noch keine Meilensteine angelegt",
          "Meilensteine markieren wichtige Projekttermine. Sie kommen aus dem Antrag und " +
            "werden vom Admin oder vom WP-Lead des zugehörigen Arbeitspakets gepflegt.",
        );

    container.replaceChildren(
      ...header(),
      body,
      dialogContainer,
      modalContainer,
      crossNav("/portal/milestones"),
    );
  }

  await rerender();
}
