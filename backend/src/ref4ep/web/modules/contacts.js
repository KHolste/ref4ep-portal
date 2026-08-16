// Projektweites Kontaktverzeichnis (Block 0053).
//
// Zeigt jeder eingeloggten Person die Kontaktdaten des gesamten
// Projekts — bewusst unabhängig von der eigenen Einrichtung und den
// eigenen Arbeitspaketen. Datenquelle ist der zusammengeführte
// Endpoint ``GET /api/contacts`` (Partnerkontakte + Portal-Accounts).
//
// Gepflegt werden Kontakte weiterhin auf der Partner-Detailseite —
// diese Seite ist reine Lese-Ansicht mit Filter und Direktlinks
// (mailto:/tel:).

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

const WP_ROLE_LABELS = {
  wp_lead: "Lead",
  wp_member: "Mitglied",
};

// ---- Hilfsfunktionen ----------------------------------------------------

function normalize(value) {
  return (value || "").toString().toLowerCase();
}

function isAdminView(ctx) {
  return ctx?.me?.person?.platform_role === "admin";
}

// Ein Eintrag ist „hervorgehoben", wenn er eine Leitungs- oder
// Hauptkontaktfunktion trägt — die Schnellfilter-Auswahl greift darauf zu.
function isKeyContact(entry) {
  return !!(entry.is_primary_contact || entry.is_project_lead || entry.is_partner_lead);
}

function searchHaystack(entry) {
  const wpParts = (entry.workpackages || []).flatMap((wp) => [wp.code, wp.title]);
  return normalize(
    [
      entry.name,
      entry.title_or_degree,
      entry.email,
      entry.phone,
      entry.function,
      entry.organization_unit,
      entry.workpackage_notes,
      entry.partner?.short_name,
      entry.partner?.name,
      entry.partner?.unit_name,
      ...wpParts,
    ]
      .filter(Boolean)
      .join(" "),
  );
}

function uniquePartners(entries) {
  const seen = new Map(); // id → { id, short_name, name }
  for (const entry of entries) {
    if (entry.partner && !seen.has(entry.partner.id)) {
      seen.set(entry.partner.id, entry.partner);
    }
  }
  return [...seen.values()].sort((a, b) => a.short_name.localeCompare(b.short_name));
}

function uniqueFunctions(entries) {
  const seen = new Set();
  for (const entry of entries) {
    if (entry.function) seen.add(entry.function);
  }
  return [...seen].sort((a, b) => a.localeCompare(b));
}

function uniqueWorkpackages(entries) {
  const seen = new Map(); // code → title
  for (const entry of entries) {
    for (const wp of entry.workpackages || []) {
      if (!seen.has(wp.code)) seen.set(wp.code, wp.title);
    }
  }
  return [...seen.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([code, title]) => ({ code, title }));
}

function applyFilters(entries, { search, partnerId, func, wpCode, keyOnly }) {
  const term = normalize(search);
  return entries.filter((entry) => {
    if (term && !searchHaystack(entry).includes(term)) return false;
    if (partnerId && entry.partner?.id !== partnerId) return false;
    if (func && entry.function !== func) return false;
    if (wpCode && !(entry.workpackages || []).some((wp) => wp.code === wpCode)) {
      return false;
    }
    if (keyOnly && !isKeyContact(entry)) return false;
    return true;
  });
}

function groupByPartner(entries) {
  const groups = new Map(); // partner_id → { partner, entries: [] }
  for (const entry of entries) {
    const partner = entry.partner;
    if (!partner) continue;
    if (!groups.has(partner.id)) {
      groups.set(partner.id, { partner, entries: [] });
    }
    groups.get(partner.id).entries.push(entry);
  }
  return [...groups.values()].sort((a, b) =>
    a.partner.short_name.localeCompare(b.partner.short_name),
  );
}

// ---- Render -------------------------------------------------------------

function renderSummary(entries) {
  const partnerCount = uniquePartners(entries).length;
  const portalCount = entries.filter((e) => e.is_portal_user).length;
  const stats = [
    { value: entries.length, label: entries.length === 1 ? "Person" : "Personen" },
    { value: partnerCount, label: partnerCount === 1 ? "Einrichtung" : "Einrichtungen" },
    { value: portalCount, label: "mit Portal-Konto" },
  ];
  return h(
    "div",
    { class: "contacts-summary" },
    ...stats.map((s) =>
      h(
        "span",
        { class: "contacts-stat" },
        h("span", { class: "contacts-stat-value" }, String(s.value)),
        h("span", { class: "contacts-stat-label" }, s.label),
      ),
    ),
  );
}

