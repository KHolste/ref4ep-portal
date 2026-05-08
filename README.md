# Ref4EP-Portal

Webbasiertes Projektportal für das DLR-geförderte Verbundprojekt
**Ref4EP** (Referenzdiagnostik für elektrische Raumfahrtantriebe). Das
Portal bündelt Workpackages, Partner, Personen, Dokumente, Meetings,
Aufgaben, Meilensteine, Testkampagnen, eine Gantt-Ansicht und ein
Audit-Log in einer einzigen internen Anwendung.

## Aktueller Stand

Funktionsfähiges internes Web-MVP mit erweitertem Projekt-, Dokumenten-,
Kampagnen- und Zeitplanmanagement. Die Plattform wird kontinuierlich in
Feature-Patches weiterentwickelt; die Datenbank hat aktuell den
Migrationsstand `0016_test_campaign_notes` (Block 0029).

Hinweis: Es handelt sich um ein internes Projektportal des
Konsortiums, kein fertiges kommerzielles Produkt.

## Funktionsumfang

Backend / Persistenz

- FastAPI-Backend mit ASGI-Entrypoint `ref4ep.api.asgi:app`
- SQLAlchemy + Alembic, dialektneutrale Schemata
- SQLite als Standard-Backend; PostgreSQL ist über
  `REF4EP_DATABASE_URL` möglich und Teil der Test-Gegenprobe
  (`backend/README.md` → „PostgreSQL-Gegenprobe")
- Lokales Datei-Storage (`Storage`-Abstraktion) mit MIME-Whitelist und
  größenbegrenztem Streaming-Upload
- HMAC-signierte Session-Cookies, CSRF-Schutz, Login-/Passwort-Wechsel-
  Workflows, Rollen `admin` / `member` und WP-Rollen `wp_lead` /
  `wp_member`
- Append-only Audit-Log für jede schreibende Aktion

Fachliche Module

- **Konsortium** — Partner mit erweiterten Stammdaten, Kontaktpersonen
  und Sichtbarkeit (intern/öffentlich vorgesehen)
- **Personen** — Konsortiumsangehörige mit Login, Plattformrolle,
  WP-Mitgliedschaften und Pflicht-Passwortwechsel beim Erstlogin
- **Workpackages** — zweistufige WP-Hierarchie, optionale Zeitplanfelder
  `start_date` / `end_date`, Cockpit-Status, WP-Detailseiten
- **Meilensteine** — Status-Lebenszyklus mit Health-Berechnung,
  übergreifende Meilensteine ohne WP-Zuordnung möglich
- **Meetings** — Kategorien (Konsortium, Jour fixe, WP-Treffen,
  Review …), Status-Lifecycle, Teilnehmende, Beschlüsse, Aktionen,
  Dokumentanhänge, Druckansicht
- **Aufgaben** — eigenständige Aktions-Liste mit Zuweisung und Status
- **Dokumentenregister** — versionierte Dokumente, Status-Lifecycle
  (`draft` → `in_review` → `released`), Sichtbarkeit
  (`workpackage` / `internal` / `public`), Datei-Upload mit
  MIME-Whitelist und Versionsnotiz, Dokumentkommentare auf
  Versionsebene
- **Öffentliche Dokumentbibliothek** — schreibgeschützte Liste der als
  `public` freigegebenen Dokumente
- **Testkampagnen** — Kategorien, Status-Lifecycle, Teilnehmende mit
  Rollen, Verknüpfung zu Workpackages und Dokumenten.
  - **Foto-Upload** (PNG/JPEG, eigene Tabelle `test_campaign_photo`,
    inline-Streaming-Download, Soft-Delete) — Patch 0028.
  - **Kampagnennotizen** als gemeinsame Arbeitsnotizen für Ideen,
    Beobachtungen und offene Fragen. Bewusst kein formales Laborbuch:
    keine Versionierung, kein Review-/Release-Lifecycle, kein Titel —
    nur ein Markdown-Body mit Autor und Soft-Delete (eigene Tabelle
    `test_campaign_note`) — Patch 0029.
- **Cockpit / Dashboard** — Projekt-Cockpit mit Ampel-Dashboard,
  WP-Cockpit, „Mein Cockpit", Lead-Übersichten
- **Gantt-Timeline** — Workpackages, Aggregate, Meilensteine und
  Testkampagnen in einer einzigen Zeitleistenansicht
- **Aktivitäts- und Auditansichten** — Audit-Log und Aktivitätsstrom
- **Admin-/Systemstatus** — Partner-, Personen- und
  Mitgliedschaftsverwaltung sowie Storage-/Upload-Diagnose

Frontend

- Vanilla-JS-SPA ohne npm/Build-Step, ausgeliefert vom Backend
- Sicherer DOM-Helfer (`appendChildren`), gemeinsamer API-Client mit
  CSRF-Header und 401-Redirect
- Eigener Mini-Markdown-Renderer mit zentralem HTML-Escape (für die
  Kampagnennotizen)
- Notiz-Editor mit einfacher Formatierungsleiste (Fett, Kursiv, Code,
  Überschrift, Liste, Zitat, Tabelle, Link) und Live-Vorschau —
  Markdown-Kenntnisse sind nicht erforderlich (Patch 0031 / 0031.1)

## Repository-Aufbau

| Pfad        | Inhalt                                                       |
| ----------- | ------------------------------------------------------------ |
| `backend/`  | Python-Backend, REST-API, statisch ausgeliefertes Frontend, Alembic-Migrationen, Tests |
| `data/`     | Lokale SQLite-DB und Storage-Verzeichnis (gitignored)        |
| `docs/`     | Aktive Betriebsdoku und historische Planungsdokumente        |
| `infra/`    | Beispielkonfigurationen für Reverse-Proxy und systemd-Units  |

## Dokumentation

Aktuelle Doku — diese Dokumente werden gepflegt:

- [`backend/README.md`](backend/README.md) — Schnellstart, lokale
  Entwicklung, Konfiguration, Tests
- [`docs/server_operations.md`](docs/server_operations.md) —
  Serverbetrieb, Update- und Backup-Ablauf für `portal.ref4ep.de`
- [`docs/manual_smoke_test.md`](docs/manual_smoke_test.md) — manuelle
  Smoke-Test-Prozedur

Historische Planungsdokumente — Stand zum Zeitpunkt der jeweiligen
Sprint-/Block-Planung; **nicht** der aktuelle Implementierungsstand:

- [`docs/reference_analysis.md`](docs/reference_analysis.md) — frühe
  Analyse des Referenz-Labormanagement-Systems
- [`docs/mvp_specification.md`](docs/mvp_specification.md) —
  ursprüngliche MVP-Spezifikation
- [`docs/sprint0_implementation_plan.md`](docs/sprint0_implementation_plan.md),
  [`docs/sprint1_implementation_plan.md`](docs/sprint1_implementation_plan.md),
  [`docs/sprint2_implementation_plan.md`](docs/sprint2_implementation_plan.md),
  [`docs/sprint3_implementation_plan.md`](docs/sprint3_implementation_plan.md) —
  Sprint-Pläne (Skelett, Identität/WP/Storage, Dokumente,
  Audit + Release-Workflow)
- [`docs/admin_ui_implementation_plan.md`](docs/admin_ui_implementation_plan.md),
  [`docs/next_steps.md`](docs/next_steps.md) — frühere Planungsnotizen

## Schnellstart

Siehe [`backend/README.md`](backend/README.md). In Kurzform:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
mkdir -p ../data
alembic upgrade head
uvicorn ref4ep.api.asgi:app --reload --port 8000
```

## Qualitätssicherung

- `ruff check src tests` und `ruff format --check src tests`
- `pytest` mit Coverage-Gate (≥ 85 %)
- Alembic-Migrationen werden in der Test-Suite up- und downgegradet
- Stand Patch 0031.1: ca. 1010 Tests, Coverage ~ 91 %

Details und Befehle in `backend/README.md`.

## Doku-Pflege

Bei jedem künftigen Feature-Patch ist zu prüfen, ob diese README, die
`backend/README.md` oder `docs/server_operations.md` angepasst werden
müssen. Änderungen am sichtbaren Funktionsumfang, am Setup, am Betrieb,
am Datenmodell oder am Deployment-Ablauf werden im selben Patch oder in
einem unmittelbar folgenden Dokumentationspatch dokumentiert. Historische
Planungsdokumente in `docs/` (MVP-Spezifikation, Sprint-Pläne) werden
**nicht** rückwirkend angepasst — sie bleiben als Planungsstand erhalten.
