import { api, h } from "/portal/common.js";

export async function render(container, ctx) {
  const code = ctx.params.code;
  const wp = await api("GET", `/api/workpackages/${encodeURIComponent(code)}`);

  const header = h(
    "div",
    {},
    h("h1", {}, `${wp.code} — ${wp.title}`),
    h("p", {}, `Lead-Partner: ${wp.lead_partner.name} (${wp.lead_partner.short_name})`),
    wp.parent
      ? h(
          "p",
          {},
          "Übergeordnet: ",
          h("a", { href: `/portal/workpackages/${wp.parent.code}` }, wp.parent.code),
          ` — ${wp.parent.title}`,
        )
      : null,
    wp.description ? h("p", {}, wp.description) : null,
  );

  const childrenSection =
    wp.children && wp.children.length
      ? h(
          "div",
          {},
          h("h2", {}, "Unterarbeitspakete"),
          h(
            "ul",
            {},
            ...wp.children.map((c) =>
              h(
                "li",
                {},
                h("a", { href: `/portal/workpackages/${c.code}` }, c.code),
                ` — ${c.title} (${c.lead_partner.short_name})`,
              ),
            ),
          ),
        )
      : null;

  const memberSection =
    wp.memberships && wp.memberships.length
      ? h(
          "div",
          {},
          h("h2", {}, "Mitglieder"),
          h(
            "ul",
            {},
            ...wp.memberships.map((m) =>
              h("li", {}, `${m.person_display_name} <${m.person_email}> (${m.wp_role})`),
            ),
          ),
        )
      : h("p", { class: "muted" }, "Noch keine Mitglieder eingetragen.");

  container.replaceChildren(header, childrenSection || h("div", {}), memberSection);
}
