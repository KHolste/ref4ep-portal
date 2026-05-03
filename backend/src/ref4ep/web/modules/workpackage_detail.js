import { api, h } from "/portal/common.js";

const TYPE_LABELS = {
  deliverable: "Deliverable",
  report: "Report",
  note: "Notiz",
  other: "Sonstiges",
};

function renderDocumentsSection(wpCode, documents, onCreate) {
  const headerRow = h(
    "div",
    { class: "section-header" },
    h("h2", {}, "Dokumente"),
    h("button", { type: "button", onclick: onCreate }, "Neues Dokument"),
  );

  if (!documents.length) {
    return h(
      "section",
      {},
      headerRow,
      h(
        "p",
        { class: "muted" },
        "Noch keine Dokumente in diesem Arbeitspaket — leg das erste an.",
      ),
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
      h(
        "td",
        {},
        new Date(d.updated_at).toLocaleDateString("de-DE"),
      ),
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
  const codeInput = h("input", { type: "text", name: "deliverable_code" });

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
    h("label", {}, "Deliverable-Code (optional)", codeInput),
    errorBox,
    h("button", { type: "submit" }, "Anlegen"),
  );

  return h(
    "div",
    { class: "dialog" },
    h("h3", {}, "Neues Dokument"),
    form,
  );
}

export async function render(container, ctx) {
  const code = ctx.params.code;
  const [wp, documents] = await Promise.all([
    api("GET", `/api/workpackages/${encodeURIComponent(code)}`),
    api("GET", `/api/workpackages/${encodeURIComponent(code)}/documents`),
  ]);

  const header = h(
    "div",
    {},
    h("h1", {}, `${wp.code} — ${wp.title}`),
    h("p", {}, `Lead-Partner: ${wp.lead_partner.name} (${wp.lead_partner.short_name})`),
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
      : h("p", { class: "muted" }, "Noch keine Mitglieder eingetragen.");

  let dialogContainer = h("div", {});
  function openCreate() {
    dialogContainer.replaceChildren(
      openCreateDialog(code, (created) => {
        ctx.navigate(`/portal/documents/${created.id}`);
      }),
    );
  }

  const documentsSection = renderDocumentsSection(code, documents, openCreate);

  container.replaceChildren(
    header,
    childrenSection || h("div", {}),
    memberSection,
    documentsSection,
    dialogContainer,
  );
}
