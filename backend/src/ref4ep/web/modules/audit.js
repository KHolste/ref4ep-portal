import { api, crossNav, h, pageHeader, renderError, renderLoading } from "/portal/common.js";

function row(entry) {
  const detailsBtn = h(
    "button",
    { type: "button", class: "linklike", "aria-expanded": "false" },
    "Details anzeigen",
  );
  const detailsBox = h("pre", { class: "audit-details", hidden: true });
  detailsBtn.addEventListener("click", () => {
    if (detailsBox.hidden) {
      detailsBox.textContent = JSON.stringify(entry.details, null, 2);
      detailsBox.hidden = false;
    } else {
      detailsBox.hidden = true;
    }
    detailsBtn.textContent = detailsBox.hidden ? "Details anzeigen" : "Details ausblenden";
    detailsBtn.setAttribute("aria-expanded", detailsBox.hidden ? "false" : "true");
  });
  const actor = entry.actor.email
    ? entry.actor.email
    : entry.actor.label || "(unbekannt)";
  return h(
    "tr",
    {},
    h("td", {}, new Date(entry.created_at).toLocaleString("de-DE")),
    h("td", {}, actor),
    h("td", {}, h("code", {}, entry.action)),
    h(
      "td",
      {},
      h("code", {}, entry.entity_type),
      " ",
      h("span", { class: "muted", title: entry.entity_id }, `${entry.entity_id.slice(0, 8)}…`),
    ),
    h("td", {}, detailsBtn, detailsBox),
  );
}

async function load(filters) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v) params.set(k, v);
  }
  const url = `/api/admin/audit${params.toString() ? "?" + params.toString() : ""}`;
  return api("GET", url);
}

export async function render(container, ctx) {
  container.classList.add("page-wide");
  if (ctx.me?.person?.platform_role !== "admin") {
    container.replaceChildren(pageHeader("Audit-Log"), renderError("Nur Admin."));
    return;
  }

  // Objektart und Aktion sind technische Schlüssel aus dem Protokoll —
  // die Beispiele zeigen, wie sie aussehen.
  const actorInput = h("input", { type: "text", placeholder: "name@beispiel.de" });
  const entityInput = h("input", { type: "text", placeholder: "z. B. document" });
  const actionInput = h("input", { type: "text", placeholder: "z. B. document.release" });
  const reload = h("button", { type: "submit", class: "button-primary" }, "Filtern");

  const tableBody = h("tbody", {});
  const table = h(
    "table",
    { class: "audit-table" },
    h(
      "thead",
      {},
      h(
        "tr",
        {},
        h("th", {}, "Zeit"),
        h("th", {}, "Wer"),
        h("th", {}, "Aktion"),
        h("th", {}, "Objekt"),
        h("th", {}, "Details"),
      ),
    ),
    tableBody,
  );

  // Status-Slot oberhalb der Tabelle: nimmt Loading- bzw. Fehlerzeile auf.
  const statusSlot = h("div", {});

  async function refresh() {
    statusSlot.replaceChildren(renderLoading("Audit-Einträge werden geladen …"));
    tableBody.replaceChildren();
    let items;
    try {
      items = await load({
        actor_email: actorInput.value || null,
        entity_type: entityInput.value || null,
        action: actionInput.value || null,
      });
    } catch (err) {
      statusSlot.replaceChildren(renderError(err));
      return;
    }
    statusSlot.replaceChildren();
    if (!items.length) {
      tableBody.append(
        h(
          "tr",
          {},
          h("td", { colspan: "5", class: "empty muted" }, "Keine Einträge für diese Filter."),
        ),
      );
    } else {
      for (const e of items) tableBody.append(row(e));
    }
  }


  container.replaceChildren(
    pageHeader(
      "Audit-Log",
      "Veränderungsprotokoll für Admin-Recherche — schreibgeschützt.",
    ),
    h(
      "form",
      {
        onsubmit: (ev) => {
          ev.preventDefault();
          refresh();
        },
      },
      h(
        "fieldset",
        { class: "audit-filterbox filterbox" },
        h("legend", {}, "Protokoll filtern"),
        h("label", {}, "Person (E-Mail)", actorInput),
        h("label", {}, "Objektart", entityInput),
        h("label", {}, "Aktion", actionInput),
        reload,
      ),
    ),
    statusSlot,
    table,
    crossNav(),
  );
  await refresh();
}
