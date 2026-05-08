// Admin-Systemstatus-Seite (Block 0019).
//
// Lädt /api/admin/system/status und rendert sechs Karten:
//   1. System / Health
//   2. Datenbank
//   3. Backups
//   4. Speicherplatz
//   5. Objektzahlen
//   6. Letzte Fehler  (in diesem Block deaktiviert — Karte zeigt
//                       einen sachlichen Hinweis statt Logzeilen)
//
// Reine Lesesicht. Es gibt absichtlich nur einen „Aktualisieren"-Button —
// keine destruktiven Aktionen und keine Schreibpfade in diesem Modul.

import { api, crossNav, h, pageHeader, renderError, renderLoading } from "/portal/common.js";

const HEALTH_LABELS = {
  ok: "OK",
  warning: "Hinweis",
  error: "Fehler",
};

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

function formatBytes(bytes) {
  if (bytes === null || bytes === undefined) return "—";
  const num = Number(bytes);
  if (!Number.isFinite(num) || num < 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = num;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const digits = value >= 100 || unit === 0 ? 0 : value >= 10 ? 1 : 2;
  return `${value.toFixed(digits)} ${units[unit]}`;
}

function formatPercent(value) {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(1)} %`;
}

function healthClass(status) {
  if (status === "error") return "system-card system-card-error";
  if (status === "warning") return "system-card system-card-warning";
  return "system-card system-card-ok";
}

function healthBadge(status) {
  const cls = `badge system-badge system-badge-${status || "ok"}`;
  return h("span", { class: cls }, HEALTH_LABELS[status] || status || "?");
}

function row(label, value) {
  return h(
    "div",
    { class: "system-row" },
    h("span", { class: "system-row-label" }, label),
    h("span", { class: "system-row-value" }, value),
  );
}

function renderHealthCard(status) {
  const warnings = status.health.warnings || [];
  const warningList = warnings.length
    ? h(
        "ul",
        { class: "system-warnings" },
        ...warnings.map((w) => h("li", {}, w)),
      )
    : h("p", { class: "muted" }, "Keine Hinweise.");
  return h(
    "section",
    { class: healthClass(status.health.status) },
    h(
      "div",
      { class: "system-card-head" },
      h("h2", {}, "Systemstatus"),
      healthBadge(status.health.status),
    ),
    row("Anwendung", `${status.app.name} ${status.app.version}`.trim()),
    row("Servertzeit", formatDateTime(status.app.current_time)),
    h("h3", { class: "system-subhead" }, "Hinweise"),
    warningList,
  );
}

function renderDatabaseCard(status) {
  const db = status.database;
  return h(
    "section",
    { class: "system-card" },
    h("h2", {}, "Datenbank"),
    row("Alembic-Revision", db.alembic_revision || "—"),
    row("Pfad", db.db_path || "(nicht-SQLite-Backend)"),
    row("Datei vorhanden", db.db_exists ? "ja" : "nein"),
    row("Größe", formatBytes(db.db_size_bytes)),
  );
}

function ynUnknown(value) {
  if (value === true) return "ja";
  if (value === false) return "nein";
  return "unbekannt";
}

function renderUploadsCard(status) {
  const u = status.uploads;
  const items = [
    row("Storage-Pfad", u.storage_dir),
    row("Storage vorhanden", u.storage_dir_exists ? "ja" : "nein"),
    row("Upload-Dateien", String(u.storage_file_count)),
    row("Upload-Speichergröße", formatBytes(u.storage_total_bytes)),
    row("data/ gesamt (Größe)", formatBytes(u.data_dir_total_bytes)),
    row("data/ gesamt (Dateien)", String(u.data_file_count)),
  ];
  if (
    u.document_storage_file_count !== null &&
    u.document_storage_file_count !== undefined
  ) {
    items.push(
      row(
        "Dokument-Uploads",
        `${u.document_storage_file_count} · ${formatBytes(u.document_storage_total_bytes)}`,
      ),
    );
  }
  items.push(
    row("Backup-Datei (geprüft)", u.backup_checked_name || "—"),
    row("Backup enthält Datenbank", ynUnknown(u.backup_contains_database)),
    row("Backup enthält Upload-Speicher", ynUnknown(u.backup_contains_storage)),
  );
  return h(
    "section",
    { class: "system-card" },
    h("h2", {}, "Upload-Speicher"),
    h(
      "p",
      { class: "muted" },
      "Die Datenbank enthält Metadaten. Hochgeladene Dateien liegen im " +
        "Storage-Verzeichnis und werden zusammen mit data/ gesichert.",
    ),
    ...items,
  );
}

function renderBackupCard(status, onRefresh) {
  const b = status.backups;
  const items = [
    row("Verzeichnis", b.backup_dir),
    row("Verzeichnis vorhanden", b.backup_dir_exists ? "ja" : "nein"),
    row("Anzahl Backups", String(b.backup_count)),
  ];
  if (b.latest_backup_name) {
    items.push(
      row("Neuestes Backup", b.latest_backup_name),
      row("Zeitpunkt", formatDateTime(b.latest_backup_mtime)),
      row("Größe", formatBytes(b.latest_backup_size_bytes)),
    );
  } else {
    items.push(row("Neuestes Backup", "—"));
  }
  // Block 0033 — manueller Backup-Trigger.
  const hint = h(
    "p",
    { class: "muted backup-trigger-hint" },
    "Erstellt ein serverseitiges Backup gemäß Betriebsroutine.",
  );
  const status_line = h("p", { class: "backup-trigger-status", style: "display:none" }, "");
  const triggerBtn = h(
    "button",
    { type: "button", class: "backup-trigger-button" },
    "Backup jetzt starten",
  );
  triggerBtn.addEventListener("click", async () => {
    if (!confirm("Backup jetzt anstoßen? Das kann ein paar Minuten dauern.")) return;
    triggerBtn.disabled = true;
    const original = triggerBtn.textContent;
    triggerBtn.textContent = "Backup wird gestartet …";
    status_line.style.display = "none";
    status_line.classList.remove("error");
    try {
      const res = await api("POST", "/api/admin/backup/start", {});
      if (res && res.result === "success") {
        status_line.textContent =
          "Backup wurde gestartet. Die neueste Sicherung erscheint nach Abschluss in der Übersicht.";
        status_line.classList.remove("error");
      } else {
        status_line.textContent =
          (res && res.message) || "Backup-Start scheiterte.";
        status_line.classList.add("error");
      }
      status_line.style.display = "";
      if (typeof onRefresh === "function") {
        await onRefresh();
        return; // onRefresh re-rendert die Karte; lokale State-Änderungen
                // brauchen nicht mehr aktualisiert zu werden.
      }
    } catch (err) {
      status_line.textContent = err.message || "Backup-Start fehlgeschlagen.";
      status_line.classList.add("error");
      status_line.style.display = "";
    } finally {
      triggerBtn.disabled = false;
      triggerBtn.textContent = original;
    }
  });
  const triggerSection = h(
    "div",
    { class: "backup-trigger" },
    hint,
    h("div", { class: "form-actions" }, triggerBtn),
    status_line,
  );
  return h(
    "section",
    { class: "system-card" },
    h("h2", {}, "Backups"),
    ...items,
    triggerSection,
  );
}

function renderStorageCard(status) {
  const s = status.storage;
  return h(
    "section",
    { class: "system-card" },
    h("h2", {}, "Speicherplatz"),
    row("Datenpfad", s.data_dir),
    row("Gemessen an", s.measured_at_path),
    row("Gesamt", formatBytes(s.total_bytes)),
    row("Belegt", formatBytes(s.used_bytes)),
    row("Frei", formatBytes(s.free_bytes)),
    row("Frei (%)", formatPercent(s.free_percent)),
  );
}

function renderCountsCard(status) {
  const c = status.counts;
  return h(
    "section",
    { class: "system-card" },
    h("h2", {}, "Objektzahlen"),
    row("Personen (gesamt)", String(c.persons)),
    row("Personen (aktiv)", String(c.active_persons)),
    row("Partner", String(c.partners)),
    row("Dokumente", String(c.documents)),
    row("Meetings", String(c.meetings)),
    row("Offene Aufgaben", String(c.open_actions)),
    row("Überfällige Aufgaben", String(c.overdue_actions)),
  );
}

function renderLogsCard(status) {
  // ``logs`` ist in diesem Block bewusst noch nicht gefüllt — wir blenden
  // die Karte trotzdem ein, damit der Betreiber sieht, dass der Punkt
  // bekannt ist und nichts vergessen wurde.
  const recent =
    status.logs && Array.isArray(status.logs.recent_errors) ? status.logs.recent_errors : null;
  const body = recent && recent.length
    ? h(
        "ul",
        { class: "system-logs" },
        ...recent.map((line) => h("li", {}, line)),
      )
    : h(
        "p",
        { class: "muted" },
        "Logzeilen werden in diesem Block nicht aus dem Server gelesen — siehe offene Punkte.",
      );
  return h("section", { class: "system-card" }, h("h2", {}, "Letzte Fehler"), body);
}

function renderAll(container, status, onRefresh) {
  const refreshBtn = h(
    "button",
    { type: "button", class: "secondary", onclick: onRefresh },
    "Aktualisieren",
  );
  container.replaceChildren(
    pageHeader(
      "Systemstatus",
      "Betriebs- und Smoke-Test-Werte für Admins. Schreibende Aktionen sind auf den manuellen Backup-Start beschränkt.",
    ),
    h("div", { class: "actions" }, refreshBtn),
    h(
      "div",
      { class: "system-grid" },
      renderHealthCard(status),
      renderDatabaseCard(status),
      renderBackupCard(status, onRefresh),
      renderUploadsCard(status),
      renderStorageCard(status),
      renderCountsCard(status),
      renderLogsCard(status),
    ),
    crossNav(),
  );
}

export async function render(container, _ctx) {
  container.classList.add("page-wide");
  async function load() {
    container.replaceChildren(
      pageHeader("Systemstatus"),
      renderLoading("Systemstatus wird geladen …"),
    );
    let status;
    try {
      status = await api("GET", "/api/admin/system/status");
    } catch (err) {
      container.replaceChildren(pageHeader("Systemstatus"), renderError(err));
      return;
    }
    renderAll(container, status, load);
  }
  await load();
}
