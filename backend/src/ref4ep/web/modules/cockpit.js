// Projekt-Cockpit (Block 0010 + 0018 + Folge-UX-Pass).
//
// Aufbau:
//   1. Begrüßung + Partnerzeile
//   2. KPI-Streifen („Zahlen auf einen Blick")
//   3. „Mein Bereich"   (Member-/User-Ansicht oben, Admin unten)
//   4. Aktivitätsbox    („Seit deinem letzten Besuch")
//   5. Projekt-Cockpit  (verdichtet: nur Problem-WPs, nur Top-N Issues)
//
// Datenquellen:
//   GET /api/cockpit/me      — persönliche Sicht (Block 0018)
//   GET /api/cockpit/project — Projekt-Aggregat (Block 0010)
//   GET /api/activity/recent — Aktivitätsstrom (Block 0018)

import {
  api,
  crossNav,
  effectivePlatformRole,
  getLastSeenAt,
  h,
  markSeenNow,
  pageHeader,
  renderEmpty,
  renderError,
  renderLoading,
} from "/portal/common.js";

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

const MEETING_STATUS_LABELS = {
  planned: "geplant",
  held: "durchgeführt",
  minutes_draft: "Protokoll in Arbeit",
  minutes_approved: "Protokoll abgestimmt",
  completed: "abgeschlossen",
  cancelled: "abgesagt",
};

// Status, die wir in der verdichteten Übersicht als „aufmerksamkeitsbedürftig"
// behandeln und mit einer Mini-Tabelle beilegen.
const PROBLEM_WP_STATUSES = new Set(["critical", "waiting_for_input", "in_progress"]);

const MY_WP_LIMIT = 5;
const OPEN_ISSUE_LIMIT = 5;

