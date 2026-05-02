# Sprint 1 – Umsetzungsplan: Identität und Projektstruktur

Dieser Plan konkretisiert den zweiten Sprint aus
`docs/mvp_specification.md` §12. Er baut auf dem Skelett aus
`docs/sprint0_implementation_plan.md` (Sprint 0) auf und liefert das
erste fachlich nutzbare Stadium des Portals.

Verbindliche Festlegungen aus der MVP-Spezifikation, die hier gelten:

- FastAPI + statisch ausgeliefertes HTML/CSS + Vanilla-JS — **kein**
  Frontend-Framework, **kein** Node/npm.
- SQLite als lokaler Default, konfigurierbar über
  `REF4EP_DATABASE_URL`.
- Alembic für jede Schema-Änderung.
- Public-Zone via Jinja2-Templates serverseitig gerendert.
- Datenmodell aus §4 der MVP-Spec (Partner, Person, Workpackage,
  Membership) — exakt wie dort spezifiziert.
- Initial-Seed aus §13 der MVP-Spec — verbindliche Daten
  (5 Partner, 8 Parent-WPs, 27 Sub-WPs mit Titeln, Lead-Vererbung).

---

## 1. Ziel von Sprint 1

Sprint 1 liefert die **erste fachlich nutzbare** Iteration des
Portals. Am Ende muss gelten:

- Eine zweite Alembic-Revision legt die Tabellen `partner`, `person`,
  `workpackage`, `membership` an. `alembic upgrade head` und
  `alembic downgrade base` laufen beide fehlerfrei.
- `ref4ep-admin seed --from antrag` legt die fünf Partner, die acht
  Parent-Arbeitspakete und die 27 Sub-Arbeitspakete gemäß §13 der
  MVP-Spec idempotent an. Wiederholter Lauf ist konfliktfrei.
- `ref4ep-admin person create …` legt eine Person mit
  Argon2id-Passwort-Hash, Plattformrolle und Partner-Zugehörigkeit an.
- `POST /api/auth/login` (JSON oder Form) erzeugt ein
  HMAC-signiertes Session-Cookie und ein CSRF-Cookie.
- `GET /api/me` liefert das eigene Profil samt Mitgliedschaften.
- `GET /api/workpackages` und `/api/workpackages/{code}` liefern die
  Daten aus dem Seed.
- `GET /portal/` zeigt nach Login ein minimales Cockpit mit den
  eigenen Arbeitspaketen.
- Eine Person mit `must_change_password = true` wird beim ersten
  Login zur Passwortänderung gezwungen.
- `pytest` läuft grün; `ruff check` ist sauber.

Sprint 1 implementiert **noch nicht**: Dokumentenregister, Storage,
Audit-Log, öffentliche Download-Bibliothek, Status-/Visibility-Workflow,
Review-Pipeline, SSO. Diese sind Sprint 2+.

---

## 2. Datenbanktabellen und Felder

Felder folgen exakt der MVP-Spezifikation §4. Konventionen:

- Primärschlüssel `id` als **`CHAR(36)`-UUID v4** (dialektneutral —
  funktioniert mit SQLite und PostgreSQL identisch).
- `created_at`, `updated_at` als `TIMESTAMP WITH TIME ZONE` (in
  SQLite über SQLAlchemys `DateTime(timezone=True)` portabel
  abgebildet); Server-Default: `CURRENT_TIMESTAMP`.
- `is_deleted` als `BOOLEAN NOT NULL DEFAULT FALSE`, optional mit
  `deleted_at TIMESTAMP NULL` für Audit-Spuren ab Sprint 3.

### `partner`

| Feld         | Typ          | Constraints                           |
| ------------ | ------------ | ------------------------------------- |
| id           | CHAR(36)     | PK                                    |
| name         | TEXT         | NOT NULL, UNIQUE                      |
| short_name   | TEXT         | NOT NULL, UNIQUE                      |
| country      | CHAR(2)      | NOT NULL                              |
| website      | TEXT         | NULL                                  |
| is_deleted   | BOOLEAN      | NOT NULL, DEFAULT FALSE               |
| created_at   | TIMESTAMP    | NOT NULL                              |
| updated_at   | TIMESTAMP    | NOT NULL                              |

### `person`

| Feld                 | Typ          | Constraints                           |
| -------------------- | ------------ | ------------------------------------- |
| id                   | CHAR(36)     | PK                                    |
| email                | TEXT         | NOT NULL, UNIQUE (case-insensitive)   |
| display_name         | TEXT         | NOT NULL                              |
| partner_id           | CHAR(36)     | NOT NULL, FK → `partner.id`           |
| password_hash        | TEXT         | NOT NULL                              |
| platform_role        | TEXT         | NOT NULL, CHECK in (`admin`,`member`) |
| is_active            | BOOLEAN      | NOT NULL, DEFAULT TRUE                |
| must_change_password | BOOLEAN      | NOT NULL, DEFAULT TRUE                |
| is_deleted           | BOOLEAN      | NOT NULL, DEFAULT FALSE               |
| created_at           | TIMESTAMP    | NOT NULL                              |
| updated_at           | TIMESTAMP    | NOT NULL                              |

E-Mail-Eindeutigkeit wird beim Schreiben in den Service durch
Lowercasing erzwungen; das DB-`UNIQUE`-Constraint reicht in Kombination
für Sprint 1.

### `workpackage`

| Feld                  | Typ          | Constraints                                |
| --------------------- | ------------ | ------------------------------------------ |
| id                    | CHAR(36)     | PK                                         |
| code                  | TEXT         | NOT NULL, UNIQUE                           |
| title                 | TEXT         | NOT NULL                                   |
| description           | TEXT         | NULL                                       |
| parent_workpackage_id | CHAR(36)     | NULL, FK → `workpackage.id`                |
| lead_partner_id       | CHAR(36)     | NOT NULL, FK → `partner.id`                |
| sort_order            | INTEGER      | NOT NULL, DEFAULT 0                        |
| is_deleted            | BOOLEAN      | NOT NULL, DEFAULT FALSE                    |
| created_at            | TIMESTAMP    | NOT NULL                                   |
| updated_at            | TIMESTAMP    | NOT NULL                                   |

