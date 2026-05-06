// Arbeitspaket-Übersicht (UX-Folgeblock).
//
// Statt einer langen Tabelle wird die Projektstruktur als hierarchisches
// Karten-Grid dargestellt:
//   - jede Top-Level-WP (parent_code IS NULL bzw. Parent nicht Teil der
//     Liste) bekommt eine eigene Karte;
//   - Unterpakete erscheinen innerhalb der jeweiligen Hauptkarte als
//     kompakte Liste; bei vielen Subs werden die ersten N direkt
//     angezeigt, der Rest klappt per <details> auf.
//
// Daten kommen weiterhin von ``GET /api/workpackages`` — keine
// API-Änderung. „Nur meine Arbeitspakete" arbeitet rein clientseitig
// über ``ctx.me.memberships`` (das Bootstrap der SPA hat das schon
// geladen).

import {
  api,
  appendChildren,
  crossNav,
  h,
  pageHeader,
  renderEmpty,
  renderError,
  renderLoading,
} from "/portal/common.js";

const SUBS_VISIBLE_LIMIT = 5;

// ---- Hilfsfunktionen ----------------------------------------------------

function normalize(value) {
  return (value || "").toString().toLowerCase();
}

function buildHierarchy(wps) {
  // Gruppiert die WP-Liste nach parent_code. WP, deren Parent nicht in
  // der Liste auftaucht, werden als Top-Level behandelt — verhindert
  // versehentliches Ausblenden bei unvollständigen Datensätzen.
  const codes = new Set(wps.map((w) => w.code));
  const groupedSubs = new Map(); // parent_code → [WP]
  const tops = [];
  for (const wp of wps) {
    const isTop = !wp.parent_code || !codes.has(wp.parent_code);
    if (isTop) {
      tops.push(wp);
    } else {
      const list = groupedSubs.get(wp.parent_code) || [];
      list.push(wp);
      groupedSubs.set(wp.parent_code, list);
    }
  }
  // Unterpakete pro Top stabil sortieren (sort_order, dann Code).
  for (const list of groupedSubs.values()) {
    list.sort((a, b) => a.sort_order - b.sort_order || a.code.localeCompare(b.code));
  }
  // Tops nach sort_order, dann Code sortieren.
  tops.sort((a, b) => a.sort_order - b.sort_order || a.code.localeCompare(b.code));
  return { tops, groupedSubs };
}

function uniqueLeads(wps) {
  const seen = new Map(); // short_name → name (für Anzeige)
  for (const wp of wps) {
    if (wp.lead_partner && !seen.has(wp.lead_partner.short_name)) {
      seen.set(wp.lead_partner.short_name, wp.lead_partner.name);
    }
  }
  return [...seen.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([short_name, name]) => ({ short_name, name }));
}

function mineCodes(ctx) {
  const memberships = (ctx && ctx.me && ctx.me.memberships) || [];
  return new Set(memberships.map((m) => m.workpackage_code));
}

// Filter: liefert für jede Top-WP entweder ``null`` (Karte komplett
// ausblenden) oder ein Objekt ``{top, subs}`` — die Sub-Liste enthält
// nur die WPs, die zur Filterauswahl passen. Wenn die Top selbst
// matcht, werden alle ihre Subs gezeigt.
function applyFilters({ tops, groupedSubs }, { search, lead, mineOnly, mineSet }) {
  const term = normalize(search);

  function matchesText(wp) {
    if (!term) return true;
    return (
      normalize(wp.code).includes(term) || normalize(wp.title).includes(term)
    );
  }
  function matchesLead(wp) {
    if (!lead) return true;
    return wp.lead_partner && wp.lead_partner.short_name === lead;
  }
  function matchesMine(wp) {
    if (!mineOnly) return true;
    return mineSet.has(wp.code);
  }
  function matchesAll(wp) {
    return matchesText(wp) && matchesLead(wp) && matchesMine(wp);
  }

  const out = [];
  for (const top of tops) {
    const subs = groupedSubs.get(top.code) || [];
    const topMatches = matchesAll(top);
    if (topMatches) {
      // Top trifft → alle Subs zeigen (oder zumindest die, die nicht
      // explizit durch Sub-spezifische Filter rausfallen würden — wir
      // bleiben pragmatisch: wenn Top trifft, alle Subs anzeigen).
      out.push({ top, subs });
      continue;
    }
    // Wenn die Top nicht selbst matcht, prüfen wir die Subs einzeln.
    const matchingSubs = subs.filter(matchesAll);
    if (matchingSubs.length > 0) {
      out.push({ top, subs: matchingSubs });
    }
  }
  return out;
}

