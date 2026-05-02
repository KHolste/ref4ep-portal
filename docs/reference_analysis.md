# Referenzanalyse: jluspaceforge (Labormanagement-System)

Diese Datei dokumentiert die Analyse des bestehenden Labormanagement-Systems
unter `jluspaceforge-reference/src/lab_management/` als technische Vorlage für
das neue Ref4EP-Projektportal. Es werden keine Änderungen am Referenzcode
vorgenommen.

Quelle: ausschließlich `jluspaceforge-reference/src/`, kein Git-Verlauf, keine
Deployment-Konfiguration.

---

## 1. Zusammenfassung der bestehenden Architektur

Das Labormanagement-System ist ein Full-Stack-Werkzeug für die Verwaltung von
Geräten, Chemikalien, Buchungen, Wartungsplänen, Wiki-Inhalten und
Sicherheitsschulungen in einem physikalischen Labor.

Die Struktur unter `src/lab_management/` ist deutlich nach Schichten getrennt:

| Paket            | Aufgabe                                                                 |
| ---------------- | ----------------------------------------------------------------------- |
| `domain/`        | SQLAlchemy-Modelle, Rollendefinitionen, Template-Engine                  |
| `services/`      | Geschäftslogik (28 Service-Module), Audit-Logger, Berechtigungsprüfung   |
| `api/`           | FastAPI-Anwendung, Routen, Schemas, Middleware, Auth                     |
| `web/`           | Vanilla-JavaScript-SPA, ausgeliefert als statische Dateien               |
| `ui/`            | PySide6-Desktop-Client (Qt-Widgets, Dialoge, eigene Views)               |
| `cli/`           | Admin-CLI für Nutzer- und API-Key-Verwaltung                             |
| `database.py`    | SQLAlchemy-Engine, Alembic-Migrationen                                   |
| `app_context.py` | Session- und Auth-Kontext für die Desktop-Anwendung                      |
| `main.py`        | Einstiegspunkt für den Desktop-Client                                    |

Charakteristische Designentscheidungen:

- **Dual-Frontend**: Es existieren zwei UIs auf demselben Backend — eine
  Web-SPA (`web/`) und eine native Qt-Anwendung (`ui/`). Beide sprechen die
  HTTP-API in `api/`.
- **Service-Layer-Pattern**: Routen sind dünn. Jede schreibende Operation
  läuft durch einen Service, der Rollen prüft und in den Audit-Log schreibt.
- **Soft-Delete und Append-only-Revisionen**: Datensätze werden i. d. R. nicht
  gelöscht, sondern als gelöscht markiert. Wiki-Revisionen sind unveränderlich.
- **Field-Definition-Registry**: Geräte- und Chemikalien-Templates beziehen
  Felder aus einer zentralen Tabelle `FieldDefinition`, statt sie pro Vorlage
  zu duplizieren.

---

## 2. Backend-Framework

- **Framework**: FastAPI mit Uvicorn als ASGI-Server.
- **Einstiegspunkt**: `api/app.py` mit Factory-Funktion `create_app()`.
  Aufruf: `uvicorn lab_management.api.app:app`.
- **Konfiguration**: `api/config.py` mit `Settings`-Objekt, das aus
  Umgebungsvariablen geladen wird (`LAB_DATABASE_PATH`, `LAB_SESSION_SECRET`,
  `LAB_ENV`, Logging-Format, Rate-Limits, CORS).
- **Middleware**: `api/middleware/` enthält `RequestIDMiddleware`,
  `ClientIPMiddleware`, `RequestLoggingMiddleware`. CSRF-Prüfung über
  `check_csrf()` in `api/deps.py`.
- **Dependency Injection**: `api/deps.py` liefert Session-Factory,
  Auth-Kontext (`get_current_user`) und CSRF-Prüfung.
