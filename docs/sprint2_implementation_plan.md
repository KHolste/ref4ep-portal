# Sprint 2 – Umsetzungsplan: Dokumentenregister mit Versionierung und Storage-Interface

Dieser Plan konkretisiert den dritten Sprint aus
`docs/mvp_specification.md` §12. Er baut auf
`docs/sprint1_implementation_plan.md` (Identität, Workpackages,
Login, Initial-Seed) auf.

Verbindliche Festlegungen aus der MVP-Spezifikation, die hier gelten:

- FastAPI + statisch ausgeliefertes HTML/CSS + Vanilla-JS — **kein**
  Frontend-Framework, **kein** Node/npm.
- SQLite als lokaler Default, konfigurierbar über
  `REF4EP_DATABASE_URL`.
- Alembic für jede Schema-Änderung.
- Datenmodell aus §4 der MVP-Spec für `document` und
  `document_version` exakt wie dort spezifiziert.
- Versionierungsregeln aus §8 der MVP-Spec (append-only,
  Pflicht-Änderungsnotiz, server-vergebene `version_number`).
- Sichtbarkeits- und Berechtigungsregeln aus §7 der MVP-Spec.
- Dokumente sind **projektbezogene Registereinträge** mit
  Workpackage-Bezug, Status, Sichtbarkeit, Version und
  Änderungsnotiz — **kein** SharePoint-Klon, **keine** allgemeine
  Dateiablage.

---

## 1. Ziel von Sprint 2

Sprint 2 liefert das **interne Dokumentenregister** mit
versionierten Dateien. Am Ende muss gelten:

- Eine neue Alembic-Revision legt die Tabellen `document` und
  `document_version` an. `alembic upgrade head` und
  `alembic downgrade base` laufen beide fehlerfrei.
- Ein `Storage`-Interface (Protocol-Klasse) und eine konkrete
  Implementierung `LocalFileStorage` existieren. Letztere legt
  Dateien unter `REF4EP_STORAGE_DIR` ab und liefert sie über
  FastAPI kontrolliert aus — **nicht** über einen statischen
  Webordner.
- Eine eingeloggte Person, die WP-Mitglied ihres Workpackages ist
  (oder Admin), kann ein Dokument anlegen und eine erste Version
  hochladen. Dabei sind Pflicht: `title`, `document_type`,
  `change_note` (mind. 5 Zeichen).
- Sie kann eine **neue Version** zu einem bestehenden Dokument
  hochladen — die alte Version bleibt erhalten und herunterladbar
  (Append-only).
- `GET /api/workpackages/{code}/documents` listet alle Dokumente
  eines WPs sichtbarkeitskonform.
- `GET /api/documents/{id}` liefert Metadaten + komplette
  Versionshistorie.
- `GET /api/documents/{id}/versions/{n}/download` liefert die Datei
  byteweise mit korrektem `Content-Type` und
  `Content-Disposition: attachment; filename="<original>"`.
- Jede Version trägt SHA-256, Originaldateiname, MIME-Typ, Größe,
  Hochladende Person, Zeitstempel.
- `pytest` läuft grün; `ruff check` ist sauber.

**Fertigkriterium** (Demo-Szenario):

1. Mitglied logt sich ein und navigiert zu `/portal/workpackages/WP3`.
2. Legt das Dokument „Konstruktionszeichnung Ref-HT" an
   (`document_type=deliverable`, `deliverable_code=D3.1`).
3. Lädt eine PDF hoch mit Notiz „Initial-Entwurf v0.1".
4. Lädt eine zweite Version hoch mit Notiz „Korrektur Maßangaben".
5. Sieht beide Versionen, kann beide herunterladen, beide haben
   unterschiedliche `version_number` (1 und 2) und unterschiedliche
   SHA-256.

---

## 2. Nicht-Ziele von Sprint 2

Bewusst **nicht** im Sprint 2:

- Status-Übergänge (`draft → in_review → released`) — Sprint 3.
- Sichtbarkeitsänderung (`POST /api/documents/{id}/visibility`) —
  Sprint 3.
- Freigabe-Workflow (`POST /api/documents/{id}/release`) und das
  zugehörige Verweis-Feld auf die freigegebene Version — Sprint 3.
  Sprint 2 modelliert die freigegebene/öffentliche Version
  **noch nicht**: das Feld `released_version_id` ist **nicht
  Bestandteil** des Sprint-2-Schemas und wird erst in Sprint 3
  per neuer Alembic-Revision ergänzt.
- Löschen von Dokumenten (`DELETE /api/documents/{id}`) — Sprint 3
  oder später.
- Audit-Log-Einträge für Dokumentaktionen — Sprint 3 (Hooks bleiben
  als TODOs vorbereitet, analog Sprint 1).
- Öffentliche Download-Bibliothek (`/downloads`,
  `/api/public/documents/*`) — Sprint 4.
- Review-Workflow (Kommentare, Reviewer-Zuweisung,
  Genehmigungs-Pipeline) — post-MVP.
- Messkampagnen-/Testplanung-Module — post-MVP.
- Allgemeine Dateiablage / SharePoint-Klon — explizit nicht der
  Zielzustand.
- S3-/MinIO-Implementierung des Storage-Interfaces — geplant, aber
  in Sprint 2 nicht implementiert. Nur die Schnittstelle wird so
  geschnitten, dass der Wechsel ohne Service-Umbau möglich ist.
- Vorschau-/Inline-Anzeige von Dateien (PDF-Viewer, Bild-Inline) —
  Dateien werden ausschließlich als `attachment` ausgeliefert.
- Volltextsuche in Dokumentinhalten — post-MVP.
- DOI- oder Zenodo-Anbindung — post-MVP (offene Entscheidung 10).

---

## 3. Datenbanktabellen und Felder

Felder folgen exakt der MVP-Spezifikation §4. Konventionen wie in
Sprint 1: PK = `CHAR(36)` UUID v4, Zeitstempel mit Zeitzone,
dialektneutral (SQLite + PostgreSQL).

### `document`

