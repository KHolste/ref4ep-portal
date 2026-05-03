# Sprint 3 – Umsetzungsplan: Audit-Log, Status-Workflow, Sichtbarkeit, Freigabe

Dieser Plan konkretisiert den vierten Sprint aus
`docs/mvp_specification.md` §12. Er baut auf
`docs/sprint2_implementation_plan.md` (internes Dokumentenregister
mit Versionierung und Storage-Interface) auf.

Verbindliche Festlegungen aus der MVP-Spezifikation, die hier gelten:

- FastAPI + statisch ausgeliefertes HTML/CSS + Vanilla-JS — **kein**
  Frontend-Framework, **kein** Node/npm.
- SQLite als lokaler Default, konfigurierbar über
  `REF4EP_DATABASE_URL`.
- Alembic für jede Schema-Änderung.
- Dokumentversionen sind und bleiben **append-only** — Sprint 3 löst
  nur die TODO-Audit-Marker aus Sprint 1/2 ein und ergänzt
  Status-/Sichtbarkeits-/Freigabe-Workflows.
- Existenz-Leakage-Schutz aus Sprint 2 (404 statt 403 für
  nicht-sichtbare Datensätze) bleibt unverändert.

---

## 1. Ziel von Sprint 3

Sprint 3 macht das interne Dokumentenregister **freigabefähig** und
**auditierbar**. Am Ende muss gelten:

- Eine neue Alembic-Revision `0004_audit_and_release` legt die
  Tabelle `audit_log` an und ergänzt das Feld
  `document.released_version_id` (siehe §3 und §7).
- Jede schreibende Aktion in Services und CLI erzeugt einen
  `audit_log`-Eintrag mit Akteur, Zeitstempel, Aktion, betroffener
  Entity, Vorher-/Nachher-Auszug der relevanten Felder und —
  soweit verfügbar — Client-IP und Request-ID.
- Ein WP-Mitglied kann ein Dokument von `draft` nach `in_review`
  und zurück schalten.
- Ein WP-Lead bzw. ein Admin kann ein `in_review`-Dokument
  **freigeben**, indem er **explizit** eine konkrete Version
  auswählt. Der Server setzt `status = released` und
  `released_version_id`. Ein normaler Upload veröffentlicht
  **nichts** automatisch.
- Ein WP-Lead bzw. ein Admin kann die Sichtbarkeit zwischen
  `workpackage`, `internal` und `public` umschalten. Die
  Plausibilitätsregel „öffentlich erst nach Release" wird im
  Service-Layer dokumentiert und greift in Sprint 4.
- Ein Admin kann ein Dokument **soft-löschen** über
  `DELETE /api/documents/{id}` (setzt `is_deleted = true`;
  Tabellenzeile bleibt physisch erhalten, Versionen samt
  Storage-Dateien werden **nicht** angefasst). Hard-Delete ist
  und bleibt in Sprint 3 ausgeschlossen.
- Ein Admin sieht das vollständige Audit-Log unter
  `/admin/audit` und über `GET /api/admin/audit`.
- `pytest` läuft grün; `ruff check` ist sauber.

**Demo-Szenario** (manuelle Abnahme):

1. WP-Mitglied legt das Dokument „Konstruktionszeichnung Ref-HT" an
   und lädt v1 hoch (Sprint-2-Fluss).
2. WP-Mitglied schaltet auf `in_review`.
3. WP-Lead wählt v1 aus und gibt sie frei (Status `released`,
   `released_version_id` zeigt auf v1).
4. WP-Mitglied lädt v2 hoch — Status bleibt `released`,
   `released_version_id` zeigt **weiterhin** auf v1.
5. WP-Lead gibt v2 explizit frei — `released_version_id` zeigt
   jetzt auf v2.
6. Admin öffnet `/admin/audit` und sieht alle vier Aktionen
   (`document.create`, `document.set_status`, `document.release`,
   `document.release` erneut) inkl. Vorher-/Nachher-Werten.

---

## 2. Nicht-Ziele von Sprint 3

Bewusst **nicht** in Sprint 3:

- Öffentliche Download-Bibliothek (`/downloads`,
  `/api/public/documents/*`, `/api/public/documents/{slug}/download`)
  — **Sprint 4**. Sprint 3 schafft nur die Voraussetzung
  (`visibility = public ∧ status = released ∧
  released_version_id IS NOT NULL`).
- Review-Kommentar-Workflow (Kommentare auf Versionen,
  Reviewer-Zuweisung, Genehmigungs-Pipeline mit mehreren Reviewern)
  — explizit kein Sprint-3-Inhalt.
- Messkampagnen- und Testplanung — post-MVP.
- Wiki-Modul — post-MVP.
- Status-Übergänge mit Reviewer-Genehmigung — Sprint 3 nutzt das
  einfache Modell „WP-Lead allein gibt frei".
- DOI-/Zenodo-Anbindung — post-MVP.
- S3- oder MinIO-Implementierung des Storage-Interfaces — Storage
  bleibt `LocalFileStorage`.
- Audit-Log-Rotation oder -Retention. Sprint 3 setzt **unbegrenzte
  Aufbewahrung** (offene Entscheidung 14 vorerst so beantwortet).
  Eine Rotation kann später ohne Schema-Bruch ergänzt werden.
- E-Mail-Benachrichtigung bei Statuswechsel — post-MVP.
- Versionsbezogene Berechtigungen (Sprint 3 kennt nur Berechtigungen
  am Dokument).
- Audit-Sicht für Nicht-Admins (pro-Dokument-Historie für
  WP-Mitglieder) — bewusst spätere Iteration; siehe MVP-Spec §7.

---

## 3. Datenbankänderungen und Alembic-Migration

Eine einzige zusammengelegte Revision für Sprint 3:

- Datei:
  `backend/alembic/versions/<datum>_0004_audit_and_release.py`
- `down_revision = "0003_documents"`
- `revision = "0004_audit_and_release"`

`upgrade()`:

1. Legt die Tabelle `audit_log` an (siehe §4).
2. Fügt der Tabelle `document` die Spalte
   `released_version_id` (CHAR(36), NULL) **mit echtem
   Foreign-Key-Constraint** auf `document_version.id` hinzu
   (siehe §7).

`downgrade()`:

- Entfernt FK-Constraint und Spalte `released_version_id` aus
  `document`.