// ---- Render -------------------------------------------------------------

function renderSummary({ tops, groupedSubs, total, mineCount, mineAvailable }) {
  const subTotal = total - tops.length;
  const parts = [
    `${total} Arbeitspakete`,
    `${tops.length} Haupt-WPs`,
    `${subTotal} Unterpakete`,
  ];
  if (mineAvailable) {
    parts.push(`${mineCount} meiner WPs`);
  }
  void groupedSubs; // (Subgruppen-Map nur zur API-Symmetrie übergeben.)
  return h("p", { class: "wp-overview-summary muted" }, parts.join(" · "));
}

function renderFilterBox({
  searchInput,
  leadSelect,
  mineCheckbox,
  resetBtn,
  mineAvailable,
}) {
  const labels = [
    h("label", {}, "Suche nach Code/Titel", searchInput),
    h("label", {}, "Lead-Partner", leadSelect),
  ];
  if (mineAvailable) {
    labels.push(
      h(
        "label",
        { class: "checkbox-row" },
        mineCheckbox,
        h("span", {}, "Nur meine Arbeitspakete"),
      ),
    );
  }
  return h(
    "fieldset",
    { class: "wp-filterbox filterbox" },
    h("legend", {}, "Arbeitspakete filtern"),
    ...labels,
    resetBtn,
  );
}

function leadBadge(short_name, full_name) {
  return h(
    "span",
    { class: "wp-lead-badge", title: full_name || short_name },
    short_name,
  );
}

function renderSubItem(sub, isMine) {
  return h(
    "li",
    { class: isMine ? "wp-subpackage-item wp-subpackage-mine" : "wp-subpackage-item" },
    h("a", { class: "wp-subpackage-code", href: `/portal/workpackages/${sub.code}` }, sub.code),
    " — ",
    h("span", { class: "wp-subpackage-title" }, sub.title),
    sub.lead_partner
      ? h(
          "span",
          { class: "muted wp-subpackage-lead" },
          ` · Lead: ${sub.lead_partner.short_name}`,
        )
      : null,
    isMine ? h("span", { class: "wp-subpackage-mine-marker" }, " · meine") : null,
  );
}

function renderSubList(subs, mineSet, totalSubsForTop) {
  if (!subs.length) {
    return h(
      "p",
      { class: "muted wp-subpackage-empty" },
      "Keine Unterpakete in dieser Auswahl.",
    );
  }
  const visible = subs.slice(0, SUBS_VISIBLE_LIMIT);
  const rest = subs.slice(SUBS_VISIBLE_LIMIT);
  const visibleList = h(
    "ul",
    { class: "wp-subpackage-list" },
    ...visible.map((s) => renderSubItem(s, mineSet.has(s.code))),
  );
  const moreBlock =
    rest.length > 0
      ? h(
          "details",
          { class: "wp-subpackage-more" },
          h("summary", {}, `+ ${rest.length} weitere Unterpakete anzeigen`),
          h(
            "ul",
            { class: "wp-subpackage-list" },
            ...rest.map((s) => renderSubItem(s, mineSet.has(s.code))),
          ),
        )
      : null;
  // Hinweis, wenn Filter Subs ausgeblendet hat.
  const hiddenByFilter = totalSubsForTop - subs.length;
  const filterHint =
    hiddenByFilter > 0
      ? h(
          "p",
          { class: "muted wp-subpackage-filterhint" },
          `${hiddenByFilter} weitere Unterpakete sind durch den Filter ausgeblendet.`,
        )
      : null;
  return h("div", {}, visibleList, moreBlock, filterHint);
}

function renderTopCard(top, subs, mineSet, totalSubsForTop) {
  const isMineTop = mineSet.has(top.code);
  const subsCount = totalSubsForTop;
  const subsCountLabel = subsCount === 1 ? "1 Unterpaket" : `${subsCount} Unterpakete`;
  return h(
    "article",
    { class: isMineTop ? "wp-card wp-card-mine" : "wp-card" },
    h(
      "header",
      { class: "wp-card-head" },
      h(
        "h2",
        { class: "wp-card-title" },
        h("a", { href: `/portal/workpackages/${top.code}` }, top.code),
        " — ",
        h("span", {}, top.title),
      ),
      top.lead_partner
        ? leadBadge(top.lead_partner.short_name, top.lead_partner.name)
        : null,
    ),
    h(
      "div",
      { class: "wp-card-meta muted" },
      subsCountLabel,
      isMineTop ? " · meine" : "",
    ),
    renderSubList(subs, mineSet, totalSubsForTop),
    h(
      "div",
      { class: "wp-card-footer" },
      h("a", { href: `/portal/workpackages/${top.code}` }, "Details anzeigen →"),
    ),
  );
}

