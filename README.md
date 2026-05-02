# Ref4EP-Portal

Eigenständiges Projektportal für das DLR-geförderte Forschungsprojekt
Ref4EP (Referenzdiagnostik für elektrische Raumfahrtantriebe).

## Repository-Aufbau

| Pfad                                    | Inhalt                                                       |
| --------------------------------------- | ------------------------------------------------------------ |
| `backend/`                              | Python-Backend (FastAPI + SQLAlchemy + Alembic)              |
| `data/`                                 | Lokale SQLite-DB und Storage-Verzeichnis (gitignored)        |
| `docs/`                                 | Spezifikationen und Pläne                                    |
| `infra/`                                | Beispiel-Konfigurationen für Reverse-Proxy und Service-Units |

## Dokumentation

- [`docs/reference_analysis.md`](docs/reference_analysis.md) — Analyse des Referenz-Labormanagement-Systems.
- [`docs/mvp_specification.md`](docs/mvp_specification.md) — MVP-Spezifikation mit Datenmodell, Routen, Sichtbarkeitsregeln und Sprintplan.
- [`docs/sprint0_implementation_plan.md`](docs/sprint0_implementation_plan.md) — konkreter Umsetzungsplan für Sprint 0 (Skelett).

## Schnellstart

Siehe [`backend/README.md`](backend/README.md).

## Stand

Sprint 0 — technisches Grundgerüst ohne fachliche Logik.
