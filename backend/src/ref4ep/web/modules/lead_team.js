// „Mein Team" — Lead-Sicht für Personen der eigenen Organisation und
// für die eigenen Lead-Arbeitspakete (Block 0013).
//
// Sektionen:
//   1. Personen meiner Organisation (lesen + anlegen)
//   2. Meine Arbeitspakete (Mitglieder hinzufügen/entfernen, Rolle ändern)
//
// Alle Aufrufe gehen gegen ``/api/lead/...``. Der Server erzwingt
// Berechtigungen — die UI vermeidet bewusst Begriffe wie „Admin"
// und bietet keine Auswahl der Plattformrolle oder einer anderen
// Organisation.

import { api, crossNav, h, renderEmpty, renderError, renderLoading } from "/portal/common.js";

const WP_ROLE_LABELS = {
  wp_member: "Mitglied",
  wp_lead: "WP-Lead",
};

function nullIfBlank(value) {
  const v = (value || "").trim();
  return v === "" ? null : v;
}

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
        h("button", { type: "button", onclick: copy }, "In Zwischenablage kopieren"),
        h("button", { type: "button", class: "secondary", onclick: onClose }, "Schließen"),
      ),
    ),
  );
}

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
      h("button", { type: "submit" }, "Anlegen"),
      h("button", { type: "button", class: "secondary", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

function renderPersonsTable(persons) {
  if (!persons.length) {
    return renderEmpty("Es sind noch keine Personen für deinen Partner angelegt.");
  }
  const rows = persons.map((p) =>
    h(
      "tr",
      {},
      h("td", {}, p.display_name),
      h("td", {}, p.email),
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
        h("th", {}, "Name"),
        h("th", {}, "E-Mail"),
        h("th", {}, "Aktiv?"),
        h("th", {}, ""),
      ),
    ),
    h("tbody", {}, ...rows),
  );
}

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
          { type: "button", class: "secondary", onclick: onCancel },
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
      h("button", { type: "submit" }, "Hinzufügen"),
      h("button", { type: "button", class: "secondary", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

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
    "tr",
    {},
    h("td", {}, member.display_name),
    h("td", {}, member.email),
    h("td", {}, roleSelect),
    h(
      "td",
      {},
      h(
        "button",
        { type: "button", class: "danger", onclick: () => onRemove(member) },
        "Entfernen",
      ),
    ),
  );
}

function renderWorkpackageBlock(wp, partnerPersons, dialogSlot, onChanged) {
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

  const heading = h(
    "div",
    { class: "section-header" },
    h(
      "h3",
      {},
      h("a", { href: `/portal/workpackages/${wp.code}` }, wp.code),
      ` — ${wp.title}`,
    ),
    h("button", { type: "button", onclick: onAdd }, "Mitglied hinzufügen …"),
  );

  const body = wp.members.length
    ? h(
        "table",
        {},
        h(
          "thead",
          {},
          h(
            "tr",
            {},
            h("th", {}, "Name"),
            h("th", {}, "E-Mail"),
            h("th", {}, "Rolle im WP"),
            h("th", {}, ""),
          ),
        ),
        h(
          "tbody",
          {},
          ...wp.members.map((m) => renderMemberRow(wp, m, onChangeRole, onRemove)),
        ),
      )
    : renderEmpty("Dieses Arbeitspaket hat noch keine Mitglieder.");

  return h("section", { class: "lead-wp-block" }, heading, body);
}

export async function render(container, ctx) {
  const partnerShort = ctx?.me?.person?.partner?.short_name || "";
  const personsHeadline = partnerShort
    ? `Personen bei ${partnerShort}`
    : "Personen meiner Organisation";
  const createDialogTitle = partnerShort
    ? `Person bei ${partnerShort} anlegen`
    : "Person für meine Organisation anlegen";

  const headerNodes = [
    h("h1", {}, "Mein Team"),
    h(
      "p",
      { class: "muted" },
      "Hier kannst du Personen deiner Organisation verwalten und sie deinen Arbeitspaketen zuordnen. Plattformrollen und andere Organisationen verwalten nur Admins.",
    ),
  ];

  container.replaceChildren(
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
    container.replaceChildren(...headerNodes, renderError(err));
    return;
  }

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
              // Nach Schließen frisch laden, damit die neue Person in der Liste auftaucht.
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
    h("button", { type: "button", onclick: openCreatePerson }, "Person anlegen …"),
  );
  const personsSection = h(
    "section",
    {},
    personsHeading,
    renderPersonsTable(partnerPersons),
    personDialogSlot,
  );

  // WP-Sektion: pro Lead-WP ein Block.
  const wpDialogSlot = h("div", {});
  function rerender() {
    render(container, ctx);
  }
  const wpsBody = leadWps.length
    ? leadWps.map((wp) =>
        renderWorkpackageBlock(wp, partnerPersons, wpDialogSlot, rerender),
      )
    : [
        renderEmpty(
          "Du leitest aktuell kein Arbeitspaket. Sobald dich ein Admin als WP-Lead einträgt, kannst du hier Mitglieder verwalten.",
        ),
      ];
  const wpsSection = h(
    "section",
    {},
    h("h2", {}, "Meine Arbeitspakete"),
    ...wpsBody,
    wpDialogSlot,
  );

  container.replaceChildren(
    ...headerNodes,
    personsSection,
    wpsSection,
    crossNav(),
  );
}
