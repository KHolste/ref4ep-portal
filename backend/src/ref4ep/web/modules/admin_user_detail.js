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

function showInitialPassword(container, password, onClose) {
  const dialog = h(
    "div",
    { class: "dialog" },
    h("h3", {}, "Neues Initialpasswort"),
    h("p", { class: "warning" }, "Bitte sicher übermitteln — wird nicht erneut angezeigt."),
    h("code", { class: "initial-password" }, password),
    h(
      "div",
      { class: "actions" },
      h(
        "button",
        { type: "button", onclick: () => navigator.clipboard?.writeText(password) },
        "In Zwischenablage kopieren",
      ),
      h("button", { type: "button", onclick: onClose }, "Schließen"),
    ),
  );
  container.replaceChildren(dialog);
}

function renderEditDialog(person, partners, onSaved) {
  const nameInput = h("input", { type: "text", value: person.display_name, required: true });
  const partnerSelect = h(
    "select",
    {},
    ...partners
      .filter((p) => !p.is_deleted)
      .map((p) =>
        h(
          "option",
          { value: p.id, selected: p.id === person.partner.id ? true : null },
          `${p.short_name} — ${p.name}`,
        ),
      ),
  );
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    try {
      await api("PATCH", `/api/admin/persons/${person.id}`, {
        display_name: nameInput.value,
        partner_id: partnerSelect.value,
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
    h("label", {}, "Anzeigename", nameInput),
    h("label", {}, "Partner", partnerSelect),
    errorBox,
    h("button", { type: "submit" }, "Speichern"),
  );
}

function renderRoleDialog(person, onSaved) {
  const roleSelect = h(
    "select",
    {},
    h(
      "option",
      { value: "member", selected: person.platform_role === "member" ? true : null },
      "Mitglied",
    ),
    h(
      "option",
      { value: "admin", selected: person.platform_role === "admin" ? true : null },
      "Admin",
    ),
  );
  const errorBox = h("p", { class: "error", style: "display:none" }, "");
  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    try {
      await api("POST", `/api/admin/persons/${person.id}/set-role`, { role: roleSelect.value });
      onSaved();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    }
  }
  return h(
    "form",
    { class: "stacked", onsubmit: onSubmit },
    h("label", {}, "Plattformrolle", roleSelect),
    errorBox,
    h("button", { type: "submit" }, "Übernehmen"),
  );
}

function renderAddMembershipDialog(personId, workpackages, existingCodes, onAdded) {
  const wpSelect = h(
    "select",
    {},
    ...workpackages
      .filter((w) => !existingCodes.includes(w.code))
      .map((w) => h("option", { value: w.code }, `${w.code} — ${w.title}`)),
  );
  const roleSelect = h(
    "select",
    {},
    h("option", { value: "wp_member", selected: true }, "Mitglied"),
    h("option", { value: "wp_lead" }, "Lead"),
  );
  const errorBox = h("p", { class: "error", style: "display:none" }, "");
  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    if (!wpSelect.value) {
      errorBox.textContent = "Kein verbleibendes Arbeitspaket verfügbar.";
      errorBox.style.display = "";
      return;
    }
    try {
      await api("POST", `/api/admin/persons/${personId}/memberships`, {
        workpackage_code: wpSelect.value,
        wp_role: roleSelect.value,
      });
      onAdded();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    }
  }
  return h(
    "form",
    { class: "stacked", onsubmit: onSubmit },
    h("label", {}, "Arbeitspaket", wpSelect),
    h("label", {}, "WP-Rolle", roleSelect),
    errorBox,
    h("button", { type: "submit" }, "Hinzufügen"),
  );
}

function membershipRow(personId, m) {
  const roleSelect = h(
    "select",
    {},
    h("option", { value: "wp_member", selected: m.wp_role === "wp_member" ? true : null }, "Mitglied"),
    h("option", { value: "wp_lead", selected: m.wp_role === "wp_lead" ? true : null }, "Lead"),
  );
  const status = h("span", { class: "muted" }, "");
  async function changeRole() {
    if (roleSelect.value === m.wp_role) return;
    try {
      await api(
        "PATCH",
        `/api/admin/persons/${personId}/memberships/${m.workpackage_code}`,
        { wp_role: roleSelect.value },
      );
      status.textContent = "Rolle aktualisiert.";
      status.className = "success";
    } catch (err) {
      status.textContent = err.message;
      status.className = "error";
    }
  }
  roleSelect.addEventListener("change", changeRole);

  async function removeMembership() {
    if (!confirm(`Mitgliedschaft in ${m.workpackage_code} entfernen?`)) return;
    try {
      await api("DELETE", `/api/admin/persons/${personId}/memberships/${m.workpackage_code}`);
      reload();
    } catch (err) {
      alert(err.message);
    }
  }

  return h(
    "tr",
    {},
    h("td", {}, m.workpackage_code),
    h("td", {}, m.workpackage_title),
    h("td", {}, roleSelect, " ", status),
    h("td", {}, h("button", { type: "button", class: "danger", onclick: removeMembership }, "Entfernen")),
  );
}