function renderFilterBox({
  searchInput,
  partnerSelect,
  functionSelect,
  wpSelect,
  keyCheckbox,
  inactiveCheckbox,
  resetBtn,
}) {
  const labels = [
    h("label", {}, "Suche nach Name, E-Mail, Telefon", searchInput),
    h("label", {}, "Einrichtung", partnerSelect),
    h("label", {}, "Funktion", functionSelect),
    h("label", {}, "Arbeitspaket", wpSelect),
    h(
      "label",
      { class: "checkbox-row" },
      keyCheckbox,
      h("span", {}, "Nur Leitungen und Hauptkontakte"),
    ),
  ];
  if (inactiveCheckbox) {
    labels.push(
      h(
        "label",
        { class: "checkbox-row" },
        inactiveCheckbox,
        h("span", {}, "Deaktivierte einblenden"),
      ),
    );
  }
  return h(
    "fieldset",
    { class: "contacts-filterbox filterbox" },
    h("legend", {}, "Kontakte filtern"),
    ...labels,
    resetBtn,
  );
}

function badge(text, modifier) {
  return h("span", { class: `badge contacts-badge contacts-badge-${modifier}` }, text);
}

function renderBadges(entry) {
  const items = [];
  // ``is_project_lead`` (Kontaktpflege) und ``is_partner_lead``
  // (Partnerrolle) meinen beide „Projektleitung" — ein Badge genügt.
  if (entry.is_project_lead || entry.is_partner_lead) {
    items.push(badge("Projektleitung", "lead"));
  }
  if (entry.is_primary_contact) items.push(badge("Hauptkontakt", "primary"));
  if (entry.is_portal_user) items.push(badge("Portal-Konto", "portal"));
  if (!entry.is_active) items.push(badge("deaktiviert", "inactive"));
  if (!items.length) return null;
  return h("div", { class: "contacts-badges" }, ...items);
}

function contactLine(label, valueNode) {
  if (!valueNode) return null;
  return h(
    "div",
    { class: "contacts-line" },
    h("span", { class: "contacts-line-label" }, label),
    h("span", { class: "contacts-line-value" }, valueNode),
  );
}

function mailLink(email) {
  if (!email) return null;
  return h("a", { href: `mailto:${email}` }, email);
}

function phoneLink(phone) {
  if (!phone) return null;
  // ``tel:``-Ziel ohne Leer-/Sonderzeichen, Anzeige bleibt wie gepflegt.
  const dialable = phone.replace(/[^\d+]/g, "");
  if (!dialable) return h("span", {}, phone);
  return h("a", { href: `tel:${dialable}` }, phone);
}

function renderWorkpackages(entry) {
  const wps = entry.workpackages || [];
  if (!wps.length) return null;
  return h(
    "div",
    { class: "contacts-wps" },
    ...wps.map((wp) =>
      h(
        "a",
        {
          class: "contacts-wp-chip",
          href: `/portal/workpackages/${wp.code}`,
          title: `${wp.code} — ${wp.title}`,
        },
        wp.code,
        h("span", { class: "contacts-wp-role" }, WP_ROLE_LABELS[wp.wp_role] || wp.wp_role),
      ),
    ),
  );
}

function renderCard(entry) {
  const displayName = entry.title_or_degree
    ? `${entry.title_or_degree} ${entry.name}`
    : entry.name;
  const classes = ["contacts-card"];
  if (!entry.is_active) classes.push("contacts-card-inactive");
  return h(
    "article",
    { class: classes.join(" ") },
    h(
      "header",
      { class: "contacts-card-head" },
      h("h3", { class: "contacts-card-name" }, displayName),
      entry.function ? h("p", { class: "contacts-card-function" }, entry.function) : null,
      renderBadges(entry),
    ),
    h(
      "div",
      { class: "contacts-card-body" },
      contactLine("E-Mail", mailLink(entry.email)),
      contactLine("Telefon", phoneLink(entry.phone)),
      contactLine(
        "Einheit",
        entry.organization_unit ? h("span", {}, entry.organization_unit) : null,
      ),
      contactLine(
        "Im Projekt",
        entry.workpackage_notes ? h("span", {}, entry.workpackage_notes) : null,
      ),
      entry.internal_note
        ? contactLine(
            "Interne Notiz",
            h("span", { class: "contacts-internal-note" }, entry.internal_note),
          )
        : null,
    ),
    renderWorkpackages(entry),
    h(
      "footer",
      { class: "contacts-card-footer" },
      h("a", { href: `/portal/partners/${entry.partner.id}` }, "Einrichtung anzeigen →"),
    ),
  );
}

function renderPartnerSection({ partner, entries }) {
  const subtitle = [partner.name, partner.unit_name].filter(Boolean).join(" · ");
  return h(
    "section",
    { class: "contacts-partner-section" },
    h(
      "header",
      { class: "contacts-partner-head" },
      h(
        "h2",
        { class: "contacts-partner-title" },
        h("a", { href: `/portal/partners/${partner.id}` }, partner.short_name),
      ),
      h("p", { class: "contacts-partner-subtitle muted" }, subtitle),
      h(
        "span",
        { class: "contacts-partner-count muted" },
        entries.length === 1 ? "1 Person" : `${entries.length} Personen`,
      ),
    ),
    h("div", { class: "contacts-card-grid" }, ...entries.map(renderCard)),
  );
}

