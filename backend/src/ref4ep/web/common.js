// Wiederverwendbare Helfer für die Ref4EP-SPA.
//
// - api(method, url, body): JSON-Fetch mit CSRF-Header bei Schreibops.
// - getCsrfToken(): liest das ref4ep_csrf-Cookie.
// - h(tag, attrs, ...children): kleine virtuelle DOM-Helper-Funktion.

export function getCsrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)ref4ep_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

export async function api(method, url, body = null) {
  const opts = {
    method,
    headers: {
      "Accept": "application/json",
    },
    credentials: "same-origin",
  };
  if (body !== null) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  if (method !== "GET" && method !== "HEAD") {
    const csrf = getCsrfToken();
    if (csrf) {
      opts.headers["X-CSRF-Token"] = csrf;
    }
  }
  const response = await fetch(url, opts);
  if (response.status === 401) {
    // Zentrale Behandlung: zur Login-Seite umleiten.
    window.location.href = "/login";
    throw new Error("unauthenticated");
  }
  let payload = null;
  if (response.headers.get("content-type")?.includes("application/json")) {
    payload = await response.json();
  }
  if (!response.ok) {
    const message = payload?.detail?.error?.message || `HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload;
}

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") {
      el.addEventListener(k.slice(2).toLowerCase(), v);
    } else if (v !== null && v !== undefined && v !== false) {
      el.setAttribute(k, v);
    }
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function clearAndAppend(container, ...nodes) {
  container.replaceChildren(...nodes);
}

// ---- UX-Helfer (Block 0011) -------------------------------------------
//
// Drei kleine Bausteine, damit Lade-, Fehler- und Empty-Zustände in
// allen Modulen gleich aussehen — und ein Cross-Nav-Footer, der die
// drei zentralen internen Seiten (Cockpit, Arbeitspakete,
// Meilensteine) miteinander verbindet, egal wo man gerade ist.

export function renderLoading(message = "Lädt …") {
  return h("p", { class: "loading muted", role: "status", "data-loading": "true" }, message);
}

export function renderError(message) {
  // Wir akzeptieren ``Error``-Objekte direkt — ``api()`` wirft solche.
  const text = typeof message === "string" ? message : message?.message || String(message);
  return h("p", { class: "error", role: "alert" }, text);
}

export function renderEmpty(message) {
  return h("p", { class: "empty muted", "data-empty": "true" }, message);
}

const CROSS_NAV_LINKS = [
  { href: "/portal/", label: "Projektcockpit" },
  { href: "/portal/workpackages", label: "Arbeitspakete" },
  { href: "/portal/milestones", label: "Meilensteine" },
];

export function crossNav(currentHref = null) {
  // Kleiner Footer-Streifen mit Quer-Navigation. Der aktive Eintrag
  // wird als Text statt als Link gerendert (kein Self-Link).
  const items = CROSS_NAV_LINKS.flatMap((link, idx) => {
    const sep = idx === 0 ? null : h("span", { class: "cross-nav-sep" }, " · ");
    const isCurrent = currentHref && link.href === currentHref;
    const node = isCurrent
      ? h("strong", {}, link.label)
      : h("a", { href: link.href }, link.label);
    return sep ? [sep, node] : [node];
  });
  return h("nav", { class: "cross-nav muted", "aria-label": "Projekt-Navigation" }, ...items);
}