- **Routen-Registrierung**: Pro Domäne ein Router-Modul unter
  `api/routes/` (über 30 Module: `devices`, `chemicals`, `bookings`,
  `wiki`, `wiki_attachments`, `events`, `maintenance`, `training`,
  `training_admin`, `users`, `keys`, `audit`, `backup`, `dashboard`,
  `search`, `ingest`, `measurements`, `form_center`, `lookups`,
  `admin_health`, `attachments`, `categories`, `chemical_fields`,
  `device_groups`, `exports`, `facilities`, `locations`, `templates`,
  `auth`). Jeder Router wird per `app.include_router()` eingebunden.
- **Schemas**: Pydantic-Modelle in `api/schemas/` für Request/Response.
- **Rate Limiting**: `api/rate_limit.py`, decorator-basierte Limits pro
  Endpunkt.
- **ORM**: SQLAlchemy mit Alembic für Schemamigrationen
  (`database.py` enthält Engine-Setup und Migrationsanstoß).
- **Standarddatenbank**: SQLite (Pfad über `LAB_DATABASE_PATH`).

---

## 3. Frontend-Struktur

Es gibt **zwei Frontends gegen dieselbe API**:

### 3.1 Web-SPA (`web/`)

- Reines HTML/CSS/Vanilla-JavaScript, **kein Framework**.
- `web/index.html` ist das Shell mit Tab-Leiste und Modul-Container.
- `web/app.js` enthält den SPA-Router (`switchModule()`), den Auth-State
  (Cookie `lab_session`) und Sichtbarkeitsregeln basierend auf der Rolle.
- Pro fachlichem Modul eine eigene JS-Datei: `devices.js`, `chemicals.js`,
  `bookings.js`, `bookings_calendar.js`, `bookings_favorites.js`,
  `wiki.js`, `events.js`, `events_calendar.js`, `maintenance.js`,
  `dashboard.js`, `measurements.js`, `form_center.js`, `training.js`,
  `training_admin.js`, `users.js`, `keys.js`, `audit_history.js`,
  `attachments.js`, `chemical_fields.js`, `device_groups.js`,
  `templates.js`, `locations.js`, `search.js`, `admin_health.js`,
  `field_inputs.js`, `dual_list.js`.
- Auslieferung: FastAPI hängt das `web/`-Verzeichnis als statische Route ein.
- Login: HTML-Loginscreen sendet `POST /api/auth/login`, danach Cookie-Session.

### 3.2 Desktop-Client (`ui/`)

- PySide6 (Qt) mit `MainWindow` und Tab-basierten Views.
- Views: `devices_view.py`, `chemicals_view.py`, `calendar_view.py`,
  `dashboard_view.py` u. a.
- Dialoge: `device_dialogs.py`, `chemical_dialogs.py`, `login_dialog.py`,
  `import_dialog.py`.
- Eigene Widgets: `widgets/` mit `DynamicFormWidget` und Field-Inputs für
  die dynamische Field-Definition-Engine.
- Start: `main.py` instanziert `QApplication`, prüft Authentifizierung über
  `app_context.py`, öffnet bei Bedarf den Login-Dialog und zeigt
  `MainWindow`.

> Hinweis: Beide Frontends greifen über die HTTP-API zu. Das Backend ist
> daher tatsächlich „headless", die Frontends sind austauschbar.

---

## 4. Datenbank- und Modellstruktur

ORM: **SQLAlchemy**, Schema in `domain/models.py`. Migrationen mit
**Alembic**. Standarddatenbank: SQLite.

Wichtige Entitäten (aus `domain/models.py` ableitbar):

- **Nutzer und Auth**
  - `User` — Login-Konto: `username`, `password_hash`, `role`, `is_active`,
    `must_change_password`.
  - `ApiKey` — persistente API-Keys (gehasht, optional Scope-Whitelist).

- **Stamm- und Hilfsdaten**
  - `Location` — Gebäude/Raum, gemeinsam von Geräten und Chemikalien genutzt.
  - `FieldDefinition` — zentrales Feld-Register (Key, Label, Typ, Pflicht,
    Validierung, Optionen).

