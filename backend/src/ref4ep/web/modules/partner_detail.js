// Partner-Detailseite für eingeloggte Personen.
//
// View / Edit der Stammdaten + Liste der Kontaktpersonen
// (Block 0007). Editierbar wenn ``can_edit`` (Admin oder
// WP-Lead des Partners). ``internal_note`` kommt nur für
// Admins über die API.

import { api, crossNav, h, renderEmpty, renderError, renderLoading } from "/portal/common.js";

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

function formatAddress(line, postal, city, country) {
  const parts = [line, [postal, city].filter(Boolean).join(" "), country]
    .filter((p) => p && p.trim())
    .join(", ");
  return parts || null;
}

function kvTable(...rows) {
  return h("table", { class: "kv" }, h("tbody", {}, ...rows));
}

function renderViewMode(partner) {
  const orgRows = [
    renderRow("Kürzel", partner.short_name),
    renderRow("Name der Organisation", partner.name),
    renderRow("Land", partner.country),
    renderRow(
      "Website",
      partner.website
        ? h("a", { href: partner.website, rel: "noopener noreferrer" }, partner.website)
        : null,
    ),
  ];
  const unitRows = [renderRow("Bearbeitende Einheit", partner.unit_name)];
  const orgAddrRows = [
    renderRow(
      "Adresse der Organisation",
      formatAddress(
        partner.organization_address_line,
        partner.organization_postal_code,
        partner.organization_city,
        partner.organization_country,
      ),
    ),
  ];
  const sameAddr = !!partner.unit_address_same_as_organization;
  const unitAddrRows = sameAddr
    ? [
        renderRow(
          "Adresse der bearbeitenden Einheit",
          h("span", { class: "muted" }, "identisch mit Organisationsadresse"),
        ),
      ]
    : [
        renderRow(
          "Adresse der bearbeitenden Einheit",
          formatAddress(
            partner.unit_address_line,
            partner.unit_postal_code,
            partner.unit_city,
            partner.unit_country,
          ),
        ),
      ];

  const sections = [
    h("section", {}, h("h3", {}, "Organisation"), kvTable(...orgRows)),
    h("section", {}, h("h3", {}, "Bearbeitende Einheit"), kvTable(...unitRows)),
    h("section", {}, h("h3", {}, "Adresse der Organisation"), kvTable(...orgAddrRows)),
    h(
      "section",
      {},
      h("h3", {}, "Adresse der bearbeitenden Einheit"),
      kvTable(...unitAddrRows),
    ),
  ];
  if (partner.internal_note !== null && partner.internal_note !== undefined) {
    sections.push(
      h(
        "section",
        {},
        h("h3", {}, "Verwaltung (nur Admin)"),
        kvTable(renderRow("Interne Notiz", partner.internal_note)),
      ),
    );
  }
  return h("div", { class: "partner-stamm-view" }, ...sections);
}