| Feld                 | Typ          | Constraints                                                    |
| -------------------- | ------------ | -------------------------------------------------------------- |
| id                   | CHAR(36)     | PK                                                             |
| workpackage_id       | CHAR(36)     | NOT NULL, FK → `workpackage.id`                                |
| title                | TEXT         | NOT NULL                                                       |
| slug                 | TEXT         | NOT NULL                                                       |
| document_type        | TEXT         | NOT NULL, CHECK in (`deliverable`, `report`, `note`, `other`)  |
| deliverable_code     | TEXT         | NULL                                                           |
| status               | TEXT         | NOT NULL, CHECK in (`draft`, `in_review`, `released`),         |
|                      |              | DEFAULT `draft`                                                |
| visibility           | TEXT         | NOT NULL, CHECK in (`workpackage`, `internal`, `public`),      |
|                      |              | DEFAULT `workpackage`                                          |
| created_by_person_id | CHAR(36)     | NOT NULL, FK → `person.id`                                     |
| is_deleted           | BOOLEAN      | NOT NULL, DEFAULT FALSE                                        |
| created_at           | TIMESTAMP    | NOT NULL                                                       |
| updated_at           | TIMESTAMP    | NOT NULL                                                       |

`UNIQUE (workpackage_id, slug)` — Slug ist innerhalb eines WPs
eindeutig.

**Hinweis zur freigegebenen / öffentlichen Version:** Das
`document`-Schema enthält in Sprint 2 **kein** Verweis-Feld auf
die freigegebene Version (kein `released_version_id` o. ä.).
Begründung: Sprint 2 implementiert ausschließlich das interne
Register mit `draft`/`workpackage`-Versionen — Release-Logik und
öffentliche Download-Bibliothek sind Sprint 3 bzw. Sprint 4.
Sobald Sprint 3 den Freigabe-Workflow einführt, ergänzt eine
eigene Alembic-Revision dort das passende Feld; Sprint 2
verzichtet bewusst darauf, um Fremd-Schlüssel-Zyklen
(`document` ↔ `document_version`) und unbenutzte Felder im
Schema zu vermeiden.

### `document_version`

Append-only. Eine Zeile pro Upload.

| Feld                  | Typ          | Constraints                                                |
| --------------------- | ------------ | ---------------------------------------------------------- |
| id                    | CHAR(36)     | PK                                                         |
| document_id           | CHAR(36)     | NOT NULL, FK → `document.id`                               |
| version_number        | INTEGER      | NOT NULL, server-vergeben, monoton ≥ 1 pro `document_id`   |
| version_label         | TEXT         | NULL (frei)                                                |
| change_note           | TEXT         | NOT NULL, mindestens 5 Zeichen (Service-validiert)         |
| storage_key           | TEXT         | NOT NULL — interner Key für das Storage-Backend            |
| original_filename     | TEXT         | NOT NULL                                                   |
| mime_type             | TEXT         | NOT NULL                                                   |
| file_size_bytes       | INTEGER      | NOT NULL, > 0                                              |
| sha256                | TEXT         | NOT NULL (64 Hex-Zeichen)                                  |
| uploaded_by_person_id | CHAR(36)     | NOT NULL, FK → `person.id`                                 |
| uploaded_at           | TIMESTAMP    | NOT NULL                                                   |

`UNIQUE (document_id, version_number)`.

**Keine Updates, keine Löschungen** — die Tabelle ist zwischen
allen Sprints append-only.

### Indexe

| Tabelle             | Index                                       | Zweck                       |
| ------------------- | ------------------------------------------- | --------------------------- |
| `document`          | `INDEX (workpackage_id, is_deleted)`        | WP-Liste                    |
| `document`          | `UNIQUE (workpackage_id, slug)`             | Slug-Eindeutigkeit pro WP   |
| `document_version`  | `UNIQUE (document_id, version_number)`      | monotone Versionsnummern    |
| `document_version`  | `INDEX (document_id, uploaded_at DESC)`     | Versionshistorie-Sortierung |
| `document_version`  | `INDEX (sha256)`                            | Duplikaterkennung pro Doku  |

### Datenmodell-Hinweise

- `document_type` ist in Sprint 2 ein einfaches Enum (CHECK-Constraint).
  Per MVP-Spec offene Entscheidung 4: bleibt fürs Erste **rein
  integer-basiert** für `version_number`; `version_label` ist
  freier Text. Ein erzwungenes D-Nummer-Schema wird aktuell **nicht**
  implementiert (kann in Sprint 5 ergänzt werden, wenn Bedarf besteht).
- Da Sprint 2 kein Verweis-Feld auf eine freigegebene Version
  enthält, gibt es zwischen `document` und `document_version`
  nur **eine** Fremd-Schlüssel-Richtung
  (`document_version.document_id → document.id`). Damit entstehen
  keine Zyklen, kein `INITIALLY DEFERRED` ist nötig, und das
  Schema bleibt sowohl unter SQLite als auch unter PostgreSQL
  unkompliziert.

### Nicht in Sprint 2

`audit_log`, `milestone`, `comment`, `review`, `dataset`,
`document_tag`, `document_link`. Bewusst weggelassen.

---

## 4. Status- und Sichtbarkeitswerte

Plan-konsistente Wertelisten — werden über CHECK-Constraints
(siehe §3) und Service-Validierung erzwungen.

### `status`

| Wert         | Bedeutung in Sprint 2                                                                |
| ------------ | ------------------------------------------------------------------------------------ |
| `draft`      | **Default** für jedes neue Dokument. In Sprint 2 unveränderlich.                     |
| `in_review`  | Wert ist im Schema vorgesehen, **wird in Sprint 2 nicht gesetzt** (kein API-Pfad).   |
| `released`   | Wird in Sprint 3 freigeschaltet; in Sprint 2 nicht setzbar.                          |

**Konsequenz:** Jedes Sprint-2-Dokument bleibt im Zustand `draft`.
Dadurch entfällt die Notwendigkeit, in Sprint 2 zwischen Status-
sichtbarkeiten zu unterscheiden — es gibt nur Drafts.

### `visibility`