- **Geräte**
  - `DeviceCategory`, `DeviceTemplate`, `Device` — Hierarchie:
    Kategorie → Template → konkrete Instanz mit `field_values`-Snapshot.
  - Junction-Tabellen `CategoryField`, `TemplateField` zur Wiederverwendung
    von Felddefinitionen.

- **Chemikalien**
  - `Chemical` mit CAS-Nummer, Gefahreninformationen (JSON), Menge,
    Lagerklasse.

- **Wartung**
  - `MaintenanceSchedule` — Plan: Typ, Intervall, nächster Termin.
  - `MaintenanceEvent` — Durchführung: durchgeführt von, Ergebnis, Notizen.

- **Kalender und Buchung**
  - `CalendarEvent` mit Recurrence (täglich/wöchentlich/monatlich), berechnet
    Vorkommen on-demand.
  - `OccurrenceException` — Override pro Vorkommen (Verschiebung,
    Streichung, Umbenennung).
  - `TestFacility` — sieben vorgesetzte Anlagen (JUMBO, BigMac, Obelix,
    Idefix, EVA, EMUC, iPott).
  - `FacilityBooking` mit Statusworkflow `angefragt` → `bestaetigt` →
    `abgeschlossen` / `storniert`.

- **Wiki**
  - `WikiPage` — Titel, Slug, Markdown, Status (`draft`/`published`/
    `archived`).
  - `WikiPageRevision` — append-only, monoton steigende
    `revision_number`.

- **Sicherheitsschulungen**
  - `SafetyTrainingCourse`, `SafetyTrainingSlide`,
    `SafetyTrainingQuestion`, `SafetyTrainingAttempt` — Slide-basierte
    jährliche Schulung mit Fragen und Score.

- **Anhänge**
  - `Attachment` — generisches Attachment via `entity_type` + `entity_id`,
    Speicherung im Dateisystem.

Querschnittsmuster:

- **`SoftDeleteMixin`** für die meisten Geschäftsobjekte
  (`is_deleted`-Flag, kein hartes Löschen).
- **Append-only-Revisionen** für Wiki.
- **Audit-Log**-Tabelle, beschrieben durch `services/audit_logger.py`.

---

## 5. Authentifizierung und Nutzerverwaltung

Zwei Authentifizierungsmechanismen, beide produktionsreif:

### 5.1 Session-Cookie (Browser- und Desktop-Logins)

- `POST /api/auth/login` mit Username/Passwort.
- Verifikation in `UserService.authenticate()`.
- Passwort-Hashing: **Argon2id** (`argon2-cffi`) mit transparenter
  Migration aus Legacy-SHA-256-Hashes beim ersten erfolgreichen Login.
- Bei erfolgreichem Login: HMAC-signiertes Session-Token im Cookie
  `lab_session` (`HttpOnly`, `SameSite=Lax`, 7 Tage).
- Token-Erstellung in `api/deps.py` (`create_session_token()`),
  Token-Geheimnis aus `LAB_SESSION_SECRET`.
- Mindestlänge Passwort: 8 Zeichen. `must_change_password` erzwingt
  Wechsel beim nächsten Login.

### 5.2 API-Keys (programmatischer Zugriff)

- Header `X-API-Key`.
- Nur SHA-256-Hash in der DB, Klartext nur einmalig bei der Erstellung.
- Optionaler Scope (z. B. `"ingest:write"`) für Messdaten-Ingest.
- In-Memory-Registry beim Start; Scope-Prüfung pro Endpunkt.

### 5.3 CLI-Verwaltung

- `cli/admin.py` mit Befehlen:
  - `lab-management-admin users list/create/reset-password/enable/disable/set-role`
  - `lab-management-admin keys create/list/rotate/delete`
- Passwortabfrage über `getpass`, niemals als CLI-Argument.
- Aktionen werden mit `actor_id="cli-admin"` im Audit-Log vermerkt.

### 5.4 CSRF

- `check_csrf()`-Dependency für zustandsverändernde Routen.
- Cookie- und Header-basierte Validierung in `api/deps.py`.

---

