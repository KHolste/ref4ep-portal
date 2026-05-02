# MVP-Spezifikation: Ref4EP-Projektportal

Diese Spezifikation legt verbindlich fest, was das erste lauffähige
Ref4EP-Projektportal können muss und was bewusst nicht enthalten ist.
Sie baut auf `docs/reference_analysis.md` auf.

Charakter: pragmatisch, umsetzungsnah, dünn. Der MVP soll ein
tragfähiges Skelett liefern — kein vollständiges Portal.

---

## 1. Ziel des MVP

Ein eigenständig lauffähiges Web-Portal mit drei nachweisbaren
Fähigkeiten:

1. **Identität und Projektstruktur** — Konsortialpartner, Personen und
   Arbeitspakete sind als erste Klasse abgebildet. Eine Person meldet
   sich an, sieht ihre Arbeitspakete, ihre Partnerorganisation und die
   Mitglieder ihres Arbeitspakets.
2. **Versioniertes Dokumentenregister mit Projektkontext** — eine
   berechtigte Person lädt ein Dokument zu einem Arbeitspaket hoch,
   spielt eine neue Version mit Pflicht-Änderungsnotiz ein, sieht die
   vollständige Versionshistorie und kann eine bestimmte Version als
   freigegeben markieren.
3. **Öffentliche Download-Bibliothek** — eine externe Person ohne Login
   öffnet die Projektseite, sieht alle als öffentlich freigegebenen
   Deliverables und lädt sie herunter.

Querschnittsanforderung: jede schreibende Aktion ist auditierbar.

**Fertigkriterium des MVP:**

- Eine Demo mit echten Konsortialdaten (Partner, Personen, Arbeitspakete)
  läuft auf einer einzelnen Instanz.
- Ein WP-Lead kann ein Deliverable in mindestens zwei Versionen
  hochladen, freigeben und im öffentlichen Bereich sehen.
- Ein anonymer Browser kann das freigegebene Deliverable von der
  öffentlichen Seite herunterladen.
- Ein Administrator kann im Audit-Log nachvollziehen, wer wann was
  geändert hat.

---

## 2. Nicht-Ziele des MVP

Bewusst **nicht** im MVP:

- Messkampagnen- und Testplanung, Diagnostik-Slots, Anlagenbuchung.
- Review-Workflow (Kommentare, Genehmigungs-Pipeline, Reviewer-Rollen).
- Wiki-Modul (Markdown-Seiten, Revisionen, interne
  Wissensdatenbank).
- Daten- und Metadatenregister (FAIR, DOI, Datensätze).
- Beschluss- und Protokolldatenbank.
- Meilenstein-Tracker mit Gantt-Sicht oder Abhängigkeiten.
- Kalender, Termine, Erinnerungen.
- E-Mail-Benachrichtigungen, Webhooks, Slack-Integration.
- Volltextsuche über Dokumentinhalte.
- SSO/OIDC (Shibboleth, DLR-IDP). Auth-Adapter wird so geschnitten,
  dass SSO später nachrüstbar ist; im MVP nur lokale Accounts.
- Mehrsprachigkeit. MVP ist deutschsprachig.
- Kommentare, Mentions, Threads, Aktivitäts-Feed.
- Mobile-App, native Clients.
- Migrations-Importer aus Altsystemen.
- Übernahme der Module Geräte, Chemikalien, Wartung, Sicherheits-
  schulungen aus dem Referenzsystem.
- Öffentliche API für Dritte. Die HTTP-API ist für das eigene Frontend.

---

## 3. Nutzerrollen im MVP

Vier Rollenbilder. Eine Person hat genau **eine** globale
Plattformrolle und kann zusätzlich pro Arbeitspaket eine WP-Rolle
tragen.

### Globale Plattformrolle

| Rolle    | Bedeutung                                                                         |
| -------- | --------------------------------------------------------------------------------- |
| `admin`  | Plattformverwaltung: Partner, Personen, Arbeitspakete, Mitgliedschaften, Audit.   |
| `member` | Eingeloggter Konsortiumsangehöriger. Sieht und bearbeitet, was seine WPs erlauben. |

Anonyme Besucher haben keine Plattformrolle und keinen Account; sie
sehen nur die öffentliche Zone.

### WP-Rolle (pro Mitgliedschaft)

| WP-Rolle     | Bedeutung                                                                              |
| ------------ | -------------------------------------------------------------------------------------- |
| `wp_lead`    | Leitet das Arbeitspaket. Darf Versionen freigeben (`released`), darf Sichtbarkeit setzen. |
| `wp_member`  | Reguläres WP-Mitglied. Darf Dokumente anlegen, neue Versionen einspielen, lesen.       |

Eine Person ohne Mitgliedschaft in einem WP sieht dessen Drafts und
internen Inhalte nicht.

### Vereinfachungen im MVP

- Keine Reviewer-, Beobachter-, Gast- oder Förderer-Rollen.
- `admin` darf alles, was ein `wp_lead` darf, in jedem WP — ohne
  Mitgliedschaft.
- Eine Person ist immer genau einer Partnerorganisation zugeordnet.

---

## 4. Datenmodell im MVP

Tabellen und Pflichtfelder. Alle Tabellen haben zusätzlich `id`
(UUID v4), `created_at`, `updated_at`. Soft-Delete (`is_deleted`,
`deleted_at`) auf den Geschäftsobjekten, nicht auf reinen
Verknüpfungstabellen.

### `partner`

Konsortialpartner (Hochschule, Institut, Firma).

| Feld          | Typ          | Anmerkung                                  |
| ------------- | ------------ | ------------------------------------------ |
| name          | text         | Anzeigename, eindeutig                     |
| short_name    | text         | Kürzel, z. B. „JLU", „DLR"                 |
| country       | text         | ISO-3166-1 Alpha-2                         |
| website       | text, null   | Optional                                   |
| is_deleted    | bool         | Soft-Delete                                |

### `person`

Konsortiumsangehörige mit Login.

| Feld                   | Typ         | Anmerkung                                          |
| ---------------------- | ----------- | -------------------------------------------------- |
| email                  | text        | eindeutig, Login-Identifier                        |
| display_name           | text        | „Vorname Nachname"                                 |
| partner_id             | uuid → partner | Pflicht                                          |
| password_hash          | text        | Argon2id                                           |
| platform_role          | enum        | `admin` \| `member`                                |
| is_active              | bool        | Login möglich?                                     |
| must_change_password   | bool        | Initialpasswort                                    |
| is_deleted             | bool        | Soft-Delete                                        |

### `workpackage`

Arbeitspaket aus dem Projektantrag. Hierarchie zweistufig: Parent-WPs
(WP1, WP2, …) und Sub-WPs (WP1.1, WP1.2, …). Sub-WPs verweisen über
`parent_workpackage_id` auf ihren Parent.

