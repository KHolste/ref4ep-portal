import { api, h } from "/portal/common.js";

function isAdmin(me) {
  return me?.person?.platform_role === "admin";
}

function reload() {
  window.location.reload();
}

function fieldsetGroup(legend, ...rows) {
  return h("fieldset", { class: "form-group" }, h("legend", {}, legend), ...rows);
}

function renderForm(initial, onSaved) {
  const isEdit = !!initial?.id;

  // Identitätsfelder — beim Edit teilweise gesperrt (siehe MVP-Berechtigungen).
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
  const generalEmailInput = h("input", {
    type: "email",
    value: initial?.general_email || "",
    placeholder: "info@…",
  });

  const addressLineInput = h("input", { type: "text", value: initial?.address_line || "" });
  const postalCodeInput = h("input", { type: "text", value: initial?.postal_code || "" });
  const cityInput = h("input", { type: "text", value: initial?.city || "" });
  const addressCountryInput = h("input", {
    type: "text",
    value: initial?.address_country || "",
    minlength: "2",
    maxlength: "2",
    placeholder: "z. B. DE",
  });

  const primaryContactInput = h("input", {
    type: "text",
    value: initial?.primary_contact_name || "",
  });
  const contactEmailInput = h("input", {
    type: "email",
    value: initial?.contact_email || "",
  });
  const contactPhoneInput = h("input", {
    type: "text",
    value: initial?.contact_phone || "",
  });
  const projectRoleInput = h("textarea", { rows: "3" }, initial?.project_role_note || "");

  const isActiveCheckbox = h("input", {
    type: "checkbox",
    ...(initial?.is_active !== false ? { checked: true } : {}),
  });
  const internalNoteInput = h("textarea", { rows: "3" }, initial?.internal_note || "");

  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  function nullIfBlank(value) {
    const v = (value || "").trim();
    return v === "" ? null : v;
  }

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    const payload = {
      short_name: shortInput.value,
      name: nameInput.value,
      country: countryInput.value.toUpperCase(),
      website: nullIfBlank(websiteInput.value),
      general_email: nullIfBlank(generalEmailInput.value),
      address_line: nullIfBlank(addressLineInput.value),
      postal_code: nullIfBlank(postalCodeInput.value),
      city: nullIfBlank(cityInput.value),
      address_country: nullIfBlank(addressCountryInput.value)?.toUpperCase() ?? null,
      primary_contact_name: nullIfBlank(primaryContactInput.value),
      contact_email: nullIfBlank(contactEmailInput.value),
      contact_phone: nullIfBlank(contactPhoneInput.value),
      project_role_note: nullIfBlank(projectRoleInput.value),
      is_active: isActiveCheckbox.checked,
      internal_note: nullIfBlank(internalNoteInput.value),
    };
    try {
      if (isEdit) {
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
    fieldsetGroup(
      "Stammdaten",
      h("label", {}, "Kürzel", shortInput),
      h("label", {}, "Name", nameInput),
      h("label", {}, "Land (ISO-3166-1 Alpha-2)", countryInput),
      h("label", {}, "Website (optional)", websiteInput),
      h("label", {}, "Allgemeine E-Mail (optional)", generalEmailInput),
    ),
    fieldsetGroup(
      "Postanschrift",
      h("label", {}, "Straße / Hausnr.", addressLineInput),
      h("label", {}, "PLZ", postalCodeInput),
      h("label", {}, "Ort", cityInput),
      h("label", {}, "Land (ISO-3166-1 Alpha-2)", addressCountryInput),
    ),
    fieldsetGroup(
      "Projektkontakt",
      h("label", {}, "Name", primaryContactInput),
      h("label", {}, "E-Mail", contactEmailInput),
      h("label", {}, "Telefon", contactPhoneInput),
      h("label", {}, "Rolle / Aufgabe im Projekt", projectRoleInput),
    ),
    fieldsetGroup(
      "Verwaltung (nur Admin)",
      h("label", { class: "checkbox" }, isActiveCheckbox, " Im Projekt aktiv"),
      h("label", {}, "Interne Notiz", internalNoteInput),
    ),
    errorBox,
    h("button", { type: "submit" }, isEdit ? "Speichern" : "Anlegen"),
  );
}

function rowFor(partner, onEdit, onDelete) {
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
    h("td", {}, statusBadge),
    h(
      "td",
      {},
      h("a", { href: `/portal/partners/${partner.id}` }, "Detail"),
      " · ",
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