## 6. Rollen- und Rechtekonzept

Definiert in `domain/roles.py`:

```python
VALID_ROLES = ("admin", "user", "reader")
```

| Rolle    | Bedeutung                                                                |
| -------- | ------------------------------------------------------------------------ |
| `admin`  | Vollzugriff: Nutzer, Templates, Kategorien, Felder + alle Schreibrechte. |
| `user`   | Lesen + Schreiben: Geräte und Chemikalien anlegen, ändern, löschen.      |
| `reader` | Nur Lesen.                                                               |

Helfer:

- `can_write(role)` → `True` für `admin`/`user`.
- `can_admin(role)` → `True` nur für `admin`.

Durchsetzung:

- **Service-Layer**, nicht im Routendekorator. Jeder Service erhält im
  Konstruktor `role` und `user_id`, schreibende Operationen rufen intern
  `_require_write()` oder `_require_admin()` und werfen `PermissionError`.
- Routen mappen `PermissionError` auf HTTP 403.
- Es gibt **keine** Pro-Ressource-ACLs, keine Gruppen, keine projektbasierten
  Rechte. Die Rolle ist global pro Nutzer.

---

## 7. Wiki-Modul

Implementiert in `services/wiki_service.py` und `api/routes/wiki.py`.

Datenmodell:

- `WikiPage`: `title`, `slug`, `content` (Markdown), `status`
  (`draft`/`published`/`archived`).
- `WikiPageRevision`: pro Speichern ein neuer Eintrag mit monoton
  steigender `revision_number`. Restore kopiert eine alte Revision
  zurück und schreibt eine neue Revision (kein Verlust der Historie).

Rendering und Sicherheit:

- Markdown wird per `markdown` zu HTML, danach durch `bleach` mit einer
  Whitelist (`p`, `h1`–`h6`, `strong`, `em`, `a`, `table`, `code`,
  `blockquote`, `ul`, `ol`, `img`) gefiltert.
- Externe URLs und `data:`-URIs sind blockiert.
- Kein Rendering-Cache, HTML wird pro Request neu berechnet.
- Wiki-Anhänge werden ausschließlich über
  `/api/wiki/pages/...`-Pfade ausgeliefert.

Slugs:

- Generiert aus dem Titel, kleingeschrieben, Bindestriche.
- Soft-deleted Pages blockieren keinen Slug.
- Slugs bleiben nach Erstellung stabil; Änderung nur über Manualfeld.

---

## 8. Termin-, Kalender- und Buchungslogik

Drei unabhängige Subsysteme.

### 8.1 Kalender (`CalendarEvent`, `OccurrenceException`)

- Recurrence-Regeln: `none`/`daily`/`weekly`/`monthly`.
- **Kein** Materialisieren der Vorkommen — `services/calendar_service.py`
  berechnet sie auf Anfrage.
- Pro Vorkommen kann eine Ausnahme gespeichert werden (Verschiebung,
  Umbenennung, Ortwechsel, Streichung).
- Owner darf eigenes Event löschen, Admin alle.

### 8.2 Anlagenbuchung (`FacilityBooking`, `TestFacility`)

- Tagesgenau: `start_date`, `end_date` (inklusive), keine Untertagesblöcke.
- Sieben fest verdrahtete Anlagen, idempotent geseedet beim App-Start
  in `_ensure_seed_facilities()` (`api/app.py`).
- Statusworkflow: `angefragt` → `bestaetigt` → `abgeschlossen` /
  `storniert`.
- Konflikterkennung in `BookingService._detect_conflicts()`: bestätigte
  Buchungen dürfen sich pro Anlage nicht überlappen. Anfragen dürfen
  überlappen (nur Hinweis). Admin kann mit `force=True` überschreiben.

### 8.3 Wartung (`MaintenanceSchedule`, `MaintenanceEvent`)

- Plan: `maintenance_type`, `interval_days`, `next_due`.
- Event: tatsächliche Durchführung mit `performed_at`, `performed_by`,
  Ergebnis, Notizen.