export async function render(container, ctx) {
  container.classList.add("page-wide");
  if (!isAdmin(ctx.me)) {
    container.replaceChildren(pageHeader("Person"), renderError("Nur Admin."));
    return;
  }

  const personId = ctx.params.id;
  container.replaceChildren(
    pageHeader("Person"),
    renderLoading("Personendaten werden geladen …"),
  );
  let person;
  let partners;
  let workpackages;
  try {
    [person, partners, workpackages] = await Promise.all([
      api("GET", `/api/admin/persons/${personId}`),
      api("GET", "/api/admin/partners"),
      api("GET", "/api/workpackages"),
    ]);
  } catch (err) {
    container.replaceChildren(pageHeader("Person"), renderError(err));
    return;
  }

  const dialogContainer = h("div", {});

  function showDialog(title, body) {
    dialogContainer.replaceChildren(h("div", { class: "dialog" }, h("h3", {}, title), body));
  }

  const header = pageHeader(
    person.display_name,
    person.email,
    {
      meta: h(
        "span",
        {},
        `Partner: ${person.partner.short_name} · Plattformrolle: ${person.platform_role} · `,
        person.is_active ? "aktiv" : "inaktiv",
        person.must_change_password ? " · Passwort fällig" : "",
      ),
    },
  );

  const actions = [
    h(
      "button",
      {
        type: "button",
        onclick: () =>
          showDialog(
            "Person bearbeiten",
            renderEditDialog(person, partners, reload),
          ),
      },
      "Person bearbeiten …",
    ),
    h(
      "button",
      {
        type: "button",
        onclick: () =>
          showDialog("Plattformrolle ändern", renderRoleDialog(person, reload)),
      },
      "Plattformrolle ändern …",
    ),
    h(
      "button",
      {
        type: "button",
        onclick: async () => {
          if (!confirm("Passwort wirklich zurücksetzen?")) return;
          try {
            const result = await api(
              "POST",
              `/api/admin/persons/${personId}/reset-password`,
              {},
            );
            showInitialPassword(dialogContainer, result.initial_password, reload);
          } catch (err) {
            alert(err.message);
          }
        },
      },
      "Passwort zurücksetzen",
    ),
    person.is_active
      ? h(
          "button",
          {
            type: "button",
            class: "danger",
            onclick: async () => {
              if (!confirm("Person wirklich deaktivieren?")) return;
              await api("POST", `/api/admin/persons/${personId}/disable`, {});
              reload();
            },
          },
          "Deaktivieren",
        )
      : h(
          "button",
          {
            type: "button",
            onclick: async () => {
              await api("POST", `/api/admin/persons/${personId}/enable`, {});
              reload();
            },
          },
          "Aktivieren",
        ),
  ];

  const memberSection = h(
    "section",
    {},
    h(
      "div",
      { class: "section-header" },
      h("h2", {}, "WP-Mitgliedschaften"),
      h(
        "button",
        {
          type: "button",
          onclick: () =>
            showDialog(
              "Mitgliedschaft hinzufügen",
              renderAddMembershipDialog(
                personId,
                workpackages,
                person.memberships.map((m) => m.workpackage_code),
                reload,
              ),
            ),
        },
        "Mitgliedschaft hinzufügen …",
      ),
    ),
    person.memberships.length
      ? h(
          "table",
          {},
          h(
            "thead",
            {},
            h(
              "tr",
              {},
              h("th", {}, "Code"),
              h("th", {}, "Titel"),
              h("th", {}, "Rolle"),
              h("th", {}, ""),
            ),
          ),
          h(
            "tbody",
            {},
            ...person.memberships.map((m) => membershipRow(personId, m)),
          ),
        )
      : renderEmpty("Diese Person ist noch keinem Arbeitspaket zugeordnet."),
  );

  container.replaceChildren(
    header,
    h("div", { class: "actions" }, ...actions),
    memberSection,
    dialogContainer,
    crossNav(),
  );
}
