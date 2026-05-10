// Partner-Detailseite für eingeloggte Personen.
//
// View / Edit der Stammdaten + Liste der Kontaktpersonen
// (Block 0007). Editierbar wenn ``can_edit`` (Admin oder
// WP-Lead des Partners). ``internal_note`` kommt nur für
// Admins über die API.

import {
  api,
  crossNav,
  effectivePlatformRole,
  h,
  pageHeader,
  renderEmpty,
  renderError,
  renderLoading,
} from "/portal/common.js";

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
        ? h(
            "span",
            {
              class: "badge badge-released",
              title:
                "Kontaktmarkierung — vergibt keine Login-/Portalrechte. " +
                "Echte Login-Projektleitung wird im Abschnitt „Projektleitung“ gepflegt.",
            },
            "Projektleitung (Kontakt)",
          )
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

// ---- Block 0044 — Partnerrollen (Projektleitung) -----------------------

function _formatDate(iso) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleDateString("de-DE");
  } catch {
    return iso;
  }
}

function _partnerRolesModal(modalContainer, title, bodyEl) {
  let keyHandler = null;
  function clear() {
    if (keyHandler) {
      document.removeEventListener("keydown", keyHandler);
      keyHandler = null;
    }
    document.body.classList.remove("modal-open");
    modalContainer.replaceChildren();
  }
  const closeBtn = h(
    "button",
    { type: "button", class: "portal-modal-close", "aria-label": "Schließen" },
    "×",
  );
  closeBtn.addEventListener("click", clear);
  const dialog = h(
    "div",
    { class: "portal-modal", role: "dialog", "aria-modal": "true", "aria-label": title },
    h(
      "div",
      { class: "portal-modal-head" },
      h("h3", { class: "portal-modal-title" }, title),
      closeBtn,
    ),
    h("div", { class: "portal-modal-body" }, bodyEl),
  );
  const backdrop = h("div", { class: "portal-modal-backdrop" }, dialog);
  backdrop.addEventListener("click", (ev) => {
    if (ev.target === backdrop) clear();
  });
  keyHandler = (ev) => {
    if (ev.key === "Escape") clear();
  };
  document.addEventListener("keydown", keyHandler);
  document.body.classList.add("modal-open");
  modalContainer.replaceChildren(backdrop);
  return clear;
}