| Wert          | Bedeutung in Sprint 2                                                                          |
| ------------- | ---------------------------------------------------------------------------------------------- |
| `workpackage` | **Default** für jedes neue Dokument. Nur WP-Mitglieder + Admin sehen das Dokument.             |
| `internal`    | Wert ist im Schema vorgesehen, wird in Sprint 2 **nicht setzbar** (kein API-Pfad).             |
| `public`      | Wert ist im Schema vorgesehen, wird in Sprint 2 **nicht setzbar**. Erste Nutzung in Sprint 3/4.|

**Konsequenz:** Sichtbarkeit jedes Sprint-2-Dokuments ist
`workpackage`. Ein öffentlicher Download-Pfad existiert in Sprint 2
nicht (siehe §2 Nicht-Ziele und §11). Erst Sprint 3 bringt
`POST /api/documents/{id}/visibility`, Sprint 4 die öffentliche
Bibliothek.

### Default-Werte beim Anlegen (server-vergeben)

| Feld                 | Default                       |
| -------------------- | ----------------------------- |
| `status`             | `draft` (in Sprint 2 konstant) |
| `visibility`         | `workpackage` (in Sprint 2 konstant) |
| `is_deleted`         | `false`                       |
| `slug`               | aus `title` generiert         |

`status` und `visibility` werden in Sprint 2 weder von einem
API-Pfad noch über die UI verändert; alle Sprint-2-Dokumente
bleiben `draft`/`workpackage`. Die Modellierung der freigegebenen
bzw. öffentlichen Version (Verweis-Feld, Release-Workflow,
öffentlicher Download) folgt erst in Sprint 3 und Sprint 4.

---

## 5. Versionierungsregeln

Sprint-2-bindend (konsistent mit MVP-Spec §8):

1. **Eine Datei = eine Version.** Jeder Upload erzeugt einen neuen
   `document_version`-Datensatz, niemals ein In-Place-Update.
2. **`version_number`** ist eine **server-vergebene** monoton
   steigende Ganzzahl pro Dokument, beginnend bei 1. Der Client
   übergibt sie nicht. Die Allokation läuft im Service als
   `MAX(version_number) + 1` innerhalb der Schreibtransaktion;
   die UNIQUE-Constraint fängt Wettlauf-Verletzungen ab und der
   Service wiederholt einmal bei `IntegrityError`.
3. **`version_label`** ist ein freier Textwert (optional).
   Empfehlung an Nutzer: „v0.1", „D3.1-final" etc. **Kein** Schema
   erzwungen.
4. **`change_note` ist Pflicht** — auch beim Erst-Upload.
   Mindestlänge **5 Zeichen** (Whitespace-getrimmt). Service wirft
   `ValueError` bei Verletzung; API antwortet 422.
5. **`sha256`** wird serverseitig beim Upload aus dem
   tatsächlichen Datei-Inhalt berechnet (nicht vom Client
   übernommen). Jeder Upload bekommt seinen eigenen Hash —
   identische Inhalte erzeugen denselben Hash.
6. **Identische Inhalte sind erlaubt.** Lädt jemand denselben
   Inhalt erneut hoch (gleicher SHA-256 wie eine bereits
   existierende Version desselben Dokuments), wirft das nicht;
   API-Antwort enthält ein Warnungs-Feld
   (`"warnings": ["duplicate_content_of_v<n>"]`). Der Aufrufer
   kann den Upload bewusst behalten (Korrektur von Metadaten o. ä.).
7. **Dateien werden nicht überschrieben.** Storage-Keys enthalten
   den `version_id`; siehe §6.
8. **Versionen werden nicht gelöscht.** Soft-Delete des Dokuments
   (Sprint 3) lässt die Versionen physisch bestehen, blendet sie
   aber aus.
9. **Erst-Upload und Folgeupload** laufen über denselben
   Endpunkt: `POST /api/documents/{id}/versions`. Ein
   neu-angelegtes Dokument ohne Versionen ist gültig (Sprint 2
   erlaubt Trennung von Anlage und erstem Upload), wird aber im
   UI als „leer" markiert.
10. **Audit-Pflicht** bleibt für Sprint 3. In Sprint 2 wird im
    Code an den passenden Stellen ein
    `# TODO Sprint 3: audit_logger.log_action(...)`-Marker
    gesetzt.

---

## 6. Storage-Interface und lokales Filesystem-Backend

Pflichten:

- **Schnittstellen-Trennung**: Geschäftslogik (Services) kennt nur
  ein abstraktes `Storage`-Protokoll, nicht das konkrete
  Filesystem.
- **Lokales Backend** für Sprint 2: `LocalFileStorage`, schreibt
  in `REF4EP_STORAGE_DIR`.
- **Spätere Backends**: `S3Storage` / `MinioStorage` werden in
  einem späteren Sprint ergänzt, ohne Service-Umbau. **Nicht** in
  Sprint 2 implementiert.
- **Auslieferung kontrolliert über FastAPI**, nicht über statische
  Mounts. Dateien sind über einen authentifizierten Endpunkt
  abrufbar; das `REF4EP_STORAGE_DIR` ist **nicht** über `/static`
  oder `/portal` exponiert.

### Storage-Protokoll

Ablage in `ref4ep/storage/__init__.py` (Interface) und
`ref4ep/storage/local.py` (Implementierung).

```python
class Storage(Protocol):
    def put_stream(self, key: str, stream: BinaryIO) -> StorageWriteResult: ...
    def open_read(self, key: str) -> BinaryIO: ...
    def exists(self, key: str) -> bool: ...
    def size(self, key: str) -> int: ...

@dataclass(frozen=True)
class StorageWriteResult:
    sha256: str
    file_size_bytes: int
```

`put_stream` liest den Stream chunkweise, schreibt in eine
temporäre Datei, berechnet währenddessen SHA-256 und Größe,
und verschiebt die Datei am Ende atomar an die Zielposition.

### Pfad-Schema von `LocalFileStorage`

```
{REF4EP_STORAGE_DIR}/
  documents/
    {document_id}/
      {version_id}.bin
```

- `document_id` und `version_id` sind UUIDs (CHAR(36)).
- Dateiendung auf der Platte ist immer `.bin` — der **Original-
  dateiname bleibt nur in der DB**. Damit landen keine vom Nutzer
  kontrollierten Pfadteile auf der Platte.
