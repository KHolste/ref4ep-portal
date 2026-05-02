# Sprint 0 – Umsetzungsplan: technisches Grundgerüst

Dieser Plan konkretisiert den ersten Sprint aus
`docs/mvp_specification.md` §12. Er beschreibt verbindlich, **was**
angelegt wird und **wofür** es da ist — ohne den Code selbst auszu-
formulieren. Die eigentliche Implementierung erfolgt in einem
separaten Schritt.

Zentrale Festlegungen aus §10/§12 der MVP-Spezifikation, die hier
gelten:

- FastAPI + statisch ausgeliefertes HTML/CSS + Vanilla-JavaScript.
- **Kein** Node, **kein** npm, **keine** Frontend-Build-Kette.
- SQLite als lokaler Default, konfigurierbar über `REF4EP_DATABASE_URL`.
- Alembic ab dem ersten Modell.
- Public-Zone via Jinja2-Templates serverseitig gerendert.
- Interne SPA-Shell vorbereitet, aber leer.

---

## 1. Ziel von Sprint 0

Sprint 0 liefert das **lauffähige Skelett** des Ref4EP-Portals **ohne
fachliche Logik**. Am Ende muss gelten:

- `pip install -e ".[dev]"` installiert das Backend-Paket fehlerfrei.
- `alembic upgrade head` läuft gegen die lokale SQLite-Datei ohne
  Fehler (eine leere Baseline-Revision existiert).
- `uvicorn ref4ep.api.app:app --reload` startet auf
  `http://localhost:8000`.
- `GET /api/health` antwortet mit HTTP 200 und führt einen DB-Ping aus.
- `GET /`, `GET /legal/imprint`, `GET /legal/privacy` rendern
  Platzhalter-Seiten (Deutsch).
- `GET /portal/` liefert die leere SPA-Shell (`web/index.html`).
- `pytest` läuft grün; `ruff check` meldet keine Fehler.
- `ref4ep-admin --help` und `ref4ep-admin seed --from antrag` sind als
  Stubs aufrufbar.

Sprint 0 implementiert **noch keine** Domänen-Modelle, Authentifizierung,
Berechtigungen, Storage-Logik, Audit oder fachliche Routen. Diese
Punkte sind explizit Sprint 1+.

---

## 2. Dateien und Ordner, die angelegt werden

### Vollständiger Soll-Baum

```
ref4ep-portal/
├── .gitignore
├── README.md
├── data/                                # gitignored (außer .gitkeep)
│   └── .gitkeep
├── docs/
│   ├── reference_analysis.md            # bereits vorhanden
│   ├── mvp_specification.md             # bereits vorhanden
│   └── sprint0_implementation_plan.md   # diese Datei
├── infra/
│   ├── nginx/
│   │   └── .gitkeep
│   └── systemd/
│       └── .gitkeep
├── .github/
│   └── workflows/
│       └── ci.yml                       # CI-Konfiguration (optional)
└── backend/
    ├── pyproject.toml
    ├── README.md                        # kurzer Backend-Quickstart
    ├── alembic.ini
    ├── alembic/
    │   ├── env.py
    │   ├── script.py.mako
    │   └── versions/
    │       └── 0001_baseline.py         # leere Baseline-Revision
    ├── src/
    │   └── ref4ep/
    │       ├── __init__.py              # __version__ = "0.0.1"
    │       ├── api/
    │       │   ├── __init__.py
    │       │   ├── app.py               # create_app(), Singleton-App
    │       │   ├── config.py            # Settings via pydantic-settings
    │       │   ├── deps.py              # get_settings, get_engine, get_session (Stubs)
    │       │   ├── routes/
    │       │   │   ├── __init__.py
    │       │   │   ├── health.py        # GET /api/health
    │       │   │   └── public_pages.py  # GET /, /legal/*
    │       │   ├── schemas/
    │       │   │   └── __init__.py      # leer
    │       │   └── middleware/
    │       │       └── __init__.py      # leer
    │       ├── domain/
    │       │   ├── __init__.py
    │       │   └── base.py              # SQLAlchemy DeclarativeBase
    │       ├── services/
    │       │   └── __init__.py          # leer
    │       ├── storage/
    │       │   └── __init__.py          # leer
    │       ├── cli/
    │       │   ├── __init__.py
    │       │   └── admin.py             # ref4ep-admin Entry Point
    │       ├── web/
    │       │   ├── index.html           # SPA-Shell, Platzhalter
    │       │   ├── app.js               # leerer JS-Router
    │       │   ├── common.js            # leer, dokumentierter Platzhalter
    │       │   ├── style.css            # CSS-Reset + Grundlayout
    │       │   └── modules/
    │       │       └── .gitkeep
    │       ├── templates/
    │       │   ├── _base.html           # gemeinsames Layout
    │       │   ├── public/
    │       │   │   └── home.html        # Projektsteckbrief-Platzhalter
    │       │   └── legal/
    │       │       ├── imprint.html
    │       │       └── privacy.html
    │       └── static/
    │           ├── style.css            # Public-Zone-CSS
    │           ├── favicon.ico          # Platzhalter
    │           └── images/
    │               └── .gitkeep
    └── tests/
        ├── __init__.py
        ├── conftest.py
        ├── test_health.py
        ├── test_public_pages.py
        ├── test_spa_shell.py
        ├── test_migrations.py
        └── test_cli.py
```

