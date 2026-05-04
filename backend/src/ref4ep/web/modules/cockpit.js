// Projekt-Cockpit (Block 0010).
//
// Begrüßung + persönliche WP-Liste (wie bisher) plus vier Karten mit
// projektweiten Aggregaten:
//   - Nächste Meilensteine
//   - Überfällige Meilensteine
//   - Offene Punkte aus Arbeitspaketen
//   - Arbeitspaket-Statusübersicht
//
// Aggregate kommen von ``GET /api/cockpit/project``.

import { api, crossNav, h, renderEmpty, renderError, renderLoading } from "/portal/common.js";

const WP_STATUS_LABELS = {
  planned: "geplant",
  in_progress: "in Arbeit",
  waiting_for_input: "wartet auf Input",
  critical: "kritisch",
  completed: "abgeschlossen",
};

const MS_STATUS_LABELS = {
  planned: "geplant",
  achieved: "erreicht",
  postponed: "verschoben",
  at_risk: "gefährdet",
  cancelled: "entfallen",
};

function formatDate(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

function statusBadge(status) {
  return h("span", { class: "badge" }, WP_STATUS_LABELS[status] || status);
}

function msStatusBadge(status) {
  return h("span", { class: "badge" }, MS_STATUS_LABELS[status] || status);
}

function dueLabel(daysToPlanned) {
  if (daysToPlanned === 0) return "heute";
  if (daysToPlanned === 1) return "morgen";
  if (daysToPlanned > 0) return `in ${daysToPlanned} Tagen`;
  if (daysToPlanned === -1) return "seit gestern überfällig";
  return `seit ${Math.abs(daysToPlanned)} Tagen überfällig`;
}

function wpLinkOrSpan(code, title) {
  if (!code) {
    return h("span", { class: "muted" }, "Gesamtprojekt");
  }
  return h("a", { href: `/portal/workpackages/${code}` }, `${code} — ${title}`);
}

function renderUpcomingCard(milestones) {
  if (!milestones.length) {
    return h(
      "section",
      { class: "cockpit-card" },
      h("h2", {}, "Nächste Meilensteine"),
      renderEmpty("Keine offenen Meilensteine in der Zukunft."),
    );
  }
  const items = milestones.map((ms) =>
    h(
      "li",
      {},
      h("strong", {}, ms.code),
      ` — ${ms.title}`,
      h("br", {}),
      `Plandatum: ${formatDate(ms.planned_date)} (${dueLabel(ms.days_to_planned)})`,
      h("br", {}),
      "WP: ",
      wpLinkOrSpan(ms.workpackage_code, ms.workpackage_title || ""),
      " · ",
      msStatusBadge(ms.status),
    ),
  );
  return h(
    "section",
    { class: "cockpit-card" },
    h("h2", {}, "Nächste Meilensteine"),
    h("ul", {}, ...items),
    h(
      "p",
      { class: "muted" },
      h("a", { href: "/portal/milestones" }, "Alle Meilensteine ansehen"),
    ),
  );
}

function renderOverdueCard(milestones) {
  if (!milestones.length) {
    return h(
      "section",
      { class: "cockpit-card" },
      h("h2", {}, "Überfällige Meilensteine"),
      renderEmpty("Keine überfälligen Meilensteine — gut so."),
    );
  }
  const items = milestones.map((ms) =>
    h(
      "li",
      {},
      h("strong", {}, ms.code),
      ` — ${ms.title}`,
      h("br", {}),
      `Plandatum: ${formatDate(ms.planned_date)} — ${dueLabel(ms.days_to_planned)}`,
      h("br", {}),
      "WP: ",
      wpLinkOrSpan(ms.workpackage_code, ms.workpackage_title || ""),
      " · ",
      msStatusBadge(ms.status),
    ),
  );
  return h(
    "section",
    { class: "cockpit-card danger" },
    h("h2", {}, "Überfällige Meilensteine"),
    h("ul", {}, ...items),
  );
}

function renderOpenIssuesCard(issues) {
  if (!issues.length) {
    return h(
      "section",
      { class: "cockpit-card" },
      h("h2", {}, "Offene Punkte aus Arbeitspaketen"),
      renderEmpty("Aktuell sind keine offenen Punkte in den Arbeitspaketen vermerkt."),
    );
  }
  const items = issues.map((issue) =>
    h(
      "li",
      {},
      h(
        "a",
        { href: `/portal/workpackages/${issue.code}` },
        `${issue.code} — ${issue.title}`,
      ),
      " · ",
      statusBadge(issue.status),
      h("br", {}),
      h("span", { class: "muted" }, "Offen: "),
      issue.open_issues,
      issue.next_steps
        ? [
            h("br", {}),
            h("span", { class: "muted" }, "Nächste Schritte: "),
            issue.next_steps,
          ]
        : null,
    ),
  );
  return h(
    "section",
    { class: "cockpit-card" },
    h("h2", {}, "Offene Punkte aus Arbeitspaketen"),
    h("ul", {}, ...items),
  );
}

function renderStatusOverviewCard(counts, overview) {
  // Counts oben als Reihe, Tabelle darunter.
  const countItems = Object.entries(WP_STATUS_LABELS).map(([key, label]) =>
    h("li", {}, h("strong", {}, String(counts[key] ?? 0)), label),
  );
  const rows = overview.map((entry) =>
    h(
      "tr",
      {},
      h(
        "td",
        {},
        h(
          "a",
          { href: `/portal/workpackages/${entry.code}` },
          entry.code,
        ),
      ),
      h("td", {}, entry.title),
      h("td", {}, statusBadge(entry.status)),
    ),
  );
  return h(
    "section",
    { class: "cockpit-card" },
    h("h2", {}, "Arbeitspaket-Statusübersicht"),
    h("ul", { class: "cockpit-status-counts" }, ...countItems),
    overview.length
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
              h("th", {}, "Status"),
            ),
          ),
          h("tbody", {}, ...rows),
        )
      : renderEmpty("Noch keine Arbeitspakete angelegt."),
  );
}

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
      "section",
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

  // Konsistenter Ladezustand: erst zeichnen, dann den Backend-Call abwarten.
  const dashboardSlot = h("div", {}, renderLoading("Cockpit-Daten werden geladen …"));
  const nav = crossNav("/portal/");
  container.replaceChildren(greeting, partnerLine, mySection, dashboardSlot, nav);

  let cockpit;
  try {
    cockpit = await api("GET", "/api/cockpit/project");
  } catch (err) {
    dashboardSlot.replaceChildren(
      renderError(`Cockpit konnte nicht geladen werden: ${err.message}`),
    );
    return;
  }

  const dashboard = h(
    "div",
    { class: "cockpit-grid" },
    renderUpcomingCard(cockpit.upcoming_milestones || []),
    renderOverdueCard(cockpit.overdue_milestones || []),
    renderOpenIssuesCard(cockpit.workpackages_with_open_issues || []),
    renderStatusOverviewCard(
      cockpit.status_counts || {},
      cockpit.workpackage_status_overview || [],
    ),
  );
  dashboardSlot.replaceChildren(dashboard);
}
