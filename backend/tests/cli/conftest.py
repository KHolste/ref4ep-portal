"""CLI-Test-Fixtures: setzt REF4EP_DATABASE_URL für die laufende CLI-Subroutine."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
from ref4ep.api.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
ALEMBIC_DIR = BACKEND_DIR / "alembic"


@pytest.fixture
def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    db = tmp_path / "cli_test.db"
    url = f"sqlite:///{db}"
    monkeypatch.setenv("REF4EP_DATABASE_URL", url)
    monkeypatch.setenv("REF4EP_SESSION_SECRET", "x" * 48)
    get_settings.cache_clear()
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    yield url
    get_settings.cache_clear()