- Droppt die Tabelle `audit_log`.

Dialektneutralität wie in den vorherigen Migrationen
(`render_as_batch` für SQLite via `alembic/env.py`).

### Migrationsskizze

Beide Backends (SQLite + PostgreSQL) verkraften den zyklischen FK
ohne `INITIALLY DEFERRED`, weil die einzige Datenoperation in
Sprint 3 ein `ADD COLUMN` mit Default `NULL` ist und keine
Bestandsdaten gefüllt werden müssen. Für SQLite läuft `ADD COLUMN
+ FK` zuverlässig über Alembics Batch-Modus:

```python
# upgrade()
with op.batch_alter_table("document") as batch_op:
    batch_op.add_column(
        sa.Column(
            "released_version_id",
            sa.String(length=36),
            sa.ForeignKey(
                "document_version.id",
                name="fk_document_released_version",
                use_alter=True,
            ),
            nullable=True,
        )
    )

# downgrade()
with op.batch_alter_table("document") as batch_op:
    batch_op.drop_constraint("fk_document_released_version", type_="foreignkey")
    batch_op.drop_column("released_version_id")
```

`use_alter=True` weist SQLAlchemy an, den FK über ein separates
ALTER TABLE anzulegen — wichtig sowohl für die Migration (sauber
benannter Constraint, gezielt droppen können) als auch für die
spätere Modell-Definition in `domain/models.py` (siehe §7),
damit `Base.metadata.create_all()` (z. B. in Tests, falls je
benötigt) die Tabellen ohne Zyklus-Konflikt erzeugt.

### Tabelle `audit_log`

| Feld             | Typ          | Constraints                                                          |
| ---------------- | ------------ | -------------------------------------------------------------------- |
| id               | CHAR(36)     | PK                                                                   |
| actor_person_id  | CHAR(36)     | NULL, FK → `person.id` (NULL = System / CLI)                         |
| actor_label      | TEXT         | NULL — z. B. `cli-admin`, `system`, falls keine Person hinterlegt    |
| action           | TEXT         | NOT NULL — z. B. `document.release`                                  |
| entity_type      | TEXT         | NOT NULL — z. B. `document`                                          |
| entity_id        | CHAR(36)     | NOT NULL                                                             |
| details          | TEXT         | NULL — JSON-serialisierter Vorher-/Nachher-Auszug (Service-validiert) |
| client_ip        | TEXT         | NULL                                                                 |
| request_id       | TEXT         | NULL                                                                 |
| created_at       | TIMESTAMP    | NOT NULL                                                             |

Indexe:

- `INDEX (entity_type, entity_id, created_at DESC)` —
  Pro-Entity-Historie (späterer UI-Zugriff).
- `INDEX (created_at DESC)` — Admin-Listenansicht.
- `INDEX (action)` — Filtern nach Aktionstyp.

`details` wird bewusst als TEXT (JSON-String) gespeichert, **nicht**
als nativer JSON-Typ — bleibt dialektneutral. Service serialisiert
mit `json.dumps(..., ensure_ascii=False, sort_keys=True)`.

### Spalte `document.released_version_id`

| Feld                | Typ          | Constraints                                                                  |
| ------------------- | ------------ | ---------------------------------------------------------------------------- |
| released_version_id | CHAR(36)     | NULL, **FK → `document_version.id`** (`name="fk_document_released_version"`) |

Default `NULL`. Der DB-FK garantiert die referenzielle Integrität;
zusätzlich erzwingt der Service-Layer die Statusinvariante
`status = 'released'` ⇔ `released_version_id IS NOT NULL`
(siehe §7).

### Migrations-Datenbestand

Bestehende Sprint-2-Dokumente sind in der Praxis alle `draft` und
haben kein release; die Migration muss nichts an Bestandsdaten
ändern.

---

## 4. Audit-Log-Tabelle und Audit-Ereignisse

### 4.1 Service `AuditLogger`

Ablage: `ref4ep/services/audit_logger.py`. Konstruktor-Signatur:

```python
class AuditLogger:
    def __init__(
        self,
        session: Session,
        *,
        actor_person_id: str | None = None,
        actor_label: str | None = None,
        client_ip: str | None = None,
        request_id: str | None = None,
    ) -> None: ...

    def log(
        self,
        action: str,
        *,
        entity_type: str,
        entity_id: str,
        before: dict | None = None,
        after: dict | None = None,
    ) -> AuditLog: ...
```

- `log()` baut ein `audit_log`-Objekt, schreibt es per
  `session.add(...)` + `session.flush()` und gibt es zurück.
- `details` wird aus `{"before": before, "after": after}`
  zusammengesetzt; Werte mit nicht-serialisierbaren Typen
  (datetime etc.) werden via `json.dumps(..., default=str)`
  konvertiert.
- Bei fehlendem Akteur (`actor_person_id is None and actor_label
  is None`) wird `actor_label = "system"` gesetzt.

### 4.2 Hook-Punkte (Einlösung der Sprint-1/2-TODOs)

| Service                      | Methode                          | Action-Code                       |
| ---------------------------- | -------------------------------- | --------------------------------- |
| `PartnerService`             | `create`                         | `partner.create`                  |
| `PartnerService`             | `update`                         | `partner.update`                  |
| `PartnerService`             | `soft_delete`                    | `partner.delete`                  |
| `PersonService`              | `create`                         | `person.create`                   |
| `PersonService`              | `reset_password`                 | `person.reset_password`           |
| `PersonService`              | `set_role`                       | `person.set_role`                 |
| `PersonService`              | `enable` / `disable`             | `person.enable` / `person.disable`|
| `PersonService`              | `change_password`                | `person.change_password`          |
| `WorkpackageService`         | `create`                         | `workpackage.create`              |
| `WorkpackageService`         | `add_membership`                 | `membership.add`                  |
| `WorkpackageService`         | `remove_membership`              | `membership.remove`               |
| `DocumentService`            | `create`                         | `document.create`                 |
| `DocumentService`            | `update_metadata`                | `document.update`                 |
| `DocumentService`            | `soft_delete` (Sprint 3 neu)     | `document.delete`                 |
| `DocumentVersionService`     | `upload_new_version`             | `document_version.upload`         |
| `DocumentLifecycleService`   | `set_status` (Sprint 3 neu)      | `document.set_status`             |
| `DocumentLifecycleService`   | `release` (Sprint 3 neu)         | `document.release`                |
| `DocumentLifecycleService`   | `unrelease` (Sprint 3 neu)       | `document.unrelease`              |
| `DocumentLifecycleService`   | `set_visibility` (Sprint 3 neu)  | `document.set_visibility`         |