| Feld                  | Typ                | Anmerkung                                                       |
| --------------------- | ------------------ | --------------------------------------------------------------- |
| code                  | text               | z. B. „WP1", „WP2.3", eindeutig                                 |
| title                 | text               | Kurzer Titel                                                    |
| description           | text               | Frei                                                            |
| parent_workpackage_id | uuid → workpackage, null | NULL für Parent-WPs, gesetzt für Sub-WPs                  |
| lead_partner_id       | uuid → partner     | Federführender Partner                                          |
| sort_order            | integer            | Reihenfolge in UI                                               |
| is_deleted            | bool               |                                                                 |

### `membership`

Person × Workpackage × WP-Rolle.

| Feld           | Typ                | Anmerkung                              |
| -------------- | ------------------ | -------------------------------------- |
| person_id      | uuid → person      | Pflicht                                |
| workpackage_id | uuid → workpackage | Pflicht                                |
| wp_role        | enum               | `wp_lead` \| `wp_member`               |

UNIQUE (`person_id`, `workpackage_id`).

### `document`

Logisches Dokument im Register. Trägt den Projektkontext, nicht die
Datei.

| Feld                 | Typ                  | Anmerkung                                                |
| -------------------- | -------------------- | -------------------------------------------------------- |
| workpackage_id       | uuid → workpackage   | Pflicht                                                  |
| title                | text                 | Anzeigetitel                                             |
| slug                 | text                 | URL-tauglich, eindeutig pro WP                           |
| document_type        | enum                 | `deliverable` \| `report` \| `note` \| `other`           |
| deliverable_code     | text, null           | Optional, z. B. „D2.1"                                   |
| status               | enum                 | `draft` \| `in_review` \| `released`                     |
| visibility           | enum                 | `workpackage` \| `internal` \| `public`                  |
| released_version_id  | uuid, null           | Zeigt auf eine Zeile in `document_version`               |
| created_by_person_id | uuid → person        | Erstanleger                                              |
| is_deleted           | bool                 |                                                          |

Konsistenzregeln (im Service-Layer geprüft):

- `released_version_id IS NOT NULL` ⇔ `status = 'released'`.
- `visibility = 'public'` ist nur sinnvoll für freigegebene Dokumente.
  Setzen erlaubt im Status `draft`/`in_review`, im UI greift die
  öffentliche Sichtbarkeit aber erst, sobald `status = 'released'`.

### `document_version`

Append-only. Eine Zeile pro Upload.

| Feld             | Typ                   | Anmerkung                                                       |
| ---------------- | --------------------- | --------------------------------------------------------------- |
| document_id      | uuid → document       | Pflicht                                                         |
| version_number   | integer               | Monoton steigend pro `document_id`, beginnt bei 1               |
| version_label    | text, null            | Frei, z. B. „v0.3", „D2.1-final"                                |
| change_note      | text                  | **Pflichtfeld**, mind. 5 Zeichen                                |
| storage_key      | text                  | Pfad/Key im Storage, intern                                     |
| original_filename| text                  |                                                                 |
| mime_type        | text                  |                                                                 |
| file_size_bytes  | integer               |                                                                 |
| sha256           | text                  | Hex                                                             |
| uploaded_by_person_id | uuid → person     |                                                                 |
| uploaded_at      | timestamp             |                                                                 |

UNIQUE (`document_id`, `version_number`). Keine Updates, keine Löschung
(Dateien können nur über Admin-Audit-Pfad entfernt werden — out of
scope für MVP).

### `audit_log`

| Feld           | Typ           | Anmerkung                                            |
| -------------- | ------------- | ---------------------------------------------------- |
| actor_person_id| uuid, null    | null = System/CLI                                    |
| action         | text          | z. B. `document.create`, `document_version.upload`,  |
|                |               | `document.release`, `document.set_visibility`        |
| entity_type    | text          | z. B. `document`                                     |
| entity_id      | uuid          |                                                      |
| details        | json          | Vorher/Nachher relevanter Felder                     |
| client_ip      | text          |                                                      |
| request_id     | text          |                                                      |
| created_at     | timestamp     |                                                      |

### `api_session`

Optional bei reiner Cookie-Auth nicht notwendig. MVP nutzt
**HMAC-signierte Cookies ohne Server-Session-Tabelle** (wie Referenz).
Eine Tabelle wird nicht angelegt.

### Nicht im MVP-Datenmodell

`milestone`, `meeting`, `decision`, `measurement_campaign`,
`wiki_page`, `dataset`, `review`, `comment`, `notification`,
`api_key`, `tag`. Bewusst weggelassen.

---

## 5. Seiten und Ansichten im MVP

Es gibt drei Zonen mit klar getrenntem Layout: **öffentlich**,
**intern**, **admin**. Pfade sind verbindlich, Designdetails nicht.

### Öffentlich (kein Login)

| Pfad                      | Inhalt                                                                                        |
| ------------------------- | --------------------------------------------------------------------------------------------- |
| `/`                       | Projektsteckbrief: Titel, Förderer, Laufzeit, Konsortialpartner-Logos, Kurzbeschreibung.       |
| `/partners`               | Liste der Konsortialpartner mit Land und Website.                                             |
| `/downloads`              | Öffentliche Download-Bibliothek (siehe §9).                                                   |
| `/downloads/{doc_slug}`   | Detail eines freigegebenen öffentlichen Dokuments mit aktueller Version und Download.         |
| `/legal/imprint`          | Impressum (Pflicht).                                                                          |
| `/legal/privacy`          | Datenschutzhinweis (Pflicht).                                                                 |
| `/login`                  | Login-Formular.                                                                               |

Die Inhalte von `/`, `/partners` und `/legal/*` werden im MVP aus
einer kleinen statischen Konfigurationsquelle (z. B. einer
`content.yaml` im Backend-Repo oder als gehärtete Markdown-Datei)
geliefert. Kein eigenes CMS-Modul.

### Intern (Login erforderlich, Rolle `member` oder `admin`)

| Pfad                                  | Inhalt                                                                  |
| ------------------------------------- | ----------------------------------------------------------------------- |
| `/portal`                             | Cockpit: meine Arbeitspakete, letzte 10 Aktivitäten, schneller Upload.  |
| `/portal/workpackages`                | Liste aller WPs, gefiltert auf sichtbare.                               |
| `/portal/workpackages/{wp_code}`      | WP-Detail: Beschreibung, Mitglieder, Dokumentenliste.                   |
| `/portal/documents/{doc_id}`          | Dokumentdetail mit Versionshistorie, Status, Sichtbarkeit, Aktionen.    |
| `/portal/documents/{doc_id}/upload`   | Formular: neue Version, Pflicht-Änderungsnotiz.                         |
| `/portal/partners`                    | Liste aller Partner und Personen (read-only).                           |
| `/portal/account`                     | Eigenes Profil, Passwort ändern.                                        |