function renderList(entries) {
  if (!entries.length) {
    return renderEmpty("Keine Kontakte für die aktuelle Filterauswahl.");
  }
  return h(
    "div",
    { class: "contacts-sections" },
    ...groupByPartner(entries).map(renderPartnerSection),
  );
}

// ---- Hauptrender --------------------------------------------------------

export async function render(container, ctx) {
  container.classList.add("page-wide");
  container.classList.add("contacts-page");

  const header = pageHeader(
    "Kontakte",
    "Alle Ansprechpersonen des Projekts — über alle Einrichtungen und " +
      "Arbeitspakete hinweg, unabhängig von der eigenen Zugehörigkeit.",
  );
  appendChildren(container, header, renderLoading("Kontakte werden geladen …"));

  const adminView = isAdminView(ctx);
  // Nur Admins dürfen deaktivierte Einträge sehen — der Server erzwingt
  // das zusätzlich und ignoriert den Parameter sonst.
  const inactiveCheckbox = adminView ? h("input", { type: "checkbox" }) : null;

  let entries = [];

  async function load() {
    const includeInactive = !!(inactiveCheckbox && inactiveCheckbox.checked);
    return api("GET", `/api/contacts?include_inactive=${includeInactive ? "true" : "false"}`);
  }

  try {
    entries = await load();
  } catch (err) {
    appendChildren(container, header, renderError(err));
    return;
  }

  if (!entries.length) {
    appendChildren(
      container,
      header,
      renderEmpty("Es sind noch keine Kontaktdaten hinterlegt."),
      crossNav(),
    );
    return;
  }

  const searchInput = h("input", {
    type: "search",
    placeholder: "z. B. Meier, WP3 oder @jlu",
  });
  const partnerSelect = h("select", {}, h("option", { value: "" }, "Alle Einrichtungen"));
  const functionSelect = h("select", {}, h("option", { value: "" }, "Alle Funktionen"));
  const wpSelect = h("select", {}, h("option", { value: "" }, "Alle Arbeitspakete"));
  const keyCheckbox = h("input", { type: "checkbox" });
  const resetBtn = h(
    "button",
    { type: "button", class: "secondary filter-reset" },
    "Zurücksetzen",
  );

  function fillSelects() {
    // Auswahl beim Neuladen erhalten, soweit der Wert noch existiert.
    const keepPartner = partnerSelect.value;
    const keepFunction = functionSelect.value;
    const keepWp = wpSelect.value;
    partnerSelect.replaceChildren(
      h("option", { value: "" }, "Alle Einrichtungen"),
      ...uniquePartners(entries).map((p) =>
        h("option", { value: p.id }, `${p.short_name} — ${p.name}`),
      ),
    );
    functionSelect.replaceChildren(
      h("option", { value: "" }, "Alle Funktionen"),
      ...uniqueFunctions(entries).map((f) => h("option", { value: f }, f)),
    );
    wpSelect.replaceChildren(
      h("option", { value: "" }, "Alle Arbeitspakete"),
      ...uniqueWorkpackages(entries).map((wp) =>
        h("option", { value: wp.code }, `${wp.code} — ${wp.title}`),
      ),
    );
    partnerSelect.value = keepPartner;
    functionSelect.value = keepFunction;
    wpSelect.value = keepWp;
  }

  const summarySlot = h("div", {});
  const listSlot = h("div", {});

  function applyAndRender() {
    const filtered = applyFilters(entries, {
      search: searchInput.value.trim(),
      partnerId: partnerSelect.value,
      func: functionSelect.value,
      wpCode: wpSelect.value,
      keyOnly: keyCheckbox.checked,
    });
    summarySlot.replaceChildren(renderSummary(filtered));
    listSlot.replaceChildren(renderList(filtered));
  }

  searchInput.addEventListener("input", applyAndRender);
  partnerSelect.addEventListener("change", applyAndRender);
  functionSelect.addEventListener("change", applyAndRender);
  wpSelect.addEventListener("change", applyAndRender);
  keyCheckbox.addEventListener("change", applyAndRender);
  resetBtn.addEventListener("click", () => {
    searchInput.value = "";
    partnerSelect.value = "";
    functionSelect.value = "";
    wpSelect.value = "";
    keyCheckbox.checked = false;
    applyAndRender();
  });
  if (inactiveCheckbox) {
    inactiveCheckbox.addEventListener("change", async () => {
      listSlot.replaceChildren(renderLoading("Kontakte werden geladen …"));
      try {
        entries = await load();
      } catch (err) {
        listSlot.replaceChildren(renderError(err));
        return;
      }
      fillSelects();
      applyAndRender();
    });
  }

  fillSelects();
  appendChildren(
    container,
    h("section", { class: "contacts-hero" }, header, summarySlot),
    renderFilterBox({
      searchInput,
      partnerSelect,
      functionSelect,
      wpSelect,
      keyCheckbox,
      inactiveCheckbox,
      resetBtn,
    }),
    listSlot,
    crossNav(),
  );
  applyAndRender();
}
