# Betriebsanleitung — Ref4EP-Portal

Konkrete Anleitung für den laufenden Server unter
`https://portal.ref4ep.de`. Befehle bitte einzeln und mit Bedacht
ausführen — nichts blind hintereinander wegkopieren.

---

## 1. Voraussetzungen

| Element             | Wert                                                |
| ------------------- | --------------------------------------------------- |
| Serverpfad          | `/opt/ref4ep-portal`                                |
| Backendpfad         | `/opt/ref4ep-portal/backend`                        |
| Datenpfad           | `/opt/ref4ep-portal/data` (DB + Storage, gitignored)|
| Backup-Pfad         | `/opt/ref4ep-backups`                               |
| systemd-Dienst      | `ref4ep-portal.service`                             |
| Backup-Timer        | `ref4ep-backup.timer` (+ `ref4ep-backup.service`)   |
| Domain              | `portal.ref4ep.de`                                  |
| GitHub-Repo         | <https://github.com/KHolste/ref4ep-portal>          |

Annahmen:

- Python-Venv liegt unter `/opt/ref4ep-portal/backend/.venv/`.
- `.env`-Datei liegt unter `/opt/ref4ep-portal/.env` und enthält
  mindestens `REF4EP_DATABASE_URL`, `REF4EP_SESSION_SECRET`,
  `REF4EP_STORAGE_DIR`, `REF4EP_PUBLIC_BASE_URL`. `REF4EP_COOKIE_SECURE`
  ist standardmäßig `true` (HTTPS-only) und muss in `.env` nicht
  explizit gesetzt werden.
- `REF4EP_SESSION_SECRET` ist Pflicht und muss mindestens 32 Zeichen
  enthalten — der Server startet sonst mit klarer Fehlermeldung nicht.
- ASGI-Entrypoint: `ref4ep.api.asgi:app` (nicht mehr `ref4ep.api.app:app`).
  Die `ExecStart`-Zeile der systemd-Unit muss diesen Pfad nutzen.
- Befehle mit `sudo` sind nötig, sobald systemd betroffen ist.

---

## 2. Update-Prozess

Reihenfolge unbedingt einhalten. Vor jedem Update **erst Backup**.

```bash
# 1. SSH auf den Server
ssh portal.ref4ep.de

# 2. In das Repo wechseln
cd /opt/ref4ep-portal

# 3. Manuelles Backup ausführen (siehe §4)
sudo systemctl start ref4ep-backup.service

# 4. Lokalen Stand prüfen — sollte sauber sein
git status

# 5. Aktuellen Stand vom GitHub holen
git pull

# 6. Ins Backend wechseln
cd /opt/ref4ep-portal/backend

# 7. Umgebungsvariablen aus .env laden
set -a && source /opt/ref4ep-portal/.env && set +a

# 8. Python-Paket aktualisieren (editable install im venv)
.venv/bin/pip install -e .

# 9. Alembic-Migration anwenden
.venv/bin/alembic upgrade head

# 10. Dienst neu starten
sudo systemctl restart ref4ep-portal.service

# 11. Dienststatus prüfen — sollte "active (running)" sein
sudo systemctl status ref4ep-portal.service

# 12. HTTP/HTTPS-Funktion prüfen
curl -I https://portal.ref4ep.de/
curl -fsS https://portal.ref4ep.de/api/health
```

Nach Schritt 12 sollte `/api/health` ein JSON mit
`"status": "ok"` und `"db": "ok"` zurückgeben. Falls nicht:
sofort Logs prüfen (siehe §3) und im Zweifel über das Backup
zurückkehren.

---

## 3. Logs prüfen

```bash
# Aktueller Status (eine Bildschirmseite)
sudo systemctl status ref4ep-portal.service

# Letzte 100 Log-Zeilen, ohne Pager
sudo journalctl -u ref4ep-portal.service -n 100 --no-pager

# Live mitlesen (Strg-C zum Beenden)
sudo journalctl -u ref4ep-portal.service -f
```

---

## 4. Backup prüfen

```bash
# Timer-Plan anzeigen — wann läuft das nächste Backup?
systemctl list-timers ref4ep-backup.timer

# Vorhandene Backups auflisten
ls -lh /opt/ref4ep-backups/

# Manuelles Backup ausführen (gleiche Logik wie Timer)
sudo systemctl start ref4ep-backup.service

# Inhalt eines Archivs sichten (Beispiel mit jüngstem Archiv)
tar -tzf "$(ls -t /opt/ref4ep-backups/*.tar.gz | head -1)" | head
```

Im Archiv müssen DB-Dump und Inhalt von
`/opt/ref4ep-portal/data/storage/` enthalten sein.

---

## 5. Restore

**Restore nicht nebenbei ausführen.** Vorgehen:

1. Anleitung lesen: `cat /opt/ref4ep-backups/RESTORE.txt`
2. Dienst stoppen: `sudo systemctl stop ref4ep-portal.service`
3. Schritte aus `RESTORE.txt` befolgen.
4. Nach Restore: `sudo systemctl start ref4ep-portal.service`
   und Status + Health-Check wie in §2 Schritt 11/12.

---

## 6. Wichtige Warnungen

- **`.env` niemals nach GitHub hochladen.** Sie enthält das
  `REF4EP_SESSION_SECRET` und ggf. die DB-Zugangsdaten.
- **`data/` niemals nach GitHub hochladen.** Enthält DB-Datei
  und hochgeladene Dokumente.
- **Vor jedem Update ein Backup ausführen** — auch bei kleinen
  Änderungen.
- **Keine direkten Änderungen in `/opt/ref4ep-portal`**, die nicht
  über Git kommen. Lokale Edits gehen beim nächsten `git pull`
  verloren oder verursachen Merge-Konflikte.
- **Keine Befehle aus dieser Anleitung automatisch oder per
  Skript abarbeiten.** Jeder Schritt soll bewusst erfolgen,
  damit Fehler früh auffallen und nicht ein halbes Update
  hinterlassen.