### Admin (Rolle `admin`)

| Pfad                              | Inhalt                                                                |
| --------------------------------- | --------------------------------------------------------------------- |
| `/admin`                          | Admin-Cockpit: Anzahl Nutzer, WPs, Dokumente, Speicherbelegung.       |
| `/admin/partners`                 | CRUD Partner.                                                         |
| `/admin/persons`                  | CRUD Personen, Passwort-Reset auslösen, Aktivierung.                  |
| `/admin/workpackages`             | CRUD Arbeitspakete und Mitgliedschaften.                              |
| `/admin/audit`                    | Audit-Log mit Filtern (Person, Aktion, Entity, Zeitraum).             |

---

## 6. API-Endpunkte im MVP

REST-stil, JSON, Präfix `/api`. Authentifizierung über Cookie.
CSRF-Header (`X-CSRF-Token`) für alle nicht-GETs.

Schreibweise: `[Rolle]` = wer aufrufen darf.

### Auth

| Methode | Pfad                  | Zweck                                | Rolle               |
| ------- | --------------------- | ------------------------------------ | ------------------- |
| POST    | `/api/auth/login`     | Login mit E-Mail + Passwort          | anonym              |
| POST    | `/api/auth/logout`    | Session beenden                      | eingeloggt          |
| POST    | `/api/auth/password`  | Eigenes Passwort ändern              | eingeloggt          |
| GET     | `/api/me`             | Aktueller Account inkl. Memberships  | eingeloggt          |

### Stammdaten (lesend, intern)

| Methode | Pfad                                | Zweck                          | Rolle      |
| ------- | ----------------------------------- | ------------------------------ | ---------- |
| GET     | `/api/partners`                     | Liste Partner                  | eingeloggt |
| GET     | `/api/persons`                      | Liste Personen                 | eingeloggt |
| GET     | `/api/workpackages`                 | Liste WPs (sichtbare)          | eingeloggt |
| GET     | `/api/workpackages/{code}`          | WP-Detail mit Mitgliedern      | eingeloggt |

### Stammdaten (Admin)

| Methode | Pfad                                            | Zweck                                  | Rolle  |
| ------- | ----------------------------------------------- | -------------------------------------- | ------ |
| POST    | `/api/admin/partners`                           | Partner anlegen                        | admin  |
| PATCH   | `/api/admin/partners/{id}`                      | Partner ändern                         | admin  |
| DELETE  | `/api/admin/partners/{id}`                      | Partner soft-delete                    | admin  |
| POST    | `/api/admin/persons`                            | Person anlegen, Initialpasswort        | admin  |
| PATCH   | `/api/admin/persons/{id}`                       | Person ändern                          | admin  |
| POST    | `/api/admin/persons/{id}/reset-password`        | Passwort zurücksetzen                  | admin  |
| POST    | `/api/admin/workpackages`                       | WP anlegen                             | admin  |
| PATCH   | `/api/admin/workpackages/{id}`                  | WP ändern                              | admin  |
| POST    | `/api/admin/workpackages/{id}/memberships`      | Mitgliedschaft anlegen                 | admin  |
| DELETE  | `/api/admin/memberships/{id}`                   | Mitgliedschaft entfernen               | admin  |

### Dokumente (intern)

| Methode | Pfad                                                         | Zweck                                                  | Rolle                              |
| ------- | ------------------------------------------------------------ | ------------------------------------------------------ | ---------------------------------- |
| GET     | `/api/workpackages/{code}/documents`                         | Dokumentenliste eines WPs                              | WP-Mitglied oder admin             |
| POST    | `/api/workpackages/{code}/documents`                         | Neues Dokument anlegen (ohne Datei)                    | WP-Mitglied oder admin             |
| GET     | `/api/documents/{id}`                                        | Dokumentdetail inkl. Versionsliste                     | Sichtbarkeitsregel (§7)            |
| PATCH   | `/api/documents/{id}`                                        | Titel, Typ, Deliverable-Code ändern                    | WP-Mitglied oder admin             |
| POST    | `/api/documents/{id}/versions`                               | Neue Version hochladen, multipart, change_note Pflicht | WP-Mitglied oder admin             |
| GET     | `/api/documents/{id}/versions/{n}/download`                  | Download einer Version                                 | Sichtbarkeitsregel (§7)            |
| POST    | `/api/documents/{id}/release`                                | Setzt `status=released` und `released_version_id`      | wp_lead des WPs oder admin         |
| POST    | `/api/documents/{id}/visibility`                             | Setzt `visibility`                                     | wp_lead des WPs oder admin         |
| DELETE  | `/api/documents/{id}`                                        | Soft-Delete                                            | admin                              |

### Öffentlich

| Methode | Pfad                                              | Zweck                                                   | Rolle  |
| ------- | ------------------------------------------------- | ------------------------------------------------------- | ------ |
| GET     | `/api/public/documents`                           | Liste freigegebener öffentlicher Dokumente              | anonym |
| GET     | `/api/public/documents/{slug}`                    | Detail eines öffentlichen Dokuments                     | anonym |
| GET     | `/api/public/documents/{slug}/download`           | Download der freigegebenen Version                      | anonym |
| GET     | `/api/public/partners`                            | Liste Partner für die Projektseite                      | anonym |

### Audit

| Methode | Pfad             | Zweck                              | Rolle  |
| ------- | ---------------- | ---------------------------------- | ------ |
| GET     | `/api/admin/audit` | Audit-Log mit Filtern             | admin  |

### Konventionen

- Fehlerantworten mit `{"error": {"code": "...", "message": "..."}}`.
- `409` für Konflikte (z. B. Slug existiert), `403` für
  Sichtbarkeitsverletzung, `404` für „nicht sichtbar **oder** nicht
  vorhanden" (keine Existenz-Leakage).
- Pagination: `?limit=`, `?offset=`. Default 50, Max 200.
- Uploads: `multipart/form-data`, Größenlimit serverseitig
  konfigurierbar (Vorschlag: 100 MB im MVP).

---

## 7. Rechte- und Sichtbarkeitsregeln

Zentral, im Service-Layer durchgesetzt. Routen prüfen nicht selbst.

### Lesezugriff auf ein Dokument

Eine Person darf ein Dokument **lesen**, wenn eine der folgenden
Bedingungen zutrifft:

1. `visibility = 'public'` **und** `status = 'released'` — auch anonym.
2. Person ist `admin`.
3. Person ist Mitglied im zugehörigen Workpackage (egal welche
   WP-Rolle) **und** `visibility ∈ {'workpackage', 'internal'}`.
4. Person ist eingeloggt **und** `visibility = 'internal'`.

### Lesezugriff auf eine bestimmte Version

