# Nächste Schritte — Zwischenstand nach MVP

Stand der Arbeit: das Portal läuft lokal vollständig durch. Bevor
es im Konsortium genutzt werden kann, sind ein paar
organisatorische und betriebliche Punkte zu klären. Diese Datei
hält den aktuellen Stand, die offenen Fragen und einen Vorschlag
für die nächsten technischen Schritte fest.

---

## 1. Was aktuell umgesetzt ist

- **Grundgerüst** — FastAPI + SQLAlchemy + Alembic + statisch
  ausgeliefertes HTML/CSS und Vanilla-JS. Lokaler Default ist
  SQLite, PostgreSQL ist später ohne Codeumbau möglich.
- **Login und Projektstruktur** — lokale Accounts mit Argon2id-
  Passwörtern, signierte Session-Cookies, CSRF-Schutz.
- **Partner, Arbeitspakete, Personen, Mitgliedschaften** — vom
  Konsortium-Antrag verbindlich befüllt (5 Partner, 8 Haupt-
  und 27 Unterarbeitspakete).
- **Dokumentenregister** mit Workpackage-Bezug, Typ,
  Dokumentcode und freier Beschreibung.
- **Versionierung** — append-only, Pflicht-Änderungsnotiz pro
  Upload, SHA-256, MIME-Whitelist und Größenlimit.
- **Audit-Log und Freigabe-Workflow** — jede schreibende Aktion
  ist nachvollziehbar; Status `draft → in_review → released` mit
  expliziter Wahl der freigegebenen Version, Sichtbarkeit
  `workpackage / internal / public`.
- **Öffentliche Download-Bibliothek** unter `/downloads`, zeigt
  ausschließlich `public + released + nicht gelöscht`.
- **Admin-Oberfläche** im Browser für Personen, Partner,
  WP-Mitgliedschaften und Audit-Sicht.
- **GitHub-Repository mit grüner CI** — alle Tests laufen, Lint
  und Format sind sauber.

Insgesamt ~230 automatische Tests, Coverage rund 89 %.

---

## 2. Was vor echter Nutzung noch zu klären ist

Diese Punkte sind keine Code-, sondern Entscheidungs- und
Betriebsfragen:

- **Verantwortlicher Betreiber.** Wer trägt die DSGVO-
  Verantwortung — JLU, Konsortium, DLR? Davon hängen Impressum
  und Datenschutz ab.
- **Impressums- und Datenschutztexte.** Aktuell stehen
  Platzhalter; müssen durch den Verantwortlichen ergänzt werden.
- **Nutzerkreis.** Nur Konsortialpartner, oder auch externe
  Reviewer/Stakeholder? Davon hängt die SSO-Frage ab.
- **Passwort- und Einladungsprozess.** Aktuell legt der Admin
  Personen an und übergibt das Initialpasswort persönlich. Reicht
  das, oder soll später eine E-Mail-Einladung kommen?
- **Umgang mit öffentlichen Dokumenten.** Welche Deliverables
  sollen tatsächlich öffentlich sichtbar werden? Wer entscheidet
  das pro Dokument? Aktuell kann das jeder WP-Lead selbst.
- **Backup-Konzept.** Wie oft, wohin, wer testet das Restore?
- **Speicherort für Dateien.** Aktuell lokales Filesystem unter
  `data/storage`. Soll es perspektivisch ein Netzlaufwerk oder
  ein Object-Storage werden?
- **SQLite lokal vs. PostgreSQL produktiv.** Für Mehrbenutzer-
  Betrieb mit gleichzeitigen Schreibzugriffen ist PostgreSQL
  robuster. Migration ist im Code vorbereitet (DB-URL umstellen,
  Alembic neu aufsetzen).
- **Domain bzw. Subdomain** für die produktive Installation.
- **Serverdienst (systemd-Unit)** — Start, Stopp, Logs.
- **Reverse-Proxy (nginx)** — TLS-Terminierung, Größenlimits.
- **SSL/TLS-Zertifikat.** Let's Encrypt oder
  Hochschul-Zertifikat?
- **Testdaten entfernen.** Die lokale `data/ref4ep.db` enthält
  jetzt Test-Personen, Test-Dokumente und Test-Storage-Dateien.
  Vor dem Produktiv-Aufsetzen leer starten oder gezielt
  importieren.
- **Erster Produktiv-Admin.** Wer wird der erste Account, der
  per CLI angelegt wird? Wie wird das Initialpasswort übergeben?

---

## 3. Vorschlag für die nächsten technischen Schritte

Diese Reihenfolge minimiert Risiko und vermeidet, dass das
Deployment zu früh läuft, bevor die organisatorischen Punkte
geklärt sind.

1. **Lokale Testdaten bereinigen.** `data/ref4ep.db` und
   `data/storage/` zurücksetzen, Migration neu anwenden, dann
   einen frischen Stand erzeugen. Damit sind die nächsten Tests
   vergleichbar.

2. **Produktionskonfiguration entwerfen.** Eine `.env.production`
   oder ein Settings-Profil für: PostgreSQL-URL, längeres
   Session-Secret, `cookie_secure=true`, abweichendes Storage-
   Verzeichnis, Public-Base-URL.

3. **Deployment-Plan schreiben** (`docs/deployment_plan.md`):
   Zielserver, Benutzer, Pfade, Versionierung der Releases,
   Rollback-Strategie. Noch ohne Code, nur als Schritt-für-
   Schritt-Beschreibung.

4. **Serverpfade festlegen** — z. B.
   `/opt/ref4ep/app`, `/var/lib/ref4ep/data`,
   `/var/log/ref4ep`. Konsistent über systemd-Unit, nginx-Config
   und Backup-Skript.

5. **systemd- und nginx-Vorlagen erstellen** — als
   `infra/systemd/ref4ep.service` und `infra/nginx/ref4ep.conf`.
   Aktuell gibt es nur Platzhalter-Verzeichnisse.

6. **Backup/Restore dokumentieren** — `docs/backup_restore.md`
   mit Befehlen für DB-Dump, Storage-rsync, Retention,
   Restore-Testlauf.

7. **Erst danach Deployment durchführen.** Reihenfolge: Server
   einrichten, App installieren, Migration ausführen,
   Initial-Admin per CLI anlegen, Initial-Seed der Konsortium-
   Daten, dann das Konsortium freischalten.

Bis zu diesem Punkt sind alle Schritte reine Dokumentation und
Konfiguration — kein Code im Portal selbst muss verändert
werden.

---

## Status in einem Satz

Der MVP ist funktional fertig; die nächsten Wochen drehen sich
um Klärung des Betriebs (Wer? Wo? Wie?) und das Schreiben der
Deployment-Anleitung — nicht mehr um Features.
