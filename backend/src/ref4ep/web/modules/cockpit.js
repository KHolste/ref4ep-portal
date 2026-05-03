import { h } from "/portal/common.js";

export async function render(container, ctx) {
  const me = ctx.me;
  const memberships = me.memberships || [];

  const greeting = h("h1", {}, `Willkommen, ${me.person.display_name}`);
  const partnerLine = h(
    "p",
    {},
    `Partner: ${me.person.partner.name} (${me.person.partner.short_name}) — `,
    h(
      "a",
      { href: `/portal/partners/${me.person.partner.id}` },
      "Stammdaten anzeigen / bearbeiten",
    ),
  );

  let mySection;
  if (memberships.length === 0) {
    mySection = h(
      "p",
      { class: "muted" },
      "Du bist noch keinem Arbeitspaket zugeordnet. Bitte einen Admin um Aufnahme.",
    );
  } else {
    mySection = h(
      "div",
      {},
      h("h2", {}, "Deine Arbeitspakete"),
      h(
        "ul",
        {},
        ...memberships.map((m) =>
          h(
            "li",
            {},
            h("a", { href: `/portal/workpackages/${m.workpackage_code}` }, m.workpackage_code),
            ` — ${m.workpackage_title} (${m.wp_role})`,
          ),
        ),
      ),
    );
  }

  const navHint = h(
    "p",
    { class: "muted" },
    "Alle Arbeitspakete des Konsortiums findest du unter ",
    h("a", { href: "/portal/workpackages" }, "Arbeitspakete"),
    ".",
  );

  container.replaceChildren(greeting, partnerLine, mySection, navHint);
}
