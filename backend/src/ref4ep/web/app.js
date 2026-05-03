// Ref4EP-SPA-Router (Sprint 1).
//
// Lädt /api/me beim Start; bei 401 wird der gemeinsame Fetch-Wrapper
// in common.js zur Login-Seite umleiten. Anschließend einfaches
// History-API-Routing für Cockpit, Workpackages, WP-Detail, Account.

import { api } from "/portal/common.js";

const ROUTES = [
  { pattern: /^\/portal\/?$/, module: "cockpit" },
  { pattern: /^\/portal\/workpackages\/?$/, module: "workpackages" },
  { pattern: /^\/portal\/workpackages\/([^/]+)\/?$/, module: "workpackage_detail", param: "code" },
  { pattern: /^\/portal\/documents\/([^/]+)\/?$/, module: "document_detail", param: "id" },
  { pattern: /^\/portal\/account\/?$/, module: "account" },
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
  const sep = document.createTextNode(" · ");
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
  box.append(span, sep, form);
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

async function bootstrap() {
  try {
    currentMe = await api("GET", "/api/me");
  } catch {
    return; // api() leitet bereits zu /login um.
  }
  renderUserBox();
  attachLinkInterception();
  await dispatch(window.location.pathname);
}

bootstrap();