`sort_order` wird beim Seed aus dem numerischen Code berechnet
(`WP3` → 30, `WP3.1` → 31, `WP3.2` → 32; siehe §6.3).

### `membership`

| Feld           | Typ          | Constraints                                          |
| -------------- | ------------ | ---------------------------------------------------- |
| id             | CHAR(36)     | PK                                                   |
| person_id      | CHAR(36)     | NOT NULL, FK → `person.id`                           |
| workpackage_id | CHAR(36)     | NOT NULL, FK → `workpackage.id`                      |
| wp_role        | TEXT         | NOT NULL, CHECK in (`wp_lead`, `wp_member`)          |
| created_at     | TIMESTAMP    | NOT NULL                                             |

`UNIQUE (person_id, workpackage_id)`.

`membership` ist eine reine Verknüpfungstabelle und trägt **kein**
`is_deleted`. Aufheben einer Mitgliedschaft heißt löschen.

### Indexe

| Tabelle      | Index                                    | Zweck                       |
| ------------ | ---------------------------------------- | --------------------------- |
| `partner`    | `UNIQUE (short_name)`, `UNIQUE (name)`    | Stammdaten-Eindeutigkeit    |
| `person`     | `UNIQUE (email)`                          | Login-Lookup                |
| `workpackage`| `UNIQUE (code)`, INDEX (parent_workpackage_id) | Hierarchie-Lookups |
| `membership` | `UNIQUE (person_id, workpackage_id)`     | Doppelmitgliedschaft sperren |

### Nicht in Sprint 1

`document`, `document_version`, `audit_log`, `milestone`. Bewusst
weggelassen — Sprint 2+.

---

## 3. Alembic-Migrationen

Eine einzige zusammengelegte Revision für Sprint 1:

- Datei: `backend/alembic/versions/<datum>_0002_identity_and_project.py`
- `down_revision = "0001_baseline"`
- `revision = "0002_identity_and_project"`

`upgrade()` legt die vier Tabellen mit allen Constraints an.
Reihenfolge: `partner` → `person` → `workpackage` → `membership`
(FK-Reihenfolge).

`downgrade()` droppt sie in umgekehrter Reihenfolge.

### Dialektneutralität

- `sa.String(length=36)` für UUID-Spalten (statt `sa.UUID`, weil
  letzteres in SQLite umständlich ist).
- `sa.DateTime(timezone=True)` für Zeitstempel.
- `sa.CheckConstraint("platform_role IN ('admin','member')",
  name="ck_person_platform_role")` und analog für `wp_role`.
- Kein JSON, keine Arrays in Sprint 1.

### `render_as_batch`

Die SQLite-Variante in `alembic/env.py` rendert bereits im
Batch-Modus (Sprint-0-Setup). Für die neuen Tabellen ist das nicht
zwingend nötig, aber unschädlich — Alter-Operationen werden in Sprint
2+ kommen und davon profitieren.

---

## 4. Services

Alle unter `ref4ep/services/`. Konstruktor-Signatur einheitlich:

```python
class FooService:
    def __init__(self, session: Session, *, role: str | None = None,
                 person_id: str | None = None) -> None: ...
```

Schreibende Methoden rufen einen Helper `_require_admin()` /
`_require_member()` auf. Verstöße werfen `PermissionError`, das die
Routen-Schicht auf HTTP 403 mappt.

In Sprint 1 wird **noch kein** Audit-Log geschrieben. Die
Service-Methoden tragen aber bereits einen
`# TODO Sprint 3: audit_logger.log_action(...)`-Marker, damit der
Hook-Punkt beim Audit-Sprint sichtbar ist.

### `services/auth.py` (modulare Helper, kein Service-Objekt)

- `hash_password(plain: str) -> str` — Argon2id über
  `argon2.PasswordHasher`.
- `verify_password(plain: str, hashed: str) -> bool`.
- `needs_rehash(hashed: str) -> bool`.
- `create_session_token(person_id: str, secret: str) -> str` —
  HMAC-SHA256 aus der Python-Stdlib (`hmac` + `hashlib`), Token-
  Format `<person_id>.<unix_ts>.<hex_signature>`. Übernimmt
  unverändert das Muster aus
  `lab_management/api/deps.py::create_session_token`. **Keine**
  Zusatz-Dependency.
- `read_session_token(token: str, secret: str, max_age_seconds: int) -> str | None` —
  splittet das Token, vergleicht die Signatur mit
  `hmac.compare_digest`, prüft das Alter gegen
  `time.time() - ts > max_age_seconds`. Liefert die `person_id`
  oder `None` bei ungültiger/abgelaufener Signatur (kein
  Exception-Mix wie bei itsdangerous nötig).
- `create_csrf_token() -> str` — `secrets.token_urlsafe(32)`.
- `verify_csrf(cookie_token: str, header_token: str) -> bool` —
  konstantzeitiger Vergleich.

### `services/partner_service.py`

Methoden:

- `list_partners(*, include_deleted: bool = False) -> list[Partner]`
- `get_by_short_name(short_name: str) -> Partner | None`
- `get_by_id(partner_id: str) -> Partner | None`
- `create(*, name: str, short_name: str, country: str, website: str | None) -> Partner`
- `update(partner_id, **fields) -> Partner`
- `soft_delete(partner_id) -> None`

Schreiboperationen verlangen `admin`.

### `services/person_service.py`

Methoden:

- `authenticate(email: str, password: str) -> Person | None` — gibt
  `None` zurück bei falschem Passwort, deaktiviert oder soft-deleted.
  Bei Erfolg wird ein Re-Hash ausgeführt, falls `needs_rehash`.
