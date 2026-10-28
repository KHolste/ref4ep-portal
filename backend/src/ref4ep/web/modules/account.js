import { api, crossNav, h, pageHeader } from "/portal/common.js";

export async function render(container, ctx) {
  const me = ctx.me;
  const status = h("p", { role: "status" }, "");

  function field(labelText, type, name) {
    const input = h("input", {
      type,
      name,
      required: true,
      minlength: name.includes("new") ? 10 : 1,
    });
    return { input, label: h("label", {}, labelText, input) };
  }

  const oldPw = field("Aktuelles Passwort", "password", "old_password");
  const newPw = field("Neues Passwort (mind. 10 Zeichen)", "password", "new_password");
  const confirm = field("Bestätigung", "password", "confirm");

  async function onSubmit(ev) {
    ev.preventDefault();
    status.textContent = "";
    if (newPw.input.value !== confirm.input.value) {
      status.textContent = "Bestätigung stimmt nicht überein.";
      status.className = "error";
      return;
    }
    try {
      await api("POST", "/api/auth/password", {
        old_password: oldPw.input.value,
        new_password: newPw.input.value,
      });
      status.textContent = "Passwort geändert. Du wirst zur Anmeldung weitergeleitet …";
      status.className = "success";
      setTimeout(() => {
        window.location.href = "/login";
      }, 1500);
    } catch (err) {
      status.textContent = err.message;
      status.className = "error";
    }
  }

  const form = h(
    "form",
    { class: "stacked", onsubmit: onSubmit },
    oldPw.label,
    newPw.label,
    confirm.label,
    h(
      "div",
      { class: "form-actions" },
      h("button", { type: "submit" }, "Passwort ändern"),
    ),
  );

  // Wenn must_change_password gesetzt ist, expandieren wir die Sektion
  // automatisch. Sonst bleibt sie eingeklappt — die Kontoansicht öffnet
  // dann nur die Zeile „Neues Passwort festlegen".
  const mustChange = !!me.person.must_change_password;
  const passwordSection = h(
    "details",
    { class: "collapsible", id: "password-section", ...(mustChange ? { open: "" } : {}) },
    h("summary", { id: "password-toggle" }, "Neues Passwort festlegen"),
    form,
    status,
  );

  const ROLE_LABELS = { admin: "Administration", member: "Mitglied" };
  const facts = [
    ["Name", me.person.display_name],
    ["E-Mail", me.person.email],
    ["Partner", `${me.person.partner.name} (${me.person.partner.short_name})`],
    ["Rolle im Portal", ROLE_LABELS[me.person.platform_role] || me.person.platform_role],
  ];
  const profile = h(
    "section",
    { class: "section-card account-card" },
    h("h2", { class: "account-card-title" }, "Profil"),
    h(
      "dl",
      { class: "account-facts" },
      ...facts.flatMap(([label, value]) => [h("dt", {}, label), h("dd", {}, value)]),
    ),
    h(
      "p",
      { class: "muted account-hint" },
      "Änderungen an Name, E-Mail oder Partner nimmt die Administration vor.",
    ),
  );

  const notice = mustChange
    ? h(
        "p",
        { class: "warning" },
        "Du musst dein Passwort ändern, bevor du weitere Bereiche aufrufen kannst.",
      )
    : null;

  container.replaceChildren(
    pageHeader("Konto", "Profil und Passwortverwaltung."),
    notice || h("div", {}),
    profile,
    h(
      "section",
      { class: "section-card account-card" },
      h("h2", { class: "account-card-title" }, "Passwort"),
      passwordSection,
    ),
    crossNav(),
  );
}