- Wer das Dokument lesen darf, darf jede seiner Versionen lesen — mit
  einer Ausnahme: anonyme Besucher dürfen nur die durch
  `released_version_id` referenzierte Version lesen, keine ältere.

### Schreibzugriff

| Aktion                                      | Erlaubt für                                        |
| ------------------------------------------- | -------------------------------------------------- |
| Dokument anlegen in WP                      | WP-Mitglied (jede WP-Rolle) oder admin             |
| Metadaten ändern (Titel, Typ, Deliverable)  | WP-Mitglied oder admin                             |
| Neue Version hochladen                      | WP-Mitglied oder admin                             |
| Status auf `in_review` setzen               | WP-Mitglied oder admin                             |
| Status auf `released` setzen + Version wählen| `wp_lead` des WPs oder admin                       |
| Status zurück auf `draft`                   | admin (mit Audit-Log-Eintrag)                      |
| Sichtbarkeit auf `public` setzen            | `wp_lead` des WPs oder admin                       |
| Sichtbarkeit auf `internal`/`workpackage`   | WP-Mitglied oder admin                             |
| Dokument löschen (soft)                     | admin                                              |
| Stammdaten (Partner, Personen, WPs)         | admin                                              |

### Audit-Log-Sichtbarkeit

- Komplettes Audit-Log: nur admin.
- Pro-Dokument-Historie im UI (wer hat wann was geändert): WP-Mitglieder
  dürfen die Einträge sehen, die ihr Dokument betreffen — aber erst in
  einer späteren Iteration. Im MVP ist die Pro-Dokument-Historie
  ausschließlich die Versionsliste.

### Default-Sichtbarkeit

Neue Dokumente starten mit `visibility = 'workpackage'` und
`status = 'draft'`.

---

## 8. Dokumenten-Versionierung

Verbindliche Regeln:

1. **Eine Datei = eine Version.** Jeder Upload erzeugt einen neuen
   `document_version`-Datensatz, niemals ein In-Place-Update.
2. **`version_number` ist eine pro Dokument monoton steigende
   Ganzzahl**, beginnend bei 1. Sie wird vom Server vergeben, nicht
   vom Client.
3. **`version_label` ist ein freies Textfeld**, optional. Der MVP
   schreibt kein Schema vor. Empfehlung an Nutzer: „v0.1", „v1.0",
   „D2.1-final" o. ä.
4. **`change_note` ist Pflicht** beim Hochladen jeder Version (auch der
   ersten). Mindestens 5 Zeichen. Wird im UI als „Was hat sich
   geändert?" gelabelt.
5. **`sha256` wird serverseitig berechnet** und bei Upload gegen die
   bestehenden Versionen desselben Dokuments verglichen. Bei
   Identität: Warnung im UI, kein Hard-Block (der Nutzer kann denselben
   Inhalt bewusst neu einspielen, falls Metadaten korrigiert werden
   sollen).
6. **Dateien werden nicht überschrieben.** Storage-Keys enthalten den
   Versions-Identifier, sodass parallele Uploads keinen Race haben.
7. **Versionen werden nicht gelöscht.** Löschung eines Dokuments ist
   Soft-Delete auf `document`. Versionen bleiben referenzierbar.
8. **Freigabe ist explizit.** Ohne aktiven Aufruf von
   `POST /api/documents/{id}/release` ist keine Version „die
   freigegebene". Die Freigabe wählt eine konkrete Version aus, nicht
   automatisch die neueste.
9. **Eine neue Version setzt das Dokument nicht automatisch in
   `draft` zurück.** Wenn ein Dokument bereits `released` ist und eine
   neue Version eingespielt wird, bleibt die zuvor freigegebene
   Version freigegeben. Nur ein erneuter `release`-Aufruf wechselt die
   freigegebene Version.
10. **Audit-Pflicht.** Jede der Aktionen create, upload, release,
    set_visibility, patch erzeugt einen `audit_log`-Eintrag mit
    Vorher/Nachher der relevanten Felder.

---

## 9. Öffentliche Download-Bibliothek

Zweck: externe Sichtbarkeit der Projektergebnisse. Kein Login, keine
Personalisierung, keine Indexierung der internen Inhalte.

### Auswahllogik

Ein Dokument erscheint im öffentlichen Bereich genau dann, wenn:

- `is_deleted = false` **und**
- `visibility = 'public'` **und**
- `status = 'released'` **und**
- `released_version_id IS NOT NULL`.

Der öffentliche Listenpunkt zeigt:

- Titel
- Arbeitspaket-Code und -Titel
- Deliverable-Code (falls gesetzt)
- `version_label` der freigegebenen Version, sonst `vN`
- Freigabedatum (= `uploaded_at` der freigegebenen Version)
- Dateigröße und MIME-Typ
- Direkter Download-Link

### Filter im MVP

- Nach Arbeitspaket (Dropdown).
- Nach Dokumenttyp.
- Sortierung nach Datum absteigend (Default).

Keine Volltextsuche, keine Tag-Filter im MVP.

### Download

- `GET /api/public/documents/{slug}/download` liefert die Datei.
- HTTP-Header `Content-Disposition: attachment; filename=...`.
- `ETag` über `sha256`. `Cache-Control: public, max-age=300`.
- Kein temporäres Token notwendig — die Datei ist explizit öffentlich.
- Audit-Log erfasst den Download **nicht** (anonym, kein Mehrwert
  für MVP, DSGVO-freundlich).

### Sichtbarkeit auf der Projektseite

- `/` zeigt einen kleinen Block „Aktuelle Veröffentlichungen" mit den
  letzten drei freigegebenen öffentlichen Dokumenten. Verlinkt auf
  `/downloads`.

### Maschinenlesbarkeit

- Im MVP **kein** RSS, **kein** OAI-PMH, **keine** DOI-Vergabe. Diese
  sind explizit Folgearbeit (siehe §11).

---

## 10. Technische Architektur

### Stack

| Schicht       | Technologie                                                                              |
| ------------- | ---------------------------------------------------------------------------------------- |
| Backend       | Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2                              |
| Datenbank     | **SQLite als lokaler Entwicklungsstandard, PostgreSQL als späteres Produktivziel.**      |
|               | Datenbankschicht von Anfang an über `REF4EP_DATABASE_URL` konfigurierbar.                |
| Storage       | Filesystem hinter Storage-Interface (`LocalFileStorage`).                                |
| Auth          | Argon2id, HMAC-signiertes Session-Cookie, CSRF-Header                                    |
| Frontend      | **Kein Frontend-Framework. Statisch ausgeliefertes HTML/CSS + Vanilla-JavaScript,**      |
|               | analog zum Referenzsystem (`web/`-Ordner). Kein Node, kein npm, kein Build-Schritt.      |
|               | Public-Zone wird per Jinja2-Templates serverseitig gerendert (SEO).                       |
| Server        | Uvicorn hinter Reverse-Proxy (nginx/Caddy)                                               |
| Container     | Docker optional. Lokal reicht `python -m ref4ep` bzw. `uvicorn`.                         |
| Migrations    | Alembic ab dem ersten Modell                                                             |
| Tests         | `pytest`, `httpx`-Testclient für Backend; Playwright (Python) optional für Browser-Smoke |
| Logging       | strukturiert (JSON in Prod, Text in Dev) auf `ref4ep`-Logger                             |
| Sprache       | Deutsch                                                                                  |

