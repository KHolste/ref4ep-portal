// Ref4EP-SPA-Router (Sprint 1).
//
// Lädt /api/me beim Start; bei 401 wird der gemeinsame Fetch-Wrapper
// in common.js zur Login-Seite umleiten. Anschließend einfaches
// History-API-Routing für Cockpit, Workpackages, WP-Detail, Account.

import { api, getAdminViewMode, setAdminViewMode } from "/portal/common.js";

const ROUTES = [
  { pattern: /^\/portal\/?$/, module: "cockpit" },
  { pattern: /^\/portal\/workpackages\/?$/, module: "workpackages" },
  { pattern: /^\/portal\/workpackages\/([^/]+)\/?$/, module: "workpackage_detail", param: "code" },
  { pattern: /^\/portal\/documents\/([^/]+)\/?$/, module: "document_detail", param: "id" },
  { pattern: /^\/portal\/partners\/([^/]+)\/?$/, module: "partner_detail", param: "id" },
  { pattern: /^\/portal\/milestones\/?$/, module: "milestones" },
  { pattern: /^\/portal\/meetings\/?$/, module: "meetings" },
  { pattern: /^\/portal\/meetings\/([^/]+)\/print\/?$/, module: "meeting_print", param: "id" },
  { pattern: /^\/portal\/meetings\/([^/]+)\/?$/, module: "meeting_detail", param: "id" },
  { pattern: /^\/portal\/actions\/?$/, module: "actions" },
  { pattern: /^\/portal\/campaigns\/?$/, module: "campaigns" },
  { pattern: /^\/portal\/campaigns\/([^/]+)\/?$/, module: "campaign_detail", param: "id" },
  { pattern: /^\/portal\/calendar\/?$/, module: "calendar" },
  { pattern: /^\/portal\/gantt\/?$/, module: "gantt" },
  { pattern: /^\/portal\/document-comments\/?$/, module: "document_comments" },
  { pattern: /^\/portal\/lead\/team\/?$/, module: "lead_team" },
  { pattern: /^\/portal\/account\/?$/, module: "account" },
  { pattern: /^\/portal\/admin\/audit\/?$/, module: "audit" },
  { pattern: /^\/portal\/admin\/users\/?$/, module: "admin_users" },
  { pattern: /^\/portal\/admin\/users\/([^/]+)\/?$/, module: "admin_user_detail", param: "id" },
  { pattern: /^\/portal\/admin\/partners\/?$/, module: "admin_partners" },
  { pattern: /^\/portal\/admin\/system\/?$/, module: "system_status" },
];

let currentMe = null;
const moduleCache = new Map();

async function loadModule(name) {
  if (!moduleCache.has(name)) {
    moduleCache.set(name, import(`/portal/modules/${name}.js`));
  }
  return moduleCache.get(name);
}

function matchRoute(pathname) {
  for (const route of ROUTES) {
    const m = pathname.match(route.pattern);
    if (m) {
      const params = {};
      if (route.param && m[1]) params[route.param] = decodeURIComponent(m[1]);
      return { route, params };
    }
  }
  return null;
}

function renderUserBox() {
  const box = document.getElementById("nav-user");
  if (!box || !currentMe) return;
  box.innerHTML = "";
  const span = document.createElement("span");
  span.textContent = `${currentMe.person.display_name} (${currentMe.person.partner.short_name})`;
  box.append(span, document.createTextNode(" · "));

  // Admin-Ansicht-Toggle: nur für echte Plattform-Admins.
  if (currentMe.person.platform_role === "admin") {
    const mode = getAdminViewMode();
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "linklike admin-view-toggle";
    toggle.textContent =
      mode === "user"
        ? "Zur Admin-Ansicht wechseln"
        : "Zur Nutzeransicht wechseln";
    toggle.addEventListener("click", () => {
      setAdminViewMode(mode === "user" ? "admin" : "user");
      window.location.reload();
    });
    box.append(toggle, document.createTextNode(" · "));
  }

  const form = document.createElement("form");
  form.method = "post";
  form.action = "/logout";
  form.style.display = "inline";
  const csrf = document.cookie.match(/(?:^|;\s*)ref4ep_csrf=([^;]+)/);
  if (csrf) {
    const hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.name = "_csrf_marker";
    hidden.value = csrf[1];
    form.append(hidden);
  }
  const btn = document.createElement("button");
  btn.type = "submit";
  btn.textContent = "Abmelden";
  btn.className = "linklike";
  form.append(btn);
  box.append(form);
}