### `.gitignore`-Inhalt (Mindestumfang)

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/

# Lokale Daten
/data/*
!/data/.gitkeep

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db

# Env
.env
.env.local
```

### Was **nicht** angelegt wird in Sprint 0

- Kein `requirements.txt` (alles über `pyproject.toml`).
- Keine `package.json`, kein `node_modules`.
- Kein `Dockerfile` oder `docker-compose.yml` (Container ist optional
  laut §10, kein DoD-Bestandteil von Sprint 0).
- Keine produktive `nginx`-Konfiguration (nur leerer Ordner als
  Platzhalter).
- Keine SQLAlchemy-Modelle für `partner`/`person`/`workpackage` —
  Sprint 1.

---

## 3. Python-Paketstruktur

Das Distributionspaket heißt **`ref4ep`** und liegt unter
`backend/src/ref4ep/`. Layout-Stil: `src/`-Layout, weil es saubere
Trennung zwischen Quellcode und Repo-Wurzel ergibt und
Test-Imports aus dem installierten Paket erzwingt.

| Subpaket           | Aufgabe                                                               | Zustand am Ende von Sprint 0          |
| ------------------ | --------------------------------------------------------------------- | ------------------------------------- |
| `ref4ep.api`       | FastAPI-App-Factory, Routen, Schemas, Middleware, Dependencies         | App + 2 Routen + Settings vorhanden   |
| `ref4ep.domain`    | SQLAlchemy `Base`, später Modelle und Enums                            | Nur `Base` definiert                  |
| `ref4ep.services`  | Geschäftslogik, Audit-Logger, Permissions                              | Leer (`__init__.py`)                  |
| `ref4ep.storage`   | Storage-Interface + Implementierungen (`LocalFileStorage`, später S3)  | Leer (`__init__.py`)                  |
| `ref4ep.cli`       | Admin-CLI (`ref4ep-admin`)                                             | `argparse`-Skelett mit Subcommand-Stubs |

Web-Assets (`web/`, `templates/`, `static/`) liegen **innerhalb** des
Pakets, damit sie über `importlib.resources` adressiert werden können
und beim `pip install` mitkopiert werden. Sie sind keine Python-Module;
ihre Auslieferung wird über `[tool.setuptools.package-data]` gesteuert
(siehe §4).

Alle `__init__.py` bleiben in Sprint 0 leer, mit Ausnahme von
`ref4ep/__init__.py`, die eine `__version__ = "0.0.1"` exportiert.

---

## 4. `pyproject.toml`-Inhalt (grob)

Build-System: `setuptools`. Begründung: Standard, ausreichend für ein
Backend-Paket dieser Größe, kein zusätzlicher Build-Tool-Dependency-
Layer.

Strukturskizze (verbindlich für die Implementierung):

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "ref4ep"
version = "0.0.1"
description = "Ref4EP-Projektportal — Backend"
readme = "README.md"
requires-python = ">=3.11"
authors = [{ name = "Ref4EP-Konsortium" }]
license = { text = "Proprietär (Konsortium)" }

dependencies = [
  "fastapi>=0.110",
  "uvicorn[standard]>=0.27",
  "sqlalchemy>=2.0",
  "alembic>=1.13",
  "pydantic>=2.6",
  "pydantic-settings>=2.2",
  "jinja2>=3.1",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "pytest-cov>=4.1",
  "httpx>=0.27",
  "ruff>=0.4",
]
postgres = [
  "psycopg[binary]>=3.1",
]

[project.scripts]
ref4ep-admin = "ref4ep.cli.admin:main"

[tool.setuptools]
package-dir = { "" = "src" }

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
ref4ep = [
  "web/**/*",
  "templates/**/*",
  "static/**/*",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP"]
