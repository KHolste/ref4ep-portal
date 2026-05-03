import { api, h } from "/portal/common.js";

function isAdmin(me) {
  return me?.person?.platform_role === "admin";
}

function reload() {
  window.location.reload();
}

function renderForm(initial, onSaved) {
  const shortInput = h("input", {
    type: "text",
    value: initial?.short_name || "",
    required: true,
  });
  const nameInput = h("input", {
    type: "text",
    value: initial?.name || "",
    required: true,
  });
  const countryInput = h("input", {
    type: "text",
    value: initial?.country || "",
    required: true,
    minlength: "2",
    maxlength: "2",
    placeholder: "z. B. DE",
  });
  const websiteInput = h("input", {
    type: "url",
    value: initial?.website || "",
    placeholder: "https://…",
  });
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    const payload = {
      short_name: shortInput.value,
      name: nameInput.value,
      country: countryInput.value.toUpperCase(),
      website: websiteInput.value || null,
    };
    try {
      if (initial?.id) {
        await api("PATCH", `/api/admin/partners/${initial.id}`, payload);
      } else {
        await api("POST", "/api/admin/partners", payload);
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
    h("label", {}, "Kürzel", shortInput),
    h("label", {}, "Name", nameInput),
    h("label", {}, "Land (ISO-3166-1 Alpha-2)", countryInput),
    h("label", {}, "Website (optional)", websiteInput),
    errorBox,
    h("button", { type: "submit" }, initial?.id ? "Speichern" : "Anlegen"),
  );
}

function rowFor(partner, onEdit, onDelete) {
  const cls = partner.is_deleted ? "muted" : "";
  return h(
    "tr",
    { class: cls },
    h("td", {}, partner.short_name),
    h("td", {}, partner.name),
    h("td", {}, partner.country),
    h(
      "td",
      {},
      partner.website
        ? h("a", { href: partner.website, rel: "noopener noreferrer" }, partner.website)
        : "—",
    ),
    h(
      "td",
      {},
      partner.is_deleted
        ? h("span", { class: "badge badge-draft" }, "soft-deleted")
        : h("span", { class: "badge badge-released" }, "aktiv"),
    ),
    h(
      "td",
      {},
      h("button", { type: "button", onclick: () => onEdit(partner) }, "Bearbeiten …"),
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
  if (!isAdmin(ctx.me)) {
    container.replaceChildren(h("h1", {}, "Partner"), h("p", { class: "error" }, "Nur Admin."));
    return;
  }

  const partners = await api("GET", "/api/admin/partners");
  const dialogContainer = h("div", {});

  function showDialog(title, body) {
    dialogContainer.replaceChildren(h("div", { class: "dialog" }, h("h3", {}, title), body));
  }

  function onEdit(partner) {
    showDialog("Partner bearbeiten", renderForm(partner, reload));
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

  const headerRow = h(
    "div",
    { class: "section-header" },
    h("h1", {}, "Partner"),
    h(
      "button",
      {
        type: "button",
        onclick: () => showDialog("Partner anlegen", renderForm(null, reload)),
      },
      "Partner anlegen …",
    ),
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
        h("th", {}, "Kürzel"),
        h("th", {}, "Name"),
        h("th", {}, "Land"),
        h("th", {}, "Website"),
        h("th", {}, "Status"),
        h("th", {}, ""),
      ),
    ),
    h("tbody", {}, ...partners.map((p) => rowFor(p, onEdit, onDelete))),
  );

  container.replaceChildren(headerRow, table, dialogContainer);
}
