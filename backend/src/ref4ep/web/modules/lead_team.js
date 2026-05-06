// „Mein Team" — Lead-Sicht für Personen der eigenen Organisation und
// für die eigenen Lead-Arbeitspakete (Block 0013 + UX-Polish).
//
// Aufbau (Desktop ≥ 960 px zwei Spalten, mobil einspaltig):
//   Linke Spalte:  Personen meiner Organisation (Tabelle + Anlegen)
//   Rechte Spalte: Meine Arbeitspakete als Karten-Grid mit
//                  kompakten Mitgliederzeilen, Rollen-Select und
//                  Add-/Remove-Aktionen.
//
// Filterung clientseitig:
//   - Suche Person (Name / E-Mail)
//   - Suche WP (Code / Titel)
//   - Optional: „Nur WPs mit mir als Lead" — siehe Hinweis im Code.
//
// Alle Aufrufe gehen gegen ``/api/lead/...``. Der Server erzwingt
// Berechtigungen — die UI vermeidet bewusst Begriffe wie „Admin"
// und bietet keine Auswahl der Plattformrolle oder einer anderen
// Organisation.

import {
  api,
  appendChildren,
  crossNav,
  h,
  pageHeader,
  renderEmpty,
  renderError,
  renderLoading,
  renderRichEmpty,
} from "/portal/common.js";

const WP_ROLE_LABELS = {
  wp_member: "Mitglied",
  wp_lead: "WP-Lead",
};

function nullIfBlank(value) {
  const v = (value || "").trim();
  return v === "" ? null : v;
}

function normalize(s) {
  return (s || "").toString().toLowerCase();
}

// ---- Initial-Passwort-Dialog -------------------------------------------

function showInitialPasswordDialog(slot, password, onClose) {
  const codeBlock = h("code", { class: "initial-password" }, password);
  function copy() {
    navigator.clipboard?.writeText(password);
  }
  slot.replaceChildren(
    h(
      "div",
      { class: "dialog" },
      h("h3", {}, "Initialpasswort"),
      h(
        "p",
        { class: "warning" },
        "Bitte sicher übermitteln. Dieses Passwort wird nicht erneut angezeigt.",
      ),
      codeBlock,
      h(
        "div",
        { class: "form-actions" },
        h(
          "button",
          { type: "button", class: "button-primary", onclick: copy },
          "In Zwischenablage kopieren",
        ),
        h(
          "button",
          { type: "button", class: "button-secondary", onclick: onClose },
          "Schließen",
        ),
      ),
    ),
  );
}

// ---- Person anlegen ----------------------------------------------------

function renderCreatePersonForm(onSaved, onCancel) {
  const emailInput = h("input", { type: "email", required: true });
  const nameInput = h("input", { type: "text", required: true });
  const passwordInput = h("input", {
    type: "text",
    placeholder: "(optional, mind. 10 Zeichen)",
    minlength: "10",
  });
  const passwordHelp = h(
    "small",
    { class: "field-hint" },
    "Optional. Wird das Feld leer gelassen, generiert der Server ein sicheres Initialpasswort.",
  );
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    const payload = {
      email: emailInput.value,
      display_name: nameInput.value,
    };
    const pw = nullIfBlank(passwordInput.value);
    if (pw) payload.initial_password = pw;
    try {
      const created = await api("POST", "/api/lead/persons", payload);
      onSaved(created);
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
      { class: "muted" },
      "Organisation und Plattformrolle werden serverseitig gesetzt — neue Personen werden automatisch deiner Organisation zugeordnet und sind reguläre Mitglieder.",
    ),
    h("label", {}, "E-Mail", emailInput),
    h("label", {}, "Anzeigename", nameInput),
    h("label", {}, "Initialpasswort", passwordInput, passwordHelp),
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit", class: "button-primary" }, "Anlegen"),
      h(
        "button",
        { type: "button", class: "button-secondary", onclick: onCancel },
        "Abbrechen",
      ),
    ),
  );
}

// ---- Personen-Tabelle (mit Suche) -------------------------------------