Die TODO-Marker aus Sprint 1 und Sprint 2 werden in dieser
Iteration durch echte `audit.log(...)`-Aufrufe ersetzt.

### 4.3 `before`/`after`-Inhalte (Beispiele)

- `document.create` →
  `before=None`,
  `after={"workpackage_id": …, "title": …, "slug": …,
  "document_type": …, "status": "draft",
  "visibility": "workpackage"}`.
- `document.update` →
  `before={"title": "Alt", "deliverable_code": null}`,
  `after={"title": "Neu", "deliverable_code": "D3.1"}`.
- `document.set_status` →
  `before={"status": "draft"}`,
  `after={"status": "in_review"}`.
- `document.release` →
  `before={"status": "in_review", "released_version_id": null}`,
  `after={"status": "released",
  "released_version_id": "<uuid>",
  "released_version_number": 2}`.
- `document.set_visibility` →
  `before={"visibility": "workpackage"}`,
  `after={"visibility": "public"}`.
- `document_version.upload` →
  `before=None`,
  `after={"version_number": 2,
  "sha256": "…", "file_size_bytes": …,
  "mime_type": …, "original_filename": …}`.

### 4.4 Akteur und Request-Kontext

- API-Pfad: Routen bauen den `AuditLogger` mit
  `actor_person_id = current_person.id`,
  `client_ip = request.client.host`,
  `request_id = request.headers.get("X-Request-ID")`
  (oder eine pro Request generierte UUID, falls Header fehlt).
- CLI-Pfad: `actor_label = "cli-admin"`, `actor_person_id = None`.
- Tests / interne Aufrufe ohne Audit-Bedarf: kein `AuditLogger`
  gesetzt; Service nutzt einen No-op-Logger
  (`AuditLogger`-Variante, die `log()` einfach verwirft, wird **nicht**
  als Klassen-Bypass implementiert — stattdessen ist der
  Audit-Parameter optional, und die Methoden machen den Aufruf
  defensiv `if self.audit is not None: self.audit.log(...)`).

### 4.5 Nicht im Audit erfasst

- Lese-Operationen (GET-Endpunkte).
- Anonyme Public-Downloads (Sprint 4) — DSGVO-freundlich, kein
  Mehrwert.
- Health-Endpoint (`/api/health`).

---

## 5. Dokumentenstatus und erlaubte Statusübergänge

Statusmenge (unverändert aus MVP §4): `draft`, `in_review`,
`released`.

### 5.1 Erlaubte Übergänge

| Von         | Nach        | Akteur                          | Notwendig                                     |
| ----------- | ----------- | ------------------------------- | --------------------------------------------- |
| `draft`     | `in_review` | WP-Mitglied oder Admin          | mind. eine Version existiert                  |
| `in_review` | `draft`     | WP-Mitglied oder Admin          | —                                             |
| `in_review` | `released`  | WP-Lead oder Admin              | über `release`-Endpunkt mit `version_id`      |
| `released`  | `draft`     | nur Admin (`unrelease`)         | setzt `released_version_id` zurück auf NULL   |

### 5.2 Verbotene Übergänge

| Von         | Nach        | Begründung                                              |
| ----------- | ----------- | ------------------------------------------------------- |
| `draft`     | `released`  | Sprint 3 verlangt Zwischenschritt `in_review`           |
| `released`  | `in_review` | Versehentliche Freigabe wird über Admin-`unrelease` zurückgesetzt; ein direkter Übergang würde den Audit-Pfad verwischen |
| beliebig    | `released`  | nur über expliziten `release`-Endpunkt mit Versionswahl |

Verstöße werden als `409 Conflict` mit
`{"error":{"code":"invalid_status_transition","message":"…"}}` an
den Client zurückgemeldet.

### 5.3 Constraints

- `status = 'released'` ⇔ `released_version_id IS NOT NULL`.
- Service-Layer prüft dies vor jedem `commit`. DB-Schema erzwingt
  es nicht (kein `CHECK` mit Bezug auf zwei Spalten — bleibt
  dialektneutral).

### 5.4 Statussetzung erfolgt nur über dedizierte Endpunkte

`status` wird **nicht** über
`PATCH /api/documents/{id}` geändert; der bestehende Sprint-2-Patch
ignoriert das Feld weiterhin. Zustandsänderungen laufen
ausschließlich über `set_status`/`release`/`unrelease`.

---

## 6. Sichtbarkeitswerte und erlaubte Sichtbarkeitsänderungen

Sichtbarkeitsmenge (unverändert aus MVP §4): `workpackage`,
`internal`, `public`.

### 6.1 Erlaubte Übergänge

| Von             | Nach            | Akteur                              |
| --------------- | --------------- | ----------------------------------- |
| `workpackage`   | `internal`      | WP-Mitglied oder Admin              |
| `internal`      | `workpackage`   | WP-Mitglied oder Admin              |
| beliebig        | `public`        | **nur WP-Lead oder Admin**          |
| `public`        | `workpackage`   | WP-Lead oder Admin                  |
| `public`        | `internal`      | WP-Lead oder Admin                  |

Begründung „WP-Lead-only für public" (offene Entscheidung 5 aus
MVP-Spec §11): öffentliche Sichtbarkeit hat externe Außenwirkung,
darf nicht von einem einzelnen WP-Mitglied alleine gesetzt werden.

### 6.2 Plausibilitätsregel „public erst nach Release"

- `visibility` darf **technisch** zu jedem Status gesetzt werden
  (auch `draft` oder `in_review`).
- **Wirksam öffentlich** wird ein Dokument **erst, wenn**
  `status = 'released'` UND `visibility = 'public'` UND
  `released_version_id IS NOT NULL` (siehe §7 und Sprint 4).
- Sprint 4 baut die öffentliche Bibliothek mit genau diesem
  Filter; Sprint 3 stellt sicher, dass die Daten konsistent
  vorliegen.
- UI in Sprint 3 zeigt im Detail eines `public`/non-`released`-
  Dokuments einen Hinweis-Banner: „Diese Sichtbarkeit ist
  öffentlich, das Dokument ist aber noch nicht freigegeben — es
  erscheint erst ab dem Release in der öffentlichen Bibliothek."

