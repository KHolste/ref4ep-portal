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