ignore = []

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q --strict-markers"
```

Begründungen für nicht aufgenommene Dependencies in Sprint 0:

- `argon2-cffi`, `itsdangerous`, `python-multipart` — erst Sprint 1
  (Auth, Sessions, Form-Uploads).
- `bleach`, `markdown` — erst Sprint mit Wiki-Modul (post-MVP).
- `psycopg[binary]` — als Optional-Extra `postgres` vorgesehen, damit
  CI ihn ohne Code-Änderung gegen PostgreSQL ergänzen kann.

---

## 5. Konfigurationskonzept

Eine zentrale `Settings`-Klasse in `ref4ep/api/config.py`, basierend
auf `pydantic-settings`. Sie liest **ausschließlich Umgebungsvariablen**
mit Präfix `REF4EP_` und optional eine `.env`-Datei.

Felder und Defaults:

| Feld                    | Env-Variable               | Default                           | In S0 verwendet? |
| ----------------------- | -------------------------- | --------------------------------- | ---------------- |
| `database_url`          | `REF4EP_DATABASE_URL`      | `sqlite:///../data/ref4ep.db`     | **ja**           |
| `session_secret`        | `REF4EP_SESSION_SECRET`    | `""` (leer, in S0 nicht erzwungen)| nein             |
| `storage_dir`           | `REF4EP_STORAGE_DIR`       | `../data/storage`                 | nein             |
| `max_upload_mb`         | `REF4EP_MAX_UPLOAD_MB`     | `100`                             | nein             |
| `public_base_url`       | `REF4EP_PUBLIC_BASE_URL`   | `http://localhost:8000`           | nein             |
| `log_format`            | `REF4EP_LOG_FORMAT`        | `text`                            | nein             |

Implementierungsregeln:

- `Settings` wird durch `get_settings()` mit `lru_cache` als Singleton
  bereitgestellt.
- `database_url` wird sowohl von `api/deps.py` (für die App) als auch
  von `alembic/env.py` (für Migrationen) gelesen — **gleiche Quelle**.
- `storage_dir` wird in Sprint 0 nicht angefasst, aber bei App-Start
  als Pfad geprüft (existieren oder anlegbar). Optional erst Sprint 2.
- `session_secret` wird in Sprint 0 nicht erzwungen; eine Validierung
  mit Pflicht-Mindestlänge wird in Sprint 1 ergänzt.
- Eine Beispiel-`.env.example` liegt unter `backend/.env.example` und
  enthält die obigen Variablen mit Default-Werten als Doku.

`.env`-Lookup-Reihenfolge: Prozessumgebung > `backend/.env` (sofern
vorhanden, gitignored) > Default in Settings.

---

## 6. FastAPI-App-Struktur

### `api/app.py`

Eine `create_app(settings: Settings | None = None) -> FastAPI`-Factory.
Nicht direkt `app = FastAPI()` auf Modul-Ebene, sondern Singleton am
Modulende: `app = create_app()`. Begründung: Tests können mit
abweichenden Settings eine eigene App bauen.

Aufgaben der Factory in Sprint 0:

1. Settings laden.
2. Logger konfigurieren (einfaches `logging.basicConfig`, JSON erst
   später).
3. SQLAlchemy-Engine via `create_engine(settings.database_url,
   future=True)` anlegen und in `app.state.engine` ablegen.
4. Jinja2-`Templates`-Objekt anlegen mit Verzeichnis aus
   `importlib.resources.files("ref4ep") / "templates"` und in
   `app.state.templates` ablegen.
5. Routen registrieren:
   - `app.include_router(health_router)` aus `routes/health.py`
   - `app.include_router(public_pages_router)` aus
     `routes/public_pages.py`
6. Statische Mounts:
   - `/static` → `ref4ep/static/` (für Public-Zone-CSS, Bilder, Favicon)
   - `/portal` → `ref4ep/web/` mit `html=True`, sodass `/portal/`
     die `index.html` liefert. Für unbekannte Sub-Pfade unter
     `/portal/...` wird in Sprint 1+ ein Fallback ergänzt; in Sprint 0
     reicht das Standard-Verhalten von `StaticFiles`.

