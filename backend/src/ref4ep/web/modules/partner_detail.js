// Partner-Detailseite für eingeloggte Personen.
//
// Anzeigemodus für alle, Bearbeitungsmodus nur wenn ``can_edit``
// (Admin oder WP-Lead des Partners) — ``internal_note`` wird vom
// Backend nur Admins ausgeliefert.

import { api, h } from "/portal/common.js";

function nullIfBlank(value) {
  const v = (value || "").trim();
  return v === "" ? null : v;
}

function renderRow(label, value) {
  if (!value) {
    return h("tr", {}, h("th", {}, label), h("td", { class: "muted" }, "—"));
  }
  return h("tr", {}, h("th", {}, label), h("td", {}, value));
}

function renderViewMode(partner) {
  const rows = [
    renderRow("Kürzel", partner.short_name),
    renderRow("Land", partner.country),
    renderRow(
      "Website",
      partner.website
        ? h("a", { href: partner.website, rel: "noopener noreferrer" }, partner.website)
        : null,
    ),
    renderRow("Allgemeine E-Mail", partner.general_email),
    renderRow(
      "Postanschrift",
      [partner.address_line, [partner.postal_code, partner.city].filter(Boolean).join(" "), partner.address_country]
        .filter((p) => p && p.trim())
        .join(", ") || null,
    ),
    renderRow("Projektkontakt", partner.primary_contact_name),
    renderRow(
      "Kontakt-E-Mail",
      partner.contact_email
        ? h("a", { href: `mailto:${partner.contact_email}` }, partner.contact_email)
        : null,
    ),
    renderRow("Telefon", partner.contact_phone),
    renderRow("Rolle / Aufgabe im Projekt", partner.project_role_note),
  ];
  if (partner.internal_note !== null && partner.internal_note !== undefined) {
    rows.push(renderRow("Interne Notiz (nur Admin)", partner.internal_note));
  }
  return h("table", { class: "kv" }, h("tbody", {}, ...rows));
}

function renderEditForm(partner, onSaved, onCancel) {
  const nameInput = h("input", { type: "text", value: partner.name || "", required: true });
  const websiteInput = h("input", {
    type: "url",
    value: partner.website || "",
    placeholder: "https://…",
  });
  const generalEmailInput = h("input", {
    type: "email",
    value: partner.general_email || "",
  });
  const addressLineInput = h("input", { type: "text", value: partner.address_line || "" });
  const postalCodeInput = h("input", { type: "text", value: partner.postal_code || "" });
  const cityInput = h("input", { type: "text", value: partner.city || "" });
  const addressCountryInput = h("input", {
    type: "text",
    value: partner.address_country || "",
    minlength: "2",
    maxlength: "2",
    placeholder: "z. B. DE",
  });
  const primaryContactInput = h("input", {
    type: "text",
    value: partner.primary_contact_name || "",
  });
  const contactEmailInput = h("input", { type: "email", value: partner.contact_email || "" });
  const contactPhoneInput = h("input", { type: "text", value: partner.contact_phone || "" });
  const projectRoleInput = h("textarea", { rows: "3" }, partner.project_role_note || "");

  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    const payload = {
      name: nameInput.value,
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
    };
    try {
      await api("PATCH", `/api/partners/${partner.id}`, payload);
      onSaved();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    }
  }

  return h(
    "form",
    { class: "stacked", onsubmit: onSubmit },
    h("p", { class: "muted" }, "Kürzel und Land sind nicht editierbar — bitte beim Admin melden."),
    h("label", {}, "Name", nameInput),
    h("label", {}, "Website (optional)", websiteInput),
    h("label", {}, "Allgemeine E-Mail (optional)", generalEmailInput),
    h("h3", {}, "Postanschrift"),
    h("label", {}, "Straße / Hausnr.", addressLineInput),
    h("label", {}, "PLZ", postalCodeInput),
    h("label", {}, "Ort", cityInput),
    h("label", {}, "Land (ISO-3166-1 Alpha-2)", addressCountryInput),
    h("h3", {}, "Projektkontakt"),
    h("label", {}, "Name", primaryContactInput),
    h("label", {}, "E-Mail", contactEmailInput),
    h("label", {}, "Telefon", contactPhoneInput),
    h("label", {}, "Rolle / Aufgabe im Projekt", projectRoleInput),
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit" }, "Speichern"),
      h("button", { type: "button", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

export async function render(container, ctx) {
  const partnerId = ctx.params.id;
  let partner;
  try {
    partner = await api("GET", `/api/partners/${partnerId}`);
  } catch (err) {
    container.replaceChildren(
      h("h1", {}, "Partner"),
      h("p", { class: "error" }, err.message),
    );
    return;
  }

  let editing = false;

  function rerender() {
    const headerRow = h(
      "div",
      { class: "section-header" },
      h("h1", {}, partner.name),
      partner.can_edit && !editing
        ? h(
            "button",
            {
              type: "button",
              onclick: () => {
                editing = true;
                rerender();
              },
            },
            "Bearbeiten …",
          )
        : null,
    );

    const breadcrumbs = h(
      "p",
      { class: "muted" },
      h("a", { href: "/portal/" }, "Cockpit"),
      " · ",
      h("a", { href: "/portal/workpackages" }, "Arbeitspakete"),
    );

    const body = editing
      ? renderEditForm(
          partner,
          async () => {
            partner = await api("GET", `/api/partners/${partnerId}`);
            editing = false;
            rerender();
          },
          () => {
            editing = false;
            rerender();
          },
        )
      : renderViewMode(partner);

    container.replaceChildren(breadcrumbs, headerRow, body);
  }

  rerender();
}
