// Partner-Detailseite für eingeloggte Personen.
//
// View / Edit der Stammdaten + Liste der Kontaktpersonen
// (Block 0007). Editierbar wenn ``can_edit`` (Admin oder
// WP-Lead des Partners). ``internal_note`` kommt nur für
// Admins über die API.

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
    renderRow(
      "Postanschrift",
      [
        partner.address_line,
        [partner.postal_code, partner.city].filter(Boolean).join(" "),
        partner.address_country,
      ]
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
    h("h3", {}, "Postanschrift"),
    h("label", {}, "Straße / Hausnr.", addressLineInput),
    h("label", {}, "PLZ", postalCodeInput),
    h("label", {}, "Ort", cityInput),
    h("label", {}, "Land (ISO-3166-1 Alpha-2)", addressCountryInput),
    h("h3", {}, "Allgemeiner Projektkontakt"),
    h(
      "p",
      { class: "muted" },
      "Konkrete Personen werden weiter unten unter „Kontaktpersonen“ gepflegt.",
    ),
    h("label", {}, "Name", primaryContactInput),
    h("label", {}, "E-Mail", contactEmailInput),
    h("label", {}, "Telefon", contactPhoneInput),
    h("label", {}, "Rolle / Aufgabe im Projekt", projectRoleInput),
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit" }, "Speichern"),
      h("button", { type: "button", class: "secondary", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

// ---- Kontaktpersonen ---------------------------------------------------

function renderContactForm(initial, functions, onSaved, onCancel) {
  const isEdit = !!initial?.id;
  const nameInput = h("input", { type: "text", required: true, value: initial?.name || "" });
  const titleInput = h("input", { type: "text", value: initial?.title_or_degree || "" });
  const emailInput = h("input", { type: "email", value: initial?.email || "" });
  const phoneInput = h("input", { type: "text", value: initial?.phone || "" });
  const functionSelect = h(
    "select",
    {},
    h("option", { value: "" }, "— bitte wählen —"),
    ...functions.map((f) =>
      h(
        "option",
        { value: f, ...(initial?.function === f ? { selected: "" } : {}) },
        f,
      ),
    ),
  );
  const orgInput = h("input", { type: "text", value: initial?.organization_unit || "" });
  const wpNotesInput = h("textarea", { rows: "2" }, initial?.workpackage_notes || "");
  const primaryCheckbox = h("input", {
    type: "checkbox",
    ...(initial?.is_primary_contact ? { checked: "" } : {}),
  });
  const projectLeadCheckbox = h("input", {
    type: "checkbox",
    ...(initial?.is_project_lead ? { checked: "" } : {}),
  });
  const visibilitySelect = h(
    "select",
    {},
    h(
      "option",
      { value: "internal", ...(initial?.visibility !== "public" ? { selected: "" } : {}) },
      "intern (nur Konsortium)",
    ),
    h(
      "option",
      { value: "public", ...(initial?.visibility === "public" ? { selected: "" } : {}) },
      "öffentlich (vorbereitet, noch nicht ausgespielt)",
    ),
  );
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    const payload = {
      name: nameInput.value,
      title_or_degree: nullIfBlank(titleInput.value),
      email: nullIfBlank(emailInput.value),
      phone: nullIfBlank(phoneInput.value),
      function: nullIfBlank(functionSelect.value),
      organization_unit: nullIfBlank(orgInput.value),
      workpackage_notes: nullIfBlank(wpNotesInput.value),
      is_primary_contact: primaryCheckbox.checked,
      is_project_lead: projectLeadCheckbox.checked,
      visibility: visibilitySelect.value,
    };
    try {
      if (isEdit) {
        await api("PATCH", `/api/partner-contacts/${initial.id}`, payload);
      } else {
        await api("POST", `/api/partners/${initial.partner_id}/contacts`, payload);
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
    h("label", {}, "Name (Pflicht)", nameInput),
    h("label", {}, "Titel / akademischer Grad", titleInput),
    h("label", {}, "Funktion im Projekt", functionSelect),
    h("label", {}, "Organisationseinheit", orgInput),
    h("label", {}, "E-Mail", emailInput),
    h("label", {}, "Telefon", phoneInput),
    h("label", {}, "Hinweise zum Arbeitspaket-Bezug", wpNotesInput),
    h(
      "label",
      { class: "checkbox-row" },
      primaryCheckbox,
      h("span", {}, "Hauptkontakt"),
    ),
    h(
      "label",
      { class: "checkbox-row" },
      projectLeadCheckbox,
      h("span", {}, "Projektleitung"),
    ),
    h("label", {}, "Sichtbarkeit", visibilitySelect),
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit" }, isEdit ? "Speichern" : "Anlegen"),
      h("button", { type: "button", class: "secondary", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

function renderContactCard(contact, canManage, onEdit, onDeactivate, onReactivate) {
  const head = h(
    "div",
    { class: "contact-head" },
    h(
      "h4",
      {},
      contact.title_or_degree ? `${contact.title_or_degree} ${contact.name}` : contact.name,
    ),
    h(
      "div",
      {},
      contact.is_primary_contact
        ? h("span", { class: "badge badge-released" }, "Hauptkontakt")
        : null,
      contact.is_project_lead
        ? h("span", { class: "badge badge-released" }, "Projektleitung")
        : null,
      contact.is_active
        ? null
        : h("span", { class: "badge badge-draft" }, "inaktiv"),
    ),
  );

  const meta = h(
    "div",
    { class: "contact-meta" },
    contact.function ? h("div", {}, `Funktion: ${contact.function}`) : null,
    contact.organization_unit ? h("div", {}, `Organisation: ${contact.organization_unit}`) : null,
    contact.email
      ? h(
          "div",
          {},
          "E-Mail: ",
          h("a", { href: `mailto:${contact.email}` }, contact.email),
        )
      : null,
    contact.phone ? h("div", {}, `Telefon: ${contact.phone}`) : null,
    contact.workpackage_notes ? h("div", {}, `WP-Bezug: ${contact.workpackage_notes}`) : null,
    contact.internal_note !== null && contact.internal_note !== undefined
      ? h("div", { class: "warning" }, `Interne Notiz (nur Admin): ${contact.internal_note}`)
      : null,
  );

  const actions = canManage
    ? h(
        "div",
        { class: "contact-actions" },
        h("button", { type: "button", onclick: () => onEdit(contact) }, "Bearbeiten …"),
        contact.is_active
          ? h(
              "button",
              { type: "button", class: "danger", onclick: () => onDeactivate(contact) },
              "Deaktivieren",
            )
          : h(
              "button",
              { type: "button", onclick: () => onReactivate(contact) },
              "Reaktivieren",
            ),
      )
    : null;

  return h(
    "div",
    { class: `contact-card ${contact.is_active ? "" : "inactive"}` },
    head,
    meta,
    actions,
  );
}

async function renderContactsSection(partner, container) {
  const wrapper = h("section", { id: "contacts-section" });
  container.append(wrapper);

  async function reload() {
    let functions = [];
    let contacts = [];
    try {
      [contacts, functions] = await Promise.all([
        api(
          "GET",
          `/api/partners/${partner.id}/contacts${partner.can_edit ? "?include_inactive=true" : ""}`,
        ),
        partner.can_edit ? api("GET", "/api/partner-contacts/functions") : Promise.resolve([]),
      ]);
    } catch (err) {
      wrapper.replaceChildren(
        h("h2", {}, "Kontaktpersonen"),
        h("p", { class: "error" }, err.message),
      );
      return;
    }

    const dialogContainer = h("div", {});

    function clearDialog() {
      dialogContainer.replaceChildren();
    }

    function showDialog(title, body) {
      dialogContainer.replaceChildren(h("div", { class: "dialog" }, h("h3", {}, title), body));
    }

    function onCreate() {
      showDialog(
        "Kontaktperson anlegen",
        renderContactForm(
          { partner_id: partner.id },
          functions,
          () => {
            clearDialog();
            reload();
          },
          clearDialog,
        ),
      );
    }

    function onEdit(contact) {
      showDialog(
        "Kontaktperson bearbeiten",
        renderContactForm(
          contact,
          functions,
          () => {
            clearDialog();
            reload();
          },
          clearDialog,
        ),
      );
    }

    async function onDeactivate(contact) {
      if (!confirm(`Kontakt ${contact.name} deaktivieren? (kein Hard-Delete)`)) return;
      try {
        await api("DELETE", `/api/partner-contacts/${contact.id}`);
        reload();
      } catch (err) {
        alert(err.message);
      }
    }

    async function onReactivate(contact) {
      try {
        await api("POST", `/api/partner-contacts/${contact.id}/reactivate`, {});
        reload();
      } catch (err) {
        alert(err.message);
      }
    }

    const heading = h(
      "div",
      { class: "section-header" },
      h("h2", {}, "Kontaktpersonen"),
      partner.can_edit
        ? h("button", { type: "button", onclick: onCreate }, "Kontakt anlegen …")
        : null,
    );

    const intro = h(
      "p",
      { class: "muted" },
      "Konkrete Projektpersonen pro Partner — sichtbar für eingeloggte Konsortialmitglieder. " +
        "Eine eigene Person pro Funktion (Projektleitung, Postdoc, Verwaltung, …); deaktiviert statt gelöscht.",
    );

    const cards = contacts.length
      ? contacts.map((c) =>
          renderContactCard(c, partner.can_edit, onEdit, onDeactivate, onReactivate),
        )
      : [h("p", { class: "muted" }, "Noch keine Kontaktpersonen hinterlegt.")];

    wrapper.replaceChildren(heading, intro, ...cards, dialogContainer);
  }

  await reload();
}

export async function render(container, ctx) {
  const partnerId = ctx.params.id;
  let partner;
  try {
    partner = await api("GET", `/api/partners/${partnerId}`);
  } catch (err) {
    container.replaceChildren(h("h1", {}, "Partner"), h("p", { class: "error" }, err.message));
    return;
  }

  let editing = false;

  async function rerender() {
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
            "Stammdaten bearbeiten …",
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

    const stamm = editing
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

    container.replaceChildren(
      breadcrumbs,
      headerRow,
      h("section", {}, h("h2", {}, "Stammdaten"), stamm),
    );

    if (!editing) {
      await renderContactsSection(partner, container);
    }
  }

  await rerender();
}