### 6.3 Sichtbarkeitssetzung erfolgt nur über dedizierten Endpunkt

`visibility` wird **nicht** über
`PATCH /api/documents/{id}` geändert; der Sprint-2-Patch ignoriert
das Feld weiterhin. Änderungen laufen ausschließlich über
`POST /api/documents/{id}/visibility`.

---

## 7. `released_version_id` für die freigegebene Version

Sprint 3 fügt das Feld `document.released_version_id` ein —
bewusst erst jetzt, weil Sprint 2 noch keinen Release-Workflow
hatte und das Feld nur Ballast gewesen wäre.

### 7.1 Feldcharakteristik

- Spalte: `document.released_version_id`, `CHAR(36)`, **nullable**.
- **Echter Foreign-Key-Constraint** auf
  `document_version.id`, benannt
  `fk_document_released_version`. Datenbankseitige
  referenzielle Integrität ist primärer Schutz; ungültige UUIDs
  werden bereits von der DB abgewiesen.
- Im SQLAlchemy-Modell mit `use_alter=True`, damit der zyklische
  FK (`document` ↔ `document_version`) bei
  `Base.metadata.create_all()` über ein separates ALTER TABLE
  aufgelöst wird:

  ```python
  class Document(Base):
      ...
      released_version_id: Mapped[str | None] = mapped_column(
          String(36),
          ForeignKey(
              "document_version.id",
              name="fk_document_released_version",
              use_alter=True,
          ),
          nullable=True,
      )
  ```

- In der Alembic-Migration wird der FK direkt mit der
  `add_column`-Operation im Batch-Modus angelegt (siehe §3
  „Migrationsskizze") — `batch_alter_table` macht das in SQLite
  über die übliche „neue Tabelle + copy + rename"-Sequenz, in
  PostgreSQL läuft es als reguläres `ALTER TABLE ... ADD COLUMN
  ... REFERENCES ...`. Beide Backends benötigen kein
  `INITIALLY DEFERRED`, weil beim Migrationszeitpunkt alle
  Datenwerte `NULL` sind und keine Bestandsdaten gefüllt werden.

### 7.2 DB- und Service-Invarianten

**DB-Schicht (Sprint 3 neu):**

- FK-Constraint stellt sicher, dass `released_version_id`
  ausschließlich auf existierende `document_version`-Zeilen
  zeigen kann.
- Inserts mit nicht-existenter UUID schlagen mit
  `IntegrityError` fehl (in beiden Dialekten).

**Service-Schicht (zusätzlich, weil DB die Semantik nicht kennt):**

1. `released_version_id IS NULL` solange `status ∈ {draft,
   in_review}`.
2. `released_version_id IS NOT NULL` ⇔ `status = 'released'`.
3. Die referenzierte Version **gehört zum richtigen Dokument**
   (`v.document_id == document.id`) — diese semantische Bindung
   prüft der Service vor jedem `release()`, weil der DB-FK das
   nicht ausdrücken kann.
4. Soft-Delete eines Dokuments setzt `released_version_id`
   **nicht** zurück; die Sicht-Logik in Sprint 4 filtert ohnehin
   auf `is_deleted = false`.

### 7.3 Hard-Delete-Tabu

Sprint 3 führt bewusst **kein Hard-Delete** ein (siehe §9.1).
Damit kann der zyklische FK
(`document` ↔ `document_version`) im laufenden Betrieb gar nicht
in eine Reihenfolge-Klemme geraten — beide Tabellen verlieren
nie eine Zeile, sondern werden allenfalls über `is_deleted`
ausgeblendet. Die Migration legt den FK ohne
`ON DELETE`-Klausel an; ein Hard-Delete in einem späteren Sprint
müsste den FK explizit mit `ON DELETE SET NULL` auf
`document.released_version_id` ergänzen oder die Reihenfolge
manuell aushandeln.

### 7.4 Wechsel der freigegebenen Version

- Erfolgt durch erneuten Aufruf von `POST /api/documents/{id}/release`
  mit einer anderen `version_number` / `version_id`.
- Vorher gespeicherte Versionen bleiben **unverändert** verfügbar
  (append-only).
- Audit-Eintrag enthält
  `before={"released_version_id": "<alt>"}`,
  `after={"released_version_id": "<neu>",
  "released_version_number": <n>}`.

### 7.5 Kein automatisches Veröffentlichen beim Upload

Verbindlich aus Sprint 2 + Sprint 3:

- `POST /api/documents/{id}/versions` ändert **niemals**
  `status`, `visibility` oder `released_version_id`.
- Wenn das Dokument bereits `released` war und eine neue Version
  hochgeladen wird, bleibt `released_version_id` auf der **alten**
  Version stehen, bis der WP-Lead bewusst eine neue freigibt.

---

## 8. Services

### 8.1 Bestehende Services — Audit-Hook

`PartnerService`, `PersonService`, `WorkpackageService`,
`DocumentService`, `DocumentVersionService` erhalten einen optionalen
Konstruktor-Parameter `audit: AuditLogger | None = None` und ersetzen
ihre bisherigen `# TODO Sprint 3: …`-Kommentare durch echte
`if self.audit: self.audit.log(...)`-Aufrufe.

### 8.2 `DocumentService` — neue Methode `soft_delete`

```python
def soft_delete(self, document_id: str) -> None:
    # nur admin
    # setzt is_deleted = True, updated_at = now
    # Audit: document.delete
```

Permission-Helper `can_admin_delete_document(auth)` —
plattformweit Admin-only (`auth.platform_role == "admin"`).

### 8.3 Neuer `DocumentLifecycleService`

Ablage: `ref4ep/services/document_lifecycle_service.py`.
Gebündelt, weil Status, Sichtbarkeit und Release stark
zusammenhängen und gemeinsam mit Audit aufgerufen werden.

```python
class DocumentLifecycleService:
    def __init__(
        self,
        session: Session,
        *,
        auth: AuthContext | None = None,
        audit: AuditLogger | None = None,
    ) -> None: ...

    def set_status(self, document_id: str, *, to: Literal["draft", "in_review"]) -> Document:
        ...

    def release(self, document_id: str, *, version_number: int) -> Document:
        ...

    def unrelease(self, document_id: str) -> Document:
        ...

    def set_visibility(self, document_id: str, *, to: Literal["workpackage", "internal", "public"]) -> Document:
        ...
```

Methoden im Detail:

- `set_status`:
  - Erlaubt `draft → in_review` und `in_review → draft`.
  - Verlangt für `draft → in_review`, dass mindestens eine
    Version existiert; sonst `ValueError(invalid_status_transition)`.
  - Akteur: WP-Mitglied oder Admin.
- `release`:
  - Erlaubt `in_review → released` (oder `released → released`
    mit Wechsel der Version).
  - Verlangt WP-Lead oder Admin.
  - Lädt die Version per `(document_id, version_number)` und
    setzt `released_version_id = version.id`,
    `status = "released"`.
- `unrelease`:
  - Erlaubt `released → draft`.
  - Verlangt **Admin** (Plattformrolle).
  - Setzt `released_version_id = NULL`, `status = "draft"`.
  - Audit-Pflicht.
- `set_visibility`:
  - Verlangt Akteur entsprechend §6.1.
  - Schreibt nur die Spalte; warnt **nicht** wenn
    `to == "public"` und `status != "released"` — die Information
    wird über die UI sichtbar gemacht (siehe §6.2).

### 8.4 Permissions-Erweiterung

`ref4ep/services/permissions.py` bekommt:

- `can_set_status(auth, document) -> bool` —
  WP-Mitglied oder Admin.
- `can_release(auth, document) -> bool` —
  WP-Lead oder Admin.
- `can_unrelease(auth) -> bool` —
  Admin only.
- `can_set_visibility(auth, document, to) -> bool` —
  WP-Mitglied oder Admin für `workpackage`/`internal`,
  WP-Lead oder Admin für `public`.
- `can_view_audit_log(auth) -> bool` — Admin only.

### 8.5 No-op-Audit für Tests / CLI

Ein `NullAuditLogger` ist **nicht** vorgesehen; Services prüfen
defensiv auf `self.audit is None`. Tests, die Audit-Wirkung prüfen
wollen, instanziieren einen echten `AuditLogger` mit der
Test-Session.

CLI-Befehle (Sprint 1) erhalten einen `AuditLogger` mit
`actor_label="cli-admin"`. Damit werden Stammdaten-Operationen,
die in Sprint 1 ohne Audit liefen, nun ebenfalls geloggt.

---

## 9. API-Endpunkte

Alle unter Präfix `/api`, JSON-Antworten. CSRF-Header
(`X-CSRF-Token`) Pflicht für alle nicht-GETs.

### 9.1 Dokument-Lebenszyklus (neu in Sprint 3)

| Methode | Pfad                                          | Zweck                                              | Rolle                              |
| ------- | --------------------------------------------- | -------------------------------------------------- | ---------------------------------- |
| POST    | `/api/documents/{id}/status`                  | `draft ↔ in_review`                                | WP-Mitglied oder Admin             |
| POST    | `/api/documents/{id}/release`                 | Setzt `status=released` + `released_version_id`   | WP-Lead oder Admin                 |
| POST    | `/api/documents/{id}/unrelease`               | `released → draft`                                 | nur Admin                          |
| POST    | `/api/documents/{id}/visibility`              | Sichtbarkeit setzen                                | siehe §6.1                         |
| DELETE  | `/api/documents/{id}`                         | **Soft-Delete** (setzt `is_deleted=true`; Versionen + Dateien bleiben) | nur Admin |

Request-Bodies:

- `POST /status`: `{"to": "draft"}` oder `{"to": "in_review"}`.
- `POST /release`: `{"version_number": <int>}`.
- `POST /unrelease`: leerer Body oder `{}`.
- `POST /visibility`: `{"to": "workpackage" | "internal" | "public"}`.

Antworten: bei Erfolg HTTP 200 mit dem aktualisierten
`DocumentDetailOut` (das bereits aus Sprint 2 existiert,
wird aber um `released_version_id` und ggf. `released_version`
ergänzt — siehe §9.4).

Fehlerantworten:

- 400 für unzulässige Felder/Werte.
- 403 für Berechtigungs- oder CSRF-Verstöße.
- 404 für „nicht sichtbar oder nicht vorhanden" (Existenz-Leakage-
  Schutz wie in Sprint 2).