### Frontend-Architektur

Begründung der Wahl: geringere Komplexität, kein Node/npm-Build-Prozess,
einfacheres Deployment, bessere Anschlussfähigkeit an das Referenzsystem
(`jluspaceforge-reference/src/lab_management/web/`).

Konsequenzen für die Umsetzung:

- **Public-Zone** (`/`, `/partners`, `/downloads`, `/downloads/{slug}`,
  `/legal/*`): serverseitig gerendert per **Jinja2-Templates** durch
  FastAPI. Keine Client-JS-Pflicht zum Lesen der Inhalte. Vorteil:
  indexierbar, ohne Login lesbar, robust ohne JS.
- **Interne Zone** (`/portal/...`) und **Admin-Zone** (`/admin/...`):
  ein einziges, statisch ausgeliefertes `index.html`-Shell mit
  Vanilla-JS. Routing per History-API; FastAPI liefert für unbekannte
  Pfade unterhalb von `/portal/` und `/admin/` denselben SPA-Shell aus.
  JS spricht ausschließlich die `/api/*`-Endpunkte.
- **Login-Seite** (`/login`): einfacher serverseitig gerenderter
  HTML-Form-Post, kein JS notwendig. Nach erfolgreichem Login Redirect
  in die interne Zone.
- **Statische Assets**: CSS und JS-Dateien liegen als Quelltext im Repo
  und werden ohne Bundler/Minifier ausgeliefert. Pro fachlichem Modul
  eine `*.js`-Datei (Muster aus Referenz). Optional einfache
  Versionierung über Query-String (`?v=...`) für Cache-Busting.
- **Keine TypeScript-Pflicht**, keine Frameworks (Svelte, React, Vue,
  Alpine, HTMX werden im MVP nicht eingesetzt). Wiederverwendbare
  Hilfsfunktionen leben in einer kleinen `common.js`.
- **Browser-Mindestziel**: aktuelle Versionen von Firefox, Chrome,
  Edge, Safari (letzte zwei Major-Releases). Keine IE-Kompatibilität.

### Repository-Layout

```
ref4ep-portal/
  backend/
    src/ref4ep/
      domain/          # SQLAlchemy-Modelle, Enums
      services/        # Geschäftslogik, Audit, Permissions
      api/
        app.py
        config.py
        deps.py
        routes/
        schemas/
        middleware/
      storage/         # Storage-Interface + LocalFileStorage
      cli/             # Admin-CLI (Personen, Initialpasswort)
      web/             # Statisch ausgelieferter SPA-Shell für /portal und /admin
        index.html
        app.js
        common.js
        style.css
        modules/       # Pro Modul eine *.js (workpackages.js, documents.js, ...)
      templates/       # Jinja2-Templates für Public-Zone und /login
        public/
        legal/
        login.html
      static/          # Public CSS/Bilder/Logos (Partnerlogos, Favicon)
    alembic/
    tests/
    pyproject.toml
  infra/
    nginx/             # Beispiel-Reverse-Proxy-Config
    systemd/           # Beispiel-Service-Unit (optional)
  data/                # Lokale SQLite-DB und Storage-Verzeichnis (gitignored)
  docs/
    reference_analysis.md
    mvp_specification.md
```

Es gibt **kein** separates Frontend-Projekt, **keine** `package.json`,
**keinen** Node-Build. Alle Web-Assets sind Teil des Backend-Pakets und
werden über `StaticFiles`/`FileResponse` ausgeliefert.

### Schichtdisziplin (übernommen aus Referenz)

- Routen sind dünn: Parsing, Service-Aufruf, Schema-Mapping.
- Jede schreibende Operation läuft durch einen Service, der
  Berechtigungen prüft **und** in den Audit-Log schreibt.
- Domäne ist frei von HTTP-Belangen.
- Storage hinter Interface, damit S3/MinIO später ohne Service-Umbau
  ergänzbar ist.

### Sicherheitsbasislinie

- Argon2id für Passwörter, Mindestlänge 10 Zeichen für den MVP.
- Sessions: HMAC-signiert mit `REF4EP_SESSION_SECRET` aus Env;
  HttpOnly, SameSite=Lax, Secure (in Prod), Lifetime 7 Tage.
- CSRF: Header `X-CSRF-Token` für POST/PATCH/DELETE; Token aus zweitem
  Cookie (Double-Submit-Pattern).
- Rate-Limit auf `/api/auth/login` (z. B. 5 Versuche pro Minute pro
  IP).
- Upload-Limits serverseitig erzwungen.
- Datei-MIME-Whitelist (PDF, DOCX, XLSX, PPTX, ZIP, PNG, JPG) für den
  MVP. Andere Typen über Admin-Konfiguration nachrüstbar.
- Public-Download-Pfad rendert keine HTML-Vorschau, sondern liefert
  immer als `attachment` aus.

### Konfiguration

Nur über Umgebungsvariablen:

- `REF4EP_DATABASE_URL` — SQLAlchemy-URL.
  - Lokaler Entwicklungsdefault: `sqlite:///./data/ref4ep.db`
  - Produktivziel: `postgresql+psycopg://...` (ohne Codeumbau, nur
    URL-Wechsel + neue Migrations-Anwendung).
- `REF4EP_SESSION_SECRET` — Pflicht, mind. 32 Zeichen Entropie.
- `REF4EP_STORAGE_DIR` — Pfad für `LocalFileStorage`,
  Default `./data/storage`.
- `REF4EP_MAX_UPLOAD_MB` — Default 100.
- `REF4EP_PUBLIC_BASE_URL` — Für absolute Links in Public-Zone.
- `REF4EP_LOG_FORMAT` — `text` (Dev-Default) oder `json` (Prod).

Wichtig: Das ORM- und Migrations-Setup muss **dialektneutral** geschrieben
werden. SQLite-spezifische Typen (z. B. `JSON1`-Funktionen) werden
vermieden; UUIDs werden als `CHAR(36)` oder über
`sqlalchemy.types.Uuid` portabel modelliert. Alembic-Revisionen werden
gegen beide Backends getestet.

### Beobachtbarkeit

