import { api, crossNav, h, renderEmpty, renderError, renderLoading } from "/portal/common.js";

function isAdmin(me) {
  return me?.person?.platform_role === "admin";
}

function showInitialPasswordDialog(container, password, onClose) {
  const codeBlock = h("code", { class: "initial-password" }, password);

  function copy() {
    navigator.clipboard?.writeText(password);
  }

  const dialog = h(
    "div",
    { class: "dialog" },
    h("h3", {}, "Initialpasswort"),
    h(
      "p",
      { class: "warning" },
      "Bitte sicher übermitteln — wird nicht erneut angezeigt.",
    ),
    codeBlock,
    h(
      "div",
      { class: "actions" },
      h("button", { type: "button", onclick: copy }, "In Zwischenablage kopieren"),
      h("button", { type: "button", onclick: onClose }, "Schließen"),
    ),
  );
  container.replaceChildren(dialog);
}

function renderCreateDialog(partners, onCreated, onError) {
  const emailInput = h("input", { type: "email", required: true });
  const nameInput = h("input", { type: "text", required: true });
  const partnerSelect = h(
    "select",
    {},
    ...partners.map((p) => h("option", { value: p.id }, `${p.short_name} — ${p.name}`)),
  );
  const roleSelect = h(
    "select",
    {},
    h("option", { value: "member", selected: true }, "Mitglied"),
    h("option", { value: "admin" }, "Admin"),
  );
  const passwordInput = h("input", {
    type: "text",
    placeholder: "(optional, mind. 10 Zeichen)",
    minlength: "10",
  });
  const passwordHelp = h(
    "small",
    { class: "field-hint" },
    "Optional. Wird leer gelassen, generiert der Server ein sicheres Initialpasswort.",
  );
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    const payload = {
      email: emailInput.value,
      display_name: nameInput.value,
      partner_id: partnerSelect.value,
      platform_role: roleSelect.value,
    };
    if (passwordInput.value) payload.initial_password = passwordInput.value;
    try {
      const created = await api("POST", "/api/admin/persons", payload);
      onCreated(created);
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
      onError?.(err);
    }
  }

  return h(
    "form",
    { class: "stacked", onsubmit: onSubmit },
    h("label", {}, "E-Mail", emailInput),
    h("label", {}, "Anzeigename", nameInput),
    h("label", {}, "Partner", partnerSelect),
    h("label", {}, "Plattformrolle", roleSelect),
    h(
      "label",
      {},
      "Initialpasswort (optional)",
      passwordInput,
      passwordHelp,
    ),
    errorBox,
    h("button", { type: "submit" }, "Anlegen"),
  );
}

function rowFor(person, navigate) {
  return h(
    "tr",
    {},
    h(
      "td",
      {},
      h("a", { href: `/portal/admin/users/${person.id}` }, person.display_name),
    ),
    h("td", {}, person.email),
    h("td", {}, person.partner.short_name),
    h("td", {}, person.platform_role === "admin" ? "Admin" : "Mitglied"),
    h(
      "td",
      {},
      h(
        "span",
        { class: person.is_active ? "badge badge-released" : "badge badge-draft" },
        person.is_active ? "aktiv" : "inaktiv",
      ),
    ),
    h(
      "td",
      {},
      person.must_change_password
        ? h("span", { class: "badge badge-review" }, "Passwort fällig")
        : "",
    ),
  );
}

export async function render(container, ctx) {
  if (!isAdmin(ctx.me)) {
    container.replaceChildren(h("h1", {}, "Personen"), renderError("Nur Admin."));
    return;
  }

  container.replaceChildren(
    h("h1", {}, "Personen"),
    renderLoading("Personen werden geladen …"),
  );

  let persons;
  let partners;
  try {
    [persons, partners] = await Promise.all([
      api("GET", "/api/admin/persons"),
      api("GET", "/api/admin/partners"),
    ]);
  } catch (err) {
    container.replaceChildren(h("h1", {}, "Personen"), renderError(err));
    return;
  }
  const activePartners = partners.filter((p) => !p.is_deleted);

  const tbody = h(
    "tbody",
    {},
    ...persons.map((p) => rowFor(p, ctx.navigate)),
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
        h("th", {}, "E-Mail"),
        h("th", {}, "Partner"),
        h("th", {}, "Rolle"),
        h("th", {}, "Status"),
        h("th", {}, ""),
      ),
    ),
    tbody,
  );

  const dialogContainer = h("div", {});

  function showCreateForm() {
    dialogContainer.replaceChildren(
      h(
        "div",
        { class: "dialog" },
        h("h3", {}, "Person anlegen"),
        renderCreateDialog(activePartners, (created) => {
          showInitialPasswordDialog(dialogContainer, created.initial_password, () => {
            window.location.href = `/portal/admin/users/${created.person.id}`;
          });
        }),
      ),
    );
  }

  const headerRow = h(
    "div",
    { class: "section-header" },
    h("h1", {}, "Personen"),
    h("button", { type: "button", onclick: showCreateForm }, "Person anlegen …"),
  );

  const body = persons.length
    ? table
    : renderEmpty("Es sind noch keine Personen angelegt.");

  container.replaceChildren(headerRow, body, dialogContainer, crossNav());
}