- 409 (`invalid_status_transition`) für nicht erlaubte Übergänge.
- 422 für Pydantic-Validierungsfehler.

### 9.2 Audit-Log (neu in Sprint 3)

| Methode | Pfad                | Zweck                                               | Rolle  |
| ------- | ------------------- | --------------------------------------------------- | ------ |
| GET     | `/api/admin/audit`  | Audit-Log mit Filtern                               | admin  |

Query-Parameter (alle optional, kombinierbar):

- `actor_email` — nur Einträge dieser Person.
- `entity_type` — z. B. `document`, `partner`, `person`.
- `entity_id` — UUID.
- `action` — exakter Action-Code, z. B. `document.release`.
- `since`, `until` — ISO-Zeitstempel.
- `limit` (Default 100, Max 500), `offset`.

Antwortschema `AuditLogOut`:

```json
{
  "id": "...",
  "created_at": "...",
  "actor": { "email": "...", "display_name": "...", "label": null },
  "action": "document.release",
  "entity_type": "document",
  "entity_id": "...",
  "details": { "before": {...}, "after": {...} },
  "client_ip": "127.0.0.1",
  "request_id": "..."
}
```

### 9.3 Bestehende Endpunkte — Erweiterungen

- `POST /api/workpackages/{code}/documents` und
  `POST /api/documents/{id}/versions` schreiben nun einen
  Audit-Eintrag.
- `PATCH /api/documents/{id}` schreibt einen Audit-Eintrag,
  ignoriert aber weiterhin `status` und `visibility` (Änderung nur
  über die dedizierten Endpunkte oben).
- `GET /api/documents/{id}` liefert zusätzlich
  `released_version_id` und — falls gesetzt — die kompakte
  Repräsentation der freigegebenen Version
  (`released_version`).

### 9.4 Schema-Änderungen am Out-Modell

`DocumentOut` und `DocumentDetailOut` (aus Sprint 2) erhalten:

- `released_version_id: str | None`
- `released_version: DocumentVersionOut | None`
  (nur in `DocumentDetailOut`)

### 9.5 Bewusst nicht in Sprint 3

