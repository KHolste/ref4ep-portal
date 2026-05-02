"""Gemeinsame Test-Fixtures.

Jeder Test bekommt eine frische SQLite-Datei in einem ``tmp_path`` und
eine FastAPI-App, die mit diesen Settings aufgebaut ist. Das
vermeidet Manipulation an Umgebungsvariablen und dem
``get_settings``-LRU-Cache.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ref4ep.api.app import create_app
from ref4ep.api.config import Settings

BACKEND_DIR = Path(__file__).resolve().parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
ALEMBIC_DIR = BACKEND_DIR / "alembic"


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_ref4ep.db"


@pytest.fixture
def settings(tmp_db_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_db_path}")


@pytest.fixture
def app(settings: Settings):
    return create_app(settings=settings)


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
