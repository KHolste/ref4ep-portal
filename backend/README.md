# Ref4EP-Portal — Backend

Python-Backend für das Ref4EP-Projektportal. FastAPI + SQLAlchemy +
Alembic, statisch ausgeliefertes HTML/CSS + Vanilla-JS für die UI.
Lokaler Default: SQLite. Konfigurierbar über `REF4EP_DATABASE_URL`.

Eine Übersicht des aktuellen Funktionsumfangs steht in der
[Repo-README](../README.md).

## Schnellstart

```bash
cd backend
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
mkdir -p ../data
alembic upgrade head
uvicorn ref4ep.api.asgi:app --reload --port 8000
```

Dann im Browser (Auswahl):

- http://localhost:8000/ — öffentlicher Projektsteckbrief
- http://localhost:8000/legal/imprint — Impressum
- http://localhost:8000/legal/privacy — Datenschutzhinweis
- http://localhost:8000/portal/ — internes Portal (Login erforderlich)
- http://localhost:8000/api/health — JSON-Health-Endpoint
- http://localhost:8000/openapi.json — OpenAPI-Schema

Initialer Admin-Account und Seed siehe `ref4ep-admin --help`.

## Tests, Linter, CLI

```bash
pytest                             # Test-Suite
ruff check src tests               # Lint
ruff format --check src tests      # Formatierung prüfen
ref4ep-admin --help                # CLI-Hilfe
ref4ep-admin version
ref4ep-admin seed --from antrag    # Stub
```

## Konfiguration

Alle Variablen tragen den Präfix `REF4EP_`. Siehe `.env.example`.

| Variable                | Default                            |
| ----------------------- | ---------------------------------- |
| `REF4EP_DATABASE_URL`   | `sqlite:///../data/ref4ep.db`      |
| `REF4EP_SESSION_SECRET` | **Pflicht, ≥ 32 Zeichen**          |
| `REF4EP_COOKIE_SECURE`  | `true` (HTTPS-only Session-Cookie) |
| `REF4EP_STORAGE_DIR`    | `../data/storage`                  |
| `REF4EP_MAX_UPLOAD_MB`  | `100`                              |
| `REF4EP_PUBLIC_BASE_URL`| `http://localhost:8000`            |
| `REF4EP_LOG_FORMAT`     | `text`                             |

`REF4EP_SESSION_SECRET` muss mindestens 32 Zeichen haben — beim Start
ohne gültige Variable schlägt `Settings()` mit klarer Fehlermeldung
fehl. Beispiel: `openssl rand -hex 32`.

`REF4EP_COOKIE_SECURE` darf in der lokalen Entwicklung über
`http://localhost` auf `false` gesetzt werden, weil der Browser
sonst das Session-Cookie nicht speichert. In Production
`true` lassen.

## PostgreSQL-Gegenprobe (optional)

```bash
pip install -e ".[dev,postgres]"
export REF4EP_DATABASE_URL="postgresql+psycopg://ref4ep:ref4ep@localhost:5432/ref4ep"
alembic upgrade head
pytest
```

## Doku-Pflege

Bei Änderungen am sichtbaren Funktionsumfang, am Setup, am Betrieb,
am Datenmodell oder am Deployment-Ablauf: Repo-`README.md`,
diese Backend-`README.md` und ggf. `../docs/server_operations.md`
mit anpassen — siehe Hinweis in der Repo-`README.md`.

Die Sprint- und MVP-Pläne unter `../docs/` (z. B.
`sprint0_implementation_plan.md`, `mvp_specification.md`) sind
**historische Planungsdokumente** zum jeweiligen Sprint-Stand und
spiegeln nicht den aktuellen Implementierungsstand wider.
