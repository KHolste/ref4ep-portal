// Globale Übersicht: alle für den Aufrufer sichtbaren Dokumentkommentare,
// gruppiert nach Dokument/Version. Filter: Status (offen/eingereicht).
// Soft-gelöschte Kommentare sind serverseitig bereits ausgefiltert.

import {
  api,
  crossNav,
  h,
  pageHeader,
  renderEmpty,
  renderError,
  renderLoading,
} from "/portal/common.js";

const STATUS_LABELS = {
  open: "offen",
  submitted: "eingereicht",
};

function fmtDateTime(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("de-DE");
}

function statusBadge(status) {
  return h(
    "span",
    { class: `badge badge-comment-${status}` },
    STATUS_LABELS[status] || status,
  );
}

function commentRow(comment) {
  const v = comment.document_version;
  return h(
    "tr",
    {},
    h(
      "td",
      {},
      h(
        "a",
        { href: `/portal/documents/${v.document_id}` },
        `Dok ${v.document_id.slice(0, 8)}…`,
      ),
      ` · v${v.version_number}`,
    ),
    h("td", {}, statusBadge(comment.status)),
    h("td", {}, comment.author.display_name),
    h("td", {}, fmtDateTime(comment.created_at)),
    h("td", {}, fmtDateTime(comment.submitted_at)),
    h("td", { class: "comment-text-cell" }, comment.text),
  );
}

function renderTable(comments) {
  if (!comments.length) {
    return renderEmpty("Keine Kommentare für die aktuelle Auswahl.");
  }
  return h(
    "table",
    {},
    h(
      "thead",
      {},
      h(
        "tr",
        {},
        h("th", {}, "Dokument · Version"),
        h("th", {}, "Status"),
        h("th", {}, "Autor"),
        h("th", {}, "Erstellt"),
        h("th", {}, "Eingereicht"),
        h("th", {}, "Text"),
      ),
    ),
    h("tbody", {}, ...comments.map(commentRow)),
  );
}

export async function render(container, _ctx) {
  container.replaceChildren(
    pageHeader("Dokumentkommentare", "Globale Übersicht aller sichtbaren Kommentare"),
    renderLoading("Kommentare werden geladen …"),
  );

  const statusSelect = h(
    "select",
    {},
    h("option", { value: "" }, "alle"),
    h("option", { value: "open" }, "offen"),
    h("option", { value: "submitted" }, "eingereicht"),
  );
  const tableContainer = h("div", {});
  const filterBar = h(
    "div",
    { class: "filter-bar" },
    h("label", {}, "Status: ", statusSelect),
  );

  async function reload() {
    tableContainer.replaceChildren(renderLoading("Kommentare werden geladen …"));
    try {
      const params = statusSelect.value ? `?status=${statusSelect.value}` : "";
      const comments = await api("GET", `/api/document-comments${params}`);
      tableContainer.replaceChildren(renderTable(comments));
    } catch (err) {
      tableContainer.replaceChildren(renderError(err));
    }
  }

  statusSelect.addEventListener("change", reload);

  container.replaceChildren(
    pageHeader("Dokumentkommentare", "Globale Übersicht aller sichtbaren Kommentare"),
    filterBar,
    tableContainer,
    crossNav(),
  );

  await reload();
}