- `get_by_email(email: str) -> Person | None`
- `get_by_id(person_id: str) -> Person | None`
- `create(*, email: str, display_name: str, partner_id: str,
  password: str, platform_role: str = "member") -> Person` —
  setzt `must_change_password = True`.
- `change_password(person_id: str, old: str, new: str) -> None` —
  Mindestlänge 10 Zeichen, prüft `old` gegen aktuellen Hash.
- `reset_password(person_id: str, new_password: str) -> None` —
  Admin-only, setzt `must_change_password = True`.
- `set_role(person_id: str, role: str) -> None` — Admin-only.
- `enable(person_id) / disable(person_id)` — Admin-only.
- `list_persons() -> list[Person]`

### `services/workpackage_service.py`

Methoden:

- `list_workpackages(*, parents_only: bool = False) -> list[Workpackage]` —
  sortiert nach `sort_order`.
- `get_by_code(code: str) -> Workpackage | None`
- `get_children(parent_id: str) -> list[Workpackage]`
- `create(*, code, title, description, parent_code: str | None,
  lead_partner_short_name: str, sort_order: int | None) -> Workpackage`
- `update(...)`
- `add_membership(person_id, workpackage_id, wp_role)`
- `remove_membership(membership_id)`
- `list_memberships(*, person_id: str | None = None,
  workpackage_id: str | None = None)`

Schreibend admin-only in Sprint 1 (WP-Mitglieder dürfen erst ab
Sprint 2 selber Inhalte anlegen).

### `services/seed_service.py`

Eine einzige Methode `apply_initial_seed(*, source: str = "antrag") -> dict[str, int]`,
die idempotent die Daten aus §13 der MVP-Spec lädt:

1. Partner aus YAML einlesen, fehlende anlegen.
2. Parent-WPs anlegen, `lead_partner_id` aus dem Partner-Mapping.
3. Sub-WPs anlegen, `parent_workpackage_id` aus dem Parent-Code,
   `lead_partner_id` per Vererbung vom Parent.
4. Rückgabe: `{"partners_added": n, "workpackages_added": n,
   "skipped_existing": n}`.

**Idempotenz-Regel:** Existiert ein Datensatz mit demselben Code
(WP) bzw. Short-Name (Partner) bereits, wird er **nicht** überschrieben
und nicht angetastet. Manuelle Korrekturen am Datenbestand bleiben
erhalten. Die Methode legt nur fehlende Datensätze an.

---

## 5. API-Endpunkte

Alle unter Präfix `/api`. Antworten als JSON. CSRF-Header
`X-CSRF-Token` für POST/PATCH/DELETE.