### `api/routes/health.py`

Ein einziger Endpoint:

- `GET /api/health` → `{"status": "ok", "db": "ok" | "error",
  "version": "<__version__>"}`.
- DB-Ping: `with engine.connect() as conn: conn.execute(text("SELECT
  1"))`. Bei Ausnahme `db = "error"` und HTTP 200 (Health-Endpoint
  selbst antwortet immer; `db`-Status reflektiert den Befund).

### `api/routes/public_pages.py`

Drei Endpoints, alle Jinja2-gerendert:

- `GET /` → `templates/public/home.html`
- `GET /legal/imprint` → `templates/legal/imprint.html`
- `GET /legal/privacy` → `templates/legal/privacy.html`

Templates erhalten ein minimales Kontext-Dict (`{"title": ...,
"version": app_version}`).

### `api/deps.py`

In Sprint 0 nur:

- `get_settings()` → cached Singleton.
- `get_engine(request)` → liest `request.app.state.engine`.

Session-Maker, Auth-Dependency, CSRF — Sprint 1.

### Was **nicht** in Sprint 0

- Kein CORS-Setup (kein externes Frontend, also nicht nötig).
- Keine Middleware (RequestID, Logging) — Sprint 1.
- Keine Exception-Handler über das FastAPI-Default hinaus.
- Keine Authentifizierung.

---

## 7. Statische Webstruktur

### `web/index.html` (SPA-Shell)

Minimales HTML-Dokument mit:

- `<!doctype html>`, `<html lang="de">`.
- `<title>Ref4EP-Portal</title>`.
- Link auf `/portal/style.css`.
- Container `<div id="app">Bitte anmelden …</div>` als Platzhalter.
- `<script type="module" src="/portal/app.js"></script>`.
- HTML-Kommentar, der erklärt, dass diese Datei in Sprint 1 zur
  echten Login/Cockpit-Shell ausgebaut wird.

### `web/app.js`

Skelett mit dokumentierten Stellen für späteren Code:

- Kommentar-Block oben: Aufgabe der Datei (SPA-Router, Auth-State,
  Modul-Loader).
- `// TODO Sprint 1: Login-Form abschicken, Session-Status prüfen,
  Modul-Routing per History API.`
- `console.info("Ref4EP-Portal — Sprint-0-Skelett geladen.");` als
  Lebenszeichen für die manuelle Prüfung.

### `web/common.js`

Komplett leer mit Header-Kommentar:
„Wiederverwendbare Helfer — wird ab Sprint 1 mit Fetch-Wrapper,
CSRF-Token-Handling und kleinen DOM-Utilities befüllt."

### `web/style.css`

Einfacher CSS-Reset (margin, box-sizing, font-family) und ein paar
Grundregeln für `body`, `header`, `main`. Maximal 30 Zeilen. **Kein**
Tailwind, **kein** SCSS.

### `templates/_base.html`

Gemeinsames Layout für die Public-Zone-Templates: `<!doctype html>`,
`<head>` mit `<title>{% block title %}{% endblock %} — Ref4EP</title>`,
Link auf `/static/style.css`, einfache Navigation
(`Projekt | Downloads | Impressum | Datenschutz`), `<main>`-Block,
schlichter Footer.

### `templates/public/home.html`

Erbt von `_base.html`. Inhalt: ein deutscher Platzhaltertext, der
explizit benennt, dass dies die spätere Projektsteckbrief-Seite ist.
Etwa zwei Absätze, kein Lorem ipsum.

### `templates/legal/imprint.html` und `privacy.html`

Erben von `_base.html`. Inhalt: deutscher Platzhalter mit dem Hinweis,
dass die endgültigen Texte in Sprint 4 (vor Go-Live) durch den
Verantwortlichen einzutragen sind.

### `static/style.css`

Public-Zone-CSS mit lesbarer Typografie, max. 600 px Breite zentriert,
schlichter Header/Footer. Maximal 80 Zeilen. **Keine** externen
Schriften (DSGVO-freundlich, kein Google Fonts).

### `static/favicon.ico`

Echter Platzhalter (z. B. einfarbiges Quadrat-ICO aus einem
Generator). Wird in Sprint 4 durch das offizielle Projekt-Favicon
ersetzt.

---

## 8. Datenbank- und Alembic-Grundstruktur

### `domain/base.py`