- `storage_key = f"documents/{document_id}/{version_id}.bin"` —
  identisch in DB-Spalte und Storage-Aufrufen.

### Pfad-Sicherheit

- `LocalFileStorage` resolved den Zielpfad und lehnt jeden Pfad
  ab, der nach `path.resolve()` nicht innerhalb von
  `REF4EP_STORAGE_DIR` liegt (Path-Traversal-Schutz).
- Der `key`-Parameter wird strikt validiert
  (Regex: `^documents/[0-9a-f-]{36}/[0-9a-f-]{36}\.bin$`).

### Auslieferung

`Storage.open_read` liefert ein binäres File-like-Objekt; die
Route streamt es mittels FastAPI `StreamingResponse` an den
Client.

### Konfiguration

`REF4EP_STORAGE_DIR` existiert seit Sprint 0 und ist Default
`../data/storage` (relativ zu `backend/`). Sprint 2 nutzt diesen
Wert unverändert. Beim Start prüft `create_app()` einmalig, dass
das Verzeichnis existiert oder anlegbar ist; bei Fehler nur
Warning-Log (Tests können kein Storage brauchen).

---

## 7. Upload-/Download-Regeln

### Upload

`POST /api/documents/{id}/versions` mit
`multipart/form-data`:

- `file`: die hochzuladende Datei (Pflicht).
- `change_note`: Pflicht-Textfeld, mind. 5 Zeichen
  (whitespace-trimmed).
- `version_label`: optional.

Verarbeitung:

1. Auth-Check (Person eingeloggt) und CSRF-Check.
2. Berechtigungs-Check (siehe §11): Aufrufer ist WP-Mitglied
   des Document-WP **oder** Admin.
3. **MIME-Whitelist** (Sprint 2 fest):
   `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`,
   `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`,
   `application/vnd.openxmlformats-officedocument.presentationml.presentation`,
   `application/zip`, `image/png`, `image/jpeg`. Ablehnung mit
   HTTP 415 (`unsupported_media_type`).
4. **Größenlimit**: `Settings.max_upload_mb` (Default 100 MB).
   Das Limit wird **hart während des Streams** durch eine
   Size-Limiting-Wrapper-Logik durchgesetzt — der Wrapper liest
   chunkweise vom Upload, summiert die Bytes mit und bricht ab,
   sobald das Limit überschritten würde. Überschreitung führt
   zuverlässig zu HTTP 413 (`payload_too_large`).
   Ein **Vorab-Check über den `Content-Length`-Header entfällt
   bewusst**: ein fehlender oder gefälschter Header darf das
   Limit nicht umgehen. Die Stream-Wrapper-Prüfung ist die einzige
   verbindliche Quelle der Wahrheit.
5. `Storage.put_stream()` schreibt chunkweise und liefert
   `StorageWriteResult` (sha256, size).
6. `version_number` wird im Service als
   `MAX(version_number) + 1` allokiert; bei IntegrityError-
   Rennen einmaliger Retry.
7. `document_version`-Zeile wird angelegt mit allen Metadaten.
8. Antwort enthält das neue `DocumentVersionOut`-Schema, ggf.
   `warnings: ["duplicate_content_of_v<n>"]`.

### Download (intern, Sprint 2)

`GET /api/documents/{id}/versions/{n}/download`:

1. Auth-Check (Person eingeloggt).
2. Berechtigungs-Check: Aufrufer darf das Dokument lesen
   (siehe §11). In Sprint 2: WP-Mitglied **oder** Admin.
3. `document_version` mit `version_number = n` für `document_id =
   id` laden; 404 bei nicht existent.
4. `Storage.open_read(storage_key)` öffnet einen Stream.
5. Antwort: `StreamingResponse` mit:
   - `Content-Type: <mime_type>`
   - `Content-Length: <file_size_bytes>`
   - `Content-Disposition: attachment; filename="<original_filename>"`
   - `X-Content-Type-Options: nosniff`
6. **Niemals** als HTML-Inline-Vorschau ausgeliefert. Auch nicht
   für PDFs (Sprint 2 setzt bewusst `attachment`).

### Download-Pfad ist nicht öffentlich

- Es gibt **keinen** statischen Mount, der `REF4EP_STORAGE_DIR`
  ausliefern würde.
- Es gibt in Sprint 2 **keinen** Endpunkt unterhalb
  `/api/public/...`, der Dateien zurückgibt.
- Sprint 4 bringt den öffentlichen Pfad
  `GET /api/public/documents/{slug}/download` — der greift dann
  über denselben `Storage.open_read`, prüft aber zusätzlich
  `visibility = public ∧ status = released` und liefert die in
  Sprint 3 freigegebene Version aus. Das nötige Schema-Element
  zur Bestimmung der freigegebenen Version wird erst in Sprint 3
  ergänzt; in Sprint 2 existiert es nicht.

### Streaming und Speicherbegrenzung

- Upload: chunkweises Lesen mit fester Chunk-Größe (z. B. 1 MiB).
  Kein vollständiges In-Memory-Holen.
- Download: chunkweises Streamen über
  `StreamingResponse(iterator)`.
- Fehler während des Uploads (Disk voll, Hash-Fehler) → temporäre
  Datei wird gelöscht; kein Halb-Schreiben in den Zielpfad.

---

## 8. Services

Alle unter `ref4ep/services/`. Konstruktor-Signatur einheitlich
wie in Sprint 1: `Service(session, *, role=None, person_id=None)`.
Schreibmethoden prüfen Berechtigung im Service, nicht in der
Route. TODO-Marker für Sprint-3-Audit bleiben dran.

### `services/storage_validation.py`

Modulglobale Konstanten und reine Hilfsfunktionen:

- `MIME_WHITELIST: frozenset[str]` — siehe §7.
- `validate_mime(mime: str) -> None` — wirft `ValueError`.
- `validate_size(bytes_: int, max_bytes: int) -> None` — wirft
  `ValueError`.
- `compute_storage_key(document_id: str, version_id: str) -> str` —
  liefert `"documents/{document_id}/{version_id}.bin"`.
