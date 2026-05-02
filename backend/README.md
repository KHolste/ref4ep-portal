# Ref4EP-Portal — Backend

Python-Backend für das Ref4EP-Projektportal. FastAPI + SQLAlchemy +
Alembic, statisch ausgeliefertes HTML/CSS + Vanilla-JS für die UI.
Lokaler Default: SQLite. Konfigurierbar über `REF4EP_DATABASE_URL`.

Stand: Sprint 0 (Skelett).

## Schnellstart

```bash
cd backend
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
mkdir -p ../data
alembic upgrade head
uvicorn ref4ep.api.app:app --reload --port 8000
```

Dann im Browser:

- http://localhost:8000/ — Projektsteckbrief (Platzhalter)
- http://localhost:8000/legal/imprint — Impressum (Platzhalter)
- http://localhost:8000/legal/privacy — Datenschutz (Platzhalter)
- http://localhost:8000/portal/ — leere SPA-Shell (Sprint 1+)
- http://localhost:8000/api/health — JSON-Health-Endpoint

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
| `REF4EP_SESSION_SECRET` | leer (Sprint 1 wird Pflicht)       |
| `REF4EP_STORAGE_DIR`    | `../data/storage`                  |
| `REF4EP_MAX_UPLOAD_MB`  | `100`                              |
| `REF4EP_PUBLIC_BASE_URL`| `http://localhost:8000`            |
| `REF4EP_LOG_FORMAT`     | `text`                             |

## PostgreSQL-Gegenprobe (optional)

```bash
pip install -e ".[dev,postgres]"
export REF4EP_DATABASE_URL="postgresql+psycopg://ref4ep:ref4ep@localhost:5432/ref4ep"
alembic upgrade head
pytest
```

## Was Sprint 0 nicht enthält

Keine Domain-Modelle, keine Authentifizierung, keine Berechtigungen,
kein Storage, kein Audit-Log, kein Seed. Siehe
`docs/sprint0_implementation_plan.md` und
`docs/mvp_specification.md` §12.