function renderViewModeBanner() {
  // Sichtbarer Hinweisbalken, wenn ein Admin auf Nutzeransicht
  // umgeschaltet hat — Serverrechte bleiben unverändert.
  const banner = document.getElementById("admin-view-banner");
  if (!banner) return;
  const isAdmin = currentMe?.person?.platform_role === "admin";
  banner.hidden = !(isAdmin && getAdminViewMode() === "user");
}

async function dispatch(pathname) {
  const main = document.getElementById("app");
  if (!main) return;

  const matched = matchRoute(pathname);
  if (!matched) {
    main.innerHTML = "<p>Unbekannter Pfad. <a href='/portal/'>Zum Cockpit</a></p>";
    return;
  }

  if (currentMe?.person?.must_change_password && matched.route.module !== "account") {
    history.replaceState(null, "", "/portal/account");
    return dispatch("/portal/account");
  }

  // ``className`` wird vor jedem Modul-Render zurückgesetzt — Module
  // können dann optional ``container.classList.add("page-wide")``
  // setzen, ohne dass das Layout der Vorgängerseite hängen bleibt.
  main.className = "";
  main.innerHTML = "<p>Lade …</p>";
  try {
    const mod = await loadModule(matched.route.module);
    await mod.render(main, { me: currentMe, params: matched.params, navigate });
    document.querySelectorAll("#nav-main a").forEach((a) => {
      a.classList.toggle("active", a.dataset.route === matched.route.module);
    });
  } catch (err) {
    main.innerHTML = `<p class="error">Fehler beim Laden: ${err.message}</p>`;
  }
}

function navigate(target) {
  if (target.startsWith(window.location.origin)) {
    target = target.slice(window.location.origin.length);
  }
  if (window.location.pathname !== target) {
    history.pushState(null, "", target);
    dispatch(target);
  }
}

function attachLinkInterception() {
  document.body.addEventListener("click", (ev) => {
    const a = ev.target.closest("a");
    if (!a) return;
    const href = a.getAttribute("href");
    if (!href || !href.startsWith("/portal")) return;
    if (a.target === "_blank" || ev.metaKey || ev.ctrlKey) return;
    ev.preventDefault();
    navigate(href);
  });
  window.addEventListener("popstate", () => dispatch(window.location.pathname));
}

function applyRoleVisibility() {
  const realAdmin = currentMe?.person?.platform_role === "admin";
  // Effektive Rolle für die UI: wenn der Admin auf Nutzeransicht
  // geschaltet hat, blenden wir Admin-Funktionen aus.
  const effectiveAdmin = realAdmin && getAdminViewMode() !== "user";
  const isAnyWpLead = (currentMe?.memberships || []).some((m) => m.wp_role === "wp_lead");
  // „Mein Team": sichtbar für WP-Leads und (Admin in Admin-Ansicht).
  if (effectiveAdmin || isAnyWpLead) {
    const lead = document.getElementById("nav-lead-team");
    if (lead) lead.hidden = false;
  }
  if (!effectiveAdmin) return;
  for (const id of [
    "nav-admin-spacer",
    "nav-admin-label",
    "nav-admin-users",
    "nav-admin-partners",
    "nav-admin-audit",
    "nav-admin-system",
  ]) {
    const el = document.getElementById(id);
    if (el) el.hidden = false;
  }
}

async function bootstrap() {
  try {
    currentMe = await api("GET", "/api/me");
  } catch {
    return; // api() leitet bereits zu /login um.
  }
  renderUserBox();
  renderViewModeBanner();
  applyRoleVisibility();
  attachLinkInterception();
  await dispatch(window.location.pathname);
}

bootstrap();
