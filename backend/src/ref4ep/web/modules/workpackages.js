import { api, crossNav, h, renderEmpty, renderError, renderLoading } from "/portal/common.js";

export async function render(container, _ctx) {
  const headerNodes = [h("h1", {}, "Arbeitspakete")];
  container.replaceChildren(...headerNodes, renderLoading("Arbeitspakete werden geladen …"));

  let wps;
  try {
    wps = await api("GET", "/api/workpackages");
  } catch (err) {
    container.replaceChildren(...headerNodes, renderError(err));
    return;
  }

  const body = wps.length
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
      )
    : renderEmpty("Noch keine Arbeitspakete angelegt.");

  container.replaceChildren(...headerNodes, body, crossNav("/portal/workpackages"));
}