Definiert den SQLAlchemy-Basis-Klassentyp:

```python
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
```

In Sprint 0 sind hier **keine** Modellklassen. Nur `Base`.

### `alembic.ini`

Standard-Alembic-Konfiguration mit folgenden Anpassungen:

- `script_location = alembic`
- `sqlalchemy.url` wird **nicht** in `alembic.ini` hinterlegt, sondern
  zur Laufzeit durch `env.py` aus `Settings.database_url` gelesen.
  Begründung: Eine Quelle der Wahrheit für die DB-URL.
- `file_template = %%(year)d%%(month).2d%%(day).2d_%%(rev)s_%%(slug)s`
  (chronologisch lesbar).

### `alembic/env.py`

Implementierung folgt dem Standard-Template, mit einer Anpassung im
Import-Block:

- `from ref4ep.api.config import get_settings`
- `from ref4ep.domain.base import Base`
- `target_metadata = Base.metadata`
- `config.set_main_option("sqlalchemy.url", get_settings().database_url)`

Online- und Offline-Mode bleiben Standard.

### `alembic/versions/0001_baseline.py`

Eine **leere** Revision:

- `revision = "0001_baseline"`
- `down_revision = None`
- `def upgrade(): pass`
- `def downgrade(): pass`

Zweck: Sicherstellen, dass `alembic upgrade head` bereits in Sprint 0
funktioniert und dass eine konsistente Revisions-Kette existiert,
bevor Sprint 1 die ersten Tabellen ergänzt.

### Sprint-0-Verbot

In Sprint 0 werden **keine** Tabellen migriert. `Base.metadata` ist
leer. Die Datei `data/ref4ep.db` entsteht erst beim ersten
`alembic upgrade head`-Lauf und enthält dann nur die
`alembic_version`-Tabelle.

---

## 9. CLI-Grundstruktur

### Entry Point

In `pyproject.toml` definiert:
`ref4ep-admin = "ref4ep.cli.admin:main"`.

### `cli/admin.py`

Implementierung mit `argparse` (keine zusätzliche Dependency):

```
ref4ep-admin <subcommand> [args]
```

Subcommands in Sprint 0 (alle als Stubs mit klarer Ausgabe):

| Subcommand                    | Verhalten in Sprint 0                                                  |
| ----------------------------- | ---------------------------------------------------------------------- |
| `ref4ep-admin --help`         | argparse-Standardhilfe, listet alle Subcommands.                       |
| `ref4ep-admin version`        | Druckt `ref4ep <__version__>` und `python <sys.version>`.              |
| `ref4ep-admin seed --from antrag` | Druckt: „Sprint-0-Stub: Seed-Logik wird in Sprint 1 implementiert. Quelldatei (geplant): backend/src/ref4ep/cli/seed_data/antrag_initial.yaml" — Exit 0. |
| `ref4ep-admin seed --help`    | argparse-Hilfe für Seed-Subcommand mit Argument `--from {antrag}`.     |

Sprint-1-Vorbereitung (nur als Kommentar im Quelltext, **nicht** als
funktionaler Code):

- `users create | reset-password | enable | disable | set-role`
- `partners create`
- `workpackages create`
- `memberships add`

### `cli/seed_data/`

In Sprint 0 **nicht** anlegen. Erst, wenn Sprint 1 den Seed
tatsächlich ausliest, wandert die `antrag_initial.yaml` (Inhalt aus
§13 der MVP-Spezifikation) dorthin.

### Verhalten bei Fehlern

- Unbekanntes Subcommand → argparse zeigt Hilfe, Exit 2.
- Fehlende `REF4EP_DATABASE_URL` ist in Sprint 0 unkritisch, da kein
  Subcommand auf die DB zugreift.

---

## 10. Tests für Sprint 0

Test-Framework: `pytest` mit `httpx`-basiertem FastAPI-Testclient.
Testdatenbank: in-memory SQLite (`sqlite:///:memory:` oder
temporäres File-DB pro Testlauf).

### `tests/conftest.py`

Fixtures:

- `settings` — überschreibt `database_url` auf eine temporäre SQLite-
  Datei pro Test (Pytest `tmp_path`-Fixture).
- `app` — baut eine frische FastAPI-App via `create_app(settings)`.
- `client` — `httpx.Client(app=app, base_url="http://testserver")`
  oder `fastapi.testclient.TestClient(app)`.

### `tests/test_health.py`