| Methode | Pfad                                              | Sprint                  |
| ------- | ------------------------------------------------- | ----------------------- |
| GET     | `/api/public/documents`                           | Sprint 4                |
| GET     | `/api/public/documents/{slug}`                    | Sprint 4                |
| GET     | `/api/public/documents/{slug}/download`           | Sprint 4                |
| POST    | `/api/documents/{id}/versions/.../comment` o. ä. | post-MVP                |

**Kein Hard-Delete-Endpunkt.** `DELETE /api/documents/{id}` ist
ausdrücklich Soft-Delete (siehe §9.1). Ein endgültiges Löschen
von `document`- oder `document_version`-Zeilen oder ein Entfernen
der zugehörigen Storage-Dateien wird in Sprint 3 nicht
eingeführt.

---

## 10. Web-Ansichten

Sprint 3 erweitert die SPA aus Sprint 2 und ergänzt eine neue
Admin-Ansicht. Public-Templates bleiben unverändert.

### 10.1 `/portal/documents/{id}` (Erweiterung)

- Statusbadge (`draft` grau, `in_review` gelb, `released` grün) im
  Kopfbereich.
- Sichtbarkeitsbadge (`workpackage` / `internal` / `public`).
- Aktion **„Zur Review schicken"** (sichtbar für WP-Mitglied im
  Status `draft`, mind. eine Version vorhanden).
- Aktion **„Zurück zu Draft"** (sichtbar für WP-Mitglied im
  Status `in_review`).
- Aktion **„Freigeben …"** (sichtbar für WP-Lead/Admin im Status
  `in_review`): öffnet einen Dialog, der eine Version auswählt
  (Default: höchste Versionsnummer).
- Aktion **„Andere Version freigeben …"** (sichtbar für WP-Lead/
  Admin im Status `released`): erlaubt Wechsel der freigegebenen
  Version.
- Aktion **„Freigabe zurückziehen"** (sichtbar nur für Admin im
  Status `released`).
- Aktion **„Sichtbarkeit ändern …"** (Dropdown
  `workpackage` / `internal` / `public`; WP-Lead-Pflicht für
  `public`).
- Aktion **„Soft-Delete"** (sichtbar nur für Admin) mit
  Bestätigungsdialog. Der Dialog macht explizit, dass das
  Dokument lediglich ausgeblendet wird; Versionen und Dateien
  bleiben physisch erhalten.
- Hinweis-Banner bei `visibility = public` und
  `status != released`: „Öffentlich erst sichtbar nach Release."
