"""Anwendungs-Konfiguration via pydantic-settings.

Liest ausschließlich Umgebungsvariablen mit Präfix ``REF4EP_`` und
optional eine ``.env``-Datei. ``get_settings()`` liefert einen
LRU-gecacheten Singleton; Tests können über ``Settings(...)`` eigene
Instanzen bauen und via ``create_app(settings)`` injizieren.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Pfade relativ zum Working-Directory ``backend/`` (siehe README).
    # ``../data`` ist damit das Repo-Wurzel-Verzeichnis ``data/``.
    database_url: str = "sqlite:///../data/ref4ep.db"
    session_secret: str = ""
    session_max_age: int = 7 * 24 * 60 * 60  # 7 Tage in Sekunden
    cookie_secure: bool = False
    storage_dir: str = "../data/storage"
    max_upload_mb: int = 100
    public_base_url: str = "http://localhost:8000"
    log_format: Literal["text", "json"] = "text"

    model_config = SettingsConfigDict(
        env_prefix="REF4EP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