function renderPersonsTable(persons) {
  if (!persons.length) {
    return renderEmpty("Es sind keine Personen für deine Suche vorhanden.");
  }
  const rows = persons.map((p) =>
    h(
      "tr",
      {},
      h(
        "td",
        {},
        h("div", {}, p.display_name),
        h("div", { class: "lead-wp-member-email muted" }, p.email),
      ),
      h(
        "td",
        {},
        h(
          "span",
          { class: p.is_active ? "badge badge-released" : "badge badge-draft" },
          p.is_active ? "aktiv" : "inaktiv",
        ),
      ),
      h(
        "td",
        {},
        p.must_change_password
          ? h("span", { class: "badge badge-review" }, "Passwort fällig")
          : "",
      ),
    ),
  );
  return h(
    "table",
    {},
    h(
      "thead",
      {},
      h(
        "tr",
        {},
        h("th", {}, "Person"),
        h("th", {}, "Aktiv"),
        h("th", {}, ""),
      ),
    ),
    h("tbody", {}, ...rows),
  );
}

// ---- Mitglied-Add-Dialog (pro WP) -------------------------------------

function renderAddMemberForm(wp, partnerPersons, onSaved, onCancel) {
  const memberIds = new Set(wp.members.map((m) => m.person_id));
  const candidates = partnerPersons.filter((p) => !memberIds.has(p.id) && p.is_active);
  if (!candidates.length) {
    return h(
      "div",
      {},
      renderEmpty(
        "Alle aktiven Personen deines Partners sind bereits Mitglied dieses Arbeitspakets — leg gegebenenfalls erst eine neue Person an.",
      ),
      h(
        "div",
        { class: "form-actions" },
        h(
          "button",
          { type: "button", class: "button-secondary", onclick: onCancel },
          "Schließen",
        ),
      ),
    );
  }
  const personSelect = h(
    "select",
    {},
    ...candidates.map((p) =>
      h("option", { value: p.id }, `${p.display_name} <${p.email}>`),
    ),
  );
  const roleSelect = h(
    "select",
    {},
    h("option", { value: "wp_member", selected: "" }, WP_ROLE_LABELS.wp_member),
    h("option", { value: "wp_lead" }, WP_ROLE_LABELS.wp_lead),
  );
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    try {
      await api(
        "POST",
        `/api/lead/workpackages/${encodeURIComponent(wp.code)}/memberships`,
        { person_id: personSelect.value, wp_role: roleSelect.value },
      );
      onSaved();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    }
  }

  return h(
    "form",
    { class: "stacked", onsubmit: onSubmit },
    h("label", {}, "Person", personSelect),
    h("label", {}, "Rolle im WP", roleSelect),
    errorBox,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit", class: "button-primary" }, "Hinzufügen"),
      h(
        "button",
        { type: "button", class: "button-secondary", onclick: onCancel },
        "Abbrechen",
      ),
    ),
  );
}

// ---- WP-Karte mit Mitgliederzeilen ------------------------------------

function renderMemberRow(wp, member, onChangeRole, onRemove) {
  const roleSelect = h(
    "select",
    {},
    h(
      "option",
      { value: "wp_member", ...(member.wp_role === "wp_member" ? { selected: "" } : {}) },
      WP_ROLE_LABELS.wp_member,
    ),
    h(
      "option",
      { value: "wp_lead", ...(member.wp_role === "wp_lead" ? { selected: "" } : {}) },
      WP_ROLE_LABELS.wp_lead,
    ),
  );
  roleSelect.addEventListener("change", () => onChangeRole(member, roleSelect.value));
  return h(
    "li",
    { class: "lead-wp-member-row" },
    h(
      "div",
      { class: "lead-wp-member-name" },
      member.display_name,
      h("span", { class: "lead-wp-member-email" }, member.email),
    ),
    roleSelect,
    h(
      "div",
      { class: "lead-wp-member-actions" },
      h(
        "button",
        {
          type: "button",
          class: "button-danger button-compact",
          onclick: () => onRemove(member),
        },
        "Entfernen",
      ),
    ),
  );
}

