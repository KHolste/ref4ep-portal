"""Anwendungs-Konfiguration via pydantic-settings.

Liest ausschließlich Umgebungsvariablen mit Präfix ``REF4EP_`` und
optional eine ``.env``-Datei. ``get_settings()`` liefert einen
LRU-gecacheten Singleton; Tests können über ``Settings(...)`` eigene
Instanzen bauen und via ``create_app(settings)`` injizieren.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Konstante lebt in ``services/auth`` (fachliche Heimat: HMAC-Token-Logik).
# ``services/auth`` importiert keine ``config``-Module — der Import hier
# ist zirkelfrei.
from ref4ep.services.auth import MIN_SESSION_SECRET_LEN

# Absoluter Pfad zur ``.env``. ``pydantic-settings`` interpretierte den
# relativen Default ``.env`` zum Working-Directory des Prozesses — eine
# systemd-Unit mit ``WorkingDirectory=/opt/ref4ep-portal`` (statt
# ``/opt/ref4ep-portal/backend``) hätte die Datei verfehlt und damit
# einen ``REF4EP_SESSION_SECRET fehlt``-Crash produziert.
# ``parents[3]`` löst von ``backend/src/ref4ep/api/config.py`` auf
# ``backend/`` auf — dort liegt ``.env`` neben ``pyproject.toml``.
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    # Pfade relativ zum Working-Directory ``backend/`` (siehe README).
    # ``../data`` ist damit das Repo-Wurzel-Verzeichnis ``data/``.
    database_url: str = "sqlite:///../data/ref4ep.db"
    # Pflichtfeld: HMAC-Key für Session-Tokens. ≥ 32 Zeichen.
    # Beim Start ohne gesetzte Variable schlägt Settings() bewusst fehl
    # — kein stiller Default mit leerem Secret.
    session_secret: str
    # 7 Tage in Sekunden. Untergrenze 5 Min — verhindert
    # ``REF4EP_SESSION_MAX_AGE=0`` o. ä., das sofort ablaufende Sessions
    # erzeugen würde.
    session_max_age: int = Field(default=7 * 24 * 60 * 60, ge=300)
    # Sicherer Default: Cookies nur über HTTPS senden. Lokale
    # Entwicklung über HTTP muss ``REF4EP_COOKIE_SECURE=false``
    # explizit setzen, sonst speichert der Browser das Session-Cookie
    # nicht.
    cookie_secure: bool = True
    storage_dir: str = "../data/storage"
    max_upload_mb: int = 100
    public_base_url: str = "http://localhost:8000"
    log_format: Literal["text", "json"] = "text"
    # Verzeichnis, in dem das Hostsystem die Backups ablegt
    # (siehe systemd-Setup). Pfad muss nicht existieren — der
    # SystemStatusService meldet ein Fehlen als Warning.
    backup_dir: str = "/opt/ref4ep-backups"
    # Block 0033 — manueller Backup-Trigger.
    # Argumentliste, die der Webprozess via ``subprocess.run`` (ohne
    # Shell) ausführt, um den ``ref4ep-backup.service`` zu starten.
    # Defaults setzen auf eine eng definierte sudoers-Regel
    # (siehe ``infra/sudoers/ref4ep-backup.sudoers.example``).
    # Override per ``REF4EP_BACKUP_TRIGGER_COMMAND`` als
    # whitespace-getrennte Argumentliste.
    backup_trigger_command: tuple[str, ...] = (
        "/usr/bin/sudo",
        "-n",
        "/usr/bin/systemctl",
        "start",
        "ref4ep-backup.service",
    )
    backup_trigger_timeout_seconds: int = Field(default=30, ge=1, le=600)

    model_config = SettingsConfigDict(
        env_prefix="REF4EP_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("session_secret")
    @classmethod
    def _validate_session_secret(cls, value: str) -> str:
        if len(value) < MIN_SESSION_SECRET_LEN:
            raise ValueError(
                "REF4EP_SESSION_SECRET muss mindestens "
                f"{MIN_SESSION_SECRET_LEN} Zeichen haben "
                "(siehe .env.example und docs/server_operations.md)."
            )
        return value

    @field_validator("backup_trigger_command", mode="before")
    @classmethod
    def _coerce_backup_trigger_command(cls, value):
        """Erlaubt das Override per Env-Variable als
        Whitespace-getrennten String und konvertiert ihn zur Liste."""
        if isinstance(value, str):
            parts = value.split()
            return tuple(parts)
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("backup_trigger_command")
    @classmethod
    def _validate_backup_trigger_command(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("REF4EP_BACKUP_TRIGGER_COMMAND darf nicht leer sein.")
        first = value[0]
        if not first.startswith("/") or ".." in first:
            raise ValueError(
                "REF4EP_BACKUP_TRIGGER_COMMAND[0] muss ein absoluter Pfad sein "
                "(kein relatives Argument, kein '..')."
            )
        forbidden = {";", "|", "&", "$", "`", "\n", "\r", "<", ">"}
        for arg in value:
            if not isinstance(arg, str) or not arg:
                raise ValueError("REF4EP_BACKUP_TRIGGER_COMMAND-Eintrag darf nicht leer sein.")
            if any(ch in forbidden for ch in arg):
                raise ValueError(
                    "REF4EP_BACKUP_TRIGGER_COMMAND enthält Shell-Metazeichen — "
                    "nur literale Argumente erlaubt."
                )
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