| Testfall                              | Erwartung                                              |
| ------------------------------------- | ------------------------------------------------------ |
| `GET /api/health` antwortet 200       | Status 200, JSON enthält `status`, `db`, `version`.    |
| DB-Ping erfolgt gegen Test-DB         | `db == "ok"` bei valider Test-Settings.                |
| Health-Endpoint hat keine Auth-Pflicht| Aufruf ohne Cookie/Header funktioniert.                |

### `tests/test_public_pages.py`

| Testfall                       | Erwartung                                                  |
| ------------------------------ | ---------------------------------------------------------- |
| `GET /`                        | 200, `Content-Type: text/html`, enthält Wort „Ref4EP".     |
| `GET /legal/imprint`           | 200, enthält Wort „Impressum".                             |
| `GET /legal/privacy`           | 200, enthält Wort „Datenschutz".                           |
| Public-Pages laden `/static/style.css` | Antwort 200 für die CSS-Datei.                     |

### `tests/test_spa_shell.py`

| Testfall                       | Erwartung                                                  |
| ------------------------------ | ---------------------------------------------------------- |
| `GET /portal/`                 | 200, `text/html`, liefert `index.html`.                    |
| `GET /portal/app.js`           | 200, `application/javascript`.                             |
| `GET /portal/style.css`        | 200, `text/css`.                                           |

### `tests/test_migrations.py`

| Testfall                                       | Erwartung                                          |
| ---------------------------------------------- | -------------------------------------------------- |
| `alembic upgrade head` gegen leere SQLite-DB   | exit 0, Tabelle `alembic_version` existiert.       |
| Aktuelle Head-Revision == `0001_baseline`      | `script.get_current_head()` liefert `"0001_baseline"`. |
| `alembic downgrade base` ist möglich           | Reversibilität der Baseline-Revision.              |

Implementierung über `alembic.config.Config` und `alembic.command`-API,
**nicht** über `subprocess`. Begründung: deterministisch, schneller,
keine Pfadabhängigkeiten in CI.

### `tests/test_cli.py`

| Testfall                                            | Erwartung                                          |
| --------------------------------------------------- | -------------------------------------------------- |
| `ref4ep-admin --help` (subprocess)                  | exit 0, stdout enthält `seed`, `version`.          |
| `ref4ep-admin version`                              | exit 0, stdout enthält `0.0.1`.                    |
| `ref4ep-admin seed --from antrag`                   | exit 0, stdout enthält „Sprint-0-Stub".            |
| `ref4ep-admin seed --from etwas-unbekanntes`        | exit ≠ 0, argparse meldet ungültigen Wert.         |

CLI-Tests dürfen `subprocess` benutzen, weil der Entry-Point im
installierten Paket validiert werden soll.

### Coverage-Ziel

Kein hartes Coverage-Ziel in Sprint 0 (zu wenig Code). Aber die
Test-Suite muss die oben genannten 14 Fälle vollständig abdecken.

---

## 11. Lokale Startbefehle

Alle Befehle gelten für eine bash-/zsh-Shell auf dem Entwicklungs-
rechner. Auf Windows entsprechend `.\.venv\Scripts\Activate.ps1`.

### Einmalige Einrichtung

```bash
cd ref4ep-portal/backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Datenbank vorbereiten

```bash
# Default: sqlite:///../data/ref4ep.db (relativ zu backend/, also Repo-Wurzel/data)
mkdir -p ../data
alembic upgrade head
```

### Entwicklungsserver starten

```bash
uvicorn ref4ep.api.app:app --reload --port 8000
```

Browser-Prüfungen:

- `http://localhost:8000/` → Projektsteckbrief-Platzhalter
- `http://localhost:8000/legal/imprint`
- `http://localhost:8000/legal/privacy`
- `http://localhost:8000/portal/` → leere SPA-Shell
- `http://localhost:8000/api/health` → JSON mit `db: ok`

### Tests, Linter, CLI

```bash
pytest                             # alle Tests
pytest -k health                   # gezielter Test
ruff check src tests               # Lint-Prüfung
ruff format src tests              # Formatierung anwenden
ref4ep-admin --help                # CLI-Hilfe
ref4ep-admin version
ref4ep-admin seed --from antrag    # Stub
```

### Optional: PostgreSQL gegenprobe lokal

Nicht Teil der DoD, aber empfohlen, um die Dialektneutralität zu
verifizieren:

```bash
pip install -e ".[dev,postgres]"
export REF4EP_DATABASE_URL="postgresql+psycopg://ref4ep:ref4ep@localhost:5432/ref4ep"
alembic upgrade head
pytest
```

---

## 12. Definition of Done

Sprint 0 ist abgeschlossen, wenn **alle** folgenden Punkte erfüllt
sind. Die Reihenfolge entspricht dem Prüfablauf.

### Repo-Struktur

- [ ] Soll-Baum aus §2 vollständig vorhanden, inkl. `.gitignore`,
  `pyproject.toml`, `alembic.ini`, `alembic/env.py`,
  `alembic/versions/0001_baseline.py`.
- [ ] `data/` ist gitignored bis auf `.gitkeep`.
- [ ] Keine `package.json`, kein `node_modules`, kein Frontend-Build.

### Installation

- [ ] `pip install -e ".[dev]"` läuft fehlerfrei in einem frischen
  venv.
- [ ] `ref4ep` ist als Distribution importierbar
  (`python -c "import ref4ep; print(ref4ep.__version__)"` druckt
  `0.0.1`).

### Konfiguration

- [ ] `Settings` lädt `REF4EP_DATABASE_URL` aus der Umgebung.
- [ ] Default `sqlite:///../data/ref4ep.db` greift, wenn keine
  Variable gesetzt ist (Pfad relativ zum Working-Directory `backend/`,
  trifft also die Repo-Wurzel-`data/`).
- [ ] `.env.example` existiert mit allen Variablen aus §5.

### Datenbank und Migration

- [ ] `alembic upgrade head` erzeugt `data/ref4ep.db` mit Tabelle
  `alembic_version`, Inhalt = `0001_baseline`.
- [ ] `alembic downgrade base` läuft fehlerfrei.
- [ ] `Base.metadata.tables` ist leer (außerhalb der Alembic-eigenen
  Tabelle).

### FastAPI-App

- [ ] `uvicorn ref4ep.api.app:app` startet ohne Exceptions.
- [ ] `GET /api/health` antwortet 200 mit `{"status": "ok",
  "db": "ok", "version": "0.0.1"}`.
- [ ] `GET /` rendert `templates/public/home.html` mit deutschem
  Platzhaltertext, der das Wort „Ref4EP" enthält.
- [ ] `GET /legal/imprint` und `GET /legal/privacy` antworten 200 mit
  je einem Platzhaltertext.
- [ ] `GET /portal/` liefert die SPA-Shell `web/index.html`.
- [ ] `GET /portal/app.js`, `/portal/style.css`,
  `/static/style.css` werden mit korrektem MIME-Typ ausgeliefert.

### CLI

- [ ] `ref4ep-admin --help` listet die Subcommands `version` und
  `seed`.
- [ ] `ref4ep-admin version` druckt Versions- und Python-Info.
- [ ] `ref4ep-admin seed --from antrag` druckt klar erkennbar einen
  Sprint-0-Stub-Hinweis und Exit 0.

### Tests und Qualität

- [ ] `pytest` läuft grün, alle 14 Testfälle aus §10 vorhanden und
  bestanden.
- [ ] `ruff check src tests` meldet 0 Fehler.
- [ ] `ruff format --check src tests` meldet keine offenen
  Formatierungen.

### CI (optional, aber empfohlen)

- [ ] `.github/workflows/ci.yml` existiert und führt mindestens aus:
  - `pip install -e ".[dev]"`
  - `ruff check`
  - `pytest`
  - `alembic upgrade head` (gegen SQLite)
- [ ] Optional zusätzlicher CI-Job mit PostgreSQL-Service-Container,
  der dieselbe Suite gegen `postgres://...` ausführt.

### Dokumentation

- [ ] `backend/README.md` enthält die Quickstart-Befehle aus §11
  (Einrichtung, Migration, Server, Tests, CLI).
- [ ] Repo-Wurzel-`README.md` verweist auf
  `docs/mvp_specification.md` und `docs/sprint0_implementation_plan.md`.

### Was Sprint 0 explizit **nicht** prüft

- Keine Domain-Modelle, keine Auth, keine Berechtigungen, kein
  Audit-Log, kein Storage, kein Seed, keine fachlichen Routen.
- Keine produktive `nginx`-Konfiguration.
- Kein Deployment, kein Docker-Compose, kein systemd.

Diese Punkte sind Sprint 1 (Identität) und folgenden zugeordnet.