- Status: `offen`, `ueberfaellig` (berechnet), `erledigt`, `storniert`.
- UI bekommt Tage-bis-fällig und eine `status_color`
  (rot/gelb/grün/grau).

---

## 9. Attachment- und Datei-Modul

Modell: `Attachment` mit generischer Bindung über
(`entity_type`, `entity_id`).

Speicherung:

- Pfad: `~/.lab_management/attachments/<entity_type>/<entity_id>/`.
- Dateiname auf der Platte ist eine UUID, der ursprüngliche Name wird
  in der DB gehalten.
- **Keine** explizite Versionsspalte. Mehrere Attachments pro Entity
  sind das Versionierungsmuster.

Service: `services/attachment_service.py`

- `add_attachment()` validiert Endung (Standard: `pdf`, `jpg`, `jpeg`,
  `png`).
- Maximalgröße: 50 MB (konfigurierbar).
- Jede Aktion durchläuft `audit_logger.log_action()`.

API: `api/routes/attachments.py` und für Wiki separat
`api/routes/wiki_attachments.py`.

- `GET /api/devices/{id}/attachments` — Liste
- `POST /api/devices/{id}/attachments` — Upload mit `document_type`,
  `title`, `description`
- `GET /api/devices/{id}/attachments/{file_id}` — Download

---

## 10. Was sich als Vorlage für Ref4EP eignet

Die folgenden Bausteine sind übertragbar und passen gut zum
Anforderungsprofil eines Projektportals:

1. **Schichtenarchitektur** — saubere Trennung
   `domain` → `services` → `api` → `web`. Diese Trennung sollte für
   Ref4EP übernommen werden, weil sie das Hinzufügen weiterer Module
   (Deliverables, Reviews, Messkampagnen) erlaubt, ohne Routen oder UI
   zu kreuzen.
2. **FastAPI + Pydantic + SQLAlchemy + Alembic** als Backend-Stack —
   ausgereift, gut dokumentiert, klein im Footprint.
3. **Service-Layer-Pattern mit Audit-Log und Rollenprüfung**. Genau das,
   was eine konsortiale Plattform mit Nachvollziehbarkeitspflicht
   braucht.
4. **Append-only-Revisionen** (wie im Wiki): direkt nutzbar für
   Dokumente, Deliverables, Beschlussprotokolle und Review-Kommentare.
   Jede Änderung bleibt nachvollziehbar.
5. **Soft-Delete-Muster** — wichtig für Auditierbarkeit in einem
   geförderten Projekt.