- `validate_storage_key(key: str) -> None` — Regex-Check.

### `services/document_service.py`

Methoden:

- `list_for_workpackage(workpackage_code: str, *, auth: AuthContext)
  -> list[Document]` — filtert sichtbarkeitskonform.
- `get_by_id(document_id: str, *, auth: AuthContext) -> Document` —
  Sichtbarkeitsprüfung; 404 bei „nicht sichtbar oder nicht
  vorhanden" (kein Existenzleak).
- `create(*, workpackage_code: str, title: str, document_type: str,
  deliverable_code: str | None, auth: AuthContext) -> Document` —
  prüft WP-Mitgliedschaft (oder Admin), erzeugt Slug aus Titel,
  setzt `status="draft"`, `visibility="workpackage"`.
- `update_metadata(document_id: str, *, title: str | None = None,
  document_type: str | None = None, deliverable_code: str | None = None,
  auth: AuthContext) -> Document`.
- `_can_read(document, auth) -> bool` und
  `_can_write(document, auth) -> bool` — interne Helfer auf
  Basis von §11.

Sprint-2-Verbot: kein `release()`, kein `set_visibility()`, kein
`delete()`.

### `services/document_version_service.py`

Methoden:

- `upload_new_version(document_id: str, *, file_stream: BinaryIO,
  original_filename: str, mime_type: str, change_note: str,
  version_label: str | None, auth: AuthContext, storage: Storage,
  max_upload_bytes: int) -> tuple[DocumentVersion, list[str]]` —
  liefert das neue Version-Objekt und eine Liste von Warnungen
  (z. B. `"duplicate_content_of_v3"`).
- `list_for_document(document_id: str, *, auth: AuthContext)
  -> list[DocumentVersion]` — sortiert nach `version_number ASC`.
- `get_for_download(document_id: str, version_number: int, *,
  auth: AuthContext) -> DocumentVersion` — Sichtbarkeitsprüfung;
  404 bei nicht-sichtbar/-vorhanden.

### `services/permissions.py` (Erweiterung)

- `can_read_document(auth: AuthContext, document: Document)
  -> bool` — Sprint-2-Variante:
  - True wenn `auth.platform_role == "admin"`.
  - True wenn `auth` Mitglied im
    `document.workpackage_id` ist und `document.visibility ∈
    {workpackage, internal}` oder Person eingeloggt und
    `document.visibility == internal`.
  - False sonst.
- `can_write_document(auth: AuthContext, document: Document)
  -> bool` — True wenn Admin oder WP-Mitglied im
  `document.workpackage_id`.

Diese Helfer sind Sprint-2-aktiv (in Routen verwendet), nicht nur
deklarativ wie in Sprint 1.

### `Storage` und `LocalFileStorage`

Ablage `ref4ep/storage/__init__.py` und
`ref4ep/storage/local.py`. Schnittstelle wie in §6 skizziert.
Die `create_app`-Factory baut **eine** `LocalFileStorage`-Instanz
und legt sie auf `app.state.storage` ab. Tests können hier eine
In-Memory-Implementierung injizieren (`InMemoryStorage` für die
Test-Suite, im Test-Modul lokal definiert oder als
`tests/_test_storage.py` ergänzt).

---

## 9. API-Endpunkte

Alle unter Präfix `/api`, JSON-Antworten. CSRF-Header
(`X-CSRF-Token`) Pflicht für alle nicht-GETs.

### Dokumentregister

| Methode | Pfad                                                    | Zweck                                          | Rolle                            |
| ------- | ------------------------------------------------------- | ---------------------------------------------- | -------------------------------- |
| GET     | `/api/workpackages/{code}/documents`                    | Liste der Dokumente eines WPs                  | WP-Mitglied oder admin           |
| POST    | `/api/workpackages/{code}/documents`                    | Neues Dokument anlegen (ohne Datei)            | WP-Mitglied oder admin           |
| GET     | `/api/documents/{id}`                                   | Dokumentdetail inkl. Versionsliste             | Sichtbarkeitsregel (§11)         |
| PATCH   | `/api/documents/{id}`                                   | Titel, Typ, Deliverable-Code ändern            | WP-Mitglied oder admin           |
| GET     | `/api/documents/{id}/versions`                          | Versionsliste (separat von Detail)             | Sichtbarkeitsregel (§11)         |
| POST    | `/api/documents/{id}/versions`                          | Neue Version hochladen, multipart, Pflicht-`change_note` | WP-Mitglied oder admin |
| GET     | `/api/documents/{id}/versions/{n}/download`             | Download einer Version                         | Sichtbarkeitsregel (§11)         |

### Bewusst nicht in Sprint 2

| Methode | Pfad                                                    | Sprint                  |
| ------- | ------------------------------------------------------- | ----------------------- |
| POST    | `/api/documents/{id}/release`                           | Sprint 3                |
| POST    | `/api/documents/{id}/visibility`                        | Sprint 3                |
| DELETE  | `/api/documents/{id}`                                   | Sprint 3 oder später    |
| GET     | `/api/public/documents`, `/api/public/documents/{slug}` | Sprint 4                |
| GET     | `/api/public/documents/{slug}/download`                 | Sprint 4                |

### Konventionen

- Fehlerantworten:
  `{"error": {"code": "...", "message": "..."}}`.
- 401 ohne gültige Session.
- 403 für Berechtigungs-/CSRF-Fehler.
- 404 für „nicht sichtbar oder nicht vorhanden" (keine
  Existenz-Leakage).
- 409 bei Slug-Kollision innerhalb des WPs.
- 413 bei Größenüberschreitung beim Upload.
- 415 bei nicht erlaubtem MIME-Typ.
- 422 für Validierungsfehler (Pydantic-Default,
  z. B. `change_note` < 5 Zeichen).
- Pagination der Dokumentenliste: `?limit=`, `?offset=`,
  Default 50, Max 200.

### Antwortschemas (Sprint 2)

- `DocumentOut` (Liste): `id`, `slug`, `title`, `document_type`,
  `deliverable_code`, `status`, `visibility`, `latest_version`
  (inline, optional), `created_at`, `updated_at`.