function _renderAddPartnerLeadForm(partner, candidates, existingIds, onSaved, onCancel) {
  // Bevorzugt nur Personen, deren ``partner_id`` zum aktuellen Partner
  // passt — fachlich ist eine Projektleitung typischerweise jemand aus
  // dem eigenen Partner. Wenn das Backend keine partnerbezogene Filter-
  // Option mitliefert, filtern wir client-seitig.
  const filtered = candidates.filter(
    (p) => p.partner?.id === partner.id && !existingIds.has(p.id),
  );
  if (!filtered.length) {
    return h(
      "div",
      {},
      renderEmpty(
        "Keine wählbare Person verfügbar. Eine Person muss diesem Partner zugeordnet sein " +
          "und darf noch nicht als Projektleitung markiert sein.",
      ),
      h(
        "div",
        { class: "form-actions" },
        h("button", { type: "button", class: "secondary", onclick: onCancel }, "Schließen"),
      ),
    );
  }
  const personSelect = h(
    "select",
    {},
    ...filtered.map((p) =>
      h("option", { value: p.id }, `${p.display_name} <${p.email}>`),
    ),
  );
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    try {
      await api("POST", `/api/admin/partners/${partner.id}/roles`, {
        person_id: personSelect.value,
        role: "partner_lead",
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
    h(
      "p",
      { class: "muted small" },
      "Eine Projektleitung ist ein Login-Account mit partnerbezogener Verantwortung. " +
        "Die Rolle ist unabhängig von der Kontaktmarkierung „Projektleitung“ bei Partnerkontakten.",
    ),
    h("label", {}, "Person", personSelect),
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit" }, "Als Projektleitung benennen"),
      h("button", { type: "button", class: "secondary", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

function _renderPartnerLeadRow(partner, role, isAdmin, onChanged) {
  const since = _formatDate(role.created_at);
  const head = h(
    "div",
    { class: "partner-role-head" },
    h("h4", {}, role.person.display_name),
    h("span", { class: "badge badge-released" }, "Projektleitung"),
  );
  const meta = h(
    "div",
    { class: "partner-role-meta muted small" },
    h("a", { href: `mailto:${role.person.email}` }, role.person.email),
    since ? h("span", {}, ` · seit ${since}`) : null,
  );
  const actions = isAdmin
    ? h(
        "div",
        { class: "partner-role-actions" },
        h(
          "button",
          {
            type: "button",
            class: "button-secondary button-compact",
            onclick: async () => {
              if (
                !window.confirm(
                  `Projektleitung "${role.person.display_name}" wirklich entfernen?`,
                )
              )
                return;
              try {
                await api(
                  "DELETE",
                  `/api/admin/partners/${partner.id}/roles/${role.person.id}?role=partner_lead`,
                );
                onChanged();
              } catch (err) {
                alert(err.message);
              }
            },
          },
          "Entfernen",
        ),
      )
    : null;
  return h("div", { class: "partner-role-card" }, head, meta, actions);
}

async function renderPartnerRolesSection(partner, container, me) {
  const wrapper = h("section", { id: "partner-roles-section", class: "partner-roles" });
  const modalContainer = h("div", {});
  container.append(wrapper);
  container.append(modalContainer);

  const isAdmin = effectivePlatformRole(me?.person) === "admin";

  async function reload() {
    wrapper.replaceChildren(
      h("h2", {}, "Projektleitung"),
      renderLoading("Lade Projektleitungen …"),
    );
    let roles = [];
    try {
      // Nur Admins dürfen die Verwaltungs-API; für Nicht-Admins
      // zeigen wir die Sektion mit dem reinen Info-Inhalt.
      if (isAdmin) {
        roles = await api("GET", `/api/admin/partners/${partner.id}/roles`);
      }
    } catch (err) {
      wrapper.replaceChildren(h("h2", {}, "Projektleitung"), renderError(err));
      return;
    }

    const description = h(
      "p",
      { class: "muted" },
      "Projektleitungen sind Login-Accounts mit partnerbezogener Verantwortung. " +
        "Die Rolle ist unabhängig von der Kontaktmarkierung „Projektleitung“ bei Partnerkontakten.",
    );

    if (!isAdmin) {
      wrapper.replaceChildren(
        h("h2", {}, "Projektleitung"),
        description,
        renderEmpty(
          "Sichtbar nur für Admins (Pflege der Projektleitung erfolgt im Adminbereich).",
        ),
      );
      return;
    }

    const addBtn = h(
      "button",
      {
        type: "button",
        onclick: async () => {
          let candidates = [];
          try {
            candidates = await api("GET", "/api/admin/persons");
          } catch (err) {
            alert(err.message);
            return;
          }
          const existingIds = new Set(roles.map((r) => r.person.id));
          let clearModal;
          clearModal = _partnerRolesModal(
            modalContainer,
            `Projektleitung für ${partner.short_name} hinzufügen`,
            _renderAddPartnerLeadForm(
              partner,
              candidates,
              existingIds,
              () => {
                clearModal();
                reload();
              },
              () => clearModal(),
            ),
          );
        },
      },
      "Projektleitung hinzufügen …",
    );

    const head = h("h2", {}, "Projektleitung");
    const actions = h("div", { class: "actions" }, addBtn);

    let body;
    if (!roles.length) {
      body = h(
        "div",
        { class: "warning" },
        "Für diesen Partner ist noch keine Projektleitung benannt.",
      );
    } else {
      body = h(
        "div",
        { class: "partner-roles-list" },
        ...roles.map((r) => _renderPartnerLeadRow(partner, r, isAdmin, reload)),
      );
    }

    wrapper.replaceChildren(head, description, actions, body);
  }

  await reload();
}

export async function render(container, ctx) {
  container.classList.add("page-wide");
  const partnerId = ctx.params.id;
  container.replaceChildren(
    pageHeader("Partner"),
    renderLoading("Partnerdaten werden geladen …"),
  );
  let partner;
  let me = null;
  try {
    partner = await api("GET", `/api/partners/${partnerId}`);
    me = await api("GET", "/api/me");
  } catch (err) {
    container.replaceChildren(pageHeader("Partner"), renderError(err));
    return;
  }

  let editing = false;

  async function rerender() {
    const editBtn =
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
        : null;
    const headerRow = pageHeader(partner.name, null, { actions: editBtn });

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
      await renderPartnerRolesSection(partner, container, me);
    }
    container.append(crossNav());
  }

  await rerender();
}