Schreibende Stammdaten-Endpunkte (POST `/api/admin/partners`,
`/api/admin/persons`, `/api/admin/workpackages`,
`/api/admin/memberships`) sind in Sprint 1 **noch nicht** vorgesehen
— Schreiben passiert über die CLI. Die Routen werden in Sprint 5
(„Polieren") nachgereicht. Begründung: Sprint 1 bringt sonst zu viel
in einen Sprint.

### Auth

| Methode | Pfad                  | Zweck                                | Rolle               |
| ------- | --------------------- | ------------------------------------ | ------------------- |
| POST    | `/api/auth/login`     | Login mit E-Mail + Passwort (JSON)   | anonym              |
| POST    | `/api/auth/logout`    | Session beenden                      | eingeloggt          |
| POST    | `/api/auth/password`  | Eigenes Passwort ändern              | eingeloggt          |
| GET     | `/api/me`             | Profil + Memberships + WP-Info       | eingeloggt          |

`POST /api/auth/login` Request-Body:

```json
{ "email": "...", "password": "..." }
```

Response 200:

```json
{
  "person": {
    "id": "...",
    "email": "...",
    "display_name": "...",
    "platform_role": "member",
    "must_change_password": false,
    "partner": { "short_name": "JLU", "name": "..." }
  },
  "must_change_password": false
}
```

Setzt zwei Cookies: `ref4ep_session` (HttpOnly) und `ref4ep_csrf`
(nicht HttpOnly).

Response 401 bei falschen Credentials oder deaktiviertem Konto —
**keine** Unterscheidung in der Fehlermeldung (Aufzählungs-Schutz).

### Stammdaten (lesend)

| Methode | Pfad                                | Zweck                          | Rolle      |
| ------- | ----------------------------------- | ------------------------------ | ---------- |
| GET     | `/api/partners`                     | Liste Partner                  | eingeloggt |
| GET     | `/api/persons`                      | Liste Personen                 | eingeloggt |
| GET     | `/api/workpackages`                 | Liste WPs (Parent+Sub)         | eingeloggt |
| GET     | `/api/workpackages/{code}`          | WP-Detail mit Kindern und      | eingeloggt |
|         |                                     | Mitgliedern                    |            |

`GET /api/workpackages` unterstützt `?parent_only=true` als
Filter-Query. Ohne Parameter: alle WPs (parent + sub) sortiert nach
`sort_order`.

`GET /api/workpackages/{code}` liefert:

```json
{
  "code": "WP3",
  "title": "Referenz-Halltriebwerk",
  "description": null,
  "parent": null,
  "lead_partner": { "short_name": "TUD", "name": "..." },
  "children": [
    { "code": "WP3.1", "title": "Konstruktion Ref-HT", "lead_partner": { "short_name": "TUD" } },
    ...
  ],
  "memberships": [
    { "person": { "email": "...", "display_name": "..." }, "wp_role": "wp_lead" },
    ...
  ]
}
```

### Konventionen

- 401 ohne gültige Session.
- 403 für Rollen-Verstöße (in Sprint 1 selten relevant —
  Lese-Routen sind für jeden eingeloggten Member offen).
- 404 für „nicht gefunden oder soft-deleted" (keine Existenz-Leakage).
- 422 für Validierungsfehler (Pydantic-Default).

---

## 6. CLI-Seed-Befehl und weitere CLI-Subcommands

### 6.1 Seed-Quelldatei

`backend/src/ref4ep/cli/seed_data/antrag_initial.yaml` —
versionierter, manuell gepflegter YAML-Inhalt entsprechend §13 der
MVP-Spec.

Schema (Auszug):

```yaml
partners:
  - short_name: JLU
    name: Justus-Liebig-Universität Gießen
    country: DE
  - short_name: IOM
    name: Leibniz-Institut für Oberflächenmodifizierung e. V., Leipzig
    country: DE
  # ... CAU, THM, TUD

workpackages:
  - code: WP1
    title: "Projektmanagement, Daten und Dissemination"
    lead: JLU
  - code: WP1.1
    title: "Projektmanagement"
    parent: WP1
  - code: WP1.2
    title: "Standardisierung & Formate"
    parent: WP1
  - code: WP2
    title: "Referenz-Gitterionenquelle"
    lead: IOM
  # ... vollständige Liste aller acht Parent-WPs und 27 Sub-WPs
```

Sub-WPs **ohne** explizites `lead`-Feld erben den Lead des Parents
(siehe §13.4 der MVP-Spec). Sub-WPs **mit** `lead`-Feld überschreiben
die Vererbung.

Verbindlich für Sprint 1: alle 8 Parent-WPs mit Titel und
Lead-Partner gemäß §13.4-Tabelle, alle 27 Sub-WPs mit Titel und
Parent-Verweis.

### 6.2 `ref4ep-admin seed`

Bereits in Sprint 0 als Stub vorhanden. Sprint 1 ersetzt den Stub:

```
ref4ep-admin seed --from antrag
```

Verhalten:

1. Liest die YAML-Quelle (Pfad relativ zum Paket, via
   `importlib.resources`).
2. Öffnet eine DB-Session.
3. Ruft `SeedService.apply_initial_seed(source="antrag")` auf.
4. Druckt knappe Zusammenfassung:
   ```
   Seed-Quelle: antrag
   Partner: 5 angelegt, 0 übersprungen
   Workpackages: 35 angelegt (8 Hauptarbeitspakete + 27 Unterarbeitspakete), 0 übersprungen
   ```
5. Exit 0 bei Erfolg, 1 bei Fehler.

Bei zweitem Lauf:
```
Partner: 0 angelegt, 5 übersprungen
Workpackages: 0 angelegt, 35 übersprungen (8 Hauptarbeitspakete + 27 Unterarbeitspakete)
```

### 6.3 Weitere CLI-Subcommands

| Subcommand                                                      | Zweck                                              |
| --------------------------------------------------------------- | -------------------------------------------------- |
| `ref4ep-admin partner list`                                     | Tabelle aller Partner                              |
| `ref4ep-admin partner create --short-name --name --country [--website]` | Partner anlegen                            |
| `ref4ep-admin workpackage list`                                 | Tabelle aller WPs (sortiert)                       |
| `ref4ep-admin workpackage create --code --title --lead [--parent] [--description]` | WP anlegen                  |
| `ref4ep-admin person list`                                      | Tabelle aller Personen                             |
| `ref4ep-admin person create --email --display-name --partner [--role admin\|member]` | Person anlegen, Passwort interaktiv |
| `ref4ep-admin person reset-password --email`                    | Setzt neues Passwort, `must_change_password=True`  |
| `ref4ep-admin person set-role --email --role`                   | `admin` oder `member`                              |
| `ref4ep-admin person enable --email`                            | `is_active = true`                                 |
| `ref4ep-admin person disable --email`                           | `is_active = false`                                |
| `ref4ep-admin membership add --person --workpackage --role`     | `wp_lead` oder `wp_member`                         |
| `ref4ep-admin membership remove --person --workpackage`         | Mitgliedschaft löschen                             |

Pflicht-Konventionen:

- Passwörter werden **nie** als Argument übergeben — immer per
  `getpass`-Prompt (keine Shell-History).
- `--partner` und `--lead` referenzieren über `short_name`.
- `--workpackage` referenziert über `code`.
- Alle Aktionen verwenden `actor_id="cli-admin"` — vorerst nur als
  Marker im Log, ab Sprint 3 als Audit-Eintrag.

---

## 7. Auth/Login-Konzept

### 7.1 Passwort-Hashing

- `argon2-cffi` (`argon2.PasswordHasher`) mit Default-Parametern.
- Mindestlänge bei jedem Setzen: **10 Zeichen** (Validierung in
  `PersonService`, nicht in der Route).
- Re-Hash on login bei `needs_rehash` (Parameter-Drift in
  zukünftigen `argon2-cffi`-Versionen).
- Keine Klartext-Persistierung, kein Passwort-Logging.

### 7.2 Sessions

- **Implementierung mit Python-Stdlib** (`hmac`, `hashlib`, `time`),
  ohne Zusatz-Dependency. Übernimmt das bewährte Muster aus dem
  Referenzsystem
  (`jluspaceforge-reference/src/lab_management/api/deps.py`,
  Funktionen `create_session_token` und `verify_session_token`).
- Token-Format: `<person_id>.<unix_ts>.<hex_signature>`.
- Signatur: `hmac.new(secret, "<person_id>.<unix_ts>", sha256).hexdigest()`.
- Verifikation: `hmac.compare_digest` (konstantzeitiger Vergleich)
  und Altersprüfung über `time.time() - ts > session_max_age`.
- Cookie-Name: `ref4ep_session`.
- Lebensdauer: **7 Tage** ab Login (kein Sliding für Sprint 1).
- Cookie-Flags: `HttpOnly`, `SameSite=Lax`, `Secure` nur in Prod
  (gesteuert über eine neue Settings-Variable `cookie_secure`,
  Default `False` in Dev).
- Begründung gegen `itsdangerous`/`TimestampSigner`: Das Stdlib-Muster
  ist ~25 Codezeilen, deckt denselben Anwendungsfall ab und führt
  keine zusätzliche Auth-Dependency ein. Das Referenzsystem läuft
  produktiv mit derselben Implementierung.

### 7.3 CSRF

- Double-Submit-Pattern.
- Cookie-Name: `ref4ep_csrf`, Wert: 32 Zeichen URL-safe Random,
  **nicht** HttpOnly (JS muss lesen).
- Header: `X-CSRF-Token`.
- Pflicht für alle `POST`, `PATCH`, `PUT`, `DELETE`. Ausnahmen:
  `POST /api/auth/login` (vor Login existiert noch kein Token).
- Implementiert als FastAPI-Dependency `require_csrf`, die der
  Router von schreibenden Endpunkten konsumiert.

### 7.4 Settings-Erweiterung

Neue Felder in `Settings` (`api/config.py`):

| Feld                | Env-Variable                  | Default     | Pflicht? |
| ------------------- | ----------------------------- | ----------- | -------- |
| `session_secret`    | `REF4EP_SESSION_SECRET`       | `""`        | **ja, lazy validiert** (≥ 32 Zeichen, siehe unten) |
| `session_max_age`   | `REF4EP_SESSION_MAX_AGE`      | `604800` (7d in Sek.) | nein |
| `cookie_secure`     | `REF4EP_COOKIE_SECURE`        | `False`     | nein     |

**Validierungsstrategie — bewusst lazy:** Die Mindestlängenprüfung
des `session_secret` erfolgt **nicht** beim App-Start, sondern erst
beim ersten Aufruf von `services.auth.create_session_token`.
Konkret: `create_session_token` wirft `RuntimeError` mit klarer
Meldung, sobald `session_secret` leer oder kürzer als 32 Zeichen
ist. Begründung:

- Modul-Import (`from ref4ep.api.app import app`) und
  `create_app()` bleiben für Tests und lokale Entwicklung möglich,
  ohne dass eine Env-Variable gesetzt sein muss. Reine Lese-
  Endpunkte und der `/api/health`-Ping funktionieren auch ohne
  konfiguriertes Secret.
- Tests injizieren ein festes Test-Secret über die
  `Settings(session_secret=…)`-Fixture und die
  `create_app(settings=…)`-Factory.
- Sobald produktiv ein Login versucht wird, schlägt der Aufruf
  von `create_session_token` ohne gesetztes Secret deterministisch
  fehl — kein stilles Weiterlaufen mit unsicheren Defaults.

### 7.5 Login-Flow

1. Benutzer ruft `GET /login` auf → Jinja2-Form (Sprint-1-neu, siehe §9).
2. Form sendet `POST /login` (`application/x-www-form-urlencoded`)
   oder JS sendet `POST /api/auth/login` (JSON).
3. `PersonService.authenticate(email, password)`:
   - Liefert `None` bei falschem Passwort, deaktivierter Person oder
     soft-deleted Person → 401 mit generischer Meldung.
   - Liefert `Person` bei Erfolg.
4. Bei Erfolg: Session-Cookie und CSRF-Cookie setzen.
5. Wenn `must_change_password = True` ist: JSON-Antwort enthält
   `must_change_password: true` und das Frontend leitet zu
   `/portal/account` (Passwort-Ändern-Maske); Form-basiert
   redirected der Server direkt dorthin.
6. **Logout** läuft über zwei Pfade:
   - `POST /api/auth/logout` (JSON-API): **CSRF-pflichtig** über
     `require_csrf`-Dependency. Antwortet mit
     `{"status": "ok"}` und löscht beide Cookies (`Set-Cookie` mit
     `Max-Age=0`).
   - `POST /logout` (serverseitiger Form-Post aus dem SPA-Header):
     **in Sprint 1 noch nicht CSRF-pflichtig**. Begründung: der
     Form-Post setzt sowieso voraus, dass eine gültige Session-
     Cookie vorliegt (`get_current_person`-Dependency); der
     Schadenshorizont ist ein erzwungener Logout, kein Datenleck.
     Eine konsequente CSRF-Pflicht auf dem Form-Pfad ist als
     Verschärfung in Sprint 5 (Polish/UAT) vorgesehen — gleicher
     Mechanismus wie bei der API.

### 7.6 FastAPI-Dependencies (Injection-Helfer)

`api/deps.py` erhält:

- `get_session()` — SQLAlchemy-Session pro Request (yield).
- `get_current_person(request, session) -> Person` — liest und
  validiert `ref4ep_session`-Cookie; bei Fehler `HTTPException(401)`.
- `get_optional_person(request, session) -> Person | None` — wie
  oben, aber liefert `None` statt zu werfen (für gemischte Routen).
- `require_csrf(request)` — prüft Cookie/Header-Match.
- `get_auth_context(person, session)` — baut ein
  `AuthContext`-Dataclass mit `platform_role` und
  `memberships` für die Service-Konstruktion.

### 7.7 Paket-Dependencies (pyproject.toml)

Sprint 1 fügt **drei** neue Laufzeit-Dependencies in
`backend/pyproject.toml` hinzu:

| Paket              | Verwendung                                                                                       |
| ------------------ | ------------------------------------------------------------------------------------------------ |
| `argon2-cffi`      | Passwort-Hashing über `argon2.PasswordHasher` (siehe §7.1).                                      |
| `pyyaml`           | Direkter Loader für die YAML-Quelldatei des Initial-Seeds (`cli/seed_data/antrag_initial.yaml`,  |
|                    | siehe §6.1). Wird zwar indirekt schon über `uvicorn[standard]` installiert, ist aber direkt      |
|                    | importiert (`import yaml`) und deshalb explizit ausgewiesen — keine versteckte Transitiv-        |
|                    | abhängigkeit für eine Pflicht-Funktion des CLI.                                                  |
| `python-multipart` | Pflicht für FastAPIs `Form()`-Parsing beim serverseitig gerenderten Login-Formular               |
|                    | (`POST /login`, siehe §9.2). Ohne dieses Paket wirft Starlette beim Form-Submit                  |
|                    | einen Import-Fehler.                                                                             |

**Bewusst nicht hinzugefügt:**

| Paket          | Begründung                                                                              |
| -------------- | --------------------------------------------------------------------------------------- |
| `itsdangerous` | Sessions werden mit Python-Stdlib (`hmac`, `hashlib`, `time`) signiert (siehe §7.2).    |

Damit wächst der Sprint-1-Stack gegenüber Sprint 0 um eine
Auth-Bibliothek (`argon2-cffi`) sowie zwei kleine Format-/Form-
Helfer (`pyyaml`, `python-multipart`). Kein Frontend-Build, kein
Templating-Wechsel, keine zusätzliche Cookie- oder Token-Bibliothek.

---

## 8. Rollen und Rechte (in Sprint 1 effektiv)

Aus MVP-Spec §3:

- Globale Plattformrolle: `admin` oder `member`.
- WP-Rolle pro Mitgliedschaft: `wp_lead` oder `wp_member`.

In Sprint 1 wirkt sich das so aus:

| Aktion                                   | In Sprint 1 erlaubt für         |
| ---------------------------------------- | ------------------------------- |
| Login                                    | jede aktive Person              |
| `GET /api/me`, `/partners`, `/persons`,  | jede eingeloggte Person          |
| `/workpackages`, `/workpackages/{code}`  |                                 |
| `POST /api/auth/password`                | jede eingeloggte Person für sich |
| Stammdaten-Schreiben (CLI)               | nur `cli-admin`-Aufrufer         |

**WP-Rollen werden gespeichert, aber in Sprint 1 noch nicht
ausgewertet.** Sie werden ab Sprint 2 (Dokumente) für
Berechtigungsprüfungen verwendet.

Helper in `services/auth.py` oder einem neuen
`services/permissions.py`:

- `can_admin(role: str) -> bool`
- `is_member_of(auth: AuthContext, workpackage_id: str) -> bool`
- `is_wp_lead(auth: AuthContext, workpackage_id: str) -> bool`

`is_wp_lead` und `is_member_of` werden in Sprint 1 noch nicht von
einer Route aufgerufen, sind aber bereits implementiert und getestet —
das vermeidet Lecks in Sprint 2.

---

## 9. Web-Ansichten

### 9.1 Public-Zone (Erweiterung aus Sprint 0)

- `GET /partners` (öffentlich erreichbar, kein Login):
  Jinja2-Template `templates/public/partners.html` mit der Liste der
  fünf Partner aus dem Seed (Name, Land, Website-Link wenn vorhanden).
  Verwendet einen schmalen Service-Read-Pfad, der nur nicht-gelöschte
  Partner ausliefert.
- Bestehend: `/`, `/legal/imprint`, `/legal/privacy`.

### 9.2 Login-Seite

- `GET /login` → `templates/login.html`, einfache HTML-Form mit
  Feldern E-Mail und Passwort.
- `POST /login` → akzeptiert Form-Submit (Content-Type
  `application/x-www-form-urlencoded`), führt
  `PersonService.authenticate` aus, setzt Cookies, redirected zu
  `/portal/` bzw. `/portal/account` bei `must_change_password`.

Diese serverseitige Form gibt es **zusätzlich** zu `POST /api/auth/login`
(JSON). Die Form ist die JS-freie Variante; der JSON-Endpoint
ist für die SPA und für CLI-/Tool-Aufrufe.

### 9.3 SPA-Shell (Erweiterung aus Sprint 0)

`backend/src/ref4ep/web/`:

- `index.html` — Shell mit Header, Navigation und einem leeren
  `<main id="app">`. Lädt `app.js` und `common.js`.
- `app.js` — implementiert:
  - Auth-Check beim Laden (`GET /api/me`); 401 → Redirect zu `/login`.
  - History-API-Routing für die Pfade `/portal/`,
    `/portal/workpackages`, `/portal/workpackages/<code>`,
    `/portal/account`.
  - Modul-Loader: lädt das passende Skript aus `web/modules/`.
- `common.js` — Fetch-Wrapper, der automatisch
  `X-CSRF-Token` aus dem `ref4ep_csrf`-Cookie setzt, JSON kodiert
  und 401 zentral behandelt (Logout-Redirect).

Module unter `web/modules/`:

- `cockpit.js` — `/portal/`: Begrüßung mit `display_name`, eigene
  Mitgliedschaften, Liste der zugeordneten WPs als Karten.
- `workpackages.js` — `/portal/workpackages`: Liste aller WPs mit
  Filter „eigene" / „alle"; Klick auf einen Eintrag öffnet
  `/portal/workpackages/<code>`.
- `workpackage_detail.js` — `/portal/workpackages/<code>`: Titel,
  Beschreibung, Lead-Partner, Sub-WPs, Mitglieder.
- `account.js` — `/portal/account`: Profilanzeige plus
  Passwort-Ändern-Form. Pflichtmaske, wenn
  `must_change_password = true`.

### 9.4 Backend-Anpassung für SPA-Routing

FastAPI liefert für unbekannte Pfade unter `/portal/...` weiterhin
die `index.html` aus (per `StaticFiles(html=True)` reicht das **nicht**
aus für tiefe Routen). Lösung: ein Catch-All-Handler

```
GET /portal/{full_path:path}
```

der bei nicht-existierenden Asset-Pfaden die `index.html`
zurückliefert. Asset-Pfade (`/portal/app.js`, `/portal/style.css`,
`/portal/modules/...`) werden weiterhin von `StaticFiles` bedient
und gehen am Catch-All vorbei.

---

## 10. Tests

Baut auf Sprint-0-`conftest.py` auf, ergänzt um:

- `engine`-Fixture, die nach App-Erstellung `Base.metadata.create_all`
  laufen lässt (oder Alembic upgrade head — siehe unten).
- `seeded_session`-Fixture, die `apply_initial_seed` aufruft.
- `admin_person`- und `member_person`-Fixtures, die je eine Person mit
  bekanntem Passwort anlegen und loggen sich ein, liefern den
  authentifizierten `TestClient`.

Empfohlener Setup-Pfad in der Fixture: **Alembic upgrade head** auf
die temporäre SQLite-Datei. Vorteil: testet das echte
Migrationsskript, kein Doppel-Setup.

### 10.1 Service- und Helper-Tests (`tests/services/`)

- `test_auth_helpers.py` — hash/verify, needs_rehash,
  session-token roundtrip, CSRF-Vergleich konstantzeitig.
- `test_partner_service.py` — list/get/create/soft_delete,
  Eindeutigkeit `short_name`.
- `test_person_service.py` — create (mit Argon2-Hash, Mindestlänge),
  authenticate (Erfolg, falsches Passwort, deaktiviert,
  case-insensitive E-Mail), change_password, reset_password,
  set_role, enable/disable.
- `test_workpackage_service.py` — list mit/ohne `parents_only`,
  get_by_code, get_children, add_membership, Doppel-Membership-Sperre.
- `test_seed_service.py` —
  - `apply_initial_seed` lädt **5 Partner** sowie
    **35 Workpackage-Einträge: 8 Hauptarbeitspakete + 27
    Unterarbeitspakete**.
  - Lead-Vererbung: jedes Sub-WP `WPx.y` hat
    `lead_partner = lead_partner(WPx)` (z. B. WP3.1 → TUD,
    WP6.4 → IOM).
  - Zweiter Aufruf legt nichts neu an (Idempotenz).
  - Manuell geänderter WP-Titel überlebt einen erneuten Seed-Lauf.

### 10.2 API-Tests (`tests/api/`)

- `test_auth_login.py`:
  - Login mit korrekten Credentials → 200, beide Cookies gesetzt.
  - Login mit falschem Passwort → 401, generische Meldung.
  - Login mit deaktivierter Person → 401, generische Meldung.
  - Login mit `must_change_password=true` → Antwort enthält Flag.
  - Login mit nicht existierender E-Mail → 401, generische Meldung.
- `test_auth_logout.py` — Cookies werden gelöscht; nachfolgender
  Aufruf von `/api/me` → 401.
- `test_auth_password.py` — Password-Change mit korrektem
  Alt-Passwort: 200, must_change_password = False; mit falschem:
  400; ohne CSRF: 403.
- `test_api_me.py` — 401 ohne Cookie, 200 mit Cookie, enthält
  `partner.short_name` und `memberships`.
- `test_api_partners.py` — 401 ohne Login, 200 mit Login, fünf
  Einträge nach Seed.
- `test_api_workpackages.py` — Liste, Filter `parent_only=true`,
  Detail per Code mit Children und Memberships.
- `test_csrf.py` — POST-Endpunkt ohne `X-CSRF-Token` → 403, mit
  falschem Token → 403, mit korrektem → 200.

### 10.3 CLI-Tests (`tests/cli/`)

- `test_cli_partner.py` — `partner create`, `partner list`.
- `test_cli_person.py` — `person create` (Passwort über stdin
  injizieren), anschließendes `authenticate()` aus dem Service
  bestätigt den Hash, `person reset-password`, `set-role`.
- `test_cli_workpackage.py` — `workpackage create` mit/ohne Parent.
- `test_cli_membership.py` — `add`, `remove`.
- `test_cli_seed.py` —
  - Seed-Lauf legt 5 Partner und 35 Workpackage-Einträge
    (8 Hauptarbeitspakete + 27 Unterarbeitspakete) an, Exit 0.
  - Zweiter Lauf legt 0 + 0 an, Exit 0.
  - Strukturprüfung: WP3 hat 3 Unterarbeitspakete, WP4 hat 6
    Unterarbeitspakete, WP8.3 existiert mit Titel
    „Energiekalibrierung".

### 10.4 Migrations-Tests (`tests/test_migrations.py`)

Erweiterung der bestehenden Datei:

- `test_upgrade_head_creates_identity_tables` — nach Upgrade
  existieren die Tabellen `partner`, `person`, `workpackage`,
  `membership` mit den erwarteten Spalten.
- `test_downgrade_to_baseline_drops_identity_tables` — Downgrade auf
  `0001_baseline` entfernt sie wieder vollständig.

### 10.5 Coverage-Ziel

Sprint 1 ist groß genug für ein erstes Coverage-Ziel: **mindestens
80 %** über `ref4ep/services/`, `ref4ep/cli/` und `ref4ep/api/`.
Konfiguration in `pyproject.toml` ergänzen
(`pytest --cov=ref4ep --cov-report=term-missing`). Kein hartes
Gate, aber in CI sichtbar.

---

## 11. Lokale Prüf- und Startbefehle

### 11.1 Migration und Seed

```bash
cd backend
source .venv/bin/activate           # Windows: .venv\Scripts\Activate.ps1
export REF4EP_SESSION_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
alembic upgrade head                # 0002_identity_and_project anwenden
ref4ep-admin seed --from antrag     # Initial-Seed laden
ref4ep-admin partner list           # erwartet: 5 Zeilen (JLU, IOM, CAU, THM, TUD)
ref4ep-admin workpackage list       # erwartet: 35 Workpackage-Einträge (8 Hauptarbeitspakete + 27 Unterarbeitspakete)
```

> **Hinweis zur lokalen Default-DB:** Manuelle Smoke-Tests gegen den
> Sprint-1-Default schreiben in
> `ref4ep-portal/data/ref4ep.db` (Pfad relativ zu `backend/` =
> `../data/ref4ep.db`). Diese Datei ist über `.gitignore` aus dem
> Repo ausgeschlossen — wiederholte Seed-/Login-Smoke-Tests
> verfälschen also weder den Repo-Stand noch die CI-Läufe (die
> verwenden frische `tmp_path`-DBs pro Test). Wer den Smoke-Stand
> zurücksetzen möchte: `rm ../data/ref4ep.db && alembic upgrade head`
> und ggf. erneut `ref4ep-admin seed --from antrag`.

### 11.2 Erste Person anlegen

```bash
ref4ep-admin person create \
  --email kristof.holste@physik.jlug.de \
  --display-name "Kristof Holste" \
  --partner JLU \
  --role admin
# Passwort interaktiv (mind. 10 Zeichen)
```

### 11.3 Server starten und manuell prüfen

```bash
uvicorn ref4ep.api.app:app --reload --port 8000
```

Browser-Prüfungen:

- `http://localhost:8000/` — Public-Steckbrief (Sprint 0)
- `http://localhost:8000/partners` — Public-Partnerliste (Sprint 1 neu)
- `http://localhost:8000/login` — Login-Form
- nach Login → `http://localhost:8000/portal/` — Cockpit
- `http://localhost:8000/portal/workpackages` — WP-Liste
- `http://localhost:8000/portal/workpackages/WP3` — WP-Detail mit
  drei Sub-WPs
- `http://localhost:8000/portal/account` — eigenes Profil
- `http://localhost:8000/api/me` — JSON-Profil

### 11.4 Tests, Linter

```bash
pytest                              # alle Tests
pytest --cov=ref4ep --cov-report=term-missing
ruff check src tests
ruff format --check src tests
```

### 11.5 Optional: PostgreSQL-Gegenprobe

```bash
pip install -e ".[dev,postgres]"
export REF4EP_DATABASE_URL="postgresql+psycopg://ref4ep:ref4ep@localhost:5432/ref4ep"
alembic upgrade head
ref4ep-admin seed --from antrag
pytest
```

---

## 12. Definition of Done

Sprint 1 ist abgeschlossen, wenn alle folgenden Punkte erfüllt sind.

### Migration

- [ ] Revision `0002_identity_and_project` existiert mit
  `down_revision = "0001_baseline"`.
- [ ] `alembic upgrade head` legt die vier Tabellen an, beide
  Dialekte (SQLite lokal verifiziert, PostgreSQL in CI).
- [ ] `alembic downgrade base` entfernt sie restlos.

### Datenmodell

- [ ] SQLAlchemy-Modelle für `Partner`, `Person`, `Workpackage`,
  `Membership` in `ref4ep/domain/` mit den Feldern aus §2.
- [ ] CHECK-Constraints für `platform_role` und `wp_role`.
- [ ] UNIQUE-Constraints für `partner.short_name`, `partner.name`,
  `person.email`, `workpackage.code`,
  `(membership.person_id, membership.workpackage_id)`.

### Initial-Seed

- [ ] Datei `cli/seed_data/antrag_initial.yaml` ist eingecheckt
  und enthält die Daten aus §13 der MVP-Spec wörtlich.
- [ ] `ref4ep-admin seed --from antrag` legt 5 Partner und 35
  Workpackage-Einträge (8 Hauptarbeitspakete + 27
  Unterarbeitspakete) an. Zweiter Lauf legt 0 neu an, exitet
  mit 0.
- [ ] Lead-Vererbung greift für alle Sub-WPs.

### Auth

- [ ] `Settings.session_secret` ist Pflichtfeld mit
  Mindestlänge-Validierung.
- [ ] Argon2id über `argon2-cffi`; Mindest-Passwortlänge 10 Zeichen.
- [ ] Session-Cookie `ref4ep_session` (HttpOnly, signiert,
  7 Tage Lebensdauer).
- [ ] CSRF-Cookie `ref4ep_csrf` + Header `X-CSRF-Token` über
  Double-Submit; `require_csrf`-Dependency in allen schreibenden
  Routen.
- [ ] `POST /api/auth/login` liefert generische 401 bei jedem
  Fehlerfall (kein E-Mail-Existenz-Lecks).
- [ ] `must_change_password`-Flag wird vom Login transportiert und
  vom Frontend ausgewertet.

### CLI

- [ ] Subcommands `seed`, `partner {list,create}`,
  `workpackage {list,create}`,
  `person {list,create,reset-password,set-role,enable,disable}`,
  `membership {add,remove}` sind implementiert.
- [ ] Passwörter werden ausschließlich über `getpass`-Prompt
  abgefragt.

### API

- [ ] Endpunkte aus §5 implementiert und dokumentiert (FastAPI
  generiert OpenAPI unter `/docs`).
- [ ] Generische Fehlerformate `{"error": {...}}`.
- [ ] CSRF-Pflicht für alle nicht-GETs (außer `POST /api/auth/login`).

### Web

- [ ] `GET /partners` öffentlich erreichbar, listet die fünf Seed-
  Partner.
- [ ] `GET /login` rendert eine HTML-Form, `POST /login` führt
  Login durch.
- [ ] SPA unter `/portal/` lädt ohne Login → Redirect auf
  `/login`; nach Login lädt sie das Cockpit.
- [ ] Catch-All-Handler liefert `index.html` für tiefe SPA-Pfade.

### Tests und Qualität

- [ ] Alle Tests aus §10 vorhanden und grün.
- [ ] Coverage über `ref4ep/services`, `ref4ep/cli`, `ref4ep/api`
  liegt bei mindestens 80 %.
- [ ] `ruff check` und `ruff format --check` grün.
- [ ] CI läuft sowohl gegen SQLite als auch PostgreSQL grün.

### Was Sprint 1 explizit **nicht** prüft

- Kein Dokumentenregister, kein Storage, kein Audit-Log.
- Keine schreibenden Stammdaten-API-Routen über die CLI hinaus.
- Keine WP-Rollen-Berechtigungsprüfung in Routen (nur als Helper
  vorhanden und getestet).
- Keine Status-/Visibility-Workflows.
- Keine SSO-Integration.

Diese Punkte sind Sprint 2 und folgenden zugeordnet.