6. **`FieldDefinition`-Registry** — sehr nützlich für
   Metadatenregister und projektbezogene Felder pro Dokumenttyp
   (z. B. „Deliverable D3.1 hat zusätzliches Feld:
   Demonstrator-ID").
7. **Argon2id-Passwort-Hashing, HMAC-Session-Cookies, scoped
   API-Keys, CSRF** — direkt übernehmbar.
8. **Markdown-Rendering mit `bleach`-Whitelist** — passt 1:1 für das
   Referenzdiagnostik-Wiki.
9. **Konflikterkennung bei Buchungen** — direkt nutzbar für die
   Messkampagnen- und Testplanung (Anlagen, Prüfstände, Diagnostiken).
10. **Idempotentes Startseed** (`_ensure_seed_facilities`) — gutes
    Muster für die Initialbefüllung von Arbeitspaketen, Partnern und
    Deliverables aus der Projektantragsstruktur.
11. **CLI-Admin** für Nutzer- und Key-Verwaltung — schlank, ohne
    eigenen Webflow.
12. **Generisches `Attachment`-Modell** — taugt als Ausgangspunkt für
    den Dokumentenspeicher.

---

## 11. Was für Ref4EP bewusst anders oder schlanker gebaut werden sollte

Mehrere Designentscheidungen passen explizit **nicht** zum
Projektportal-Profil und sollten nicht übernommen werden:

1. **Kein Dual-Frontend.** Die Qt-Desktop-App (`ui/`) hat im
   Konsortium keinen Anwendungsfall. Ref4EP braucht ein einziges
   Web-Frontend.
2. **Vanilla-JS-SPA ist zu eng**. Für Dashboards, Reviewing,
   Kommentar-Threads und ein Arbeitspaket-Cockpit ist ein modernes
   Frontend-Framework angemessen (Vorschlag: SvelteKit oder Next.js mit
   serverseitigem Rendering, optional HTMX falls bewusst leichtgewichtig
   gewünscht). Pro Modul eine eigene `*.js`-Datei mit handgeschriebenem
   Routing skaliert nicht für die geplanten zwölf Module.
3. **Globale Rollen reichen nicht.** `admin`/`user`/`reader` ist zu grob
   für ein Konsortium. Ref4EP braucht mindestens:
   - Mitgliedschaft pro **Partnerorganisation**.
   - Rolle pro **Arbeitspaket** (WP-Lead, WP-Mitglied, Beobachter).
   - Sichtbarkeitsstufe pro **Dokument/Deliverable**
     (öffentlich / Konsortium / WP / Förderer).
   - Optional: Reviewer-Rolle pro Deliverable-Instanz.
4. **Keine Projektkontextfelder am Datenmodell.** Im Referenzsystem
   sind Geräte und Chemikalien projektneutral. Ref4EP muss umgekehrt
   denken: jedes domänenspezifische Objekt (Dokument, Deliverable,
   Messkampagne, Beschluss) trägt zwingend Arbeitspaket, Status, Version,
   Autor/Partner und Freigabezustand.
5. **Keine Modul-Mischung Labor + Projekt.** Geräte-, Chemikalien-,
   Sicherheitsschulungs- und Wartungs-Module sind hier nicht relevant
   und sollten nicht mitgezogen werden.
6. **Kalender ist zu generisch, Buchung zu spezifisch.** Für Ref4EP
   reicht zunächst eine Meilenstein- und Messkampagnen-Sicht; die
   tagesgenaue Anlagenbuchung mit sieben festen Anlagen ist nicht
   übertragbar. Die zugrunde liegende Konfliktlogik ist trotzdem ein
   gutes Muster, falls später Diagnostik-Slots geplant werden.
7. **SQLite als Standarddatenbank ist für ein Portal mit
   externer Sichtbarkeit und mehreren Partnern grenzwertig.** Vorschlag:
   PostgreSQL als Standard, SQLite optional für Entwicklung.
   `~/.lab_management/attachments/...` als Speicherpfad eignet sich
   ebenfalls nicht für eine Mehrnutzer-Serverumgebung; stattdessen ein
   konfigurierbares Object-Storage- oder Filesystem-Backend.
8. **Attachments ohne Versionsspalte.** Für ein Dokumentenregister mit
   Deliverable-Versionen reicht das Muster „mehrere Attachments pro
   Entity" nicht. Ref4EP braucht ein explizites `Document` mit
   Versionen, Status, Änderungsnotiz, Freigeber, ggf. Hash.
9. **Audit-Log ist gut, aber zu serviceintern.** Für Ref4EP sollte das
   Audit-Log auch im UI sichtbar sein (pro Dokument/Deliverable eine
   Historie), nicht nur als Admin-Inspektion.
10. **Login-Konzept zu lokal.** Konsortien bestehen typischerweise aus
    mehreren Hochschulen mit eigenem IDP. Ref4EP sollte SSO/OIDC
    (Shibboleth/AAI, ggf. DLR-IDP) von Anfang an einplanen — lokale
    Accounts nur als Fallback. Argon2id und Session-Cookies bleiben für
    den Fallback gültig.
11. **Keine öffentliche Zone.** Das Referenzsystem ist hinter Login
    komplett geschlossen. Ref4EP braucht zwei klar getrennte Zonen
    (öffentliche Projektseite + öffentliche Download-Bibliothek vs.
    geschützter Projektbereich), idealerweise als zwei getrennte
    Render-Pfade gegen dieselbe API.

---

## 12. Vorschlag für einen ersten MVP (rein konzeptionell)

Der MVP soll bewusst klein sein und das **Skelett** der späteren
Plattform tragen, ohne fachliche Tiefe vorzutäuschen. Empfehlung: drei
vertikale Schnitte, die zusammen ein nutzbares Cockpit ergeben und das
Datenmodell tragfähig machen.

### Vertikale 1 — Projektgrundgerüst und Identität

- Datenmodell: `Partner`, `Person` (mit Partnerzugehörigkeit),
  `Workpackage`, `Membership` (Person × Workpackage × Rolle).
- Login: lokal (Argon2id, Session-Cookie wie Referenz). SSO als
  Architekturplatzhalter (Auth-Adapter), aber noch nicht
  implementiert.
- UI: Partner- und Kontaktbereich (Punkt 8 der Zielliste) plus
  Arbeitspaket-Übersicht ohne Tiefen-Funktionen — nur Liste, Lead,
  Mitglieder, Kurzbeschreibung.

### Vertikale 2 — Dokumentenregister mit Projektkontext

- Datenmodell: `Document` mit Pflichtfeldern Arbeitspaket, Status
  (`draft`/`in_review`/`released`), `version` (semver oder D-Nummer),
  Autor (Person/Partner), Freigeber, Änderungsnotiz.
- `DocumentRevision` als append-only Tabelle (Muster aus dem Wiki
  übernehmen).
- `DocumentFile` als Speicherobjekt mit Hash, MIME, Größe; Auslieferung
  über signierte URLs.
- UI: Dokumentenliste pro Arbeitspaket, Detailansicht mit Versionen,
  Upload neuer Version mit Pflichtfeld „Änderungsnotiz".

### Vertikale 3 — Öffentliche Projektseite und Download-Bibliothek

- Renderpfad ohne Login. Liest aus denselben Tabellen, aber filtert
  strikt auf `visibility = "public"` und `status = "released"`.
- Inhalte: Projektsteckbrief (statisch oder als Wiki-Page mit Flag
  „public"), Liste öffentlicher Deliverables mit Version und
  Veröffentlichungsdatum.

### Bewusst noch nicht im MVP

- Messkampagnen- und Testplanung (Vertikale später, sobald die
  Diagnostik-Anlagen bekannt sind).
- Review-Workflow (erst sinnvoll, sobald das Dokumentenregister benutzt
  wird).
- Daten- und Metadatenregister (braucht eine FAIR-Diskussion mit dem
  Konsortium).
- Referenzdiagnostik-Wiki (kann auf der Wiki-Logik der Referenz
  aufbauen, sobald die Inhalte stehen).
- Beschlussdatenbank (sobald die ersten Sitzungen anstehen).

### Empfohlener technischer Stack für den MVP

- Backend: Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL.
- Auth: Argon2id, HMAC-signierte Cookies, CSRF-Middleware (Muster aus
  Referenz). Auth-Adapter so geschnitten, dass OIDC später ohne
  Routenumbau ergänzt werden kann.
- Frontend: ein einziges modernes Web-Frontend mit serverseitigem
  Rendering (Vorschlag: SvelteKit oder Next.js). Öffentliche und
  geschützte Zone über getrennte Routenpräfixe.
- Storage: lokales Filesystem hinter einem Storage-Interface, das später
  auf S3/MinIO geswitcht werden kann.
- Audit-Log: von Anfang an pro schreibender Service-Operation, im UI
  sichtbar pro Dokument/Deliverable.

### Erfolgskriterien des MVP

1. Ein Konsortialpartner kann sich einloggen, sein Arbeitspaket sehen,
   ein Dokument hochladen, eine neue Version mit Änderungsnotiz
   einspielen und die Versionshistorie nachvollziehen.
2. Eine externe Person kann ohne Login die Projektseite öffnen und ein
   freigegebenes Deliverable herunterladen.
3. Jede schreibende Aktion ist im Audit-Log sichtbar — sowohl für
   Admins als auch in der Dokumenthistorie.
