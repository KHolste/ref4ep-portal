import { api, h } from "/portal/common.js";

export async function render(container, ctx) {
  const me = ctx.me;
  const status = h("p", {}, "");

  function field(labelText, type, name) {
    const input = h("input", { type, name, required: true, minlength: name.includes("new") ? 10 : 1 });
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
    h("button", { type: "submit" }, "Passwort ändern"),
  );

  const profile = h(
    "section",
    {},
    h("h2", {}, "Profil"),
    h("p", {}, `Name: ${me.person.display_name}`),
    h("p", {}, `E-Mail: ${me.person.email}`),
    h(
      "p",
      {},
      `Partner: ${me.person.partner.name} (${me.person.partner.short_name})`,
    ),
    h("p", {}, `Rolle: ${me.person.platform_role}`),
  );

  const notice = me.person.must_change_password
    ? h(
        "p",
        { class: "warning" },
        "Du musst dein Passwort ändern, bevor du weitere Bereiche aufrufen kannst.",
      )
    : null;

  container.replaceChildren(
    h("h1", {}, "Konto"),
    notice || h("div", {}),
    profile,
    h("section", {}, h("h2", {}, "Passwort ändern"), form, status),
  );
}