function renderGrid(filtered, mineSet, originalGrouped) {
  if (!filtered.length) {
    return renderEmpty("Keine Arbeitspakete für die aktuelle Filterauswahl.");
  }
  return h(
    "div",
    { class: "wp-card-grid" },
    ...filtered.map(({ top, subs }) =>
      renderTopCard(
        top,
        subs,
        mineSet,
        // Total der Subs für „N weitere durch Filter ausgeblendet"-Hinweis.
        (originalGrouped.get(top.code) || []).length,
      ),
    ),
  );
}

// ---- Hauptrender --------------------------------------------------------

export async function render(container, ctx) {
  container.classList.add("page-wide");
  const headerNodes = [
    pageHeader(
      "Arbeitspakete",
      "Hierarchische Übersicht aller Haupt- und Unterpakete des Projekts.",
    ),
  ];
  appendChildren(
    container,
    ...headerNodes,
    renderLoading("Arbeitspakete werden geladen …"),
  );

  let wps;
  try {
    wps = await api("GET", "/api/workpackages");
  } catch (err) {
    appendChildren(container, ...headerNodes, renderError(err));
    return;
  }

  if (!wps.length) {
    appendChildren(
      container,
      ...headerNodes,
      renderEmpty("Noch keine Arbeitspakete angelegt."),
      crossNav("/portal/workpackages"),
    );
    return;
  }

  const { tops, groupedSubs } = buildHierarchy(wps);
  const leads = uniqueLeads(wps);
  const mineSet = mineCodes(ctx);
  // „Nur meine"-Filter ist nur sinnvoll, wenn die SPA Mitgliedschafts-
  // Daten aus /api/me kennt — sonst blenden wir den Schalter aus.
  const mineAvailable = !!(ctx && ctx.me && Array.isArray(ctx.me.memberships));
  const mineCount = mineSet.size;

  // Filter-Felder definieren (live-Filterung beim Tippen/Wechseln).
  const searchInput = h("input", {
    type: "search",
    placeholder: "z. B. WP3 oder Diagnostik",
  });
  const leadSelect = h(
    "select",
    {},
    h("option", { value: "" }, "Alle Lead-Partner"),
    ...leads.map((lp) =>
      h("option", { value: lp.short_name }, `${lp.short_name} — ${lp.name}`),
    ),
  );
  const mineCheckbox = h("input", { type: "checkbox" });
  const resetBtn = h(
    "button",
    { type: "button", class: "secondary wp-filter-reset" },
    "Zurücksetzen",
  );

  const summaryNode = renderSummary({
    tops,
    groupedSubs,
    total: wps.length,
    mineCount,
    mineAvailable,
  });
  const filterBox = renderFilterBox({
    searchInput,
    leadSelect,
    mineCheckbox,
    resetBtn,
    mineAvailable,
  });
  const gridSlot = h("div", {}, h("div", {})); // Platzhalter — wird sofort ersetzt.

  function applyAndRender() {
    const filtered = applyFilters(
      { tops, groupedSubs },
      {
        search: searchInput.value.trim(),
        lead: leadSelect.value,
        mineOnly: mineAvailable && mineCheckbox.checked,
        mineSet,
      },
    );
    gridSlot.replaceChildren(renderGrid(filtered, mineSet, groupedSubs));
  }

  searchInput.addEventListener("input", applyAndRender);
  leadSelect.addEventListener("change", applyAndRender);
  mineCheckbox.addEventListener("change", applyAndRender);
  resetBtn.addEventListener("click", () => {
    searchInput.value = "";
    leadSelect.value = "";
    mineCheckbox.checked = false;
    applyAndRender();
  });

  appendChildren(
    container,
    ...headerNodes,
    summaryNode,
    filterBox,
    gridSlot,
    crossNav("/portal/workpackages"),
  );
  applyAndRender();
}