- Request-ID-Middleware (analog Referenz).
- Strukturierte Zugriffslogs.
- Healthcheck-Endpoint `/api/health` mit DB-Ping und Storage-Schreibtest.

### Backups (außerhalb des MVP-Codes)

- DB-Sicherung täglich, Retention 14 Tage.
  - SQLite: Datei-Snapshot per `sqlite3 .backup` oder Dateikopie bei
    angehaltenem Schreibverkehr.
  - PostgreSQL (später): `pg_dump` mit kompressioniertem Custom-Format.
- Storage-Verzeichnis täglich rsync, Retention 14 Tage.
- Verantwortung: Betreiber, nicht im MVP-Code automatisiert.

---

## 11. Offene Entscheidungen

### Bereits getroffene Entscheidungen

Diese Punkte sind verbindlich entschieden und werden in §10 abgebildet.
Sie tauchen unten in der Tabelle nicht mehr als offen auf.

- **Frontend (vorher #1):** Kein SvelteKit, kein React, kein Vue, kein
  HTMX. Stattdessen FastAPI + statisch ausgeliefertes HTML/CSS +
  Vanilla-JavaScript, analog zum Referenzsystem. Public-Zone per
  Jinja2-Template gerendert. Begründung: geringere Komplexität, kein
  Node/npm-Build, einfacheres Deployment, bessere Anschlussfähigkeit
  an die Referenz.
- **Datenbank (zuvor implizit gesetzt):** SQLite als lokaler
  Entwicklungsstandard, PostgreSQL als späteres Produktivziel. Schicht
  von Anfang an über `REF4EP_DATABASE_URL` konfigurierbar. Alembic
  ab dem ersten Modell. ORM-Code dialektneutral.
- **Initialer Daten-Seed (vorher #13):** Verbindliche Liste der
  Konsortialpartner (JLU, IOM, CAU, THM, TUD), des Projektkalenders
  (Start 2026-03-01, 36 Monate), der Parent-Arbeitspakete WP1–WP8 mit
  Titeln und Lead-Partnern, der 27 Sub-Arbeitspakete WP1.1–WP8.3 mit
  Titeln und geerbten Lead-Partnern sowie der vier Meilensteine
  MS1–MS4 mit `planned_date` ist in §13 dokumentiert. Offen bleibt nur
  noch das Eintragen tatsächlicher `actual_date`-Werte für MS2–MS4
  (sobald erreicht) sowie ergänzender Beschreibungen — beides
  Pflegevorgänge im laufenden Betrieb, keine Spec-Lücken.

### Noch offen

Bewusst ungeklärte Punkte. Müssen vor Ende des jeweils benannten Sprints
(siehe §12) getroffen sein, damit Folgesprints nicht blockiert werden.

| #   | Frage                                                                                  | Entscheidungsfrist          |
| --- | -------------------------------------------------------------------------------------- | --------------------------- |
| 2   | Hosting-Ziel und Domain (DLR-Server? Hochschulserver? eigene VM?)                     | vor Sprint 4                |
| 3   | SSO-Strategie und Zeitpunkt: Shibboleth/AAI vs. DLR-IDP vs. nur lokal bis v1.1         | vor v1.0                    |
| 4   | Versionierungsschema: rein integer + freies Label vs. erzwungene D-Nummer für         | vor Sprint 2                |
|     | `document_type = deliverable`                                                          |                             |
| 5   | Wer darf `visibility = public` setzen: nur admin oder auch wp_lead?                    | vor Sprint 3                |
| 6   | Default-Sichtbarkeit von Drafts: `workpackage` (vorgesehen) oder `internal` für mehr  | vor Sprint 3                |
|     | Konsortialtransparenz?                                                                 |                             |
| 7   | Storage-Backend in Prod: lokales FS, MinIO, oder direkt S3?                            | vor Sprint 2                |
| 8   | DSGVO-Text und Verantwortlicher (Hochschule? Konsortium? DLR?)                         | vor Sprint 4                |
| 9   | Datei-MIME-Whitelist: aktuelle Liste ausreichend oder erweitern (LaTeX-Quellen,       | vor Sprint 2                |
|     | Tabellen)?                                                                             |                             |
| 10  | Persistente DOI/Zenodo-Anbindung für freigegebene öffentliche Dokumente — ja/nein,     | nach MVP                    |
|     | wann?                                                                                  |                             |
| 11  | Mehrsprachigkeit (DE/EN) — ab welcher Version?                                          | nach MVP                    |
| 12  | Wer pflegt die statischen Inhalte (`/`, Partnerlogos, Datenschutz)? Inline im Repo    | vor Sprint 4                |
|     | oder im Admin-UI?                                                                      |                             |
| 14  | Audit-Log-Retention (unbegrenzt vs. Rotation nach X Monaten)                           | vor Sprint 3                |

---

## 12. Reihenfolge der Umsetzung

Sechs Sprints. Jeder Sprint endet mit lauffähiger Software auf einer
lokalen Entwicklungsumgebung. „Definition of Done" für jeden Sprint:
Migrations laufen, Smoke-Tests grün, betroffene UI-Pfade von Hand
ausprobiert.

### Sprint 0 — Setup (Skelett)

- Repo-Layout gemäß §10 anlegen (leere Pakete, `pyproject.toml`,
  `backend/src/ref4ep/web/`, `backend/src/ref4ep/templates/`,
  `backend/src/ref4ep/static/`).
- Lokale SQLite-Datenbank unter `data/ref4ep.db`,
  `REF4EP_DATABASE_URL` mit sinnvollem Default.
- Alembic initialisieren, leeres `versions/`-Verzeichnis. Erste
  No-op-Revision, gegen SQLite und (CI-optional) PostgreSQL geprüft.
- FastAPI-„Hello"-Endpoint `/api/health` mit DB-Ping.
- `StaticFiles`-Mount für `web/` und `static/`. Leeres
  `web/index.html` als SPA-Shell. Public-Landing
  (`templates/public/home.html`) mit Platzhaltertext.
- CI: Linting (`ruff`), Unit-Test-Runner (`pytest`), Migrations-Check
  (Alembic upgrade head auf SQLite, optional PostgreSQL-Service).
- Skelett für das Seed-Skript (`ref4ep-admin seed --from antrag`)
  anlegen, das später §13 einliest.

### Sprint 1 — Identität

- Modelle: `partner`, `person`, `workpackage`, `membership`.
- Argon2id-Hashing, Login, Session-Cookie, CSRF.
- Admin-CLI: `ref4ep-admin person create|reset-password|set-role`,
  `ref4ep-admin partner create`, `ref4ep-admin workpackage create`,
  `ref4ep-admin membership add`.
- Routen: `/api/auth/*`, `/api/me`, `/api/workpackages` (read).
- UI: Login, `/portal` (Cockpit minimal), `/portal/workpackages`.
- Initial-Seed-Skript für Partner und WPs gemäß §13 ausführen:
  fünf Partner (JLU, IOM, CAU, THM, TUD), acht Parent-WPs mit Titeln
  und Lead-Partnern, 27 Sub-WPs mit Titeln und geerbten Lead-Partnern.
  Ausführliche WP-`description`-Texte können nachträglich über
  Admin-CLI/UI eingepflegt werden.
- **Entscheidung 7** treffen.

### Sprint 2 — Dokumentenregister (intern)

- Modelle: `document`, `document_version`.
- Storage-Interface + `LocalFileStorage`, Hashing, MIME-Whitelist.
- Routen: WP-Dokumentenliste, Anlage, Version-Upload, Download intern,
  Metadaten-Patch.
- UI: WP-Detail, Dokumentdetail, Upload-Formular mit Pflicht-
  Änderungsnotiz.
- Servicelayer-Berechtigungslogik (§7) für Schreibaktionen.
- **Entscheidung 4, 9** treffen.

### Sprint 3 — Audit, Status, Sichtbarkeit

- `audit_log`-Modell, Audit-Service, Hook in alle schreibenden Services.
- Status-Übergänge `draft → in_review → released`.
- `release`- und `set_visibility`-Endpoints inklusive Berechtigungs-
  prüfung.
- Admin-Audit-View mit Filtern.
- UI: Statusbadge und Aktionen am Dokumentdetail.
- **Entscheidung 5, 6, 14** treffen.

### Sprint 4 — Öffentliche Zone

- Public-Routen: Liste, Detail, Download.
- `/` Projektsteckbrief, `/partners`, `/downloads`,
  `/downloads/{slug}`.
- Statische Inhalte (Impressum, Datenschutz) ausliefern.
- ETag, Caching-Header, MIME-Korrektheit.
- **Entscheidung 2, 8, 12** treffen.

### Sprint 5 — Polieren und UAT

- Admin-UI für Partner, Personen, Workpackages, Mitgliedschaften
  (über das CLI hinaus).
- Filter und Pagination in den internen Listen.
- Fehlerseiten (403, 404, 500) auf Deutsch.
- Smoke-Tests über Playwright (Python-Bindings, kein Node nötig) für
  die drei Demo-Szenarien aus §1.
- Dokumentation: Betriebs-Handbuch (Deploy, Backup, Initialnutzer).
- UAT mit zwei bis drei Konsortialpartnern auf einer Staging-Instanz.

### Nach dem MVP (nicht Teil dieser Spezifikation)

Reihenfolge bewusst offen. Kandidaten:

- SSO/OIDC.
- Review-Workflow (Kommentare, Reviewer-Zuweisung, Genehmigungs-Pipeline).
- Wiki-Modul (Referenzdiagnostik-Wissensbasis).
- Meilenstein- und Deliverable-Tracker mit Terminen (Datenbasis liegt
  bereits in §13 vor und kann beim Bau des Trackers übernommen werden).
- Messkampagnen- und Testplanung.
- Daten- und Metadatenregister, ggf. mit DOI-Vergabe.
- Beschluss- und Protokolldatenbank.
- Mehrsprachigkeit DE/EN.

---

## 13. Verbindliche Initial-Seed-Daten (aus Antrag/Gantt)

### 13.1 Quelle und Pflege

Die folgenden Tabellen sind die **verbindliche Ausgangsbasis** für das
Initial-Seed-Skript des MVP. Quelle: Ref4EP2-Projektantrag und
zugehöriger Gantt-Plan. Sie werden im Admin-CLI/-UI pflegbar abgelegt
und können nach dem Initial-Seed jederzeit durch tatsächliche
Projektdaten ergänzt oder korrigiert werden — Änderungen laufen über
denselben Audit-Pfad wie alle anderen Schreibaktionen.

Partner, Lead-Partner, WP-Codes mit Titeln, Sub-WP-Codes mit Titeln
und die Plandaten aller vier Meilensteine sind verbindlich gesetzt
und müssen vor dem Produktiv-Seed nicht mehr ergänzt werden. Nachträge
betreffen ausschließlich:

- ausführliche Beschreibungen der Arbeitspakete (`description`),
- tatsächliche Meilensteintermine (`actual_date`) für MS2–MS4, sobald
  sie erreicht sind,
- ggf. abweichende Lead-Partner einzelner Sub-WPs gegenüber dem
  geerbten Default,
- Detail-Metadaten der Partner (Website, Kontaktperson).

Diese Nachpflege erfolgt über das Admin-CLI/-UI ohne Codeumbau.

### 13.2 Projekt-Eckdaten

| Feld                  | Wert                                                   |
| --------------------- | ------------------------------------------------------ |
| Projektname           | Ref4EP                                                 |
| Projektstart          | 2026-03-01                                             |
| Projektende           | 2029-02-28                                             |
| Laufzeit              | 36 Monate                                              |
| Gantt-Monat 1         | März 2026                                              |
| Gantt-Monat 36        | Februar 2029                                           |
| Förderer              | DLR (Deutsches Zentrum für Luft- und Raumfahrt)        |

Der Monatsindex aus dem Gantt-Plan wird im Portal über eine kleine
Hilfsfunktion auf Kalenderdaten gemappt (Monat n → erster Tag des
Kalendermonats `2026-03 + (n-1)`). Diese Funktion ist Teil des
`services`-Pakets und nicht Teil des Datenmodells.

### 13.3 Initiale Partner

Vollnamen sind die kanonischen Bezeichnungen der Institutionen; sie
sind vor dem ersten produktiven Seed gegen den genauen Wortlaut im
Antrag zu prüfen.

| Code | Vollname (Vorschlag, gegen Antrag prüfen)                          | Land | Hinweis                                                  |
| ---- | ------------------------------------------------------------------ | ---- | -------------------------------------------------------- |
| JLU  | Justus-Liebig-Universität Gießen                                   | DE   | Voraussichtlich Projektkoordination                      |
| IOM  | Leibniz-Institut für Oberflächenmodifizierung e. V., Leipzig       | DE   |                                                          |
| CAU  | Christian-Albrechts-Universität zu Kiel                            | DE   |                                                          |
| THM  | Technische Hochschule Mittelhessen                                 | DE   |                                                          |
| TUD  | Technische Universität Dresden                                     | DE   |                                                          |

`short_name` = Code, `country` = Land. Website pro Partner ist im Seed
optional und wird im Admin-UI nachgepflegt.

### 13.4 Initiale Arbeitspakete

#### Parent-Arbeitspakete

| Code | Titel                                                         | Parent-WP | Lead-Partner |
| ---- | ------------------------------------------------------------- | --------- | ------------ |
| WP1  | Projektmanagement, Daten und Dissemination                    | —         | JLU          |
| WP2  | Referenz-Gitterionenquelle                                    | —         | IOM          |
| WP3  | Referenz-Halltriebwerk                                        | —         | TUD          |
| WP4  | Plume-Diagnostiksysteme                                       | —         | CAU          |
| WP5  | Elektronikentwicklung                                         | —         | THM          |
| WP6  | Spezialdiagnostik                                             | —         | IOM          |
| WP7  | Plume-Wechselwirkungen und facility-induzierte Strompfade     | —         | JLU          |
| WP8  | Ringvergleiche und Facility-Effekte                           | —         | JLU          |

`sort_order` ergibt sich aus der numerischen Reihenfolge des Codes.

#### Sub-Arbeitspakete

Die Sub-Arbeitspakete reichen laut Antrag von **WP1.1 bis WP8.3**, mit
27 Sub-WPs verteilt über die acht Parent-WPs (Anzahl pro Parent: 2–6).
Jedes Sub-WP referenziert über `parent_workpackage_id` exakt einen
Parent aus der obigen Tabelle.

**Lead-Partner-Vererbung:** Im Initial-Seed übernimmt jedes Sub-WP den
Lead-Partner seines Parent-WPs (siehe Spalte „Lead-Partner" unten,
geerbt aus §13.4 Parent-Tabelle). Diese Vererbung ist ein
Seed-Default; sobald für ein einzelnes Sub-WP eine abweichende
Information vorliegt, wird sie über Admin-CLI/UI gesetzt und
überschreibt den geerbten Wert.

| Code   | Titel                                                  | Parent-WP | Lead-Partner |
| ------ | ------------------------------------------------------ | --------- | ------------ |
| WP1.1  | Projektmanagement                                      | WP1       | JLU          |
| WP1.2  | Standardisierung & Formate                             | WP1       | JLU          |
| WP2.1  | RefGIQ Langzeitcharakterisierung                       | WP2       | IOM          |
| WP2.2  | Quellenbau                                             | WP2       | IOM          |
| WP3.1  | Konstruktion Ref-HT                                    | WP3       | TUD          |
| WP3.2  | Basischarakterisierung Referenz-HT                     | WP3       | TUD          |
| WP3.3  | Erweiterte Diagnostik Referenz-HT                      | WP3       | TUD          |
| WP4.1  | FS-Langzeittest                                        | WP4       | CAU          |
| WP4.2  | FS-Systembau                                           | WP4       | CAU          |
| WP4.3  | E×B-Sonde                                              | WP4       | CAU          |
| WP4.4  | Energieanalysatoren                                    | WP4       | CAU          |
| WP4.5  | Teilchenfluss-Sonde                                    | WP4       | CAU          |
| WP4.6  | Plasmasonden                                           | WP4       | CAU          |
| WP5.1  | Plasmasondenelektronik für Treibstrahl                 | WP5       | THM          |
| WP5.2  | Plasmasondenelektronik für Strompfadanalyse            | WP5       | THM          |
| WP5.3  | E×B-Sondenelektronik                                   | WP5       | THM          |
| WP5.4  | Validierung Diagnostik/Elektronik                      | WP5       | THM          |
| WP6.1  | TALIF-Systemaufbau und Anwendung                       | WP6       | IOM          |
| WP6.2  | TALIF-gestützte Validierung                            | WP6       | IOM          |
| WP6.3  | LIF-Diagnostik und Anwendung am HT                     | WP6       | IOM          |
| WP6.4  | ESMS-Messungen und Validierung der E×B-Sonde           | WP6       | IOM          |
| WP7.1  | Sensorik-Konzeption                                    | WP7       | JLU          |
| WP7.2  | SPIS-Modellierung                                      | WP7       | JLU          |
| WP7.3  | Wechselwirkung Facility/Triebwerk                      | WP7       | JLU          |
| WP8.1  | Ringvergleiche Planung                                 | WP8       | JLU          |
| WP8.2  | Ringvergleiche Durchführung                            | WP8       | JLU          |
| WP8.3  | Energiekalibrierung                                    | WP8       | JLU          |

### 13.5 Initiale Meilensteine

> Hinweis zum MVP-Scope: Das MVP-Datenmodell (§4) enthält **keine**
> `milestone`-Tabelle. Die Meilensteindaten werden hier dokumentiert,
> damit sie beim späteren Bau des Meilenstein-Trackers (siehe „Nach
> dem MVP" in §12) ohne Recherche übernommen werden können. Im MVP
> selbst werden sie nicht eingespielt.

Felder (für den späteren Tracker): `code`, `title`, `workpackage_code`
(Bezug zu einem Parent- oder Sub-WP), `planned_date`, `actual_date`.

| Code | Titel       | WP-Bezug    | planned_date | actual_date  |
| ---- | ----------- | ----------- | ------------ | ------------ |
| MS1  | (Antrag)   | (Antrag)   | 2026-03-02   | 2026-03-28   |
| MS2  | (Antrag)   | (Antrag)   | 2027-02-15   | —            |
| MS3  | (Antrag)   | (Antrag)   | 2028-02-15   | —            |
| MS4  | (Antrag)   | (Antrag)   | 2029-02-28   | —            |

Bedeutung der Sonderwerte:

- `actual_date = —` ⇒ Spalte bleibt im späteren Modell `NULL`
  (Meilenstein noch nicht erreicht). Wird auf den tatsächlichen Termin
  gesetzt, sobald der Meilenstein erreicht ist.
- `actual_date = 2026-03-28` für MS1 bildet den tatsächlich
  stattgefundenen Termin ab. MS1 ist somit beim Initial-Seed bereits
  als „erreicht" markiert.
- `(Antrag)` in den Spalten Titel und WP-Bezug bedeutet: aus dem
  Antrag wörtlich übernehmen, sobald der Tracker gebaut wird. Diese
  beiden Felder sind nicht offen, sondern liegen in der
  Antrags-Datei vor.

### 13.6 Pflegeprozess

- Der Initial-Seed wird einmalig per CLI ausgeführt (`ref4ep-admin
  seed --from antrag`). Die Quelldatei liegt versioniert im Repo unter
  `backend/src/ref4ep/cli/seed_data/antrag_initial.yaml` (Pfad
  vorgeschlagen, nicht verbindlich).
- Spätere Änderungen (z. B. ausführliche WP-Beschreibungen,
  tatsächliche Meilenstein-Termine `actual_date` für MS2–MS4, davon
  abweichende Sub-WP-Lead-Partner, Partner-Webseiten und
  Kontaktdaten) erfolgen über das Admin-UI bzw. die Admin-CLI. Sie
  laufen durch denselben Audit-Pfad wie reguläre Schreibaktionen.
- Das Seed-Skript ist **idempotent**: erneuter Lauf legt nur fehlende
  Datensätze an und überschreibt keine bereits gepflegten Felder.