- In der Versionsliste wird die freigegebene Version markiert
  (z. B. „Freigegeben am …, durch …").

### 10.2 `/portal/workpackages/{code}` (kleine Erweiterung)

Dokumententabelle bekommt zwei zusätzliche Spalten:

- `Status` (Badge wie oben).
- `Sichtbarkeit` (Badge).

Soft-deleted Dokumente bleiben in der Liste ausgeblendet
(Sprint-2-Verhalten unverändert).

### 10.3 `/admin/audit` (neu)

Neue Admin-SPA-Route:

- Tabelle mit Spalten `Zeit`, `Akteur`, `Aktion`, `Entity`,
  `Vorher → Nachher` (Kurzanzeige), `Details` (Klick öffnet die
  vollständige JSON-Detail-Ansicht).
- Filter im Kopfbereich: Akteur (E-Mail), Entity-Typ, Aktion,
  Zeitbereich.
- Pagination mit `limit`/`offset`.
- Nur sichtbar für Plattformrolle `admin`; nicht-Admins werden
  serverseitig auf 403 gemappt und SPA-seitig auf `/portal/`
  umgeleitet.

### 10.4 Neue/erweiterte JS-Module

Unter `backend/src/ref4ep/web/modules/`:

- `document_detail.js` (Erweiterung): Status-/Sichtbarkeitsaktionen,
  Release-Dialog, Freigabe-Markierung in Versionsliste.
- `audit.js` (neu): Admin-Audit-Tabelle.
- `app.js` bekommt Routen-Pattern für `/admin/audit` und
  Auth-Gating (Admin-Check beim Modul-Load).

### 10.5 Public-Templates

Bleiben **unverändert**. Die öffentliche Sichtbarkeit
freigegebener Dokumente kommt erst in Sprint 4 inhaltlich an.

---

## 11. Rechte- und Sichtbarkeitsregeln (in Sprint 3 wirksam)

Sprint 3 aktiviert die volle MVP-§7-Logik in den Routen.

### 11.1 Lesezugriff auf ein Dokument

Eine Person darf ein Dokument **lesen**, wenn:

1. `visibility = 'public'` UND `status = 'released'` UND
   `released_version_id IS NOT NULL` UND `is_deleted = false`
   — auch anonym lesbar (Sprint 4 baut die UI dazu, aber die
   Berechtigungslogik gilt bereits jetzt im Service).
2. Person ist `admin`.
3. Person ist Mitglied im zugehörigen Workpackage und
   `visibility ∈ {workpackage, internal}`.
4. Person ist eingeloggt und `visibility = 'internal'`.

Wer ein Dokument lesen darf, darf jede zugehörige Version lesen —
mit Sprint-4-Ausnahme: anonyme Besucher bekommen nur die durch
`released_version_id` referenzierte Version.

### 11.2 Schreibzugriff (Sprint-3-Ergänzungen)

| Aktion                                          | Erlaubt für                                |
| ----------------------------------------------- | ------------------------------------------ |
| Dokument anlegen / Metadaten ändern             | WP-Mitglied oder Admin (unverändert)       |
| Neue Version hochladen                          | WP-Mitglied oder Admin (unverändert)       |
| Status auf `in_review` setzen                   | WP-Mitglied oder Admin                     |
| Status auf `draft` zurücksetzen                 | WP-Mitglied oder Admin                     |
| Release (`in_review → released` + Versionswahl) | WP-Lead oder Admin                         |
| Re-Release (Version wechseln)                   | WP-Lead oder Admin                         |
| Unrelease (`released → draft`)                  | nur Admin                                  |
| Sichtbarkeit auf `internal`/`workpackage`       | WP-Mitglied oder Admin                     |
| Sichtbarkeit auf `public`                       | WP-Lead oder Admin                         |
| Soft-Delete (`DELETE /api/documents/{id}` setzt `is_deleted`) | nur Admin                                  |
| Audit-Log lesen                                 | nur Admin                                  |

### 11.3 Existenz-Leakage-Schutz

Bleibt aus Sprint 2 unverändert: 404 statt 403 für nicht
sichtbare/vorhandene Dokumente. Auch Sprint-3-Endpunkte
(`status`, `release`, `visibility`, `unrelease`, `DELETE` als
Soft-Delete) liefern 404, wenn der Aufrufer das Dokument gar
nicht sehen darf.

### 11.4 Anonyme

- Schreibende Endpunkte: 401.
- Lesende Endpunkte: 401, **außer** `visibility = public ∧
  status = released` — dort kein anonymer Lesepfad in Sprint 3
  (kommt in Sprint 4); aktuell werden anonyme Aufrufe der
  internen Lesewege weiterhin mit 401 abgewiesen.

---

## 12. Tests

Erweiterung der Sprint-1/2-Tests; Pakete bleiben:
`tests/services/`, `tests/api/`, `tests/cli/`.

### 12.1 Service-Tests

- `test_audit_logger.py`:
  - `log()` schreibt Eintrag mit korrektem
    `actor_person_id`/`actor_label`, serialisiertem `details`-JSON,
    `client_ip` und `request_id` (sofern gesetzt).
  - `log()` ohne Akteur setzt `actor_label = "system"`.
  - `details` mit `datetime`-Werten serialisiert per
    `default=str`.
- `test_document_lifecycle_service.py`:
  - `draft → in_review` ohne Versionen → `ValueError`.
  - `draft → in_review` mit Version → ok, Audit-Eintrag
    `document.set_status`.
  - `in_review → released` ohne Versionswahl → `ValueError`.
  - `release()` als Nicht-Lead → `PermissionError`.
  - `release()` als WP-Lead → `status=released`,
    `released_version_id` gesetzt, Audit-Eintrag.
  - Erneuter `release()` mit anderer Version → wechselt
    `released_version_id`, Audit-Eintrag mit Vorher/Nachher.
  - `unrelease()` als Nicht-Admin → `PermissionError`.
  - `unrelease()` als Admin → `status=draft`,
    `released_version_id=None`.
  - `set_visibility(public)` als WP-Member ohne Lead → 
    `PermissionError`.
  - `set_visibility(public)` als WP-Lead → ok, Audit-Eintrag.
  - `set_visibility(workpackage)` als WP-Member → ok.
- `test_document_service_audit.py`:
  - `create` schreibt Audit-Eintrag.
  - `update_metadata` schreibt Audit-Eintrag mit Vorher/Nachher.
  - `soft_delete` als Nicht-Admin → `PermissionError`;
    als Admin → ok, Audit-Eintrag, Dokument verschwindet aus
    Listen, **`document`-Zeile bleibt physisch in der Tabelle**
    mit `is_deleted=true`, Versionen samt Storage-Dateien bleiben
    unangetastet.
- `test_document_version_service_audit.py`:
  - Upload schreibt Audit-Eintrag.
  - Upload setzt `status` und `released_version_id` **nicht**.
- `test_existing_services_audit.py`:
  - Stammdaten-Schreibops aus Sprint 1 (Partner, Person,
    Workpackage, Membership) erzeugen jetzt Audit-Einträge.
- `test_permissions_lifecycle.py`:
  - `can_release` / `can_unrelease` / `can_set_visibility`
    liefern erwartete True/False für Plattform-/WP-Rollen.

### 12.2 API-Tests

- `test_api_status.py`:
  - `POST /api/documents/{id}/status` als WP-Member nach Upload →
    200, `status=in_review`.
  - Anonym → 401, fremde WP → 404 (Existenz-Leakage),
    Wert `released` → 400.
- `test_api_release.py`:
  - `POST /api/documents/{id}/release` als WP-Lead → 200,
    `released_version_id` gesetzt.
  - als WP-Member → 403.
  - mit unbekannter `version_number` → 404.
  - mit einer `version_number`, die zu einem **anderen Dokument**
    gehört → 404 (Service prüft die semantische Bindung; die
    DB-FK alleine würde den Wert akzeptieren, weil die Version
    physisch existiert).
  - im Status `draft` → 409 (`invalid_status_transition`).
- `test_api_unrelease.py`:
  - Admin → 200, `status=draft`.
  - WP-Lead → 403.
- `test_api_visibility.py`:
  - WP-Member setzt `internal` → 200.
  - WP-Member setzt `public` → 403.
  - WP-Lead setzt `public` → 200.
- `test_api_documents_delete.py`:
  - Admin → 200/204, Dokument im List-Endpunkt nicht mehr.
  - WP-Lead → 403.
- `test_api_audit.py`:
  - Admin → 200, sieht eigene Test-Aktionen.
  - Member → 403.
  - Filter nach `entity_type=document` und `action=document.release`
    funktionieren.
- `test_api_documents_versions_no_autorelease.py`:
  - Nach `release()` von v1 wird v2 hochgeladen — `status` bleibt
    `released`, `released_version_id` zeigt weiterhin auf v1.

### 12.3 Migrations-Tests (Erweiterung)

- `test_upgrade_head_creates_audit_table` —
  `audit_log` existiert nach `upgrade head`.
- `test_document_table_has_released_version_id` —
  Spalte vorhanden.
- `test_document_released_version_id_has_fk` —
  `inspect(engine).get_foreign_keys("document")` enthält einen
  Constraint mit Namen `fk_document_released_version`, der
  `document_version.id` referenziert.
- `test_released_version_id_rejects_unknown_uuid` —
  Direkter SQL-Insert/Update von `document.released_version_id`
  mit einer UUID, zu der es keinen `document_version`-Eintrag
  gibt, scheitert mit `IntegrityError` (auf SQLite mit
  `PRAGMA foreign_keys = ON` und auf PostgreSQL nativ).
- `test_downgrade_to_0003_drops_audit_and_release` — FK-Constraint
  und Spalte sind weg, `audit_log`-Tabelle ist weg.

### 12.4 Coverage-Ziel

Coverage ≥ 80 % auf `ref4ep/services/`,
`ref4ep/api/routes/documents*` und `ref4ep/api/routes/audit*`.

---

## 13. Lokale Prüf- und Startbefehle

Annahme: Sprint-2-Stand ist eingespielt, venv aktiv,
`REF4EP_SESSION_SECRET` gesetzt.

### 13.1 Migration

```bash
cd backend
source .venv/bin/activate           # Windows: .venv\Scripts\Activate.ps1
alembic upgrade head                # 0004_audit_and_release
```

### 13.2 Server starten und manuell prüfen

```bash
uvicorn ref4ep.api.app:app --reload --port 8000
```

Browser-Pfade (mit eingeloggtem Account):

- `/portal/documents/<id>` zeigt jetzt Statusbadge,
  Sichtbarkeitsbadge und Aktionen entsprechend Rolle.
- Nach Upload v1 → „Zur Review schicken" → als WP-Lead
  „Freigeben" mit Versions-Auswahl → Status springt auf
  `released`.
- v2 hochladen → `released_version_id` bleibt auf v1.
- `/admin/audit` (als Admin-Account) zeigt die zugehörigen
  Audit-Einträge.

Beispiel-curl für direkte API-Test:

```bash
curl -X POST http://localhost:8000/api/documents/<id>/release \
  -H "X-CSRF-Token: <csrf>" \
  -b "ref4ep_session=<sess>; ref4ep_csrf=<csrf>" \
  -H "Content-Type: application/json" \
  -d '{"version_number": 1}'
```

Erwartete Antwort: `200 OK` mit `status=released`,
`released_version_id` gesetzt, kompletter `DocumentDetailOut`.

### 13.3 Tests, Linter

```bash
pytest                              # alle Tests
pytest --cov=ref4ep --cov-report=term-missing
ruff check src tests
ruff format --check src tests
```

> **Hinweis zur lokalen Default-DB und zum Storage:** wie in
> Sprint 2 — `data/ref4ep.db` und `data/storage/` sind
> gitignored. Reset:
> `rm -rf ../data/ref4ep.db ../data/storage && alembic upgrade head`.

---

## 14. Definition of Done

Sprint 3 ist abgeschlossen, wenn alle folgenden Punkte erfüllt
sind.

### Migration

- [ ] Revision `0004_audit_and_release` mit
  `down_revision = "0003_documents"`.
- [ ] `alembic upgrade head` legt `audit_log` an und ergänzt
  `document.released_version_id`.
- [ ] `alembic downgrade 0003_documents` entfernt beides
  rückstandsfrei.

### Audit-Log

- [ ] Modell `AuditLog` in `ref4ep/domain/models.py` mit Indexen
  aus §3.
- [ ] `AuditLogger`-Service mit Konstruktor- und `log()`-API aus
  §4.1.
- [ ] Hook in **allen** schreibenden Methoden gemäß §4.2; alte
  TODO-Marker aus Sprint 1 und Sprint 2 sind entfernt.
- [ ] `details` als JSON-String mit Vorher/Nachher der relevanten
  Felder.
- [ ] CLI nutzt `actor_label = "cli-admin"`; API nutzt
  `actor_person_id` aus `current_person`, `client_ip` und
  `request_id`.

### Status-Workflow

- [ ] `DocumentLifecycleService.set_status` implementiert mit
  Validierung „mind. eine Version" für `draft → in_review`.
- [ ] `release` setzt `status=released` **und**
  `released_version_id` atomar.
- [ ] `unrelease` setzt beides zurück, nur Admin.
- [ ] `PATCH /api/documents/{id}` ignoriert `status` und
  `visibility`.

### Sichtbarkeit

- [ ] `set_visibility` über dedizierten Endpunkt; CSRF-pflichtig.
- [ ] WP-Lead/Admin nötig für `to = public`.
- [ ] UI-Hinweis bei `public`/non-`released` ist sichtbar.

### Freigegebene Version

- [ ] `document.released_version_id` (CHAR(36), null) per
  Migration ergänzt **mit echtem FK auf
  `document_version.id`** (`name="fk_document_released_version"`,
  SQLAlchemy-`use_alter=True`, Alembic via
  `batch_alter_table` für SQLite).
- [ ] FK-Constraint ist im Schema sichtbar (Migrationstest
  `test_document_released_version_id_has_fk`).
- [ ] DB lehnt unbekannte UUIDs in `released_version_id` ab
  (Migrationstest `test_released_version_id_rejects_unknown_uuid`).
- [ ] Service garantiert die zusätzliche semantische Bindung
  „Version gehört zum Dokument" sowie die Invariante
  `status = released` ⇔ `released_version_id IS NOT NULL`.
- [ ] Upload einer neuen Version setzt **kein** Release.
- [ ] Re-Release wechselt `released_version_id`; alle
  Vorgängerversionen bleiben intakt und herunterladbar.

### API

- [ ] Endpunkte aus §9.1 (`status`, `release`, `unrelease`,
  `visibility`, `DELETE` als **Soft-Delete**) implementiert mit
  Pydantic-Schemas. **Kein** Hard-Delete-Endpunkt vorhanden.
- [ ] `GET /api/admin/audit` mit Filter-Query gemäß §9.2.
- [ ] CSRF-Pflicht bei allen schreibenden Endpunkten.
- [ ] 404 statt 403 für nicht-sichtbare Dokumente
  (Existenz-Leakage).
- [ ] 409 für unzulässige Statusübergänge.
- [ ] `DocumentDetailOut` enthält `released_version_id` und
  ggf. `released_version`.

### Web

- [ ] `document_detail.js` zeigt Statusbadge,
  Sichtbarkeitsbadge, Lifecycle-Aktionen und Release-Dialog
  rollenbasiert.
- [ ] Versionsliste markiert die freigegebene Version.
- [ ] `/admin/audit` zeigt das Log mit Filtern.
- [ ] Hinweis-Banner bei `visibility=public` und
  `status≠released`.

### Tests und Qualität

- [ ] Alle Tests aus §12 grün.
- [ ] Coverage ≥ 80 % auf `services/`,
  `routes/documents*`, `routes/audit*`.
- [ ] `ruff check` und `ruff format --check` grün.
- [ ] CI gegen SQLite und PostgreSQL grün.

### Was Sprint 3 explizit **nicht** prüft

- Keine öffentliche Download-Bibliothek (Sprint 4).
- Keine Review-Kommentare auf Versionen.
- Keine E-Mail-Benachrichtigung bei Statuswechsel.
- Keine Audit-Log-Rotation oder DSGVO-Spezialfälle.
- Keine versionsbezogenen Berechtigungen
  (Berechtigungen wirken am Dokument).