function renderEditForm(partner, onSaved, onCancel) {
  // Organisation
  const nameInput = h("input", { type: "text", value: partner.name || "", required: true });
  const websiteInput = h("input", {
    type: "url",
    value: partner.website || "",
    placeholder: "https://…",
  });
  // Bearbeitende Einheit
  const unitNameInput = h("input", { type: "text", value: partner.unit_name || "" });
  // Organisationsadresse
  const orgLineInput = h("input", {
    type: "text",
    value: partner.organization_address_line || "",
  });
  const orgPostalInput = h("input", {
    type: "text",
    value: partner.organization_postal_code || "",
  });
  const orgCityInput = h("input", { type: "text", value: partner.organization_city || "" });
  const orgCountryInput = h("input", {
    type: "text",
    value: partner.organization_country || "",
    minlength: "2",
    maxlength: "2",
    placeholder: "z. B. DE",
  });
  // Einheitsadresse + Toggle
  const sameAddressCheckbox = h("input", {
    type: "checkbox",
    ...(partner.unit_address_same_as_organization !== false ? { checked: "" } : {}),
  });
  const unitLineInput = h("input", { type: "text", value: partner.unit_address_line || "" });
  const unitPostalInput = h("input", { type: "text", value: partner.unit_postal_code || "" });
  const unitCityInput = h("input", { type: "text", value: partner.unit_city || "" });
  const unitCountryInput = h("input", {
    type: "text",
    value: partner.unit_country || "",
    minlength: "2",
    maxlength: "2",
    placeholder: "z. B. DE",
  });

  const unitAddressFieldset = h(
    "fieldset",
    { class: "form-group", id: "unit-address-fieldset" },
    h("legend", {}, "Adresse der bearbeitenden Einheit"),
    h("label", {}, "Straße / Hausnr.", unitLineInput),
    h("label", {}, "PLZ", unitPostalInput),
    h("label", {}, "Ort", unitCityInput),
    h("label", {}, "Land (ISO-3166-1 Alpha-2)", unitCountryInput),
  );

  function applySameAddressVisibility() {
    const same = sameAddressCheckbox.checked;
    unitAddressFieldset.style.display = same ? "none" : "";
    for (const inp of [unitLineInput, unitPostalInput, unitCityInput, unitCountryInput]) {
      inp.disabled = same;
    }
  }
  sameAddressCheckbox.addEventListener("change", applySameAddressVisibility);
  applySameAddressVisibility();

  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    const same = sameAddressCheckbox.checked;
    const payload = {
      name: nameInput.value,
      website: nullIfBlank(websiteInput.value),
      unit_name: nullIfBlank(unitNameInput.value),
      organization_address_line: nullIfBlank(orgLineInput.value),
      organization_postal_code: nullIfBlank(orgPostalInput.value),
      organization_city: nullIfBlank(orgCityInput.value),
      organization_country: nullIfBlank(orgCountryInput.value)?.toUpperCase() ?? null,
      unit_address_same_as_organization: same,
      unit_address_line: same ? null : nullIfBlank(unitLineInput.value),
      unit_postal_code: same ? null : nullIfBlank(unitPostalInput.value),
      unit_city: same ? null : nullIfBlank(unitCityInput.value),
      unit_country: same ? null : (nullIfBlank(unitCountryInput.value)?.toUpperCase() ?? null),
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
    h(
      "fieldset",
      { class: "form-group" },
      h("legend", {}, "Organisation"),
      h("label", {}, "Name der Organisation", nameInput),
      h("label", {}, "Website (optional)", websiteInput),
    ),
    h(
      "fieldset",
      { class: "form-group" },
      h("legend", {}, "Bearbeitende Einheit"),
      h("label", {}, "Institut / Arbeitsgruppe / Abteilung", unitNameInput),
    ),
    h(
      "fieldset",
      { class: "form-group" },
      h("legend", {}, "Adresse der Organisation"),
      h("label", {}, "Straße / Hausnr.", orgLineInput),
      h("label", {}, "PLZ", orgPostalInput),
      h("label", {}, "Ort", orgCityInput),
      h("label", {}, "Land (ISO-3166-1 Alpha-2)", orgCountryInput),
    ),
    h(
      "label",
      { class: "checkbox-row" },
      sameAddressCheckbox,
      h("span", {}, "Adresse der bearbeitenden Einheit ist identisch mit der Organisationsadresse"),
    ),
    unitAddressFieldset,
    h(
      "p",
      { class: "muted" },
      "Personenbezogene Angaben werden ausschließlich unter „Kontaktpersonen“ gepflegt.",
    ),
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
      wrapper.replaceChildren(h("h2", {}, "Kontaktpersonen"), renderError(err));
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
      : [renderEmpty("Noch keine Kontaktpersonen hinterlegt.")];

    wrapper.replaceChildren(heading, intro, ...cards, dialogContainer);
  }

  await reload();
}

export async function render(container, ctx) {
  container.classList.add("page-wide");
  const partnerId = ctx.params.id;
  container.replaceChildren(
    h("h1", {}, "Partner"),
    renderLoading("Partnerdaten werden geladen …"),
  );
  let partner;
  try {
    partner = await api("GET", `/api/partners/${partnerId}`);
  } catch (err) {
    container.replaceChildren(h("h1", {}, "Partner"), renderError(err));
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
    container.append(crossNav());
  }

  await rerender();
}