function renderWorkpackageCard(wp, partnerPersons, dialogSlot, onChanged) {
  function clearDialog() {
    dialogSlot.replaceChildren();
  }
  function showDialog(title, body) {
    dialogSlot.replaceChildren(
      h("div", { class: "dialog" }, h("h3", {}, title), body),
    );
  }
  function onAdd() {
    showDialog(
      `Mitglied zu ${wp.code} hinzufügen`,
      renderAddMemberForm(
        wp,
        partnerPersons,
        () => {
          clearDialog();
          onChanged();
        },
        clearDialog,
      ),
    );
  }
  async function onChangeRole(member, newRole) {
    if (newRole === member.wp_role) return;
    try {
      await api(
        "PATCH",
        `/api/lead/workpackages/${encodeURIComponent(wp.code)}/memberships/${member.person_id}`,
        { wp_role: newRole },
      );
      onChanged();
    } catch (err) {
      alert(err.message);
      onChanged();
    }
  }
  async function onRemove(member) {
    if (
      !confirm(
        `Mitglied ${member.display_name} aus ${wp.code} entfernen? Die Person bleibt erhalten.`,
      )
    )
      return;
    try {
      await api(
        "DELETE",
        `/api/lead/workpackages/${encodeURIComponent(wp.code)}/memberships/${member.person_id}`,
      );
      onChanged();
    } catch (err) {
      alert(err.message);
    }
  }

  // Anzahl-Lead/Member als kleine Meta-Zeile.
  const leadsCount = wp.members.filter((m) => m.wp_role === "wp_lead").length;
  const membersCount = wp.members.length - leadsCount;

  const memberList = wp.members.length
    ? h(
        "ul",
        { class: "lead-wp-member-list" },
        ...wp.members.map((m) => renderMemberRow(wp, m, onChangeRole, onRemove)),
      )
    : h("p", { class: "muted" }, "Noch keine Mitglieder.");

  return h(
    "article",
    { class: "lead-wp-card" },
    h(
      "header",
      { class: "lead-wp-card-head" },
      h(
        "h3",
        { class: "lead-wp-card-title" },
        h("a", { href: `/portal/workpackages/${wp.code}` }, wp.code),
        " — ",
        h("span", {}, wp.title),
      ),
      h(
        "span",
        { class: "muted" },
        `${leadsCount} Lead · ${membersCount} Mitglied`,
      ),
    ),
    memberList,
    h(
      "div",
      { class: "lead-wp-card-footer" },
      h(
        "button",
        { type: "button", class: "button-primary button-compact", onclick: onAdd },
        "Mitglied hinzufügen …",
      ),
    ),
  );
}

// ---- Filter-Anwendung -------------------------------------------------

function filterPersons(persons, query) {
  const term = normalize(query);
  if (!term) return persons;
  return persons.filter(
    (p) => normalize(p.display_name).includes(term) || normalize(p.email).includes(term),
  );
}

function filterWorkpackages(wps, { query, mineLeadOnly, myEmail }) {
  const term = normalize(query);
  return wps.filter((wp) => {
    if (term && !(normalize(wp.code).includes(term) || normalize(wp.title).includes(term))) {
      return false;
    }
    if (mineLeadOnly && wp.my_role !== "wp_lead") {
      return false;
    }
    void myEmail; // (myEmail nicht nötig; my_role kommt vom Server)
    return true;
  });
}

// ---- Hauptrender ------------------------------------------------------