- `DocumentDetailOut`: zusätzlich `description` (falls
  vorhanden — in Sprint 2 nicht ausgefüllt), `workpackage`
  (Code+Title), `created_by` (Person-Ref), `versions:
  list[DocumentVersionOut]`.
- `DocumentVersionOut`: `id`, `version_number`, `version_label`,
  `change_note`, `original_filename`, `mime_type`,
  `file_size_bytes`, `sha256`, `uploaded_by` (Person-Ref),
  `uploaded_at`.

---

## 10. Web-Ansichten

Sprint 2 erweitert die bestehende SPA aus Sprint 1 um zwei
Ansichten und einen Inline-Bereich.

### `/portal/workpackages/{code}` (Erweiterung)

Bestehende Detail-Seite aus Sprint 1 erhält im Hauptbereich einen
zusätzlichen Block **„Dokumente"**:

- Tabelle aller Dokumente im WP: Spalten `Code` (Deliverable-Code,
  falls vorhanden), `Titel`, `Typ`, `Status`, `Letzte Version`,
  `Aktualisiert`.
- Klick auf Zeile öffnet `/portal/documents/{id}`.
- Button **„Neues Dokument"** → öffnet einen Dialog mit
  Pflichtfeldern `title`, `document_type`, `deliverable_code`
  (optional). Submit ruft
  `POST /api/workpackages/{code}/documents`. Bei Erfolg Redirect
  auf das neu angelegte Dokument.

### `/portal/documents/{id}` (neu)

Dokumentdetail in der SPA:

- Kopfbereich: Titel, Workpackage-Code, Typ, Status, Sichtbarkeit
  (alle in Sprint 2 konstant `draft`/`workpackage`),
  Deliverable-Code (falls vorhanden), Erstellt-Datum, Erstellt-
  Person.
- Block **„Versionen"**: Tabelle absteigend nach
  `version_number`. Spalten: `#`, `Label`, `Änderungsnotiz`,
  `Datei`, `Größe`, `SHA-256` (gekürzt, mit Tooltip), `Hochladende`,
  `Datum`, `Aktion (Download)`.
- Button **„Neue Version hochladen"**: öffnet das Upload-Formular
  (siehe unten).
- Button **„Metadaten bearbeiten"**: einfaches Inline-Formular
  für `title`, `document_type`, `deliverable_code`.

### Upload-Formular

In Sprint 2 als **Inline-Dialog** im Detailfenster (kein
separater Pfad nötig). Felder:

