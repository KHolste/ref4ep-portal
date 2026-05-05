// Zentrale Aufgabenübersicht (Block 0018).
//
// Tabelle aller MeetingAction-Einträge mit Filtern (Meine, offen,
// überfällig, Status, Arbeitspaket). Statusänderung direkt aus der
// Liste, wenn ``can_edit=true``.

import {
  api,
  crossNav,
  h,
  renderEmpty,
  renderError,
  renderLoading,
  renderRichEmpty,
} from "/portal/common.js";

const STATUS_LABELS = {
  open: "offen",
  in_progress: "in Arbeit",
  done: "erledigt",
  cancelled: "entfällt",
};

function formatDate(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

function isOverdue(action) {
  if (!action.due_date) return false;
  if (action.status === "done" || action.status === "cancelled") return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return new Date(action.due_date) < today;
}

function statusSelect(action, onChange) {
  const sel = h(
    "select",
    {},
    ...Object.entries(STATUS_LABELS).map(([v, l]) =>
      h("option", { value: v, ...(action.status === v ? { selected: "" } : {}) }, l),
    ),
  );
  sel.addEventListener("change", () => onChange(sel.value));
  return sel;
}

function rowFor(action, onChangeStatus) {
  const overdue = isOverdue(action);
  const dueCell = h("td", { class: overdue ? "error" : "" }, formatDate(action.due_date));
  const statusCell = action.can_edit
    ? h("td", {}, statusSelect(action, (v) => onChangeStatus(action, v)))
    : h("td", {}, h("span", { class: "badge" }, STATUS_LABELS[action.status] || action.status));
  return h(
    "tr",
    {},
    dueCell,
    statusCell,
    h("td", {}, action.text),
    h(
      "td",
      {},
      action.responsible_person?.display_name || h("span", { class: "muted" }, "—"),
    ),
    h("td", {}, action.workpackage_code || h("span", { class: "muted" }, "—")),
    h(
      "td",
      {},
      h(
        "a",
        { href: `/portal/meetings/${action.meeting_id}` },
        action.meeting_title,
      ),
    ),
  );
}

export async function render(container, _ctx) {
  container.classList.add("page-wide");
  const headerNodes = [
    h("h1", {}, "Aufgaben"),
    h(
      "p",
      { class: "muted" },
      "Aufgaben aus den Meeting-Protokollen — gefiltert nach Person, Status und Arbeitspaket.",
    ),
  ];

  const mineCheckbox = h("input", { type: "checkbox" });
  const overdueCheckbox = h("input", { type: "checkbox" });
  const statusFilter = h(
    "select",
    {},
    h("option", { value: "" }, "Alle Status"),
    ...Object.entries(STATUS_LABELS).map(([v, l]) => h("option", { value: v }, l)),
  );
  const wpFilter = h("input", {
    type: "text",
    placeholder: "WP-Code filtern, z. B. WP3.1",
  });
  const refreshBtn = h("button", { type: "button" }, "Filtern");

  const resetBtn = h(
    "button",
    { type: "button", class: "secondary filter-reset" },
    "Zurücksetzen",
  );
  const filterBox = h(
    "fieldset",
    { class: "meeting-filterbox filterbox" },
    h("legend", {}, "Aufgaben filtern"),
    h("label", { class: "checkbox-row" }, mineCheckbox, h("span", {}, "Meine Aufgaben")),
    h("label", { class: "checkbox-row" }, overdueCheckbox, h("span", {}, "Überfällig")),
    h("label", {}, "Status", statusFilter),
    h("label", {}, "Arbeitspaket", wpFilter),
    refreshBtn,
    resetBtn,
  );

  const tableSlot = h("div", {}, renderLoading("Aufgaben werden geladen …"));

  async function refresh() {
    tableSlot.replaceChildren(renderLoading("Aufgaben werden geladen …"));
    const params = new URLSearchParams();
    if (mineCheckbox.checked) params.set("mine", "true");
    if (overdueCheckbox.checked) params.set("overdue", "true");
    if (statusFilter.value) params.set("status", statusFilter.value);
    if (wpFilter.value.trim()) params.set("workpackage", wpFilter.value.trim());
    const url = `/api/actions${params.toString() ? "?" + params.toString() : ""}`;
    let actions;
    try {
      actions = await api("GET", url);
    } catch (err) {
      tableSlot.replaceChildren(renderError(err));
      return;
    }
    if (!actions.length) {
      const filtersActive =
        mineCheckbox.checked ||
        overdueCheckbox.checked ||
        statusFilter.value ||
        wpFilter.value.trim();
      if (filtersActive) {
        tableSlot.replaceChildren(
          renderRichEmpty(
            "Keine Aufgaben für die aktuelle Filterauswahl",
            "Passe Filter an oder setze sie zurück, um wieder alle Aufgaben zu sehen.",
          ),
        );
      } else {
        tableSlot.replaceChildren(
          renderRichEmpty(
            "Keine Aufgaben vorhanden",
            "Aufgaben entstehen aus Meeting-Protokollen und erscheinen hier, sobald sie " +
              "mit einer Frist oder verantwortlichen Person angelegt wurden.",
          ),
        );
      }
      return;
    }
    async function onChangeStatus(action, newStatus) {
      try {
        await api("PATCH", `/api/actions/${action.id}`, { status: newStatus });
        await refresh();
      } catch (err) {
        alert(err.message);
      }
    }
    const table = h(
      "table",
      {},
      h(
        "thead",
        {},
        h(
          "tr",
          {},
          h("th", {}, "Frist"),
          h("th", {}, "Status"),
          h("th", {}, "Aufgabe"),
          h("th", {}, "Verantwortlich"),
          h("th", {}, "WP"),
          h("th", {}, "Quelle / Meeting"),
        ),
      ),
      h("tbody", {}, ...actions.map((a) => rowFor(a, onChangeStatus))),
    );
    tableSlot.replaceChildren(table);
  }

  refreshBtn.addEventListener("click", refresh);
  resetBtn.addEventListener("click", () => {
    mineCheckbox.checked = false;
    overdueCheckbox.checked = false;
    statusFilter.value = "";
    wpFilter.value = "";
    refresh();
  });

  container.replaceChildren(...headerNodes, filterBox, tableSlot, crossNav());
  await refresh();
}