export async function render(container, ctx) {
  container.classList.add("page-wide");

  const partnerShort = ctx?.me?.person?.partner?.short_name || "";
  const personsHeadline = partnerShort
    ? `Personen bei ${partnerShort}`
    : "Personen meiner Organisation";
  const createDialogTitle = partnerShort
    ? `Person bei ${partnerShort} anlegen`
    : "Person für meine Organisation anlegen";

  const headerNodes = [
    pageHeader(
      "Mein Team",
      "Hier kannst du Personen deiner Organisation verwalten und sie deinen Arbeitspaketen zuordnen. Plattformrollen und andere Organisationen verwalten nur Admins.",
    ),
  ];

  appendChildren(
    container,
    ...headerNodes,
    renderLoading("Team-Daten werden geladen …"),
  );

  let partnerPersons;
  let leadWps;
  try {
    [partnerPersons, leadWps] = await Promise.all([
      api("GET", "/api/lead/persons"),
      api("GET", "/api/lead/workpackages"),
    ]);
  } catch (err) {
    appendChildren(container, ...headerNodes, renderError(err));
    return;
  }

  // Filter-Felder.
  const personSearch = h("input", {
    type: "search",
    placeholder: "Name oder E-Mail",
  });
  const wpSearch = h("input", {
    type: "search",
    placeholder: "Code oder Titel",
  });
  const mineLeadOnly = h("input", { type: "checkbox" });
  const resetBtn = h(
    "button",
    { type: "button", class: "button-secondary filter-reset" },
    "Zurücksetzen",
  );
  const filterBox = h(
    "fieldset",
    { class: "filterbox" },
    h("legend", {}, "Mein Team filtern"),
    h("label", {}, "Person suchen", personSearch),
    h("label", {}, "Arbeitspaket suchen", wpSearch),
    h(
      "label",
      { class: "checkbox-row" },
      mineLeadOnly,
      h("span", {}, "Nur WPs mit mir als Lead"),
    ),
    resetBtn,
  );

  // Personen-Sektion mit Anlage-Dialog.
  const personDialogSlot = h("div", {});
  function clearPersonDialog() {
    personDialogSlot.replaceChildren();
  }
  function openCreatePerson() {
    personDialogSlot.replaceChildren(
      h(
        "div",
        { class: "dialog" },
        h("h3", {}, createDialogTitle),
        renderCreatePersonForm((created) => {
          showInitialPasswordDialog(
            personDialogSlot,
            created.initial_password,
            () => {
              clearPersonDialog();
              render(container, ctx);
            },
          );
        }, clearPersonDialog),
      ),
    );
  }

  const personsHeading = h(
    "div",
    { class: "section-header" },
    h("h2", {}, personsHeadline),
    h(
      "button",
      { type: "button", class: "button-primary", onclick: openCreatePerson },
      "Person anlegen …",
    ),
  );

  const personsTableSlot = h("div", {}, renderPersonsTable(partnerPersons));

  const personsSection = h(
    "section",
    { class: "lead-team-persons" },
    personsHeading,
    personsTableSlot,
    personDialogSlot,
  );

  // WP-Karten.
  const wpDialogSlot = h("div", {});
  function rerender() {
    render(container, ctx);
  }
  const wpsGridSlot = h("div", { class: "lead-wp-grid" });

  function renderWpsGrid(filteredWps) {
    if (!leadWps.length) {
      return renderRichEmpty(
        "Du leitest aktuell kein Arbeitspaket",
        "Sobald dich ein Admin als WP-Lead einträgt, kannst du hier Mitglieder verwalten.",
      );
    }
    if (!filteredWps.length) {
      return renderRichEmpty(
        "Keine Arbeitspakete für die aktuelle Filterauswahl",
        "Passe die Suche an oder setze die Filter zurück.",
      );
    }
    return h(
      "div",
      { class: "lead-wp-grid" },
      ...filteredWps.map((wp) =>
        renderWorkpackageCard(wp, partnerPersons, wpDialogSlot, rerender),
      ),
    );
  }

  const wpsSection = h(
    "section",
    { class: "lead-team-wps" },
    h("h2", {}, "Meine Arbeitspakete"),
    wpsGridSlot,
    wpDialogSlot,
  );

  function applyFilters() {
    const filteredPersons = filterPersons(partnerPersons, personSearch.value);
    personsTableSlot.replaceChildren(renderPersonsTable(filteredPersons));
    const filteredWps = filterWorkpackages(leadWps, {
      query: wpSearch.value,
      mineLeadOnly: mineLeadOnly.checked,
    });
    wpsGridSlot.replaceChildren(renderWpsGrid(filteredWps));
  }

  personSearch.addEventListener("input", applyFilters);
  wpSearch.addEventListener("input", applyFilters);
  mineLeadOnly.addEventListener("change", applyFilters);
  resetBtn.addEventListener("click", () => {
    personSearch.value = "";
    wpSearch.value = "";
    mineLeadOnly.checked = false;
    applyFilters();
  });

  appendChildren(
    container,
    ...headerNodes,
    filterBox,
    h(
      "div",
      { class: "lead-team-layout" },
      personsSection,
      wpsSection,
    ),
    crossNav(),
  );
  applyFilters();
}