- `change_note` (Textarea, Pflicht, ≥ 5 Zeichen, sichtbarer
  Hinweis „Was hat sich geändert?").
- `version_label` (optional, Eingabefeld).
- `file` (File-Picker, eine Datei).

Submit per `multipart/form-data` an
`POST /api/documents/{id}/versions`. Während des Uploads
deaktivierter Submit-Button und einfacher Progress-Hinweis (kein
Fortschrittsbalken in Sprint 2 — erst Sprint 5).

Erfolgsfall: Versionsliste wird aktualisiert (Reload des
Dokumentdetails).

Fehlerfall: Server-Antwort wird im Dialog als Fehler-Banner
angezeigt (z. B. „Datei zu groß", „MIME-Typ nicht erlaubt",
„Änderungsnotiz zu kurz").

### Neue JS-Module

Unter `backend/src/ref4ep/web/modules/`:

- `document_detail.js` — Detail- und Versionsanzeige.
- `document_create.js` — Anlage-Dialog (kann ggf. Teil von
  `workpackage_detail.js` werden).
- `document_upload.js` — Upload-Dialog mit Pflicht-`change_note`.

### Erweiterung von `app.js`

- Neue Routen-Patterns:
  - `/^\/portal\/documents\/([^/]+)\/?$/` → Modul
    `document_detail`, Param `id`.
- `workpackage_detail.js` lädt zusätzlich
  `GET /api/workpackages/{code}/documents` und rendert die
  Dokumente-Tabelle.

### Public-Zone

In Sprint 2 **keine** Erweiterung der öffentlichen Templates — die
öffentliche Download-Bibliothek folgt Sprint 4.

---

## 11. Rechte- und Sichtbarkeitsregeln (in Sprint 2 wirksam)

Per MVP-Spec §7, eingeschränkt auf das, was Sprint 2 schon zeigt
(alle Dokumente sind in Sprint 2 `draft`/`workpackage`).

### Lesezugriff auf ein Dokument

Eine Person darf ein Sprint-2-Dokument **lesen**, wenn:

1. Person ist `admin` (Plattformrolle), **oder**
2. Person ist Mitglied im `workpackage_id` des Dokuments
   (egal welche WP-Rolle).

In Sprint 2 erfüllt Bedingung „2" alle Sichtbarkeitsfälle, weil
`visibility` immer `workpackage` ist. Die generische
`can_read_document`-Funktion (siehe §8) bleibt aber bereits jetzt
auf den vollen MVP-§7-Regeln aufgebaut, damit Sprint 3 sie
unverändert nutzen kann.

### Lesezugriff auf eine Version

Wer das Dokument lesen darf, darf jede zugehörige Version lesen.
Sprint 2 kennt keine öffentlichen Anonymen, deshalb keine
„nur freigegebene Version"-Sonderregel.

### Schreibzugriff

| Aktion                                          | Erlaubt für                                    |
| ----------------------------------------------- | ---------------------------------------------- |
| Dokument anlegen in WP                          | WP-Mitglied (jede WP-Rolle) oder admin         |
| Metadaten ändern (`title`, `document_type`,     |                                                |
| `deliverable_code`)                             | WP-Mitglied oder admin                         |
| Neue Version hochladen                          | WP-Mitglied oder admin                         |
| Status, Sichtbarkeit, Release, Löschen          | **nicht in Sprint 2**                          |

Ein nicht-Mitglied (eingeloggt, aber nicht im Workpackage) erhält
HTTP 404 — kein 403 — beim Versuch, ein nicht-sichtbares Dokument
abzufragen (Existenz-Leakage-Schutz).

### Anonyme

Anonyme bekommen für **alle** `/api/documents/...`- und
`/api/workpackages/.../documents`-Endpunkte HTTP 401. Es gibt in
Sprint 2 keinen anonymen Lesepfad auf Dokumente.

---

## 12. Tests

Erweiterung der Testbasis aus Sprint 1; Pakete bleiben:
`tests/services/`, `tests/api/`, `tests/cli/`.

### Service- und Storage-Tests

- `test_storage_local.py`:
  - `LocalFileStorage.put_stream` schreibt Datei, liefert
    korrekten SHA-256 und Größe; Rückgabewert deckt sich mit
    erwartetem `hashlib.sha256(content).hexdigest()`.
  - `open_read` liefert byte-identischen Inhalt zurück.
  - Pfad-Traversal-Versuch (`key="../../etc/passwd"`) wird
    abgelehnt.
  - Fehlende Datei: `open_read` wirft eindeutige Exception
    (`FileNotFoundError` oder eigener Typ).
- `test_storage_validation.py`:
  - MIME-Whitelist akzeptiert/blockiert die jeweils erwarteten
    Typen.
  - Größenlimit korrekt.
  - `compute_storage_key` und `validate_storage_key` Roundtrip.
- `test_document_service.py`:
  - Anlegen ohne Mitgliedschaft wirft `PermissionError`.
  - Mitglied legt Dokument an, Slug aus Titel, `status=draft`,
    `visibility=workpackage`.
  - Slug-Kollision pro WP führt zu IntegrityError oder
    Service-eigener Konflikt-Exception.
  - `update_metadata` ändert nur erlaubte Felder.
  - `list_for_workpackage`: Mitglied sieht alle, Nicht-Mitglied
    sieht nichts (oder 404 in Route).
- `test_document_version_service.py`:
  - Erst-Upload: `version_number = 1`, neuer Storage-Key,
    `change_note ≥ 5 Zeichen` Pflicht.
  - Zweit-Upload: `version_number = 2`, beide bleiben lesbar.
  - `change_note` zu kurz → `ValueError` / 422.
  - Identische Datei zweimal → zweite Version wird angelegt,
    Warnung `duplicate_content_of_v1` zurückgegeben.

> **Race-Verhalten — bewusst kein Sprint-2-Test.** Ein expliziter
> paralleler Upload-Test mit `threading.Thread` /
> `concurrent.futures` wird in Sprint 2 **nicht** umgesetzt. Die
> Korrektheit der `version_number`-Vergabe wird stattdessen
> strukturell abgesichert:
>
> - Die Tabelle `document_version` trägt
>   `UNIQUE (document_id, version_number)` (siehe §3); gleichzeitige
>   Schreibversuche mit derselben Nummer scheitern an dieser
>   Datenbank-Constraint.
> - `DocumentVersionService.upload_new_version` reagiert auf den
>   `IntegrityError` mit einem einmaligen Retry und holt sich dabei
>   die nächste freie `version_number`.
>
> Ein echter Parallel- bzw. Lasttest wird als **späterer Testpunkt**
> notiert (sinnvoll, sobald Mehr-Worker-Setups oder konkurrierende
> Clients in der Praxis vorkommen) und ist nicht Teil der Sprint-2-
> Definition of Done.

### API-Tests

- `test_api_documents.py`:
  - `POST /api/workpackages/{code}/documents` als Nicht-Mitglied
    → 403 oder 404.
  - Als Mitglied → 201 mit `slug`, `status=draft`.
  - `GET /api/workpackages/{code}/documents` listet eigene
    Dokumente.
  - `PATCH /api/documents/{id}` ändert `title`.
- `test_api_versions_upload.py`:
  - Multipart-Upload mit gültiger PDF → 201,
    `version_number=1`, `sha256`-Wert prüfbar.
  - Upload ohne `change_note` → 422.
  - Upload mit `change_note="    "` → 422.
  - Upload mit `Content-Type: application/x-msdownload` → 415.
  - Upload zu groß → 413.
  - CSRF-Token fehlt → 403.
- `test_api_versions_download.py`:
  - Download als Mitglied → 200, `Content-Disposition: attachment`,
    Body-Hash gleich `sha256` aus DB.
  - Download anonym (kein Cookie / ungültiger Token) → 401.
  - Download nicht-existente `version_number` → 404.

> **Fremdnutzer-Leakage-Schutz — Aufteilung Service vs. API.** Der
> Schutz davor, dass eine eingeloggte Person ohne WP-Mitgliedschaft
> Existenz und Inhalt fremder Dokumente erfährt, wird in Sprint 2
> auf **Service-Ebene** geprüft (siehe
> `tests/services/test_document_service.py
> ::test_get_by_id_hides_documents_for_non_members` und
> `::test_list_for_workpackage_excludes_non_members` —
> `DocumentNotFoundError` wird mit einem ``foreign``-AuthContext
> ausgelöst). Auf API-Ebene wird in Sprint 2 nur der anonyme/
> ungültige Token-Pfad gegen 401 abgesichert; ein API-Test mit
> einem **echten Drittnutzer-Account** ohne Membership wird ergänzt,
> sobald die Admin-UI / Personenanlage komfortabler nutzbar ist
> (Sprint 5 — Plan-konformer Polish-Sprint).

### Migrations-Tests (Erweiterung)

- `test_upgrade_head_creates_document_tables` (analog Sprint 1).
- `test_downgrade_to_0002_drops_document_tables`.

### CLI

In Sprint 2 **keine** CLI-Erweiterung. Dokumente werden
ausschließlich über das Web-API angelegt; die CLI bleibt auf
Identität/Stammdaten beschränkt. (Bei Bedarf in Sprint 5.)

### Coverage

Coverage-Ziel ≥ 80 % auf `ref4ep/services/`, `ref4ep/storage/`
und `ref4ep/api/routes/documents*` (zusätzliches Modul).

---

## 13. Lokale Prüf- und Startbefehle

Annahme: Sprint-1-Stand ist eingespielt, venv aktiv,
`REF4EP_SESSION_SECRET` gesetzt.

### Migration

```bash
cd backend
source .venv/bin/activate           # Windows: .venv\Scripts\Activate.ps1
alembic upgrade head                # 0003_documents anwenden
```

### Storage-Verzeichnis

`REF4EP_STORAGE_DIR` zeigt per Default auf
`../data/storage`. Beim ersten Lauf wird das Verzeichnis von der
App angelegt (oder manuell vorab):

```bash
mkdir -p ../data/storage
```

### Server starten und manuell prüfen

```bash
uvicorn ref4ep.api.app:app --reload --port 8000
```

Browser-/curl-Pfade:

- Login wie in Sprint 1.
- `http://localhost:8000/portal/workpackages/WP3` zeigt den
  Dokumenten-Block (zunächst leer).
- Neues Dokument anlegen, dann Erst-Upload via Dialog.
- `curl` für API-Direkttest, mit `ref4ep_session`- und
  `ref4ep_csrf`-Cookies aus dem Browser:

```bash
curl -X POST http://localhost:8000/api/documents/<id>/versions \
  -H "X-CSRF-Token: <csrf>" \
  -b "ref4ep_session=<sess>; ref4ep_csrf=<csrf>" \
  -F "file=@./entwurf.pdf;type=application/pdf" \
  -F "change_note=Initial-Entwurf v0.1"
```

Erwartete Antwort: `201 Created` mit `version_number=1`, `sha256`,
`storage_key="documents/<doc-uuid>/<version-uuid>.bin"`.

### Tests, Linter

```bash
pytest                              # alle Tests
pytest --cov=ref4ep --cov-report=term-missing
ruff check src tests
ruff format --check src tests
```

> **Hinweis zur lokalen Default-DB und zum Storage-Verzeichnis:**
> Manuelle Smoke-Tests schreiben in
> `ref4ep-portal/data/ref4ep.db` und in
> `ref4ep-portal/data/storage/`. Beide Pfade sind
> über `.gitignore` aus dem Repo ausgeschlossen — Smoke-Uploads
> verfälschen weder den Repo-Stand noch die CI. Reset:
> `rm -rf ../data/ref4ep.db ../data/storage && alembic upgrade head`.

---

## 14. Definition of Done

Sprint 2 ist abgeschlossen, wenn alle folgenden Punkte erfüllt
sind.

### Migration

- [ ] Revision `0003_documents` existiert mit
  `down_revision = "0002_identity_and_project"`.
- [ ] `alembic upgrade head` legt `document` und
  `document_version` an. `alembic downgrade -1` entfernt sie
  rückstandsfrei.
- [ ] CHECK- und UNIQUE-Constraints sind im Schema verankert,
  insbesondere
  `UNIQUE (workpackage_id, slug)` und
  `UNIQUE (document_id, version_number)`.

### Storage

- [ ] `Storage`-Protocol in `ref4ep/storage/__init__.py`.
- [ ] `LocalFileStorage` in `ref4ep/storage/local.py` schreibt
  unter `REF4EP_STORAGE_DIR` mit Pfad-Schema
  `documents/{document_id}/{version_id}.bin`.
- [ ] `put_stream` berechnet SHA-256 und Größe streamend.
- [ ] Pfad-Traversal-Schutz und Storage-Key-Regex aktiv.
- [ ] **Kein** statischer Mount auf `REF4EP_STORAGE_DIR`.

### Datenmodell und Versionierung

- [ ] Modelle `Document` und `DocumentVersion` in
  `ref4ep/domain/models.py` mit Relationen.
- [ ] `version_number` wird **server-seitig** vergeben; Client-
  Werte werden ignoriert.
- [ ] `change_note` ist Pflicht bei jedem Upload, mind. 5 Zeichen.
- [ ] SHA-256, MIME, Size, Originalname werden in
  `document_version` persistiert.
- [ ] Identische Inhalte erlaubt; Antwort enthält Warnung
  `duplicate_content_of_v<n>`.

### API

- [ ] Endpunkte aus §9 implementiert und über Pydantic-Schemas
  typisiert.
- [ ] Multipart-Upload mit `Form()`-Feldern und `UploadFile`.
- [ ] Streaming-Download über `StreamingResponse`,
  `Content-Disposition: attachment`,
  `X-Content-Type-Options: nosniff`.
- [ ] CSRF-Pflicht bei allen schreibenden Endpunkten.
- [ ] Generische 404 statt 403 für nicht-sichtbare Dokumente.
- [ ] 413 bei Größenüberschreitung, 415 bei nicht erlaubtem MIME,
  422 bei kurzer `change_note`.

### Berechtigungen

- [ ] `can_read_document` und `can_write_document` in
  `services/permissions.py` ergänzt und in den Routen verwendet.
- [ ] Anonyme Aufrufe auf `/api/documents/...` → 401.
- [ ] Eingeloggte Nicht-Mitglieder ohne Admin → 404 für
  Workpackage-Inhalte des fremden WPs.

### Web (SPA-Erweiterung)

- [ ] `workpackage_detail.js` zeigt die Dokumentenliste des WPs.
- [ ] `document_detail.js` zeigt Metadaten und alle Versionen.
- [ ] Upload-Dialog mit Pflicht-`change_note` (Mindestlänge im
  Frontend kommuniziert).
- [ ] „Metadaten bearbeiten" funktioniert für
  `title`, `document_type`, `deliverable_code`.
- [ ] **Keine** öffentliche UI-Komponente, die Sprint-2-Dokumente
  öffentlich anzeigt.

### Tests und Qualität

- [ ] Alle Tests aus §12 vorhanden und grün.
- [ ] Coverage über `ref4ep/services/`, `ref4ep/storage/` und
  `ref4ep/api/routes/documents*` ≥ 80 %.
- [ ] `ruff check` und `ruff format --check` grün.
- [ ] CI läuft sowohl gegen SQLite als auch PostgreSQL grün.

### Was Sprint 2 explizit **nicht** prüft

- Kein Status-Workflow, kein `release()`, kein `set_visibility()`.
- Kein Audit-Log.
- Keine öffentliche Download-Bibliothek.
- Kein Soft-Delete-Endpunkt.
- Keine S3-/MinIO-Implementierung.

Diese Punkte sind Sprint 3 und 4 zugeordnet.