function formatDate(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

function formatDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("de-DE", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
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

// ---- KPI-Streifen ------------------------------------------------------
//
// Tönung (``tone``):
//   - ``"danger"``  — echte Problemfälle (überfällig, kritisch).
//   - ``"warning"`` — informativer Hinweis (z. B. WPs mit offenen Punkten —
//                     normaler Arbeitsstand, aber gut zu wissen).
//   - undefined     — neutral (Zahlen, die selten alarmieren sollen).
//
// Klickbare Kacheln werden als ``<a>`` gerendert und tragen zusätzlich die
// Klasse ``cockpit-kpi-link`` (für Hover/Focus/Cursor + dezenten Pfeil).

function renderKpiTile({ value, label, href, tone }) {
  const classes = ["cockpit-kpi"];
  if (tone === "danger") classes.push("cockpit-kpi-danger");
  if (tone === "warning") classes.push("cockpit-kpi-warning");
  if (href) classes.push("cockpit-kpi-link");
  const valueNode = h("div", { class: "cockpit-kpi-value" }, String(value));
  const labelNode = h("div", { class: "cockpit-kpi-label" }, label);
  if (href) {
    return h(
      "a",
      { class: classes.join(" "), href, "aria-label": `${label}: ${value} — Anzeigen` },
      valueNode,
      labelNode,
      h("span", { class: "cockpit-kpi-cta", "aria-hidden": "true" }, "Anzeigen →"),
    );
  }
  return h("div", { class: classes.join(" ") }, valueNode, labelNode);
}

function renderKpiStrip(myCockpit, projectCockpit) {
  // Beide Quellen können fehlen — wir füllen mit 0.
  const my = myCockpit || {};
  const proj = projectCockpit || {};
  const overdueActions = (my.my_overdue_actions || []).length;
  const openActions = (my.my_open_actions || []).length;
  const nextMeetings = (my.my_next_meetings || []).length;
  const overdueMs = (proj.overdue_milestones || []).length;
  const wpsWithIssues = (proj.workpackages_with_open_issues || []).length;
  return h(
    "section",
    { class: "cockpit-kpi-strip", "aria-label": "Zahlen auf einen Blick" },
    renderKpiTile({
      value: overdueActions,
      label: "Überfällige Aufgaben",
      href: "/portal/actions?overdue=true",
      // Echter Problemfall — eskaliert auch farblich.
      tone: overdueActions > 0 ? "danger" : undefined,
    }),
    renderKpiTile({
      value: openActions,
      label: "Offene Aufgaben",
      href: "/portal/actions?mine=true",
      // Bewusst neutral — offene Aufgaben sind Normalbetrieb.
    }),
    renderKpiTile({
      value: nextMeetings,
      label: "Nächste Meetings",
      href: "/portal/meetings",
    }),
    renderKpiTile({
      value: overdueMs,
      label: "Überfällige Meilensteine",
      href: "/portal/milestones",
      tone: overdueMs > 0 ? "danger" : undefined,
    }),
    renderKpiTile({
      value: wpsWithIssues,
      label: "WPs mit offenen Punkten",
      href: "/portal/workpackages",
      // Hinweisfarbe (warning), kein „danger" — offene Punkte sind oft
      // normaler Arbeitsstand und sollen nicht rot wirken.
      tone: wpsWithIssues > 0 ? "warning" : undefined,
    }),
  );
}

// ---- „Mein Bereich" — kompakt -----------------------------------------

function roleBadge(wpRole) {
  // Rolle als kleines Badge — visuell konsistent mit anderen Badges.
  if (wpRole === "wp_lead") {
    return h("span", { class: "badge badge-lead" }, "Lead");
  }
  return h("span", { class: "badge badge-member" }, "Member");
}

function renderMyWpRows(workpackages) {
  // Eine kompakte Tabellenzeile pro WP — Code/Titel/Rolle. Lange Titel
  // brechen über die ``my-wp-title``-Klasse sauber um.
  return workpackages.map((wp) =>
    h(
      "tr",
      {},
      h(
        "td",
        { class: "my-wp-code" },
        h("a", { href: `/portal/workpackages/${wp.code}` }, wp.code),
      ),
      h("td", { class: "my-wp-title" }, wp.title),
      h("td", { class: "my-wp-role" }, roleBadge(wp.wp_role)),
    ),
  );
}

function renderMyWpTable(workpackages) {
  return h(
    "table",
    { class: "my-wp-table" },
    h(
      "thead",
      {},
      h(
        "tr",
        {},
        h("th", {}, "Code"),
        h("th", {}, "Titel"),
        h("th", {}, "Rolle"),
      ),
    ),
    h("tbody", {}, ...renderMyWpRows(workpackages)),
  );
}

function renderMyWpCard(myCockpit) {
  const lead = myCockpit.my_lead_workpackages || [];
  const all = myCockpit.my_workpackages || [];
  const memberCount = Math.max(all.length - lead.length, 0);

  // Lead-WPs zuerst anzeigen, danach reine Member-WPs — Duplikate per Code raus.
  const seen = new Set();
  const ordered = [];
  for (const wp of [...lead, ...all]) {
    if (seen.has(wp.code)) continue;
    seen.add(wp.code);
    ordered.push(wp);
  }

  const counts = h(
    "p",
    { class: "muted my-wp-counts" },
    `${lead.length} Lead · ${memberCount} Member`,
  );

  if (!ordered.length) {
    return h(
      "section",
      { class: "my-area-card" },
      h("h3", {}, "Meine Arbeitspakete"),
      counts,
      renderEmpty("Du bist noch keinem Arbeitspaket zugeordnet."),
    );
  }

  const visible = ordered.slice(0, MY_WP_LIMIT);
  const remaining = ordered.slice(MY_WP_LIMIT);
  const visibleTable = renderMyWpTable(visible);
  const moreBlock =
    remaining.length > 0
      ? h(
          "details",
          { class: "my-wp-more" },
          h("summary", {}, `+ ${remaining.length} weitere anzeigen`),
          renderMyWpTable(remaining),
        )
      : null;

  return h(
    "section",
    { class: "my-area-card" },
    h("h3", {}, "Meine Arbeitspakete"),
    counts,
    visibleTable,
    moreBlock,
    h(
      "p",
      { class: "muted" },
      h("a", { href: "/portal/workpackages" }, "Alle meine Arbeitspakete anzeigen"),
    ),
  );
}

function renderMyActionsCard(myCockpit) {
  const overdue = myCockpit.my_overdue_actions || [];
  const open = myCockpit.my_open_actions || [];
  const allActionsLink = h(
    "p",
    { class: "muted" },
    h("a", { href: "/portal/actions" }, "Alle Aufgaben ansehen"),
  );
  if (!overdue.length && !open.length) {
    return h(
      "section",
      { class: "my-area-card" },
      h("h3", {}, "Meine Aufgaben"),
      renderEmpty("Aktuell keine offenen Aufgaben."),
      allActionsLink,
    );
  }
  const isCritical = overdue.length > 0;
  const items = [];
  for (const a of overdue) {
    items.push(
      h(
        "li",
        {},
        h("strong", {}, "überfällig: "),
        a.text,
        " · Frist ",
        formatDate(a.due_date),
        " · ",
        h("a", { href: `/portal/meetings/${a.meeting_id}` }, a.meeting_title),
      ),
    );
  }
  for (const a of open) {
    items.push(
      h(
        "li",
        {},
        a.text,
        a.due_date ? ` · Frist ${formatDate(a.due_date)}` : "",
        " · ",
        h("a", { href: `/portal/meetings/${a.meeting_id}` }, a.meeting_title),
      ),
    );
  }
  return h(
    "section",
    { class: isCritical ? "my-area-card danger" : "my-area-card" },
    h("h3", {}, `Meine Aufgaben (${overdue.length} überfällig, ${open.length} offen)`),
    h("ul", {}, ...items),
    allActionsLink,
  );
}

function renderMyMeetingsCard(myCockpit) {
  const meetings = myCockpit.my_next_meetings || [];
  if (!meetings.length) {
    return h(
      "section",
      { class: "my-area-card" },
      h("h3", {}, "Nächste Meetings"),
      renderEmpty("Keine geplanten Meetings."),
      h(
        "p",
        { class: "muted" },
        h("a", { href: "/portal/meetings" }, "Alle Meetings ansehen"),
      ),
    );
  }
  const items = meetings.map((m) =>
    h(
      "li",
      {},
      h("a", { href: `/portal/meetings/${m.id}` }, m.title),
      ` · ${formatDateTime(m.starts_at)}`,
      m.workpackage_codes?.length ? ` · ${m.workpackage_codes.join(", ")}` : "",
      " · ",
      h("span", { class: "muted" }, MEETING_STATUS_LABELS[m.status] || m.status),
    ),
  );
  return h(
    "section",
    { class: "my-area-card" },
    h("h3", {}, "Nächste Meetings"),
    h("ul", {}, ...items),
    h(
      "p",
      { class: "muted" },
      h("a", { href: "/portal/meetings" }, "Alle Meetings ansehen"),
    ),
  );
}

function renderMyArea(myCockpit) {
  return h(
    "section",
    {},
    h("h2", {}, "Mein Bereich"),
    h(
      "div",
      { class: "my-area-grid" },
      renderMyWpCard(myCockpit),
      renderMyActionsCard(myCockpit),
      renderMyMeetingsCard(myCockpit),
    ),
  );
}

// ---- Aktivitätsbox -----------------------------------------------------

const ACTIVITY_TYPE_LABELS = {
  document: "Dokument",
  meeting: "Meeting",
  action: "Aufgabe",
  decision: "Beschluss",
  workpackage: "Arbeitspaket",
  team: "Team",
  milestone: "Meilenstein",
  partner: "Partner",
  other: "Sonstiges",
};

function renderActivityEntry(entry) {
  const typeLabel = ACTIVITY_TYPE_LABELS[entry.type] || entry.type;
  const titleNode = entry.link
    ? h("a", { href: entry.link }, entry.title)
    : h("span", {}, entry.title);
  return h(
    "li",
    {},
    h("div", {}, h("span", { class: "badge" }, typeLabel), " ", titleNode),
    entry.description ? h("div", { class: "activity-meta" }, entry.description) : null,
    h(
      "div",
      { class: "activity-meta" },
      formatDateTime(entry.timestamp),
      entry.actor ? ` · ${entry.actor}` : "",
    ),
  );
}

function renderActivityBox(entries, since) {
  const heading = since
    ? `Änderungen seit deinem letzten Besuch (${formatDateTime(since)})`
    : "Änderungen der letzten 14 Tage";
  if (!entries.length) {
    return h(
      "section",
      { class: "activity-box" },
      h("h2", {}, heading),
      renderEmpty("Keine relevanten Änderungen."),
    );
  }
  return h(
    "section",
    { class: "activity-box" },
    h("h2", {}, heading),
    h("ul", {}, ...entries.map(renderActivityEntry)),
  );
}

// ---- Projekt-Cockpit (verdichtet) -------------------------------------

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
      renderEmpty("Keine überfälligen Meilensteine."),
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

function renderIssueCard(issue) {
  const head = h(
    "div",
    { class: "wp-issue-head" },
    h(
      "h3",
      {},
      h(
        "a",
        { href: `/portal/workpackages/${issue.code}` },
        `${issue.code} — ${issue.title}`,
      ),
    ),
    statusBadge(issue.status),
  );
  const sections = [
    h(
      "div",
      { class: "wp-issue-section wp-issue-open" },
      h("div", { class: "wp-issue-label" }, "Offene Punkte"),
      h("p", {}, issue.open_issues),
    ),
  ];
  if (issue.next_steps) {
    sections.push(
      h(
        "div",
        { class: "wp-issue-section wp-issue-next" },
        h("div", { class: "wp-issue-label" }, "Nächste Schritte"),
        h("p", {}, issue.next_steps),
      ),
    );
  }
  const grid = h("div", { class: "wp-issue-grid" }, ...sections);
  return h("article", { class: "wp-issue-card" }, head, grid);
}

function renderOpenIssuesCard(issues) {
  // Auf der Startseite bewusst nur ein Auszug — die Vollsicht lebt im
  // WP-Detail bzw. unter /portal/workpackages.
  const heading = "Offene Punkte aus Arbeitspaketen — Auszug";
  if (!issues.length) {
    return h(
      "section",
      { class: "cockpit-card" },
      h("h2", {}, heading),
      renderEmpty("Aktuell sind keine offenen Punkte in den Arbeitspaketen vermerkt."),
    );
  }
  const visible = issues.slice(0, OPEN_ISSUE_LIMIT);
  const hidden = issues.length - visible.length;
  const link = h("a", { href: "/portal/workpackages" }, "Alle Arbeitspakete anzeigen");
  const footer =
    hidden > 0
      ? h(
          "p",
          { class: "muted" },
          `Weitere offene Punkte vorhanden (${hidden} weitere). `,
          link,
        )
      : h("p", { class: "muted" }, link);
  return h(
    "section",
    { class: "cockpit-card cockpit-card-wide" },
    h("h2", {}, heading),
    ...visible.map(renderIssueCard),
    footer,
  );
}

function renderStatusOverviewCard(counts, overview) {
  // Verdichtete Sicht: Statuszahlen prominent, anschließend nur eine
  // Mini-Tabelle der „Problem"-WPs (kritisch / wartet auf Input / in Arbeit).
  // Die vollständige Liste lebt auf /portal/workpackages.
  const countItems = Object.entries(WP_STATUS_LABELS).map(([key, label]) =>
    h("li", {}, h("strong", {}, String(counts[key] ?? 0)), label),
  );
  const problems = overview.filter((entry) => PROBLEM_WP_STATUSES.has(entry.status));
  const problemRows = problems.map((entry) =>
    h(
      "tr",
      {},
      h(
        "td",
        {},
        h("a", { href: `/portal/workpackages/${entry.code}` }, entry.code),
      ),
      h("td", {}, entry.title),
      h("td", {}, statusBadge(entry.status)),
    ),
  );
  const table = problems.length
    ? h(
        "table",
        { class: "cockpit-problem-wps" },
        h(
          "thead",
          {},
          h("tr", {}, h("th", {}, "Code"), h("th", {}, "Titel"), h("th", {}, "Status")),
        ),
        h("tbody", {}, ...problemRows),
      )
    : h(
        "p",
        { class: "muted" },
        "Keine WPs in den Status kritisch / wartet auf Input / in Arbeit.",
      );
  return h(
    "section",
    { class: "cockpit-card" },
    h("h2", {}, "Arbeitspaket-Statusübersicht"),
    h("ul", { class: "cockpit-status-counts" }, ...countItems),
    h("h3", { class: "cockpit-subhead" }, "Aufmerksamkeit nötig"),
    table,
    h(
      "p",
      { class: "muted" },
      h("a", { href: "/portal/workpackages" }, "Alle Arbeitspakete anzeigen"),
    ),
  );
}

function renderProjectCockpit(cockpit) {
  return h(
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
}

// ---- Zusammenbau -------------------------------------------------------

export async function render(container, ctx) {
  container.classList.add("page-wide");
  const me = ctx.me;
  const isAdminView = effectivePlatformRole(me.person) === "admin";

  const partnerLine = h(
    "p",
    { class: "page-meta" },
    `Partner: ${me.person.partner.name} (${me.person.partner.short_name}) — `,
    h(
      "a",
      { href: `/portal/partners/${me.person.partner.id}` },
      "Stammdaten anzeigen / bearbeiten",
    ),
  );
  const greeting = pageHeader(
    `Willkommen, ${me.person.display_name}`,
    "Persönliche Sicht und aktuelle Projektkennzahlen — alles auf einer Seite.",
    { meta: partnerLine },
  );

  // Slots werden in einer Reihenfolge zusammengesteckt, die sich nach der
  // effektiven Plattformrolle richtet:
  //
  //   Nutzeransicht (effectivePlatformRole === "member"):
  //     greeting → partnerLine → KPI-Streifen → „Mein Bereich" →
  //     Projekt-Cockpit → Aktivitätsbox → crossNav
  //
  //   Admin-Ansicht (effectivePlatformRole === "admin"):
  //     greeting → partnerLine → KPI-Streifen → Projekt-Cockpit →
  //     „Mein Bereich" → Aktivitätsbox → crossNav
  //
  // KPI-Zahlen sind global und stehen in beiden Modi oben — sie verdrängen
  // den persönlichen Bereich aber nicht, weil „Mein Bereich" in der
  // Nutzeransicht direkt darunter folgt.
  const kpiSlot = h("div", {}, renderLoading("Kennzahlen werden geladen …"));
  const myAreaSlot = h("div", {}, renderLoading("Mein Bereich wird geladen …"));
  const activitySlot = h("div", {}, renderLoading("Aktivitäten werden geladen …"));
  const projectSlot = h("div", {}, renderLoading("Projekt-Cockpit wird geladen …"));
  const projectHeader = h("h2", {}, "Projekt-Cockpit");
  // ``myAreaHeader`` ist ein unsichtbarer Anker für Screenreader, damit die
  // Sektionsreihenfolge in der Admin-Ansicht semantisch stabil bleibt.
  const myAreaHeader = h("h2", { class: "sr-only" }, "Mein Bereich (Übersicht)");

  const nav = crossNav("/portal/");
  const orderedBlocks = isAdminView
    ? [projectHeader, projectSlot, myAreaHeader, myAreaSlot]
    : [myAreaSlot, projectHeader, projectSlot];

  container.replaceChildren(
    greeting,
    kpiSlot,
    ...orderedBlocks,
    activitySlot,
    nav,
  );

  // „Seit letztem Besuch": vor dem Fetch lesen, danach erst markieren.
  const since = getLastSeenAt();
  const sinceParam = since ? `?since=${encodeURIComponent(since)}` : "";

  // Drei API-Aufrufe parallel — jeweils mit eigenem Fehler-Handling, damit
  // ein Fehler in einem Block die anderen nicht abschießt.
  const [myCockpitRes, activityRes, projectRes] = await Promise.allSettled([
    api("GET", "/api/cockpit/me"),
    api("GET", `/api/activity/recent${sinceParam}`),
    api("GET", "/api/cockpit/project"),
  ]);

  const myCockpit = myCockpitRes.status === "fulfilled" ? myCockpitRes.value : null;
  const projectCockpit = projectRes.status === "fulfilled" ? projectRes.value : null;

  // KPI-Streifen — wir zeigen ihn auch dann, wenn nur eine Quelle erreicht
  // wurde; fehlende Werte erscheinen als 0.
  kpiSlot.replaceChildren(renderKpiStrip(myCockpit, projectCockpit));

  if (myCockpit) {
    myAreaSlot.replaceChildren(renderMyArea(myCockpit));
  } else {
    myAreaSlot.replaceChildren(
      renderError(`„Mein Bereich" konnte nicht geladen werden: ${myCockpitRes.reason.message}`),
    );
  }

  if (activityRes.status === "fulfilled") {
    activitySlot.replaceChildren(renderActivityBox(activityRes.value, since));
    // Erst markieren, wenn der Fetch erfolgreich war — sonst verliert
    // der Nutzer beim nächsten Besuch alle Einträge, die er nie gesehen hat.
    markSeenNow();
  } else {
    activitySlot.replaceChildren(
      renderError(`Aktivitäten konnten nicht geladen werden: ${activityRes.reason.message}`),
    );
  }

  if (projectCockpit) {
    projectSlot.replaceChildren(renderProjectCockpit(projectCockpit));
  } else {
    projectSlot.replaceChildren(
      renderError(`Cockpit konnte nicht geladen werden: ${projectRes.reason.message}`),
    );
  }
}
