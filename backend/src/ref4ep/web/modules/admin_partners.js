// Admin-Partnerverwaltung — Liste + Anlegen.
//
// Bearbeitung läuft über die Detailseite (Klick auf den Namen).
// Hier auf der Liste nur noch: Soft-Delete und Anlegen.

import {
  api,
  crossNav,
  h,
  pageHeader,
  renderEmpty,
  renderError,
  renderLoading,
} from "/portal/common.js";

function isAdmin(me) {
  return me?.person?.platform_role === "admin";
}

function reload() {
  window.location.reload();
}

function fieldsetGroup(legend, ...rows) {
  return h("fieldset", { class: "form-group" }, h("legend", {}, legend), ...rows);
}

function nullIfBlank(value) {
  const v = (value || "").trim();
  return v === "" ? null : v;
}

function renderCreateForm(onSaved, onCancel) {
  const shortInput = h("input", { type: "text", required: true });
  const nameInput = h("input", { type: "text", required: true });
  const countryInput = h("input", {
    type: "text",
    required: true,
    minlength: "2",
    maxlength: "2",
    placeholder: "z. B. DE",
  });
  const websiteInput = h("input", { type: "url", placeholder: "https://…" });
  const unitNameInput = h("input", {
    type: "text",
    placeholder: "z. B. I. Physikalisches Institut (optional)",
  });
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    try {
      await api("POST", "/api/admin/partners", {
        short_name: shortInput.value,
        name: nameInput.value,
        country: countryInput.value.toUpperCase(),
        website: nullIfBlank(websiteInput.value),
        unit_name: nullIfBlank(unitNameInput.value),
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
    fieldsetGroup(
      "Organisation",
      h("label", {}, "Kürzel", shortInput),
      h("label", {}, "Name der Organisation", nameInput),
      h("label", {}, "Land (ISO-3166-1 Alpha-2)", countryInput),
      h("label", {}, "Website (optional)", websiteInput),
    ),
    fieldsetGroup(
      "Bearbeitende Einheit (optional)",
      h("label", {}, "Institut / Arbeitsgruppe / Abteilung", unitNameInput),
    ),
    h(
      "p",
      { class: "muted" },
      "Adressen und Kontaktpersonen werden anschließend auf der Detailseite gepflegt.",
    ),
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit" }, "Anlegen"),
      h("button", { type: "button", class: "secondary", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

function rowFor(partner, onDelete) {
  const cls = partner.is_deleted ? "muted" : "";
  let statusBadge;
  if (partner.is_deleted) {
    statusBadge = h("span", { class: "badge badge-draft" }, "soft-deleted");
  } else if (!partner.is_active) {
    statusBadge = h("span", { class: "badge badge-draft" }, "inaktiv");
  } else {
    statusBadge = h("span", { class: "badge badge-released" }, "aktiv");
  }
  return h(
    "tr",
    { class: cls },
    h("td", {}, h("a", { href: `/portal/partners/${partner.id}` }, partner.name)),
    h("td", {}, partner.short_name),
    h("td", {}, partner.unit_name || h("span", { class: "muted" }, "—")),
    h("td", {}, partner.country),
    h(
      "td",
      {},
      partner.website
        ? h("a", { href: partner.website, rel: "noopener noreferrer" }, partner.website)
        : "—",
    ),
    h("td", {}, statusBadge),
    h(
      "td",
      {},
      partner.is_deleted
        ? null
        : h(
            "button",
            { type: "button", class: "danger", onclick: () => onDelete(partner) },
            "Soft-Delete …",
          ),
    ),
  );
}

export async function render(container, ctx) {
  container.classList.add("page-wide");
  if (!isAdmin(ctx.me)) {
    container.replaceChildren(pageHeader("Partner"), renderError("Nur Admin."));
    return;
  }

  container.replaceChildren(
    pageHeader(
      "Partner",
      "Partnerorganisationen des Konsortiums — Stammdaten und Kontaktpersonen pflegen Admins.",
    ),
    renderLoading("Partnerliste wird geladen …"),
  );
  let partners;
  try {
    partners = await api("GET", "/api/admin/partners");
  } catch (err) {
    container.replaceChildren(pageHeader("Partner"), renderError(err));
    return;
  }
  const dialogContainer = h("div", {});

  function clearDialog() {
    dialogContainer.replaceChildren();
  }

  function showDialog(title, body) {
    dialogContainer.replaceChildren(h("div", { class: "dialog" }, h("h3", {}, title), body));
  }

  async function onDelete(partner) {
    if (!confirm(`Partner ${partner.short_name} soft-löschen? (Reaktivierung nicht möglich)`))
      return;
    try {
      await api("DELETE", `/api/admin/partners/${partner.id}`);
      reload();
    } catch (err) {
      alert(err.message);
    }
  }

  const headerRow = pageHeader(
    "Partner",
    "Klick auf den Partnernamen öffnet die Detailseite — dort werden Stammdaten und Kontaktpersonen gepflegt.",
    {
      actions: h(
        "button",
        {
          type: "button",
          onclick: () => showDialog("Partner anlegen", renderCreateForm(reload, clearDialog)),
        },
        "Partner anlegen …",
      ),
    },
  );


  const table = h(
    "table",
    {},
    h(
      "thead",
      {},
      h(
        "tr",
        {},
        h("th", {}, "Name"),
        h("th", {}, "Kürzel"),
        h("th", {}, "Bearbeitende Einheit"),
        h("th", {}, "Land"),
        h("th", {}, "Website"),
        h("th", {}, "Status"),
        h("th", {}, ""),
      ),
    ),
    h("tbody", {}, ...partners.map((p) => rowFor(p, onDelete))),
  );

  const body = partners.length
    ? table
    : renderEmpty("Es sind noch keine Partner angelegt.");

  container.replaceChildren(headerRow, body, dialogContainer, crossNav());
}
