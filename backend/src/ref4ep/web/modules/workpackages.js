import { api, h } from "/portal/common.js";

export async function render(container, _ctx) {
  const wps = await api("GET", "/api/workpackages");

  const table = h(
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
        h("th", {}, "Parent"),
        h("th", {}, "Lead"),
      ),
    ),
    h(
      "tbody",
      {},
      ...wps.map((w) =>
        h(
          "tr",
          {},
          h("td", {}, h("a", { href: `/portal/workpackages/${w.code}` }, w.code)),
          h("td", {}, w.title),
          h("td", {}, w.parent_code || "—"),
          h("td", {}, w.lead_partner.short_name),
        ),
      ),
    ),
  );

  container.replaceChildren(h("h1", {}, "Arbeitspakete"), table);
}
